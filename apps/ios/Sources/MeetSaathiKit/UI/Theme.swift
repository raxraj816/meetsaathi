import SwiftUI

/// packages/design/tokens.json (master v1). Dynamic Type is used throughout (no fixed point sizes for body text).
public enum MS {
    static func c(_ dark: UInt32, _ light: UInt32) -> Color {
        #if os(iOS)
        return Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
        #else
        return Color(hex: dark)
        #endif
    }
    public static let canvas = c(0x081522, 0xF4F8FA)
    public static let surface = c(0x132839, 0xFFFFFF)
    public static let raised = c(0x183B38, 0xEAF6F3)
    public static let border = c(0x2C495A, 0xD6E1E6)
    public static let text = c(0xF0F8F8, 0x142630)
    public static let secondary = c(0xA0B8C6, 0x51636F)
    public static let accent = c(0x70E6D0, 0x087968)
    public static let onAccent = c(0x092B2C, 0xFFFFFF)
    public static let caution = c(0xFFCF8A, 0x9C6000)
    public static let danger = c(0xFF9BA7, 0xA72641)
    public static let radiusCard: CGFloat = 18
    public static let radiusSmall: CGFloat = 12
    public static let minTouch: CGFloat = 44
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

#if os(iOS)
extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255, blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}
#endif

public enum Tone { case accent, caution, danger, neutral
    var color: Color { switch self { case .accent: MS.accent; case .caution: MS.caution; case .danger: MS.danger; case .neutral: MS.secondary } }
    var glyph: String { switch self { case .accent: "●"; case .caution: "▲"; case .danger: "■"; case .neutral: "○" } }
}

struct Card<Content: View>: View {
    var raised = false
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(raised ? MS.raised : MS.surface, in: RoundedRectangle(cornerRadius: MS.radiusCard))
            .overlay(RoundedRectangle(cornerRadius: MS.radiusCard).stroke(MS.border, lineWidth: 1))
    }
}

struct Eyebrow: View {
    let text: String
    init(_ t: String) { text = t }
    var body: some View {
        Text(text.uppercased()).font(.caption.weight(.bold)).foregroundStyle(MS.secondary).kerning(1.1)
            .accessibilityLabel(text).accessibilityAddTraits(.isHeader)
    }
}

struct SecondaryText: View {
    let text: String
    init(_ t: String) { text = t }
    var body: some View { Text(text).font(.subheadline).foregroundStyle(MS.secondary).fixedSize(horizontal: false, vertical: true) }
}

/// Status always carries a glyph + words, never colour alone (master 3.1).
struct StatusPill: View {
    let text: String
    let tone: Tone
    var body: some View {
        HStack(spacing: 6) { Text(tone.glyph).foregroundStyle(tone.color); Text(text).font(.footnote.weight(.semibold)).foregroundStyle(MS.text) }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .overlay(Capsule().stroke(tone.color, lineWidth: 1))
            .accessibilityElement(children: .ignore).accessibilityLabel(text)
    }
}

struct Banner: View {
    let text: String
    let tone: Tone
    var body: some View {
        HStack(alignment: .top, spacing: 8) { Text(tone.glyph).foregroundStyle(tone.color); Text(text).font(.subheadline).foregroundStyle(MS.text) }
            .frame(maxWidth: .infinity, alignment: .leading).padding(12)
            .overlay(RoundedRectangle(cornerRadius: MS.radiusSmall).stroke(tone.color, lineWidth: 1))
    }
}

struct PrimaryButton: View {
    let title: String
    var enabled = true
    let action: () -> Void
    init(_ t: String, enabled: Bool = true, action: @escaping () -> Void) { title = t; self.enabled = enabled; self.action = action }
    var body: some View {
        Button(action: action) {
            Text(title).font(.headline).frame(maxWidth: .infinity, minHeight: MS.minTouch)
        }
        .foregroundStyle(MS.onAccent)
        .background(enabled ? MS.accent : MS.accent.opacity(0.4), in: RoundedRectangle(cornerRadius: MS.radiusSmall))
        .disabled(!enabled)
    }
}

