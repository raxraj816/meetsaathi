package app.meetsaathi.ui

import android.net.Uri
import android.os.Build
import androidx.annotation.StringRes
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import app.meetsaathi.AppContainer
import app.meetsaathi.R
import app.meetsaathi.core.ApiException
import app.meetsaathi.core.AskIn
import app.meetsaathi.core.AskResponse
import app.meetsaathi.core.ConsentIn
import app.meetsaathi.core.ConsentResult
import app.meetsaathi.core.CreateSessionIn
import app.meetsaathi.core.IngestCredential
import app.meetsaathi.core.Me
import app.meetsaathi.core.NoteIn
import app.meetsaathi.core.OfflineException
import app.meetsaathi.core.Page
import app.meetsaathi.core.PreflightReport
import app.meetsaathi.core.SessionState
import app.meetsaathi.core.SessionStateMachine
import app.meetsaathi.core.SessionSummary
import app.meetsaathi.core.SessionView
import app.meetsaathi.core.StartIn
import app.meetsaathi.core.Utterance
import app.meetsaathi.core.WireJson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.net.URLEncoder
import java.util.UUID

sealed interface Route {
    data object Welcome : Route
    data object Auth : Route
    data object Sample : Route
    data object Home : Route
    data object ContextChooser : Route
    data object Preflight : Route
    data object Live : Route
    data object LiveAsk : Route
    data class Transcript(val sessionId: String) : Route
    data object Voice : Route
    data class Recap(val sessionId: String) : Route
    data class Speakers(val sessionId: String) : Route
    data class MemoryDetail(val claimId: String) : Route
    data class InsightDetail(val sessionId: String, val insightId: String) : Route
    data class Insights(val sessionId: String) : Route
    data class Share(val sessionId: String) : Route
    data object Sessions : Route
    data object Projects : Route
    data class Project(val projectId: String) : Route
    data object Memories : Route
    data object Ask : Route
    data object You : Route
    data object Study : Route
    data object Interview : Route
    data class Mock(val mockId: String) : Route
}

enum class Tab(@StringRes val label: Int, val route: Route) {
    Home(R.string.tab_home, Route.Home), Memories(R.string.tab_memories, Route.Memories), Ask(R.string.tab_ask, Route.Ask), You(R.string.tab_you, Route.You)
}

/** Session setup draft. Each control dimension is independent (ADR-003). Defaults: Listener + Text (ADR-004). */
data class Draft(
    val context: String = "MEETING",
    val preset: String? = null,
    val title: String = "",
    val captureSource: String = "PHONE_MIC",
    val participantsInformed: Boolean = false,
    val recordingAllowed: Boolean? = null, // Interview: "May this be recorded?"
    val aiAllowed: Boolean? = null,        // Interview: "Is AI permitted?" (unknown = no)
    val aiConsent: Boolean = false,
    val assistance: String = "LISTENER",
    val intensity: String = "QUIET",
    val output: String = "TEXT",
    val sensitiveOptIn: Boolean = false,
    val spaceId: String? = null,
    val projectId: String? = null,
)

/** A start-gate the UI must show (resource id), evaluated client-side for honest UI; the server re-checks all. */
enum class Blocker(@StringRes val text: Int) {
    MIC(R.string.blocker_mic), INTERVIEW_RECORDING(R.string.blocker_interview_recording), NOTICE(R.string.blocker_notice),
    INTERVIEW_AI(R.string.blocker_interview_ai), AI_CONSENT(R.string.blocker_ai_consent), PRIVATE_ROUTE(R.string.blocker_private_route),
    AUDIO_CHECK(R.string.blocker_audio_check),
}

data class ExportState(val exportId: String, val status: String, val scope: String)

data class UiState(
    val route: Route = Route.Welcome,
    val back: List<Route> = emptyList(),
    val me: Me? = null,
    val recent: List<SessionSummary> = emptyList(),
    val active: List<SessionSummary> = emptyList(),
    val draft: Draft = Draft(),
    val preflight: PreflightReport? = null,
    val preflightRunning: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    val askResult: AskResponse? = null,
    val recap: JsonObject? = null,
    val speakers: JsonArray? = null,
    val memories: JsonArray? = null,
    val matchingSessions: JsonArray? = null,
    val memorySpace: String? = null,
    val transcript: List<Utterance> = emptyList(),
    val study: JsonObject? = null,
    val lastAttempt: JsonObject? = null,
    val reviews: JsonArray? = null,
    val mock: JsonObject? = null,
    val mocks: JsonArray? = null,
    val goals: JsonArray? = null,
    val toast: String? = null,
    val devices: JsonArray? = null,
    val projects: JsonArray? = null,
    val claim: JsonObject? = null,
    val insightDetail: JsonObject? = null,
    val insights: JsonArray? = null,
    val sharePreview: JsonObject? = null,
    val shareLink: JsonObject? = null,
    val shares: JsonArray? = null,
    val project: JsonObject? = null,
    val brief: JsonObject? = null,
    val decisions: JsonArray? = null,
    val sessions: List<SessionSummary> = emptyList(),
    val sessionsCursor: String? = null,
    val sessionsLoaded: Boolean = false,
    val export: ExportState? = null,
)

