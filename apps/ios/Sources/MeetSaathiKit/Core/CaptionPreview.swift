import Foundation

/// Ephemeral hypotheses have no citation IDs and never enter the evidence transcript.
public struct CaptionPreview: Sendable {
    public let runId: String
    public let previewId: String
    public let text: String
    public let startMs: Int64
    public var expiresAt: Date = Date().addingTimeInterval(15)

    public func clearedBy(run: String?, preview: String?) -> Bool {
        run == runId && (preview == nil || preview == previewId)
    }
    public func expired(now: Date = Date()) -> Bool { now >= expiresAt }
}
