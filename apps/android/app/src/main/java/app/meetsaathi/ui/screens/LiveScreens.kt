package app.meetsaathi.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.meetsaathi.R
import app.meetsaathi.core.Dates
import app.meetsaathi.core.AskResponse
import app.meetsaathi.core.CaptureTruth
import app.meetsaathi.core.LiveUiState
import app.meetsaathi.core.SessionState
import app.meetsaathi.core.phrase
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.Route
import app.meetsaathi.ui.Tab
import app.meetsaathi.ui.UiState
import app.meetsaathi.ui.components.Banner
import app.meetsaathi.ui.components.Body
import app.meetsaathi.ui.components.ChoiceChips
import app.meetsaathi.ui.components.CitationChips
import app.meetsaathi.ui.components.ConfirmDanger
import app.meetsaathi.ui.components.EvidenceButton
import app.meetsaathi.ui.components.Eyebrow
import app.meetsaathi.ui.components.Gap
import app.meetsaathi.ui.components.Heading
import app.meetsaathi.ui.components.GapBanner
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
import app.meetsaathi.ui.components.provenanceTitle
import app.meetsaathi.ui.components.speakerName
import app.meetsaathi.ui.theme.LocalMs
import app.meetsaathi.ui.theme.Spacing
import kotlinx.serialization.json.JsonObject

fun toneFor(t: CaptureTruth) = when (t) {
    CaptureTruth.RECORDING -> Tone.Accent
    CaptureTruth.RECORDING_LOCAL, CaptureTruth.STARTING, CaptureTruth.PAUSED -> Tone.Caution
    CaptureTruth.INTERRUPTED, CaptureTruth.MIC_DENIED -> Tone.Danger
    else -> Tone.Neutral
}

/**
 * U05 Live Focus. Fixed header (capture truth, timer, route), topic/last line, ONE insight or "Listening quietly",
 * collapsed transcript, Ask, and persistent Save / Pause / End controls that never move when cards arrive.
 */
