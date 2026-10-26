package app.meetsaathi.audio

import app.meetsaathi.core.ApiErrorBody
import app.meetsaathi.core.ChunkAck
import app.meetsaathi.core.WireJson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** Transport seam so the upload policy is unit-testable without a network. */
interface ChunkTransport {
    /** Returns HTTP status and body. Throws IOException when offline. */
    fun put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk): Pair<Int, String>
}

class OkHttpChunkTransport(private val baseUrl: String, private val http: OkHttpClient) : ChunkTransport {
    private val octet = "application/octet-stream".toMediaType()
    override fun put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk): Pair<Int, String> {
        val req = Request.Builder().url("${baseUrl.trimEnd('/')}/v1/ingest/sessions/$sessionId/chunks/${chunk.sequence}")
            .header("Authorization", "Bearer $token")
            .header("X-Sample-Rate", chunk.sampleRate.toString())
            .header("X-Capture-Start-Ms", chunk.captureStartMs.toString())
            .header("X-Duration-Ms", chunk.durationMs.toString())
            .header("X-Sha256", chunk.sha256)
            .header("X-Encoding", "pcm_s16le")
            .apply { deviceId?.let { header("X-Device-Id", it) } }
            .put(chunk.pcm.toRequestBody(octet)).build()
        http.newCall(req).execute().use { return it.code to (it.body?.string() ?: "") }
    }
}

data class UploadStatus(
    val online: Boolean = true,
    val receivedThrough: Long = -1,
    val pending: Int = 0,
    val gaps: List<Long> = emptyList(),
    val stoppedReason: String? = null,
)

/**
 * Resumable, idempotent uploader (master 7.2, IMP-005): sends spooled chunks in sequence order, resumes from the
 * server cursor after reconnect, refreshes short-lived ingest credentials, and never re-sends ACKed audio.
 */
class Uploader(
    private val spool: ChunkSpool,
    private val transport: ChunkTransport,
    private val sessionId: String,
    private val deviceId: String?,
    private val credentials: suspend (expired: Boolean) -> String?,
) {
    private val _status = MutableStateFlow(UploadStatus())
    val status: StateFlow<UploadStatus> = _status
    private var job: Job? = null
    @Volatile private var token: String? = null

    fun start(scope: CoroutineScope, initialToken: String?) {
        token = initialToken
        job?.cancel()
        job = scope.launch(Dispatchers.IO) { loop() }
    }

    fun stop() { job?.cancel() }

    /** One pass over the spool. Returns false when it should back off (offline / no credential). */
    suspend fun pass(): Boolean {
        val pending = spool.pendingSequences()
        _status.value = _status.value.copy(pending = pending.size)
        for (seq in pending) {
            val chunk = spool.read(seq) ?: run { spool.drop(seq); null } ?: continue
            val tok = token ?: credentials(false).also { token = it } ?: run {
                _status.value = _status.value.copy(stoppedReason = "NO_CREDENTIAL"); return false
            }
            val (code, body) = try {
                transport.put(sessionId, tok, deviceId, chunk)
            } catch (e: IOException) {
                _status.value = _status.value.copy(online = false); return false
            }
            _status.value = _status.value.copy(online = true)
            when (code) {
                200 -> {
                    val ack = WireJson.decodeFromString(ChunkAck.serializer(), body)
                    spool.drop(seq) // this sequence is stored server-side (ACKED or idempotent DUPLICATE)
                    spool.ackThrough(ack.receivedThrough)
                    _status.value = _status.value.copy(receivedThrough = ack.receivedThrough, gaps = ack.gapSequences,
                        pending = spool.pendingSequences().size)
                }
                401 -> {
                    val err = runCatching { WireJson.decodeFromString(ApiErrorBody.serializer(), body) }.getOrNull()
                    token = null
                    if (err?.code == "INGEST_REVOKED") {
                        _status.value = _status.value.copy(stoppedReason = "DEVICE_REVOKED"); return false
                    }
                    token = credentials(true) ?: return false
                    return true
                }
                409 -> {
                    val err = runCatching { WireJson.decodeFromString(ApiErrorBody.serializer(), body) }.getOrNull()
                    when (err?.code) {
                        // Same bytes are already stored => nothing to retry. A conflict means local corruption; keep server copy.
                        "CHUNK_CONFLICT" -> spool.drop(seq)
                        // Server no longer accepts this sequence (paused/ended/withdrawn): never resend it.
                        "CAPTURE_PAUSED", "SESSION_ENDED", "SESSION_NOT_CAPTURING" -> spool.drop(seq)
                        else -> return false
                    }
                }
                403 -> { spool.drop(seq); _status.value = _status.value.copy(stoppedReason = "NOT_AUTHORIZED") }
                422 -> {
                    val ack = runCatching { WireJson.decodeFromString(ChunkAck.serializer(), body) }.getOrNull()
                    if (ack != null && !ack.checksumConfirmed) return true // transient corruption: resend next pass
                    spool.drop(seq)
                }
                else -> return false
            }
        }
        return true
    }

    private suspend fun kotlinx.coroutines.CoroutineScope.loop() {
        var backoff = 500L
        while (isActive) {
            val ok = pass()
            if (ok && spool.pendingSequences().isEmpty()) {
                backoff = 500L
                delay(400)
            } else if (ok) {
                backoff = 500L
            } else {
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(15_000)
            }
        }
    }
}
