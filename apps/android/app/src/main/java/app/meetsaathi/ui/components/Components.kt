package app.meetsaathi.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.meetsaathi.R
import app.meetsaathi.audio.EvidencePlayer
import app.meetsaathi.core.Citation
import app.meetsaathi.core.GapPhrase
import app.meetsaathi.core.render
import app.meetsaathi.ui.theme.LocalMs
import app.meetsaathi.ui.theme.MinTouch
import app.meetsaathi.ui.theme.Radii
import app.meetsaathi.ui.theme.Spacing

@Composable
fun Eyebrow(text: String) {
    Text(text.uppercase(), color = LocalMs.current.secondary, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp,
        modifier = Modifier.semantics { contentDescription = text })
}

@Composable
fun Heading(text: String) = Text(text, color = LocalMs.current.text, fontSize = 26.sp, fontWeight = FontWeight.Bold, lineHeight = 32.sp,
    modifier = Modifier.semantics { heading() })

@Composable
fun Title(text: String) = Text(text, color = LocalMs.current.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, lineHeight = 23.sp,
    modifier = Modifier.semantics { heading() })

@Composable
fun Body(text: String, color: Color = LocalMs.current.text, size: Int = 16) =
    Text(text, color = color, fontSize = size.sp, lineHeight = (size * 1.45).sp)

@Composable
fun Secondary(text: String) = Body(text, LocalMs.current.secondary, 14)

@Composable
fun MsCard(modifier: Modifier = Modifier, raised: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    val t = LocalMs.current
    Column(
        modifier.fillMaxWidth().padding(vertical = Spacing.s)
            .background(if (raised) t.raised else t.surface, RoundedCornerShape(Radii.card))
            .border(1.dp, t.border, RoundedCornerShape(Radii.card)).padding(Spacing.l),
        verticalArrangement = Arrangement.spacedBy(Spacing.s), content = content,
    )
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    val t = LocalMs.current
    Button(onClick = onClick, enabled = enabled, modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = MinTouch),
        shape = RoundedCornerShape(Radii.small),
        colors = ButtonDefaults.buttonColors(containerColor = t.accent, contentColor = t.onAccent)) {
        Text(text, fontWeight = FontWeight.Bold, fontSize = 16.sp)
    }
}

@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, danger: Boolean = false, enabled: Boolean = true) {
    val t = LocalMs.current
    OutlinedButton(onClick = onClick, enabled = enabled, modifier = modifier.defaultMinSize(minHeight = MinTouch),
        shape = RoundedCornerShape(Radii.small), border = BorderStroke(1.dp, if (danger) t.danger else t.border)) {
        Text(text, color = if (!enabled) t.secondary else if (danger) t.danger else t.text, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun LinkButton(text: String, enabled: Boolean = true, onClick: () -> Unit) {
    TextButton(onClick = onClick, enabled = enabled, modifier = Modifier.defaultMinSize(minHeight = MinTouch)) {
        Text(text, color = if (enabled) LocalMs.current.accent else LocalMs.current.secondary, fontWeight = FontWeight.SemiBold)
    }
}

/** Screen top bar for pushed screens: eyebrow on the left, a single obvious Close on the right. */
@Composable
fun TopRow(eyebrow: String, onClose: () -> Unit) {
    Row(horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Eyebrow(eyebrow)
        LinkButton(stringResource(R.string.action_close), onClick = onClose)
    }
}

/** Checkbox row: the whole row is the touch target, and the state is announced. */
@Composable
fun CheckRow(checked: Boolean, text: String, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    val t = LocalMs.current
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().defaultMinSize(minHeight = MinTouch)
        .toggleable(value = checked, enabled = enabled, role = Role.Checkbox, onValueChange = onChange)) {
        Checkbox(checked, null, enabled = enabled, colors = CheckboxDefaults.colors(checkedColor = t.accent))
        Spacer(Modifier.width(Spacing.s))
        Body(text, size = 14, color = if (enabled) t.text else t.secondary)
    }
}

/** Two-step destructive confirmation; the destructive button never appears without the explanation above it. */
@Composable
fun ConfirmDanger(prompt: String, confirmLabel: String, onCancel: () -> Unit, onConfirm: () -> Unit) {
    Body(prompt, size = 15)
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.s)) {
        SecondaryButton(stringResource(R.string.action_cancel), onCancel, Modifier.weight(1f))
        SecondaryButton(confirmLabel, onConfirm, Modifier.weight(1f), danger = true)
    }
}

