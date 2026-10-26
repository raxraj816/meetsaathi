package app.meetsaathi.core

import androidx.annotation.StringRes
import app.meetsaathi.R

/**
 * Mirror of the authoritative server table (backend/app/domain/state_machine.py, master 7.1).
 * The client never invents a state: it renders the server state plus *locally observed* capture truth.
 */
enum class SessionState {
    PREFLIGHT, NOTES_ONLY, STARTING, RECORDING, PAUSED, INTERRUPTED, STOPPING, FINALIZING,
    FINALIZATION_RETRYABLE, COMPLETED, COMPLETED_PARTIAL, ERROR, DELETING, DELETED;

    companion object {
        fun parse(s: String): SessionState = entries.firstOrNull { it.name == s } ?: ERROR
    }
}

object SessionStateMachine {
    private val transitions: Map<SessionState, Set<SessionState>> = mapOf(
        SessionState.PREFLIGHT to setOf(SessionState.STARTING, SessionState.NOTES_ONLY, SessionState.STOPPING, SessionState.ERROR, SessionState.DELETING),
        SessionState.NOTES_ONLY to setOf(SessionState.STARTING, SessionState.STOPPING, SessionState.DELETING),
        SessionState.STARTING to setOf(SessionState.RECORDING, SessionState.ERROR, SessionState.STOPPING, SessionState.INTERRUPTED, SessionState.DELETING),
        SessionState.RECORDING to setOf(SessionState.PAUSED, SessionState.INTERRUPTED, SessionState.STOPPING, SessionState.DELETING),
        SessionState.PAUSED to setOf(SessionState.STARTING, SessionState.STOPPING, SessionState.DELETING),
        SessionState.INTERRUPTED to setOf(SessionState.STARTING, SessionState.STOPPING, SessionState.DELETING),
        SessionState.STOPPING to setOf(SessionState.FINALIZING, SessionState.DELETING),
        SessionState.FINALIZING to setOf(SessionState.COMPLETED, SessionState.COMPLETED_PARTIAL, SessionState.FINALIZATION_RETRYABLE, SessionState.DELETING),
        SessionState.FINALIZATION_RETRYABLE to setOf(SessionState.FINALIZING, SessionState.DELETING),
        SessionState.COMPLETED to setOf(SessionState.DELETING),
        SessionState.COMPLETED_PARTIAL to setOf(SessionState.DELETING),
        SessionState.ERROR to setOf(SessionState.STARTING, SessionState.STOPPING, SessionState.DELETING),
        SessionState.DELETING to setOf(SessionState.DELETED),
        SessionState.DELETED to emptySet(),
    )

    fun canTransition(from: SessionState, to: SessionState): Boolean = transitions[from]?.contains(to) == true

    val active = setOf(SessionState.STARTING, SessionState.RECORDING, SessionState.PAUSED, SessionState.INTERRUPTED, SessionState.NOTES_ONLY)
    val ended = setOf(SessionState.STOPPING, SessionState.FINALIZING, SessionState.FINALIZATION_RETRYABLE, SessionState.COMPLETED, SessionState.COMPLETED_PARTIAL)
}

/** What the header may honestly say. "Recording" requires BOTH server RECORDING and real local audio buffers. */
enum class CaptureTruth(@StringRes val labelRes: Int) {
    OFF(R.string.truth_off),
    STARTING(R.string.truth_starting),
    RECORDING(R.string.truth_recording),
    RECORDING_LOCAL(R.string.truth_recording_local),
    PAUSED(R.string.truth_paused),
    INTERRUPTED(R.string.truth_interrupted),
    NOTES_ONLY(R.string.truth_notes_only),
    STOPPED(R.string.truth_stopped),
    MIC_DENIED(R.string.truth_mic_denied),
}

fun captureTruth(server: SessionState, localBuffersFlowing: Boolean, online: Boolean, micPermission: Boolean): CaptureTruth = when {
    !micPermission && server != SessionState.NOTES_ONLY && server in SessionStateMachine.active -> CaptureTruth.MIC_DENIED
    server == SessionState.NOTES_ONLY -> CaptureTruth.NOTES_ONLY
    server == SessionState.PAUSED -> CaptureTruth.PAUSED
    server == SessionState.INTERRUPTED -> CaptureTruth.INTERRUPTED
    server in SessionStateMachine.ended -> CaptureTruth.STOPPED
    (server == SessionState.RECORDING || server == SessionState.STARTING) && localBuffersFlowing -> if (online) CaptureTruth.RECORDING else CaptureTruth.RECORDING_LOCAL
    server == SessionState.STARTING || server == SessionState.RECORDING -> CaptureTruth.STARTING
    else -> CaptureTruth.OFF
}
