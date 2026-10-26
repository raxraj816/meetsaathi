import Combine
import CryptoKit
import Foundation

public struct PreflightReport: Sendable {
    public var micPermission: Bool
    public var levelDbfs: Double?
    public var quality: String?
    public var route: AudioRoute
    public var warnings: [String]
}

/// Coordinates one live session: server lifecycle, capture, encrypted spool, resumable upload, realtime events,
/// routes and private voice. Mirrors apps/android LiveSessionController. Never claims an unobserved state.
@MainActor
public final class LiveSessionController: ObservableObject {
    @Published public private(set) var session: SessionView?
    @Published public private(set) var truth: CaptureTruth = .off
    @Published public private(set) var elapsedMs: Int64 = 0
    @Published public private(set) var levelDbfs: Double = -120
    @Published public private(set) var online = true
    @Published public private(set) var insight: Insight?
    @Published public private(set) var transcript: [Utterance] = []
    @Published public private(set) var captionPreview: CaptionPreview?
    @Published public private(set) var status: (text: String, severity: String)?
    @Published public private(set) var route: AudioRoute
    @Published public private(set) var privateRouteVerified = false
    @Published public private(set) var pendingUploads = 0
    @Published public private(set) var finalizationMessage: String?
    @Published public private(set) var invalidatedClaims: Set<String> = []
    /// Consent withdrawal not yet acknowledged by the server: capture and uploads stay stopped until it is.
    @Published public private(set) var withdrawPending = false
    static let withdrawMarker = "withdraw_pending"

    let api: APIClient
    public let routes = AudioRoutes()
    private let keychain: Keychain
    private var capture: AudioCapture?
    private var spool: ChunkSpool?
    private var uploader: Uploader?
    private var realtime: RealtimeClient?
    private var voice: PrivateVoice?
    private var ticker: Timer?
    private var nextSeq: Int64 = 0
    private var origin = Date() { didSet { clockBox.set(origin) } }
    private let clockBox = ClockBox()
    private var buffersFlowing = false
    private var lastSpeech = Date.distantPast
    private var speakingSignalled = false
    private var captureSequence: SeqBox?
    private var locallyEnded = false
    private var stopInFlight = false
    private var recoveryTasks: [Task<Void, Never>] = []
    private var recoveryLoop: Task<Void, Never>?
    private var tickCount = 0

    public init(api: APIClient, keychain: Keychain) {
        self.api = api
        self.keychain = keychain
        self.route = routes.route
        routes.onChange = { [weak self] old, new, lost in
            Task { @MainActor in self?.routeChanged(old: old, new: new, lost: lost) }
        }
        routes.onInterruption = { [weak self] began in
            Task { @MainActor in if began { self?.captureFailed("OS_INTERRUPTION") } }
        }
        routes.start()
        route = routes.route
    }

    public var micGranted: Bool { AudioRoutes.recordPermissionGranted }

    private func setStatus(_ t: String?, _ sev: String = "info") { status = t.map { ($0, sev) } }

    private func routeChanged(old: AudioRoute, new: AudioRoute, lost: Bool) {
        route = new
        privateRouteVerified = routes.privateRouteVerified
        if (lost || old.privateOutputPresent) && !routes.privateRouteVerified {
            voice?.hardMute() // fail closed locally first, then tell the server
            realtime?.reportRouteLost()
            if old.privateOutputPresent { setStatus(L("status_voice_disconnected"), "warning") }
        }
        if old.input != new.input && (truth == .recording || truth == .recordingLocal) {
            setStatus(L("status_source_changed"), "warning")
        }
        if let s = session { Task { await postRoute(s.sessionId) } }
    }

    // ------------------------------------------------------------------ preflight
    public func preflight() async -> PreflightReport {
        var warnings: [String] = []
        guard micGranted else { return PreflightReport(micPermission: false, levelDbfs: nil, quality: nil, route: routes.route, warnings: [L("truth_mic_denied")]) }
        try? routes.configureForCapture()
        let probe = AudioCapture()
        let peak = LevelBox()
        probe.onFirstBuffer = { peak.gotFrames = true }
        probe.onLevel = { peak.update($0) }
        probe.onFailure = { _ in peak.failed = true }
        if probe.start() {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            probe.stop()
        }
        if peak.failed { warnings.append(L("preflight_mic_busy")) }
        if !peak.gotFrames { warnings.append(L("preflight_no_frames")) }
        let q = peak.gotFrames ? Signal.quality(peak.value) : nil
        if q == "POOR" || q == "SILENT_OR_BLOCKED" { warnings.append(L("preflight_poor")) }
        if routes.route.couplesInputAndOutput { warnings.append(L("preflight_headset_mic")) }
        warnings.append(L("preflight_laptop_headphones"))
        if capture == nil { routes.deactivate() }
        return PreflightReport(micPermission: true, levelDbfs: peak.gotFrames ? peak.value : nil, quality: q, route: routes.route, warnings: warnings)
    }

