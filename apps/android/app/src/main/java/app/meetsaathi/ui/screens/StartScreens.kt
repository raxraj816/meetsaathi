package app.meetsaathi.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.sp
import app.meetsaathi.R
import app.meetsaathi.core.LiveUiState
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.Draft
import app.meetsaathi.ui.Route
import app.meetsaathi.ui.UiState
import app.meetsaathi.ui.components.Banner
import app.meetsaathi.ui.components.Body
import app.meetsaathi.ui.components.CheckRow
import app.meetsaathi.ui.components.ChoiceChips
import app.meetsaathi.ui.components.Eyebrow
import app.meetsaathi.ui.components.Gap
import app.meetsaathi.ui.components.Heading
import app.meetsaathi.ui.components.LinkButton
import app.meetsaathi.ui.components.MsCard
import app.meetsaathi.ui.components.PrimaryButton
import app.meetsaathi.ui.components.Secondary
import app.meetsaathi.ui.components.SecondaryButton
import app.meetsaathi.ui.components.StatusPill
import app.meetsaathi.ui.components.Title
import app.meetsaathi.ui.components.Tone
import app.meetsaathi.ui.components.clock
import app.meetsaathi.ui.theme.LocalMs
import app.meetsaathi.ui.theme.Spacing

@Composable
fun Screen(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = Spacing.l, vertical = Spacing.m),
        verticalArrangement = Arrangement.spacedBy(Spacing.s)) { content() }
}

@Composable
fun contextName(ctx: String): String = stringResource(when (ctx) {
    "LEARNING" -> R.string.ctx_learning; "INTERVIEW" -> R.string.ctx_interview; "CONVERSATION" -> R.string.ctx_conversation; else -> R.string.ctx_meeting
})

/** Presets are wire identifiers shared with backend policy (app/domain/policy.py); only their labels are localized. */
val PRESETS = mapOf(
    "MEETING" to listOf("Architecture review", "Team standup", "Customer discussion", "Strategy meeting", "Sales discovery", "Other"),
    "LEARNING" to listOf("Lecture", "Tutorial", "Seminar", "Workshop", "Talk/Seminar (research)", "Study group"),
    "INTERVIEW" to listOf("System design", "Behavioral", "Coding", "AI / ML", "Cloud architecture", "Product"),
    "CONVERSATION" to listOf("Mentoring", "Networking", "Language exchange", "Everyday conversation", "Brainstorming",
        "Trusted family discussion", "Personal coaching", "Medical consultation", "Legal consultation", "Financial consultation"),
)
val SENSITIVE_PRESETS = setOf("Trusted family discussion", "Personal coaching", "Medical consultation", "Legal consultation", "Financial consultation")

@StringRes fun presetRes(p: String): Int = when (p) {
    "Architecture review" -> R.string.preset_architecture_review; "Team standup" -> R.string.preset_team_standup
    "Customer discussion" -> R.string.preset_customer_discussion; "Strategy meeting" -> R.string.preset_strategy_meeting
    "Sales discovery" -> R.string.preset_sales_discovery; "Other" -> R.string.preset_other
    "Lecture" -> R.string.preset_lecture; "Tutorial" -> R.string.preset_tutorial; "Seminar" -> R.string.preset_seminar
    "Workshop" -> R.string.preset_workshop; "Talk/Seminar (research)" -> R.string.preset_research_talk; "Study group" -> R.string.preset_study_group
    "System design" -> R.string.preset_system_design; "Behavioral" -> R.string.preset_behavioral; "Coding" -> R.string.preset_coding
    "AI / ML" -> R.string.preset_ai_ml; "Cloud architecture" -> R.string.preset_cloud_architecture; "Product" -> R.string.preset_product
    "Mentoring" -> R.string.preset_mentoring; "Networking" -> R.string.preset_networking; "Language exchange" -> R.string.preset_language_exchange
    "Everyday conversation" -> R.string.preset_everyday; "Brainstorming" -> R.string.preset_brainstorming
    "Trusted family discussion" -> R.string.preset_family; "Personal coaching" -> R.string.preset_coaching
    "Medical consultation" -> R.string.preset_medical; "Legal consultation" -> R.string.preset_legal
    else -> R.string.preset_financial
}