@Composable
fun LiveScreen(vm: AppViewModel, ui: UiState, live: LiveUiState) {
    val t = LocalMs.current
    val s = live.session ?: run {
        Screen { Body(stringResource(R.string.live_no_session)); LinkButton(stringResource(R.string.tab_home)) { vm.tab(Tab.Home) } }
        return
    }
    val state = SessionState.parse(s.state)
    val notesOnly = s.captureSource == "NONE"
    var showCaptions by remember { mutableStateOf(false) }
    var showOptions by remember { mutableStateOf(false) }
    var confirmEnd by remember { mutableStateOf(false) }
    var confirmWithdraw by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var noting by remember { mutableStateOf(false) }
    val large = vm.prefBool("captions_large")
    val capturing = state == SessionState.RECORDING || state == SessionState.STARTING || state == SessionState.PAUSED || state == SessionState.INTERRUPTED
    val stopped = !notesOnly && (state in app.meetsaathi.core.SessionStateMachine.ended || live.truth == CaptureTruth.STOPPED)

    Column(Modifier.fillMaxSize()) {
        // Sticky header: state is words + glyph, never colour alone; End is always reachable.
        Column(Modifier.fillMaxWidth().background(t.surface).padding(Spacing.l), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("${contextName(s.context)} · ${clock(live.elapsedMs)}", color = t.secondary, fontSize = 14.sp)
                StatusPill(stringResource(live.truth.labelRes), toneFor(live.truth))
            }
            Text(s.title, color = t.text, fontWeight = FontWeight.Bold, fontSize = 20.sp)
            val route = live.route
            val output = if (s.outputMode != "TEXT" && live.privateRouteVerified)
                stringResource(R.string.live_output_private, route?.outputDeviceName ?: stringResource(R.string.voice_earbuds))
            else stringResource(R.string.output_silent_text)
            Secondary(stringResource(R.string.live_route_line, route?.input?.replace('_', ' ')?.lowercase() ?: stringResource(R.string.label_none), output))
            if (!live.online) Banner(stringResource(R.string.live_offline), Tone.Caution)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = Spacing.l), verticalArrangement = Arrangement.spacedBy(Spacing.s)) {
            Gap(4)
            live.status?.let { StatusBanner(it, live.statusSeverity) }
            if (live.withdrawPending) {
                MsCard { Body(stringResource(R.string.status_withdraw_pending)); PrimaryButton(stringResource(R.string.action_retry), { vm.withdrawConsent() }) }
            }
            if (state == SessionState.INTERRUPTED && !live.withdrawPending) {
                MsCard { Body(stringResource(R.string.live_interrupted)); PrimaryButton(stringResource(R.string.action_resume), { vm.resume() }) }
            }
            if (stopped) {
                MsCard {
                    Body(stringResource(R.string.live_after_stop_note))
                    OutlinedTextField(note, { note = it.take(8000) }, label = { Text(stringResource(R.string.live_note_hint)) }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                    SecondaryButton(stringResource(R.string.live_save_note), { vm.addNote(note, false); note = "" }, Modifier.fillMaxWidth(), enabled = note.isNotBlank())
                }
            } else if (notesOnly) {
                MsCard {
                    Body(stringResource(R.string.copy_notes_only))
                    OutlinedTextField(note, { note = it.take(8000) }, label = { Text(stringResource(R.string.live_note_hint)) }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                    Secondary(stringResource(R.string.live_note_own_words))
                    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                        SecondaryButton(stringResource(R.string.live_save_note), { vm.addNote(note, false); note = "" }, Modifier.weight(1f), enabled = note.isNotBlank())
                        SecondaryButton(stringResource(R.string.live_save_recollection), { vm.addNote(note, true); note = "" }, Modifier.weight(1f), enabled = note.isNotBlank())
                    }
                }
            } else {
                val last = live.transcript.lastOrNull()
                MsCard {
                    Eyebrow(stringResource(R.string.live_latest))
                    val preview = live.captionPreview
                    if (preview != null) {
                        Secondary(stringResource(R.string.live_draft, clock(preview.startMs)))
                        Body("“${preview.text}”", size = if (large) 22 else 16)
                    } else if (last != null) {
                        Secondary(utteranceMeta(last.speakerAlias, last.speakerVerified, last.speakerDisplay, last.startMs, last.isFinal, last.uncertain))
                        Body("“${last.text}”", size = if (large) 22 else 16)
                    } else {
                        Secondary(stringResource(when (s.transcriptStatus) {
                            "UNAVAILABLE" -> R.string.live_captions_unavailable
                            "DELAYED" -> R.string.live_captions_delayed
                            else -> R.string.live_captions_waiting
                        }))
                    }
                }
                val ins = live.insight
                if (ins != null && s.mutedUntil == null) {
                    MsCard(raised = true, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
                        Eyebrow("✦ " + (ins.label ?: stringResource(R.string.label_suggests)) + " · " + humanize(ins.kind))
                        Text(ins.shortText, color = t.text, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, lineHeight = 25.sp)
                        if (ins.sourceRefs.isNotEmpty()) CitationChips(ins.sourceRefs) { vm.openCitation(it) }
                        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                            SecondaryButton(stringResource(R.string.insight_why), { vm.openInsight(s.sessionId, ins.insightId) }, Modifier.weight(1f))
                            SecondaryButton(stringResource(R.string.action_save), { vm.insightFeedback(ins.insightId, "SAVED") }, Modifier.weight(1f))
                            SecondaryButton(stringResource(R.string.action_dismiss), { vm.insightFeedback(ins.insightId, "DISMISSED") }, Modifier.weight(1f))
                        }
                        Row {
                            LinkButton(stringResource(R.string.insight_useful)) { vm.insightFeedback(ins.insightId, "USEFUL") }
                            LinkButton(stringResource(R.string.insight_too_frequent)) { vm.insightFeedback(ins.insightId, "TOO_FREQUENT") }
                        }
                    }
                } else {
                    Secondary(stringResource(if (s.mutedUntil != null) R.string.live_muted else R.string.copy_live_empty))
                }
                if (s.context == "LEARNING") PrimaryButton(stringResource(R.string.live_explain), { vm.explain() }, enabled = s.aiAssistancePermitted)
                if (s.aiAssistancePermitted) LinkButton(stringResource(R.string.live_catch_up)) { vm.catchUp() }
                LinkButton(stringResource(if (showCaptions) R.string.live_hide_captions else R.string.live_show_captions)) { showCaptions = !showCaptions }
                if (showCaptions) live.transcript.takeLast(6).forEach {
                    Secondary(utteranceMeta(it.speakerAlias, it.speakerVerified, it.speakerDisplay, it.startMs, it.isFinal, false))
                    Body(it.text, size = if (large) 20 else 15)
                }
                if (noting) MsCard {
                    OutlinedTextField(note, { note = it.take(8000) }, label = { Text(stringResource(R.string.live_note_hint)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                    Secondary(stringResource(R.string.live_note_timed))
                    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                        SecondaryButton(stringResource(R.string.action_cancel), { noting = false; note = "" }, Modifier.weight(1f))
                        SecondaryButton(stringResource(R.string.live_save_note), { vm.addNote(note, false); note = ""; noting = false }, Modifier.weight(1f), enabled = note.isNotBlank())
                    }
                } else LinkButton(stringResource(R.string.live_add_note)) { noting = true }
                Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                    SecondaryButton(stringResource(R.string.live_transcript), { vm.openTranscript(s.sessionId) }, Modifier.weight(1f))
                    SecondaryButton(stringResource(R.string.live_voice_devices), { vm.go(Route.Voice) }, Modifier.weight(1f))
                }
                if (s.assistanceMode == "COMPANION") {
                    if (s.mutedUntil == null) {
                        Secondary(stringResource(R.string.live_mute_label))
                        ChoiceChips(listOf("5" to stringResource(R.string.mute_5), "15" to stringResource(R.string.mute_15),
                            "60" to stringResource(R.string.mute_60), "-1" to stringResource(R.string.mute_session)), null, { vm.mute(it.toInt()) })
                    } else SecondaryButton(stringResource(R.string.live_unmute), { vm.unmute() }, Modifier.fillMaxWidth())
                }
                if (s.assistanceMode != "LISTENER") LinkButton(stringResource(R.string.live_insights_history)) { vm.openInsights(s.sessionId) }
            }
            // Once recording has stopped, live controls no longer apply; only notes and Finish remain.
            if (!stopped) LinkButton(stringResource(if (showOptions) R.string.live_hide_options else R.string.live_show_options)) { showOptions = !showOptions }
            if (showOptions && !stopped) MsCard {
                if (!notesOnly) {
                    Title(stringResource(R.string.preflight_help_title))
                    AssistanceChips(s.assistanceMode, s.aiAssistancePermitted) { v ->
                        vm.setAssistance(v, if (v == "COMPANION" && s.proactiveIntensity == "QUIET") "BALANCED" else s.proactiveIntensity) }
                    if (!s.aiAssistancePermitted) Secondary(stringResource(R.string.live_ai_not_permitted))
                    if (s.assistanceMode == "COMPANION") IntensityChips(s.proactiveIntensity) { vm.setAssistance("COMPANION", it) }
                }
                Title(stringResource(R.string.live_switch_context))
                Secondary(stringResource(R.string.live_switch_context_note))
                ChoiceChips(listOf("MEETING", "LEARNING", "INTERVIEW", "CONVERSATION").map { it to contextName(it) }, s.context,
                    { if (it != s.context) vm.switchContext(it) })
                if (capturing && !live.withdrawPending) SecondaryButton(stringResource(R.string.live_stop_keep_notes), { vm.stopKeepNotes() }, Modifier.fillMaxWidth())
                if (capturing && !live.withdrawPending) {
                    Title(stringResource(R.string.withdraw_title))
                    if (confirmWithdraw) ConfirmDanger(stringResource(R.string.withdraw_confirm), stringResource(R.string.withdraw_action),
                        { confirmWithdraw = false }) { confirmWithdraw = false; vm.withdrawConsent() }
                    else SecondaryButton(stringResource(R.string.withdraw_button), { confirmWithdraw = true }, Modifier.fillMaxWidth(), danger = true)
                }
            }
            Gap(8)
        }
        // Persistent safe controls (never shifted by cards).
        Column(Modifier.fillMaxWidth().background(t.surface).padding(Spacing.m), verticalArrangement = Arrangement.spacedBy(Spacing.s)) {
            if (s.aiAssistancePermitted || notesOnly) SecondaryButton(stringResource(R.string.live_ask), { vm.clearAsk(); vm.go(Route.LiveAsk) }, Modifier.fillMaxWidth())
            else Secondary(stringResource(R.string.live_ai_off))
            if (stopped) {
                PrimaryButton(stringResource(R.string.live_finish_review), { vm.finishToRecap() })
            } else if (confirmEnd) {
                Body(stringResource(R.string.live_end_confirm), size = 15)
                Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                    SecondaryButton(stringResource(R.string.live_keep_going), { confirmEnd = false }, Modifier.weight(1f))
                    SecondaryButton(stringResource(R.string.live_end_save), { confirmEnd = false; vm.end() }, Modifier.weight(1f), danger = true)
                }
            } else Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                if (!notesOnly) SecondaryButton(stringResource(R.string.live_save_moment), { vm.saveMoment() }, Modifier.weight(1f), enabled = capturing)
                if (state == SessionState.RECORDING || state == SessionState.STARTING) SecondaryButton(stringResource(R.string.action_pause), { vm.pause() }, Modifier.weight(1f))
                if (state == SessionState.PAUSED) SecondaryButton(stringResource(R.string.action_resume), { vm.resume() }, Modifier.weight(1f))
                SecondaryButton(stringResource(R.string.action_end), { confirmEnd = true }, Modifier.weight(1f), danger = true)
            }
        }
    }
}

