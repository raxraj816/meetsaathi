import CryptoKit
import Foundation
import Testing
@testable import MeetSaathiKit

@Suite struct StateMachineTests {
    /// Client table must equal the server table (packages/contracts/state_machine_v1.json).
    @Test func parityWithServerContract() throws {
        let url = try #require(Bundle.module.url(forResource: "state_machine_v1", withExtension: "json"))
        let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let table = obj["transitions"] as! [String: [String]]
        #expect(Set(table.keys) == Set(SessionState.allCases.map(\.rawValue)))
        for (from, tos) in table {
            for to in SessionState.allCases {
                #expect(SessionStateMachine.canTransition(SessionState(rawValue: from)!, to) == tos.contains(to.rawValue), "\(from) -> \(to)")
            }
        }
    }

    @Test func recordingRequiresRealBuffers() {
        #expect(captureTruth(server: .RECORDING, localBuffersFlowing: false, online: true, micPermission: true) == .starting)
        #expect(captureTruth(server: .RECORDING, localBuffersFlowing: true, online: true, micPermission: true) == .recording)
        #expect(captureTruth(server: .RECORDING, localBuffersFlowing: true, online: false, micPermission: true) == .recordingLocal)
        #expect(captureTruth(server: .STARTING, localBuffersFlowing: false, online: true, micPermission: false) == .micDenied)
        #expect(captureTruth(server: .NOTES_ONLY, localBuffersFlowing: false, online: true, micPermission: false) == .notesOnly)
        #expect(captureTruth(server: .FINALIZING, localBuffersFlowing: false, online: true, micPermission: true) == .stopped)
    }
}

@Suite struct SpoolTests {
    func spool(cap: Int = 10_000_000) -> (ChunkSpool, URL) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return (ChunkSpool(dir: dir, sealer: Sealer(key: SymmetricKey(size: .bits256)), sessionId: "s1", capBytes: cap), dir)
    }

    @Test func encryptedAtRestAndRoundTrips() throws {
        let (sp, dir) = spool()
        let pcm = Data((0..<32000).map { UInt8($0 % 251) })
        #expect(sp.append(seq: 0, captureStartMs: 0, durationMs: 1000, sampleRate: 16000, pcm: pcm) == .stored)
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
        let raw = try Data(contentsOf: files[0])
        #expect(raw.range(of: pcm.prefix(64)) == nil, "plaintext must not be on disk")
        let back = try #require(sp.read(0))
        #expect(back.pcm == pcm && back.sha256 == Signal.sha256Hex(pcm))
    }

    @Test func tamperDetected() throws {
        let (sp, dir) = spool()
        _ = sp.append(seq: 0, captureStartMs: 0, durationMs: 1000, sampleRate: 16000, pcm: Data(count: 32000))
        let f = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)[0]
        var d = try Data(contentsOf: f); d[40] ^= 0xFF; try d.write(to: f)
        #expect(sp.read(0) == nil)
    }

    @Test func capRefuses() {
        let (sp, _) = spool(cap: 50_000)
        #expect(sp.append(seq: 0, captureStartMs: 0, durationMs: 1000, sampleRate: 16000, pcm: Data(count: 32000)) == .stored)
        #expect(sp.append(seq: 1, captureStartMs: 1000, durationMs: 1000, sampleRate: 16000, pcm: Data(count: 32000)) == .storageFull)
    }

    @Test func ackDeletesCovered() {
        let (sp, _) = spool()
        for i in 0..<5 { _ = sp.append(seq: Int64(i), captureStartMs: Int64(i) * 1000, durationMs: 1000, sampleRate: 16000, pcm: Data(count: 100)) }
        sp.ackThrough(2)
        #expect(sp.pendingSequences() == [3, 4])
    }
}

final class FakeTransport: ChunkTransport, @unchecked Sendable {
    var script: [(SpooledChunk) throws -> (Int, Data)]
    var sent: [Int64] = []
    init(_ s: [(SpooledChunk) throws -> (Int, Data)]) { script = s }
    func put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk) async throws -> (Int, Data) {
        sent.append(chunk.sequence)
        return try script.removeFirst()(chunk)
    }
}

