package app.meetsaathi.core

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.SystemClock
import androidx.core.content.ContextCompat
import app.meetsaathi.R
import app.meetsaathi.audio.AudioCapture
import app.meetsaathi.audio.CaptureService
import app.meetsaathi.audio.ChunkSpool
import app.meetsaathi.audio.OkHttpChunkTransport
import app.meetsaathi.audio.PrivateVoice
import app.meetsaathi.audio.RouteMonitor
import app.meetsaathi.audio.Signal
import app.meetsaathi.audio.Uploader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.isActive
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.io.File
import java.security.MessageDigest
import java.util.UUID

data class LiveUiState(
    val session: SessionView? = null,
    val truth: CaptureTruth = CaptureTruth.OFF,
    val elapsedMs: Long = 0,
    val levelDbfs: Double = -120.0,
    val online: Boolean = true,
    val realtimeConnected: Boolean = false,
    val insight: Insight? = null,
    val transcript: List<Utterance> = emptyList(),
    val captionPreview: CaptionPreview? = null,
    val status: String? = null,
    val statusSeverity: String = "info",
    val route: app.meetsaathi.audio.AudioRoute? = null,
    val privateRouteVerified: Boolean = false,
    val pendingUploads: Int = 0,
    val error: String? = null,
    val finalizationMessage: String? = null,
    val invalidatedClaims: Set<String> = emptySet(),
    /** Consent withdrawal not yet acknowledged by the server: capture and uploads stay stopped until it is. */
    val withdrawPending: Boolean = false,
)

/** Preflight result shown on U04: measured, not assumed. */
data class PreflightReport(val micPermission: Boolean, val levelDbfs: Double?, val quality: String?, val route: app.meetsaathi.audio.AudioRoute,
                           val warnings: List<String>)

/**
 * Coordinates one live session: server lifecycle, native capture, encrypted spool, resumable upload, realtime
 * events, route monitoring and private voice. The UI renders [state]; nothing here ever claims a state that
 * isn't observed (master 1.2 "truthful state").
 */
