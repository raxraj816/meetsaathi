package app.meetsaathi.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.PasswordVisualTransformation
import app.meetsaathi.R
import app.meetsaathi.core.Dates
import app.meetsaathi.core.LiveUiState
import app.meetsaathi.core.captureGapPhrase
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.Route
import app.meetsaathi.ui.UiState
import app.meetsaathi.ui.components.Banner
import app.meetsaathi.ui.components.Body
import app.meetsaathi.ui.components.CheckRow
import app.meetsaathi.ui.components.ChoiceChips
import app.meetsaathi.ui.components.ConfirmDanger
import app.meetsaathi.ui.components.Eyebrow
import app.meetsaathi.ui.components.GapBanner
import app.meetsaathi.ui.components.Heading
import app.meetsaathi.ui.components.LinkButton
import app.meetsaathi.ui.components.MsCard
import app.meetsaathi.ui.components.PrimaryButton
import app.meetsaathi.ui.components.Secondary
import app.meetsaathi.ui.components.SecondaryButton
import app.meetsaathi.ui.components.StatusPill
import app.meetsaathi.ui.components.Title
import app.meetsaathi.ui.components.Tone
import app.meetsaathi.ui.components.TopRow
import app.meetsaathi.ui.components.clock
import app.meetsaathi.ui.components.humanize
import app.meetsaathi.ui.theme.Spacing
import kotlinx.serialization.json.JsonPrimitive

/** Recap sections in outcome-first order (wire key → title). */
private val RECAP_SECTIONS = listOf("decisions" to R.string.sec_decisions, "actions" to R.string.sec_actions,
    "commitments" to R.string.sec_commitments, "open_questions" to R.string.sec_open_questions, "risks" to R.string.sec_risks,
    "concepts" to R.string.sec_concepts, "lessons" to R.string.sec_lessons, "ideas" to R.string.sec_ideas,
    "bookmarks" to R.string.sec_bookmarks, "notes" to R.string.sec_notes, "recollections" to R.string.sec_recollections,
    "ai_suggestions" to R.string.sec_ai_suggestions)

@Composable
fun decisionName(status: String?): String = stringResource(when (status) {
    "PROPOSED" -> R.string.decision_proposed; "DISCUSSED" -> R.string.decision_discussed; "ACCEPTED" -> R.string.decision_accepted
    "REJECTED" -> R.string.decision_rejected; "DEFERRED" -> R.string.decision_deferred; "SUPERSEDED" -> R.string.decision_superseded
    else -> R.string.decision_unresolved
})

@Composable
fun ownerText(owner: String?, confirmed: Boolean): String = when {
    owner.isNullOrBlank() -> stringResource(R.string.owner_unconfirmed)
    confirmed -> owner
    else -> stringResource(R.string.owner_named_unconfirmed, owner)
}

