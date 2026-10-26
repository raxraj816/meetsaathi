package app.meetsaathi.core

import app.meetsaathi.audio.ChunkSpool
import app.meetsaathi.audio.ChunkTransport
import app.meetsaathi.audio.Signal
import app.meetsaathi.audio.SpooledChunk
import app.meetsaathi.audio.Uploader
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException
import java.nio.file.Files
import javax.crypto.KeyGenerator

class StateMachineParityTest {
    /** The client table must equal the server table exactly (packages/contracts/state_machine_v1.json). */
    @Test fun matchesServerContract() {
        val text = javaClass.classLoader!!.getResource("state_machine_v1.json")!!.readText()
        val t = Json.parseToJsonElement(text) as JsonObject
        val transitions = t["transitions"] as JsonObject
        assertEquals(SessionState.entries.map { it.name }.toSet(), transitions.keys)
        for ((from, tos) in transitions) {
            val allowed = (tos as JsonArray).map { it.jsonPrimitive.content }.toSet()
            for (to in SessionState.entries) {
                assertEquals("$from -> ${to.name}", to.name in allowed,
                    SessionStateMachine.canTransition(SessionState.valueOf(from), to))
            }
        }
    }

    @Test fun recordingRequiresRealBuffers() {
        assertEquals(CaptureTruth.STARTING, captureTruth(SessionState.RECORDING, localBuffersFlowing = false, online = true, micPermission = true))
        assertEquals(CaptureTruth.RECORDING, captureTruth(SessionState.RECORDING, true, true, true))
        assertEquals(CaptureTruth.RECORDING_LOCAL, captureTruth(SessionState.RECORDING, true, online = false, micPermission = true))
        assertEquals(CaptureTruth.MIC_DENIED, captureTruth(SessionState.RECORDING, false, true, micPermission = false))
        assertEquals(CaptureTruth.NOTES_ONLY, captureTruth(SessionState.NOTES_ONLY, false, true, false))
        assertEquals(CaptureTruth.PAUSED, captureTruth(SessionState.PAUSED, false, true, true))
        assertEquals(CaptureTruth.STOPPED, captureTruth(SessionState.FINALIZING, false, true, true))
    }
}

class SignalTest {
    @Test fun silenceIsBlocked() {
        assertEquals("SILENT_OR_BLOCKED", Signal.quality(Signal.rmsDbfs(ShortArray(1600))))
    }

    @Test fun pcmLittleEndian() {
        val b = Signal.toBytes(shortArrayOf(0x0102, -2), 2)
        assertEquals(listOf(0x02, 0x01, 0xFE, 0xFF), b.map { it.toInt() and 0xFF })
    }
}

private fun testSealer(): Sealer {
    val key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
    return AesGcmSealer { key }
}

class ChunkSpoolTest {
    private fun spool(cap: Long = 10_000_000): Pair<ChunkSpool, File> {
        val dir = Files.createTempDirectory("spool").toFile()
        return ChunkSpool(dir, testSealer(), "s1", cap) to dir
    }

    @Test fun encryptedAtRestAndRoundTrips() {
        val (sp, dir) = spool()
        val pcm = ByteArray(32000) { (it % 251).toByte() }
        assertEquals(ChunkSpool.AppendResult.Stored, sp.append(0, 0, 1000, 16000, pcm))
        val raw = dir.listFiles()!!.single().readBytes()
        assertFalse("plaintext must not be on disk", raw.toList().windowed(64).any { it == pcm.take(64) })
        val back = sp.read(0)!!
        assertTrue(back.pcm.contentEquals(pcm))
        assertEquals(ChunkSpool.sha256Hex(pcm), back.sha256)
    }

    @Test fun tamperedChunkIsNotReturned() {
        val (sp, dir) = spool()
        sp.append(0, 0, 1000, 16000, ByteArray(32000))
        val f = dir.listFiles()!!.single()
        val b = f.readBytes(); b[40] = (b[40].toInt() xor 0xFF).toByte(); f.writeBytes(b)
        assertNull(sp.read(0))
    }

