import Foundation

/// Wire models for packages/contracts/openapi_v1.json. JSON keys are snake_case on the wire.
public enum Wire {
    public static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()
    public static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.outputFormatting = [.sortedKeys]
        return e
    }()
}

/// Loosely-typed JSON for read-mostly views (recap, memories) so the UI tolerates additive server fields.
public enum JSONValue: Codable, Equatable, Sendable {
    case string(String), integer(Int64), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Int64.self) { self = .integer(n) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .integer(let n): try c.encode(n)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .object(let o): try c.encode(o)
        case .array(let a): try c.encode(a)
        case .null: try c.encodeNil()
        }
    }

    public subscript(_ key: String) -> JSONValue? { if case .object(let o) = self { return o[key] }; return nil }
    public var string: String? { if case .string(let s) = self { return s }; return nil }
    public var double: Double? {
        switch self { case .integer(let n): return Double(n); case .number(let n): return n; default: return nil }
    }
    public var int64: Int64? {
        switch self { case .integer(let n): return n; case .number(let n): return Int64(exactly: n); default: return nil }
    }
    public var int: Int? {
        if case .integer(let n) = self { return Int(exactly: n) }
        guard let n = double, n.isFinite, n >= Double(Int.min), n < Double(Int.max) else { return nil }
        return Int(n)
    }
    public static func == (lhs: JSONValue, rhs: JSONValue) -> Bool {
        switch (lhs, rhs) {
        case (.integer(let a), .integer(let b)): return a == b
        case (.number(let a), .number(let b)): return a == b
        case (.integer(let a), .number(let b)): return Int64(exactly: b) == a
        case (.number(let a), .integer(let b)): return Int64(exactly: a) == b
        case (.string(let a), .string(let b)): return a == b
        case (.bool(let a), .bool(let b)): return a == b
        case (.array(let a), .array(let b)): return a == b
        case (.object(let a), .object(let b)): return a == b
        case (.null, .null): return true
        default: return false
        }
    }
    public var bool: Bool { if case .bool(let b) = self { return b }; return false }
    public var array: [JSONValue] { if case .array(let a) = self { return a }; return [] }
    public var isNull: Bool { if case .null = self { return true }; return false }
}

public struct APIErrorBody: Codable, Error, Sendable {
    public var code: String
    public var userMessage: String
    public var retryable: Bool
    public var correlationId: String
    public init(code: String, userMessage: String, retryable: Bool = false, correlationId: String = "") {
        self.code = code; self.userMessage = userMessage; self.retryable = retryable; self.correlationId = correlationId
    }
}

public struct Tokens: Codable, Sendable {
    public var accessToken: String
    public var refreshToken: String?
    public var deviceId: String?
    public var userId: String?
}

public struct Space: Codable, Identifiable, Hashable, Sendable {
    public var spaceId: String
    public var name: String
    public var kind: String
    public var role: String?
    public var id: String { spaceId }
}

public struct Quota: Codable, Sendable {
    public var plan: String = "FREE"
    public var captureHoursUsed: Double = 0
    public var captureHoursLimit: Double = 0
    public var reasonerCallsUsed: Int = 0
    public var reasonerCallsLimit: Int = 0
}

public struct Me: Codable, Sendable {
    public var user: JSONValue
    public var tenant: JSONValue
    public var spaces: [Space]
    public var quota: Quota
    public var processingDisclosureVersion: String
    public var policyVersion: String
}

/// Observed capability report. Every field reflects real OS state, never an assumption.
public struct Capabilities: Codable, Hashable, Sendable {
    public var micPermission: String
    public var inputRoute: String?
    public var outputRoute: String?
    public var outputDeviceName: String?
    public var privateRouteVerified: Bool
    public var measuredLevelDbfs: Double?
    public var platform: String = "IOS"
    public var backgroundCaptureSupported: Bool = true
    public init(micPermission: String, inputRoute: String?, outputRoute: String?, outputDeviceName: String?, privateRouteVerified: Bool,
                measuredLevelDbfs: Double?) {
        self.micPermission = micPermission; self.inputRoute = inputRoute; self.outputRoute = outputRoute
        self.outputDeviceName = outputDeviceName; self.privateRouteVerified = privateRouteVerified; self.measuredLevelDbfs = measuredLevelDbfs
    }
}

public struct IngestCredential: Codable, Sendable {
    public var token: String
    public var expiresAt: String
    public var resumeCursor: Int64
    public var drainOnly: Bool?
    public var maxSequence: Int64?
}

public struct Gap: Codable, Hashable, Sendable {
    public var startMs: Int64
    public var endMs: Int64?
    public var reason: String
    public var missingSequenceFrom: Int64?
    public var missingSequenceTo: Int64?
    public var timeBoundsEstimated: Bool?
}