struct SecondaryButton: View {
    let title: String
    var danger = false
    var enabled = true
    let action: () -> Void
    init(_ t: String, danger: Bool = false, enabled: Bool = true, action: @escaping () -> Void) {
        title = t; self.danger = danger; self.enabled = enabled; self.action = action
    }
    var body: some View {
        Button(action: action) {
            Text(title).font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, minHeight: MS.minTouch)
        }
        .foregroundStyle(danger ? MS.danger : MS.text)
        .overlay(RoundedRectangle(cornerRadius: MS.radiusSmall).stroke(danger ? MS.danger : MS.border, lineWidth: 1))
        .disabled(!enabled).opacity(enabled ? 1 : 0.5)
    }
}

/// Single-select chips; selection is announced, not only coloured.
struct Chips: View {
    let options: [(String, String)]
    let selected: String?
    var enabled: (String) -> Bool = { _ in true }
    let onSelect: (String) -> Void
    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(options, id: \.0) { value, label in
                let on = value == selected
                Button { onSelect(value) } label: {
                    Text((on ? "✓ " : "") + label).font(.subheadline.weight(on ? .bold : .regular)).padding(.horizontal, 14).frame(minHeight: MS.minTouch)
                }
                .foregroundStyle(enabled(value) ? MS.text : MS.secondary)
                .background(on ? MS.raised : MS.surface, in: RoundedRectangle(cornerRadius: MS.radiusSmall))
                .overlay(RoundedRectangle(cornerRadius: MS.radiusSmall).stroke(on ? MS.accent : MS.border, lineWidth: on ? 2 : 1))
                .disabled(!enabled(value))
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
    }
}

/// Wrapping layout for chips (works at large Dynamic Type sizes without clipping).
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, w: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x + sz.width > maxW && x > 0 { x = 0; y += rowH + spacing; rowH = 0 }
            x += sz.width + spacing; rowH = max(rowH, sz.height); w = max(w, x)
        }
        return CGSize(width: min(w, maxW), height: y + rowH)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowH: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x + sz.width > bounds.maxX && x > bounds.minX { x = bounds.minX; y += rowH + spacing; rowH = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(sz))
            x += sz.width + spacing; rowH = max(rowH, sz.height)
        }
    }
}

struct CitationChips: View {
    let cites: [Citation]
    var onOpen: ((Citation) -> Void)? = nil
    var body: some View {
        if !cites.isEmpty {
            FlowLayout(spacing: 6) {
                ForEach(Array(cites.enumerated()), id: \.offset) { _, c in
                    let chip = Text(label(c)).font(.footnote).foregroundStyle(MS.text).padding(.horizontal, 8).padding(.vertical, 6)
                        .frame(minHeight: 32).background(MS.raised, in: RoundedRectangle(cornerRadius: 8))
                    if let onOpen { Button { onOpen(c) } label: { chip }.buttonStyle(.plain) } else { chip }
                }
            }
        }
    }
    func label(_ c: Citation) -> String {
        if c.utteranceId != nil {
            var s = "▶ \(clockString(c.startMs))"
            if let a = c.speakerAlias { s += " · " + speakerName(alias: a, verified: c.speakerVerified ?? false, label: (c.speakerVerified ?? false) ? a : nil) }
            if c.isFinal == false { s += " · " + L("label_provisional") }
            return s
        }
        return "◇ " + (c.sourceKind.map(humanize) ?? L("label_note"))
    }
}

/// Speaker labels separate voices; they never identify a person unless the user confirmed a name.
func speakerName(alias: String?, verified: Bool, label: String?) -> String {
    if verified, let label, !label.isEmpty { return label }
    guard let alias, alias != "Unassigned" else { return L("speaker_unassigned") }
    return L("speaker_unconfirmed", alias)
}

func humanize(_ code: String?) -> String {
    guard let code, !code.isEmpty else { return "" }
    let s = code.lowercased().replacingOccurrences(of: "_", with: " ")
    return s.prefix(1).uppercased() + s.dropFirst()
}

func contextName(_ ctx: String?) -> String {
    switch ctx { case "LEARNING": L("ctx_learning"); case "INTERVIEW": L("ctx_interview"); case "CONVERSATION": L("ctx_conversation"); default: L("ctx_meeting") }
}

