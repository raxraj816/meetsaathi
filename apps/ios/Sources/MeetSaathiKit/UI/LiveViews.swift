import SwiftUI

private func tone(_ t: CaptureTruth) -> Tone {
    switch t {
    case .recording: return .accent
    case .recordingLocal, .starting, .paused: return .caution
    case .interrupted, .micDenied: return .danger
    default: return .neutral
    }
}

func utteranceMeta(_ u: Utterance, showUncertain: Bool = true) -> String {
    var parts = [speakerName(alias: u.speakerAlias, verified: u.speakerVerified ?? false, label: u.speakerDisplay), clockString(u.startMs),
                 u.isFinal ? L("label_final") : L("label_provisional")]
    if showUncertain && (u.uncertain ?? false) { parts.append(L("label_may_have_misheard")) }
    return parts.joined(separator: " · ")
}

/// U05 Live Focus: sticky truthful header, ONE insight or "Listening quietly", collapsed captions, Ask,
/// and persistent Save / Pause / End controls that never move when cards arrive.
struct LiveView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    @State private var showCaptions = false
    @State private var showOptions = false
    @State private var confirmEnd = false
    @State private var confirmWithdraw = false
    @State private var note = ""
    @State private var showAsk = false
    @State private var transcriptFor: String?
    @State private var showVoice = false
    @State private var insightFor: SheetID?
    @State private var showHistory = false
    @State private var noting = false
    @State private var liveNote = ""

    var body: some View {
        if let s = live.session {
            let state = SessionState.parse(s.state)
            let notesOnly = s.captureSource == "NONE"
            let capturing = [.RECORDING, .STARTING, .PAUSED, .INTERRUPTED].contains(state)
            let large = model.preferences["captions_large"]?.bool == true
            let stopped = !notesOnly && (SessionStateMachine.ended.contains(state) || live.truth == .stopped)
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("\(contextName(s.context)) · \(clockString(live.elapsedMs))").font(.subheadline).foregroundStyle(MS.secondary)
                        Spacer()
                        StatusPill(text: live.truth.label, tone: tone(live.truth))
                    }
                    Text(s.title).font(.title3.bold()).foregroundStyle(MS.text)
                    let output = s.outputMode != "TEXT" && live.privateRouteVerified ? L("live_output_private", live.route.outputDeviceName ?? L("voice_earbuds")) : L("output_silent_text")
                    SecondaryText(L("live_route_line", live.route.input.replacingOccurrences(of: "_", with: " "), output))
                    if !live.online { Banner(text: L("live_offline"), tone: .caution) }
                }
                .padding(16).background(MS.surface)

                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if let st = live.status { Banner(text: st.text, tone: st.severity == "error" ? .danger : (st.severity == "warning" ? .caution : .accent)) }
                        if live.withdrawPending {
                            Card { Text(L("status_withdraw_pending")).foregroundStyle(MS.text); PrimaryButton(L("action_retry")) { model.withdrawConsent() } }
                        } else if state == .INTERRUPTED {
                            Card { Text(L("live_interrupted")).foregroundStyle(MS.text); PrimaryButton(L("action_resume")) { model.resume() } }
                        }
                        if stopped {
                            Card {
                                Text(L("live_after_stop_note")).foregroundStyle(MS.text)
                                TextField(L("live_note_hint"), text: $note, axis: .vertical).lineLimit(3...8).textFieldStyle(.roundedBorder)
                                SecondaryButton(L("live_save_note"), enabled: !note.isEmpty) { model.addNote(note, recollection: false); note = "" }
                            }
                        } else if notesOnly {
                            Card {
                                Text(L("copy_notes_only")).foregroundStyle(MS.text)
                                TextField(L("live_note_hint"), text: $note, axis: .vertical).lineLimit(3...8).textFieldStyle(.roundedBorder)
                                SecondaryText(L("live_note_own_words"))
                                HStack {
                                    SecondaryButton(L("live_save_note"), enabled: !note.isEmpty) { model.addNote(note, recollection: false); note = "" }
                                    SecondaryButton(L("live_save_recollection"), enabled: !note.isEmpty) { model.addNote(note, recollection: true); note = "" }
                                }
                            }
                        } else {
                            Card {
                                Eyebrow(L("live_latest"))
                                if let draft = live.captionPreview {
                                    SecondaryText(L("live_draft", clockString(draft.startMs)))
                                    Text("“\(draft.text)”").font(large ? .title2 : .body).foregroundStyle(MS.text)
                                } else if let last = live.transcript.last {
                                    SecondaryText(utteranceMeta(last))
                                    Text("“\(last.text)”").font(large ? .title2 : .body).foregroundStyle(MS.text)
                                } else {
                                    SecondaryText(L(s.transcriptStatus == "UNAVAILABLE" ? "live_captions_unavailable"
                                                    : s.transcriptStatus == "DELAYED" ? "live_captions_delayed" : "live_captions_waiting"))
                                }
                            }
                            if let ins = live.insight, s.mutedUntil == nil {
                                Card(raised: true) {
                                    Eyebrow("✦ \(ins.label ?? L("label_suggests")) · \(humanize(ins.kind))")
                                    Text(ins.shortText).font(.title3.weight(.semibold)).foregroundStyle(MS.text)
                                    CitationChips(cites: ins.sourceRefs)
                                    HStack {
                                        SecondaryButton(L("insight_why")) { model.loadInsight(s.sessionId, ins.insightId); insightFor = SheetID(id: ins.insightId) }
                                        SecondaryButton(L("action_save")) { model.feedback(ins.insightId, "SAVED") }
                                        SecondaryButton(L("action_dismiss")) { model.feedback(ins.insightId, "DISMISSED") }
                                    }
                                    HStack { LinkText(L("insight_useful")) { model.feedback(ins.insightId, "USEFUL") }
                                        LinkText(L("insight_too_frequent")) { model.feedback(ins.insightId, "TOO_FREQUENT") } }
                                }
                                .accessibilityElement(children: .contain)
                            } else {
                                SecondaryText(s.mutedUntil != nil ? L("live_muted") : L("copy_live_empty"))
                            }
                            if s.context == "LEARNING" {
                                PrimaryButton(L("live_explain"), enabled: s.aiAssistancePermitted) { model.explainThis(); showAsk = true }
                            }
                            if s.aiAssistancePermitted {
                                LinkText(L("live_catch_up")) {
                                    model.askResult = nil; model.explain = nil
                                    model.askSession(s.sessionId, L("quick_missed"), mode: "REMEMBER"); showAsk = true
                                }
                            }
                            LinkText(showCaptions ? L("live_hide_captions") : L("live_show_captions")) { showCaptions.toggle() }
                            if showCaptions {
                                ForEach(live.transcript.suffix(6)) { u in
                                    SecondaryText(utteranceMeta(u, showUncertain: false))
                                    Text(u.text).font(large ? .title3 : .body).foregroundStyle(MS.text)
                                }
                            }
                            if noting {
                                Card {
                                    TextField(L("live_note_hint"), text: $liveNote, axis: .vertical).lineLimit(2...6).textFieldStyle(.roundedBorder)
                                    SecondaryText(L("live_note_timed"))
                                    HStack {
                                        SecondaryButton(L("action_cancel")) { noting = false; liveNote = "" }
                                        SecondaryButton(L("live_save_note"), enabled: !liveNote.isEmpty) { model.addNote(liveNote, recollection: false); liveNote = ""; noting = false }
                                    }
                                }
                            } else {
                                LinkText(L("live_add_note")) { noting = true }
                            }
                            HStack {
                                SecondaryButton(L("live_transcript")) { model.utterances = []; model.loadTranscript(s.sessionId); transcriptFor = s.sessionId }
                                SecondaryButton(L("live_voice_devices")) { showVoice = true }
                            }
                            if s.assistanceMode == "COMPANION" {
                                if s.mutedUntil == nil {
                                    SecondaryText(L("live_mute_label"))
                                    Chips(options: [("5", L("mute_5")), ("15", L("mute_15")), ("60", L("mute_60")), ("-1", L("mute_session"))], selected: nil) {
                                        model.mute(Int($0) ?? 15)
                                    }
                                } else { SecondaryButton(L("live_unmute")) { model.unmute() } }
                            }
                            if s.assistanceMode != "LISTENER" { LinkText(L("live_insights_history")) { model.loadInsights(s.sessionId); showHistory = true } }
                        }
                        // Once recording has stopped, live controls no longer apply; only notes and Finish remain.
                        if !stopped { LinkText(showOptions ? L("live_hide_options") : L("live_show_options")) { showOptions.toggle() } }
                        if showOptions && !stopped {
                            Card {
                                if !notesOnly {
                                    Text(L("preflight_help_title")).font(.headline).foregroundStyle(MS.text)
                                    AssistanceChips(selected: s.assistanceMode, aiOk: s.aiAssistancePermitted) { v in
                                        model.setAssistance(v, v == "COMPANION" && s.proactiveIntensity == "QUIET" ? "BALANCED" : s.proactiveIntensity)
                                    }
                                    if !s.aiAssistancePermitted { SecondaryText(L("live_ai_not_permitted")) }
                                    if s.assistanceMode == "COMPANION" { IntensityChips(selected: s.proactiveIntensity) { model.setAssistance("COMPANION", $0) } }
                                }
                                Text(L("live_switch_context")).font(.headline).foregroundStyle(MS.text)
                                SecondaryText(L("live_switch_context_note"))
                                Chips(options: ["MEETING", "LEARNING", "INTERVIEW", "CONVERSATION"].map { ($0, contextName($0)) }, selected: s.context) {
                                    if $0 != s.context { model.switchContext($0) }
                                }
                                if capturing && !live.withdrawPending { SecondaryButton(L("live_stop_keep_notes")) { model.stopKeepNotes() } }
                                if capturing && !live.withdrawPending {
                                    Text(L("withdraw_title")).font(.headline).foregroundStyle(MS.text)
                                    if confirmWithdraw {
                                        ConfirmDanger(prompt: L("withdraw_confirm"), confirm: L("withdraw_action"), onCancel: { confirmWithdraw = false }) {
                                            confirmWithdraw = false; model.withdrawConsent()
                                        }
                                    } else {
                                        SecondaryButton(L("withdraw_button"), danger: true) { confirmWithdraw = true }
                                    }
                                }
                            }
                        }
                    }.padding(16)
                }

                VStack(spacing: 8) {
                    if s.aiAssistancePermitted || notesOnly { SecondaryButton(L("live_ask")) { model.askResult = nil; model.explain = nil; showAsk = true } }
                    else { SecondaryText(L("live_ai_off")) }
                    if stopped {
                        PrimaryButton(L("live_finish_review")) { model.finishToRecap() }
                    } else if confirmEnd {
                        Text(L("live_end_confirm")).font(.subheadline).foregroundStyle(MS.text)
                        HStack { SecondaryButton(L("live_keep_going")) { confirmEnd = false }; SecondaryButton(L("live_end_save"), danger: true) { confirmEnd = false; model.end() } }
                    } else {
                        HStack {
                            if !notesOnly { SecondaryButton(L("live_save_moment"), enabled: capturing) { model.saveMoment() } }
                            if state == .RECORDING || state == .STARTING { SecondaryButton(L("action_pause")) { model.pause() } }
                            if state == .PAUSED { SecondaryButton(L("action_resume")) { model.resume() } }
                            SecondaryButton(L("action_end"), danger: true) { confirmEnd = true }
                        }
                    }
                }
                .padding(12).background(MS.surface)
            }
            .screenBackground()
            .sheet(isPresented: $showAsk) { NavigationStack { LiveAskView(model: model, live: live) } }
            .sheet(item: Binding(get: { transcriptFor.map(SheetID.init) }, set: { transcriptFor = $0?.id })) { item in
                NavigationStack { TranscriptView(model: model, live: live, sessionId: item.id) }
            }
            .sheet(isPresented: $showVoice) { NavigationStack { VoiceView(model: model, live: live) } }
            .sheet(item: $insightFor) { item in NavigationStack { InsightDetailView(model: model, sessionId: s.sessionId, insightId: item.id, inLive: true) } }
            .sheet(isPresented: $showHistory) { NavigationStack { InsightsView(model: model, sessionId: s.sessionId, inLive: true) } }
        } else {
            ScrollPage { SecondaryText(L("live_no_session")); SecondaryButton(L("action_close")) { model.liveOpen = false } }
        }
    }
}

