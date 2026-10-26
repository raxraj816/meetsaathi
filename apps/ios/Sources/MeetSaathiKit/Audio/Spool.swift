import CryptoKit
import Foundation

public enum Signal {
    public static func rmsDbfs(_ s: [Int16]) -> Double {
        guard !s.isEmpty else { return -120 }
        var acc = 0.0
        for v in s { acc += Double(v) * Double(v) }
        let rms = (acc / Double(s.count)).squareRoot()
        return rms <= 0 ? -120 : 20 * log10(rms / 32768.0)
    }

    public static func quality(_ dbfs: Double) -> String { dbfs < -55 ? "SILENT_OR_BLOCKED" : (dbfs < -42 ? "POOR" : "GOOD") }

    public static func littleEndianBytes(_ s: [Int16]) -> Data {
        var d = Data(capacity: s.count * 2)
        for v in s { var le = v.littleEndian; withUnsafeBytes(of: &le) { d.append(contentsOf: $0) } }
        return d
    }

    public static func sha256Hex(_ d: Data) -> String { SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }
}

public struct SpooledChunk: Sendable {
    public var sequence: Int64
    public var captureStartMs: Int64
    public var durationMs: Int
    public var sampleRate: Int
    public var sha256: String
    public var pcm: Data
}

/// Encrypted, bounded local spool (master 7.2). Chunks are sealed with a Keychain key (AAD = session:sequence),
/// excluded from backups, and deleted once the server ACK watermark covers them. Refuses when the cap is reached.
public final class ChunkSpool: @unchecked Sendable {
    public enum AppendResult: Equatable { case stored, storageFull }
    let dir: URL
    let sealer: Sealer
    let sessionId: String
    let capBytes: Int
    private let lock = NSLock()

    public init(dir: URL, sealer: Sealer, sessionId: String, capBytes: Int = 200 * 1024 * 1024) {
        self.dir = dir; self.sealer = sealer; self.sessionId = sessionId; self.capBytes = capBytes
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var u = dir
        var rv = URLResourceValues(); rv.isExcludedFromBackup = true
        try? u.setResourceValues(rv)
    }

    private func file(_ seq: Int64) -> URL { dir.appendingPathComponent(String(format: "%012lld.chunk", seq)) }
    private func aad(_ seq: Int64) -> Data { Data("\(sessionId):\(seq)".utf8) }

    public func bytesUsed() -> Int {
        let files = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.fileSizeKey])) ?? []
        return files.reduce(0) { $0 + ((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
    }

    public func append(seq: Int64, captureStartMs: Int64, durationMs: Int, sampleRate: Int, pcm: Data) -> AppendResult {
        lock.lock(); defer { lock.unlock() }
        if bytesUsed() + pcm.count + 128 > capBytes { return .storageFull }
        let header = Data("\(captureStartMs),\(durationMs),\(sampleRate),\(Signal.sha256Hex(pcm))\n".utf8)
        guard let sealed = try? sealer.seal(header + pcm, aad: aad(seq)) else { return .storageFull }
        do {
            #if os(iOS)
            try sealed.write(to: file(seq), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            #else
            try sealed.write(to: file(seq), options: [.atomic])
            #endif
        } catch { return .storageFull }
        return .stored
    }

    public func pendingSequences() -> [Int64] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        return names.filter { $0.hasSuffix(".chunk") }.compactMap { Int64($0.replacingOccurrences(of: ".chunk", with: "")) }.sorted()
    }

    public func read(_ seq: Int64) -> SpooledChunk? {
        guard let blob = try? Data(contentsOf: file(seq)), let plain = try? sealer.open(blob, aad: aad(seq)),
              let nl = plain.firstIndex(of: 0x0A), let header = String(data: plain[plain.startIndex..<nl], encoding: .utf8) else { return nil }
        let p = header.split(separator: ",").map(String.init)
        guard p.count == 4, let start = Int64(p[0]), let dur = Int(p[1]), let rate = Int(p[2]) else { return nil }
        return SpooledChunk(sequence: seq, captureStartMs: start, durationMs: dur, sampleRate: rate, sha256: p[3], pcm: Data(plain[plain.index(after: nl)...]))
    }

    public func ackThrough(_ through: Int64) { pendingSequences().filter { $0 <= through }.forEach(drop) }
    public func drop(_ seq: Int64) { try? FileManager.default.removeItem(at: file(seq)) }
    public func purgeAll() { try? FileManager.default.removeItem(at: dir) }
}

public protocol ChunkTransport: Sendable {
    /// Returns HTTP status + body; throws when offline.
    func put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk) async throws -> (Int, Data)
}

public struct URLSessionChunkTransport: ChunkTransport {
    let baseURL: URL
    let session: URLSession
    public init(baseURL: URL, session: URLSession) { self.baseURL = baseURL; self.session = session }