@Composable
fun utteranceMeta(alias: String?, verified: Boolean, display: String, startMs: Long, isFinal: Boolean, uncertain: Boolean): String =
    listOfNotNull(speakerName(alias, verified, display), clock(startMs),
        stringResource(if (isFinal) R.string.label_final else R.string.label_provisional),
        if (uncertain) stringResource(R.string.label_may_have_misheard) else null).joinToString(" · ")

@Composable
private fun StatusBanner(text: String, severity: String) =
    Banner(text, when (severity) { "error" -> Tone.Danger; "warning" -> Tone.Caution; else -> Tone.Accent })

@Composable
fun AskModeChips(mode: String, onSelect: (String) -> Unit) =
    ChoiceChips(listOf("REMEMBER" to stringResource(R.string.mode_remember), "THINK" to stringResource(R.string.mode_think),
        "LEARN" to stringResource(R.string.mode_learn), "PREPARE" to stringResource(R.string.mode_prepare)), mode, onSelect)

/** U06 Ask overlay: Remember / Think / Learn / Prepare, explicit scope chip, sourced sections. Pause/End stay one tap away. */
@Composable
fun LiveAskSheet(vm: AppViewModel, ui: UiState, live: LiveUiState) = Screen {
    var q by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf("REMEMBER") }
    TopRow(stringResource(R.string.ask_live_eyebrow)) { vm.back() }
    ui.study?.let { ex -> ExplainCard(ex) }
    AskModeChips(mode) { mode = it }
    Secondary(stringResource(when (mode) {
        "REMEMBER" -> R.string.mode_remember_note; "THINK" -> R.string.mode_think_note
        "LEARN" -> R.string.mode_learn_note; else -> R.string.mode_prepare_note
    }))
    val quick = listOf(R.string.quick_missed, R.string.quick_decided, R.string.quick_unclear, R.string.quick_explain, R.string.quick_ask).map { stringResource(it) }
    ChoiceChips(quick.map { it to it }, null, { q = it })
    OutlinedTextField(q, { q = it.take(4000) }, label = { Text(stringResource(R.string.ask_your_question)) }, modifier = Modifier.fillMaxWidth())
    PrimaryButton(stringResource(R.string.action_ask), { vm.ask(q, mode, "CURRENT_SESSION", null) }, enabled = q.isNotBlank() && !ui.busy)
    ui.askResult?.let { AnswerView(it) { c -> vm.openCitation(c) } }
    StatusPill(stringResource(live.truth.labelRes), Tone.Neutral)
}

