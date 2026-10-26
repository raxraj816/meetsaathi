package app.meetsaathi.ui.screens

import android.content.ClipData
import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ClipEntry
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.PasswordVisualTransformation
import app.meetsaathi.R
import app.meetsaathi.core.Dates
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.Route
import app.meetsaathi.ui.UiState
import app.meetsaathi.ui.components.Banner
import app.meetsaathi.ui.components.Body
import app.meetsaathi.ui.components.CheckRow
import app.meetsaathi.ui.components.ChoiceChips
import app.meetsaathi.ui.components.ConfirmDanger
import app.meetsaathi.ui.components.EvidenceButton
import app.meetsaathi.ui.components.Eyebrow
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
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

/** Mirror of backend DECISION_FLOW (app/memory/service.py); the server is authoritative and re-validates. */
val DECISION_FLOW: Map<String?, List<String>> = mapOf(
    null to listOf("PROPOSED", "DISCUSSED", "UNRESOLVED"),
    "PROPOSED" to listOf("DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"),
    "DISCUSSED" to listOf("ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"),
    "UNRESOLVED" to listOf("DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED"),
    "DEFERRED" to listOf("DISCUSSED", "ACCEPTED", "REJECTED", "UNRESOLVED"),
    "ACCEPTED" to listOf("SUPERSEDED"),
    "REJECTED" to listOf("SUPERSEDED", "DISCUSSED"),
    "SUPERSEDED" to emptyList(),
)

/**
 * S14 evidence + S22 decision/owner. One memory with its provenance, the exact cited transcript revisions (with replay
 * of the cited span when audio is retained), decision status history, and owner confirmation. Recorded items are
 * corrected at the source (transcript/speaker), never rewritten here.
 */