/** U09/U10 end + recap: capture stopped and finalization shown separately; outcomes first; deliberate keep/discard. */
@Composable
fun RecapScreen(vm: AppViewModel, ui: UiState, sessionId: String, live: LiveUiState) = Screen {
    val liveState = live.session?.takeIf { it.sessionId == sessionId }?.state
    LaunchedEffect(sessionId, liveState) { vm.loadRecap(sessionId) } // refresh when finalization completes
    val r = ui.recap?.takeIf { it.str("session_id") == sessionId }
    val keep = remember { mutableStateListOf<String>() }
    var confirmDiscard by remember { mutableStateOf(false) }
    var confirmAudio by remember { mutableStateOf(false) }
    var exclude by remember(sessionId) { mutableStateOf(false) }
    if (r == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    val proc = r.obj("processing")
    val state = r.str("state")
    val comp = r.obj("completeness")
    val ended = state in setOf("COMPLETED", "COMPLETED_PARTIAL", "FINALIZATION_RETRYABLE")
    Eyebrow(stringResource(R.string.recap_eyebrow))
    Heading(r.str("title") ?: "")
    Secondary(listOf(contextName(r.str("context") ?: "MEETING"), clock(r.long("duration_ms")), Dates.date(r.str("created_at")) ?: "").joinToString(" · "))
    if (live.session?.sessionId == sessionId && live.finalizationMessage != null && state in setOf("STOPPING", "FINALIZING"))
        StatusPill(live.finalizationMessage, Tone.Neutral)
    proc?.str("message")?.let { StatusPill(it, if (state == "COMPLETED") Tone.Accent else Tone.Caution) }
    if (state == "FINALIZATION_RETRYABLE") PrimaryButton(stringResource(R.string.recap_retry), { vm.retryFinalization(sessionId) })
    if (state == "FINALIZING" || state == "STOPPING") LinkButton(stringResource(R.string.action_refresh)) { vm.loadRecap(sessionId) }
    comp?.arr("gaps")?.forEach { g -> val o = g.o
        if (o.str("reason") != "PAUSED_BY_USER") GapBanner(captureGapPhrase(o.long("start_ms"), o.long("end_ms"), o.bool("time_bounds_estimated"), o.str("reason") ?: ""))
    }
    r.arr("participants_confirmed")?.mapNotNull { it.text.takeIf { t -> t.isNotBlank() } }?.takeIf { it.isNotEmpty() }?.let {
        Secondary(stringResource(R.string.recap_participants, it.joinToString(", ")))
    }
    if (comp?.bool("notes_only") == true) Secondary(stringResource(R.string.recap_notes_only))
    if (comp?.bool("audio_deleted") == true) Secondary(stringResource(R.string.recap_audio_deleted))
    r.obj("recap")?.let { rc ->
        MsCard {
            Eyebrow(stringResource(R.string.recap_summary))
            val summary = rc.arr("summary")
            if (summary.isNullOrEmpty()) Secondary(rc.str("message") ?: stringResource(R.string.recap_no_summary))
            summary?.forEach { Body(it.o.str("text") ?: "", size = 15) }
            if (rc.bool("visual_content_missing")) Secondary(stringResource(R.string.recap_visual_missing))
        }
        rc.arr("suggested_next_steps")?.takeIf { it.isNotEmpty() }?.let { steps ->
            MsCard(raised = true) { Eyebrow(stringResource(R.string.label_suggests)); steps.forEach { Body("• " + (it.o.str("text") ?: ""), size = 15) } }
        }
    }
    RECAP_SECTIONS.forEach { (key, title) ->
        val items = r.arr(key)?.takeIf { it.isNotEmpty() } ?: return@forEach
        Eyebrow(stringResource(title))
        items.forEach { el ->
            val c = el.o
            val id = c.str("claim_id") ?: return@forEach
            val stale = c.bool("stale") || id in live.invalidatedClaims
            MsCard {
                CheckRow(id in keep, c.str("text_value") ?: "", enabled = !stale) { v -> if (v) keep.add(id) else keep.remove(id) }
                val meta = buildList {
                    c.str("label")?.let { add(it) }
                    if (c.str("claim_kind") == "DECISION") add(decisionName(c.str("decision_status")))
                    if (c.str("claim_kind") in setOf("ACTION", "COMMITMENT")) add(ownerText(c.str("owner_label"), c.bool("owner_confirmed")))
                    c.str("due_text")?.let { add(stringResource(R.string.due_as_spoken, it)) }
                    c.long("time_start_ms")?.let { add("▶ ${clock(it)}") }
                }
                Secondary(meta.joinToString(" · "))
                if (stale) Banner(stringResource(R.string.recap_stale), Tone.Caution)
                LinkButton(stringResource(R.string.recap_open_item)) { vm.openMemory(id) }
            }
        }
    }
    if (ended || comp?.bool("notes_only") == true) RecapAsk(vm, ui, sessionId)
    if (r.str("review_state") == "PENDING") {
        Eyebrow(stringResource(R.string.recap_keep_title))
        Secondary(stringResource(R.string.recap_keep_note))
        val keepable = RECAP_SECTIONS.flatMap { (k, _) -> r.arr(k).orEmpty().map { it.o } }
            .filter { !it.bool("stale") && it.str("claim_id") !in live.invalidatedClaims }.mapNotNull { it.str("claim_id") }
        if (keepable.isNotEmpty()) {
            if (keep.containsAll(keepable)) LinkButton(stringResource(R.string.recap_select_none)) { keep.clear() }
            else LinkButton(stringResource(R.string.recap_select_all)) { keep.clear(); keep.addAll(keepable) }
        }
        CheckRow(exclude, stringResource(R.string.recap_exclude)) { exclude = it }
        PrimaryButton(if (keep.isEmpty()) stringResource(R.string.action_done) else pluralStringResource(R.plurals.recap_keep_n, keep.size, keep.size),
            { vm.review(sessionId, keep.toList(), false, exclude) }, enabled = !ui.busy)
    } else Secondary(stringResource(R.string.recap_reviewed))
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        if (comp?.bool("notes_only") != true) SecondaryButton(stringResource(R.string.live_transcript), { vm.openTranscript(sessionId) }, Modifier.weight(1f))
        if (comp?.bool("notes_only") != true) SecondaryButton(stringResource(R.string.recap_review_speakers), { vm.loadSpeakers(sessionId); vm.go(Route.Speakers(sessionId)) }, Modifier.weight(1f))
    }
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        if (ended) SecondaryButton(stringResource(R.string.recap_share), { vm.openShare(sessionId) }, Modifier.weight(1f))
        if (r.str("context") == "LEARNING") SecondaryButton(stringResource(R.string.recap_practice), { vm.generatePractice(sessionId) }, Modifier.weight(1f))
    }
    if (ended && comp?.bool("notes_only") != true && comp?.bool("audio_deleted") != true) {
        if (confirmAudio) ConfirmDanger(stringResource(R.string.recap_delete_audio_confirm), stringResource(R.string.recap_delete_audio),
            { confirmAudio = false }) { confirmAudio = false; vm.deleteAudio(sessionId) }
        else SecondaryButton(stringResource(R.string.recap_delete_audio), { confirmAudio = true }, Modifier.fillMaxWidth())
    }
    if (confirmDiscard) ConfirmDanger(stringResource(R.string.recap_discard_confirm), stringResource(R.string.recap_discard_action),
        { confirmDiscard = false }) { vm.review(sessionId, emptyList(), true) }
    else SecondaryButton(stringResource(R.string.recap_discard), { confirmDiscard = true }, Modifier.fillMaxWidth(), danger = true)
}