@Composable
fun ExplainCard(ex: JsonObject) {
    MsCard(raised = true) {
        if (ex.str("status") == "OK") {
            Eyebrow(ex.str("label") ?: stringResource(R.string.explain_label))
            Body(ex.str("title") ?: stringResource(R.string.explain_title), size = 18)
            Body(ex.str("answer") ?: "")
            ex.str("example")?.let { Secondary(stringResource(R.string.explain_example, it)) }
            ex.arr("from_lecture")?.forEach { s ->
                Eyebrow(s.o.str("label") ?: stringResource(R.string.explain_from_lecture))
                Body(s.o.str("text") ?: "", size = 15)
            }
            ex.str("visual_notice")?.let { Banner(it, Tone.Caution) }
        } else {
            Body(ex.str("message") ?: "")
            Secondary(stringResource(R.string.explain_bookmarked))
        }
    }
}

@Composable
fun AnswerView(a: AskResponse, onCite: ((app.meetsaathi.core.Citation) -> Unit)? = null) {
    MsCard(raised = true) {
        Eyebrow(provenanceTitle(a.provenanceLabel))
        if (a.sections.isEmpty()) Body(a.answer)
        a.sections.forEach { sec ->
            Eyebrow(sec.label)
            Body(sec.text, size = 15)
            CitationChips(sec.citations, onCite)
        }
        a.proposedActions.forEach { Secondary(stringResource(R.string.answer_proposed_action, it.text)) }
        a.checkQuestion?.let { Secondary(stringResource(R.string.answer_check_yourself, it)) }
        if (a.uncertainty.isNotBlank()) Secondary("▲ ${a.uncertainty}")
    }
}

