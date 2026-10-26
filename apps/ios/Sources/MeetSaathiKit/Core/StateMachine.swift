import Foundation

/// Mirror of backend/app/domain/state_machine.py (master 7.1); pinned by packages/contracts/state_machine_v1.json.
public enum SessionState: String, CaseIterable, Sendable {
    case PREFLIGHT, NOTES_ONLY, STARTING, RECORDING, PAUSED, INTERRUPTED, STOPPING, FINALIZING,
         FINALIZATION_RETRYABLE, COMPLETED, COMPLETED_PARTIAL, ERROR, DELETING, DELETED

    public static func parse(_ s: String) -> SessionState { SessionState(rawValue: s) ?? .ERROR }
}

public enum SessionStateMachine {
    public static let transitions: [SessionState: Set<SessionState>] = [
        .PREFLIGHT: [.STARTING, .NOTES_ONLY, .STOPPING, .ERROR, .DELETING],
        .NOTES_ONLY: [.STARTING, .STOPPING, .DELETING],
        .STARTING: [.RECORDING, .ERROR, .STOPPING, .INTERRUPTED, .DELETING],
        .RECORDING: [.PAUSED, .INTERRUPTED, .STOPPING, .DELETING],
        .PAUSED: [.STARTING, .STOPPING, .DELETING],
        .INTERRUPTED: [.STARTING, .STOPPING, .DELETING],
        .STOPPING: [.FINALIZING, .DELETING],
        .FINALIZING: [.COMPLETED, .COMPLETED_PARTIAL, .FINALIZATION_RETRYABLE, .DELETING],
        .FINALIZATION_RETRYABLE: [.FINALIZING, .DELETING],
        .COMPLETED: [.DELETING],
        .COMPLETED_PARTIAL: [.DELETING],
        .ERROR: [.STARTING, .STOPPING, .DELETING],
        .DELETING: [.DELETED],
        .DELETED: [],
    ]

    public static func canTransition(_ from: SessionState, _ to: SessionState) -> Bool { transitions[from]?.contains(to) ?? false }
    public static let active: Set<SessionState> = [.STARTING, .RECORDING, .PAUSED, .INTERRUPTED, .NOTES_ONLY]
    public static let ended: Set<SessionState> = [.STOPPING, .FINALIZING, .FINALIZATION_RETRYABLE, .COMPLETED, .COMPLETED_PARTIAL]
}

/// What the header may honestly say. "Recording" requires BOTH server RECORDING/STARTING and real audio buffers.
public enum CaptureTruth: String, Sendable {
    case off = "truth_off"
    case starting = "truth_starting"
    case recording = "truth_recording"
    case recordingLocal = "truth_recording_local"
    case paused = "truth_paused"
    case interrupted = "truth_interrupted"
    case notesOnly = "truth_notes_only"
    case stopped = "truth_stopped"
    case micDenied = "truth_mic_denied"

    /// What the header may honestly say, localized.
    public var label: String { L(rawValue) }
}

public func captureTruth(server: SessionState, localBuffersFlowing: Bool, online: Bool, micPermission: Bool) -> CaptureTruth {
    if !micPermission && server != .NOTES_ONLY && SessionStateMachine.active.contains(server) { return .micDenied }
    switch server {
    case .NOTES_ONLY: return .notesOnly
    case .PAUSED: return .paused
    case .INTERRUPTED: return .interrupted
    case _ where SessionStateMachine.ended.contains(server): return .stopped
    case .RECORDING, .STARTING: return localBuffersFlowing ? (online ? .recording : .recordingLocal) : .starting
    default: return .off
    }
}

public func clockString(_ ms: Int64?) -> String {
    let s = max(0, (ms ?? 0) / 1000)
    return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60) : String(format: "%02d:%02d", s / 60, s % 60)
}