struct SheetID: Identifiable { let id: String }

/// S06 insight history: every suggestion this session, current or retired ("Not current"), each opening its detail.
struct InsightsView: View {
    @ObservedObject var model: AppModel
    let sessionId: String
    var inLive = false
    @Environment(\.dismiss) private var dismiss
    @State private var detail: SheetID?
    var body: some View {
        ScrollPage {
            if let items = model.insights {
                if items.isEmpty { SecondaryText(L("insights_empty")) }
                ForEach(Array(items.enumerated()), id: \.offset) { _, o in
                    Button {
                        guard let id = o["insight_id"]?.string else { return }
                        model.loadInsight(sessionId, id)
                        if inLive { detail = SheetID(id: id) } else { model.push(.insight(sessionId, id)) }
                    } label: {
                        Card {
                            Eyebrow(humanize(o["kind"]?.string) + (Dates.dateTime(o["delivered_at"]?.string).map { " · \($0)" } ?? ""))
                            Text(o["short_text"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                            if o["not_current"]?.bool == true { SecondaryText(L("insight_not_current")) }
                        }
                    }.buttonStyle(.plain)
                }
            } else { SecondaryText(L("label_loading")) }
        }
        .navigationTitle(L("insights_title"))
        .toolbar { ToolbarItem { Button(L("action_close")) { dismiss() } } }
        .sheet(item: $detail) { item in NavigationStack { InsightDetailView(model: model, sessionId: sessionId, insightId: item.id, inLive: inLive) } }
    }
}

/// M08 Insight detail: what was suggested, why now, which moments it rests on, and whether it is still current.
struct InsightDetailView: View {
    @ObservedObject var model: AppModel
    let sessionId: String
    let insightId: String
    var inLive = false
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollPage {
            if let d = model.insightDetail, d["insight_id"]?.string == insightId {
                StatusPill(text: d["label"]?.string ?? L("label_suggests"), tone: d["source_kind"]?.string == "FROM_CONVERSATION" ? .accent : .neutral)
                Text(d["short_text"]?.string ?? "").font(.title2.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
                if let lt = d["long_text"]?.string { Text(lt).font(.subheadline).foregroundStyle(MS.text) }
                if d["not_current"]?.bool == true { Banner(text: L("insight_not_current"), tone: .caution) }
                if let r = d["rationale"]?.string { Card { Text(L("insight_rationale")).font(.headline).foregroundStyle(MS.text); Text(r).font(.subheadline).foregroundStyle(MS.text) } }
                let refs: [Citation] = (d["evidence_refs"]?.array ?? []).compactMap { v in
                    (try? Wire.encoder.encode(v)).flatMap { try? Wire.decoder.decode(Citation.self, from: $0) }
                }
                Card {
                    Text(L("insight_based_on")).font(.headline).foregroundStyle(MS.text)
                    if refs.isEmpty { SecondaryText(L("insight_no_evidence")) }
                    ForEach(Array(refs.enumerated()), id: \.offset) { _, c in
                        if let t = c.text { Text("“\(t)”").font(.subheadline).foregroundStyle(MS.text) }
                        // Inside the live surface the moment is still being recorded: show the source, never replay it.
                        CitationChips(cites: [c], onOpen: inLive ? nil : { model.openCitation($0) })
                    }
                }
                if d["not_current"]?.bool != true {
                    HStack {
                        SecondaryButton(L("insight_useful")) { model.feedback(insightId, "USEFUL") }
                        SecondaryButton(L("action_save")) { model.feedback(insightId, "SAVED") }
                        SecondaryButton(L("action_dismiss")) { model.feedback(insightId, "DISMISSED"); dismiss() }
                    }
                }
            } else {
                SecondaryText(L("label_loading"))
            }
        }
        .navigationTitle(L("insight_detail_eyebrow"))
        .toolbar { ToolbarItem { Button(L("action_close")) { dismiss() } } }
    }
}

struct ExplainCard: View {
    let ex: JSONValue
    var body: some View {
        Card(raised: true) {
            if ex["status"]?.string == "OK" {
                Eyebrow(ex["label"]?.string ?? L("explain_label"))
                Text(ex["title"]?.string ?? L("explain_title")).font(.headline).foregroundStyle(MS.text)
                Text(ex["answer"]?.string ?? "").foregroundStyle(MS.text)
                if let e = ex["example"]?.string { SecondaryText(L("explain_example", e)) }
                ForEach(Array((ex["from_lecture"]?.array ?? []).enumerated()), id: \.offset) { _, s in
                    Eyebrow(s["label"]?.string ?? L("explain_from_lecture")); Text(s["text"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                }
                if let v = ex["visual_notice"]?.string { Banner(text: v, tone: .caution) }
            } else {
                Text(ex["message"]?.string ?? "").foregroundStyle(MS.text)
                SecondaryText(L("explain_bookmarked"))
            }
        }
    }
}

struct AnswerView: View {
    let a: AskResponse
    var onCite: ((Citation) -> Void)? = nil
    var body: some View {
        Card(raised: true) {
            Eyebrow(a.provenanceTitle)
            if a.sections.isEmpty { Text(a.answer).foregroundStyle(MS.text) }
            ForEach(Array(a.sections.enumerated()), id: \.offset) { _, sec in
                Eyebrow(sec.label)
                Text(sec.text).font(.subheadline).foregroundStyle(MS.text)
                CitationChips(cites: sec.citations, onOpen: onCite)
            }
            ForEach(Array((a.proposedActions ?? []).enumerated()), id: \.offset) { _, p in SecondaryText(L("answer_proposed_action", p.text)) }
            if let q = a.checkQuestion { SecondaryText(L("answer_check_yourself", q)) }
            if !a.uncertainty.isEmpty { SecondaryText("▲ \(a.uncertainty)") }
        }
    }
}

struct AskModeChips: View {
    let mode: String
    let onSelect: (String) -> Void
    var body: some View {
        Chips(options: [("REMEMBER", L("mode_remember")), ("THINK", L("mode_think")), ("LEARN", L("mode_learn")), ("PREPARE", L("mode_prepare"))],
              selected: mode, onSelect: onSelect)
    }
}

/// U06 Ask overlay. Scope chip is explicit; Remember is evidence-bound; analysis labelled separately.
struct LiveAskView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    @Environment(\.dismiss) private var dismiss
    @State private var q = ""
    @State private var mode = "REMEMBER"
    var body: some View {
        ScrollPage {
            Eyebrow(L("ask_live_eyebrow"))
            if let ex = model.explain { ExplainCard(ex: ex) }
            AskModeChips(mode: mode) { mode = $0 }
            SecondaryText(L(mode == "REMEMBER" ? "mode_remember_note" : mode == "THINK" ? "mode_think_note" : mode == "LEARN" ? "mode_learn_note" : "mode_prepare_note"))
            let quick = ["quick_missed", "quick_decided", "quick_unclear", "quick_explain", "quick_ask"].map { L($0) }
            Chips(options: quick.map { ($0, $0) }, selected: nil) { q = $0 }
            TextField(L("ask_your_question"), text: $q, axis: .vertical).textFieldStyle(.roundedBorder)
            PrimaryButton(L("action_ask"), enabled: !q.isEmpty && !model.busy) { model.ask(q, mode: mode, scope: "CURRENT_SESSION", scopeId: nil) }
            if let a = model.askResult { AnswerView(a: a) }
            StatusPill(text: live.truth.label, tone: .neutral)
        }
        .navigationTitle(L("ask_eyebrow"))
        .toolbar { ToolbarItem { Button(L("action_close")) { dismiss() } } }
    }
}

/// U07 Transcript & evidence with provisional labels, gaps, corrections and the cited audio when retained.
struct TranscriptView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    let sessionId: String
    @Environment(\.dismiss) private var dismiss
    @State private var editing: String?
    @State private var text = ""
    @State private var find = ""
    var body: some View {
        let liveSession = live.session?.sessionId == sessionId ? live.session : nil
        // Never replay audio while the microphone may be live: the clip would be re-recorded into the conversation.
        let capturing = liveSession.map { SessionStateMachine.active.contains(SessionState.parse($0.state)) } ?? false
        let recap = model.recap?["session_id"]?.string == sessionId ? model.recap : nil
        let audio = !capturing && (liveSession.map { $0.captureSource != "NONE" }
            ?? (recap.map { $0["completeness"]?["audio_deleted"]?.bool != true && $0["completeness"]?["notes_only"]?.bool != true } ?? false))
        ScrollPage {
            SecondaryText(L("transcript_note"))
            ForEach(liveSession?.gaps.filter { $0.reason != "PAUSED_BY_USER" } ?? [], id: \.self) { g in Banner(text: g.description, tone: .caution) }
            if model.utterances.isEmpty { SecondaryText(L("transcript_empty")) }
            else { TextField(L("transcript_find"), text: $find).textFieldStyle(.roundedBorder) }
            let needle = find.trimmingCharacters(in: .whitespaces)
            let shown = needle.isEmpty ? model.utterances : model.utterances.filter { $0.text.localizedCaseInsensitiveContains(needle) }
            if !model.utterances.isEmpty && shown.isEmpty { SecondaryText(L("transcript_no_match")) }
            ForEach(shown) { u in
                Card {
                    SecondaryText(utteranceMeta(u))
                    if editing == u.utteranceId {
                        TextField(L("transcript_correct"), text: $text, axis: .vertical).textFieldStyle(.roundedBorder)
                        HStack {
                            SecondaryButton(L("transcript_save_correction"), enabled: !text.isEmpty) { model.correct(sessionId, u, text); editing = nil }
                            SecondaryButton(L("action_cancel")) { editing = nil }
                        }
                    } else {
                        Text(u.text).foregroundStyle(MS.text)
                        HStack {
                            if audio { EvidenceButton(player: model.evidence, utteranceId: u.utteranceId, startMs: u.startMs) { model.playEvidence(sessionId, u.utteranceId) } }
                            LinkText(L("transcript_correct")) { editing = u.utteranceId; text = u.text }
                        }
                    }
                }
            }
            LinkText(L("recap_review_speakers")) { model.loadSpeakers(sessionId); model.push(.speakers(sessionId)) }
        }
        .navigationTitle(L("transcript_eyebrow"))
        .toolbar { ToolbarItem { Button(L("action_close")) { model.evidence.stop(); dismiss() } } }
        .onDisappear { model.evidence.stop() }
    }
}

/// U08 Voice & devices: observed routes, private test, explicit confirmation. Fails closed.
struct VoiceView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    @Environment(\.dismiss) private var dismiss
    @State private var testing = false
    var body: some View {
        ScrollPage {
            Card {
                Text(L("voice_input", live.route.input.replacingOccurrences(of: "_", with: " "))).foregroundStyle(MS.text)
                Text(L("voice_output", live.route.output.replacingOccurrences(of: "_", with: " ") + (live.route.outputDeviceName.map { " · \($0)" } ?? ""))).foregroundStyle(MS.text)
                if live.route.couplesInputAndOutput { Banner(text: L("voice_coupled"), tone: .caution) }
                StatusPill(text: live.privateRouteVerified ? L("voice_verified") : L("voice_off"), tone: live.privateRouteVerified ? .accent : .neutral)
            }
            if !live.route.privateOutputPresent {
                Banner(text: L("voice_no_device"), tone: .caution)
            } else if !live.privateRouteVerified {
                PrimaryButton(L("voice_play_sample")) { testing = live.verifyPrivateRoute() }
                if testing {
                    Text(L("voice_heard_question", live.route.outputDeviceName ?? L("voice_your_earbuds"))).foregroundStyle(MS.text)
                    HStack { SecondaryButton(L("voice_heard_yes")) { live.confirmHeardPrivateSample(); testing = false }; SecondaryButton(L("voice_heard_no")) { testing = false } }
                }
            }
            if let s = live.session {
                Eyebrow(L("voice_delivery_session"))
                OutputChips(selected: s.outputMode, enabled: { $0 == "TEXT" || live.privateRouteVerified }) { model.setOutput($0) }
                SecondaryText(L("voice_off_note"))
            }
        }
        .navigationTitle(L("live_voice_devices"))
        .toolbar { ToolbarItem { Button(L("action_close")) { dismiss() } } }
    }
}