/** U07 Transcript/Evidence: provisional/final labels, per-turn time, aliases, correction, and the cited audio when retained. */
@Composable
fun TranscriptScreen(vm: AppViewModel, ui: UiState, live: LiveUiState, sessionId: String) = Screen {
    val liveSession = live.session?.takeIf { it.sessionId == sessionId }
    val recap = ui.recap?.takeIf { it.str("session_id") == sessionId }
    // Never replay audio while the microphone may be live: the clip would be re-recorded into the conversation.
    val capturing = liveSession != null && SessionState.parse(liveSession.state) in app.meetsaathi.core.SessionStateMachine.active
    val audioAvailable = !capturing && if (liveSession != null) liveSession.captureSource != "NONE"
        else recap?.obj("completeness")?.let { !it.bool("audio_deleted") && !it.bool("notes_only") } ?: false
    val player by vm.evidence.state.collectAsState()
    var editing by remember { mutableStateOf<String?>(null) }
    var text by remember { mutableStateOf("") }
    LaunchedEffect(sessionId) { vm.loadTranscript(sessionId) }
    TopRow(stringResource(R.string.transcript_eyebrow)) { vm.back() }
    Secondary(stringResource(R.string.transcript_note))
    liveSession?.gaps?.filter { it.reason != "PAUSED_BY_USER" }?.forEach { GapBanner(it.phrase()) }
    var find by remember { mutableStateOf("") }
    if (ui.transcript.isEmpty()) Secondary(stringResource(R.string.transcript_empty))
    else OutlinedTextField(find, { find = it.take(100) }, label = { Text(stringResource(R.string.transcript_find)) }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    val shown = if (find.isBlank()) ui.transcript else ui.transcript.filter { it.text.contains(find.trim(), ignoreCase = true) }
    if (ui.transcript.isNotEmpty() && shown.isEmpty()) Secondary(stringResource(R.string.transcript_no_match))
    shown.forEach { u ->
        MsCard {
            Secondary(utteranceMeta(u.speakerAlias, u.speakerVerified, u.speakerDisplay, u.startMs, u.isFinal, u.uncertain))
            if (editing == u.utteranceId) {
                OutlinedTextField(text, { text = it.take(8000) }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                    SecondaryButton(stringResource(R.string.transcript_save_correction), { vm.correctUtterance(sessionId, u, text); editing = null },
                        Modifier.weight(1f), enabled = text.isNotBlank())
                    SecondaryButton(stringResource(R.string.action_cancel), { editing = null }, Modifier.weight(1f))
                }
            } else {
                Body(u.text, size = 15)
                Row {
                    if (audioAvailable) EvidenceButton(player, u.utteranceId, u.startMs) { vm.playEvidence(sessionId, u.utteranceId) }
                    LinkButton(stringResource(R.string.transcript_correct)) { editing = u.utteranceId; text = u.text }
                }
            }
        }
    }
    LinkButton(stringResource(R.string.recap_review_speakers)) { vm.loadSpeakers(sessionId); vm.go(Route.Speakers(sessionId)) }
}

/** U08 Voice & devices: observed routes, private-voice test, explicit confirmation, mute. Fails closed. */
@Composable
fun VoiceScreen(vm: AppViewModel, live: LiveUiState) = Screen {
    val r = live.route
    var testing by remember { mutableStateOf(false) }
    val none = stringResource(R.string.label_none)
    TopRow(stringResource(R.string.live_voice_devices)) { vm.back() }
    MsCard {
        Body(stringResource(R.string.voice_input, r?.input?.replace('_', ' ')?.lowercase() ?: none))
        Body(stringResource(R.string.voice_output, (r?.output?.replace('_', ' ')?.lowercase() ?: none) + (r?.outputDeviceName?.let { " · $it" } ?: "")))
        if (r?.couplesInputAndOutput == true) Banner(stringResource(R.string.voice_coupled), Tone.Caution)
        if (live.privateRouteVerified) StatusPill(stringResource(R.string.voice_verified), Tone.Accent) else StatusPill(stringResource(R.string.voice_off), Tone.Neutral)
    }
    if (r?.privateOutputPresent != true) {
        Banner(stringResource(R.string.voice_no_device), Tone.Caution)
    } else if (!live.privateRouteVerified) {
        PrimaryButton(stringResource(R.string.voice_play_sample), { testing = vm.live.verifyPrivateRoute() })
        if (testing) {
            Body(stringResource(R.string.voice_heard_question, r.outputDeviceName ?: stringResource(R.string.voice_your_earbuds)))
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
                SecondaryButton(stringResource(R.string.voice_heard_yes), { vm.live.confirmHeardPrivateSample(); testing = false }, Modifier.weight(1f))
                SecondaryButton(stringResource(R.string.voice_heard_no), { testing = false }, Modifier.weight(1f))
            }
        }
    }
    live.session?.let { s ->
        Eyebrow(stringResource(R.string.voice_delivery_session))
        OutputChips(s.outputMode, { it == "TEXT" || live.privateRouteVerified }) { vm.setOutput(it) }
        Secondary(stringResource(R.string.voice_off_note))
    }
}