class LiveSessionController(private val context: Context, private val api: ApiClient) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _state = MutableStateFlow(LiveUiState())
    val state: StateFlow<LiveUiState> = _state

    val routes = RouteMonitor(context).also { it.start() }
    private var capture: AudioCapture? = null
    private var spool: ChunkSpool? = null
    private var uploader: Uploader? = null
    private var realtime: RealtimeClient? = null
    private var voice: PrivateVoice? = null
    private var ticker: Job? = null
    @Volatile private var nextSeq = 0L
    private var originElapsed = SystemClock.elapsedRealtime()
    private var buffersFlowing = false
    private var lastSpeech = 0L
    private var speakingSignalled = false
    private var locallyEnded = false
    private var stopInFlight = false
    private var recoveryJob: Job? = null

    init {
        routes.onChange { old, new ->
            _state.update { it.copy(route = new, privateRouteVerified = routes.privateRouteVerified()) }
            val s = _state.value.session ?: return@onChange
            if (old.privateOutputPresent && !routes.privateRouteVerified()) {
                voice?.hardMute() // fail closed locally first, then tell the server
                realtime?.reportRouteLost()
                setStatus(str(R.string.status_voice_disconnected), "warning")
            }
            if (old.input != new.input && truthIsLive()) setStatus(str(R.string.status_source_changed), "warning")
            scope.launch { runCatching { postRoute(s.sessionId) } }
        }
        _state.update { it.copy(route = routes.route.value) }
    }

    private fun truthIsLive() = _state.value.truth == CaptureTruth.RECORDING || _state.value.truth == CaptureTruth.RECORDING_LOCAL

    fun micGranted(): Boolean = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun str(id: Int, vararg args: Any): String = context.getString(id, *args)

    private fun setStatus(msg: String?, sev: String = "info") = _state.update { it.copy(status = msg, statusSeverity = sev) }

    // ------------------------------------------------------------------------------------ preflight
    /** 3-second monitored audio check (J1 step 6). Uses the mic only after the user tapped "Check audio". */
    suspend fun preflight(): PreflightReport = withContext(Dispatchers.IO) {
        val route = routes.route.value
        val warnings = mutableListOf<String>()
        if (!micGranted()) return@withContext PreflightReport(false, null, null, route, listOf(str(R.string.truth_mic_denied)))
        var peak = -120.0
        var gotFrames = false
        val probe = AudioCapture(onFirstBuffer = { gotFrames = true }, onChunk = { _, _, _, _ -> }, onLevel = { peak = maxOf(peak, it) },
            onFailure = { warnings += str(R.string.preflight_mic_busy) })
        if (probe.start()) {
            Thread.sleep(3000)
            probe.stop()
        }
        if (!gotFrames) warnings += str(R.string.preflight_no_frames)
        val q = if (gotFrames) Signal.quality(peak) else null
        if (q == "POOR" || q == "SILENT_OR_BLOCKED") warnings += str(R.string.preflight_poor)
        if (route.couplesInputAndOutput) warnings += str(R.string.preflight_headset_mic)
        warnings += str(R.string.preflight_laptop_headphones)
        PreflightReport(true, if (gotFrames) peak else null, q, route, warnings)
    }

    fun capabilities(report: PreflightReport?): Capabilities {
        val r = routes.route.value
        return Capabilities(
            micPermission = if (micGranted()) "granted" else "denied",
            inputRoute = if (micGranted()) r.input else null,
            outputRoute = r.output, outputDeviceName = r.outputDeviceName,
            privateRouteVerified = routes.privateRouteVerified(),
            measuredLevelDbfs = report?.levelDbfs,
        )
    }

    fun capabilitiesHash(c: Capabilities): String =
        MessageDigest.getInstance("SHA-256").digest(WireJson.encodeToString(Capabilities.serializer(), c).toByteArray())
            .joinToString("") { "%02x".format(it) }.take(32)

    // ------------------------------------------------------------------------------------ lifecycle
    fun attach(session: SessionView) {
        locallyEnded = PendingStop.load(File(context.noBackupFilesDir, "spool/${session.sessionId}")) != null
        _state.value = LiveUiState(session = session, route = routes.route.value, privateRouteVerified = routes.privateRouteVerified())
        refreshTruth()
        connectRealtime(session)
        startTicker()
    }

    private fun connectRealtime(session: SessionView) {
        realtime?.stop()
        realtime = RealtimeClient(api, scope, session.sessionId, session.eventCursor).also { rt ->
            rt.start()
            scope.launch { rt.events.collect { onEvent(it) } }
            scope.launch { rt.connected.collect { c -> _state.update { it.copy(realtimeConnected = c, captionPreview = if (c) it.captionPreview else null) } } }
        }
    }

    /** Called after POST /start succeeded. Capture begins only now, from the visible activity. */
    fun beginCapture(session: SessionView, ingest: IngestCredential) {
        attach(session)
        val dir = File(context.noBackupFilesDir, "spool/${session.sessionId}")
        val sp = ChunkSpool(dir, AesGcmSealer { KeystoreKeys.key("ms_spool_v1") }, session.sessionId)
        spool = sp
        nextSeq = File(dir, "next_seq").takeIf { it.exists() }?.readText()?.toLongOrNull() ?: ingest.resumeCursor
        // Monotonic session clock: continues from the server's audio watermark, and keeps running while paused
        // so a pause appears as a visible gap rather than overlapping audio (master 7.1 timestamp consistency).
        originElapsed = SystemClock.elapsedRealtime() - session.sourceWatermarkMs
        startUploader(session.sessionId, ingest.token)
        ensureVoice()
        CaptureService.start(context)
    }

    private fun clock() = SystemClock.elapsedRealtime() - originElapsed

    /** Session-clock position for a user note, only while this device is capturing (otherwise the note has no moment). */
    fun noteAtMs(): Long? = if (capture != null && !locallyEnded) clock() else null

    fun resetForSignOut(purgeLocal: Boolean = false) {
        stopCaptureLocally()
        locallyEnded = true
        uploader?.stop(); uploader = null
        realtime?.stop(); realtime = null
        voice?.shutdown(); voice = null
        scope.coroutineContext.cancelChildren()
        if (purgeLocal) File(context.noBackupFilesDir, "spool").deleteRecursively()
        spool = null
        _state.value = LiveUiState(route = routes.route.value)
    }

    private fun startUploader(sessionId: String, token: String?) {
        val sp = spool ?: return
        uploader?.stop()
        uploader = Uploader(sp, OkHttpChunkTransport(api.baseUrl, api.http), sessionId, api.deviceId()) { _ ->
            runCatching {
                api.call("POST", "/v1/sessions/$sessionId/ingest-token", null, IngestCredential.serializer())!!.token
            }.getOrNull()
        }.also { up ->
            up.start(scope, token)
            scope.launch {
                up.status.collect { st ->
                    _state.update { it.copy(online = st.online, pendingUploads = st.pending) }
                    refreshTruth()
                    if (st.stoppedReason == "DEVICE_REVOKED") {
                        stopCaptureLocally(); setStatus(str(R.string.status_device_revoked), "error")
                    }
                }
            }
        }
    }

    /** CaptureService is in the foreground: start AudioRecord now. */
    fun onServiceForeground() {
        if (capture != null) return
        if (!micGranted()) { onCaptureFailure("PERMISSION_REVOKED"); return }
        val sp = spool ?: return
        val dir = File(context.noBackupFilesDir, "spool/${_state.value.session?.sessionId}")
        val cap = AudioCapture(
            onFirstBuffer = { scope.launch { buffersFlowing = true; refreshTruth(); confirmRecording() } },
            onChunk = { start, dur, pcm, level ->
                val seq = nextSeq
                when (sp.append(seq, start, dur, 16_000, pcm)) {
                    ChunkSpool.AppendResult.Stored -> { nextSeq = seq + 1; File(dir, "next_seq").writeText(nextSeq.toString()) }
                    ChunkSpool.AppendResult.StorageFull -> scope.launch {
                        setStatus(str(R.string.status_storage_full), "error")
                        end()
                    }
                }
                onSpeechLevel(level)
            },
            onLevel = { l -> _state.update { it.copy(levelDbfs = l) } },
            onFailure = { reason -> scope.launch { onCaptureFailure(reason) } },
        )
        cap.sessionClockOriginElapsed = originElapsed
        capture = cap
        if (!cap.start()) capture = null
    }

    private fun onSpeechLevel(level: Double) {
        val now = SystemClock.elapsedRealtime()
        if (level > -38) {
            lastSpeech = now
            voice?.let { if (it.isSpeaking) it.onSpeechDetected() }
        }
        val speaking = now - lastSpeech < 1500
        if (speaking != speakingSignalled) {
            speakingSignalled = speaking
            realtime?.signalUserSpeaking(speaking)
        }
    }

    private suspend fun confirmRecording() {
        val s = _state.value.session ?: return
        runCatching {
            val v = api.call("POST", "/v1/sessions/${s.sessionId}/capture-state",
                buildJsonObject { put("state", "RECORDING"); put("reason", "AUDIO_CALLBACK_CONFIRMED") }.toString(), SessionView.serializer())!!
            _state.update { it.copy(session = v) }
            refreshTruth()
        }
    }

    fun onCaptureFailure(reason: String) {
        val s = _state.value.session ?: return
        stopCaptureLocally()
        val last = nextSeq - 1
        setStatus(str(R.string.status_capture_interrupted, formatClock(clock())), "error")
        scope.launch {
            runCatching {
                val v = api.call("POST", "/v1/sessions/${s.sessionId}/capture-state", buildJsonObject {
                    put("state", "INTERRUPTED"); put("reason", reason); put("at_ms", clock()); put("last_sequence", last)
                }.toString(), SessionView.serializer())!!
                _state.update { it.copy(session = v) }
            }
            refreshTruth()
        }
    }

    fun onServiceDestroyed() {
        if (capture != null) onCaptureFailure("PROCESS_RESTORED")
    }

    private fun stopCaptureLocally() {
        capture?.stop()
        capture = null
        buffersFlowing = false
        CaptureService.stop(context)
        voice?.hardMute()
        refreshTruth()
    }

    suspend fun pause() {
        val s = _state.value.session ?: return
        stopCaptureLocally() // microphone released BEFORE the network call (no frames while paused)
        val v = api.call("POST", "/v1/sessions/${s.sessionId}/pause", buildJsonObject {
            put("stop_watermark_sequence", nextSeq - 1); put("at_ms", clock())
        }.toString(), SessionView.serializer(), idempotent = true)!!
        _state.update { it.copy(session = v) }
        v.ingest?.let { ing -> runCatching { WireJson.decodeFromJsonElement(IngestCredential.serializer(), ing) }.getOrNull()?.let { startUploader(v.sessionId, it.token) } }
        refreshTruth()
    }

    suspend fun resume(report: PreflightReport?) {
        val s = _state.value.session ?: return
        val caps = capabilities(report)
        val body = buildJsonObject {
            put("capabilities_hash", capabilitiesHash(caps)); put("capabilities", WireJson.encodeToJsonElement(Capabilities.serializer(), caps)); put("at_ms", clock())
        }
        val v = api.call("POST", "/v1/sessions/${s.sessionId}/resume", body.toString(), SessionView.serializer(), idempotent = true)!!
        val ing = WireJson.decodeFromJsonElement(IngestCredential.serializer(), v.ingest!!)
        _state.update { it.copy(session = v) }
        startUploader(v.sessionId, ing.token)
        CaptureService.start(context)
    }

    /** End: microphone stops at once; finalization continues separately (ADR-010). Works offline. */
    suspend fun end() {
        val s = _state.value.session ?: return
        stopCaptureLocally()
        locallyEnded = true
        _state.update { it.copy(truth = CaptureTruth.STOPPED, finalizationMessage = str(R.string.status_ended)) }
        val dir = File(context.noBackupFilesDir, "spool/${s.sessionId}")
        val body = PendingStop.load(dir) ?: PendingStop(nextSeq - 1, clock())
        try { withContext(Dispatchers.IO) { body.save(dir) } }
        catch (_: Exception) { setStatus(str(R.string.status_stop_not_saved), "error"); return }
        syncStop(s.sessionId, body)
    }

    /**
     * A participant objected (CON-013): the microphone stops and uploads halt first, then the server records the
     * withdrawal, revokes ingest and stops the session. Audio not yet uploaded is never sent afterwards, so the
     * local spool for this session is purged. Offline, the withdrawal stays pending and is retried; nothing uploads.
     */
    suspend fun withdrawConsent(): Boolean {
        val s = _state.value.session ?: return false
        stopCaptureLocally()
        locallyEnded = true
        uploader?.stop(); uploader = null
        _state.update { it.copy(truth = CaptureTruth.STOPPED, withdrawPending = true) }
        val dir = File(context.noBackupFilesDir, "spool/${s.sessionId}")
        // Durable marker: after process death, recovery retries the withdrawal and never uploads this spool.
        runCatching { withContext(Dispatchers.IO) { dir.mkdirs(); File(dir, WITHDRAW_MARKER).writeText("1") } }
        return try {
            val v = api.call("POST", "/v1/sessions/${s.sessionId}/consent/withdraw", buildJsonObject { put("reason", "PARTICIPANT_WITHDREW") }.toString(),
                SessionView.serializer(), idempotent = true, idempotencyKey = "withdraw-${s.sessionId}")!!
            withContext(Dispatchers.IO) { dir.deleteRecursively() }
            spool = null
            _state.update { it.copy(session = v, withdrawPending = false, finalizationMessage = str(R.string.status_consent_withdrawn)) }
            setStatus(null)
            true
        } catch (e: Exception) {
            setStatus(str(R.string.status_withdraw_pending), "error")
            false
        }
    }

    private suspend fun syncStop(sessionId: String, body: PendingStop) {
        if (stopInFlight) return
        stopInFlight = true
        try {
        runCatching { api.call("POST", "/v1/sessions/$sessionId/stop", body.body(), SessionView.serializer(),
            idempotent = true, idempotencyKey = "end-$sessionId")!! }
            .onSuccess { v ->
                PendingStop.clear(File(context.noBackupFilesDir, "spool/$sessionId"))
                _state.update { it.copy(session = v) }
                v.ingest?.let { ing -> runCatching { WireJson.decodeFromJsonElement(IngestCredential.serializer(), ing) }.getOrNull()?.let { startUploader(v.sessionId, it.token) } }
            }
            .onFailure { setStatus(str(if (it is OfflineException) R.string.status_stop_offline else R.string.status_stop_retrying), "warning") }
        } finally { stopInFlight = false }
    }

    fun endFromNotification() { scope.launch { end() } }

    suspend fun setControls(body: JsonObject) {
        val s = _state.value.session ?: return
        val v = api.call("PATCH", "/v1/sessions/${s.sessionId}/controls", body.toString(), SessionView.serializer())!!
        _state.update { it.copy(session = v, insight = if (v.mutedUntil != null) null else it.insight) }
    }

    fun verifyPrivateRoute(): Boolean {
        val r = routes.route.value
        if (!r.privateOutputPresent) return false
        val v = ensureVoice()
        return v.playTestSample(r.outputDeviceName)
    }

    private fun ensureVoice(): PrivateVoice = voice ?: PrivateVoice(context, routes,
        onPlayback = { start, end -> _state.value.session?.sessionId?.let { reportPlayback(it, start, end) } },
        clockMs = { clock() }).also { voice = it }

    fun confirmHeardPrivateSample() {
        routes.confirmPrivateRoute()
        _state.update { it.copy(privateRouteVerified = routes.privateRouteVerified()) }
        _state.value.session?.let { s -> scope.launch { runCatching { postRoute(s.sessionId) } } }
    }

    private suspend fun postRoute(sessionId: String) {
        val r = routes.route.value
        api.raw("POST", "/v1/sessions/$sessionId/route", buildJsonObject {
            put("input_route", r.input); put("output_route", r.output); put("private_route_verified", routes.privateRouteVerified())
            r.outputDeviceName?.let { put("device_name", it) }
            put("audio_quality", Signal.quality(_state.value.levelDbfs))
        })
    }

    private fun reportPlayback(sessionId: String, startMs: Long, endMs: Long) {
        if (endMs <= startMs) return
        scope.launch { runCatching { api.raw("POST", "/v1/sessions/$sessionId/voice/playback-window", buildJsonObject { put("start_ms", startMs); put("end_ms", endMs) }) } }
    }

    suspend fun saveMoment(text: String = ""): Boolean {
        val s = _state.value.session ?: return false
        val note = NoteIn("BOOKMARK", text, clientId = UUID.randomUUID().toString(), atMs = clock(), windowMs = 30_000)
        return runCatching { api.post("/v1/sessions/${s.sessionId}/notes", note, JsonObject.serializer(), idempotent = false); true }.getOrDefault(false)
    }

    suspend fun feedback(insightId: String, value: String) {
        val s = _state.value.session ?: return
        api.raw("POST", "/v1/sessions/${s.sessionId}/insights/$insightId/feedback", buildJsonObject { put("value", value) }, idempotent = true)
        _state.update { it.copy(insight = null) }
    }

    fun detach() {
        ticker?.cancel()
        realtime?.stop(); realtime = null
        if (capture == null) uploader?.stop()
    }

    private fun startTicker() {
        ticker?.cancel()
        ticker = scope.launch {
            var ticks = 0
            while (true) {
                if (ticks % 5 == 0 && _state.value.withdrawPending) withdrawConsent()
                if (ticks++ % 5 == 0 && !stopInFlight && !_state.value.withdrawPending) {
                    _state.value.session?.sessionId?.let { sid ->
                        PendingStop.load(File(context.noBackupFilesDir, "spool/$sid"))?.let { syncStop(sid, it) }
                    }
                }
                if (truthIsLive()) _state.update { it.copy(elapsedMs = clock()) }
                if (_state.value.captionPreview?.expired() == true) _state.update { it.copy(captionPreview = null) }
                val ins = _state.value.insight
                if (ins != null && runCatching { java.time.Instant.parse(ins.expiresAt).isBefore(java.time.Instant.now()) }.getOrDefault(false)) {
                    _state.update { it.copy(insight = null) }
                }
                kotlinx.coroutines.delay(1000)
            }
        }
    }

    private fun refreshTruth() {
        val s = _state.value.session ?: return
        if (locallyEnded) { _state.update { it.copy(truth = CaptureTruth.STOPPED) }; return }
        val truth = captureTruth(SessionState.parse(s.state), buffersFlowing && capture != null, _state.value.online, micGranted() || s.captureSource == "NONE")
        _state.update { it.copy(truth = truth) }
    }

    // ------------------------------------------------------------------------------------ events
    private fun onEvent(e: EventEnvelope) {
        if (e.sessionId != null && e.sessionId != _state.value.session?.sessionId) return
        val p = e.payload
        when (e.type) {
            "session.state_changed" -> {
                val cur = p["current"]?.jsonPrimitive?.contentOrNull ?: return
                _state.update { st -> st.copy(session = st.session?.copy(state = cur)) }
                refreshTruth()
            }
            "session.status" -> setStatus(p["message"]?.jsonPrimitive?.contentOrNull, p["severity"]?.jsonPrimitive?.contentOrNull ?: "info")
            "session.finalization_progress" -> _state.update { it.copy(finalizationMessage = p["message"]?.jsonPrimitive?.contentOrNull) }
            "transcript.preview" -> {
                val run = p["run_id"]?.jsonPrimitive?.contentOrNull ?: return
                val id = p["preview_id"]?.jsonPrimitive?.contentOrNull ?: return
                val text = p["text"]?.jsonPrimitive?.contentOrNull ?: return
                _state.update { it.copy(captionPreview = CaptionPreview(run, id, text, p["start_ms"]?.jsonPrimitive?.longOrNull ?: 0)) }
            }
            "transcript.preview_clear" -> {
                val run = p["run_id"]?.jsonPrimitive?.contentOrNull
                val id = p["preview_id"]?.jsonPrimitive?.contentOrNull
                _state.update { it.copy(captionPreview = it.captionPreview?.takeUnless { draft -> draft.clearedBy(run, id) }) }
            }
            "transcript.partial", "transcript.final" -> {
                val id = p["utterance_id"]?.jsonPrimitive?.contentOrNull ?: return
                val u = Utterance(id, p["revision"]?.jsonPrimitive?.longOrNull?.toInt() ?: 1, p["start_ms"]?.jsonPrimitive?.longOrNull ?: 0,
                    p["end_ms"]?.jsonPrimitive?.longOrNull ?: 0, p["text"]?.jsonPrimitive?.contentOrNull ?: "",
                    p["is_final"]?.jsonPrimitive?.booleanOrNull ?: false, p["speaker_alias"]?.jsonPrimitive?.contentOrNull,
                    speakerDisplay = speakerDisplay(p), speakerVerified = p["speaker_verified"]?.jsonPrimitive?.booleanOrNull ?: false,
                    uncertain = (p["overlap"]?.jsonPrimitive?.booleanOrNull ?: false) || (p["low_confidence"]?.jsonPrimitive?.booleanOrNull ?: false),
                    label = if (p["is_final"]?.jsonPrimitive?.booleanOrNull == true) "Final" else "Provisional")
                _state.update { st -> st.copy(transcript = (st.transcript.filter { it.utteranceId != id } + u).sortedBy { it.startMs }.takeLast(200)) }
            }
            "insight.delivered" -> {
                val ins = runCatching { WireJson.decodeFromJsonElement(Insight.serializer(), p) }.getOrNull() ?: return
                _state.update { it.copy(insight = ins) }
                if ((ins.outputChannel == "PRIVATE_VOICE" || ins.outputChannel == "BOTH") && ins.voiceText != null) {
                    voice?.speak(ins.voiceText, ins.voiceMaxSeconds) // speaks only on a verified private route
                }
            }
            "insight.expired" -> {
                val id = p["insight_id"]?.jsonPrimitive?.contentOrNull
                _state.update { if (it.insight?.insightId == id) it.copy(insight = null) else it }
            }
            "voice.route_lost" -> { voice?.hardMute(); setStatus(str(R.string.status_voice_disconnected), "warning") }
            "memory.invalidated" -> {
                val ids = (p["claim_ids"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
                _state.update { it.copy(invalidatedClaims = it.invalidatedClaims + ids) }
            }
        }
    }

    private fun speakerDisplay(p: JsonObject): String {
        val alias = p["speaker_alias"]?.jsonPrimitive?.contentOrNull ?: return "Unassigned speaker"
        val verified = p["speaker_verified"]?.jsonPrimitive?.booleanOrNull ?: false
        return if (verified || alias == "Unassigned") alias.replace("Unassigned", "Unassigned speaker") else "$alias (unconfirmed)"
    }

    /** UNI-004: after process death, upload only already-permitted, unacknowledged chunks; never restart the mic. */
    fun recoverSpools() {
        if (recoveryJob?.isActive == true) return
        recoveryJob = scope.launch {
            while (isActive) {
                recoverSpoolsOnce()
                kotlinx.coroutines.delay(10_000)
            }
        }
    }

    private suspend fun recoverSpoolsOnce() = coroutineScope {
        val root = File(context.noBackupFilesDir, "spool")
        root.listFiles()?.forEach { dir ->
            val sid = dir.name
            if (_state.value.session?.sessionId == sid) return@forEach
            launch {
                var v = try { api.get("/v1/sessions/$sid", SessionView.serializer()) }
                catch (e: ApiException) { if (e.status == 404 || e.status == 410) dir.deleteRecursively(); return@launch }
                catch (_: Exception) { return@launch } // temporary failures never authorize audio deletion
                if (_state.value.session?.sessionId == sid) return@launch
                if (File(dir, WITHDRAW_MARKER).exists()) {
                    runCatching {
                        api.call("POST", "/v1/sessions/$sid/consent/withdraw", buildJsonObject { put("reason", "PARTICIPANT_WITHDREW") }.toString(),
                            SessionView.serializer(), idempotent = true, idempotencyKey = "withdraw-$sid")
                    }.onSuccess { dir.deleteRecursively() }
                    return@launch
                }
                PendingStop.load(dir)?.let { pending ->
                    v = try { api.call("POST", "/v1/sessions/$sid/stop", pending.body(), SessionView.serializer(),
                        idempotent = true, idempotencyKey = "end-$sid")!! }
                    catch (_: Exception) { return@launch }
                    PendingStop.clear(dir)
                }
                val st = SessionState.parse(v.state)
                if (st == SessionState.RECORDING || st == SessionState.STARTING) {
                    // Capture was live when the process died: record the truth (interrupted) instead of silently resuming.
                    runCatching {
                        api.call("POST", "/v1/sessions/$sid/capture-state", buildJsonObject {
                            put("state", "INTERRUPTED"); put("reason", "PROCESS_RESTORED")
                            put("last_sequence", (File(dir, "next_seq").takeIf { it.exists() }?.readText()?.toLongOrNull() ?: 0L) - 1)
                        }.toString(), SessionView.serializer())
                    }
                }
                val sp = ChunkSpool(dir, AesGcmSealer { KeystoreKeys.key("ms_spool_v1") }, sid)
                if (sp.pendingSequences().isEmpty()) { if (st in SessionStateMachine.ended) dir.deleteRecursively(); return@launch }
                val up = Uploader(sp, OkHttpChunkTransport(api.baseUrl, api.http), sid, api.deviceId()) { _ ->
                    runCatching { api.call("POST", "/v1/sessions/$sid/ingest-token", null, IngestCredential.serializer())!!.token }.getOrNull()
                }
                withContext(Dispatchers.IO) { repeat(20) { if (sp.pendingSequences().isNotEmpty()) up.pass() } }
                if (sp.pendingSequences().isEmpty() && st in SessionStateMachine.ended) dir.deleteRecursively()
            }
        }
    }

    companion object {
        const val WITHDRAW_MARKER = "withdraw_pending"

        fun formatClock(ms: Long): String {
            val s = ms / 1000
            return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, (s % 3600) / 60, s % 60) else "%02d:%02d".format(s / 60, s % 60)
        }
    }
}