    public func put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk) async throws -> (Int, Data) {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/ingest/sessions/\(sessionId)/chunks/\(chunk.sequence)"))
        req.httpMethod = "PUT"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("\(chunk.sampleRate)", forHTTPHeaderField: "X-Sample-Rate")
        req.setValue("\(chunk.captureStartMs)", forHTTPHeaderField: "X-Capture-Start-Ms")
        req.setValue("\(chunk.durationMs)", forHTTPHeaderField: "X-Duration-Ms")
        req.setValue(chunk.sha256, forHTTPHeaderField: "X-Sha256")
        req.setValue("pcm_s16le", forHTTPHeaderField: "X-Encoding")
        if let deviceId { req.setValue(deviceId, forHTTPHeaderField: "X-Device-Id") }
        req.httpBody = chunk.pcm
        let (data, resp) = try await session.data(for: req)
        return ((resp as? HTTPURLResponse)?.statusCode ?? 0, data)
    }
}

public struct UploadStatus: Sendable, Equatable {
    public var online = true
    public var receivedThrough: Int64 = -1
    public var pending = 0
    public var gaps: [Int64] = []
    public var stoppedReason: String?
}

/// Resumable idempotent uploader (IMP-005): in-order sends, resume from server cursor, credential refresh,
/// never re-sends ACKed audio, never retries a sequence the server refused (paused / ended / withdrawn).
public actor Uploader {
    let spool: ChunkSpool
    let transport: ChunkTransport
    let sessionId: String
    let deviceId: String?
    let credentials: @Sendable (_ expired: Bool) async -> String?
    private var token: String?
    public private(set) var status = UploadStatus()
    private var loopTask: Task<Void, Never>?
    public var onStatus: (@Sendable (UploadStatus) -> Void)?

    public init(spool: ChunkSpool, transport: ChunkTransport, sessionId: String, deviceId: String?, initialToken: String?,
                credentials: @escaping @Sendable (_ expired: Bool) async -> String?) {
        self.spool = spool; self.transport = transport; self.sessionId = sessionId; self.deviceId = deviceId
        self.token = initialToken; self.credentials = credentials
    }

    public func setOnStatus(_ f: @escaping @Sendable (UploadStatus) -> Void) { onStatus = f }

    private func publish() { onStatus?(status) }

    /// One pass. Returns false when it should back off.
    public func pass() async -> Bool {
        let pending = spool.pendingSequences()
        status.pending = pending.count; publish()
        for seq in pending {
            guard let chunk = spool.read(seq) else { spool.drop(seq); continue }
            if token == nil { token = await credentials(false) }
            guard let tok = token else { status.stoppedReason = "NO_CREDENTIAL"; publish(); return false }
            let code: Int, body: Data
            do { (code, body) = try await transport.put(sessionId: sessionId, token: tok, deviceId: deviceId, chunk: chunk) }
            catch { status.online = false; publish(); return false }
            status.online = true
            let err = try? Wire.decoder.decode(APIErrorBody.self, from: body)
            switch code {
            case 200:
                guard let ack = try? Wire.decoder.decode(ChunkAck.self, from: body) else { return false }
                spool.drop(seq)
                spool.ackThrough(ack.receivedThroughSequence)
                status.receivedThrough = ack.receivedThroughSequence
                status.gaps = ack.gapSequences
                status.pending = spool.pendingSequences().count
                publish()
            case 401:
                token = nil
                if err?.code == "INGEST_REVOKED" { status.stoppedReason = "DEVICE_REVOKED"; publish(); return false }
                token = await credentials(true)
                return token != nil
            case 409:
                switch err?.code {
                case "CHUNK_CONFLICT", "CAPTURE_PAUSED", "SESSION_ENDED", "SESSION_NOT_CAPTURING": spool.drop(seq)
                default: return false
                }
            case 403:
                spool.drop(seq); status.stoppedReason = "NOT_AUTHORIZED"; publish()
            case 422:
                if let ack = try? Wire.decoder.decode(ChunkAck.self, from: body), !ack.checksumConfirmed { return true }
                spool.drop(seq)
            default:
                return false
            }
        }
        return true
    }

    public func start() {
        loopTask?.cancel()
        loopTask = Task { [weak self] in
            var backoff: UInt64 = 500_000_000
            while !Task.isCancelled, let self {
                let ok = await self.pass()
                if ok {
                    backoff = 500_000_000
                    if self.spool.pendingSequences().isEmpty { try? await Task.sleep(nanoseconds: 400_000_000) }
                } else {
                    try? await Task.sleep(nanoseconds: backoff)
                    backoff = min(backoff * 2, 15_000_000_000)
                }
            }
        }
    }

    public func stop() { loopTask?.cancel() }
    public func setToken(_ t: String?) { token = t }
}
