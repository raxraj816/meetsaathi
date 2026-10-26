import SwiftUI

/// Learning Study Studio: retrieval practice (answer hidden until attempted) + flexible review plan (no streaks).
struct StudyView: View {
    @ObservedObject var model: AppModel
    @State private var answers: [String: String] = [:]
    var body: some View {
        ScrollPage {
            Text(L("study_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            ForEach(Array((model.study?["items"]?.array ?? []).enumerated()), id: \.offset) { _, it in
                let id = it["item_id"]?.string ?? ""
                Card {
                    Eyebrow((it["concept"]?.string ?? L("study_concept")) + " · " + humanize(it["source_kind"]?.string))
                    Text(it["prompt"]?.string ?? "").foregroundStyle(MS.text)
                    TextField(L("study_answer_hint"), text: Binding(get: { answers[id] ?? "" }, set: { answers[id] = String($0.prefix(4000)) }), axis: .vertical)
                        .lineLimit(2...6).textFieldStyle(.roundedBorder)
                    SecondaryButton(L("study_check"), enabled: !(answers[id] ?? "").isEmpty && !model.busy) { model.attempt(id, answers[id] ?? "") }
                }
            }
            if let a = model.lastAttempt {
                Card(raised: true) {
                    let v = a["verdict"]?.string
                    StatusPill(text: v == "CORRECT" ? L("verdict_correct") : v == "PARTIAL" ? L("verdict_partial") : v == "INCORRECT" ? L("verdict_incorrect") : humanize(v),
                               tone: v == "CORRECT" ? .accent : v == "PARTIAL" ? .caution : v == "INCORRECT" ? .danger : .neutral)
                    Text(a["feedback"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                    if let k = a["key_points"]?.string { SecondaryText(L("study_key_points", k)) }
                    if let n = a["note"]?.string { SecondaryText(n) }
                }
            }
            Eyebrow(L("study_review_plan"))
            if model.reviews.isEmpty { SecondaryText(L("study_review_empty")) }
            ForEach(Array(model.reviews.enumerated()), id: \.offset) { _, r in
                let key = r["concept_key"]?.string ?? ""
                let space = r["space_id"]?.string ?? ""
                Card {
                    Text(r["concept"]?.string ?? key).foregroundStyle(MS.text)
                    SecondaryText([humanize(r["lineage_state"]?.string), L("study_next_review", Dates.date(r["due_at"]?.string) ?? ""),
                                   r["due"]?.bool == true ? L("study_due_now") : nil].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    HStack {
                        SecondaryButton(L("study_snooze")) { model.reviewAction(space: space, key: key, action: "SNOOZE", days: 1) }
                        SecondaryButton(L("action_remove")) { model.reviewAction(space: space, key: key, action: "REMOVE", days: nil) }
                    }
                }
            }
        }
        .navigationTitle(L("study_eyebrow"))
        .onAppear { model.loadReviews() }
    }
}

private let mockTopics: [(String, String)] = [("System Design", "preset_system_design"), ("Behavioral", "preset_behavioral"), ("Coding", "preset_coding"),
                                              ("AI / ML", "preset_ai_ml"), ("Cloud Architecture", "preset_cloud_architecture"), ("Product", "preset_product")]
private let difficulties: [(String, String)] = [("Warmup", "difficulty_warmup"), ("Challenging", "difficulty_challenging"), ("Expert", "difficulty_expert")]

/// Interview home: goals (with job description) + practice (always available; no third-party permission needed).
struct InterviewView: View {
    @ObservedObject var model: AppModel
    @State private var topic = "System Design"
    @State private var difficulty = "Challenging"
    @State private var goal: String?
    @State private var creating = false
    var body: some View {
        ScrollPage {
            Text(L("interview_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            SecondaryText(L("interview_note"))
            Card {
                Text(L("interview_goal")).font(.headline).foregroundStyle(MS.text)
                if !model.goals.isEmpty {
                    Chips(options: model.goals.map { ($0["project_id"]?.string ?? "", $0["title"]?.string ?? "") }, selected: goal) { goal = goal == $0 ? nil : $0 }
                    if let g = goal { LinkText(L("interview_open_goal")) { model.openProject(g) } }
                }
                if creating {
                    ProjectForm(kind: "INTERVIEW_GOAL", initialTitle: "", initial: nil, submit: L("interview_save_goal"), busy: model.busy) { title, meta in
                        model.createProject(kind: "INTERVIEW_GOAL", title: title, meta: meta); creating = false
                    }
                    LinkText(L("action_cancel")) { creating = false }
                } else {
                    LinkText(L("interview_new_goal")) { creating = true }
                }
            }
            Card {
                Text(L("interview_setup")).font(.headline).foregroundStyle(MS.text)
                Chips(options: mockTopics.map { ($0.0, L($0.1)) }, selected: topic) { topic = $0 }
                Chips(options: difficulties.map { ($0.0, L($0.1)) }, selected: difficulty) { difficulty = $0 }
                SecondaryText(L("interview_setup_note"))
                PrimaryButton(L("interview_start_mock"), enabled: !model.busy) { model.startMock(topic: topic, difficulty: difficulty, goal: goal) }
                SecondaryButton(L("interview_warmup"), enabled: !model.busy) { model.startMock(topic: topic, difficulty: "Warmup", goal: goal, maxQuestions: 3) }
                SecondaryText(L("interview_warmup_note"))
            }
            if !model.mocks.isEmpty {
                Eyebrow(L("interview_recent"))
                ForEach(Array(model.mocks.prefix(8).enumerated()), id: \.offset) { _, m in
                    Button { if let id = m["mock_id"]?.string { model.loadMock(id); model.push(.mock(id)) } } label: {
                        Card {
                            Text("\(m["topic"]?.string ?? "") · \(m["difficulty"]?.string ?? "")").foregroundStyle(MS.text)
                            SecondaryText([humanize(m["state"]?.string), Dates.date(m["created_at"]?.string),
                                           m["parent_mock_id"].map { $0.isNull ? nil : L("mock_retry_label") } ?? nil].compactMap { $0 }.joined(separator: " · "))
                        }
                    }.buttonStyle(.plain)
                }
            }
        }
        .navigationTitle(L("interview_eyebrow"))
    }
}

struct MockView: View {
    @ObservedObject var model: AppModel
    let mockId: String
    @State private var answer = ""
    var body: some View {
        ScrollPage {
            if let m = model.mock, m["mock"]?["mock_id"]?.string == mockId {
                if let f = m["mock"]?["settings"]?["focus"]?.string { Banner(text: L("mock_focus", f), tone: .accent) }
                ForEach(Array((m["turns"]?.array ?? []).enumerated()), id: \.offset) { _, t in
                    switch t["role"]?.string {
                    case "INTERVIEWER":
                        Card(raised: true) { Eyebrow(t["kind"]?.string == "FOLLOWUP" ? L("mock_followup") : L("mock_question")); Text(t["text_value"]?.string ?? "").foregroundStyle(MS.text) }
                    case "CANDIDATE":
                        Card { Eyebrow(L("mock_your_answer")); Text(t["text_value"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text) }
                    default:
                        SecondaryText((t["kind"]?.string == "HINT" ? L("mock_hint_prefix") + " " : "") + (t["text_value"]?.string ?? ""))
                    }
                }
                if let d = m["debrief"], !d.isNull {
                    debrief(d)
                } else if m["mock"]?["state"]?.string == "FINISHED" {
                    SecondaryButton(L("mock_get_feedback"), enabled: !model.busy) { model.requestDebrief(mockId) }
                } else {
                    TextField(L("mock_answer_hint"), text: $answer, axis: .vertical).lineLimit(4...12).textFieldStyle(.roundedBorder)
                    PrimaryButton(L("mock_submit"), enabled: !answer.isEmpty && !model.busy) { model.mockAction(mockId, "ANSWER", String(answer.prefix(12000))); answer = "" }
                    HStack {
                        SecondaryButton(L("mock_need_time")) { model.mockAction(mockId, "NEED_TIME", nil) }
                        SecondaryButton(L("mock_repeat")) { model.mockAction(mockId, "REPEAT", nil) }
                        SecondaryButton(L("mock_hint")) { model.mockAction(mockId, "HINT", nil) }
                    }
                    SecondaryButton(L("mock_finish")) { model.mockAction(mockId, "FINISH", nil) }
                }
            } else {
                SecondaryText(L("label_loading"))
            }
        }
        .navigationTitle(L("mock_eyebrow"))
    }

    @ViewBuilder func debrief(_ d: JSONValue) -> some View {
        if d["status"]?.string == "READY" {
            Card(raised: true) {
                Eyebrow(L("mock_debrief") + " · " + (d["evidence_level"]?.string ?? ""))
                Text(L("mock_strengths")).font(.headline).foregroundStyle(MS.text)
                ForEach(Array((d["strengths"]?.array ?? []).enumerated()), id: \.offset) { _, s in SecondaryText("✓ " + (s.string ?? "")) }
                Text(L("mock_improve")).font(.headline).foregroundStyle(MS.text)
                ForEach(Array((d["improvements"]?.array ?? []).enumerated()), id: \.offset) { _, s in SecondaryText("▲ " + (s.string ?? "")) }
                ForEach(Array((d["dimensions"]?.array ?? []).enumerated()), id: \.offset) { _, dim in
                    Eyebrow(dim["name"]?.string ?? "")
                    Text(dim["observation"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                    if let r = dim["repair"]?.string { SecondaryText(L("mock_try", r)) }
                    ForEach(Array((dim["evidence"]?.array ?? []).enumerated()), id: \.offset) { _, e in SecondaryText("“" + (e["excerpt"]?.string ?? "") + "”") }
                }
                let claims = d["uncertain_claims"]?.array ?? []
                if !claims.isEmpty {
                    Text(L("mock_check_claims")).font(.headline).foregroundStyle(MS.text)
                    ForEach(Array(claims.enumerated()), id: \.offset) { _, c in SecondaryText("? " + (c.string ?? "")) }
                }
                SecondaryText(d["disclaimer"]?.string ?? "")
            }
            let drills = Array(NSOrderedSet(array: ((d["next_drills"]?.array ?? []) + (d["improvements"]?.array ?? [])).compactMap(\.string).filter { !$0.isEmpty })
                .compactMap { $0 as? String }.prefix(4))
            if !drills.isEmpty {
                Card {
                    Text(L("mock_retry_title")).font(.headline).foregroundStyle(MS.text)
                    SecondaryText(L("mock_retry_note"))
                    ForEach(drills, id: \.self) { drill in SecondaryButton(drill, enabled: !model.busy) { model.retrySkill(mockId, focus: drill) } }
                }
            }
        } else {
            Banner(text: d["message"]?.string ?? L("mock_feedback_unavailable"), tone: .caution)
            if d["status"]?.string == "UNAVAILABLE" { SecondaryButton(L("mock_feedback_retry"), enabled: !model.busy) { model.requestDebrief(mockId) } }
        }
    }
}