/** M08 Insight detail: what was suggested, why now, which moments it rests on, and whether it is still current. */
@Composable
fun InsightDetailScreen(vm: AppViewModel, ui: UiState, sessionId: String, insightId: String) = Screen {
    TopRow(stringResource(R.string.insight_detail_eyebrow)) { vm.back() }
    val d = ui.insightDetail?.takeIf { it.str("insight_id") == insightId }
    if (d == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    StatusPill(d.str("label") ?: stringResource(R.string.label_suggests), if (d.str("source_kind") == "FROM_CONVERSATION") Tone.Accent else Tone.Neutral)
    Heading(d.str("short_text") ?: "")
    d.str("long_text")?.let { Body(it, size = 15) }
    if (d.bool("not_current")) Banner(stringResource(R.string.insight_not_current), Tone.Caution)
    d.str("rationale")?.let { MsCard { Title(stringResource(R.string.insight_rationale)); Body(it, size = 15) } }
    val refs = d.arr("evidence_refs").orEmpty().mapNotNull { runCatching { app.meetsaathi.core.WireJson.decodeFromJsonElement(app.meetsaathi.core.Citation.serializer(), it) }.getOrNull() }
    MsCard {
        Title(stringResource(R.string.insight_based_on))
        if (refs.isEmpty()) Secondary(stringResource(R.string.insight_no_evidence))
        refs.forEach { c -> c.text?.let { Body("“$it”", size = 15) }; CitationChips(listOf(c)) { vm.openCitation(it) } }
    }
    if (!d.bool("not_current")) Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        SecondaryButton(stringResource(R.string.insight_useful), { vm.insightFeedback(insightId, "USEFUL") }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.action_save), { vm.insightFeedback(insightId, "SAVED") }, Modifier.weight(1f))
        SecondaryButton(stringResource(R.string.action_dismiss), { vm.insightFeedback(insightId, "DISMISSED"); vm.back() }, Modifier.weight(1f))
    }
}

/** S06 insight history: every suggestion this session, current or retired ("Not current"), each opening its detail. */
@Composable
fun InsightsScreen(vm: AppViewModel, ui: UiState, sessionId: String) = Screen {
    TopRow(stringResource(R.string.insights_title)) { vm.back() }
    val items = ui.insights
    if (items == null) { Secondary(stringResource(R.string.label_loading)); return@Screen }
    if (items.isEmpty()) Secondary(stringResource(R.string.insights_empty))
    items.forEach { el -> val o = el.o
        MsCard(Modifier.clickable(role = androidx.compose.ui.semantics.Role.Button) { o.str("insight_id")?.let { vm.openInsight(sessionId, it) } }) {
            Eyebrow(humanize(o.str("kind")) + (Dates.dateTime(o.str("delivered_at"))?.let { " · $it" } ?: ""))
            Body(o.str("short_text") ?: "", size = 15)
            if (o.bool("not_current")) Secondary(stringResource(R.string.insight_not_current))
        }
    }
}
