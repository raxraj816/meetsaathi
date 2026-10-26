import SwiftUI
#if os(iOS)
import UIKit
#endif

/// Mirror of backend DECISION_FLOW (app/memory/service.py); the server is authoritative and re-validates.
let decisionFlow: [String: [String]] = [
    "": ["PROPOSED", "DISCUSSED", "UNRESOLVED"],
    "PROPOSED": ["DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"],
    "DISCUSSED": ["ACCEPTED", "REJECTED", "DEFERRED", "UNRESOLVED"],
    "UNRESOLVED": ["DISCUSSED", "ACCEPTED", "REJECTED", "DEFERRED"],
    "DEFERRED": ["DISCUSSED", "ACCEPTED", "REJECTED", "UNRESOLVED"],
    "ACCEPTED": ["SUPERSEDED"],
    "REJECTED": ["SUPERSEDED", "DISCUSSED"],
    "SUPERSEDED": [],
]

/// S14 evidence + S22 decision/owner: provenance, the exact cited transcript revisions (with replay of the cited span
/// when audio is retained), decision history and owner confirmation. Recorded items are corrected at the source.
struct MemoryDetailView: View {
    @ObservedObject var model: AppModel
    let claimId: String
    @State private var editing = false
    @State private var text = ""
    @State private var note = ""
    @State private var owner = ""
    @State private var due = ""
    @State private var confirmDelete = false

