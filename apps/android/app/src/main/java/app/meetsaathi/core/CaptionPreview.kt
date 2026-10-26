package app.meetsaathi.core

/** Ephemeral hypotheses have no citation IDs and never enter the evidence transcript. */
data class CaptionPreview(val runId: String, val previewId: String, val text: String, val startMs: Long,
                          val expiresAtMs: Long = System.currentTimeMillis() + 15_000) {
    fun clearedBy(run: String?, preview: String?): Boolean = run == runId && (preview == null || preview == previewId)
    fun expired(nowMs: Long = System.currentTimeMillis()): Boolean = nowMs >= expiresAtMs
}
