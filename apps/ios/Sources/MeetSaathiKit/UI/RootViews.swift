import SwiftUI
#if os(iOS)
import UIKit
#endif

/// App root: Home / Memories / Ask / You tabs; Live is an immersive full-screen surface (master 2.1).
public struct RootView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController

    public init(model: AppModel) { self.model = model; self.live = model.live }

    public var body: some View {
        Group {
            if !model.signedIn {
                if model.showSample { SampleView(model: model) } else { WelcomeView(model: model) }
            } else {
                TabView(selection: $model.tab) {
                    tabStack { HomeView(model: model, live: live) }.tabItem { Label(Tab.home.label, systemImage: "house") }.tag(Tab.home)
                    tabStack { MemoriesView(model: model) }.tabItem { Label(Tab.memories.label, systemImage: "tray.full") }.tag(Tab.memories)
                    tabStack { GlobalAskView(model: model) }.tabItem { Label(Tab.ask.label, systemImage: "sparkles") }.tag(Tab.ask)
                    tabStack { YouView(model: model) }.tabItem { Label(Tab.you.label, systemImage: "person.crop.circle") }.tag(Tab.you)
                }
                .tint(MS.accent)
                .safeAreaInset(edge: .top) { miniBar }
                .onChange(of: model.tab) { _, _ in model.path = []; model.evidence.stop() }
            }
        }
        #if os(iOS)
        .fullScreenCover(isPresented: $model.liveOpen) { NavigationStack { LiveView(model: model, live: live).navigationDestination(for: Screen.self, destination: destination) } }
        #else
        .sheet(isPresented: $model.liveOpen) { NavigationStack { LiveView(model: model, live: live).navigationDestination(for: Screen.self, destination: destination) } }
        #endif
        .alert(model.message ?? "", isPresented: Binding(get: { model.message != nil }, set: { if !$0 { model.message = nil } })) { Button(L("action_done")) {} }
    }

    func tabStack<V: View>(@ViewBuilder _ v: () -> V) -> some View {
        NavigationStack(path: $model.path) { v().navigationDestination(for: Screen.self, destination: destination) }
    }

    /// Persistent mini-bar: an active session is recoverable from every tab.
    @ViewBuilder var miniBar: some View {
        if let s = live.session, SessionStateMachine.active.contains(SessionState.parse(s.state)), !model.liveOpen {
            Button { model.liveOpen = true } label: {
                Text(L("minibar", live.truth.label, s.title, clockString(live.elapsedMs)))
                    .font(.subheadline.weight(.semibold)).foregroundStyle(MS.text).frame(maxWidth: .infinity, minHeight: MS.minTouch).padding(.horizontal, 12)
            }.background(MS.raised)
        }
    }

    @ViewBuilder func destination(_ s: Screen) -> some View {
        switch s {
        case .contextChooser: ContextChooserView(model: model)
        case .preflight: PreflightView(model: model, live: live)
        case .liveAsk: LiveAskView(model: model, live: live)
        case .transcript(let id): TranscriptView(model: model, live: live, sessionId: id)
        case .voice: VoiceView(model: model, live: live)
        case .recap(let id): RecapView(model: model, live: live, sessionId: id)
        case .speakers(let id): SpeakersView(model: model, sessionId: id)
        case .study: StudyView(model: model)
        case .interview: InterviewView(model: model)
        case .mock(let id): MockView(model: model, mockId: id)
        case .memory(let id): MemoryDetailView(model: model, claimId: id)
        case .share(let id): ShareView(model: model, sessionId: id)
        case .sessions: SessionsView(model: model)
        case .projects: ProjectsView(model: model)
        case .project(let id): ProjectView(model: model, projectId: id)
        case .insight(let sid, let iid): InsightDetailView(model: model, sessionId: sid, insightId: iid)
        case .insights(let sid): InsightsView(model: model, sessionId: sid)
        }
    }
}

struct ScrollPage<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView { VStack(alignment: .leading, spacing: 12) { content }.padding(16) }.screenBackground()
    }
}