/** Recap "Ask this meeting": evidence-bound questions scoped to this one session. */
@Composable
private fun RecapAsk(vm: AppViewModel, ui: UiState, sessionId: String) {
    var q by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf("REMEMBER") }
    MsCard {
        Title(stringResource(R.string.recap_ask_title))
        AskModeChips(mode) { mode = it }
        OutlinedTextField(q, { q = it.take(4000) }, label = { Text(stringResource(R.string.recap_ask_hint)) }, modifier = Modifier.fillMaxWidth())
        SecondaryButton(stringResource(R.string.action_ask), { vm.askSession(sessionId, q, mode) }, Modifier.fillMaxWidth(), enabled = q.isNotBlank() && !ui.busy)
    }
    ui.askResult?.let { AnswerView(it) { c -> vm.openCitation(c) } }
}

/** S17 Speaker review: anonymous until the user confirms; corrections cascade (master 6.4). */
@Composable
fun SpeakersScreen(vm: AppViewModel, ui: UiState, sessionId: String) = Screen {
    TopRow(stringResource(R.string.speakers_eyebrow)) { vm.back() }
    Heading(stringResource(R.string.speakers_title))
    Secondary(stringResource(R.string.speakers_note))
    if (ui.speakers.isNullOrEmpty()) Secondary(stringResource(R.string.speakers_empty))
    ui.speakers?.forEach { el ->
        val sp = el.o
        val alias = sp.str("alias") ?: return@forEach
        var name by remember(alias) { mutableStateOf(sp.str("user_verified_label") ?: "") }
        val verified = sp.str("status") == "VERIFIED_BY_USER"
        MsCard {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Body(sp.str("user_verified_label") ?: stringResource(R.string.speaker_unconfirmed, alias))
                StatusPill(stringResource(if (verified) R.string.speakers_confirmed else R.string.speakers_anonymous), if (verified) Tone.Accent else Tone.Neutral)
            }
            if (sp.bool("has_overlap")) Secondary(stringResource(R.string.speakers_overlap))
            OutlinedTextField(name, { name = it.take(80) }, label = { Text(stringResource(R.string.speakers_name_hint)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            SecondaryButton(stringResource(R.string.action_save), { vm.renameSpeaker(sessionId, alias, name.ifBlank { "unknown" }, (sp.long("mapping_revision") ?: 1).toInt()) })
        }
    }
}

/** U11 Memories: scoped spaces, search, provenance, session timeline, projects/courses/goals. Never defaults to all spaces. */
@Composable
fun MemoriesScreen(vm: AppViewModel, ui: UiState) = Screen {
    val spaces = ui.me?.spaces.orEmpty()
    var space by remember { mutableStateOf(ui.memorySpace ?: spaces.firstOrNull { it.kind == "WORK" }?.spaceId) }
    var q by remember { mutableStateOf("") }
    LaunchedEffect(space) { space?.let { vm.loadMemories(it, null) } }
    Eyebrow(stringResource(R.string.memories_eyebrow))
    Heading(stringResource(R.string.memories_title))
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        SecondaryButton(stringResource(R.string.memories_sessions), { vm.loadSessions(true); vm.go(Route.Sessions) }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.memories_projects), { vm.loadProjects(); vm.go(Route.Projects) }, Modifier.weight(1f))
    }
    ChoiceChips(spaces.map { it.spaceId to it.name }, space, { space = it })
    Secondary(stringResource(R.string.memories_scope_note))
    OutlinedTextField(q, { q = it.take(200) }, label = { Text(stringResource(R.string.memories_search_hint)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    SecondaryButton(stringResource(R.string.action_search), { space?.let { vm.loadMemories(it, q) } }, Modifier.fillMaxWidth())
    ui.matchingSessions?.takeIf { it.isNotEmpty() }?.let { ms ->
        Eyebrow(stringResource(R.string.memories_matching_sessions))
        ms.forEach { s -> val o = s.o
            MsCard(Modifier.clickable(role = Role.Button) { o.str("session_id")?.let { vm.openRecap(it) } }) {
                Body(o.str("title") ?: "", size = 15)
                Secondary(listOf(contextName(o.str("context") ?: "MEETING"), Dates.date(o.str("created_at")) ?: "").joinToString(" · "))
            }
        }
    }
    var filter by remember { mutableStateOf("ALL") }
    ChoiceChips(listOf("ALL" to stringResource(R.string.filter_all), "DECISION" to stringResource(R.string.filter_decisions),
        "OWNER" to stringResource(R.string.filter_needs_owner), "QUESTION" to stringResource(R.string.filter_questions)), filter, { filter = it })
    val all = ui.memories
    val items = all?.filter { el -> val m = el.o
        when (filter) {
            "DECISION" -> m.str("claim_kind") == "DECISION"
            "OWNER" -> m.str("claim_kind") in setOf("ACTION", "COMMITMENT") && !m.bool("owner_confirmed")
            "QUESTION" -> m.str("claim_kind") in setOf("QUESTION", "RISK")
            else -> true
        } }
    if (all.isNullOrEmpty()) Secondary(stringResource(R.string.memories_empty))
    else if (items.isNullOrEmpty()) Secondary(stringResource(R.string.filter_empty))
    val pending = all.orEmpty().map { it.o }.filter { it.str("memory_state") == "PENDING_REVIEW" }.mapNotNull { it.str("claim_id") }
    if (pending.isNotEmpty() && space != null) SecondaryButton(pluralStringResource(R.plurals.memories_keep_pending, pending.size, pending.size),
        { vm.retain(space!!, pending) }, Modifier.fillMaxWidth())
    items?.forEach { el ->
        val m = el.o
        val state = m.str("memory_state")
        MsCard(Modifier.clickable(role = Role.Button) { m.str("claim_id")?.let { vm.openMemory(it) } }) {
            Body(m.str("text_value") ?: "", size = 15)
            Secondary(listOfNotNull(m.str("provenance_label"), humanize(m.str("claim_kind")),
                m.str("decision_status")?.let { decisionName(it) }, m.str("session_title"), memoryStateName(state)).joinToString(" · "))
            if (state == "INVALIDATED") Banner(stringResource(R.string.memory_invalidated), Tone.Caution)
        }
    }
    LinkButton(stringResource(R.string.memories_ask_space)) { vm.tab(app.meetsaathi.ui.Tab.Ask) }
}

@Composable
fun memoryStateName(state: String?): String? = when (state) {
    "APPROVED" -> stringResource(R.string.mstate_kept); "PENDING_REVIEW" -> stringResource(R.string.mstate_pending)
    "INVALIDATED" -> stringResource(R.string.mstate_invalidated); null -> null; else -> humanize(state)
}

/** U12 Ask across sessions: explicit, visible retrieval boundary. */
@Composable
fun AskScreen(vm: AppViewModel, ui: UiState) = Screen {
    val spaces = ui.me?.spaces.orEmpty()
    var scopeId by remember { mutableStateOf(spaces.firstOrNull { it.kind == "WORK" }?.spaceId) }
    var general by remember { mutableStateOf(false) }
    var mode by remember { mutableStateOf("REMEMBER") }
    var q by remember { mutableStateOf("") }
    var project by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { vm.loadProjects() }
    Eyebrow(stringResource(R.string.ask_eyebrow))
    Heading(stringResource(R.string.ask_title))
    Title(stringResource(R.string.ask_scope))
    ChoiceChips(spaces.map { it.spaceId to it.name } + ("GENERAL" to stringResource(R.string.ask_general)), if (general) "GENERAL" else if (project == null) scopeId else null,
        { project = null; if (it == "GENERAL") general = true else { general = false; scopeId = it } })
    ui.projects?.takeIf { it.isNotEmpty() }?.let { ps ->
        Secondary(stringResource(R.string.ask_single_project))
        ChoiceChips(ps.map { (it.o.str("project_id") ?: "") to (it.o.str("title") ?: "") }, project, { project = it; general = false })
    }
    AskModeChips(mode) { mode = it }
    Secondary(stringResource(if (mode == "REMEMBER") R.string.ask_remember_note else R.string.ask_ai_note))
    OutlinedTextField(q, { q = it.take(4000) }, label = { Text(stringResource(R.string.ask_hint)) }, modifier = Modifier.fillMaxWidth())
    PrimaryButton(stringResource(R.string.action_ask), { vm.ask(q, mode, when { general -> "GENERAL"; project != null -> "SELECTED_PROJECT"; else -> "SELECTED_SPACE" },
        when { general -> null; project != null -> project; else -> scopeId }) }, enabled = q.isNotBlank() && !ui.busy)
    ui.askResult?.let { a ->
        AnswerView(a) { c -> vm.openCitation(c) }
        Secondary(pluralStringResource(R.plurals.ask_searched, a.searchedSessions, a.searchedSessions))
    }
}

/** U13 You: assistance defaults, retention, privacy, devices, accessibility, export/delete (re-authentication for sensitive actions). */
@Composable
fun YouScreen(vm: AppViewModel, ui: UiState) = Screen {
    var pw by remember { mutableStateOf("") }
    var confirmDelete by remember { mutableStateOf(false) }
    val saveExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let { vm.saveExport(it) } }
    LaunchedEffect(Unit) { vm.loadDevices() }
    Eyebrow(stringResource(R.string.you_eyebrow))
    Heading(stringResource(R.string.you_title))
    MsCard {
        Title(stringResource(R.string.you_defaults))
        Secondary(stringResource(R.string.you_defaults_note))
        Body(stringResource(R.string.you_default_assistance), size = 15)
        AssistanceChips(vm.pref("default_assistance") ?: "LISTENER", true) { vm.savePrefs(mapOf("default_assistance" to JsonPrimitive(it))) }
        Body(stringResource(R.string.you_default_output), size = 15)
        OutputChips(vm.pref("default_output") ?: "TEXT", { true }) { vm.savePrefs(mapOf("default_output" to JsonPrimitive(it))) }
        if (vm.pref("default_output").let { it != null && it != "TEXT" }) Secondary(stringResource(R.string.you_voice_still_tested))
        Body(stringResource(R.string.you_default_intensity), size = 15)
        val byCtx = ui.me?.preferences?.obj("default_intensity_by_context")
        listOf("MEETING", "LEARNING", "INTERVIEW", "CONVERSATION").forEach { ctx ->
            Secondary(contextName(ctx))
            IntensityChips(byCtx?.str(ctx) ?: "QUIET") { vm.setDefaultIntensity(ctx, it) }
        }
    }
    MsCard {
        Title(stringResource(R.string.you_accessibility))
        CheckRow(vm.prefBool("captions_large"), stringResource(R.string.you_captions_large)) { vm.savePrefs(mapOf("captions_large" to JsonPrimitive(it))) }
        Secondary(stringResource(R.string.you_accessibility_body))
    }
    MsCard {
        Title(stringResource(R.string.you_retention))
        Secondary(stringResource(R.string.you_retention_body))
    }
    ui.me?.let { me ->
        MsCard {
            Title(stringResource(R.string.you_usage))
            Secondary(stringResource(R.string.you_usage_line, me.quota.captureHoursUsed, me.quota.captureHoursLimit, me.quota.reasonerCallsUsed, me.quota.reasonerCallsLimit))
            Secondary(stringResource(R.string.you_region, me.tenant.str("residency_region") ?: "", me.disclosureVersion))
        }
    }
    MsCard {
        Title(stringResource(R.string.you_privacy))
        Secondary(stringResource(R.string.you_reauth_note))
        OutlinedTextField(pw, { pw = it.take(256) }, label = { Text(stringResource(R.string.you_password)) }, visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(), singleLine = true)
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
            SecondaryButton(stringResource(R.string.you_export), { vm.requestExport(pw); pw = "" }, Modifier.weight(1f), enabled = pw.length >= 10 && !ui.busy)
            SecondaryButton(stringResource(R.string.you_delete_account), { confirmDelete = true }, Modifier.weight(1f), danger = true, enabled = pw.length >= 10)
        }
        ExportStatus(vm, ui) { saveExport.launch("meetsaathi-export.json") }
        if (confirmDelete) ConfirmDanger(stringResource(R.string.you_delete_confirm), stringResource(R.string.you_delete_action),
            { confirmDelete = false }) { vm.deleteAccount(pw) }
    }
    MsCard {
        Title(stringResource(R.string.you_devices))
        ui.devices?.forEach { el ->
            val d = el.o
            val revoked = d.str("revoked_at") != null
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Secondary(listOfNotNull(d.str("name"), humanize(d.str("platform")), if (d.bool("current")) stringResource(R.string.you_this_device) else null,
                    if (revoked) stringResource(R.string.you_signed_out) else null).joinToString(" · "))
                if (!revoked && !d.bool("current")) LinkButton(stringResource(R.string.you_sign_out_device)) { d.str("device_id")?.let { vm.revokeDevice(it) } }
            }
        }
    }
    SecondaryButton(stringResource(R.string.you_sign_out), { vm.signOut() }, Modifier.fillMaxWidth())
}

/** Export progress with an honest status; the file is saved only where the user chooses. */
@Composable
fun ExportStatus(vm: AppViewModel, ui: UiState, onSave: () -> Unit) {
    val e = ui.export ?: return
    when (e.status) {
        "REQUESTED", "IN_PROGRESS" -> { StatusPill(stringResource(R.string.export_preparing), Tone.Neutral); LinkButton(stringResource(R.string.action_refresh)) { vm.refreshExport() } }
        "COMPLETE" -> { StatusPill(stringResource(R.string.export_ready), Tone.Accent); SecondaryButton(stringResource(R.string.export_save), onSave, Modifier.fillMaxWidth()) }
        "EXPIRED" -> StatusPill(stringResource(R.string.export_expired), Tone.Caution)
        else -> StatusPill(stringResource(R.string.export_failed), Tone.Danger)
    }
}