@Composable
fun MemoryDetailScreen(vm: AppViewModel, ui: UiState, claimId: String) = Screen {
    val c = ui.claim?.takeIf { it.str("claim_id") == claimId }
    val player by vm.evidence.state.collectAsState()
    TopRow(stringResource(R.string.memory_eyebrow)) { vm.back() }
    if (c == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    val kind = c.str("claim_kind")
    val recorded = c.str("provenance") == "RECORDED"
    val sessionId = c.str("session_id")
    var editing by remember(claimId) { mutableStateOf(false) }
    var text by remember(claimId) { mutableStateOf(c.str("text_value") ?: "") }
    var confirmDelete by remember { mutableStateOf(false) }

    StatusPill(c.str("provenance_label") ?: "", if (recorded) Tone.Accent else Tone.Neutral)
    if (editing) {
        OutlinedTextField(text, { text = it.take(8000) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
            SecondaryButton(stringResource(R.string.action_cancel), { editing = false; text = c.str("text_value") ?: "" }, Modifier.weight(1f))
            SecondaryButton(stringResource(R.string.action_save), { vm.editMemory(claimId, text, null); editing = false }, Modifier.weight(1f), enabled = text.isNotBlank())
        }
    } else Heading(c.str("text_value") ?: "")
    c.str("long_text")?.let { Body(it, size = 15) }
    Secondary(listOfNotNull(humanize(kind), memoryStateName(c.str("memory_state")), c.str("session_title"), Dates.date(c.str("session_created_at"))).joinToString(" · "))
    if (c.str("memory_state") == "INVALIDATED") Banner(stringResource(R.string.memory_invalidated), Tone.Caution)

    // Evidence: the exact revisions this memory was built from.
    val sources = c.arr("sources").orEmpty()
    MsCard {
        Title(stringResource(R.string.memory_sources))
        if (sources.isEmpty()) Secondary(stringResource(if (recorded) R.string.memory_no_sources else R.string.memory_user_source))
        sources.forEach { el -> val s = el.o
            val uid = s.str("utterance_id") ?: return@forEach
            Secondary(listOfNotNull(clock(s.long("start_ms")), s.str("speaker_label_snapshot"),
                stringResource(if (s.bool("is_final")) R.string.label_final else R.string.label_provisional)).joinToString(" · "))
            Body("“${s.str("transcript") ?: ""}”", size = 15)
            if (!s.bool("is_current")) Banner(stringResource(R.string.memory_source_corrected), Tone.Caution)
            if (s.bool("replay_available") && sessionId != null) EvidenceButton(player, uid, s.long("start_ms")) { vm.playEvidence(sessionId, uid) }
            else Secondary(stringResource(R.string.evidence_deleted))
        }
    }

    if (kind == "DECISION") DecisionCard(vm, c, claimId)
    if (kind == "ACTION" || kind == "COMMITMENT") OwnerCard(vm, c, claimId)

    MsCard {
        Title(stringResource(R.string.memory_controls))
        CheckRow(c.bool("exclude_from_suggestions"), stringResource(R.string.memory_exclude)) { vm.editMemory(claimId, null, it) }
        if (recorded) Secondary(stringResource(R.string.memory_recorded_edit_note))
        else if (!editing) LinkButton(stringResource(R.string.memory_edit)) { editing = true }
        if (sessionId != null) LinkButton(stringResource(R.string.memory_open_session)) { vm.openRecap(sessionId) }
        if (confirmDelete) ConfirmDanger(stringResource(R.string.memory_delete_confirm), stringResource(R.string.action_delete),
            { confirmDelete = false }) { confirmDelete = false; vm.deleteMemory(claimId) }
        else SecondaryButton(stringResource(R.string.memory_delete), { confirmDelete = true }, Modifier.fillMaxWidth(), danger = true)
    }
}

@Composable
private fun DecisionCard(vm: AppViewModel, c: JsonObject, claimId: String) {
    val status = c.str("decision_status")
    var note by remember(claimId) { mutableStateOf("") }
    MsCard(raised = true) {
        Title(stringResource(R.string.decision_title))
        StatusPill(decisionName(status), if (status == "ACCEPTED") Tone.Accent else Tone.Caution)
        Secondary(stringResource(R.string.decision_note))
        val next = DECISION_FLOW[status].orEmpty()
        if (next.isNotEmpty()) {
            OutlinedTextField(note, { note = it.take(300) }, label = { Text(stringResource(R.string.decision_reason_hint)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            ChoiceChips(next.map { it to decisionName(it) }, null, { vm.setDecision(claimId, it, note); note = "" })
        }
        c.arr("decision_history")?.takeIf { it.isNotEmpty() }?.let { h ->
            Eyebrow(stringResource(R.string.decision_history))
            h.forEach { e -> val o = e.o
                Secondary(listOfNotNull(Dates.dateTime(o.str("created_at")),
                    "${o.str("from_state")?.let { decisionName(it) } ?: "—"} → ${decisionName(o.str("to_state"))}",
                    o.str("actor")?.let { humanize(it) }, o.str("note")).joinToString(" · "))
            }
        }
    }
}

@Composable
private fun OwnerCard(vm: AppViewModel, c: JsonObject, claimId: String) {
    var owner by remember(claimId, c.long("version")) { mutableStateOf(c.str("owner_label") ?: "") }
    var due by remember(claimId, c.long("version")) { mutableStateOf(c.str("due_text") ?: "") }
    MsCard(raised = true) {
        Title(stringResource(R.string.owner_title))
        StatusPill(ownerText(c.str("owner_label"), c.bool("owner_confirmed")), if (c.bool("owner_confirmed")) Tone.Accent else Tone.Caution)
        Secondary(stringResource(R.string.owner_note))
        OutlinedTextField(owner, { owner = it.take(120) }, label = { Text(stringResource(R.string.owner_hint)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(due, { due = it.take(120) }, label = { Text(stringResource(R.string.owner_due_hint)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
            SecondaryButton(stringResource(R.string.owner_confirm), { vm.confirmOwner(claimId, owner, due) }, Modifier.weight(1f), enabled = owner.isNotBlank())
            if (c.str("owner_label") != null) SecondaryButton(stringResource(R.string.owner_clear), { vm.confirmOwner(claimId, "", "") }, Modifier.weight(1f))
        }
    }
}

private val SHARE_SECTIONS = listOf("summary" to R.string.share_sec_summary, "decisions" to R.string.sec_decisions, "actions" to R.string.sec_actions,
    "questions" to R.string.share_sec_questions, "notes" to R.string.sec_notes)

/** M23: audience-specific share with a redaction preview before any link exists; expiry and revoke; no audio ever. */
@Composable
fun ShareScreen(vm: AppViewModel, ui: UiState, sessionId: String) = Screen {
    val sections = remember { mutableStateListOf("summary", "decisions", "actions", "questions") }
    var redact by remember { mutableStateOf(true) }
    var hours by remember { mutableStateOf(72) }
    var pw by remember { mutableStateOf("") }
    val context = LocalContext.current
    val clipboard = LocalClipboard.current
    val scope = rememberCoroutineScope()
    TopRow(stringResource(R.string.share_eyebrow)) { vm.back() }
    Heading(stringResource(R.string.share_title))
    Secondary(stringResource(R.string.share_note))
    MsCard {
        Title(stringResource(R.string.share_include))
        SHARE_SECTIONS.forEach { (key, label) ->
            CheckRow(key in sections, stringResource(label)) { v -> if (v) sections.add(key) else sections.remove(key) }
        }
        CheckRow(redact, stringResource(R.string.share_redact)) { redact = it }
        Secondary(stringResource(R.string.share_expires))
        ChoiceChips(listOf("24" to pluralStringResource(R.plurals.hours, 24, 24), "72" to pluralStringResource(R.plurals.days, 3, 3),
            "168" to pluralStringResource(R.plurals.days, 7, 7), "720" to pluralStringResource(R.plurals.days, 30, 30)), hours.toString(), { hours = it.toInt() })
        SecondaryButton(stringResource(R.string.share_preview), { vm.shareRequest(sessionId, sections.toList(), redact, hours, false) },
            Modifier.fillMaxWidth(), enabled = sections.isNotEmpty() && !ui.busy)
    }
    ui.sharePreview?.let { p ->
        MsCard(raised = true) {
            Eyebrow(stringResource(R.string.share_preview_eyebrow))
            Title(p.str("title") ?: "")
            Secondary(listOfNotNull(p.str("date"), p.str("context")?.let { contextName(it) }).joinToString(" · "))
            p.arr("summary")?.forEach { Body(it.text, size = 15) }
            listOf("decisions" to R.string.sec_decisions, "actions" to R.string.sec_actions, "questions" to R.string.share_sec_questions, "notes" to R.string.sec_notes)
                .forEach { (k, label) -> p.arr(k)?.takeIf { it.isNotEmpty() }?.let { items ->
                    Eyebrow(stringResource(label))
                    items.forEach { i -> val o = i.o
                        Body("• " + (o.str("text") ?: ""), size = 15)
                        val meta = listOfNotNull(o.str("status")?.let { decisionName(it) }, o.str("owner"), o.str("label")).joinToString(" · ")
                        if (meta.isNotBlank()) Secondary(meta)
                    }
                } }
            Secondary(p.str("notice") ?: "")
        }
        if (ui.shareLink == null) PrimaryButton(stringResource(R.string.share_create), { vm.shareRequest(sessionId, sections.toList(), redact, hours, true) }, enabled = !ui.busy)
    }
    ui.shareLink?.let { l ->
        val url = vm.shareUrl(l.str("token") ?: "")
        MsCard(raised = true) {
            StatusPill(stringResource(R.string.share_link_ready, Dates.dateTime(l.str("expires_at")) ?: ""), Tone.Accent)
            Secondary(stringResource(R.string.share_link_once))
            Body(url, size = 13)
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                SecondaryButton(stringResource(R.string.share_copy), {
                    scope.launch { clipboard.setClipEntry(ClipEntry(ClipData.newPlainText("MeetSaathi", url))) }
                    vm.toast(context.getString(R.string.share_copied)) }, Modifier.weight(1f))
                SecondaryButton(stringResource(R.string.share_send), {
                    context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, url), null))
                }, Modifier.weight(1f))
            }
        }
    }
    ui.shares?.takeIf { it.isNotEmpty() }?.let { shares ->
        Eyebrow(stringResource(R.string.share_existing))
        shares.forEach { el -> val s = el.o
            val revoked = s.str("revoked_at") != null
            MsCard {
                Secondary(listOfNotNull(stringResource(R.string.share_created_at, Dates.dateTime(s.str("created_at")) ?: ""),
                    if (revoked) stringResource(R.string.share_revoked) else stringResource(R.string.share_expires_at, Dates.dateTime(s.str("expires_at")) ?: ""),
                    if (s.bool("stale")) stringResource(R.string.share_stale) else null).joinToString(" · "))
                if (!revoked) LinkButton(stringResource(R.string.share_revoke)) { s.str("share_id")?.let { vm.revokeShare(sessionId, it) } }
            }
        }
    }
    MsCard {
        Title(stringResource(R.string.share_export_title))
        Secondary(stringResource(R.string.share_export_note))
        OutlinedTextField(pw, { pw = it.take(256) }, label = { Text(stringResource(R.string.you_password)) }, visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(), singleLine = true)
        SecondaryButton(stringResource(R.string.share_export), { vm.requestExport(pw, sessionId); pw = "" }, Modifier.fillMaxWidth(), enabled = pw.length >= 10 && !ui.busy)
        val saver = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/json")) { uri ->
            uri?.let { vm.saveExport(it) } }
        if (ui.export?.scope == sessionId) ExportStatus(vm, ui) { saver.launch("meetsaathi-session.json") }
    }
}

/** U11 session timeline: every session, newest first, paged. */
@Composable
fun SessionsScreen(vm: AppViewModel, ui: UiState) = Screen {
    TopRow(stringResource(R.string.memories_sessions)) { vm.back() }
    Heading(stringResource(R.string.sessions_title))
    if (ui.sessionsLoaded && ui.sessions.isEmpty()) Secondary(stringResource(R.string.home_empty))
    ui.sessions.forEach { s ->
        MsCard(Modifier.clickable(role = Role.Button) { vm.openRecap(s.sessionId) }) {
            Title(s.title)
            Secondary(sessionMeta(s.context, s.sourceWatermarkMs, s.decisions, s.openItems))
            Secondary(listOf(Dates.date(s.createdAt) ?: "", stateName(s.state)).joinToString(" · "))
        }
    }
    if (ui.sessionsCursor != null) SecondaryButton(stringResource(R.string.action_load_more), { vm.loadSessions(false) }, Modifier.fillMaxWidth(), enabled = !ui.busy)
}

private val KIND_FIELDS = mapOf(
    "PROJECT" to listOf("description" to R.string.field_description),
    "COURSE" to listOf("term" to R.string.field_term, "instructor_label" to R.string.field_instructor, "syllabus_text" to R.string.field_syllabus),
    "INTERVIEW_GOAL" to listOf("company" to R.string.field_company, "stage" to R.string.field_stage, "interview_date" to R.string.field_interview_date,
        "coding_language" to R.string.field_coding_language, "jd_text" to R.string.field_jd, "experience_notes" to R.string.field_experience),
)
private val LONG_FIELDS = setOf("description", "syllabus_text", "jd_text", "experience_notes")

/** Create/edit form shared by projects, courses and interview goals (job description lives here). */
@Composable
fun ProjectForm(kind: String, initialTitle: String, initial: JsonObject?, submitLabel: String, busy: Boolean, onSubmit: (String, Map<String, String>) -> Unit) {
    var title by remember(kind, initialTitle) { mutableStateOf(initialTitle) }
    val fields = KIND_FIELDS.getValue(kind)
    val values = remember(kind, initial) { mutableStateListOf(*fields.map { initial?.str(it.first) ?: "" }.toTypedArray()) }
    OutlinedTextField(title, { title = it.take(160) }, label = { Text(stringResource(if (kind == "INTERVIEW_GOAL") R.string.field_role else R.string.field_title)) },
        modifier = Modifier.fillMaxWidth(), singleLine = true)
    fields.forEachIndexed { i, (key, label) ->
        val long = key in LONG_FIELDS
        OutlinedTextField(values[i], { values[i] = it.take(if (long) 20000 else 200) }, label = { Text(stringResource(label)) },
            modifier = Modifier.fillMaxWidth(), singleLine = !long, minLines = if (long) 3 else 1)
        if (key == "jd_text") Secondary(stringResource(R.string.field_jd_note))
    }
    SecondaryButton(submitLabel, { onSubmit(title, fields.mapIndexed { i, f -> f.first to values[i] }.toMap()) }, Modifier.fillMaxWidth(),
        enabled = title.isNotBlank() && !busy)
}

/** Projects, courses and interview goals: the scopes for briefs, decision ledgers and Ask. */
@Composable
fun ProjectsScreen(vm: AppViewModel, ui: UiState) = Screen {
    var kind by remember { mutableStateOf("PROJECT") }
    var creating by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.loadProjects() }
    TopRow(stringResource(R.string.memories_projects)) { vm.back() }
    Heading(stringResource(R.string.projects_title))
    Secondary(stringResource(R.string.projects_note))
    val all = ui.projects.orEmpty().map { it.o }
    listOf("PROJECT", "COURSE", "INTERVIEW_GOAL").forEach { k ->
        val items = all.filter { it.str("kind") == k }
        if (items.isEmpty()) return@forEach
        Eyebrow(projectKindName(k))
        items.forEach { p ->
            MsCard(Modifier.clickable(role = Role.Button) { p.str("project_id")?.let { vm.openProject(it) } }) {
                Title(p.str("title") ?: "")
                Secondary(p.str("last_session_at")?.let { stringResource(R.string.projects_last_session, Dates.date(it) ?: "") } ?: stringResource(R.string.projects_no_sessions))
            }
        }
    }
    if (all.isEmpty()) Secondary(stringResource(R.string.projects_empty))
    MsCard {
        if (creating) {
            Title(stringResource(R.string.projects_new))
            ChoiceChips(listOf("PROJECT", "COURSE", "INTERVIEW_GOAL").map { it to projectKindName(it) }, kind, { kind = it })
            ProjectForm(kind, "", null, stringResource(R.string.action_create), ui.busy) { title, meta -> vm.createProject(kind, title, meta); creating = false }
            LinkButton(stringResource(R.string.action_cancel)) { creating = false }
        } else SecondaryButton(stringResource(R.string.projects_new), { creating = true }, Modifier.fillMaxWidth())
    }
}

/** One project/course/goal: sessions, decision ledger (M19), next-time brief (M22/S21), editable context, delete. */
@Composable
fun ProjectScreen(vm: AppViewModel, ui: UiState, projectId: String) = Screen {
    val p = ui.project?.takeIf { it.str("project_id") == projectId }
    var editing by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    TopRow(stringResource(R.string.memories_projects)) { vm.back() }
    if (p == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    val kind = p.str("kind") ?: "PROJECT"
    Eyebrow(projectKindName(kind))
    Heading(p.str("title") ?: "")
    val meta = p.obj("metadata")
    KIND_FIELDS.getValue(kind).forEach { (k, label) -> meta?.str(k)?.let { v ->
        Secondary(stringResource(label) + ": " + if (k in LONG_FIELDS && v.length > 240) v.take(240) + "…" else v) } }
    if (kind == "INTERVIEW_GOAL") {
        if (meta?.str("jd_text") == null) Banner(stringResource(R.string.interview_jd_missing), Tone.Caution)
        PrimaryButton(stringResource(R.string.project_warmup), { vm.startMock(meta?.str("stage") ?: p.str("title") ?: "", "Warmup", projectId, 3) }, enabled = !ui.busy)
    }
    if (editing) MsCard {
        ProjectForm(kind, p.str("title") ?: "", meta, stringResource(R.string.action_save), ui.busy) { title, m -> vm.updateProject(projectId, title, m); editing = false }
        LinkButton(stringResource(R.string.action_cancel)) { editing = false }
    } else LinkButton(stringResource(R.string.action_edit)) { editing = true }

    MsCard(raised = true) {
        Title(stringResource(if (kind == "COURSE") R.string.brief_title_course else R.string.brief_title))
        val b = ui.brief
        if (b == null) SecondaryButton(stringResource(R.string.brief_prepare), { vm.loadBrief(projectId) }, Modifier.fillMaxWidth(), enabled = !ui.busy)
        else if (b.bool("empty")) Secondary(b.str("message") ?: stringResource(R.string.brief_empty))
        else {
            Secondary(stringResource(R.string.brief_scope_note))
            b.arr("last_agreed")?.takeIf { it.isNotEmpty() }?.let { items ->
                Eyebrow(stringResource(R.string.brief_last_agreed))
                items.forEach { i -> BriefItem(vm, i.o) }
            }
            b.arr("still_open")?.takeIf { it.isNotEmpty() }?.let { items ->
                Eyebrow(stringResource(R.string.brief_still_open))
                items.forEach { i -> BriefItem(vm, i.o) }
            }
            val qs = b.arr("questions_worth_asking").orEmpty()
            if (qs.isNotEmpty()) {
                Eyebrow(b.str("questions_label") ?: stringResource(R.string.label_suggests))
                qs.forEach { Body("? " + it.text, size = 15) }
            } else if (b.bool("questions_unavailable")) Secondary(stringResource(R.string.brief_questions_unavailable))
        }
    }

    val decisions = ui.decisions.orEmpty()
    if (kind != "INTERVIEW_GOAL") MsCard {
        Title(stringResource(R.string.ledger_title))
        if (decisions.isEmpty()) Secondary(stringResource(R.string.ledger_empty))
        decisions.forEach { d -> val o = d.o
            Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { o.str("claim_id")?.let { vm.openMemory(it) } }) {
                androidx.compose.foundation.layout.Column {
                    Body(o.str("text_value") ?: "", size = 15)
                    Secondary(listOfNotNull(decisionName(o.str("decision_status")), o.str("session_title"), Dates.date(o.str("session_date")),
                        if (o.bool("stale")) stringResource(R.string.mstate_invalidated) else null).joinToString(" · "))
                    val h = o.arr("history").orEmpty()
                    if (h.size > 1) Secondary(h.map { decisionName(it.o.str("to")) }.joinToString(" → "))
                }
            }
        }
    }

    val sessions = p.arr("sessions").orEmpty()
    Eyebrow(stringResource(R.string.memories_sessions))
    if (sessions.isEmpty()) Secondary(stringResource(R.string.projects_no_sessions))
    sessions.forEach { s -> val o = s.o
        MsCard(Modifier.clickable(role = Role.Button) { o.str("session_id")?.let { vm.openRecap(it) } }) {
            Body(o.str("title") ?: "", size = 15)
            Secondary(listOfNotNull(Dates.date(o.str("created_at")), clock(o.long("source_watermark_ms")), o.str("state")?.let { stateName(it) }).joinToString(" · "))
        }
    }
    p.arr("mocks")?.takeIf { it.isNotEmpty() }?.let { mocks ->
        Eyebrow(stringResource(R.string.interview_recent))
        mocks.forEach { m -> val o = m.o
            MsCard(Modifier.clickable(role = Role.Button) { o.str("mock_id")?.let { vm.loadMock(it); vm.go(Route.Mock(it)) } }) {
                Body("${o.str("topic") ?: ""} · ${o.str("difficulty") ?: ""}", size = 15)
                Secondary(listOfNotNull(humanize(o.str("state")), Dates.date(o.str("created_at"))).joinToString(" · "))
            }
        }
    }
    if (confirmDelete) ConfirmDanger(pluralStringResource(R.plurals.project_delete_confirm, sessions.size, sessions.size), stringResource(R.string.action_delete),
        { confirmDelete = false }) { confirmDelete = false; vm.deleteProject(projectId) }
    else SecondaryButton(stringResource(when (kind) { "COURSE" -> R.string.project_delete_course; "INTERVIEW_GOAL" -> R.string.project_delete_goal; else -> R.string.project_delete_project }), { confirmDelete = true }, Modifier.fillMaxWidth(), danger = true)
}

@Composable
private fun BriefItem(vm: AppViewModel, o: JsonObject) {
    Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { o.str("claim_id")?.let { vm.openMemory(it) } }) {
        androidx.compose.foundation.layout.Column {
            Body("• " + (o.str("text_value") ?: ""), size = 15)
            Secondary(listOfNotNull(humanize(o.str("claim_kind")), o.str("decision_status")?.let { decisionName(it) },
                if (o.str("claim_kind") in setOf("ACTION", "COMMITMENT")) ownerText(o.str("owner_label"), o.bool("owner_confirmed")) else null,
                o.str("session_title"), Dates.date(o.str("session_date"))).joinToString(" · "))
        }
    }
}
