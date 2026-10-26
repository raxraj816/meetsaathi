package app.meetsaathi.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Exact, durable stop request: retries keep both the watermark and timestamp after process death. */
@Serializable
data class PendingStop(@SerialName("final_sequence") val finalSequence: Long, @SerialName("at_ms") val atMs: Long) {
    fun body(): String = WireJson.encodeToString(serializer(), this)

    fun save(dir: File) {
        check(dir.isDirectory || dir.mkdirs()) { "Cannot persist stop request" }
        val tmp = File.createTempFile("stop-", ".tmp", dir)
        try {
            FileOutputStream(tmp).use { it.write(body().toByteArray()); it.fd.sync() }
            Files.move(tmp.toPath(), File(dir, NAME).toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        } finally { tmp.delete() }
    }

    companion object {
        private const val NAME = "pending_stop.json"
        fun load(dir: File): PendingStop? = runCatching { WireJson.decodeFromString(serializer(), File(dir, NAME).readText()) }.getOrNull()
        fun clear(dir: File) { File(dir, NAME).delete() }
    }
}