class AppViewModel(private val c: AppContainer) : ViewModel() {
    private val _ui = MutableStateFlow(UiState(route = if (c.api.isSignedIn) Route.Home else Route.Welcome))
    val ui: StateFlow<UiState> = _ui
    val live = c.live
    val evidence = c.evidence

    init {
        c.api.onSignedOut = { viewModelScope.launch { live.resetForSignOut(); evidence.stop(); _ui.value = UiState(route = Route.Welcome) } }
        if (c.api.isSignedIn) refreshHome()
    }

    private fun str(@StringRes id: Int, vararg args: Any): String = c.app.getString(id, *args)

    // ---------------------------------------------------------------- navigation
    fun go(r: Route) {
        evidence.stop() // leaving a screen never leaves a clip playing
        _ui.update { it.copy(route = r, back = it.back + it.route, error = null) }
    }
    fun tab(t: Tab) { evidence.stop(); _ui.update { it.copy(route = t.route, back = emptyList(), error = null) } }
    fun back(): Boolean {
        val b = _ui.value.back
        if (b.isEmpty()) return false
        evidence.stop()
        _ui.update { it.copy(route = b.last(), back = b.dropLast(1), error = null) }
        return true
    }
    fun toast(msg: String?) = _ui.update { it.copy(toast = msg) }
    fun clearError() = _ui.update { it.copy(error = null) }

    private fun launchSafe(block: suspend () -> Unit) = viewModelScope.launch {
        _ui.update { it.copy(busy = true, error = null) }
        try {
            block()
        } catch (e: ApiException) {
            _ui.update { it.copy(error = e.error.userMessage.ifBlank { str(R.string.error_generic) }) }
        } catch (e: OfflineException) {
            _ui.update { it.copy(error = str(R.string.error_offline)) }
        } finally {
            _ui.update { it.copy(busy = false) }
        }
    }

    private fun deviceName() = "${Build.MANUFACTURER} ${Build.MODEL}".take(80)

    // ---------------------------------------------------------------- auth
    fun signIn(email: String, password: String, create: Boolean, name: String?, ageConfirmed: Boolean = false) = launchSafe {
        if (create) c.api.register(email.trim(), password, name?.takeIf { it.isNotBlank() }, deviceName(), ageConfirmed)
        else c.api.login(email.trim(), password, deviceName())
        live.recoverSpools()
        _ui.update { it.copy(route = Route.Home, back = emptyList()) }
        refreshHomeNow()
    }

    fun signOut() = launchSafe {
        val session = live.state.value.session
        if (session != null && SessionState.parse(session.state) in SessionStateMachine.active) live.end()
        live.resetForSignOut()
        evidence.stop()
        c.api.logout(); _ui.value = UiState(route = Route.Welcome)
    }

    fun refreshHome() = launchSafe { refreshHomeNow() }

    private suspend fun refreshHomeNow() {
        val me = c.api.get("/v1/me", Me.serializer())
        val recent = c.api.get("/v1/sessions?limit=6", Page.serializer(SessionSummary.serializer())).items
        val active = c.api.get("/v1/sessions?active=true&limit=3", Page.serializer(SessionSummary.serializer())).items
        _ui.update { it.copy(me = me, recent = recent, active = active) }
    }