    public func capabilities(_ r: PreflightReport?) -> Capabilities {
        let rt = routes.route
        return Capabilities(micPermission: micGranted ? "granted" : "denied", inputRoute: micGranted ? rt.input : nil, outputRoute: rt.output,
                            outputDeviceName: rt.outputDeviceName, privateRouteVerified: routes.privateRouteVerified, measuredLevelDbfs: r?.levelDbfs)
    }

    public func capabilitiesHash(_ c: Capabilities) -> String {
        let d = (try? Wire.encoder.encode(c)) ?? Data()
        return String(SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined().prefix(32))
    }

    // ------------------------------------------------------------------ lifecycle
    public func attach(_ s: SessionView) {
        locallyEnded = PendingStop.load(from: spoolDir(s.sessionId)) != nil
        session = s
        transcript = []; captionPreview = nil; insight = nil; status = nil; finalizationMessage = nil
        refreshTruth()
        realtime?.stop()
        let rt = RealtimeClient(api: api, sessionId: s.sessionId, cursor: s.eventCursor ?? 0)
        rt.onEvent = { [weak self] ev in Task { @MainActor in self?.onEvent(ev) } }
        rt.onConnection = { [weak self] connected in
            Task { @MainActor in
                guard let self, self.session?.sessionId == s.sessionId else { return }
                if !connected { self.captionPreview = nil }
            }
        }
        rt.start()
        realtime = rt
        ticker?.invalidate()
        ticker = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    private func spoolDir(_ sid: String) -> URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("spool/\(sid)")
    }

    public func beginCapture(_ s: SessionView, ingest: IngestCredential) {
        attach(s)
        let sp = ChunkSpool(dir: spoolDir(s.sessionId), sealer: Sealer(key: keychain.symmetricKey("spool_key_v1")), sessionId: s.sessionId)
        spool = sp
        let seqFile = spoolDir(s.sessionId).appendingPathComponent("next_seq")
        nextSeq = (try? String(contentsOf: seqFile, encoding: .utf8)).flatMap { Int64($0) } ?? ingest.resumeCursor
        // Monotonic session clock continues from the server watermark; pauses show as gaps, never overlaps.
        origin = Date().addingTimeInterval(-Double(s.sourceWatermarkMs) / 1000)
        startUploader(s.sessionId, token: ingest.token)
        ensureVoice()
        startMicrophone()
    }

    private func clock() -> Int64 { Int64(Date().timeIntervalSince(origin) * 1000) }

    /// Session-clock position for a user note, only while this device is capturing (otherwise the note has no moment).
    public func noteAtMs() -> Int64? { capture != nil && !locallyEnded ? clock() : nil }

    private func startUploader(_ sid: String, token: String?) {
        guard let sp = spool else { return }
        let api = self.api
        let up = Uploader(spool: sp, transport: URLSessionChunkTransport(baseURL: api.baseURL, session: api.session), sessionId: sid,
                          deviceId: api.deviceId, initialToken: token) { _ in
            let c: IngestCredential? = try? await api.send("POST", "/v1/sessions/\(sid)/ingest-token")
            return c?.token
        }
        let previous = uploader
        Task {
            await previous?.stop()
            guard self.session?.sessionId == sid else { return }
            await up.setOnStatus { [weak self] st in Task { @MainActor in self?.uploadStatus(st) } }
            await up.start()
        }
        uploader = up
    }

    private func uploadStatus(_ st: UploadStatus) {
        online = st.online
        pendingUploads = st.pending
        refreshTruth()
        if st.stoppedReason == "DEVICE_REVOKED" { stopMicrophone(); setStatus(L("status_device_revoked"), "error") }
    }

