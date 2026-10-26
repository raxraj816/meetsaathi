package app.meetsaathi.core

import android.content.Context
import app.meetsaathi.R

/**
 * What may honestly be said about a capture gap. Unknown ends stay unknown; adjacent source timestamps only
 * bound an upload gap approximately. Structured (not prose) so copy lives in string resources.
 */
sealed interface GapPhrase {
    data object TimingUnknown : GapPhrase
    data class After(val start: String) : GapPhrase
    data class Between(val start: String, val end: String, val approximate: Boolean) : GapPhrase
}

fun captureGapPhrase(startMs: Long?, endMs: Long?, estimated: Boolean, reason: String): GapPhrase {
    if (startMs == null || startMs < 0 || (endMs != null && endMs < startMs)) return GapPhrase.TimingUnknown
    val start = gapClock(startMs)
    if (endMs == null) return GapPhrase.After(start)
    return GapPhrase.Between(start, gapClock(endMs), approximate = estimated || reason == "UPLOAD_MISSING")
}

fun Gap.phrase() = captureGapPhrase(startMs, endMs, timeBoundsEstimated, reason)

fun GapPhrase.render(context: Context): String = when (this) {
    GapPhrase.TimingUnknown -> context.getString(R.string.gap_timing_unknown)
    is GapPhrase.After -> context.getString(R.string.gap_after, start)
    is GapPhrase.Between -> context.getString(if (approximate) R.string.gap_between_approx else R.string.gap_between, start, end)
}

private fun gapClock(ms: Long): String {
    val total = ms / 1000
    val minutes = (total % 3600) / 60
    val seconds = total % 60
    return if (total >= 3600) "${total / 3600}:%02d:%02d".format(minutes, seconds)
    else "%d:%02d".format(minutes, seconds)
}
