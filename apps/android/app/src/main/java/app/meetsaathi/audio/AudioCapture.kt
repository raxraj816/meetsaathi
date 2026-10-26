package app.meetsaathi.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import kotlin.concurrent.thread
import kotlin.math.log10
import kotlin.math.sqrt

/** Pure helpers (unit-tested): level and a conservative energy VAD used only to avoid talking over speech. */
object Signal {
    fun rmsDbfs(pcm: ShortArray, n: Int = pcm.size): Double {
        if (n == 0) return -120.0
        var acc = 0.0
        for (i in 0 until n) acc += pcm[i].toDouble() * pcm[i]
        val rms = sqrt(acc / n)
        return if (rms <= 0) -120.0 else 20 * log10(rms / 32768.0)
    }

    fun quality(dbfs: Double): String = when {
        dbfs < -55 -> "SILENT_OR_BLOCKED"
        dbfs < -42 -> "POOR"
        else -> "GOOD"
    }

    fun toBytes(pcm: ShortArray, n: Int): ByteArray {
        val out = ByteArray(n * 2)
        for (i in 0 until n) {
            out[2 * i] = (pcm[i].toInt() and 0xFF).toByte()
            out[2 * i + 1] = ((pcm[i].toInt() shr 8) and 0xFF).toByte()
        }
        return out
    }
}

/**
 * AudioRecord capture at 16 kHz mono PCM16 in 1 s chunks. [onFirstBuffer] fires only when real frames arrive,
 * which is the only signal allowed to turn the UI to "Recording" (master 7.1 invariant).
 */
class AudioCapture(
    private val sampleRate: Int = 16_000,
    private val onFirstBuffer: () -> Unit,
    private val onChunk: (startOffsetMs: Long, durationMs: Int, pcm: ByteArray, levelDbfs: Double) -> Unit,
    private val onLevel: (Double) -> Unit,
    private val onFailure: (String) -> Unit,
) {
    @Volatile private var running = false
    private var record: AudioRecord? = null
    private var worker: Thread? = null

    /** Offset of the capture clock relative to session start, so pauses produce visible gaps, not overlaps. */
    @Volatile var sessionClockOriginElapsed: Long = SystemClock.elapsedRealtime()

    val routedInputType: Int? get() = record?.routedDevice?.type

    @SuppressLint("MissingPermission") // checked by the caller before starting the foreground service
    fun start(): Boolean {
        val minBuf = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minBuf <= 0) { onFailure("INPUT_LOST"); return false }
        val rec = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, sampleRate, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, sampleRate / 5 * 2))
        } catch (e: SecurityException) {
            onFailure("PERMISSION_REVOKED"); return false
        }
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release(); onFailure("INPUT_LOST"); return false // e.g. microphone occupied by another app (INT-037)
        }
        record = rec
        rec.startRecording()
        if (rec.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            rec.release(); record = null; onFailure("INPUT_LOST"); return false
        }
        running = true
        worker = thread(name = "ms-capture", priority = Thread.MAX_PRIORITY) { readLoop(rec) }
        return true
    }

    private fun readLoop(rec: AudioRecord) {
        val frame = ShortArray(sampleRate / 10) // 100 ms
        val chunk = ShortArray(sampleRate)        // 1 s
        var filled = 0
        var first = true
        var chunkStart = SystemClock.elapsedRealtime() - sessionClockOriginElapsed
        while (running) {
            val n = rec.read(frame, 0, frame.size)
            if (n < 0) { if (running) onFailure("INPUT_LOST"); break }
            if (n == 0) continue
            if (first) { first = false; onFirstBuffer() }
            onLevel(Signal.rmsDbfs(frame, n))
            var off = 0
            while (off < n) {
                val take = minOf(n - off, chunk.size - filled)
                System.arraycopy(frame, off, chunk, filled, take)
                filled += take; off += take
                if (filled == chunk.size) {
                    onChunk(chunkStart, 1000, Signal.toBytes(chunk, filled), Signal.rmsDbfs(chunk, filled))
                    filled = 0
                    chunkStart += 1000
                }
            }
        }
        if (filled > sampleRate / 10) { // flush the last partial chunk (>=100 ms) so nothing captured is lost
            val ms = filled * 1000 / sampleRate
            onChunk(chunkStart, ms, Signal.toBytes(chunk, filled), Signal.rmsDbfs(chunk, filled))
        }
    }

    /** Stops the microphone immediately; local stop never waits for the network (ADR-010). */
    fun stop() {
        running = false
        record?.let { runCatching { it.stop() }; it.release() }
        record = null
        worker?.join(1500)
        worker = null
    }
}