    @Test fun capRefusesInsteadOfFillingDisk() {
        val (sp, _) = spool(cap = 50_000)
        assertEquals(ChunkSpool.AppendResult.Stored, sp.append(0, 0, 1000, 16000, ByteArray(32000)))
        assertEquals(ChunkSpool.AppendResult.StorageFull, sp.append(1, 1000, 1000, 16000, ByteArray(32000)))
    }

    @Test fun ackDeletesCoveredChunks() {
        val (sp, _) = spool()
        for (i in 0L..4L) sp.append(i, i * 1000, 1000, 16000, ByteArray(100))
        sp.ackThrough(2)
        assertEquals(listOf(3L, 4L), sp.pendingSequences())
    }
}

class UploaderTest {
    private class FakeTransport(val script: MutableList<(SpooledChunk) -> Pair<Int, String>>) : ChunkTransport {
        val sent = mutableListOf<Long>()
        override fun put(sessionId: String, token: String, deviceId: String?, chunk: SpooledChunk): Pair<Int, String> {
            sent += chunk.sequence
            return script.removeAt(0)(chunk)
        }
    }

    private fun ack(through: Long, status: String = "ACKED") = 200 to """{"received_through_sequence":$through,"gap_sequences":[],"checksum_confirmed":true,"status":"$status"}"""

    private fun newSpool(n: Int): ChunkSpool {
        val sp = ChunkSpool(Files.createTempDirectory("up").toFile(), testSealer(), "s1")
        for (i in 0 until n) sp.append(i.toLong(), i * 1000L, 1000, 16000, ByteArray(320) { i.toByte() })
        return sp
    }

    @Test fun uploadsInOrderAndClearsSpool() = runTest {
        val sp = newSpool(3)
        val tr = FakeTransport(mutableListOf({ ack(0) }, { ack(1) }, { ack(2) }))
        val up = Uploader(sp, tr, "s1", "d1") { "tok" }
        assertTrue(up.pass())
        assertEquals(listOf(0L, 1L, 2L), tr.sent)
        assertTrue(sp.pendingSequences().isEmpty())
        assertEquals(2L, up.status.value.receivedThrough)
    }

    @Test fun offlineKeepsChunksAndReportsOffline() = runTest {
        val sp = newSpool(2)
        val tr = FakeTransport(mutableListOf({ throw IOException("down") }))
        val up = Uploader(sp, tr, "s1", "d1") { "tok" }
        assertFalse(up.pass())
        assertFalse(up.status.value.online)
        assertEquals(listOf(0L, 1L), sp.pendingSequences())
    }

    @Test fun expiredCredentialIsRefreshedAndChunkResent() = runTest {
        val sp = newSpool(1)
        val tr = FakeTransport(mutableListOf({ 401 to """{"code":"INGEST_TOKEN_EXPIRED","user_message":"x","retryable":true,"correlation_id":"c"}""" }, { ack(0) }))
        var refreshed = 0
        val up = Uploader(sp, tr, "s1", "d1") { expired -> if (expired) refreshed++; "tok$refreshed" }
        assertTrue(up.pass())
        assertTrue(up.pass())
        assertEquals(1, refreshed)
        assertEquals(listOf(0L, 0L), tr.sent)
        assertTrue(sp.pendingSequences().isEmpty())
    }

    @Test fun pausedServerRejectionIsNeverRetried() = runTest {
        val sp = newSpool(1)
        val tr = FakeTransport(mutableListOf({ 409 to """{"code":"CAPTURE_PAUSED","user_message":"x","retryable":false,"correlation_id":"c"}""" }))
        val up = Uploader(sp, tr, "s1", "d1") { "tok" }
        assertTrue(up.pass())
        assertTrue(sp.pendingSequences().isEmpty())
    }

    @Test fun revokedDeviceStops() = runTest {
        val sp = newSpool(1)
        val tr = FakeTransport(mutableListOf({ 401 to """{"code":"INGEST_REVOKED","user_message":"x","retryable":false,"correlation_id":"c"}""" }))
        val up = Uploader(sp, tr, "s1", "d1") { "tok" }
        assertFalse(up.pass())
        assertEquals("DEVICE_REVOKED", up.status.value.stoppedReason)
        assertNotNull(sp.read(0))
    }
}

