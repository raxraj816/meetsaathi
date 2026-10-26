package app.meetsaathi.audio

import app.meetsaathi.core.Sealer
import java.io.File
import java.security.MessageDigest

/** One captured audio unit (master 7.2): monotonic sequence + capture offset + checksum. */
data class SpooledChunk(
    val sequence: Long,
    val captureStartMs: Long,
    val durationMs: Int,
    val sampleRate: Int,
    val sha256: String,
    val pcm: ByteArray,
)

/**
 * Encrypted, bounded local spool. Chunks are sealed with a device Keystore key (AAD = session + sequence) and
 * deleted as soon as the server ACK watermark covers them. When the cap is reached [append] refuses, so the
 * caller can stop capture safely with an explicit message rather than exhausting the disk (master 7.2).
 */
class ChunkSpool(private val dir: File, private val sealer: Sealer, private val sessionId: String,
                 private val capBytes: Long = 200L * 1024 * 1024) {
    init { dir.mkdirs() }

    sealed class AppendResult {
        data object Stored : AppendResult()
        data object StorageFull : AppendResult()
    }

    private fun file(seq: Long) = File(dir, "%012d.chunk".format(seq))
    private fun aad(seq: Long) = "$sessionId:$seq".toByteArray()

    fun bytesUsed(): Long = dir.listFiles()?.sumOf { it.length() } ?: 0L

    fun append(seq: Long, captureStartMs: Long, durationMs: Int, sampleRate: Int, pcm: ByteArray): AppendResult {
        if (bytesUsed() + pcm.size + 128 > capBytes) return AppendResult.StorageFull
        val header = "$captureStartMs,$durationMs,$sampleRate,${sha256Hex(pcm)}\n".toByteArray()
        val tmp = File(dir, file(seq).name + ".tmp")
        tmp.writeBytes(sealer.seal(header + pcm, aad(seq)))
        if (!tmp.renameTo(file(seq))) {
            tmp.delete(); return AppendResult.StorageFull
        }
        return AppendResult.Stored
    }

    fun pendingSequences(): List<Long> =
        dir.listFiles { f -> f.name.endsWith(".chunk") }?.mapNotNull { it.name.removeSuffix(".chunk").toLongOrNull() }?.sorted() ?: emptyList()

    fun read(seq: Long): SpooledChunk? {
        val f = file(seq)
        if (!f.exists()) return null
        val plain = runCatching { sealer.open(f.readBytes(), aad(seq)) }.getOrNull() ?: return null
        val nl = plain.indexOf('\n'.code.toByte())
        val (start, dur, rate, sha) = String(plain, 0, nl).split(",")
        return SpooledChunk(seq, start.toLong(), dur.toInt(), rate.toInt(), sha, plain.copyOfRange(nl + 1, plain.size))
    }

    /** Server ACKed everything through [through]: remove local copies (retention covers the spool too). */
    fun ackThrough(through: Long) {
        pendingSequences().filter { it <= through }.forEach { file(it).delete() }
    }

    fun drop(seq: Long) { file(seq).delete() }

    fun purgeAll() {
        dir.listFiles()?.forEach { it.delete() }
    }

    companion object {
        fun sha256Hex(b: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }
    }
}
