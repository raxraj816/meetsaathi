import Foundation

public enum Tab: String, CaseIterable, Sendable { case home, memories, ask, you
    public var label: String { L("tab_\(rawValue)") }
}

public enum Screen: Hashable, Sendable {
    case contextChooser, preflight, liveAsk, transcript(String), voice, recap(String), speakers(String), study, interview, mock(String)
    case memory(String), share(String), sessions, projects, project(String), insight(String, String), insights(String)
}

/// Session setup draft. Each control dimension is independent (ADR-003). Defaults: Listener + Text (ADR-004).
public struct Draft: Sendable {
    public var context = "MEETING"
    public var preset: String?
    public var title = ""
    public var captureSource = "PHONE_MIC"
    public var participantsInformed = false
    public var recordingAllowed: Bool?   // Interview: "May this be recorded?"
    public var aiAllowed: Bool?          // Interview: "Is AI permitted?" (unknown = no)
    public var aiConsent = false
    public var assistance = "LISTENER"
    public var intensity = "QUIET"
    public var output = "TEXT"
    public var sensitiveOptIn = false
    public var spaceId: String?
    public var projectId: String?
    public init() {}
}

public struct ExportState: Equatable, Sendable { public var exportId: String; public var status: String; public var scope: String }

@MainActor
public final class AppModel: ObservableObject {
    @Published public var signedIn: Bool
    @Published public var showSample = false
    @Published public var tab: Tab = .home
    @Published public var path: [Screen] = []
    @Published public var liveOpen = false
    @Published public var me: Me?
    @Published public var preferences: [String: JSONValue] = [:]
    @Published public var recent: [SessionSummary] = []
    @Published public var active: [SessionSummary] = []
    @Published public var draft = Draft()
    @Published public var preflight: PreflightReport?
    @Published public var preflightRunning = false
    @Published public var busy = false
    @Published public var message: String?
    @Published public var askResult: AskResponse?
    @Published public var explain: JSONValue?
    @Published public var recap: JSONValue?
    @Published public var speakers: [JSONValue] = []
    @Published public var memories: [JSONValue] = []
    @Published public var matchingSessions: [JSONValue] = []
    @Published public var utterances: [Utterance] = []
    @Published public var study: JSONValue?
    @Published public var lastAttempt: JSONValue?
    @Published public var reviews: [JSONValue] = []
    @Published public var mock: JSONValue?
    @Published public var mocks: [JSONValue] = []
    @Published public var goals: [JSONValue] = []
    @Published public var devices: [JSONValue] = []
    @Published public var projects: [JSONValue] = []
    @Published public var claim: JSONValue?
    @Published public var insightDetail: JSONValue?
    @Published public var insights: [JSONValue]?
    @Published public var sharePreview: JSONValue?
    @Published public var shareLink: JSONValue?
    @Published public var shares: [JSONValue] = []
    @Published public var project: JSONValue?
    @Published public var brief: JSONValue?
    @Published public var decisions: [JSONValue] = []
    @Published public var sessions: [SessionSummary] = []
    @Published public var sessionsCursor: String?
    @Published public var sessionsLoaded = false
    @Published public var export: ExportState?
    @Published public var exportData: Data?

    public let api: APIClient
    public let live: LiveSessionController
    public let evidence: EvidencePlayer

    public init(baseURL: URL, keychain: Keychain = Keychain()) {
        api = APIClient(baseURL: baseURL, tokens: KeychainTokenStore(keychain))
        live = LiveSessionController(api: api, keychain: keychain)
        evidence = EvidencePlayer(api: api)
        signedIn = api.isSignedIn
        api.onSignedOut = { [weak self] in Task { @MainActor in self?.live.resetForSignOut(); self?.evidence.stop(); self?.signedIn = false } }
        if signedIn { live.recoverSpools(); Task { await refreshHome() } }
    }

    func run(_ op: @escaping () async throws -> Void) {
        Task {
            busy = true
            defer { busy = false }
            do { try await op() } catch let e as APIError { message = e.userMessage } catch { message = L("error_generic") }
        }
    }

    public func push(_ s: Screen) { evidence.stop(); path.append(s) }
    public func pop() { evidence.stop(); if !path.isEmpty { path.removeLast() } }