    private func startMicrophone() {
        guard capture == nil, let sp = spool, let sid = session?.sessionId else { return }
        guard micGranted else { captureFailed("PERMISSION_REVOKED"); return }
        do { try routes.configureForCapture() } catch { captureFailed("INPUT_LOST"); return }
        let cap = AudioCapture()
        cap.clockOrigin = origin
        let seqFile = spoolDir(sid).appendingPathComponent("next_seq")
        let box = SeqBox(nextSeq)
        captureSequence = box
        cap.onFirstBuffer = { [weak self] in Task { @MainActor in self?.buffersFlowing = true; self?.refreshTruth(); await self?.confirmRecording() } }
        cap.onChunk = { [weak self] start, dur, pcm, level in
            let seq = box.take()
            switch sp.append(seq: seq, captureStartMs: start, durationMs: dur, sampleRate: 16000, pcm: pcm) {
            case .stored: try? String(seq + 1).write(to: seqFile, atomically: true, encoding: .utf8)
            case .storageFull:
                box.giveBack()
                Task { @MainActor in self?.setStatus(L("status_storage_full"), "error"); await self?.end() }
            }
            Task { @MainActor in self?.nextSeq = box.peek(); self?.speech(level) }
        }
        cap.onLevel = { [weak self] l in Task { @MainActor in self?.levelDbfs = l } }
        cap.onFailure = { [weak self] r in Task { @MainActor in self?.captureFailed(r) } }
        capture = cap
        if !cap.start() { capture = nil }
    }

    private func speech(_ level: Double) {
        if level > -38 { lastSpeech = Date(); if voice?.isSpeaking == true { voice?.hardMute() } } // barge-in (UNI-015)
        let speaking = Date().timeIntervalSince(lastSpeech) < 1.5
        if speaking != speakingSignalled { speakingSignalled = speaking; realtime?.signalUserSpeaking(speaking) }
    }

    private func confirmRecording() async {
        guard let s = session else { return }
        struct Body: Encodable { var state = "RECORDING"; var reason = "AUDIO_CALLBACK_CONFIRMED" }
        if let v: SessionView = try? await api.send("POST", "/v1/sessions/\(s.sessionId)/capture-state", body: Body()) { session = v; refreshTruth() }
    }

    func captureFailed(_ reason: String) {
        guard let s = session, capture != nil else { return }
        stopMicrophone()
        let last = nextSeq - 1
        setStatus(L("status_capture_interrupted", clockString(clock())), "error")
        struct Body: Encodable { var state = "INTERRUPTED"; var reason: String; var atMs: Int64; var lastSequence: Int64 }
        Task {
            if let v: SessionView = try? await api.send("POST", "/v1/sessions/\(s.sessionId)/capture-state",
                                                        body: Body(reason: reason, atMs: clock(), lastSequence: last)) { session = v }
            refreshTruth()
        }
    }

    private func stopMicrophone() {
        capture?.stop()
        // stop() synchronously flushes the partial chunk on the capture queue. The main-actor
        // callbacks may still be queued, so read its synchronized counter before publishing a watermark.
        if let sequence = captureSequence { nextSeq = sequence.peek() }
        captureSequence = nil
        capture = nil
        buffersFlowing = false
        voice?.hardMute()
        routes.deactivate()
        refreshTruth()
    }

    public func pause() async throws {
        guard let s = session else { return }
        stopMicrophone() // microphone released BEFORE the network call
        struct Body: Encodable { var stopWatermarkSequence: Int64; var atMs: Int64 }
        let v: SessionView = try await api.send("POST", "/v1/sessions/\(s.sessionId)/pause", body: Body(stopWatermarkSequence: nextSeq - 1, atMs: clock()),
                                                idempotencyKey: APIClient.newKey())
        session = v
        if let ing = v.ingestCredential { startUploader(v.sessionId, token: ing.token) }
        refreshTruth()
    }

    public func resume() async throws {
        guard let s = session else { return }
        let report = await preflight()
        let caps = capabilities(report)
        struct Body: Encodable { var capabilitiesHash: String; var capabilities: Capabilities; var atMs: Int64 }
        let v: SessionView = try await api.send("POST", "/v1/sessions/\(s.sessionId)/resume", body: Body(capabilitiesHash: capabilitiesHash(caps),
                                                capabilities: caps, atMs: clock()), idempotencyKey: APIClient.newKey())
        session = v
        if let ing = v.ingestCredential { startUploader(v.sessionId, token: ing.token) }
        startMicrophone()
    }