/** Single-select chips. Selection is announced (not conveyed by colour alone). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChoiceChips(options: List<Pair<String, String>>, selected: String?, onSelect: (String) -> Unit, enabled: (String) -> Boolean = { true }) {
    val t = LocalMs.current
    val on = stringResource(R.string.a11y_selected)
    val off = stringResource(R.string.a11y_not_selected)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.s), verticalArrangement = Arrangement.spacedBy(Spacing.s)) {
        options.forEach { (value, label) ->
            val isOn = value == selected
            val ok = enabled(value)
            Row(
                Modifier.defaultMinSize(minHeight = MinTouch)
                    .background(if (isOn) t.raised else t.surface, RoundedCornerShape(Radii.small))
                    .border(if (isOn) 2.dp else 1.dp, if (isOn) t.accent else t.border, RoundedCornerShape(Radii.small))
                    .clickable(enabled = ok, role = Role.RadioButton) { onSelect(value) }
                    .semantics { this.selected = isOn; stateDescription = if (isOn) on else off }
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text((if (isOn) "✓ " else "") + label, color = if (ok) t.text else t.secondary, fontSize = 14.sp,
                    fontWeight = if (isOn) FontWeight.Bold else FontWeight.Normal)
            }
        }
    }
}

enum class Tone { Accent, Caution, Danger, Neutral }

/** Status always carries an icon glyph + words, never colour alone (master 3.1). */
@Composable
fun StatusPill(text: String, tone: Tone, glyph: String = when (tone) { Tone.Accent -> "●"; Tone.Caution -> "▲"; Tone.Danger -> "■"; Tone.Neutral -> "○" }) {
    val t = LocalMs.current
    val c = when (tone) { Tone.Accent -> t.accent; Tone.Caution -> t.caution; Tone.Danger -> t.danger; Tone.Neutral -> t.secondary }
    Row(Modifier.background(t.surface, RoundedCornerShape(50)).border(1.dp, c, RoundedCornerShape(50))
        .padding(horizontal = 10.dp, vertical = 6.dp).clearAndSetSemantics { contentDescription = text }, verticalAlignment = Alignment.CenterVertically) {
        Text(glyph, color = c, fontSize = 12.sp)
        Spacer(Modifier.width(6.dp))
        Text(text, color = t.text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun Banner(text: String, tone: Tone) {
    val t = LocalMs.current
    val c = when (tone) { Tone.Danger -> t.danger; Tone.Caution -> t.caution; else -> t.accent }
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp).border(1.dp, c, RoundedCornerShape(Radii.small)).padding(12.dp)
        .clearAndSetSemantics { contentDescription = text }) {
        Text(if (tone == Tone.Danger) "■ " else if (tone == Tone.Caution) "▲ " else "● ", color = c)
        Text(text, color = t.text, fontSize = 14.sp)
    }
}

@Composable
fun GapBanner(p: GapPhrase) = Banner(p.render(LocalContext.current), Tone.Caution)

fun clock(ms: Long?): String {
    val s = (ms ?: 0) / 1000
    return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, (s % 3600) / 60, s % 60) else "%02d:%02d".format(s / 60, s % 60)
}

/** Speaker labels separate voices; they never identify a person unless the user confirmed a name. */
@Composable
fun speakerName(alias: String?, verified: Boolean, verifiedLabel: String?): String = when {
    verified && !verifiedLabel.isNullOrBlank() -> verifiedLabel
    alias == null || alias == "Unassigned" -> stringResource(R.string.speaker_unassigned)
    else -> stringResource(R.string.speaker_unconfirmed, alias)
}

@Composable
fun provenanceTitle(label: String): String = stringResource(when (label) {
    "FROM_CONVERSATION" -> R.string.prov_from_conversation
    "FROM_USER_NOTE" -> R.string.prov_from_notes
    "AI_ANALYSIS" -> R.string.prov_ai_analysis
    "GENERAL_KNOWLEDGE" -> R.string.prov_general
    else -> R.string.prov_not_established
})

@Composable
fun humanize(code: String?): String = code?.lowercase()?.replace('_', ' ')?.replaceFirstChar { it.uppercase() } ?: ""

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CitationChips(cites: List<Citation>, onOpen: ((Citation) -> Unit)? = null) {
    val t = LocalMs.current
    if (cites.isEmpty()) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        cites.forEach { c ->
            val label = if (c.utteranceId != null) {
                val who = c.speakerAlias?.let { " · " + speakerName(it, c.speakerVerified, if (c.speakerVerified) it else null) } ?: ""
                "▶ ${clock(c.startMs)}$who" + if (!c.isFinal) " · " + stringResource(R.string.label_provisional) else ""
            } else "◇ " + (c.sourceKind?.let { humanize(it) } ?: stringResource(R.string.label_note))
            val mod = Modifier.background(t.raised, RoundedCornerShape(8.dp)).defaultMinSize(minHeight = 32.dp)
            Text(label, color = t.text, fontSize = 13.sp,
                modifier = (if (onOpen != null) mod.clickable(role = Role.Button) { onOpen(c) } else mod).padding(horizontal = 8.dp, vertical = 6.dp))
        }
    }
}

/**
 * Evidence play control for one cited utterance. Shows truthful state (loading / playing / why unavailable) and plays
 * only the cited span. Hidden entirely when audio was deleted or never recorded.
 */
@Composable
fun EvidenceButton(state: EvidencePlayer.State, utteranceId: String, startMs: Long?, onToggle: () -> Unit) {
    val mine = when (state) {
        is EvidencePlayer.State.Loading -> state.utteranceId == utteranceId
        is EvidencePlayer.State.Playing -> state.utteranceId == utteranceId
        is EvidencePlayer.State.Failed -> state.utteranceId == utteranceId
        else -> false
    }
    val label = when {
        mine && state is EvidencePlayer.State.Loading -> stringResource(R.string.evidence_loading)
        mine && state is EvidencePlayer.State.Playing -> stringResource(R.string.evidence_stop, clock(startMs))
        else -> stringResource(R.string.evidence_play, clock(startMs))
    }
    Column {
        LinkButton(label, onClick = onToggle)
        if (mine && state is EvidencePlayer.State.Failed) Secondary(when (state.code) {
            "AUDIO_DELETED" -> stringResource(R.string.evidence_deleted)
            "CLIP_UNAVAILABLE" -> stringResource(R.string.evidence_unavailable)
            "OFFLINE" -> stringResource(R.string.evidence_offline)
            else -> state.message.ifBlank { stringResource(R.string.evidence_failed) }
        })
    }
}

@Composable
fun Gap(h: Int = 12) = Spacer(Modifier.height(h.dp))