    private func items(_ path: String) async throws -> [JSONValue] { (try await api.send("GET", path, as: JSONValue.self))["items"]?.array ?? [] }
    private static func enc(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed.subtracting(CharacterSet(charactersIn: "+&="))) ?? s }

    // ---------------------------------------------------------------- auth & home
    public func signIn(email: String, password: String, create: Bool, name: String?, ageConfirmed: Bool = false) {
        run {
            let device = DeviceInfo.name
            if create { try await self.api.register(email: email, password: password, name: name, deviceName: device, ageConfirmed: ageConfirmed) }
            else { try await self.api.login(email: email, password: password, deviceName: device) }
            self.signedIn = true
            self.live.recoverSpools()
            await self.refreshHome()
        }
    }

    public func signOut() { run {
        if let s = self.live.session, SessionStateMachine.active.contains(SessionState.parse(s.state)) { await self.live.end() }
        self.live.resetForSignOut()
        self.evidence.stop()
        await self.api.logout(); self.signedIn = false
        self.me = nil; self.recent = []; self.memories = []; self.askResult = nil; self.recap = nil; self.path = []
    } }

    public func refreshHome() async {
        if let m: JSONValue = try? await api.send("GET", "/v1/me") {
            if let d = try? Wire.encoder.encode(m), let parsed = try? Wire.decoder.decode(Me.self, from: d) { me = parsed }
            if case .object(let p) = m["preferences"] ?? .null { preferences = p }
        }
        recent = (try? await api.send("GET", "/v1/sessions?limit=6", as: Page<SessionSummary>.self))?.items ?? []
        active = (try? await api.send("GET", "/v1/sessions?active=true&limit=3", as: Page<SessionSummary>.self))?.items ?? []
    }

    // ---------------------------------------------------------------- preferences (U13)
    public func pref(_ key: String) -> String? { preferences[key]?.string }
    public func intensityPref(_ ctx: String) -> String? { preferences["default_intensity_by_context"]?[ctx]?.string }

    public func savePrefs(_ values: [String: JSONValue], silent: Bool = false) {
        run {
            let r: JSONValue = try await self.api.send("PUT", "/v1/me/preferences", body: ["prefs": JSONValue.object(values)], idempotencyKey: APIClient.newKey())
            if case .object(let p) = r["prefs"] ?? .null { self.preferences = p }
            if !silent { self.message = L("prefs_saved") }
        }
    }

    public func setDefaultIntensity(_ ctx: String, _ v: String) {
        var cur: [String: JSONValue] = [:]
        if case .object(let o) = preferences["default_intensity_by_context"] ?? .null { cur = o }
        cur[ctx] = .string(v)
        savePrefs(["default_intensity_by_context": .object(cur)])
    }

    // ---------------------------------------------------------------- start flow
    public func chooseContext(_ ctx: String, preset: String?) {
        if let s = live.session, SessionStateMachine.active.contains(SessionState.parse(s.state)) {
            message = L("toast_end_current_first")
            liveOpen = true
            return
        }
        var d = Draft()
        d.context = ctx; d.preset = preset
        d.captureSource = ctx == "CONVERSATION" ? "NONE" : "PHONE_MIC"
        let kind = ctx == "LEARNING" ? "LEARNING" : (ctx == "CONVERSATION" ? "PERSONAL" : "WORK")
        d.spaceId = me?.spaces.first { $0.kind == kind }?.spaceId ?? me?.spaces.first?.spaceId
        // Saved defaults pre-fill choices only; AI consent, interview rules and the private-route test are still asked.
        d.assistance = ctx == "INTERVIEW" ? "LISTENER" : (pref("default_assistance") ?? "LISTENER")
        d.intensity = intensityPref(ctx) ?? (d.assistance == "COMPANION" ? "BALANCED" : "QUIET")
        d.output = pref("default_output") ?? "TEXT"
        draft = d
        preflight = nil
        if pref("last_context") != ctx { savePrefs(["last_context": .string(ctx)], silent: true) }
        loadProjects()
        push(.preflight)
    }

    public func runPreflight() {
        Task { preflightRunning = true; preflight = await live.preflight(); preflightRunning = false }
    }

    public func blockers() -> [String] {
        let d = draft
        guard d.captureSource != "NONE" else { return [] }
        var out: [String] = []
        if !live.micGranted { out.append(L("blocker_mic")) }
        if d.context == "INTERVIEW" && d.recordingAllowed != true { out.append(L("blocker_interview_recording")) }
        if !d.participantsInformed { out.append(L("blocker_notice")) }
        if d.context == "INTERVIEW" && d.aiAllowed != true && d.assistance != "LISTENER" { out.append(L("blocker_interview_ai")) }
        if d.context != "INTERVIEW" && !d.aiConsent && d.assistance != "LISTENER" { out.append(L("blocker_ai_consent")) }
        if d.output != "TEXT" && !live.privateRouteVerified { out.append(L("blocker_private_route")) }
        if preflight == nil { out.append(L("blocker_audio_check")) }
        return out
    }

    struct CreateIn: Encodable {
        var spaceId: String; var context: String; var title: String?; var captureSource: String; var processingRegion: String
        var preset: String?; var projectId: String?; var interviewMode: String?
    }
    struct ConsentIn: Encodable { var captureBasis: String; var noticesAttested: Bool; var aiAssistancePermitted: Bool; var processingDisclosureVersion: String }
    struct ConsentOut: Decodable { var receiptId: String; var capturePermitted: Bool; var aiAssistancePermitted: Bool }
    struct StartIn: Encodable {
        var consentReceiptId: String; var capabilitiesHash: String; var capabilities: Capabilities
        var assistanceMode: String; var proactiveIntensity: String; var outputMode: String; var sensitiveOptIn: Bool
    }

    public func startSession() {
        run {
            let d = self.draft
            guard let me = self.me, let space = d.spaceId else { return }
            let region = me.tenant["residency_region"]?.string ?? "ap-south-1"
            let mode: String? = d.context == "INTERVIEW" ? (d.captureSource == "NONE" ? "REFLECTION" : "LIVE") : nil
            let created: SessionView = try await self.api.send("POST", "/v1/sessions", body: CreateIn(spaceId: space, context: d.context,
                title: d.title.isEmpty ? nil : d.title, captureSource: d.captureSource, processingRegion: region, preset: d.preset,
                projectId: d.projectId, interviewMode: mode), idempotencyKey: APIClient.newKey())
            if d.captureSource == "NONE" {
                self.live.attach(created); self.path = []; self.liveOpen = true; return
            }
            let receipt: ConsentOut = try await self.api.send("POST", "/v1/sessions/\(created.sessionId)/consent-receipts", body: ConsentIn(
                captureBasis: d.participantsInformed ? "PARTICIPANTS_INFORMED" : "UNKNOWN", noticesAttested: d.participantsInformed,
                aiAssistancePermitted: d.context == "INTERVIEW" ? d.aiAllowed == true : d.aiConsent, processingDisclosureVersion: me.processingDisclosureVersion),
                idempotencyKey: APIClient.newKey())
            guard receipt.capturePermitted else { self.message = L("error_recording_not_authorized"); return }
            let caps = self.live.capabilities(self.preflight)
            let started: SessionView = try await self.api.send("POST", "/v1/sessions/\(created.sessionId)/start", body: StartIn(
                consentReceiptId: receipt.receiptId, capabilitiesHash: self.live.capabilitiesHash(caps), capabilities: caps,
                assistanceMode: d.assistance, proactiveIntensity: d.assistance == "COMPANION" ? d.intensity : "QUIET", outputMode: d.output,
                sensitiveOptIn: d.sensitiveOptIn), idempotencyKey: APIClient.newKey())
            guard let ing = started.ingestCredential else { return }
            self.live.beginCapture(started, ingest: ing)
            self.path = []
            self.liveOpen = true
        }
    }

    public func openActive(_ id: String) {
        run { let v: SessionView = try await self.api.send("GET", "/v1/sessions/\(id)"); self.live.attach(v); self.liveOpen = true }
    }

    // ---------------------------------------------------------------- live actions
    public func end() {
        run {
            let sid = self.live.session?.sessionId
            await self.live.end()
            self.liveOpen = false
            if let sid { self.tab = .home; self.recap = nil; self.path = [.recap(sid)]; try await self.loadRecap(sid) }
        }
    }

    /// CC-014: capture stops first (same as End); the user stays on Live to keep writing their own notes.
    public func stopKeepNotes() { run { await self.live.end() } }

    public func finishToRecap() {
        guard let sid = live.session?.sessionId else { return }
        liveOpen = false; tab = .home; recap = nil; askResult = nil; path = [.recap(sid)]
        reloadRecap(sid)
    }

    /// Someone objected to recording: stop now, record the withdrawal, never upload the rest (CON-013).
    public func withdrawConsent() {
        run {
            guard let sid = self.live.session?.sessionId else { return }
            if await self.live.withdrawConsent() {
                self.message = L("toast_consent_withdrawn")
                self.liveOpen = false
                self.tab = .home; self.recap = nil; self.path = [.recap(sid)]
                try await self.loadRecap(sid)
            }
        }
    }

    public func switchContext(_ ctx: String) {
        run {
            guard let sid = self.live.session?.sessionId else { return }
            let v: SessionView = try await self.api.send("POST", "/v1/sessions/\(sid)/context", body: ["context": ctx])
            self.live.attach(v)
            self.message = L("toast_context_switched")
        }
    }

    public func pause() { run { try await self.live.pause() } }
    public func resume() { run { try await self.live.resume() } }
    public func saveMoment() { run { self.message = await self.live.saveMoment() ? L("toast_moment_saved") : L("toast_moment_failed") } }
    public func mute(_ minutes: Int) { run { try await self.live.setControls(["mute_minutes": .integer(Int64(minutes))]) } }
    public func unmute() { run { try await self.live.setControls(["unmute": .bool(true)]) } }
    public func setOutput(_ o: String) { run { try await self.live.setControls(["output_mode": .string(o)]) } }
    public func setAssistance(_ mode: String, _ intensity: String) {
        run { try await self.live.setControls(["assistance_mode": .string(mode), "proactive_intensity": .string(intensity)]) }
    }
    public func feedback(_ id: String, _ v: String) { run { await self.live.feedback(id, v) } }

    public func addNote(_ text: String, recollection: Bool) {
        run {
            guard let sid = self.live.session?.sessionId else { return }
            struct N: Encodable { var kind: String; var text: String; var clientId = UUID().uuidString; var atMs: Int64? }
            try await self.api.raw("POST", "/v1/sessions/\(sid)/notes", body: N(kind: recollection ? "RECOLLECTION" : "NOTE", text: text,
                                                                                  atMs: recollection ? nil : self.live.noteAtMs()))
            self.message = recollection ? L("toast_recollection_saved") : L("toast_note_saved")
        }
    }

    public func explainThis() {
        run {
            guard let sid = self.live.session?.sessionId else { return }
            self.explain = try await self.api.send("POST", "/v1/sessions/\(sid)/explain", body: ["window_seconds": 60], as: JSONValue.self)
        }
    }

    // ---------------------------------------------------------------- ask
    struct AskIn: Encodable { var question: String; var mode: String; var scope: String; var scopeId: String? }
    public func ask(_ q: String, mode: String, scope: String, scopeId: String?) {
        run {
            if scope == "CURRENT_SESSION", let sid = self.live.session?.sessionId {
                self.askResult = try await self.api.send("POST", "/v1/sessions/\(sid)/ask", body: AskIn(question: q, mode: mode, scope: scope, scopeId: nil))
            } else {
                self.askResult = try await self.api.send("POST", "/v1/ask", body: AskIn(question: q, mode: mode, scope: scope, scopeId: scopeId))
            }
        }
    }

    /// Ask scoped to one session, live or finished ("Ask this meeting", "What did I miss?").
    public func askSession(_ sid: String, _ q: String, mode: String) {
        run { self.askResult = try await self.api.send("POST", "/v1/sessions/\(sid)/ask", body: AskIn(question: q, mode: mode, scope: "CURRENT_SESSION", scopeId: nil)) }
    }

    // ---------------------------------------------------------------- transcript, recap, speakers
    public func openTranscript(_ sid: String) { utterances = []; loadTranscript(sid); push(.transcript(sid)) }
    public func loadTranscript(_ sid: String) {
        run { self.utterances = (try await self.api.send("GET", "/v1/sessions/\(sid)/utterances", as: Page<Utterance>.self)).items }
    }

    public func correct(_ sid: String, _ u: Utterance, _ text: String) {
        run {
            try await self.api.raw("PATCH", "/v1/sessions/\(sid)/utterances/\(u.utteranceId)",
                                   body: ["text": JSONValue.string(text), "expected_revision": .integer(Int64(u.revision))], idempotencyKey: APIClient.newKey())
            self.message = L("toast_correction_saved")
            self.utterances = (try await self.api.send("GET", "/v1/sessions/\(sid)/utterances", as: Page<Utterance>.self)).items
        }
    }

    public func openRecap(_ sid: String) { recap = nil; askResult = nil; reloadRecap(sid); push(.recap(sid)) }
    public func loadRecap(_ sid: String) async throws { recap = try await api.send("GET", "/v1/sessions/\(sid)/recap", as: JSONValue.self) }
    public func reloadRecap(_ sid: String) { run { try await self.loadRecap(sid) } }

    public func review(_ sid: String, keep: [String], discard: Bool, exclude: Bool = false) {
        run {
            try await self.api.raw("POST", "/v1/sessions/\(sid)/review", body: ["keep_claim_ids": JSONValue.array(keep.map { .string($0) }),
                                                                                "discard_session": .bool(discard), "exclude_from_suggestions": .bool(exclude)],
                                   idempotencyKey: APIClient.newKey())
            self.message = discard ? L("toast_session_discarded") : L("toast_review_saved")
            if self.live.session?.sessionId == sid { self.live.detach() }
            self.path = []
            self.recap = nil
            await self.refreshHome()
        }
    }

    public func retryFinalization(_ sid: String) {
        run { try await self.api.raw("POST", "/v1/sessions/\(sid)/finalization/retry", idempotencyKey: APIClient.newKey()); try await self.loadRecap(sid) }
    }

    public func loadSpeakers(_ sid: String) { run { self.speakers = try await self.items("/v1/sessions/\(sid)/speakers") } }

    public func renameSpeaker(_ sid: String, alias: String, label: String, revision: Int) {
        run {
            let a = alias.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? alias
            try await self.api.raw("PATCH", "/v1/sessions/\(sid)/speakers/\(a)", body: ["verified_label": JSONValue.string(label),
                                   "expected_revision": .integer(Int64(revision))], idempotencyKey: APIClient.newKey())
            self.message = L("toast_speaker_updated")
            self.speakers = try await self.items("/v1/sessions/\(sid)/speakers")
        }
    }

    /// Delete raw audio but keep transcript and notes (retention control).
    public func deleteAudio(_ sid: String) {
        run {
            try await self.api.raw("DELETE", "/v1/sessions/\(sid)/audio", idempotencyKey: APIClient.newKey())
            self.evidence.stop()
            self.message = L("toast_audio_deleted")
            try await self.loadRecap(sid)
        }
    }

    // ---------------------------------------------------------------- session timeline
    public func loadSessions(reset: Bool) {
        run {
            let cursor = reset ? nil : self.sessionsCursor
            if !reset && cursor == nil { return }
            let path = "/v1/sessions?limit=30" + (cursor.map { "&before=" + Self.enc($0) } ?? "")
            let page = try await self.api.send("GET", path, as: Page<SessionSummary>.self)
            self.sessions = reset ? page.items : self.sessions + page.items
            self.sessionsCursor = page.nextCursor
            self.sessionsLoaded = true
        }
    }

    // ---------------------------------------------------------------- memory detail: evidence, decisions, owners
    public func openMemory(_ id: String) { claim = nil; loadMemory(id); push(.memory(id)) }
    public func loadMemory(_ id: String) { run { self.claim = try await self.api.send("GET", "/v1/memories/\(id)", as: JSONValue.self) } }
    private var claimVersion: Int64 { claim?["version"]?.int64 ?? 0 }

    public func setDecision(_ id: String, to: String, note: String) {
        run {
            var b: [String: JSONValue] = ["to_state": .string(to), "expected_version": .integer(self.claimVersion)]
            if !note.isEmpty { b["note"] = .string(note) }
            self.claim = try await self.api.send("POST", "/v1/memories/\(id)/decision", body: b, idempotencyKey: APIClient.newKey(), as: JSONValue.self)
            self.message = L("toast_decision_updated")
        }
    }

    public func confirmOwner(_ id: String, owner: String, due: String) {
        run {
            self.claim = try await self.api.send("POST", "/v1/memories/\(id)/owner", body: [
                "owner_label": JSONValue.string(owner.trimmingCharacters(in: .whitespaces)), "due_text": .string(due.trimmingCharacters(in: .whitespaces)),
                "expected_version": .integer(self.claimVersion)], idempotencyKey: APIClient.newKey(), as: JSONValue.self)
            self.message = owner.isEmpty ? L("toast_owner_cleared") : L("toast_owner_confirmed")
        }
    }

    public func editMemory(_ id: String, text: String?, exclude: Bool?) {
        run {
            var b: [String: JSONValue] = ["expected_version": .integer(self.claimVersion)]
            if let text { b["text_value"] = .string(text) }
            if let exclude { b["exclude_from_suggestions"] = .bool(exclude) }
            self.claim = try await self.api.send("PATCH", "/v1/memories/\(id)", body: b, idempotencyKey: APIClient.newKey(), as: JSONValue.self)
            self.message = L("toast_memory_saved")
        }
    }

    public func deleteMemory(_ id: String) {
        run {
            try await self.api.raw("DELETE", "/v1/memories/\(id)", idempotencyKey: APIClient.newKey())
            self.message = L("toast_memory_deleted")
            self.memories.removeAll { $0["claim_id"]?.string == id }
            self.pop()
        }
    }

    /// A tapped citation opens its source: a memory, or the cited moment (the transcript if that session is still live).
    public func openCitation(_ c: Citation) {
        if let claim = c.claimId, c.utteranceId == nil { openMemory(claim); return }
        guard let uid = c.utteranceId, let sid = c.sessionId else { return }
        if let s = live.session, s.sessionId == sid, SessionStateMachine.active.contains(SessionState.parse(s.state)) { openTranscript(sid) }
        else { playEvidence(sid, uid) }
    }

    public func loadInsights(_ sid: String) {
        insights = nil
        run { self.insights = try await self.items("/v1/sessions/\(sid)/insights") }
    }

    public func loadInsight(_ sid: String, _ iid: String) {
        insightDetail = nil
        run { self.insightDetail = try await self.api.send("GET", "/v1/sessions/\(sid)/insights/\(iid)", as: JSONValue.self) }
    }

    /// Never replay audio while any session may be capturing: the clip would be re-recorded into that conversation.
    public func playEvidence(_ sid: String, _ uid: String) {
        if let s = live.session, s.captureSource != "NONE", SessionStateMachine.active.contains(SessionState.parse(s.state)) {
            message = L("evidence_while_recording"); return
        }
        evidence.toggle(sessionId: sid, utteranceId: uid)
    }

    // ---------------------------------------------------------------- memories
    public func loadMemories(space: String, q: String?) {
        run {
            var path = "/v1/memories?space_id=\(space)&state=ALL"
            if let q, !q.isEmpty { path += "&q=" + Self.enc(q) }
            let r: JSONValue = try await self.api.send("GET", path)
            self.memories = r["items"]?.array ?? []
            self.matchingSessions = r["matching_sessions"]?.array ?? []
        }
    }

    public func retain(space: String, ids: [String]) {
        run {
            try await self.api.raw("POST", "/v1/memories/retain", body: ["space_id": JSONValue.string(space), "claim_ids": .array(ids.map { .string($0) })],
                                   idempotencyKey: APIClient.newKey())
            self.message = LP("toast_kept", ids.count)
            self.memories = try await self.items("/v1/memories?space_id=\(space)&state=ALL")
        }
    }

    // ---------------------------------------------------------------- projects, briefs, decision ledger
    public func loadProjects() { run { self.projects = try await self.items("/v1/projects") } }

    private func spaceFor(_ kind: String) -> String? {
        let want = kind == "COURSE" ? "LEARNING" : "WORK"
        return me?.spaces.first { $0.kind == want }?.spaceId ?? me?.spaces.first?.spaceId
    }

    public func createProject(kind: String, title: String, meta: [String: String], attachToDraft: Bool = false) {
        run {
            // A project attached to a session must live in that session's space (the server enforces it; never mix spaces).
            guard let space = (attachToDraft ? self.draft.spaceId : nil) ?? self.spaceFor(kind) else { return }
            let m = meta.filter { !$0.value.trimmingCharacters(in: .whitespaces).isEmpty }.mapValues { JSONValue.string($0.trimmingCharacters(in: .whitespaces)) }
            let r: JSONValue = try await self.api.send("POST", "/v1/projects", body: ["space_id": JSONValue.string(space), "kind": .string(kind),
                                                                                    "title": .string(title.trimmingCharacters(in: .whitespaces)), "metadata": .object(m)])
            self.message = L("toast_project_created")
            self.projects = try await self.items("/v1/projects")
            if attachToDraft, let id = r["project_id"]?.string { self.draft.projectId = id }
            if kind == "INTERVIEW_GOAL" { self.goals = try await self.items("/v1/projects?kind=INTERVIEW_GOAL") }
        }
    }

    public func openProject(_ id: String) {
        project = nil; brief = nil; decisions = []
        push(.project(id))
        run {
            self.project = try await self.api.send("GET", "/v1/projects/\(id)", as: JSONValue.self)
            self.decisions = try await self.items("/v1/decisions?scope=SELECTED_PROJECT&scope_id=\(id)")
        }
    }

    public func loadBrief(_ id: String) { run { self.brief = try await self.api.send("GET", "/v1/briefs?scope=SELECTED_PROJECT&scope_id=\(id)", as: JSONValue.self) } }

    public func updateProject(_ id: String, title: String, meta: [String: String]) {
        run {
            // Blank values are sent so a cleared field really clears; the server merges metadata.
            try await self.api.raw("PATCH", "/v1/projects/\(id)", body: ["title": JSONValue.string(title.trimmingCharacters(in: .whitespaces)),
                "expected_version": .integer(self.project?["version"]?.int64 ?? 1),
                "metadata": .object(meta.mapValues { .string($0.trimmingCharacters(in: .whitespaces)) })], idempotencyKey: APIClient.newKey())
            self.message = L("toast_project_saved")
            self.project = try await self.api.send("GET", "/v1/projects/\(id)", as: JSONValue.self)
        }
    }

    public func deleteProject(_ id: String) {
        run {
            try await self.api.raw("DELETE", "/v1/projects/\(id)", idempotencyKey: APIClient.newKey())
            self.message = L("toast_project_deleted")
            self.projects = try await self.items("/v1/projects")
            self.project = nil
            self.pop()
        }
    }

    // ---------------------------------------------------------------- sharing: preview, confirm, revoke
    public func openShare(_ sid: String) { sharePreview = nil; shareLink = nil; shares = []; push(.share(sid)); loadShares(sid) }
    public func loadShares(_ sid: String) { run { self.shares = try await self.items("/v1/sessions/\(sid)/shares") } }

    public func shareRequest(_ sid: String, sections: [String], redact: Bool, hours: Int, confirm: Bool) {
        run {
            let r: JSONValue = try await self.api.send("POST", "/v1/sessions/\(sid)/shares", body: [
                "sections": JSONValue.array(sections.map { .string($0) }), "redact_identities": .bool(redact),
                "expires_in_hours": .integer(Int64(hours)), "confirm": .bool(confirm)], idempotencyKey: confirm ? APIClient.newKey() : nil)
            self.sharePreview = r["preview"]
            self.shareLink = confirm ? r : nil
            if confirm { self.shares = try await self.items("/v1/sessions/\(sid)/shares") }
        }
    }

    /// Recipient page (backend app/api/public_share.py): static, script-free, noindex, revocable.
    public func shareURL(_ token: String) -> URL { api.baseURL.appendingPathComponent("s").appendingPathComponent(token) }

    public func revokeShare(_ sid: String, _ shareId: String) {
        run {
            try await self.api.raw("DELETE", "/v1/shares/\(shareId)", idempotencyKey: APIClient.newKey())
            self.message = L("toast_share_revoked")
            if self.shareLink?["share_id"]?.string == shareId { self.shareLink = nil }
            self.shares = try await self.items("/v1/sessions/\(sid)/shares")
        }
    }

    // ---------------------------------------------------------------- privacy: export (re-auth), delete account, devices
    public func requestExport(password: String, sessionId: String? = nil) {
        run {
            try await self.api.reauth(password: password)
            var body: [String: JSONValue] = [:]
            if let sessionId { body["session_id"] = .string(sessionId) }
            let r: JSONValue = try await self.api.send("POST", "/v1/exports", body: body)
            guard let id = r["export_id"]?.string else { return }
            let scope = sessionId ?? "ALL"
            self.exportData = nil
            self.export = ExportState(exportId: id, status: "REQUESTED", scope: scope)
            // The export job runs server-side; poll briefly so the save action appears without a manual refresh.
            for _ in 0..<30 {
                try await Task.sleep(nanoseconds: 2_000_000_000)
                let st: JSONValue = try await self.api.send("GET", "/v1/exports/\(id)")
                let status = st["status"]?.string ?? "REQUESTED"
                self.export = ExportState(exportId: id, status: status, scope: scope)
                if status != "REQUESTED" && status != "IN_PROGRESS" { break }
            }
        }
    }

    public func refreshExport() {
        run {
            guard let e = self.export else { return }
            let st: JSONValue = try await self.api.send("GET", "/v1/exports/\(e.exportId)")
            self.export?.status = st["status"]?.string ?? e.status
        }
    }

    /// Fetches the archive into memory for the system save dialog; it is never cached on disk by the app.
    public func prepareExportFile() {
        run {
            guard let e = self.export else { return }
            self.exportData = try await self.api.bytes("/v1/exports/\(e.exportId)/download")
        }
    }

    public func deleteAccount(password: String) {
        run {
            try await self.api.reauth(password: password)
            self.live.resetForSignOut(purgeLocal: true)
            self.evidence.stop()
            try await self.api.raw("DELETE", "/v1/account")
            await self.api.logout()
            self.signedIn = false
            self.path = []
            self.message = L("toast_account_deleted")
        }
    }

    public func loadDevices() { run { self.devices = try await self.items("/v1/devices") } }

    public func revokeDevice(_ id: String) {
        run {
            try await self.api.raw("DELETE", "/v1/devices/\(id)")
            self.message = L("toast_device_revoked")
            self.devices = try await self.items("/v1/devices")
        }
    }

    // ---------------------------------------------------------------- learning & interview
    public func practice(_ sid: String) {
        run {
            self.study = try await self.api.send("POST", "/v1/learning/practice", body: ["session_id": JSONValue.string(sid), "count": .integer(5)], as: JSONValue.self)
            self.lastAttempt = nil
            self.push(.study)
        }
    }
    public func attempt(_ item: String, _ response: String) {
        run { self.lastAttempt = try await self.api.send("POST", "/v1/learning/practice/\(item)/attempts", body: ["response": response], as: JSONValue.self) }
    }
    public func loadReviews() { run { self.reviews = try await self.items("/v1/learning/reviews") } }
    public func reviewAction(space: String, key: String, action: String, days: Int?) {
        run {
            var b: [String: JSONValue] = ["space_id": .string(space), "action": .string(action)]
            if let days { b["days"] = .integer(Int64(days)) }
            try await self.api.raw("POST", "/v1/learning/reviews/\(key)", body: b)
            self.reviews = try await self.items("/v1/learning/reviews")
        }
    }
    public func loadInterview() {
        run {
            self.goals = try await self.items("/v1/projects?kind=INTERVIEW_GOAL")
            self.mocks = try await self.items("/v1/interview/mocks")
        }
    }
    public func startMock(topic: String, difficulty: String, goal: String?, maxQuestions: Int = 3) {
        run {
            guard let space = self.spaceFor("INTERVIEW_GOAL") else { return }
            var b: [String: JSONValue] = ["space_id": .string(space), "topic": .string(topic), "difficulty": .string(difficulty),
                                          "max_questions": .integer(Int64(maxQuestions))]
            if let goal { b["goal_id"] = .string(goal) }
            let r: JSONValue = try await self.api.send("POST", "/v1/interview/mocks", body: b)
            self.mock = r
            if let id = r["mock"]?["mock_id"]?.string { self.push(.mock(id)) }
        }
    }
    private func mergeMock(_ r: JSONValue) {
        if case .object(var cur) = mock ?? .object([:]), case .object(let new) = r { for (k, v) in new { cur[k] = v }; mock = .object(cur) }
    }
    public func mockAction(_ id: String, _ action: String, _ text: String?) {
        run {
            var b: [String: JSONValue] = ["action": .string(action)]
            if let text { b["text"] = .string(text) }
            let r: JSONValue = try await self.api.send("POST", "/v1/interview/mocks/\(id)/turns", body: b)
            if let n = r["notice"]?.string { self.message = n }
            self.mergeMock(r)
        }
    }
    public func loadMock(_ id: String) { run { self.mock = try await self.api.send("GET", "/v1/interview/mocks/\(id)", as: JSONValue.self) } }
    public func requestDebrief(_ id: String) { run { self.mergeMock(try await self.api.send("GET", "/v1/interview/mocks/\(id)/debrief", as: JSONValue.self)) } }
    /// Focused single-question retry on one skill from the debrief (Answer Lab).
    public func retrySkill(_ id: String, focus: String) {
        run {
            let r: JSONValue = try await self.api.send("POST", "/v1/interview/mocks/\(id)/retry", body: ["focus": String(focus.prefix(300))])
            self.mock = r
            if let nid = r["mock"]?["mock_id"]?.string { self.push(.mock(nid)) }
        }
    }
}

enum DeviceInfo {
    static var name: String {
        #if os(iOS)
        return "iPhone"
        #else
        return "Mac (development)"
        #endif
    }
}