    /// End: microphone stops at once; finalization continues separately (ADR-010). Works offline; stable key.
    public func end() async {
        guard let s = session else { return }
        stopMicrophone()
        locallyEnded = true
        truth = .stopped
        finalizationMessage = L("status_ended")
        let dir = spoolDir(s.sessionId)
        let body = PendingStop.load(from: dir) ?? PendingStop(finalSequence: nextSeq - 1, atMs: clock())
        do {
            try body.save(to: dir)
        } catch {
            setStatus(L("status_stop_not_saved"), "error")
            return
        }
        await syncStop(s.sessionId, body: body)
    }

    /// A participant objected (CON-013): the microphone and uploads stop first, then the server records the withdrawal,
    /// revokes ingest and stops the session. Unsent audio is never uploaded afterwards, so this session's spool is purged.
    /// Offline, a durable marker keeps the withdrawal pending; recovery retries it and never uploads that spool.
    @discardableResult
    public func withdrawConsent() async -> Bool {
        guard let s = session else { return false }
        stopMicrophone()
        locallyEnded = true
        truth = .stopped
        withdrawPending = true
        let previous = uploader
        uploader = nil
        await previous?.stop()
        let dir = spoolDir(s.sessionId)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? Data("1".utf8).write(to: dir.appendingPathComponent(Self.withdrawMarker))
        do {
            let v: SessionView = try await api.send("POST", "/v1/sessions/\(s.sessionId)/consent/withdraw", body: ["reason": "PARTICIPANT_WITHDREW"],
                                                    idempotencyKey: "withdraw-\(s.sessionId)")
            try? FileManager.default.removeItem(at: dir)
            spool = nil
            session = v
            withdrawPending = false
            status = nil
            finalizationMessage = L("status_consent_withdrawn")
            return true
        } catch {
            setStatus(L("status_withdraw_pending"), "error")
            return false
        }
    }

    private func syncStop(_ sid: String, body: PendingStop) async {
        guard !stopInFlight else { return }
        stopInFlight = true
        defer { stopInFlight = false }
        do {
            let v: SessionView = try await api.send("POST", "/v1/sessions/\(sid)/stop", body: body,
                                                    idempotencyKey: "end-\(sid)")
            PendingStop.clear(from: spoolDir(sid))
            session = v
            if let ing = v.ingestCredential { startUploader(v.sessionId, token: ing.token) }
        } catch APIError.offline {
            setStatus(L("status_stop_offline"), "warning")
        } catch let e as APIError { setStatus(e.userMessage, "error") }
        catch { setStatus(L("status_stop_retrying"), "warning") }
    }

    public func setControls(_ body: [String: JSONValue]) async throws {
        guard let s = session else { return }
        let v: SessionView = try await api.send("PATCH", "/v1/sessions/\(s.sessionId)/controls", body: body)
        session = v
        if v.mutedUntil != nil { insight = nil }
    }

    public func verifyPrivateRoute() -> Bool {
        ensureVoice()
        return voice?.playTestSample() ?? false
    }

    private func ensureVoice() {
        if voice == nil { let box = clockBox; voice = PrivateVoice(routes: routes, clockMs: { box.ms() }) }
        voice?.onPlayback = { [weak self] a, b in Task { @MainActor in await self?.reportPlayback(a, b) } }
    }

    public func confirmHeardPrivateSample() {
        routes.confirmPrivateRoute()
        privateRouteVerified = routes.privateRouteVerified
        if let s = session { Task { await postRoute(s.sessionId) } }
    }

    private func postRoute(_ sid: String) async {
        let r = routes.route
        var body: [String: JSONValue] = ["input_route": .string(r.input), "output_route": .string(r.output),
                                         "private_route_verified": .bool(routes.privateRouteVerified), "audio_quality": .string(Signal.quality(levelDbfs))]
        if let n = r.outputDeviceName { body["device_name"] = .string(n) }
        _ = try? await api.raw("POST", "/v1/sessions/\(sid)/route", body: body)
    }

    private func reportPlayback(_ a: Int64, _ b: Int64) async {
        guard let s = session, b > a else { return }
        _ = try? await api.raw("POST", "/v1/sessions/\(s.sessionId)/voice/playback-window", body: ["start_ms": JSONValue.number(Double(a)), "end_ms": .number(Double(b))])
    }

    public func saveMoment(_ text: String = "") async -> Bool {
        guard let s = session else { return false }
        struct Note: Encodable { var kind = "BOOKMARK"; var text: String; var clientId: String; var atMs: Int64; var windowMs: Int64 = 30000 }
        return (try? await api.raw("POST", "/v1/sessions/\(s.sessionId)/notes", body: Note(text: text, clientId: UUID().uuidString, atMs: clock()))) != nil
    }