/** U01: one-sentence promise, demo without permissions, privacy explanation. No microphone request here. */
@Composable
fun WelcomeScreen(vm: AppViewModel) = Screen {
    Gap(24)
    Eyebrow(stringResource(R.string.app_name))
    Heading(stringResource(R.string.welcome_promise))
    Body(stringResource(R.string.welcome_sub))
    MsCard {
        Title(stringResource(R.string.welcome_listens_title))
        Secondary(stringResource(R.string.welcome_listens_body))
        Title(stringResource(R.string.welcome_helps_title))
        Secondary(stringResource(R.string.welcome_helps_body))
        Title(stringResource(R.string.welcome_stop_title))
        Secondary(stringResource(R.string.welcome_stop_body))
    }
    PrimaryButton(stringResource(R.string.welcome_get_started), { vm.go(Route.Auth) })
    SecondaryButton(stringResource(R.string.welcome_sample), { vm.go(Route.Sample) }, Modifier.fillMaxWidth())
}

@Composable
fun AuthScreen(vm: AppViewModel, ui: UiState) = Screen {
    var create by remember { mutableStateOf(true) }
    var email by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    Heading(stringResource(if (create) R.string.auth_create_title else R.string.auth_signin_title))
    ChoiceChips(listOf("new" to stringResource(R.string.auth_new), "existing" to stringResource(R.string.auth_existing)),
        if (create) "new" else "existing", { create = it == "new" })
    if (create) OutlinedTextField(name, { name = it.take(80) }, label = { Text(stringResource(R.string.auth_name)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    OutlinedTextField(email, { email = it.take(254) }, label = { Text(stringResource(R.string.auth_email)) }, modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), singleLine = true)
    OutlinedTextField(pw, { pw = it.take(256) }, label = { Text(stringResource(R.string.auth_password)) }, modifier = Modifier.fillMaxWidth(),
        visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), singleLine = true)
    var adult by remember { mutableStateOf(false) }
    if (create) {
        CheckRow(adult, stringResource(R.string.auth_age_confirm)) { adult = it }
        Secondary(stringResource(R.string.auth_age_note))
    }
    Secondary(stringResource(R.string.auth_privacy))
    PrimaryButton(stringResource(if (create) R.string.auth_create else R.string.auth_signin), { vm.signIn(email, pw, create, name, adult) },
        enabled = email.contains("@") && pw.length >= 10 && (!create || adult) && !ui.busy)
    LinkButton(stringResource(R.string.action_back)) { vm.back() }
}

/** U02 Home: Start Companion dominates; readiness; active-session bar; recent memory. No analytics dashboard. */
@Composable
fun HomeScreen(vm: AppViewModel, ui: UiState, live: LiveUiState) = Screen {
    val t = LocalMs.current
    Eyebrow(stringResource(R.string.home_eyebrow))
    Heading(stringResource(R.string.home_title))
    Secondary(stringResource(R.string.home_sub))
    MsCard(raised = true) {
        Title(stringResource(R.string.home_start_title))
        val input = live.route?.input?.replace('_', ' ')?.lowercase() ?: stringResource(R.string.home_phone_mic)
        val output = stringResource(when (vm.pref("default_output")) { "PRIVATE_VOICE" -> R.string.output_private_voice; "BOTH" -> R.string.output_both; else -> R.string.output_silent_text })
        Secondary(stringResource(R.string.home_readiness, input, output))
        PrimaryButton(stringResource(R.string.home_start), { vm.go(Route.ContextChooser) })
        vm.pref("last_context")?.let { last ->
            LinkButton(stringResource(R.string.home_start_again, contextName(last))) { vm.chooseContext(last, null) }
        }
    }
    ui.active.forEach { s ->
        MsCard {
            StatusPill(stringResource(R.string.home_active, stateName(s.state)), Tone.Accent)
            Body(s.title)
            SecondaryButton(stringResource(R.string.action_return_to_session), { vm.openActive(s.sessionId) })
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        SecondaryButton(stringResource(R.string.home_interview_practice), { vm.loadInterview(); vm.go(Route.Interview) }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.home_study), { vm.loadReviews(); vm.go(Route.Study) }, Modifier.weight(1f))
    }
    if (ui.recent.isNotEmpty()) {
        Eyebrow(stringResource(R.string.home_recent))
        ui.recent.forEach { s ->
            MsCard(Modifier.clickable(role = Role.Button) { vm.openRecap(s.sessionId) }) {
                Text(s.title, color = t.text, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Secondary(sessionMeta(s.context, s.sourceWatermarkMs, s.decisions, s.openItems))
            }
        }
        LinkButton(stringResource(R.string.home_all_sessions)) { vm.loadSessions(true); vm.go(Route.Sessions) }
    } else {
        Secondary(stringResource(R.string.home_empty))
    }
}

@Composable
fun sessionMeta(ctx: String, durationMs: Long, decisions: Int, open: Int): String {
    return listOf(contextName(ctx), clock(durationMs), pluralStringResource(R.plurals.decisions_count, decisions, decisions),
        pluralStringResource(R.plurals.open_count, open, open)).joinToString(" · ")
}

@Composable
fun stateName(state: String): String = stringResource(when (state) {
    "PREFLIGHT" -> R.string.state_preflight; "NOTES_ONLY" -> R.string.state_notes_only; "STARTING" -> R.string.state_starting
    "RECORDING" -> R.string.state_recording; "PAUSED" -> R.string.state_paused; "INTERRUPTED" -> R.string.state_interrupted
    "STOPPING", "FINALIZING" -> R.string.state_finalizing; "FINALIZATION_RETRYABLE" -> R.string.state_retryable
    "COMPLETED" -> R.string.state_completed; "COMPLETED_PARTIAL" -> R.string.state_completed_partial
    "DELETING", "DELETED" -> R.string.state_deleting; else -> R.string.state_error
})

private data class Ctx(val id: String, @StringRes val sub: Int)
private val CONTEXTS = listOf(Ctx("MEETING", R.string.ctx_meeting_sub), Ctx("LEARNING", R.string.ctx_learning_sub),
    Ctx("INTERVIEW", R.string.ctx_interview_sub), Ctx("CONVERSATION", R.string.ctx_conversation_sub))

/** U03: four context cards, optional presets; remembers the last choice. Context changes suggestions, never permissions (CON-003). */
@Composable
fun ContextChooserScreen(vm: AppViewModel) = Screen {
    var ctx by remember { mutableStateOf(vm.pref("last_context") ?: "MEETING") }
    var preset by remember { mutableStateOf<String?>(null) }
    val t = LocalMs.current
    Eyebrow(stringResource(R.string.home_start))
    Heading(stringResource(R.string.chooser_title))
    CONTEXTS.forEach { c ->
        val on = ctx == c.id
        MsCard(Modifier.semantics { selected = on }.clickable(role = Role.RadioButton) { ctx = c.id; preset = null }, raised = on) {
            Text((if (on) "✓ " else "") + contextName(c.id), color = t.text, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Secondary(stringResource(c.sub))
        }
    }
    Eyebrow(stringResource(R.string.chooser_preset))
    ChoiceChips(PRESETS.getValue(ctx).map { it to stringResource(presetRes(it)) }, preset, { preset = if (preset == it) null else it })
    if (ctx == "INTERVIEW") LinkButton(stringResource(R.string.chooser_mock_instead)) { vm.loadInterview(); vm.go(Route.Interview) }
    PrimaryButton(stringResource(R.string.action_continue), { vm.chooseContext(ctx, preset) })
    LinkButton(stringResource(R.string.action_cancel)) { vm.back() }
}

private fun projectKindFor(ctx: String) = when (ctx) { "LEARNING" -> "COURSE"; "INTERVIEW" -> "INTERVIEW_GOAL"; else -> "PROJECT" }

/** U04 Preflight: every hard gate is visible and resolvable; no start on an unresolved gate. */
@Composable
fun PreflightScreen(vm: AppViewModel, ui: UiState, live: LiveUiState) = Screen {
    val d = ui.draft
    val micGranted = vm.live.micGranted()
    var micAsked by remember { mutableStateOf(false) }
    val askMic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { micAsked = true; vm.runPreflight() }
    val askNotif = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    fun upd(f: (Draft) -> Draft) = vm.updateDraft(f)
    val yes = stringResource(R.string.answer_yes_permitted)
    val no = stringResource(R.string.answer_no_not_sure)

    Eyebrow(stringResource(R.string.preflight_eyebrow))
    Heading(stringResource(R.string.preflight_title, contextName(d.context)))
    OutlinedTextField(d.title, { v -> upd { it.copy(title = v.take(160)) } }, label = { Text(stringResource(R.string.preflight_session_title)) },
        modifier = Modifier.fillMaxWidth(), singleLine = true)

    ProjectPicker(vm, ui, projectKindFor(d.context), d.projectId) { id -> upd { it.copy(projectId = id) } }

    if (d.context == "INTERVIEW") {
        MsCard {
            Title(stringResource(R.string.interview_rules_title))
            Secondary(stringResource(R.string.interview_rules_sub))
            Body(stringResource(R.string.interview_may_record), size = 15)
            ChoiceChips(listOf("yes" to yes, "no" to no), d.recordingAllowed?.let { if (it) "yes" else "no" },
                { v -> upd { it.copy(recordingAllowed = v == "yes", captureSource = if (v == "yes") "PHONE_MIC" else "NONE") } })
            Body(stringResource(R.string.interview_ai_permitted), size = 15)
            ChoiceChips(listOf("yes" to yes, "no" to no), d.aiAllowed?.let { if (it) "yes" else "no" },
                { v -> upd { it.copy(aiAllowed = v == "yes", assistance = if (v == "yes") it.assistance else "LISTENER") } })
            if (d.recordingAllowed == false) Banner(stringResource(R.string.interview_no_recording), Tone.Caution)
            if (d.aiAllowed == false) Banner(stringResource(R.string.interview_no_ai), Tone.Caution)
        }
    }

    if (d.preset in SENSITIVE_PRESETS) {
        MsCard {
            Title(stringResource(R.string.sensitive_title))
            Secondary(stringResource(R.string.sensitive_body))
            if (d.assistance == "COMPANION") CheckRow(d.sensitiveOptIn, stringResource(R.string.sensitive_opt_in)) { v -> upd { it.copy(sensitiveOptIn = v) } }
        }
    }

    MsCard {
        Title(stringResource(R.string.preflight_audio_source))
        ChoiceChips(listOf("PHONE_MIC" to stringResource(R.string.source_phone_mic), "NONE" to stringResource(R.string.source_notes_only)), d.captureSource,
            { v -> upd { it.copy(captureSource = v) } }, enabled = { it == "NONE" || d.context != "INTERVIEW" || d.recordingAllowed == true })
        if (d.captureSource == "NONE") {
            Secondary(stringResource(R.string.copy_notes_only))
        } else if (!micGranted) {
            StatusPill(stringResource(R.string.truth_mic_denied), Tone.Danger)
            Secondary(stringResource(R.string.preflight_mic_why))
            PrimaryButton(stringResource(R.string.preflight_enable_mic), { askMic.launch(Manifest.permission.RECORD_AUDIO) })
            if (micAsked) {
                Secondary(stringResource(R.string.preflight_mic_declined))
                val ctx = androidx.compose.ui.platform.LocalContext.current
                SecondaryButton(stringResource(R.string.preflight_open_settings), {
                    ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        android.net.Uri.fromParts("package", ctx.packageName, null)))
                }, Modifier.fillMaxWidth())
            }
        } else {
            val p = ui.preflight
            when {
                ui.preflightRunning -> StatusPill(stringResource(R.string.preflight_checking), Tone.Neutral)
                p == null -> SecondaryButton(stringResource(R.string.preflight_check_audio), {
                    vm.runPreflight(); if (android.os.Build.VERSION.SDK_INT >= 33) askNotif.launch(Manifest.permission.POST_NOTIFICATIONS) })
                else -> {
                    val quality = when (p.quality) { "GOOD" -> stringResource(R.string.quality_good); "POOR" -> stringResource(R.string.quality_poor)
                        "SILENT_OR_BLOCKED" -> stringResource(R.string.quality_silent); else -> stringResource(R.string.quality_no_frames) }
                    StatusPill(stringResource(R.string.preflight_input_result, p.route.input.replace('_', ' ').lowercase(), quality) +
                        (p.levelDbfs?.let { " (%.0f dBFS)".format(it) } ?: ""), if (p.quality == "GOOD") Tone.Accent else Tone.Caution)
                    p.warnings.forEach { Secondary("• $it") }
                    LinkButton(stringResource(R.string.preflight_check_again)) { vm.runPreflight() }
                }
            }
        }
    }

    if (d.captureSource != "NONE") {
        MsCard {
            Title(stringResource(R.string.preflight_permission_title))
            CheckRow(d.participantsInformed, stringResource(R.string.preflight_permission_check)) { v -> upd { it.copy(participantsInformed = v) } }
            Secondary(stringResource(R.string.preflight_permission_note))
            if (d.context != "INTERVIEW") {
                CheckRow(d.aiConsent, stringResource(R.string.preflight_ai_check)) { allowed ->
                    upd { it.copy(aiConsent = allowed, assistance = if (allowed) it.assistance else "LISTENER", intensity = if (allowed) it.intensity else "QUIET") }
                }
                Secondary(stringResource(R.string.preflight_ai_note))
            }
        }
        MsCard {
            Title(stringResource(R.string.preflight_help_title))
            val aiOk = if (d.context == "INTERVIEW") d.aiAllowed == true else d.aiConsent
            AssistanceChips(d.assistance, aiOk) { v -> upd { it.copy(assistance = v, intensity = if (v == "COMPANION" && it.intensity == "QUIET") "BALANCED" else it.intensity) } }
            if (d.assistance == "COMPANION") {
                IntensityChips(d.intensity) { v -> upd { it.copy(intensity = v) } }
                Secondary(stringResource(R.string.intensity_balanced_note))
            }
            Body(stringResource(R.string.preflight_delivery), size = 15)
            OutputChips(d.output, { true }) { v -> upd { it.copy(output = v) } }
            if (d.output != "TEXT") {
                if (live.privateRouteVerified) StatusPill(stringResource(R.string.voice_verified_device, live.route?.outputDeviceName ?: stringResource(R.string.voice_earbuds)), Tone.Accent)
                else SecondaryButton(stringResource(R.string.voice_test_earbuds), { vm.go(Route.Voice) })
            }
        }
        MsCard {
            Title(stringResource(R.string.preflight_processing_title))
            Secondary(stringResource(R.string.preflight_processing_body))
        }
    }
    val blockers = vm.startBlockers(d, micGranted)
    blockers.forEach { Secondary("• " + stringResource(it.text)) }
    Secondary(stringResource(R.string.copy_consent_line))
    PrimaryButton(stringResource(if (d.captureSource == "NONE") R.string.preflight_open_notes else R.string.preflight_start), { vm.startSession() },
        enabled = blockers.isEmpty() && !ui.busy)
    LinkButton(stringResource(R.string.action_back)) { vm.back() }
}

@Composable
fun AssistanceChips(selected: String, aiOk: Boolean, onSelect: (String) -> Unit) =
    ChoiceChips(listOf("LISTENER" to stringResource(R.string.assist_listener), "ASK" to stringResource(R.string.assist_ask),
        "COMPANION" to stringResource(R.string.assist_companion)), selected, onSelect, enabled = { it == "LISTENER" || aiOk })

@Composable
fun IntensityChips(selected: String, onSelect: (String) -> Unit) =
    ChoiceChips(listOf("QUIET" to stringResource(R.string.intensity_quiet), "BALANCED" to stringResource(R.string.intensity_balanced),
        "ACTIVE" to stringResource(R.string.intensity_active)), selected, onSelect)

@Composable
fun OutputChips(selected: String, enabled: (String) -> Boolean, onSelect: (String) -> Unit) =
    ChoiceChips(listOf("TEXT" to stringResource(R.string.output_text), "PRIVATE_VOICE" to stringResource(R.string.output_private_voice),
        "BOTH" to stringResource(R.string.output_both)), selected, onSelect, enabled = enabled)

@Composable
fun projectKindName(kind: String): String = stringResource(when (kind) { "COURSE" -> R.string.kind_course; "INTERVIEW_GOAL" -> R.string.kind_goal; else -> R.string.kind_project })

/** Optional grouping: a project (Meeting), a course (Learning) or an interview goal. Scopes briefs, decisions and Ask. */
@Composable
fun ProjectPicker(vm: AppViewModel, ui: UiState, kind: String, selected: String?, onSelect: (String?) -> Unit) {
    var creating by remember { mutableStateOf(false) }
    var title by remember { mutableStateOf("") }
    // Only groupings in the session's own space: Personal and Work never mix.
    val options = ui.projects.orEmpty().map { it.o }.filter { it.str("kind") == kind && it.str("space_id") == ui.draft.spaceId }
    MsCard {
        Title(stringResource(R.string.picker_title, projectKindName(kind)))
        Secondary(stringResource(when (kind) { "COURSE" -> R.string.picker_course_note; "INTERVIEW_GOAL" -> R.string.picker_goal_note; else -> R.string.picker_project_note }))
        ChoiceChips(listOf("" to stringResource(R.string.picker_none)) + options.map { (it.str("project_id") ?: "") to (it.str("title") ?: "") },
            selected ?: "", { onSelect(it.ifBlank { null }) })
        if (creating) {
            OutlinedTextField(title, { title = it.take(160) }, label = { Text(stringResource(R.string.picker_new_name, projectKindName(kind))) },
                modifier = Modifier.fillMaxWidth(), singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                SecondaryButton(stringResource(R.string.action_cancel), { creating = false; title = "" }, Modifier.weight(1f))
                SecondaryButton(stringResource(R.string.action_create), { vm.createProject(kind, title, emptyMap(), attachToDraft = true); creating = false; title = "" },
                    Modifier.weight(1f), enabled = title.isNotBlank())
            }
        } else LinkButton(stringResource(R.string.picker_new, projectKindName(kind))) { creating = true }
    }
}