class WireModelTest {
    @Test fun parsesInsightEventPayload() {
        val ev = WireJson.decodeFromString(EventEnvelope.serializer(), """{"event_id":"e","schema_version":"1.0","session_id":"s","sequence":7,
            "created_at":"2026-10-18T10:00:00Z","type":"insight.delivered","payload":{"insight_id":"i","short_text":"Ask who owns rollback.",
            "kind":"CLARIFY","source_refs":[{"utterance_id":"u","revision":1,"start_ms":1000,"end_ms":2000,"speaker_alias":"Speaker A"}],
            "expires_at":"2026-10-18T10:02:00Z","policy_version":"p","output_channel":"TEXT","label":"MeetSaathi suggests"}}""")
        val ins = WireJson.decodeFromJsonElement(Insight.serializer(), ev.payload)
        assertEquals("TEXT", ins.outputChannel)
        assertEquals(1000L, ins.sourceRefs.single().startMs)
    }
}

class PendingStopTest {
    @Test fun exactStopBodySurvivesRestart() {
        val dir = Files.createTempDirectory("ms-stop-test").toFile()
        try {
            val stop = PendingStop(8, 9123)
            stop.save(dir)
            val recovered = PendingStop.load(dir)
            assertEquals(stop, recovered)
            assertEquals(stop.body(), recovered!!.body())
            assertTrue(recovered.body().contains("\"final_sequence\":8"))
            assertTrue(recovered.body().contains("\"at_ms\":9123"))
            PendingStop.clear(dir)
            assertNull(PendingStop.load(dir))
        } finally { dir.deleteRecursively() }
    }
}

class CaptionPreviewTest {
    @Test fun lateClearDoesNotEraseANewerDraft() {
        val draft = CaptionPreview("new-run", "next-result", "Draft words", 1200, expiresAtMs = 15_000)
        assertFalse(draft.clearedBy("old-run", null))
        assertFalse(draft.clearedBy("new-run", "previous-result"))
        assertTrue(draft.clearedBy("new-run", "next-result"))
        assertTrue(draft.clearedBy("new-run", null))
        assertFalse(draft.expired(14_999))
        assertTrue(draft.expired(15_000))
    }
}

class GapDescriptionTest {
    @Test fun unknownEndStaysUnknownForLegacyAndCurrentPayloads() {
        val gap = WireJson.decodeFromString(Gap.serializer(), """{"start_ms":6000,"end_ms":null,"reason":"UPLOAD_MISSING"}""")
        assertEquals(GapPhrase.After("0:06"), gap.phrase())
        assertEquals(GapPhrase.TimingUnknown, captureGapPhrase(null, null, false, "UPLOAD_MISSING"))
        assertEquals(GapPhrase.TimingUnknown, captureGapPhrase(9000, 3000, false, "INPUT_LOST"))
    }
    @Test fun estimatedGapIsNotPresentedAsAnExactInterval() {
        val gap = WireJson.decodeFromString(Gap.serializer(), """{"start_ms":6000,"end_ms":5400000,"reason":"UPLOAD_MISSING","missing_sequence_from":1,"missing_sequence_to":9223372036854775806,"time_bounds_estimated":true}""")
        assertEquals(9223372036854775806L, gap.missingSequenceTo)
        assertEquals(GapPhrase.Between("0:06", "1:30:00", approximate = true), gap.phrase())
        assertEquals(GapPhrase.Between("0:06", "0:12", approximate = false), captureGapPhrase(6000, 12000, false, "INPUT_LOST"))
    }
}

class DatesTest {
    @Test fun serverInstantsRenderInTheReadersZone() {
        val ist = java.time.ZoneId.of("Asia/Kolkata")
        // 22:22 UTC on the 18th is already the 19th in India: the date must follow the reader, not the server.
        assertEquals("Oct 19, 2026", Dates.date("2026-10-18T22:22:05.123456+00:00", ist, java.util.Locale.US))
        assertTrue(Dates.dateTime("2026-10-18T22:22:05Z", ist, java.util.Locale.US)!!.contains("3:52"))
        assertEquals("Oct 18, 2026", Dates.date("2026-10-18", ist, java.util.Locale.US))
        assertEquals(null, Dates.date(null))
    }
}