public struct RouteView: Codable, Sendable {
    public var input: String?
    public var output: String?
    public var deviceName: String?
    public var privateRouteVerified: Bool?
    public var audioQuality: String?
}

public struct Finalization: Codable, Sendable { public var status: String; public var attempts: Int; public var error: String? }

public struct SessionView: Codable, Identifiable, Sendable {
    public var sessionId: String
    public var spaceId: String
    public var projectId: String?
    public var context: String
    public var preset: String?
    public var interviewMode: String?
    public var title: String
    public var state: String
    public var captureSource: String
    public var sourceWatermarkMs: Int64
    public var version: Int64
    public var capturePermitted: Bool
    public var aiAssistancePermitted: Bool
    public var assistanceMode: String
    public var proactiveIntensity: String
    public var outputMode: String
    public var sensitive: Bool
    public var retentionPolicyId: String?
    public var mutedUntil: String?
    public var transcriptStatus: String
    public var finalization: Finalization
    public var reviewState: String
    public var gaps: [Gap]
    public var ingest: JSONValue?
    public var route: RouteView?
    public var speakersNeedReview: Bool?
    public var eventCursor: Int64?
    public var id: String { sessionId }

    public var ingestCredential: IngestCredential? {
        guard let ingest, case .object = ingest, let data = try? Wire.encoder.encode(ingest) else { return nil }
        return try? Wire.decoder.decode(IngestCredential.self, from: data)
    }
}

public struct SessionSummary: Codable, Identifiable, Sendable {
    public var sessionId: String
    public var title: String
    public var context: String
    public var state: String
    public var createdAt: String
    public var sourceWatermarkMs: Int64
    public var decisions: Int
    public var openItems: Int
    public var id: String { sessionId }
}

public struct Page<T: Codable & Sendable>: Codable, Sendable { public var items: [T]; public var nextCursor: String? }

public struct Citation: Codable, Hashable, Sendable {
    public var utteranceId: String?
    public var claimId: String?
    public var revision: Int?
    public var startMs: Int64?
    public var endMs: Int64?
    public var speakerAlias: String?
    public var speakerVerified: Bool?
    public var sessionTitle: String?
    public var isFinal: Bool?
    public var sourceKind: String?
    public var sessionId: String?
    public var text: String?
}

public struct AskSection: Codable, Hashable, Sendable { public var label: String; public var text: String; public var citations: [Citation] }
public struct ProposedAction: Codable, Hashable, Sendable { public var kind: String; public var text: String; public var requiresApproval: Bool? }

public struct AskResponse: Codable, Sendable {
    public var mode: String
    public var answer: String
    public var provenanceLabel: String
    public var citations: [Citation]
    public var uncertainty: String
    public var sections: [AskSection]
    public var proposedActions: [ProposedAction]?
    public var checkQuestion: String?
    public var searchedSessions: Int?

    public var provenanceTitle: String {
        switch provenanceLabel {
        case "FROM_CONVERSATION": return L("prov_from_conversation")
        case "FROM_USER_NOTE": return L("prov_from_notes")
        case "AI_ANALYSIS": return L("prov_ai_analysis")
        case "GENERAL_KNOWLEDGE": return L("prov_general")
        default: return L("prov_not_established")
        }
    }
}

public struct Utterance: Codable, Identifiable, Hashable, Sendable {
    public var utteranceId: String
    public var revision: Int
    public var startMs: Int64
    public var endMs: Int64
    public var text: String
    public var isFinal: Bool
    public var speakerAlias: String?
    public var speakerDisplay: String?
    public var speakerVerified: Bool?
    public var uncertain: Bool?
    public var label: String?
    public var id: String { utteranceId }
}

public struct Insight: Codable, Identifiable, Hashable, Sendable {
    public var insightId: String
    public var shortText: String
    public var kind: String
    public var sourceRefs: [Citation]
    public var expiresAt: String
    public var outputChannel: String
    public var sourceKind: String?
    public var label: String?
    public var voiceText: String?
    public var voiceMaxSeconds: Int?
    public var id: String { insightId }
}

public struct EventEnvelope: Codable, Sendable {
    public var eventId: String?
    public var schemaVersion: String?
    public var sessionId: String?
    public var sequence: Int64?
    public var createdAt: String?
    public var type: String
    public var payload: JSONValue?
    public var code: String?
}

public struct ChunkAck: Codable, Sendable {
    public var receivedThroughSequence: Int64
    public var gapSequences: [Int64]
    public var gapSequencesTruncated: Bool?
    public var checksumConfirmed: Bool
    public var sequence: Int64?
    public var status: String?
}
