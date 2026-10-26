import SwiftUI
import UniformTypeIdentifiers

private let recapSections: [(String, String)] = [("decisions", "sec_decisions"), ("actions", "sec_actions"), ("commitments", "sec_commitments"),
    ("open_questions", "sec_open_questions"), ("risks", "sec_risks"), ("concepts", "sec_concepts"), ("lessons", "sec_lessons"), ("ideas", "sec_ideas"),
    ("bookmarks", "sec_bookmarks"), ("notes", "sec_notes"), ("recollections", "sec_recollections"), ("ai_suggestions", "sec_ai_suggestions")]

func memoryStateName(_ s: String?) -> String? {
    switch s { case "APPROVED": L("mstate_kept"); case "PENDING_REVIEW": L("mstate_pending"); case "INVALIDATED": L("mstate_invalidated")
    case nil: nil; default: humanize(s) }
}

/// U09/U10: capture stopped and finalization shown separately; outcomes first; deliberate keep / discard.
struct RecapView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var live: LiveSessionController
    let sessionId: String
    @State private var keep: Set<String> = []
    @State private var confirmDiscard = false
    @State private var confirmAudio = false
    @State private var exclude = false

    var body: some View {
        ScrollPage {
            if let r = model.recap, r["session_id"]?.string == sessionId {
                let state = r["state"]?.string
                let comp = r["completeness"]
                let notesOnly = comp?["notes_only"]?.bool == true
                let ended = ["COMPLETED", "COMPLETED_PARTIAL", "FINALIZATION_RETRYABLE"].contains(state ?? "")
                Eyebrow(L("recap_eyebrow"))
                Text(r["title"]?.string ?? "").font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
                SecondaryText([contextName(r["context"]?.string), clockString(r["duration_ms"]?.int64), Dates.date(r["created_at"]?.string) ?? ""].joined(separator: " · "))
                if live.session?.sessionId == sessionId, let m = live.finalizationMessage, state == "STOPPING" || state == "FINALIZING" { StatusPill(text: m, tone: .neutral) }
                if let m = r["processing"]?["message"]?.string, !m.isEmpty { StatusPill(text: m, tone: state == "COMPLETED" ? .accent : .caution) }
                if state == "FINALIZATION_RETRYABLE" { PrimaryButton(L("recap_retry")) { model.retryFinalization(sessionId) } }
                if state == "FINALIZING" || state == "STOPPING" { SecondaryButton(L("action_refresh")) { model.reloadRecap(sessionId) } }
                ForEach(Array((comp?["gaps"]?.array ?? []).enumerated()), id: \.offset) { _, g in
                    if g["reason"]?.string != "PAUSED_BY_USER" {
                        Banner(text: captureGapDescription(startMs: g["start_ms"]?.int64, endMs: g["end_ms"]?.int64,
                                                           estimated: g["time_bounds_estimated"]?.bool == true, reason: g["reason"]?.string ?? ""), tone: .caution)
                    }
                }
                let confirmed = (r["participants_confirmed"]?.array ?? []).compactMap(\.string).filter { !$0.isEmpty }
                if !confirmed.isEmpty { SecondaryText(L("recap_participants", confirmed.joined(separator: ", "))) }
                if notesOnly { SecondaryText(L("recap_notes_only")) }
                if comp?["audio_deleted"]?.bool == true { SecondaryText(L("recap_audio_deleted")) }
                if let rc = r["recap"], !rc.isNull {
                    Card {
                        Eyebrow(L("recap_summary"))
                        let summary = rc["summary"]?.array ?? []
                        if summary.isEmpty { SecondaryText(rc["message"]?.string ?? L("recap_no_summary")) }
                        ForEach(Array(summary.enumerated()), id: \.offset) { _, s in Text(s["text"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text) }
                        if rc["visual_content_missing"]?.bool == true { SecondaryText(L("recap_visual_missing")) }
                    }
                    let steps = rc["suggested_next_steps"]?.array ?? []
                    if !steps.isEmpty {
                        Card(raised: true) { Eyebrow(L("label_suggests")); ForEach(Array(steps.enumerated()), id: \.offset) { _, s in Text("• " + (s["text"]?.string ?? "")).font(.subheadline).foregroundStyle(MS.text) } }
                    }
                }
                ForEach(recapSections, id: \.0) { key, title in
                    let items = r[key]?.array ?? []
                    if !items.isEmpty {
                        Eyebrow(L(title))
                        ForEach(Array(items.enumerated()), id: \.offset) { _, c in claimRow(c) }
                    }
                }
                if ended || notesOnly { RecapAskView(model: model, sessionId: sessionId) }
                if r["review_state"]?.string == "PENDING" {
                    Eyebrow(L("recap_keep_title"))
                    SecondaryText(L("recap_keep_note"))
                    let keepable = recapSections.flatMap { r[$0.0]?.array ?? [] }
                        .filter { $0["stale"]?.bool != true && !live.invalidatedClaims.contains($0["claim_id"]?.string ?? "") }.compactMap { $0["claim_id"]?.string }
                    if !keepable.isEmpty {
                        if Set(keepable).isSubset(of: keep) { LinkText(L("recap_select_none")) { keep.removeAll() } }
                        else { LinkText(L("recap_select_all")) { keep = Set(keepable) } }
                    }
                    CheckRow(text: L("recap_exclude"), on: $exclude)
                    PrimaryButton(keep.isEmpty ? L("action_done") : LP("recap_keep_n", keep.count), enabled: !model.busy) {
                        model.review(sessionId, keep: Array(keep), discard: false, exclude: exclude)
                    }
                } else {
                    SecondaryText(L("recap_reviewed"))
                }
                if !notesOnly {
                    HStack {
                        SecondaryButton(L("live_transcript")) { model.openTranscript(sessionId) }
                        SecondaryButton(L("recap_review_speakers")) { model.loadSpeakers(sessionId); model.push(.speakers(sessionId)) }
                    }
                }
                HStack {
                    if ended { SecondaryButton(L("recap_share")) { model.openShare(sessionId) } }
                    if r["context"]?.string == "LEARNING" { SecondaryButton(L("recap_practice")) { model.practice(sessionId) } }
                }
                if ended && !notesOnly && comp?["audio_deleted"]?.bool != true {
                    if confirmAudio {
                        ConfirmDanger(prompt: L("recap_delete_audio_confirm"), confirm: L("recap_delete_audio"), onCancel: { confirmAudio = false }) {
                            confirmAudio = false; model.deleteAudio(sessionId)
                        }
                    } else { SecondaryButton(L("recap_delete_audio")) { confirmAudio = true } }
                }
                if confirmDiscard {
                    ConfirmDanger(prompt: L("recap_discard_confirm"), confirm: L("recap_discard_action"), onCancel: { confirmDiscard = false }) {
                        model.review(sessionId, keep: [], discard: true)
                    }
                } else {
                    SecondaryButton(L("recap_discard"), danger: true) { confirmDiscard = true }
                }
            } else {
                SecondaryText(L("label_loading"))
            }
        }
        .navigationTitle(L("recap_eyebrow"))
        .task(id: live.session?.sessionId == sessionId ? live.session?.state : nil) { try? await model.loadRecap(sessionId) } // refresh when finalization completes
    }

    static func meta(_ c: JSONValue) -> String {
        let kind = c["claim_kind"]?.string
        var meta: [String] = []
        if let l = c["label"]?.string { meta.append(l) }
        if kind == "DECISION" { meta.append(decisionName(c["decision_status"]?.string)) }
        if kind == "ACTION" || kind == "COMMITMENT" { meta.append(ownerText(c["owner_label"]?.string, confirmed: c["owner_confirmed"]?.bool ?? false)) }
        if let d = c["due_text"]?.string { meta.append(L("due_as_spoken", d)) }
        if let t = c["time_start_ms"]?.int64 { meta.append("▶ \(clockString(t))") }
        return meta.joined(separator: " · ")
    }

    @ViewBuilder func claimRow(_ c: JSONValue) -> some View {
        let id = c["claim_id"]?.string ?? ""
        let stale = (c["stale"]?.bool ?? false) || live.invalidatedClaims.contains(id)
        Card {
            CheckRow(text: c["text_value"]?.string ?? "", on: Binding(get: { keep.contains(id) }, set: { if $0 { keep.insert(id) } else { keep.remove(id) } }),
                     enabled: !stale)
            SecondaryText(Self.meta(c))
            if stale { Banner(text: L("recap_stale"), tone: .caution) }
            LinkText(L("recap_open_item")) { model.openMemory(id) }
        }
    }
}

