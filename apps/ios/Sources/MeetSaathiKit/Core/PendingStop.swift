import Foundation

/// Persist the exact stop body before the first network attempt. A retry must use the same timestamp,
/// watermark and key even after process death or the response being lost after server commit.
public struct PendingStop: Codable, Equatable, Sendable {
    public let finalSequence: Int64
    public let atMs: Int64
    public init(finalSequence: Int64, atMs: Int64) { self.finalSequence = finalSequence; self.atMs = atMs }

    public static func load(from dir: URL) -> PendingStop? {
        guard let data = try? Data(contentsOf: dir.appendingPathComponent("pending_stop.json")) else { return nil }
        return try? Wire.decoder.decode(Self.self, from: data)
    }

    public func save(to dir: URL) throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Wire.encoder.encode(self).write(to: dir.appendingPathComponent("pending_stop.json"), options: .atomic)
        var url = dir
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try url.setResourceValues(values)
    }

    public static func clear(from dir: URL) {
        try? FileManager.default.removeItem(at: dir.appendingPathComponent("pending_stop.json"))
    }
}
