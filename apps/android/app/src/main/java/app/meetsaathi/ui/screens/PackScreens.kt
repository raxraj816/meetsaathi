package app.meetsaathi.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import app.meetsaathi.R
import app.meetsaathi.core.Dates
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.Route
import app.meetsaathi.ui.UiState
import app.meetsaathi.ui.components.Banner
import app.meetsaathi.ui.components.Body
import app.meetsaathi.ui.components.ChoiceChips
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
import app.meetsaathi.ui.components.humanize
import app.meetsaathi.ui.theme.Spacing

/** Learning Study Studio: retrieval practice (answer hidden until attempted) + flexible review plan (no streaks). */
@Composable
fun StudyScreen(vm: AppViewModel, ui: UiState) = Screen {
    LaunchedEffect(Unit) { vm.loadReviews() }
    TopRow(stringResource(R.string.study_eyebrow)) { vm.back() }
    Heading(stringResource(R.string.study_title))
    ui.study?.arr("items")?.forEach { el ->
        val it = el.o
        val id = it.str("item_id") ?: return@forEach
        var answer by remember(id) { mutableStateOf("") }
        MsCard {
            Eyebrow((it.str("concept") ?: stringResource(R.string.study_concept)) + " · " + humanize(it.str("source_kind")))
            Body(it.str("prompt") ?: "")
            OutlinedTextField(answer, { a -> answer = a.take(4000) }, label = { Text(stringResource(R.string.study_answer_hint)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
            SecondaryButton(stringResource(R.string.study_check), { vm.attempt(id, answer) }, enabled = answer.isNotBlank() && !ui.busy)
        }
    }
    ui.lastAttempt?.let { a ->
        MsCard(raised = true) {
            val verdict = a.str("verdict")
            StatusPill(when (verdict) { "CORRECT" -> stringResource(R.string.verdict_correct); "PARTIAL" -> stringResource(R.string.verdict_partial)
                "INCORRECT" -> stringResource(R.string.verdict_incorrect); else -> humanize(verdict) },
                when (verdict) { "CORRECT" -> Tone.Accent; "PARTIAL" -> Tone.Caution; "INCORRECT" -> Tone.Danger; else -> Tone.Neutral })
            Body(a.str("feedback") ?: "", size = 15)
            a.str("key_points")?.let { Secondary(stringResource(R.string.study_key_points, it)) }
            a.str("note")?.let { Secondary(it) }
        }
    }
    Eyebrow(stringResource(R.string.study_review_plan))
    val reviews = ui.reviews
    if (reviews.isNullOrEmpty()) Secondary(stringResource(R.string.study_review_empty))
    reviews?.forEach { el ->
        val r = el.o
        val key = r.str("concept_key") ?: return@forEach
        val space = r.str("space_id") ?: return@forEach
        MsCard {
            Body(r.str("concept") ?: key)
            Secondary(listOfNotNull(humanize(r.str("lineage_state")), stringResource(R.string.study_next_review, Dates.date(r.str("due_at")) ?: ""),
                if (r.bool("due")) stringResource(R.string.study_due_now) else null).joinToString(" · "))
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                SecondaryButton(stringResource(R.string.study_snooze), { vm.reviewAction(space, key, "SNOOZE", 1) }, Modifier.weight(1f))
                SecondaryButton(stringResource(R.string.action_remove), { vm.reviewAction(space, key, "REMOVE", null) }, Modifier.weight(1f))
            }
        }
    }
}

private val MOCK_TOPICS = listOf("System Design" to R.string.preset_system_design, "Behavioral" to R.string.preset_behavioral,
    "Coding" to R.string.preset_coding, "AI / ML" to R.string.preset_ai_ml, "Cloud Architecture" to R.string.preset_cloud_architecture,
    "Product" to R.string.preset_product)
private val DIFFICULTIES = listOf("Warmup" to R.string.difficulty_warmup, "Challenging" to R.string.difficulty_challenging, "Expert" to R.string.difficulty_expert)

/** Interview home: goals (with job description) + practice (always available, no third-party permission needed). */
@Composable
fun InterviewScreen(vm: AppViewModel, ui: UiState) = Screen {
    var topic by remember { mutableStateOf("System Design") }
    var difficulty by remember { mutableStateOf("Challenging") }
    var goal by remember { mutableStateOf<String?>(null) }
    var creating by remember { mutableStateOf(false) }
    TopRow(stringResource(R.string.interview_eyebrow)) { vm.back() }
    Heading(stringResource(R.string.interview_title))
    Secondary(stringResource(R.string.interview_note))
    MsCard {
        Title(stringResource(R.string.interview_goal))
        ui.goals?.takeIf { it.isNotEmpty() }?.let { g ->
            ChoiceChips(g.map { (it.o.str("project_id") ?: "") to (it.o.str("title") ?: "") }, goal, { goal = if (goal == it) null else it })
            goal?.let { id -> LinkButton(stringResource(R.string.interview_open_goal)) { vm.openProject(id) } }
        }
        if (creating) {
            ProjectForm("INTERVIEW_GOAL", "", null, stringResource(R.string.interview_save_goal), ui.busy) { title, meta ->
                vm.createProject("INTERVIEW_GOAL", title, meta); creating = false }
            LinkButton(stringResource(R.string.action_cancel)) { creating = false }
        } else LinkButton(stringResource(R.string.interview_new_goal)) { creating = true }
    }
    MsCard {
        Title(stringResource(R.string.interview_setup))
        ChoiceChips(MOCK_TOPICS.map { it.first to stringResource(it.second) }, topic, { topic = it })
        ChoiceChips(DIFFICULTIES.map { it.first to stringResource(it.second) }, difficulty, { difficulty = it })
        Secondary(stringResource(R.string.interview_setup_note))
        PrimaryButton(stringResource(R.string.interview_start_mock), { vm.startMock(topic, difficulty, goal) }, enabled = !ui.busy)
        SecondaryButton(stringResource(R.string.interview_warmup), { vm.startMock(topic, "Warmup", goal, 3) }, Modifier.fillMaxWidth(), enabled = !ui.busy)
        Secondary(stringResource(R.string.interview_warmup_note))
    }
    ui.mocks?.takeIf { it.isNotEmpty() }?.let { mocks ->
        Eyebrow(stringResource(R.string.interview_recent))
        mocks.take(8).forEach { m ->
            val o = m.o
            MsCard(Modifier.clickable(role = Role.Button) { o.str("mock_id")?.let { vm.loadMock(it); vm.go(Route.Mock(it)) } }) {
                Body("${o.str("topic") ?: ""} · ${o.str("difficulty") ?: ""}")
                Secondary(listOfNotNull(humanize(o.str("state")), Dates.date(o.str("created_at")),
                    if (o.str("parent_mock_id") != null) stringResource(R.string.mock_retry_label) else null).joinToString(" · "))
            }
        }
    }
}

@Composable
fun MockScreen(vm: AppViewModel, ui: UiState, mockId: String) = Screen {
    var answer by remember { mutableStateOf("") }
    val m = ui.mock?.takeIf { it.obj("mock")?.str("mock_id") == mockId }
    TopRow(stringResource(R.string.mock_eyebrow)) { vm.back() }
    if (m == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    m.obj("mock")?.obj("settings")?.str("focus")?.let { Banner(stringResource(R.string.mock_focus, it), Tone.Accent) }
    m.arr("turns").orEmpty().forEach { el ->
        val t = el.o
        when (t.str("role")) {
            "INTERVIEWER" -> MsCard(raised = true) {
                Eyebrow(stringResource(if (t.str("kind") == "FOLLOWUP") R.string.mock_followup else R.string.mock_question)); Body(t.str("text_value") ?: "") }
            "CANDIDATE" -> MsCard { Eyebrow(stringResource(R.string.mock_your_answer)); Body(t.str("text_value") ?: "", size = 15) }
            else -> Secondary((if (t.str("kind") == "HINT") stringResource(R.string.mock_hint_prefix) + " " else "") + (t.str("text_value") ?: ""))
        }
    }
    val debrief = m.obj("debrief")
    val finished = m.obj("mock")?.str("state") == "FINISHED"
    if (debrief != null) {
        if (debrief.str("status") == "READY") {
            MsCard(raised = true) {
                Eyebrow(stringResource(R.string.mock_debrief) + " · " + (debrief.str("evidence_level") ?: ""))
                Title(stringResource(R.string.mock_strengths)); debrief.arr("strengths")?.forEach { Secondary("✓ " + it.text) }
                Title(stringResource(R.string.mock_improve)); debrief.arr("improvements")?.forEach { Secondary("▲ " + it.text) }
                debrief.arr("dimensions")?.forEach { d -> val o = d.o
                    Eyebrow(o.str("name") ?: "")
                    Body(o.str("observation") ?: "", size = 15)
                    o.str("repair")?.let { Secondary(stringResource(R.string.mock_try, it)) }
                    o.arr("evidence")?.forEach { e -> Secondary("“" + (e.o.str("excerpt") ?: "") + "”") }
                }
                debrief.arr("uncertain_claims")?.takeIf { it.isNotEmpty() }?.let { u ->
                    Title(stringResource(R.string.mock_check_claims)); u.forEach { Secondary("? " + it.text) }
                }
                Secondary(debrief.str("disclaimer") ?: "")
            }
            val drills = (debrief.arr("next_drills").orEmpty() + debrief.arr("improvements").orEmpty()).map { it.text }.filter { it.isNotBlank() }.distinct().take(4)
            if (drills.isNotEmpty()) MsCard {
                Title(stringResource(R.string.mock_retry_title))
                Secondary(stringResource(R.string.mock_retry_note))
                drills.forEach { d -> SecondaryButton(d, { vm.retrySkill(mockId, d) }, Modifier.fillMaxWidth(), enabled = !ui.busy) }
            }
        } else {
            Banner(debrief.str("message") ?: stringResource(R.string.mock_feedback_unavailable), Tone.Caution)
            if (debrief.str("status") == "UNAVAILABLE") SecondaryButton(stringResource(R.string.mock_feedback_retry), { vm.requestDebrief(mockId) }, Modifier.fillMaxWidth(), enabled = !ui.busy)
        }
        return@Screen
    }
    if (finished) {
        SecondaryButton(stringResource(R.string.mock_get_feedback), { vm.requestDebrief(mockId) }, Modifier.fillMaxWidth(), enabled = !ui.busy)
        return@Screen
    }
    OutlinedTextField(answer, { answer = it.take(12000) }, label = { Text(stringResource(R.string.mock_answer_hint)) }, modifier = Modifier.fillMaxWidth(), minLines = 4)
    PrimaryButton(stringResource(R.string.mock_submit), { vm.mockAction(mockId, "ANSWER", answer); answer = "" }, enabled = answer.isNotBlank() && !ui.busy)
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        SecondaryButton(stringResource(R.string.mock_need_time), { vm.mockAction(mockId, "NEED_TIME", null) }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.mock_repeat), { vm.mockAction(mockId, "REPEAT", null) }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.mock_hint), { vm.mockAction(mockId, "HINT", null) }, Modifier.weight(1f))
    }
    SecondaryButton(stringResource(R.string.mock_finish), { vm.mockAction(mockId, "FINISH", null) }, Modifier.fillMaxWidth())
}