/// Recap "Ask this meeting": evidence-bound questions scoped to this one session.
struct RecapAskView: View {
    @ObservedObject var model: AppModel
    let sessionId: String
    @State private var q = ""
    @State private var mode = "REMEMBER"
    var body: some View {
        Card {
            Text(L("recap_ask_title")).font(.headline).foregroundStyle(MS.text)
            AskModeChips(mode: mode) { mode = $0 }
            TextField(L("recap_ask_hint"), text: $q, axis: .vertical).textFieldStyle(.roundedBorder)
            SecondaryButton(L("action_ask"), enabled: !q.isEmpty && !model.busy) { model.askSession(sessionId, String(q.prefix(4000)), mode: mode) }
        }
        if let a = model.askResult { AnswerView(a: a, onCite: { model.openCitation($0) }) }
    }
}

/// S17 Speaker review: anonymous until the user confirms; corrections cascade.
struct SpeakersView: View {
    @ObservedObject var model: AppModel
    let sessionId: String
    @State private var names: [String: String] = [:]
    var body: some View {
        ScrollPage {
            Text(L("speakers_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            SecondaryText(L("speakers_note"))
            if model.speakers.isEmpty { SecondaryText(L("speakers_empty")) }
            ForEach(Array(model.speakers.enumerated()), id: \.offset) { _, sp in
                let alias = sp["alias"]?.string ?? ""
                let verified = sp["status"]?.string == "VERIFIED_BY_USER"
                Card {
                    HStack {
                        Text(sp["user_verified_label"]?.string ?? L("speaker_unconfirmed", alias)).foregroundStyle(MS.text)
                        Spacer()
                        StatusPill(text: verified ? L("speakers_confirmed") : L("speakers_anonymous"), tone: verified ? .accent : .neutral)
                    }
                    if sp["has_overlap"]?.bool == true { SecondaryText(L("speakers_overlap")) }
                    TextField(L("speakers_name_hint"), text: Binding(get: { names[alias] ?? sp["user_verified_label"]?.string ?? "" }, set: { names[alias] = String($0.prefix(80)) }))
                        .textFieldStyle(.roundedBorder)
                    SecondaryButton(L("action_save")) {
                        let n = (names[alias] ?? "").trimmingCharacters(in: .whitespaces)
                        model.renameSpeaker(sessionId, alias: alias, label: n.isEmpty ? "unknown" : n, revision: sp["mapping_revision"]?.int ?? 1)
                    }
                }
            }
        }
        .navigationTitle(L("speakers_eyebrow"))
    }
}

/// U11 Memories: scoped spaces, search, provenance, session timeline, projects. Never defaults to all spaces.
struct MemoriesView: View {
    @ObservedObject var model: AppModel
    @State private var space: String?
    @State private var q = ""
    @State private var filter = "ALL"
    var body: some View {
        ScrollPage {
            Eyebrow(L("memories_eyebrow"))
            Text(L("memories_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            HStack {
                SecondaryButton(L("memories_sessions")) { model.loadSessions(reset: true); model.push(.sessions) }
                SecondaryButton(L("memories_projects")) { model.loadProjects(); model.push(.projects) }
            }
            Chips(options: (model.me?.spaces ?? []).map { ($0.spaceId, $0.name) }, selected: space) { space = $0; model.loadMemories(space: $0, q: nil) }
            SecondaryText(L("memories_scope_note"))
            TextField(L("memories_search_hint"), text: $q).textFieldStyle(.roundedBorder).onSubmit { if let s = space { model.loadMemories(space: s, q: q) } }
            SecondaryButton(L("action_search")) { if let s = space { model.loadMemories(space: s, q: q) } }
            if !model.matchingSessions.isEmpty {
                Eyebrow(L("memories_matching_sessions"))
                ForEach(Array(model.matchingSessions.enumerated()), id: \.offset) { _, s in
                    Button { if let id = s["session_id"]?.string { model.openRecap(id) } } label: {
                        Card { Text(s["title"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                            SecondaryText([contextName(s["context"]?.string), Dates.date(s["created_at"]?.string) ?? ""].joined(separator: " · ")) }
                    }.buttonStyle(.plain)
                }
            }
            Chips(options: [("ALL", L("filter_all")), ("DECISION", L("filter_decisions")), ("OWNER", L("filter_needs_owner")), ("QUESTION", L("filter_questions"))],
                  selected: filter) { filter = $0 }
            let shown = model.memories.filter { m in
                let k = m["claim_kind"]?.string ?? ""
                switch filter {
                case "DECISION": return k == "DECISION"
                case "OWNER": return (k == "ACTION" || k == "COMMITMENT") && m["owner_confirmed"]?.bool != true
                case "QUESTION": return k == "QUESTION" || k == "RISK"
                default: return true
                }
            }
            if model.memories.isEmpty { SecondaryText(L("memories_empty")) } else if shown.isEmpty { SecondaryText(L("filter_empty")) }
            let pending = model.memories.filter { $0["memory_state"]?.string == "PENDING_REVIEW" }.compactMap { $0["claim_id"]?.string }
            if !pending.isEmpty, let s = space { SecondaryButton(LP("memories_keep_pending", pending.count)) { model.retain(space: s, ids: pending) } }
            ForEach(Array(shown.enumerated()), id: \.offset) { _, m in
                Button { if let id = m["claim_id"]?.string { model.openMemory(id) } } label: {
                    Card {
                        Text(m["text_value"]?.string ?? "").font(.subheadline).foregroundStyle(MS.text)
                        SecondaryText([m["provenance_label"]?.string, humanize(m["claim_kind"]?.string), m["decision_status"]?.string.map(decisionName),
                                       m["session_title"]?.string, memoryStateName(m["memory_state"]?.string)].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        if m["memory_state"]?.string == "INVALIDATED" { Banner(text: L("memory_invalidated"), tone: .caution) }
                    }
                }.buttonStyle(.plain)
            }
            LinkText(L("memories_ask_space")) { model.tab = .ask }
        }
        .onAppear {
            if space == nil, let s = model.me?.spaces.first(where: { $0.kind == "WORK" })?.spaceId ?? model.me?.spaces.first?.spaceId { space = s; model.loadMemories(space: s, q: nil) }
        }
    }
}

/// U12 Ask across sessions with a visible retrieval boundary.
struct GlobalAskView: View {
    @ObservedObject var model: AppModel
    @State private var scopeId: String?
    @State private var general = false
    @State private var project: String?
    @State private var mode = "REMEMBER"
    @State private var q = ""
    var body: some View {
        ScrollPage {
            Eyebrow(L("ask_eyebrow"))
            Text(L("ask_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            Text(L("ask_scope")).font(.headline).foregroundStyle(MS.text)
            Chips(options: (model.me?.spaces ?? []).map { ($0.spaceId, $0.name) } + [("GENERAL", L("ask_general"))],
                  selected: general ? "GENERAL" : (project == nil ? scopeId : nil)) { v in project = nil; if v == "GENERAL" { general = true } else { general = false; scopeId = v } }
            if !model.projects.isEmpty {
                SecondaryText(L("ask_single_project"))
                Chips(options: model.projects.map { ($0["project_id"]?.string ?? "", $0["title"]?.string ?? "") }, selected: project) { project = $0; general = false }
            }
            AskModeChips(mode: mode) { mode = $0 }
            SecondaryText(L(mode == "REMEMBER" ? "ask_remember_note" : "ask_ai_note"))
            TextField(L("ask_hint"), text: $q, axis: .vertical).textFieldStyle(.roundedBorder)
            PrimaryButton(L("action_ask"), enabled: !q.isEmpty && !model.busy) {
                model.ask(q, mode: mode, scope: general ? "GENERAL" : (project != nil ? "SELECTED_PROJECT" : "SELECTED_SPACE"),
                          scopeId: general ? nil : (project ?? scopeId))
            }
            if let a = model.askResult { AnswerView(a: a, onCite: { model.openCitation($0) }); SecondaryText(LP("ask_searched", a.searchedSessions ?? 0)) }
        }
        .onAppear {
            model.loadProjects()
            if scopeId == nil { scopeId = model.me?.spaces.first(where: { $0.kind == "WORK" })?.spaceId }
        }
    }
}

/// In-memory export file for the system save dialog; written only where the user chooses.
struct ExportFile: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

/// Export progress with an honest status; the file is saved only where the user chooses.
struct ExportStatusView: View {
    @ObservedObject var model: AppModel
    let scope: String
    @State private var saving = false
    var body: some View {
        if let e = model.export, e.scope == scope {
            switch e.status {
            case "REQUESTED", "IN_PROGRESS": StatusPill(text: L("export_preparing"), tone: .neutral); LinkText(L("action_refresh")) { model.refreshExport() }
            case "COMPLETE":
                StatusPill(text: L("export_ready"), tone: .accent)
                SecondaryButton(L("export_save")) { model.prepareExportFile() }
                    .onChange(of: model.exportData) { _, d in if d != nil { saving = true } }
                    .fileExporter(isPresented: $saving, document: model.exportData.map(ExportFile.init(data:)), contentType: .json,
                                  defaultFilename: scope == "ALL" ? "meetsaathi-export" : "meetsaathi-session") { result in
                        model.exportData = nil
                        if case .success = result { model.message = L("toast_export_saved") }
                    }
            case "EXPIRED": StatusPill(text: L("export_expired"), tone: .caution)
            default: StatusPill(text: L("export_failed"), tone: .danger)
            }
        }
    }
}

/// U13 You: defaults, retention, privacy (re-auth for export/delete), devices, accessibility.
struct YouView: View {
    @ObservedObject var model: AppModel
    @State private var password = ""
    @State private var confirmDelete = false
    var body: some View {
        ScrollPage {
            Eyebrow(L("you_eyebrow"))
            Text(L("you_title")).font(.title.bold()).foregroundStyle(MS.text).accessibilityAddTraits(.isHeader)
            Card {
                Text(L("you_defaults")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("you_defaults_note"))
                Text(L("you_default_assistance")).foregroundStyle(MS.text)
                AssistanceChips(selected: model.pref("default_assistance") ?? "LISTENER", aiOk: true) { model.savePrefs(["default_assistance": .string($0)]) }
                Text(L("you_default_output")).foregroundStyle(MS.text)
                OutputChips(selected: model.pref("default_output") ?? "TEXT") { model.savePrefs(["default_output": .string($0)]) }
                if let o = model.pref("default_output"), o != "TEXT" { SecondaryText(L("you_voice_still_tested")) }
                Text(L("you_default_intensity")).foregroundStyle(MS.text)
                ForEach(["MEETING", "LEARNING", "INTERVIEW", "CONVERSATION"], id: \.self) { ctx in
                    SecondaryText(contextName(ctx))
                    IntensityChips(selected: model.intensityPref(ctx) ?? "QUIET") { model.setDefaultIntensity(ctx, $0) }
                }
            }
            Card {
                Text(L("you_accessibility")).font(.headline).foregroundStyle(MS.text)
                CheckRow(text: L("you_captions_large"), on: Binding(get: { model.preferences["captions_large"]?.bool == true },
                                                                     set: { model.savePrefs(["captions_large": .bool($0)]) }))
                SecondaryText(L("you_accessibility_body"))
            }
            Card { Text(L("you_retention")).font(.headline).foregroundStyle(MS.text); SecondaryText(L("you_retention_body")) }
            if let me = model.me {
                Card {
                    Text(L("you_usage")).font(.headline).foregroundStyle(MS.text)
                    SecondaryText(L("you_usage_line", me.quota.captureHoursUsed, me.quota.captureHoursLimit, me.quota.reasonerCallsUsed, me.quota.reasonerCallsLimit))
                    SecondaryText(L("you_region", me.tenant["residency_region"]?.string ?? "", me.processingDisclosureVersion))
                }
            }
            Card {
                Text(L("you_privacy")).font(.headline).foregroundStyle(MS.text)
                SecondaryText(L("you_reauth_note"))
                SecureField(L("you_password"), text: $password).textFieldStyle(.roundedBorder)
                HStack {
                    SecondaryButton(L("you_export"), enabled: password.count >= 10 && !model.busy) { model.requestExport(password: password); password = "" }
                    SecondaryButton(L("you_delete_account"), danger: true, enabled: password.count >= 10) { confirmDelete = true }
                }
                ExportStatusView(model: model, scope: "ALL")
                if confirmDelete {
                    ConfirmDanger(prompt: L("you_delete_confirm"), confirm: L("you_delete_action"), onCancel: { confirmDelete = false }) { model.deleteAccount(password: password) }
                }
            }
            Card {
                Text(L("you_devices")).font(.headline).foregroundStyle(MS.text)
                ForEach(Array(model.devices.enumerated()), id: \.offset) { _, d in
                    let revoked = d["revoked_at"].map { !$0.isNull } ?? false
                    let current = d["current"]?.bool ?? false
                    HStack {
                        SecondaryText([d["name"]?.string, humanize(d["platform"]?.string), current ? L("you_this_device") : nil, revoked ? L("you_signed_out") : nil]
                            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        Spacer()
                        if !revoked && !current, let id = d["device_id"]?.string { LinkText(L("you_sign_out_device")) { model.revokeDevice(id) } }
                    }
                }
            }
            SecondaryButton(L("you_sign_out")) { model.signOut() }
        }
        .onAppear { model.loadDevices() }
    }
}