/// U01: promise, sample without permissions, privacy explanation. No microphone prompt here.
struct WelcomeView: View {
    @ObservedObject var model: AppModel
    @State private var create = true
    @State private var email = ""
    @State private var password = ""
    @State private var name = ""
    @State private var adult = false
    var body: some View {
        ScrollPage {
            Eyebrow(L("app_name"))
            Text(L("welcome_promise")).font(.largeTitle.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            Text(L("welcome_sub")).foregroundStyle(MS.text)
            Card {
                Text(L("welcome_listens_title")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("welcome_listens_body"))
                Text(L("welcome_helps_title")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("welcome_helps_body"))
                Text(L("welcome_stop_title")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("welcome_stop_body"))
            }
            SecondaryButton(L("welcome_sample")) { model.showSample = true }
            Chips(options: [("new", L("auth_new")), ("existing", L("auth_existing"))], selected: create ? "new" : "existing") { create = $0 == "new" }
            if create { TextField(L("auth_name"), text: $name).textFieldStyle(.roundedBorder) }
            TextField(L("auth_email"), text: $email).textFieldStyle(.roundedBorder).emailField()
            SecureField(L("auth_password"), text: $password).textFieldStyle(.roundedBorder)
            if create {
                CheckRow(text: L("auth_age_confirm"), on: $adult)
                SecondaryText(L("auth_age_note"))
            }
            SecondaryText(L("auth_privacy"))
            PrimaryButton(create ? L("auth_create") : L("auth_signin"), enabled: email.contains("@") && password.count >= 10 && (!create || adult) && !model.busy) {
                model.signIn(email: email.trimmingCharacters(in: .whitespaces), password: password, create: create, name: name.isEmpty ? nil : name,
                             ageConfirmed: adult)
            }
        }
    }
}

/// J1 step 1: explicitly labelled FICTIONAL sample — no microphone, account or AI.
struct SampleView: View {
    @ObservedObject var model: AppModel
    @State private var step = 0
    var body: some View {
        ScrollPage {
            Eyebrow(L("sample_eyebrow"))
            Banner(text: L("sample_banner"), tone: .caution)
            switch step {
            case 0:
                Text(L("sample_title")).font(.title2.bold()).foregroundStyle(MS.text)
                StatusPill(text: L("sample_not_recording"), tone: .neutral)
                Card { Eyebrow(L("live_latest")); SecondaryText(L("sample_line_meta")); Text(L("sample_line")).foregroundStyle(MS.text) }
                Card(raised: true) {
                    Eyebrow(L("sample_insight_eyebrow"))
                    Text(L("sample_insight")).font(.title3).foregroundStyle(MS.text)
                    SecondaryText(L("sample_insight_why"))
                }
                PrimaryButton(L("sample_next_ask")) { step = 1 }
            case 1:
                Card { Eyebrow(L("sample_you_asked")); Text(L("sample_question")).foregroundStyle(MS.text) }
                Card(raised: true) { Eyebrow(L("sample_answer_eyebrow")); Text(L("sample_answer")).foregroundStyle(MS.text); SecondaryText("▶ 18:42 · ▶ 23:15") }
                Card { Eyebrow(L("prov_ai_analysis")); Text(L("sample_analysis")).foregroundStyle(MS.text) }
                PrimaryButton(L("sample_next_recap")) { step = 2 }
            default:
                Text(L("sample_recap_title")).font(.title2.bold()).foregroundStyle(MS.text)
                Card { Eyebrow(L("sec_decisions")); Text(L("sample_decision")).foregroundStyle(MS.text) }
                Card { Eyebrow(L("sec_open_questions")); Text(L("sample_open")).foregroundStyle(MS.text) }
                SecondaryText(L("sample_choose_note"))
                PrimaryButton(L("welcome_get_started")) { model.showSample = false }
            }
            SecondaryButton(L("action_close")) { model.showSample = false }
        }
    }
}

/// U02 Home: Start Companion dominates; readiness; active session; recent memory.
struct HomeView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    var body: some View {
        ScrollPage {
            Eyebrow(L("home_eyebrow"))
            Text(L("home_title")).font(.largeTitle.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            SecondaryText(L("home_sub"))
            Card(raised: true) {
                Text(L("home_start_title")).font(.headline).foregroundStyle(MS.text)
                let output = model.pref("default_output") == "PRIVATE_VOICE" ? L("output_private_voice") : model.pref("default_output") == "BOTH" ? L("output_both") : L("output_silent_text")
                SecondaryText(L("home_readiness", live.route.input.replacingOccurrences(of: "_", with: " "), output))
                PrimaryButton(L("home_start")) { model.push(.contextChooser) }
                if let last = model.pref("last_context") { LinkText(L("home_start_again", contextName(last))) { model.chooseContext(last, preset: nil) } }
            }
            ForEach(model.active) { s in
                Card { StatusPill(text: L("home_active", stateName(s.state)), tone: .accent); Text(s.title).foregroundStyle(MS.text)
                    SecondaryButton(L("action_return_to_session")) { model.openActive(s.sessionId) } }
            }
            HStack {
                SecondaryButton(L("home_interview_practice")) { model.loadInterview(); model.push(.interview) }
                SecondaryButton(L("home_study")) { model.loadReviews(); model.push(.study) }
            }
            if model.recent.isEmpty {
                SecondaryText(L("home_empty"))
            } else {
                Eyebrow(L("home_recent"))
                ForEach(model.recent) { s in
                    Button { model.openRecap(s.sessionId) } label: {
                        Card { Text(s.title).font(.headline).foregroundStyle(MS.text)
                            SecondaryText(sessionMeta(s.context, s.sourceWatermarkMs, s.decisions, s.openItems)) }
                    }.buttonStyle(.plain)
                }
                LinkText(L("home_all_sessions")) { model.loadSessions(reset: true); model.push(.sessions) }
            }
        }
        .refreshable { await model.refreshHome() }
    }
}

let contextSubs: [(String, String)] = [("MEETING", "ctx_meeting_sub"), ("LEARNING", "ctx_learning_sub"), ("INTERVIEW", "ctx_interview_sub"),
                                       ("CONVERSATION", "ctx_conversation_sub")]
/// Presets are wire identifiers shared with backend policy (app/domain/policy.py); only their labels are localized.
let presets: [String: [String]] = [
    "MEETING": ["Architecture review", "Team standup", "Customer discussion", "Strategy meeting", "Sales discovery", "Other"],
    "LEARNING": ["Lecture", "Tutorial", "Seminar", "Workshop", "Talk/Seminar (research)", "Study group"],
    "INTERVIEW": ["System design", "Behavioral", "Coding", "AI / ML", "Cloud architecture", "Product"],
    "CONVERSATION": ["Mentoring", "Networking", "Language exchange", "Everyday conversation", "Brainstorming", "Trusted family discussion",
                     "Personal coaching", "Medical consultation", "Legal consultation", "Financial consultation"],
]
let sensitivePresets: Set<String> = ["Trusted family discussion", "Personal coaching", "Medical consultation", "Legal consultation", "Financial consultation"]
let presetKeys: [String: String] = [
    "Architecture review": "preset_architecture_review", "Team standup": "preset_team_standup", "Customer discussion": "preset_customer_discussion",
    "Strategy meeting": "preset_strategy_meeting", "Sales discovery": "preset_sales_discovery", "Other": "preset_other", "Lecture": "preset_lecture",
    "Tutorial": "preset_tutorial", "Seminar": "preset_seminar", "Workshop": "preset_workshop", "Talk/Seminar (research)": "preset_research_talk",
    "Study group": "preset_study_group", "System design": "preset_system_design", "Behavioral": "preset_behavioral", "Coding": "preset_coding",
    "AI / ML": "preset_ai_ml", "Cloud architecture": "preset_cloud_architecture", "Product": "preset_product", "Mentoring": "preset_mentoring",
    "Networking": "preset_networking", "Language exchange": "preset_language_exchange", "Everyday conversation": "preset_everyday",
    "Brainstorming": "preset_brainstorming", "Trusted family discussion": "preset_family", "Personal coaching": "preset_coaching",
    "Medical consultation": "preset_medical", "Legal consultation": "preset_legal", "Financial consultation": "preset_financial",
]
func presetLabel(_ p: String) -> String { presetKeys[p].map { L($0) } ?? p }

/// U03: four cards, remembers the last choice; context changes suggestions, never permissions.
struct ContextChooserView: View {
    @ObservedObject var model: AppModel
    @State private var ctx = "MEETING"
    @State private var preset: String?
    var body: some View {
        ScrollPage {
            Text(L("chooser_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            ForEach(contextSubs, id: \.0) { id, sub in
                Button { ctx = id; preset = nil } label: {
                    Card(raised: ctx == id) { Text((ctx == id ? "✓ " : "") + contextName(id)).font(.headline).foregroundStyle(MS.text); SecondaryText(L(sub)) }
                }.buttonStyle(.plain).accessibilityAddTraits(ctx == id ? .isSelected : [])
            }
            Eyebrow(L("chooser_preset"))
            Chips(options: (presets[ctx] ?? []).map { ($0, presetLabel($0)) }, selected: preset) { preset = preset == $0 ? nil : $0 }
            if ctx == "INTERVIEW" { SecondaryButton(L("chooser_mock_instead")) { model.loadInterview(); model.push(.interview) } }
            PrimaryButton(L("action_continue")) { model.chooseContext(ctx, preset: preset) }
        }
        .navigationTitle(L("home_start"))
        .onAppear { if let last = model.pref("last_context") { ctx = last } }
    }
}

func projectKindName(_ kind: String?) -> String {
    switch kind { case "COURSE": L("kind_course"); case "INTERVIEW_GOAL": L("kind_goal"); default: L("kind_project") }
}

/// U04 Preflight: every hard gate is visible; no start on an unresolved gate. Mic permission is requested here.
struct PreflightView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    var body: some View {
        let d = model.draft
        let yes = L("answer_yes_permitted"), no = L("answer_no_not_sure")
        ScrollPage {
            Text(L("preflight_title", contextName(d.context))).font(.title2.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            TextField(L("preflight_session_title"), text: $model.draft.title).textFieldStyle(.roundedBorder)
            ProjectPicker(model: model, kind: d.context == "LEARNING" ? "COURSE" : d.context == "INTERVIEW" ? "INTERVIEW_GOAL" : "PROJECT")
            if d.context == "INTERVIEW" {
                Card {
                    Text(L("interview_rules_title")).font(.headline).foregroundStyle(MS.text)
                    SecondaryText(L("interview_rules_sub"))
                    Text(L("interview_may_record")).foregroundStyle(MS.text)
                    Chips(options: [("yes", yes), ("no", no)], selected: d.recordingAllowed.map { $0 ? "yes" : "no" }) { v in
                        model.draft.recordingAllowed = v == "yes"; model.draft.captureSource = v == "yes" ? "PHONE_MIC" : "NONE"
                    }
                    Text(L("interview_ai_permitted")).foregroundStyle(MS.text)
                    Chips(options: [("yes", yes), ("no", no)], selected: d.aiAllowed.map { $0 ? "yes" : "no" }) { v in
                        model.draft.aiAllowed = v == "yes"; if v != "yes" { model.draft.assistance = "LISTENER" }
                    }
                    if d.recordingAllowed == false { Banner(text: L("interview_no_recording"), tone: .caution) }
                    if d.aiAllowed == false { Banner(text: L("interview_no_ai"), tone: .caution) }
                }
            }
            if let p = d.preset, sensitivePresets.contains(p) {
                Card {
                    Text(L("sensitive_title")).font(.headline).foregroundStyle(MS.text)
                    SecondaryText(L("sensitive_body"))
                    if d.assistance == "COMPANION" { CheckRow(text: L("sensitive_opt_in"), on: $model.draft.sensitiveOptIn) }
                }
            }
            Card {
                Text(L("preflight_audio_source")).font(.headline).foregroundStyle(MS.text)
                Chips(options: [("PHONE_MIC", L("source_phone_mic")), ("NONE", L("source_notes_only"))], selected: d.captureSource,
                      enabled: { $0 == "NONE" || d.context != "INTERVIEW" || d.recordingAllowed == true }) { model.draft.captureSource = $0 }
                if d.captureSource == "NONE" {
                    SecondaryText(L("copy_notes_only"))
                } else if !live.micGranted {
                    StatusPill(text: L("truth_mic_denied"), tone: .danger)
                    SecondaryText(L("preflight_mic_why"))
                    PrimaryButton(L("preflight_enable_mic")) { Task { _ = await AudioRoutes.requestRecordPermission(); model.runPreflight() } }
                    SecondaryText(L("preflight_mic_declined"))
                    #if os(iOS)
                    SecondaryButton(L("preflight_open_settings")) { if let u = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(u) } }
                    #endif
                } else if model.preflightRunning {
                    StatusPill(text: L("preflight_checking"), tone: .neutral)
                } else if let p = model.preflight {
                    let q = p.quality == "GOOD" ? L("quality_good") : p.quality == "POOR" ? L("quality_poor") : p.quality == "SILENT_OR_BLOCKED" ? L("quality_silent") : L("quality_no_frames")
                    StatusPill(text: L("preflight_input_result", p.route.input.replacingOccurrences(of: "_", with: " "), q), tone: p.quality == "GOOD" ? .accent : .caution)
                    ForEach(p.warnings, id: \.self) { SecondaryText("• \($0)") }
                    SecondaryButton(L("preflight_check_again")) { model.runPreflight() }
                } else {
                    SecondaryButton(L("preflight_check_audio")) { model.runPreflight() }
                }
            }
            if d.captureSource != "NONE" {
                Card {
                    Text(L("preflight_permission_title")).font(.headline).foregroundStyle(MS.text)
                    CheckRow(text: L("preflight_permission_check"), on: $model.draft.participantsInformed)
                    SecondaryText(L("preflight_permission_note"))
                    if d.context != "INTERVIEW" {
                        CheckRow(text: L("preflight_ai_check"), on: $model.draft.aiConsent)
                            .onChange(of: model.draft.aiConsent) { _, allowed in
                                if !allowed { model.draft.assistance = "LISTENER"; model.draft.intensity = "QUIET" }
                            }
                        SecondaryText(L("preflight_ai_note"))
                    }
                }
                Card {
                    Text(L("preflight_help_title")).font(.headline).foregroundStyle(MS.text)
                    let aiOk = d.context == "INTERVIEW" ? d.aiAllowed == true : d.aiConsent
                    AssistanceChips(selected: d.assistance, aiOk: aiOk) { v in
                        model.draft.assistance = v; if v == "COMPANION" && model.draft.intensity == "QUIET" { model.draft.intensity = "BALANCED" }
                    }
                    if d.assistance == "COMPANION" {
                        IntensityChips(selected: d.intensity) { model.draft.intensity = $0 }
                        SecondaryText(L("intensity_balanced_note"))
                    }
                    Text(L("preflight_delivery")).foregroundStyle(MS.text)
                    OutputChips(selected: d.output) { model.draft.output = $0 }
                    if d.output != "TEXT" {
                        if live.privateRouteVerified { StatusPill(text: L("voice_verified_device", live.route.outputDeviceName ?? L("voice_earbuds")), tone: .accent) }
                        else { SecondaryButton(L("voice_test_earbuds")) { model.push(.voice) } }
                    }
                }
                Card {
                    Text(L("preflight_processing_title")).font(.headline).foregroundStyle(MS.text)
                    SecondaryText(L("preflight_processing_body"))
                }
            }
            ForEach(model.blockers(), id: \.self) { SecondaryText("• \($0)") }
            SecondaryText(L("copy_consent_line"))
            PrimaryButton(d.captureSource == "NONE" ? L("preflight_open_notes") : L("preflight_start"), enabled: model.blockers().isEmpty && !model.busy) { model.startSession() }
        }
        .navigationTitle(L("preflight_eyebrow"))
    }
}

struct AssistanceChips: View {
    let selected: String
    let aiOk: Bool
    let onSelect: (String) -> Void
    var body: some View {
        Chips(options: [("LISTENER", L("assist_listener")), ("ASK", L("assist_ask")), ("COMPANION", L("assist_companion"))], selected: selected,
              enabled: { $0 == "LISTENER" || aiOk }, onSelect: onSelect)
    }
}

struct IntensityChips: View {
    let selected: String
    let onSelect: (String) -> Void
    var body: some View {
        Chips(options: [("QUIET", L("intensity_quiet")), ("BALANCED", L("intensity_balanced")), ("ACTIVE", L("intensity_active"))], selected: selected, onSelect: onSelect)
    }
}

struct OutputChips: View {
    let selected: String
    var enabled: (String) -> Bool = { _ in true }
    let onSelect: (String) -> Void
    var body: some View {
        Chips(options: [("TEXT", L("output_text")), ("PRIVATE_VOICE", L("output_private_voice")), ("BOTH", L("output_both"))], selected: selected,
              enabled: enabled, onSelect: onSelect)
    }
}

/// Optional grouping: a project (Meeting), a course (Learning) or an interview goal. Scopes briefs, decisions and Ask.
struct ProjectPicker: View {
    @ObservedObject var model: AppModel
    let kind: String
    @State private var creating = false
    @State private var title = ""
    var body: some View {
        // Only groupings in the session's own space: Personal and Work never mix.
        let options = model.projects.filter { $0["kind"]?.string == kind && $0["space_id"]?.string == model.draft.spaceId }
        Card {
            Text(L("picker_title", projectKindName(kind))).font(.headline).foregroundStyle(MS.text)
            SecondaryText(L(kind == "COURSE" ? "picker_course_note" : kind == "INTERVIEW_GOAL" ? "picker_goal_note" : "picker_project_note"))
            Chips(options: [("", L("picker_none"))] + options.map { ($0["project_id"]?.string ?? "", $0["title"]?.string ?? "") },
                  selected: model.draft.projectId ?? "") { model.draft.projectId = $0.isEmpty ? nil : $0 }
            if creating {
                TextField(L("picker_new_name", projectKindName(kind)), text: $title).textFieldStyle(.roundedBorder)
                HStack {
                    SecondaryButton(L("action_cancel")) { creating = false; title = "" }
                    SecondaryButton(L("action_create"), enabled: !title.trimmingCharacters(in: .whitespaces).isEmpty) {
                        model.createProject(kind: kind, title: title, meta: [:], attachToDraft: true); creating = false; title = ""
                    }
                }
            } else {
                LinkText(L("picker_new", projectKindName(kind))) { creating = true }
            }
        }
    }
}