    public func feedback(_ insightId: String, _ value: String) async {
        guard let s = session else { return }
        _ = try? await api.raw("POST", "/v1/sessions/\(s.sessionId)/insights/\(insightId)/feedback", body: ["value": value], idempotencyKey: APIClient.newKey())
        insight = nil
    }

    public func detach() {
        ticker?.invalidate()
        realtime?.stop(); realtime = nil
    }

    public func resetForSignOut(purgeLocal: Bool = false) {
        stopMicrophone()
        locallyEnded = true
        detach()
        recoveryTasks.forEach { $0.cancel() }; recoveryTasks.removeAll()
        recoveryLoop?.cancel(); recoveryLoop = nil
        let previous = uploader
        uploader = nil
        Task { await previous?.stop() }
        if purgeLocal {
            let root = spoolDir("_").deletingLastPathComponent()
            try? FileManager.default.removeItem(at: root)
        }
        spool = nil; session = nil; transcript = []; captionPreview = nil; insight = nil
        truth = .off; pendingUploads = 0; elapsedMs = 0
    }

    private func tick() {
        if captionPreview?.expired() == true { captionPreview = nil }
        tickCount += 1
        if withdrawPending && tickCount % 5 == 0 { Task { await withdrawConsent() } }
        if !withdrawPending, let sid = session?.sessionId, let body = PendingStop.load(from: spoolDir(sid)), !stopInFlight {
            Task { await syncStop(sid, body: body) }
        }
        if truth == .recording || truth == .recordingLocal { elapsedMs = clock() }
        if let i = insight, let exp = ISO8601DateFormatter().date(from: i.expiresAt), exp < Date() { insight = nil }
    }

    private func refreshTruth() {
        guard let s = session else { return }
        if locallyEnded { truth = .stopped; return }
        truth = captureTruth(server: SessionState.parse(s.state), localBuffersFlowing: buffersFlowing && capture != nil, online: online,
                             micPermission: micGranted || s.captureSource == "NONE")
    }

    // ------------------------------------------------------------------ events
    func onEvent(_ e: EventEnvelope) {
        if let id = e.sessionId, id != session?.sessionId { return }
        let p = e.payload ?? .null
        switch e.type {
        case "session.state_changed":
            if let cur = p["current"]?.string { session?.state = cur; refreshTruth() }
        case "session.status":
            setStatus(p["message"]?.string, p["severity"]?.string ?? "info")
        case "session.finalization_progress":
            finalizationMessage = p["message"]?.string
        case "transcript.preview":
            guard let run = p["run_id"]?.string, let id = p["preview_id"]?.string, let text = p["text"]?.string,
                  let startMs = p["start_ms"]?.int64, startMs >= 0 else { return }
            captionPreview = CaptionPreview(runId: run, previewId: id, text: text, startMs: startMs)
        case "transcript.preview_clear":
            if captionPreview?.clearedBy(run: p["run_id"]?.string, preview: p["preview_id"]?.string) == true { captionPreview = nil }
        case "transcript.partial", "transcript.final":
            guard let id = p["utterance_id"]?.string, let startMs = p["start_ms"]?.int64,
                  let endMs = p["end_ms"]?.int64, startMs >= 0, endMs > startMs else { return }
            let isFinal = p["is_final"]?.bool ?? false
            let alias = p["speaker_alias"]?.string
            let verified = p["speaker_verified"]?.bool ?? false
            let display = alias.map { verified ? $0 : ($0 == "Unassigned" ? L("speaker_unassigned") : L("speaker_unconfirmed", $0)) } ?? L("speaker_unassigned")
            let u = Utterance(utteranceId: id, revision: p["revision"]?.int ?? 1, startMs: startMs,
                              endMs: endMs, text: p["text"]?.string ?? "", isFinal: isFinal, speakerAlias: alias,
                              speakerDisplay: display, speakerVerified: verified,
                              uncertain: (p["overlap"]?.bool ?? false) || (p["low_confidence"]?.bool ?? false), label: isFinal ? "Final" : "Provisional")
            transcript = Array((transcript.filter { $0.utteranceId != id } + [u]).sorted { $0.startMs < $1.startMs }.suffix(200))
        case "insight.delivered":
            guard let d = try? Wire.encoder.encode(p), let ins = try? Wire.decoder.decode(Insight.self, from: d) else { return }
            insight = ins
            if ins.outputChannel != "TEXT", let vt = ins.voiceText { voice?.speak(vt, maxSeconds: ins.voiceMaxSeconds ?? 7) } // private route only
        case "insight.expired":
            if insight?.insightId == p["insight_id"]?.string { insight = nil }
        case "voice.route_lost":
            voice?.hardMute(); setStatus(L("status_voice_disconnected"), "warning")
        case "memory.invalidated":
            invalidatedClaims.formUnion((p["claim_ids"]?.array ?? []).compactMap(\.string))
        default: break
        }
    }