    var body: some View {
        ScrollPage {
            if let c = model.claim, c["claim_id"]?.string == claimId {
                let kind = c["claim_kind"]?.string
                let recorded = c["provenance"]?.string == "RECORDED"
                let sid = c["session_id"]?.string
                StatusPill(text: c["provenance_label"]?.string ?? "", tone: recorded ? .accent : .neutral)
                if editing {
                    TextField(L("memory_edit"), text: $text, axis: .vertical).lineLimit(2...8).textFieldStyle(.roundedBorder)
                    HStack {
                        SecondaryButton(L("action_cancel")) { editing = false }
                        SecondaryButton(L("action_save"), enabled: !text.isEmpty) { model.editMemory(claimId, text: text, exclude: nil); editing = false }
                    }
                } else {
                    Text(c["text_value"]?.string ?? "").font(.title2.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
                }
                if let lt = c["long_text"]?.string { Text(lt).font(.subheadline).foregroundStyle(MS.text) }
                SecondaryText([humanize(kind), memoryStateName(c["memory_state"]?.string), c["session_title"]?.string, Dates.date(c["session_created_at"]?.string)]
                    .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                if c["memory_state"]?.string == "INVALIDATED" { Banner(text: L("memory_invalidated"), tone: .caution) }

                Card {
                    Text(L("memory_sources")).font(.headline).foregroundStyle(MS.text)
                    let sources = c["sources"]?.array ?? []
                    if sources.isEmpty { SecondaryText(L(recorded ? "memory_no_sources" : "memory_user_source")) }
                    ForEach(Array(sources.enumerated()), id: \.offset) { _, s in
                        let uid = s["utterance_id"]?.string ?? ""
                        SecondaryText([clockString(s["start_ms"]?.int64), s["speaker_label_snapshot"]?.string,
                                       s["is_final"]?.bool == true ? L("label_final") : L("label_provisional")].compactMap { $0 }.joined(separator: " · "))
                        Text("“\(s["transcript"]?.string ?? "")”").font(.subheadline).foregroundStyle(MS.text)
                        if s["is_current"]?.bool == false { Banner(text: L("memory_source_corrected"), tone: .caution) }
                        if s["replay_available"]?.bool == true, let sid {
                            EvidenceButton(player: model.evidence, utteranceId: uid, startMs: s["start_ms"]?.int64) { model.playEvidence(sid, uid) }
                        } else {
                            SecondaryText(L("evidence_deleted"))
                        }
                    }
                }

                if kind == "DECISION" { decisionCard(c) }
                if kind == "ACTION" || kind == "COMMITMENT" { ownerCard(c) }

                Card {
                    Text(L("memory_controls")).font(.headline).foregroundStyle(MS.text)
                    CheckRow(text: L("memory_exclude"), on: Binding(get: { c["exclude_from_suggestions"]?.bool ?? false },
                                                                     set: { model.editMemory(claimId, text: nil, exclude: $0) }))
                    if recorded { SecondaryText(L("memory_recorded_edit_note")) }
                    else if !editing { LinkText(L("memory_edit")) { text = c["text_value"]?.string ?? ""; editing = true } }
                    if let sid { LinkText(L("memory_open_session")) { model.openRecap(sid) } }
                    if confirmDelete {
                        ConfirmDanger(prompt: L("memory_delete_confirm"), confirm: L("action_delete"), onCancel: { confirmDelete = false }) {
                            confirmDelete = false; model.deleteMemory(claimId)
                        }
                    } else { SecondaryButton(L("memory_delete"), danger: true) { confirmDelete = true } }
                }
            } else {
                SecondaryText(L("label_loading"))
            }
        }
        .navigationTitle(L("memory_eyebrow"))
        .onDisappear { model.evidence.stop() }
        .onChange(of: model.claim?["version"]?.int64) { _, _ in
            owner = model.claim?["owner_label"]?.string ?? ""; due = model.claim?["due_text"]?.string ?? ""
        }
    }

    @ViewBuilder func decisionCard(_ c: JSONValue) -> some View {
        let status = c["decision_status"]?.string
        Card(raised: true) {
            Text(L("decision_title")).font(.headline).foregroundStyle(MS.text)
            StatusPill(text: decisionName(status), tone: status == "ACCEPTED" ? .accent : .caution)
            SecondaryText(L("decision_note"))
            let next = decisionFlow[status ?? ""] ?? []
            if !next.isEmpty {
                TextField(L("decision_reason_hint"), text: $note).textFieldStyle(.roundedBorder)
                Chips(options: next.map { ($0, decisionName($0)) }, selected: nil) { model.setDecision(claimId, to: $0, note: String(note.prefix(300))); note = "" }
            }
            let history = c["decision_history"]?.array ?? []
            if !history.isEmpty {
                Eyebrow(L("decision_history"))
                ForEach(Array(history.enumerated()), id: \.offset) { _, e in
                    SecondaryText([Dates.dateTime(e["created_at"]?.string), "\(e["from_state"]?.string.map(decisionName) ?? "—") → \(decisionName(e["to_state"]?.string))",
                                   humanize(e["actor"]?.string), e["note"]?.string].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                }
            }
        }
    }

    @ViewBuilder func ownerCard(_ c: JSONValue) -> some View {
        let confirmed = c["owner_confirmed"]?.bool ?? false
        Card(raised: true) {
            Text(L("owner_title")).font(.headline).foregroundStyle(MS.text)
            StatusPill(text: ownerText(c["owner_label"]?.string, confirmed: confirmed), tone: confirmed ? .accent : .caution)
            SecondaryText(L("owner_note"))
            TextField(L("owner_hint"), text: $owner).textFieldStyle(.roundedBorder)
            TextField(L("owner_due_hint"), text: $due).textFieldStyle(.roundedBorder)
            HStack {
                SecondaryButton(L("owner_confirm"), enabled: !owner.trimmingCharacters(in: .whitespaces).isEmpty) { model.confirmOwner(claimId, owner: String(owner.prefix(120)), due: String(due.prefix(120))) }
                if c["owner_label"]?.string != nil { SecondaryButton(L("owner_clear")) { model.confirmOwner(claimId, owner: "", due: "") } }
            }
        }
        .onAppear { owner = c["owner_label"]?.string ?? ""; due = c["due_text"]?.string ?? "" }
    }
}

private let shareSections: [(String, String)] = [("summary", "share_sec_summary"), ("decisions", "sec_decisions"), ("actions", "sec_actions"),
                                                 ("questions", "share_sec_questions"), ("notes", "sec_notes")]

/// M23: audience-specific share with a redaction preview before any link exists; expiry and revoke; never audio.
struct ShareView: View {
    @ObservedObject var model: AppModel
    let sessionId: String
    @State private var sections: Set<String> = ["summary", "decisions", "actions", "questions"]
    @State private var redact = true
    @State private var hours = 72
    @State private var password = ""

    var body: some View {
        ScrollPage {
            Text(L("share_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            SecondaryText(L("share_note"))
            Card {
                Text(L("share_include")).font(.headline).foregroundStyle(MS.text)
                ForEach(shareSections, id: \.0) { key, label in
                    CheckRow(text: L(label), on: Binding(get: { sections.contains(key) }, set: { if $0 { sections.insert(key) } else { sections.remove(key) } }))
                }
                CheckRow(text: L("share_redact"), on: $redact)
                SecondaryText(L("share_expires"))
                Chips(options: [("24", LP("hours", 24)), ("72", LP("days", 3)), ("168", LP("days", 7)), ("720", LP("days", 30))], selected: String(hours)) { hours = Int($0) ?? 72 }
                SecondaryButton(L("share_preview"), enabled: !sections.isEmpty && !model.busy) {
                    model.shareRequest(sessionId, sections: shareSections.map(\.0).filter(sections.contains), redact: redact, hours: hours, confirm: false)
                }
            }
            if let p = model.sharePreview, !p.isNull {
                Card(raised: true) {
                    Eyebrow(L("share_preview_eyebrow"))
                    Text(p["title"]?.string ?? "").font(.headline).foregroundStyle(MS.text)
                    SecondaryText([p["date"]?.string, p["context"]?.string.map(contextName)].compactMap { $0 }.joined(separator: " · "))
                    ForEach(Array((p["summary"]?.array ?? []).enumerated()), id: \.offset) { _, s in Text(s.string ?? "").font(.subheadline).foregroundStyle(MS.text) }
                    ForEach([("decisions", "sec_decisions"), ("actions", "sec_actions"), ("questions", "share_sec_questions"), ("notes", "sec_notes")], id: \.0) { key, label in
                        let items = p[key]?.array ?? []
                        if !items.isEmpty {
                            Eyebrow(L(label))
                            ForEach(Array(items.enumerated()), id: \.offset) { _, i in
                                Text("• " + (i["text"]?.string ?? "")).font(.subheadline).foregroundStyle(MS.text)
                                let meta = [i["status"]?.string.map(decisionName), i["owner"]?.string, i["label"]?.string].compactMap { $0 }.joined(separator: " · ")
                                if !meta.isEmpty { SecondaryText(meta) }
                            }
                        }
                    }
                    SecondaryText(p["notice"]?.string ?? "")
                }
                if model.shareLink == nil {
                    PrimaryButton(L("share_create"), enabled: !model.busy) {
                        model.shareRequest(sessionId, sections: shareSections.map(\.0).filter(sections.contains), redact: redact, hours: hours, confirm: true)
                    }
                }
            }
            if let l = model.shareLink, let token = l["token"]?.string {
                let url = model.shareURL(token)
                Card(raised: true) {
                    StatusPill(text: L("share_link_ready", Dates.dateTime(l["expires_at"]?.string) ?? ""), tone: .accent)
                    SecondaryText(L("share_link_once"))
                    Text(url.absoluteString).font(.footnote).foregroundStyle(MS.text).textSelection(.enabled)
                    HStack {
                        #if os(iOS)
                        SecondaryButton(L("share_copy")) { UIPasteboard.general.string = url.absoluteString; model.message = L("share_copied") }
                        #endif
                        ShareLink(item: url) { Text(L("share_send")).font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, minHeight: MS.minTouch) }
                            .foregroundStyle(MS.text).overlay(RoundedRectangle(cornerRadius: MS.radiusSmall).stroke(MS.border, lineWidth: 1))
                    }
                }
            }
            if !model.shares.isEmpty {
                Eyebrow(L("share_existing"))
                ForEach(Array(model.shares.enumerated()), id: \.offset) { _, s in
                    let revoked = s["revoked_at"].map { !$0.isNull } ?? false
                    Card {
                        SecondaryText([L("share_created_at", Dates.dateTime(s["created_at"]?.string) ?? ""),
                                       revoked ? L("share_revoked") : L("share_expires_at", Dates.dateTime(s["expires_at"]?.string) ?? ""),
                                       s["stale"]?.bool == true ? L("share_stale") : nil].compactMap { $0 }.joined(separator: " · "))
                        if !revoked, let id = s["share_id"]?.string { LinkText(L("share_revoke")) { model.revokeShare(sessionId, id) } }
                    }
                }
            }
            Card {
                Text(L("share_export_title")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("share_export_note"))
                SecureField(L("you_password"), text: $password).textFieldStyle(.roundedBorder)
                SecondaryButton(L("share_export"), enabled: password.count >= 10 && !model.busy) { model.requestExport(password: password, sessionId: sessionId); password = "" }
                ExportStatusView(model: model, scope: sessionId)
            }
        }
        .navigationTitle(L("share_eyebrow"))
    }
}

/// U11 session timeline: every session, newest first, paged.
struct SessionsView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        ScrollPage {
            Text(L("sessions_title")).font(.title2.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            if model.sessionsLoaded && model.sessions.isEmpty { SecondaryText(L("home_empty")) }
            ForEach(model.sessions) { s in
                Button { model.openRecap(s.sessionId) } label: {
                    Card {
                        Text(s.title).font(.headline).foregroundStyle(MS.text)
                        SecondaryText(sessionMeta(s.context, s.sourceWatermarkMs, s.decisions, s.openItems))
                        SecondaryText([Dates.date(s.createdAt) ?? "", stateName(s.state)].joined(separator: " · "))
                    }
                }.buttonStyle(.plain)
            }
            if model.sessionsCursor != nil { SecondaryButton(L("action_load_more"), enabled: !model.busy) { model.loadSessions(reset: false) } }
        }
        .navigationTitle(L("memories_sessions"))
    }
}

let kindFields: [String: [(String, String)]] = [
    "PROJECT": [("description", "field_description")],
    "COURSE": [("term", "field_term"), ("instructor_label", "field_instructor"), ("syllabus_text", "field_syllabus")],
    "INTERVIEW_GOAL": [("company", "field_company"), ("stage", "field_stage"), ("interview_date", "field_interview_date"),
                       ("coding_language", "field_coding_language"), ("jd_text", "field_jd"), ("experience_notes", "field_experience")],
]
let longFields: Set<String> = ["description", "syllabus_text", "jd_text", "experience_notes"]

/// Create/edit form shared by projects, courses and interview goals (job description lives here).
struct ProjectForm: View {
    let kind: String
    let initialTitle: String
    let initial: JSONValue?
    let submit: String
    let busy: Bool
    let onSubmit: (String, [String: String]) -> Void
    @State private var title = ""
    @State private var values: [String: String] = [:]
    @State private var loaded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            TextField(L(kind == "INTERVIEW_GOAL" ? "field_role" : "field_title"), text: $title).textFieldStyle(.roundedBorder)
            ForEach(kindFields[kind] ?? [], id: \.0) { key, label in
                let binding = Binding(get: { values[key] ?? "" }, set: { values[key] = String($0.prefix(longFields.contains(key) ? 20000 : 200)) })
                if longFields.contains(key) {
                    TextField(L(label), text: binding, axis: .vertical).lineLimit(3...10).textFieldStyle(.roundedBorder)
                } else {
                    TextField(L(label), text: binding).textFieldStyle(.roundedBorder)
                }
                if key == "jd_text" { SecondaryText(L("field_jd_note")) }
            }
            SecondaryButton(submit, enabled: !title.trimmingCharacters(in: .whitespaces).isEmpty && !busy) {
                onSubmit(title, Dictionary(uniqueKeysWithValues: (kindFields[kind] ?? []).map { ($0.0, values[$0.0] ?? "") }))
            }
        }
        .onAppear {
            guard !loaded else { return }
            loaded = true
            title = initialTitle
            for (k, _) in kindFields[kind] ?? [] { values[k] = initial?[k]?.string ?? "" }
        }
    }
}

/// Projects, courses and interview goals: the scopes for briefs, decision ledgers and Ask.
struct ProjectsView: View {
    @ObservedObject var model: AppModel
    @State private var kind = "PROJECT"
    @State private var creating = false
    var body: some View {
        ScrollPage {
            Text(L("projects_title")).font(.title2.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            SecondaryText(L("projects_note"))
            ForEach(["PROJECT", "COURSE", "INTERVIEW_GOAL"], id: \.self) { k in
                let items = model.projects.filter { $0["kind"]?.string == k }
                if !items.isEmpty {
                    Eyebrow(projectKindName(k))
                    ForEach(Array(items.enumerated()), id: \.offset) { _, p in
                        Button { if let id = p["project_id"]?.string { model.openProject(id) } } label: {
                            Card {
                                Text(p["title"]?.string ?? "").font(.headline).foregroundStyle(MS.text)
                                SecondaryText(Dates.date(p["last_session_at"]?.string).map { L("projects_last_session", $0) } ?? L("projects_no_sessions"))
                            }
                        }.buttonStyle(.plain)
                    }
                }
            }
            if model.projects.isEmpty { SecondaryText(L("projects_empty")) }
            Card {
                if creating {
                    Text(L("projects_new")).font(.headline).foregroundStyle(MS.text)
                    Chips(options: ["PROJECT", "COURSE", "INTERVIEW_GOAL"].map { ($0, projectKindName($0)) }, selected: kind) { kind = $0 }
                    ProjectForm(kind: kind, initialTitle: "", initial: nil, submit: L("action_create"), busy: model.busy) { title, meta in
                        model.createProject(kind: kind, title: title, meta: meta); creating = false
                    }.id(kind)
                    LinkText(L("action_cancel")) { creating = false }
                } else {
                    SecondaryButton(L("projects_new")) { creating = true }
                }
            }
        }
        .navigationTitle(L("memories_projects"))
        .onAppear { model.loadProjects() }
    }
}

/// One project/course/goal: sessions, decision ledger (M19), next-time brief (M22/S21), editable context, delete.
struct ProjectView: View {
    @ObservedObject var model: AppModel
    let projectId: String
    @State private var editing = false
    @State private var confirmDelete = false
    var body: some View {
        ScrollPage {
            if let p = model.project, p["project_id"]?.string == projectId {
                let kind = p["kind"]?.string ?? "PROJECT"
                let meta = p["metadata"]
                Eyebrow(projectKindName(kind))
                Text(p["title"]?.string ?? "").font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
                ForEach(kindFields[kind] ?? [], id: \.0) { k, label in
                    if let v = meta?[k]?.string, !v.isEmpty { SecondaryText(L(label) + ": " + (longFields.contains(k) && v.count > 240 ? String(v.prefix(240)) + "…" : v)) }
                }
                if kind == "INTERVIEW_GOAL" {
                    if (meta?["jd_text"]?.string ?? "").isEmpty { Banner(text: L("interview_jd_missing"), tone: .caution) }
                    PrimaryButton(L("project_warmup"), enabled: !model.busy) {
                        model.startMock(topic: meta?["stage"]?.string ?? p["title"]?.string ?? "", difficulty: "Warmup", goal: projectId, maxQuestions: 3)
                    }
                }
                if editing {
                    Card {
                        ProjectForm(kind: kind, initialTitle: p["title"]?.string ?? "", initial: meta, submit: L("action_save"), busy: model.busy) { title, m in
                            model.updateProject(projectId, title: title, meta: m); editing = false
                        }
                        LinkText(L("action_cancel")) { editing = false }
                    }
                } else { LinkText(L("action_edit")) { editing = true } }

                Card(raised: true) {
                    Text(L(kind == "COURSE" ? "brief_title_course" : "brief_title")).font(.headline).foregroundStyle(MS.text)
                    if let b = model.brief, !b.isNull {
                        if b["empty"]?.bool == true { SecondaryText(b["message"]?.string ?? L("brief_empty")) }
                        else {
                            SecondaryText(L("brief_scope_note"))
                            briefGroup(L("brief_last_agreed"), b["last_agreed"]?.array ?? [])
                            briefGroup(L("brief_still_open"), b["still_open"]?.array ?? [])
                            let qs = b["questions_worth_asking"]?.array ?? []
                            if !qs.isEmpty {
                                Eyebrow(b["questions_label"]?.string ?? L("label_suggests"))
                                ForEach(Array(qs.enumerated()), id: \.offset) { _, q in Text("? " + (q.string ?? "")).font(.subheadline).foregroundStyle(MS.text) }
                            } else if b["questions_unavailable"]?.bool == true { SecondaryText(L("brief_questions_unavailable")) }
                        }
                    } else {
                        SecondaryButton(L("brief_prepare"), enabled: !model.busy) { model.loadBrief(projectId) }
                    }
                }
                if kind != "INTERVIEW_GOAL" {
                    Card {
                        Text(L("ledger_title")).font(.headline).foregroundStyle(MS.text)
                        if model.decisions.isEmpty { SecondaryText(L("ledger_empty")) }
                        ForEach(Array(model.decisions.enumerated()), id: \.offset) { _, d in
                            Button { if let id = d["claim_id"]?.string { model.openMemory(id) } } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(d["text_value"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                                    SecondaryText([decisionName(d["decision_status"]?.string), d["session_title"]?.string, Dates.date(d["session_date"]?.string),
                                                   d["stale"]?.bool == true ? L("mstate_invalidated") : nil].compactMap { $0 }.joined(separator: " · "))
                                    let h = d["history"]?.array ?? []
                                    if h.count > 1 { SecondaryText(h.map { decisionName($0["to"]?.string) }.joined(separator: " → ")) }
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }.buttonStyle(.plain)
                        }
                    }
                }
                let sessions = p["sessions"]?.array ?? []
                Eyebrow(L("memories_sessions"))
                if sessions.isEmpty { SecondaryText(L("projects_no_sessions")) }
                ForEach(Array(sessions.enumerated()), id: \.offset) { _, s in
                    Button { if let id = s["session_id"]?.string { model.openRecap(id) } } label: {
                        Card { Text(s["title"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                            SecondaryText([Dates.date(s["created_at"]?.string), clockString(s["source_watermark_ms"]?.int64), stateName(s["state"]?.string)]
                                .compactMap { $0 }.joined(separator: " · ")) }
                    }.buttonStyle(.plain)
                }
                let mocks = p["mocks"]?.array ?? []
                if !mocks.isEmpty {
                    Eyebrow(L("interview_recent"))
                    ForEach(Array(mocks.enumerated()), id: \.offset) { _, m in
                        Button { if let id = m["mock_id"]?.string { model.loadMock(id); model.push(.mock(id)) } } label: {
                            Card { Text("\(m["topic"]?.string ?? "") · \(m["difficulty"]?.string ?? "")").font(.subheadline).foregroundStyle(MS.text)
                                SecondaryText([humanize(m["state"]?.string), Dates.date(m["created_at"]?.string)].compactMap { $0 }.joined(separator: " · ")) }
                        }.buttonStyle(.plain)
                    }
                }
                if confirmDelete {
                    ConfirmDanger(prompt: LP("project_delete_confirm", sessions.count), confirm: L("action_delete"), onCancel: { confirmDelete = false }) {
                        confirmDelete = false; model.deleteProject(projectId)
                    }
                } else {
                    SecondaryButton(L(kind == "COURSE" ? "project_delete_course" : kind == "INTERVIEW_GOAL" ? "project_delete_goal" : "project_delete_project"), danger: true) {
                        confirmDelete = true
                    }
                }
            } else {
                SecondaryText(L("label_loading"))
            }
        }
        .navigationTitle(L("memories_projects"))
    }

    @ViewBuilder func briefGroup(_ title: String, _ items: [JSONValue]) -> some View {
        if !items.isEmpty {
            Eyebrow(title)
            ForEach(Array(items.enumerated()), id: \.offset) { _, o in
                Button { if let id = o["claim_id"]?.string { model.openMemory(id) } } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("• " + (o["text_value"]?.string ?? "")).font(.subheadline).foregroundStyle(MS.text)
                        let k = o["claim_kind"]?.string
                        SecondaryText([humanize(k), o["decision_status"]?.string.map(decisionName),
                                       (k == "ACTION" || k == "COMMITMENT") ? ownerText(o["owner_label"]?.string, confirmed: o["owner_confirmed"]?.bool ?? false) : nil,
                                       o["session_title"]?.string, Dates.date(o["session_date"]?.string)].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain)
            }
        }
    }
}