func stateName(_ s: String?) -> String {
    switch s {
    case "PREFLIGHT": L("state_preflight"); case "NOTES_ONLY": L("state_notes_only"); case "STARTING": L("state_starting")
    case "RECORDING": L("state_recording"); case "PAUSED": L("state_paused"); case "INTERRUPTED": L("state_interrupted")
    case "STOPPING", "FINALIZING": L("state_finalizing"); case "FINALIZATION_RETRYABLE": L("state_retryable")
    case "COMPLETED": L("state_completed"); case "COMPLETED_PARTIAL": L("state_completed_partial")
    case "DELETING", "DELETED": L("state_deleting"); default: L("state_error")
    }
}

func decisionName(_ s: String?) -> String {
    switch s {
    case "PROPOSED": L("decision_proposed"); case "DISCUSSED": L("decision_discussed"); case "ACCEPTED": L("decision_accepted")
    case "REJECTED": L("decision_rejected"); case "DEFERRED": L("decision_deferred"); case "SUPERSEDED": L("decision_superseded")
    default: L("decision_unresolved")
    }
}

func ownerText(_ owner: String?, confirmed: Bool) -> String {
    guard let owner, !owner.isEmpty else { return L("owner_unconfirmed") }
    return confirmed ? owner : L("owner_named_unconfirmed", owner)
}

func sessionMeta(_ ctx: String, _ ms: Int64, _ decisions: Int, _ open: Int) -> String {
    [contextName(ctx), clockString(ms), LP("decisions_count", decisions), LP("open_count", open)].joined(separator: " · ")
}

/// Two-step destructive confirmation; the destructive button never appears without the explanation above it.
struct ConfirmDanger: View {
    let prompt: String
    let confirm: String
    let onCancel: () -> Void
    let onConfirm: () -> Void
    var body: some View {
        Text(prompt).font(.subheadline).foregroundStyle(MS.text).fixedSize(horizontal: false, vertical: true)
        HStack { SecondaryButton(L("action_cancel"), action: onCancel); SecondaryButton(confirm, danger: true, action: onConfirm) }
    }
}

/// Checkbox-style row: whole row is the target and the state is announced.
struct CheckRow: View {
    let text: String
    @Binding var on: Bool
    var enabled = true
    var body: some View {
        Toggle(isOn: $on) { Text(text).font(.subheadline).foregroundStyle(enabled ? MS.text : MS.secondary).fixedSize(horizontal: false, vertical: true) }
            .tint(MS.accent).disabled(!enabled).frame(minHeight: MS.minTouch)
    }
}

/// Evidence play control for one cited utterance with truthful loading/playing/unavailable state.
struct EvidenceButton: View {
    @ObservedObject var player: EvidencePlayer
    let utteranceId: String
    let startMs: Int64?
    let onToggle: () -> Void
    var body: some View {
        let mine = player.state.utteranceId == utteranceId
        VStack(alignment: .leading, spacing: 4) {
            Button(action: onToggle) {
                Text(mine && player.state == .loading(utteranceId) ? L("evidence_loading")
                     : mine && player.state == .playing(utteranceId) ? L("evidence_stop", clockString(startMs)) : L("evidence_play", clockString(startMs)))
                    .font(.subheadline.weight(.semibold)).frame(minHeight: MS.minTouch)
            }.tint(MS.accent)
            if mine, case .failed(_, let code, let msg) = player.state {
                SecondaryText(code == "AUDIO_DELETED" ? L("evidence_deleted") : code == "CLIP_UNAVAILABLE" ? L("evidence_unavailable")
                              : code == "OFFLINE" ? L("evidence_offline") : (msg.isEmpty ? L("evidence_failed") : msg))
            }
        }
    }
}

struct LinkText: View {
    let title: String
    let action: () -> Void
    init(_ t: String, action: @escaping () -> Void) { title = t; self.action = action }
    var body: some View { Button(title, action: action).font(.subheadline.weight(.semibold)).tint(MS.accent).frame(minHeight: MS.minTouch) }
}

extension View {
    func screenBackground() -> some View { self.background(MS.canvas.ignoresSafeArea()) }
    @ViewBuilder func emailField() -> some View {
        #if os(iOS)
        self.textInputAutocapitalization(.never).keyboardType(.emailAddress).autocorrectionDisabled()
        #else
        self
        #endif
    }
}