    /// UNI-004: after process death, upload already-permitted unacknowledged chunks; never restart the microphone.
    public func recoverSpools() {
        guard recoveryLoop == nil else { return }
        recoveryLoop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.recoverSpoolsOnce()
                try? await Task.sleep(nanoseconds: 10_000_000_000)
            }
        }
    }

    private func recoverSpoolsOnce() async {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("spool")
        let dirs = (try? FileManager.default.contentsOfDirectory(atPath: root.path)) ?? []
        for sid in dirs {
            if session?.sessionId == sid { continue }
            let dir = root.appendingPathComponent(sid)
            let recovery = Task {
                var v: SessionView
                do { v = try await api.send("GET", "/v1/sessions/\(sid)") }
                catch APIError.server(let code, _) where code == 404 || code == 410 {
                    try? FileManager.default.removeItem(at: dir); return
                } catch { return } // Offline/5xx/expired auth never authorizes local audio deletion.
                if self.session?.sessionId == sid { return }
                if FileManager.default.fileExists(atPath: dir.appendingPathComponent(LiveSessionController.withdrawMarker).path) {
                    let done = (try? await api.raw("POST", "/v1/sessions/\(sid)/consent/withdraw", body: ["reason": "PARTICIPANT_WITHDREW"],
                                                    idempotencyKey: "withdraw-\(sid)")) != nil
                    if done { try? FileManager.default.removeItem(at: dir) }
                    return
                }
                if let pending = PendingStop.load(from: dir) {
                    do {
                        v = try await api.send("POST", "/v1/sessions/\(sid)/stop", body: pending, idempotencyKey: "end-\(sid)")
                        PendingStop.clear(from: dir)
                    } catch { return }
                }
                let st = SessionState.parse(v.state)
                if st == .RECORDING || st == .STARTING {
                    struct Body: Encodable { var state = "INTERRUPTED"; var reason = "PROCESS_RESTORED"; var lastSequence: Int64 }
                    let next = (try? String(contentsOf: dir.appendingPathComponent("next_seq"), encoding: .utf8)).flatMap(Int64.init) ?? 0
                    _ = try? await api.raw("POST", "/v1/sessions/\(sid)/capture-state", body: Body(lastSequence: next - 1))
                }
                let sp = ChunkSpool(dir: dir, sealer: Sealer(key: keychain.symmetricKey("spool_key_v1")), sessionId: sid)
                let api = self.api
                let up = Uploader(spool: sp, transport: URLSessionChunkTransport(baseURL: api.baseURL, session: api.session), sessionId: sid,
                                  deviceId: api.deviceId, initialToken: nil) { _ in
                    let c: IngestCredential? = try? await api.send("POST", "/v1/sessions/\(sid)/ingest-token"); return c?.token
                }
                for _ in 0..<20 where !sp.pendingSequences().isEmpty { _ = await up.pass() }
                if sp.pendingSequences().isEmpty && SessionStateMachine.ended.contains(st) { sp.purgeAll() }
            }
            recoveryTasks.append(recovery)
        }
        for task in recoveryTasks { await task.value }
        recoveryTasks.removeAll()
    }
}

final class LevelBox: @unchecked Sendable {
    var value = -120.0
    var gotFrames = false
    var failed = false
    func update(_ v: Double) { value = max(value, v) }
}

final class ClockBox: @unchecked Sendable {
    private var origin = Date()
    private let lock = NSLock()
    func set(_ d: Date) { lock.lock(); origin = d; lock.unlock() }
    func ms() -> Int64 { lock.lock(); defer { lock.unlock() }; return Int64(Date().timeIntervalSince(origin) * 1000) }
}

final class SeqBox: @unchecked Sendable {
    private var v: Int64
    private let lock = NSLock()
    init(_ v: Int64) { self.v = v }
    func take() -> Int64 { lock.lock(); defer { lock.unlock() }; let r = v; v += 1; return r }
    func giveBack() { lock.lock(); v -= 1; lock.unlock() }
    func peek() -> Int64 { lock.lock(); defer { lock.unlock() }; return v }
}