    // ---------------------------------------------------------------- preferences (U13)
    fun pref(key: String): String? = (_ui.value.me?.preferences?.get(key) as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
    fun prefBool(key: String): Boolean = pref(key) == "true"
    private fun intensityPref(ctx: String): String? =
        ((_ui.value.me?.preferences?.get("default_intensity_by_context") as? JsonObject)?.get(ctx) as? JsonPrimitive)?.content

    fun savePrefs(values: Map<String, JsonElement>, silent: Boolean = false) = launchSafe {
        val r = c.api.raw("PUT", "/v1/me/preferences", buildJsonObject { put("prefs", JsonObject(values)) }, idempotent = true)!!
        val prefs = r["prefs"] as? JsonObject ?: return@launchSafe
        _ui.update { st -> st.copy(me = st.me?.copy(preferences = prefs)) }
        if (!silent) toast(str(R.string.prefs_saved))
    }

    fun setDefaultIntensity(ctx: String, intensity: String) {
        val cur = (_ui.value.me?.preferences?.get("default_intensity_by_context") as? JsonObject)?.toMutableMap() ?: mutableMapOf()
        cur[ctx] = JsonPrimitive(intensity)
        savePrefs(mapOf("default_intensity_by_context" to JsonObject(cur)))
    }

    // ---------------------------------------------------------------- start flow (U03 -> U04 -> U05)
    fun chooseContext(ctx: String, preset: String?) {
        val current = live.state.value.session
        if (current != null && SessionState.parse(current.state) in SessionStateMachine.active) {
            toast(str(R.string.toast_end_current_first))
            go(Route.Live)
            return
        }
        val me = _ui.value.me
        val kind = when (ctx) { "LEARNING" -> "LEARNING"; "CONVERSATION" -> "PERSONAL"; else -> "WORK" }
        val space = me?.spaces?.firstOrNull { it.kind == kind }?.spaceId ?: me?.spaces?.firstOrNull()?.spaceId
        // Saved defaults pre-fill choices only. Every permission (AI consent, interview rules, private route) is still asked per session.
        val assistance = if (ctx == "INTERVIEW") "LISTENER" else pref("default_assistance") ?: "LISTENER"
        val intensity = intensityPref(ctx) ?: if (assistance == "COMPANION") "BALANCED" else "QUIET"
        _ui.update { it.copy(draft = Draft(context = ctx, preset = preset, spaceId = space,
            captureSource = if (ctx == "CONVERSATION") "NONE" else "PHONE_MIC", assistance = assistance, intensity = intensity,
            output = pref("default_output") ?: "TEXT"), preflight = null) }
        if (pref("last_context") != ctx) savePrefs(mapOf("last_context" to JsonPrimitive(ctx)), silent = true)
        loadProjects()
        go(Route.Preflight)
    }

    fun updateDraft(f: (Draft) -> Draft) = _ui.update { it.copy(draft = f(it.draft)) }

    fun runPreflight() = viewModelScope.launch {
        _ui.update { it.copy(preflightRunning = true) }
        val r = live.preflight()
        _ui.update { it.copy(preflight = r, preflightRunning = false) }
    }

    fun startBlockers(d: Draft, micGranted: Boolean): List<Blocker> {
        val out = mutableListOf<Blocker>()
        if (d.captureSource == "NONE") return out
        if (!micGranted) out += Blocker.MIC
        if (d.context == "INTERVIEW" && d.recordingAllowed != true) out += Blocker.INTERVIEW_RECORDING
        if (!d.participantsInformed) out += Blocker.NOTICE
        if (d.context == "INTERVIEW" && d.aiAllowed != true && d.assistance != "LISTENER") out += Blocker.INTERVIEW_AI
        if (d.context != "INTERVIEW" && !d.aiConsent && d.assistance != "LISTENER") out += Blocker.AI_CONSENT
        if (d.output != "TEXT" && !live.routes.privateRouteVerified()) out += Blocker.PRIVATE_ROUTE
        if (_ui.value.preflight == null) out += Blocker.AUDIO_CHECK
        return out
    }

    fun startSession() = launchSafe {
        val d = _ui.value.draft
        val me = _ui.value.me ?: c.api.get("/v1/me", Me.serializer())
        val region = (me.tenant["residency_region"] as? JsonPrimitive)?.content ?: "ap-south-1"
        val interviewMode = if (d.context == "INTERVIEW") (if (d.captureSource == "NONE") "REFLECTION" else "LIVE") else null
        val created = c.api.post("/v1/sessions", CreateSessionIn(d.spaceId!!, d.context, d.title.ifBlank { null }, d.captureSource, region,
            d.preset, d.projectId, interviewMode), SessionView.serializer())
        if (d.captureSource == "NONE") {
            live.attach(created)
            _ui.update { it.copy(route = Route.Live, back = listOf(Route.Home)) }
            return@launchSafe
        }
        val receipt = c.api.post("/v1/sessions/${created.sessionId}/consent-receipts", ConsentIn(
            captureBasis = if (d.participantsInformed) "PARTICIPANTS_INFORMED" else "UNKNOWN",
            noticesAttested = d.participantsInformed,
            aiAssistancePermitted = if (d.context == "INTERVIEW") d.aiAllowed == true else d.aiConsent,
            disclosureVersion = me.disclosureVersion), ConsentResult.serializer())
        if (!receipt.capturePermitted) {
            _ui.update { it.copy(error = str(R.string.error_recording_not_authorized)) }
            return@launchSafe
        }
        val caps = live.capabilities(_ui.value.preflight)
        val started = c.api.post("/v1/sessions/${created.sessionId}/start", StartIn(receipt.receiptId, live.capabilitiesHash(caps), caps,
            d.assistance, if (d.assistance == "COMPANION") d.intensity else "QUIET", d.output, d.sensitiveOptIn), SessionView.serializer())
        val ingest = WireJson.decodeFromJsonElement(IngestCredential.serializer(), started.ingest!!)
        live.beginCapture(started, ingest)
        _ui.update { it.copy(route = Route.Live, back = listOf(Route.Home)) }
    }

    fun openActive(sessionId: String) = launchSafe {
        val v = c.api.get("/v1/sessions/$sessionId", SessionView.serializer())
        live.attach(v)
        go(Route.Live)
    }

    // ---------------------------------------------------------------- live actions
    fun pause() = launchSafe { live.pause() }
    fun resume() = launchSafe { live.resume(live.preflight()) }
    fun end() = launchSafe {
        val sid = live.state.value.session?.sessionId
        live.end()
        if (sid != null) _ui.update { it.copy(route = Route.Recap(sid), back = listOf(Route.Home), recap = null) }
        loadRecapNow(sid ?: return@launchSafe)
    }

    /** CC-014: capture stops first (same as End); the user stays on Live to keep writing their own notes. */
    fun stopKeepNotes() = launchSafe { live.end() }

    fun finishToRecap() {
        val sid = live.state.value.session?.sessionId ?: return
        _ui.update { it.copy(route = Route.Recap(sid), back = listOf(Route.Home), recap = null, askResult = null) }
        loadRecap(sid)
    }

    /** Someone objected to recording: stop now, record the withdrawal, never upload the rest (CON-013). */
    fun withdrawConsent() = launchSafe {
        val sid = live.state.value.session?.sessionId ?: return@launchSafe
        if (live.withdrawConsent()) {
            toast(str(R.string.toast_consent_withdrawn))
            _ui.update { it.copy(route = Route.Recap(sid), back = listOf(Route.Home), recap = null) }
            loadRecapNow(sid)
        }
    }

    fun switchContext(ctx: String) = launchSafe {
        val sid = live.state.value.session?.sessionId ?: return@launchSafe
        val v = c.api.call("POST", "/v1/sessions/$sid/context", buildJsonObject { put("context", ctx) }.toString(), SessionView.serializer())!!
        live.attach(v)
        toast(str(R.string.toast_context_switched))
    }

    fun saveMoment() = launchSafe { toast(str(if (live.saveMoment()) R.string.toast_moment_saved else R.string.toast_moment_failed)) }
    fun mute(minutes: Int) = launchSafe { live.setControls(buildJsonObject { put("mute_minutes", minutes) }) }
    fun unmute() = launchSafe { live.setControls(buildJsonObject { put("unmute", true) }) }
    fun setAssistance(mode: String, intensity: String) = launchSafe {
        live.setControls(buildJsonObject { put("assistance_mode", mode); put("proactive_intensity", intensity) })
    }
    fun setOutput(mode: String) = launchSafe { live.setControls(buildJsonObject { put("output_mode", mode) }) }
    fun insightFeedback(id: String, v: String) = launchSafe { live.feedback(id, v) }

    fun addNote(text: String, recollection: Boolean) = launchSafe {
        val sid = live.state.value.session?.sessionId ?: return@launchSafe
        c.api.post("/v1/sessions/$sid/notes", NoteIn(if (recollection) "RECOLLECTION" else "NOTE", text, clientId = UUID.randomUUID().toString(),
            atMs = if (recollection) null else live.noteAtMs()), JsonObject.serializer(), idempotent = false)
        toast(str(if (recollection) R.string.toast_recollection_saved else R.string.toast_note_saved))
    }

    fun explain() = launchSafe {
        val sid = live.state.value.session?.sessionId ?: return@launchSafe
        val r = c.api.raw("POST", "/v1/sessions/$sid/explain", buildJsonObject { put("window_seconds", 60) })!!
        _ui.update { it.copy(study = r) }
        go(Route.LiveAsk)
    }

    // ---------------------------------------------------------------- ask
    fun ask(question: String, mode: String, scope: String, scopeId: String?) = launchSafe {
        val sid = live.state.value.session?.sessionId
        val res = if (scope == "CURRENT_SESSION" && sid != null)
            c.api.post("/v1/sessions/$sid/ask", AskIn(question, mode, scope, null), AskResponse.serializer(), idempotent = false)
        else c.api.post("/v1/ask", AskIn(question, mode, scope, scopeId), AskResponse.serializer(), idempotent = false)
        _ui.update { it.copy(askResult = res) }
    }

    fun clearAsk() = _ui.update { it.copy(askResult = null, study = null) }

    /** Ask scoped to one session, live or finished ("Ask this meeting", "What did I miss?"). */
    fun askSession(sessionId: String, question: String, mode: String) = launchSafe {
        val res = c.api.post("/v1/sessions/$sessionId/ask", AskIn(question, mode, "CURRENT_SESSION", null), AskResponse.serializer(), idempotent = false)
        _ui.update { it.copy(askResult = res) }
    }

    fun catchUp() {
        val sid = live.state.value.session?.sessionId ?: return
        clearAsk()
        go(Route.LiveAsk)
        askSession(sid, str(R.string.quick_missed), "REMEMBER")
    }

    // ---------------------------------------------------------------- transcript / speakers / recap
    fun openTranscript(sessionId: String) { _ui.update { it.copy(transcript = emptyList()) }; loadTranscript(sessionId); go(Route.Transcript(sessionId)) }
    fun loadTranscript(sessionId: String) = launchSafe {
        val p = c.api.get("/v1/sessions/$sessionId/utterances", Page.serializer(Utterance.serializer()))
        _ui.update { it.copy(transcript = p.items) }
    }

    fun correctUtterance(sessionId: String, u: Utterance, text: String) = launchSafe {
        c.api.raw("PATCH", "/v1/sessions/$sessionId/utterances/${u.utteranceId}", buildJsonObject {
            put("text", text); put("expected_revision", u.revision) }, idempotent = true)
        toast(str(R.string.toast_correction_saved))
        val p = c.api.get("/v1/sessions/$sessionId/utterances", Page.serializer(Utterance.serializer()))
        _ui.update { it.copy(transcript = p.items) }
    }

    fun openRecap(sessionId: String) { _ui.update { it.copy(recap = null, askResult = null) }; loadRecap(sessionId); go(Route.Recap(sessionId)) }
    fun loadRecap(sessionId: String) = launchSafe { loadRecapNow(sessionId) }
    private suspend fun loadRecapNow(sessionId: String) {
        val r = c.api.raw("GET", "/v1/sessions/$sessionId/recap")
        _ui.update { it.copy(recap = r) }
    }

    fun review(sessionId: String, keep: List<String>, discard: Boolean, excludeFromSuggestions: Boolean = false) = launchSafe {
        c.api.raw("POST", "/v1/sessions/$sessionId/review", buildJsonObject {
            put("keep_claim_ids", JsonArray(keep.map { JsonPrimitive(it) })); put("discard_session", discard)
            put("exclude_from_suggestions", excludeFromSuggestions)
        }, idempotent = true)
        toast(str(if (discard) R.string.toast_session_discarded else R.string.toast_review_saved))
        if (live.state.value.session?.sessionId == sessionId) live.detach()
        _ui.update { it.copy(route = Route.Home, back = emptyList(), recap = null) }
        refreshHomeNow()
    }

    fun retryFinalization(sessionId: String) = launchSafe {
        c.api.raw("POST", "/v1/sessions/$sessionId/finalization/retry", null, idempotent = true); loadRecapNow(sessionId)
    }

    fun loadSpeakers(sessionId: String) = launchSafe {
        val r = c.api.raw("GET", "/v1/sessions/$sessionId/speakers")!!
        _ui.update { it.copy(speakers = r["items"] as? JsonArray) }
    }

    fun renameSpeaker(sessionId: String, alias: String, label: String, rev: Int) = launchSafe {
        c.api.raw("PATCH", "/v1/sessions/$sessionId/speakers/${URLEncoder.encode(alias, "UTF-8").replace("+", "%20")}",
            buildJsonObject { put("verified_label", label); put("expected_revision", rev) }, idempotent = true)
        toast(str(R.string.toast_speaker_updated))
        val r = c.api.raw("GET", "/v1/sessions/$sessionId/speakers")!!
        _ui.update { it.copy(speakers = r["items"] as? JsonArray) }
    }

    fun deleteSession(sessionId: String) = launchSafe {
        c.api.raw("DELETE", "/v1/sessions/$sessionId", null, idempotent = true)
        if (live.state.value.session?.sessionId == sessionId) live.detach()
        toast(str(R.string.toast_deletion_in_progress))
        _ui.update { st -> st.copy(route = Route.Home, back = emptyList(), recap = null,
            sessions = st.sessions.filter { it.sessionId != sessionId }) }
        refreshHomeNow()
    }

    /** Delete raw audio but keep transcript and notes (retention control, U10/U13). */
    fun deleteAudio(sessionId: String) = launchSafe {
        c.api.raw("DELETE", "/v1/sessions/$sessionId/audio", null, idempotent = true)
        evidence.stop()
        toast(str(R.string.toast_audio_deleted))
        loadRecapNow(sessionId)
    }

    // ---------------------------------------------------------------- session history (U11 timeline)
    fun loadSessions(reset: Boolean) = launchSafe {
        val cursor = if (reset) null else _ui.value.sessionsCursor
        if (!reset && cursor == null) return@launchSafe
        val q = "/v1/sessions?limit=30" + (cursor?.let { "&before=" + URLEncoder.encode(it, "UTF-8") } ?: "")
        val p = c.api.get(q, Page.serializer(SessionSummary.serializer()))
        _ui.update { st -> st.copy(sessions = if (reset) p.items else st.sessions + p.items, sessionsCursor = p.nextCursor, sessionsLoaded = true) }
    }

    // ---------------------------------------------------------------- memory detail: evidence, decisions, owners (S14/S22)
    fun openMemory(claimId: String) { _ui.update { it.copy(claim = null) }; loadMemory(claimId); go(Route.MemoryDetail(claimId)) }
    fun loadMemory(claimId: String) = launchSafe { _ui.update { it.copy(claim = c.api.raw("GET", "/v1/memories/$claimId")) } }

    private fun claimVersion(): Long = (_ui.value.claim?.get("version") as? JsonPrimitive)?.longOrNull ?: 0

    fun setDecision(claimId: String, toState: String, note: String?) = launchSafe {
        val r = c.api.raw("POST", "/v1/memories/$claimId/decision", buildJsonObject {
            put("to_state", toState); put("expected_version", claimVersion()); note?.takeIf { it.isNotBlank() }?.let { put("note", it) }
        }, idempotent = true)
        _ui.update { it.copy(claim = r) }
        toast(str(R.string.toast_decision_updated))
    }

    fun confirmOwner(claimId: String, owner: String, due: String) = launchSafe {
        val r = c.api.raw("POST", "/v1/memories/$claimId/owner", buildJsonObject {
            put("owner_label", owner.trim()); put("due_text", due.trim()); put("expected_version", claimVersion())
        }, idempotent = true)
        _ui.update { it.copy(claim = r) }
        toast(str(if (owner.isBlank()) R.string.toast_owner_cleared else R.string.toast_owner_confirmed))
    }

    fun editMemory(claimId: String, text: String?, excludeFromSuggestions: Boolean?) = launchSafe {
        val r = c.api.raw("PATCH", "/v1/memories/$claimId", buildJsonObject {
            text?.let { put("text_value", it) }; excludeFromSuggestions?.let { put("exclude_from_suggestions", it) }
            put("expected_version", claimVersion())
        }, idempotent = true)
        _ui.update { it.copy(claim = r) }
        toast(str(R.string.toast_memory_saved))
    }

    fun deleteMemory(claimId: String) = launchSafe {
        c.api.raw("DELETE", "/v1/memories/$claimId", null, idempotent = true)
        toast(str(R.string.toast_memory_deleted))
        _ui.update { st -> st.copy(memories = st.memories?.let { JsonArray(it.filter { m -> (m as? JsonObject)?.get("claim_id")?.let { id -> (id as JsonPrimitive).content } != claimId }) }) }
        back()
    }

    /** Never replay audio while any session may be capturing: the clip would be re-recorded into that conversation. */
    /** A tapped citation opens its source: a memory, or the cited moment (the transcript if that session is still live). */
    fun openCitation(cite: app.meetsaathi.core.Citation) {
        val sid = cite.sessionId
        val uid = cite.utteranceId
        when {
            cite.claimId != null && uid == null -> openMemory(cite.claimId)
            uid != null && sid != null -> {
                val s = live.state.value.session
                if (s != null && s.sessionId == sid && SessionState.parse(s.state) in SessionStateMachine.active) openTranscript(sid)
                else playEvidence(sid, uid)
            }
        }
    }

    fun openInsights(sessionId: String) {
        _ui.update { it.copy(insights = null) }
        go(Route.Insights(sessionId))
        launchSafe { _ui.update { it.copy(insights = c.api.raw("GET", "/v1/sessions/$sessionId/insights")?.get("items") as? JsonArray) } }
    }

    fun openInsight(sessionId: String, insightId: String) {
        _ui.update { it.copy(insightDetail = null) }
        go(Route.InsightDetail(sessionId, insightId))
        launchSafe { _ui.update { it.copy(insightDetail = c.api.raw("GET", "/v1/sessions/$sessionId/insights/$insightId")) } }
    }

    fun playEvidence(sessionId: String, utteranceId: String) {
        val s = live.state.value.session
        if (s != null && s.captureSource != "NONE" && SessionState.parse(s.state) in SessionStateMachine.active) {
            toast(str(R.string.evidence_while_recording)); return
        }
        evidence.toggle(sessionId, utteranceId)
    }

    // ---------------------------------------------------------------- memories
    fun loadMemories(spaceId: String, q: String?) = launchSafe {
        val qp = q?.takeIf { it.isNotBlank() }?.let { "&q=" + URLEncoder.encode(it, "UTF-8") } ?: ""
        val r = c.api.raw("GET", "/v1/memories?space_id=$spaceId&state=ALL$qp")!!
        _ui.update { it.copy(memories = r["items"] as? JsonArray, matchingSessions = r["matching_sessions"] as? JsonArray, memorySpace = spaceId) }
    }

    fun retain(spaceId: String, ids: List<String>) = launchSafe {
        c.api.raw("POST", "/v1/memories/retain", buildJsonObject { put("space_id", spaceId); put("claim_ids", JsonArray(ids.map { JsonPrimitive(it) })) }, idempotent = true)
        toast(c.app.resources.getQuantityString(R.plurals.toast_kept, ids.size, ids.size))
        val r = c.api.raw("GET", "/v1/memories?space_id=$spaceId&state=ALL")!!
        _ui.update { it.copy(memories = r["items"] as? JsonArray) }
    }

    // ---------------------------------------------------------------- projects, courses, interview goals; briefs & decision ledger
    fun loadProjects() = launchSafe { _ui.update { it.copy(projects = c.api.raw("GET", "/v1/projects")!!["items"] as? JsonArray) } }

    fun createProject(kind: String, title: String, meta: Map<String, String>, attachToDraft: Boolean = false) = launchSafe {
        // A project attached to a session must live in that session's space (the server enforces it; never mix spaces).
        val space = (if (attachToDraft) _ui.value.draft.spaceId else null) ?: spaceFor(kind) ?: return@launchSafe
        val r = c.api.raw("POST", "/v1/projects", buildJsonObject {
            put("space_id", space); put("kind", kind); put("title", title.trim())
            put("metadata", JsonObject(meta.filterValues { it.isNotBlank() }.mapValues { JsonPrimitive(it.value.trim()) }))
        })!!
        toast(str(R.string.toast_project_created))
        _ui.update { it.copy(projects = c.api.raw("GET", "/v1/projects")!!["items"] as? JsonArray) }
        if (attachToDraft) (r["project_id"] as? JsonPrimitive)?.content?.let { id -> updateDraft { it.copy(projectId = id) } }
        if (kind == "INTERVIEW_GOAL") loadInterviewNow()
    }

    private fun spaceFor(kind: String): String? {
        val spaces = _ui.value.me?.spaces.orEmpty()
        val want = when (kind) { "COURSE" -> "LEARNING"; else -> "WORK" }
        return spaces.firstOrNull { it.kind == want }?.spaceId ?: spaces.firstOrNull()?.spaceId
    }

    fun openProject(projectId: String) {
        _ui.update { it.copy(project = null, brief = null, decisions = null) }
        go(Route.Project(projectId))
        launchSafe {
            val p = c.api.raw("GET", "/v1/projects/$projectId")
            _ui.update { it.copy(project = p) }
            val d = c.api.raw("GET", "/v1/decisions?scope=SELECTED_PROJECT&scope_id=$projectId")
            _ui.update { it.copy(decisions = d?.get("items") as? JsonArray) }
        }
    }

    fun loadBrief(projectId: String) = launchSafe {
        _ui.update { it.copy(brief = c.api.raw("GET", "/v1/briefs?scope=SELECTED_PROJECT&scope_id=$projectId")) }
    }

    fun updateProject(projectId: String, title: String, meta: Map<String, String>) = launchSafe {
        val version = (_ui.value.project?.get("version") as? JsonPrimitive)?.longOrNull ?: 1
        c.api.raw("PATCH", "/v1/projects/$projectId", buildJsonObject {
            put("title", title.trim()); put("expected_version", version)
            // Blank values are sent (not dropped) so a cleared field really clears; the server merges metadata.
            put("metadata", JsonObject(meta.mapValues { JsonPrimitive(it.value.trim()) }))
        }, idempotent = true)
        toast(str(R.string.toast_project_saved))
        _ui.update { it.copy(project = c.api.raw("GET", "/v1/projects/$projectId")) }
    }

    fun deleteProject(projectId: String) = launchSafe {
        c.api.raw("DELETE", "/v1/projects/$projectId", null, idempotent = true)
        toast(str(R.string.toast_project_deleted))
        _ui.update { it.copy(projects = c.api.raw("GET", "/v1/projects")!!["items"] as? JsonArray, project = null) }
        back()
    }

    // ---------------------------------------------------------------- sharing (M23): preview, confirm, revoke
    fun openShare(sessionId: String) {
        _ui.update { it.copy(sharePreview = null, shareLink = null, shares = null) }
        go(Route.Share(sessionId))
        loadShares(sessionId)
    }

    fun loadShares(sessionId: String) = launchSafe {
        _ui.update { it.copy(shares = c.api.raw("GET", "/v1/sessions/$sessionId/shares")!!["items"] as? JsonArray) }
    }

    fun shareRequest(sessionId: String, sections: List<String>, redact: Boolean, hours: Int, confirm: Boolean) = launchSafe {
        val r = c.api.raw("POST", "/v1/sessions/$sessionId/shares", buildJsonObject {
            put("sections", JsonArray(sections.map { JsonPrimitive(it) })); put("redact_identities", redact)
            put("expires_in_hours", hours); put("confirm", confirm)
        }, idempotent = confirm)!!
        if (confirm) {
            _ui.update { it.copy(shareLink = r, sharePreview = r["preview"] as? JsonObject) }
            loadShares(sessionId)
        } else _ui.update { it.copy(sharePreview = r["preview"] as? JsonObject, shareLink = null) }
    }

    /** Recipient page (backend app/api/public_share.py): static, script-free, noindex, revocable. */
    fun shareUrl(token: String): String = c.api.baseUrl.trimEnd('/') + "/s/" + token

    fun revokeShare(sessionId: String, shareId: String) = launchSafe {
        c.api.raw("DELETE", "/v1/shares/$shareId", null, idempotent = true)
        toast(str(R.string.toast_share_revoked))
        _ui.update { it.copy(shareLink = if ((it.shareLink?.get("share_id") as? JsonPrimitive)?.content == shareId) null else it.shareLink) }
        loadShares(sessionId)
    }

    // ---------------------------------------------------------------- privacy: export (re-auth), delete account, devices
    fun requestExport(password: String, sessionId: String? = null) = launchSafe {
        c.api.reauth(password)
        val r = c.api.raw("POST", "/v1/exports", buildJsonObject { sessionId?.let { put("session_id", it) } })!!
        val id = (r["export_id"] as JsonPrimitive).content
        val scope = sessionId ?: "ALL"
        _ui.update { it.copy(export = ExportState(id, "REQUESTED", scope)) }
        // The export job runs server-side; poll briefly so the download appears without a manual refresh.
        repeat(30) {
            delay(2000)
            val st = c.api.raw("GET", "/v1/exports/$id")
            val status = (st?.get("status") as? JsonPrimitive)?.content ?: return@repeat
            _ui.update { it.copy(export = ExportState(id, status, scope)) }
            if (status != "REQUESTED" && status != "IN_PROGRESS") return@launchSafe
        }
    }

    fun refreshExport() = launchSafe {
        val e = _ui.value.export ?: return@launchSafe
        val st = c.api.raw("GET", "/v1/exports/${e.exportId}")
        _ui.update { it.copy(export = e.copy(status = (st?.get("status") as? JsonPrimitive)?.content ?: e.status)) }
    }

    /** Writes the export straight to the document the user picked; it is never cached elsewhere on the device. */
    fun saveExport(target: Uri) = launchSafe {
        val e = _ui.value.export ?: return@launchSafe
        val bytes = c.api.bytes("/v1/exports/${e.exportId}/download")
        withContext(Dispatchers.IO) { c.app.contentResolver.openOutputStream(target)?.use { it.write(bytes) } ?: error("no stream") }
        toast(str(R.string.toast_export_saved))
    }

    fun deleteAccount(password: String) = launchSafe {
        c.api.reauth(password)
        live.resetForSignOut(purgeLocal = true)
        evidence.stop(); evidence.purgeCache()
        c.api.raw("DELETE", "/v1/account")
        c.api.logout()
        _ui.value = UiState(route = Route.Welcome, toast = str(R.string.toast_account_deleted))
    }

    fun loadDevices() = launchSafe { _ui.update { it.copy(devices = c.api.raw("GET", "/v1/devices")!!["items"] as? JsonArray) } }

    fun revokeDevice(id: String) = launchSafe {
        c.api.raw("DELETE", "/v1/devices/$id")
        toast(str(R.string.toast_device_revoked))
        _ui.update { it.copy(devices = c.api.raw("GET", "/v1/devices")!!["items"] as? JsonArray) }
    }

    // ---------------------------------------------------------------- learning studio
    fun generatePractice(sessionId: String) = launchSafe {
        val r = c.api.raw("POST", "/v1/learning/practice", buildJsonObject { put("session_id", sessionId); put("count", 5) })!!
        _ui.update { it.copy(study = r, lastAttempt = null) }
        go(Route.Study)
    }

    fun attempt(itemId: String, response: String) = launchSafe {
        val r = c.api.raw("POST", "/v1/learning/practice/$itemId/attempts", buildJsonObject { put("response", response) })!!
        _ui.update { it.copy(lastAttempt = r) }
    }

    fun loadReviews() = launchSafe {
        val r = c.api.raw("GET", "/v1/learning/reviews")!!
        _ui.update { it.copy(reviews = r["items"] as? JsonArray) }
    }

    fun reviewAction(spaceId: String, key: String, action: String, days: Int?) = launchSafe {
        c.api.raw("POST", "/v1/learning/reviews/$key", buildJsonObject { put("space_id", spaceId); put("action", action); days?.let { put("days", it) } })
        loadReviews()
    }

    // ---------------------------------------------------------------- interview practice
    fun loadInterview() = launchSafe { loadInterviewNow() }
    private suspend fun loadInterviewNow() {
        val goals = c.api.raw("GET", "/v1/projects?kind=INTERVIEW_GOAL")!!["items"] as? JsonArray
        val mocks = c.api.raw("GET", "/v1/interview/mocks")!!["items"] as? JsonArray
        _ui.update { it.copy(goals = goals, mocks = mocks) }
    }

    fun startMock(topic: String, difficulty: String, goalId: String?, maxQuestions: Int = 3) = launchSafe {
        val space = spaceFor("INTERVIEW_GOAL") ?: return@launchSafe
        val r = c.api.raw("POST", "/v1/interview/mocks", buildJsonObject {
            put("space_id", space); put("topic", topic); put("difficulty", difficulty); put("max_questions", maxQuestions); goalId?.let { put("goal_id", it) }
        })!!
        _ui.update { it.copy(mock = r) }
        go(Route.Mock(((r["mock"] as JsonObject)["mock_id"] as JsonPrimitive).content))
    }

    fun mockAction(mockId: String, action: String, text: String?) = launchSafe {
        val r = c.api.raw("POST", "/v1/interview/mocks/$mockId/turns", buildJsonObject { put("action", action); text?.let { put("text", it) } })!!
        val notice = (r["notice"] as? JsonPrimitive)?.content
        if (notice != null) toast(notice)
        val merged = (_ui.value.mock ?: JsonObject(emptyMap())).toMutableMap().apply { putAll(r) }
        _ui.update { it.copy(mock = JsonObject(merged)) }
    }

    fun loadMock(mockId: String) = launchSafe { _ui.update { it.copy(mock = c.api.raw("GET", "/v1/interview/mocks/$mockId")) } }

    fun requestDebrief(mockId: String) = launchSafe {
        val r = c.api.raw("GET", "/v1/interview/mocks/$mockId/debrief")!!
        val merged = (_ui.value.mock ?: JsonObject(emptyMap())).toMutableMap().apply { putAll(r) }
        _ui.update { it.copy(mock = JsonObject(merged)) }
    }

    /** Focused single-question retry on one skill from the debrief (Answer Lab). */
    fun retrySkill(mockId: String, focus: String) = launchSafe {
        val r = c.api.raw("POST", "/v1/interview/mocks/$mockId/retry", buildJsonObject { put("focus", focus.take(300)) })!!
        _ui.update { it.copy(mock = r) }
        go(Route.Mock(((r["mock"] as JsonObject)["mock_id"] as JsonPrimitive).content))
    }

    override fun onCleared() { evidence.stop() }

    companion object {
        fun factory(c: AppContainer) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AppViewModel(c) as T
        }
    }
}