/** J1 step 1: explicitly labelled FICTIONAL sample — no microphone, no account, no AI calls. */
@Composable
fun SampleScreen(vm: AppViewModel) = Screen {
    var step by remember { mutableStateOf(0) }
    TopRow(stringResource(R.string.sample_eyebrow)) { vm.back() }
    Banner(stringResource(R.string.sample_banner), Tone.Caution)
    when (step) {
        0 -> {
            Heading(stringResource(R.string.sample_title))
            StatusPill(stringResource(R.string.sample_not_recording), Tone.Neutral)
            MsCard { Eyebrow(stringResource(R.string.live_latest)); Secondary(stringResource(R.string.sample_line_meta)); Body(stringResource(R.string.sample_line)) }
            MsCard(raised = true) {
                Eyebrow(stringResource(R.string.sample_insight_eyebrow))
                Body(stringResource(R.string.sample_insight), size = 17)
                Secondary(stringResource(R.string.sample_insight_why))
            }
            PrimaryButton(stringResource(R.string.sample_next_ask), { step = 1 })
        }
        1 -> {
            Heading(stringResource(R.string.ask_eyebrow))
            MsCard { Eyebrow(stringResource(R.string.sample_you_asked)); Body(stringResource(R.string.sample_question)) }
            MsCard(raised = true) { Eyebrow(stringResource(R.string.sample_answer_eyebrow)); Body(stringResource(R.string.sample_answer)); Secondary("▶ 18:42 · ▶ 23:15") }
            MsCard { Eyebrow(stringResource(R.string.prov_ai_analysis)); Body(stringResource(R.string.sample_analysis)) }
            PrimaryButton(stringResource(R.string.sample_next_recap), { step = 2 })
        }
        else -> {
            Heading(stringResource(R.string.sample_recap_title))
            MsCard { Eyebrow(stringResource(R.string.sec_decisions)); Body(stringResource(R.string.sample_decision)) }
            MsCard { Eyebrow(stringResource(R.string.sec_open_questions)); Body(stringResource(R.string.sample_open)) }
            Secondary(stringResource(R.string.sample_choose_note))
            PrimaryButton(stringResource(R.string.welcome_get_started), { vm.go(Route.Auth) })
        }
    }
}