func ack(_ through: Int64) -> (Int, Data) {
    (200, Data(#"{"received_through_sequence":\#(through),"gap_sequences":[],"checksum_confirmed":true,"status":"ACKED"}"#.utf8))
}
func err(_ status: Int, _ code: String) -> (Int, Data) {
    (status, Data(#"{"code":"\#(code)","user_message":"x","retryable":false,"correlation_id":"c"}"#.utf8))
}

@Suite struct UploaderTests {
    func spool(_ n: Int) -> ChunkSpool {
        let sp = ChunkSpool(dir: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString),
                            sealer: Sealer(key: SymmetricKey(size: .bits256)), sessionId: "s1")
        for i in 0..<n { _ = sp.append(seq: Int64(i), captureStartMs: Int64(i) * 1000, durationMs: 1000, sampleRate: 16000, pcm: Data(repeating: UInt8(i), count: 320)) }
        return sp
    }

    @Test func uploadsInOrderAndClears() async {
        let sp = spool(3)
        let tr = FakeTransport([{ _ in ack(0) }, { _ in ack(1) }, { _ in ack(2) }])
        let up = Uploader(spool: sp, transport: tr, sessionId: "s1", deviceId: "d", initialToken: "t") { _ in "t" }
        #expect(await up.pass())
        #expect(tr.sent == [0, 1, 2] && sp.pendingSequences().isEmpty)
        #expect(await up.status.receivedThrough == 2)
    }

    @Test func offlineKeepsChunks() async {
        let sp = spool(2)
        let tr = FakeTransport([{ _ in throw URLError(.notConnectedToInternet) }])
        let up = Uploader(spool: sp, transport: tr, sessionId: "s1", deviceId: "d", initialToken: "t") { _ in "t" }
        #expect(await up.pass() == false)
        #expect(await up.status.online == false && sp.pendingSequences() == [0, 1])
    }

    @Test func refreshesExpiredCredential() async {
        let sp = spool(1)
        let tr = FakeTransport([{ _ in err(401, "INGEST_TOKEN_EXPIRED") }, { _ in ack(0) }])
        let up = Uploader(spool: sp, transport: tr, sessionId: "s1", deviceId: "d", initialToken: "old") { expired in expired ? "new" : nil }
        #expect(await up.pass())
        #expect(await up.pass())
        #expect(tr.sent == [0, 0] && sp.pendingSequences().isEmpty)
    }

    @Test func pausedRejectionNeverRetried() async {
        let sp = spool(1)
        let up = Uploader(spool: sp, transport: FakeTransport([{ _ in err(409, "CAPTURE_PAUSED") }]), sessionId: "s1", deviceId: "d", initialToken: "t") { _ in "t" }
        #expect(await up.pass())
        #expect(sp.pendingSequences().isEmpty)
    }

    @Test func revokedDeviceStops() async {
        let sp = spool(1)
        let up = Uploader(spool: sp, transport: FakeTransport([{ _ in err(401, "INGEST_REVOKED") }]), sessionId: "s1", deviceId: "d", initialToken: "t") { _ in "t" }
        #expect(await up.pass() == false)
        #expect(await up.status.stoppedReason == "DEVICE_REVOKED" && sp.read(0) != nil)
    }
}

@Suite struct WireTests {
    @Test func decodesSessionAndInsight() throws {
        let json = #"""
        {"session_id":"s","space_id":"sp","context":"MEETING","title":"T","state":"RECORDING","capture_source":"PHONE_MIC","source_watermark_ms":1000,
         "version":3,"capture_permitted":true,"ai_assistance_permitted":true,"assistance_mode":"LISTENER","proactive_intensity":"QUIET","output_mode":"TEXT",
         "sensitive":false,"transcript_status":"LIVE","finalization":{"status":"NOT_STARTED","attempts":0,"error":null},"review_state":"PENDING",
         "gaps":[{"start_ms":0,"end_ms":10,"reason":"PAUSED_BY_USER"}],"ingest":{"token":"tok","expires_at":"2026-10-18T10:00:00Z","resume_cursor":4,"drain_only":false}}
        """#
        let s = try Wire.decoder.decode(SessionView.self, from: Data(json.utf8))
        #expect(s.ingestCredential?.resumeCursor == 4 && s.gaps.count == 1)
        let ev = try Wire.decoder.decode(EventEnvelope.self, from: Data(#"{"sequence":9,"type":"insight.delivered","payload":{"insight_id":"i","short_text":"Ask who owns rollback.","kind":"CLARIFY","source_refs":[{"utterance_id":"u","revision":1,"start_ms":1000}],"expires_at":"2026-10-18T10:02:00Z","output_channel":"TEXT","policy_version":"p"}}"#.utf8))
        let ins = try Wire.decoder.decode(Insight.self, from: try Wire.encoder.encode(ev.payload!))
        #expect(ins.outputChannel == "TEXT" && ins.sourceRefs.first?.startMs == 1000)
    }

    @Test func capabilitiesEncodeSnakeCase() throws {
        let c = Capabilities(micPermission: "granted", inputRoute: "phone_mic", outputRoute: "receiver", outputDeviceName: nil, privateRouteVerified: false, measuredLevelDbfs: -30)
        let s = String(data: try Wire.encoder.encode(c), encoding: .utf8)!
        #expect(s.contains("\"mic_permission\":\"granted\"") && s.contains("\"private_route_verified\":false"))
    }
}

@Suite struct RouteTests {
    @Test func privateRouteFailsClosedOnLoss() {
        let r = AudioRoutes()
        var lostEvents = 0
        r.onChange = { _, _, lost in if lost { lostEvents += 1 } }
        r._simulate(AudioRoute(input: "phone_mic", output: "bluetooth_a2dp", outputDeviceName: "Buds", privateOutputPresent: true, couplesInputAndOutput: false), deviceLost: false)
        r.confirmPrivateRoute()
        #expect(r.privateRouteVerified)
        r._simulate(AudioRoute(input: "phone_mic", output: "receiver", outputDeviceName: nil, privateOutputPresent: false, couplesInputAndOutput: false), deviceLost: true)
        #expect(!r.privateRouteVerified && lostEvents == 1)
        // Reconnecting does not silently restore verification: a fresh route check is required (ADR-014).
        r._simulate(AudioRoute(input: "phone_mic", output: "bluetooth_a2dp", outputDeviceName: "Buds", privateOutputPresent: true, couplesInputAndOutput: false), deviceLost: false)
        #expect(!r.privateRouteVerified)
    }

    @Test func voiceRefusesWithoutVerifiedRoute() {
        let r = AudioRoutes()
        let v = PrivateVoice(routes: r, clockMs: { 0 })
        #expect(v.speak("Clarify the ordering scope.") == false)
    }
}

@Suite struct PendingStopTests {
    @Test func exactStopBodySurvivesRestart() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let stop = PendingStop(finalSequence: 8, atMs: 9123)
        try stop.save(to: dir)
        let recovered = try #require(PendingStop.load(from: dir))
        #expect(recovered == stop)
        #expect(try Wire.encoder.encode(recovered) == Wire.encoder.encode(stop))
        let body = String(data: try Wire.encoder.encode(recovered), encoding: .utf8)!
        #expect(body.contains("\"final_sequence\":8") && body.contains("\"at_ms\":9123"))
        PendingStop.clear(from: dir)
        #expect(PendingStop.load(from: dir) == nil)
    }
}

@Suite struct CaptionPreviewTests {
    @Test func lateClearDoesNotEraseANewerDraft() {
        let draft = CaptionPreview(runId: "new-run", previewId: "next-result", text: "Draft words", startMs: 1200,
                                   expiresAt: Date(timeIntervalSince1970: 15))
        #expect(!draft.clearedBy(run: "old-run", preview: nil))
        #expect(!draft.clearedBy(run: "new-run", preview: "previous-result"))
        #expect(draft.clearedBy(run: "new-run", preview: "next-result"))
        #expect(draft.clearedBy(run: "new-run", preview: nil))
        #expect(!draft.expired(now: Date(timeIntervalSince1970: 14.999)))
        #expect(draft.expired(now: Date(timeIntervalSince1970: 15)))
    }
}

@Suite struct GapDescriptionTests {
    @Test func unknownEndStaysUnknownForLegacyAndCurrentPayloads() throws {
        let raw = Data(#"{"start_ms":6000,"end_ms":null,"reason":"UPLOAD_MISSING"}"#.utf8)
        let gap = try Wire.decoder.decode(Gap.self, from: raw)
        #expect(gap.description.contains("after 0:06"))
        #expect(gap.description.contains("end time is unknown"))
        #expect(!gap.description.contains("0:00"))
        #expect(captureGapDescription(startMs: nil, endMs: nil, estimated: false, reason: "UPLOAD_MISSING").contains("timing is unknown"))
    }
    @Test func estimatedGapIsNotPresentedAsAnExactInterval() throws {
        let raw = Data(#"{"start_ms":6000,"end_ms":5400000,"reason":"UPLOAD_MISSING","missing_sequence_from":1,"missing_sequence_to":9223372036854775806,"time_bounds_estimated":true}"#.utf8)
        let gap = try Wire.decoder.decode(Gap.self, from: raw)
        #expect(gap.missingSequenceTo == 9223372036854775806)
        #expect(gap.description.contains("approximately 0:06 and 1:30:00"))
        #expect(!captureGapDescription(startMs: 6000, endMs: 12000, estimated: false, reason: "INPUT_LOST").contains("approximately"))
    }
}

@Suite struct IntegerWireTests {
    @Test func signedCaptureCountersSurviveGenericJsonWithoutFloatingPointLoss() throws {
        let raw = Data(#"{"sequence":9223372036854775806,"end_ms":9223372036854775807}"#.utf8)
        let value = try Wire.decoder.decode(JSONValue.self, from: raw)
        #expect(value["sequence"]?.int64 == Int64.max-1)
        #expect(value["end_ms"]?.int64 == Int64.max)
        let roundtrip = try Wire.decoder.decode(JSONValue.self, from: Wire.encoder.encode(value))
        #expect(roundtrip == value)
        #expect(JSONValue.integer(5) == JSONValue.number(5))
    }
    @Test func invalidNumericConversionsCannotTrap() {
        #expect(JSONValue.number(.infinity).int == nil)
        #expect(JSONValue.number(.nan).int64 == nil)
        #expect(JSONValue.number(Double(Int64.max)).int64 == nil)
        #expect(JSONValue.number(0.5).int64 == nil)
        #expect(JSONValue.number(0.5).int == 0)
    }
}
