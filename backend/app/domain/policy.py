"""Policy engine: context packs (ContextPolicy, master 2.2 / ADR-015) and the four independent
consent/control dimensions (ADR-003): capture, live AI assistance, private voice, retention.

Context packs configure behaviour; they never grant permissions (CON-003). Every decision here is
re-evaluated server-side on every relevant endpoint; client switches are never trusted alone (INT-030).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import get_settings
from ..errors import policy_denied, preflight_failed

CONTEXTS = ("MEETING", "LEARNING", "INTERVIEW", "CONVERSATION")
INSIGHT_KINDS = ("CLARIFY", "TRADEOFF", "DECISION_UNRESOLVED", "FOLLOWUP", "LEARN", "CONNECTION", "REMINDER",
                 "TRANSLATION", "INTERVIEW_PRACTICE", "NO_ACTION")
CAPTURE_BASES = ("PARTICIPANTS_INFORMED", "ALL_PARTY_CONSENT", "ORGANIZATION_POLICY", "SELF_ONLY",
                 "NOT_PERMITTED", "UNKNOWN")
PERMITTING_BASES = {"PARTICIPANTS_INFORMED", "ALL_PARTY_CONSENT", "ORGANIZATION_POLICY", "SELF_ONLY"}
RETENTION_POLICIES = ("EPHEMERAL", "REVIEW_TO_KEEP", "KEEP_SELECTED")


@dataclass(frozen=True)
class Budget:
    cooldown_s: int          # minimum gap between delivered proactive insights
    max_per_15_min: int      # hard cap in any rolling 15 minutes
    min_score: float         # ranking threshold after gates


@dataclass(frozen=True)
class ContextPolicy:
    context: str
    allowed_kinds: tuple[str, ...]
    default_retention: str
    budgets: dict[str, Budget]
    max_live_words: int = 45
    preferred_words: tuple[int, int] = (12, 28)
    sensitive_presets: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    extraction_kinds: tuple[str, ...] = ()
    live_guidance: str = ""
    voice_max_seconds: int = 7
    version: str = field(default_factory=lambda: get_settings().policy_version)

    def budget(self, intensity: str) -> Budget | None:
        return self.budgets.get(intensity)


_QUIET = None  # Quiet = 0 proactive
POLICIES: dict[str, ContextPolicy] = {
    "MEETING": ContextPolicy(
        context="MEETING",
        allowed_kinds=("CLARIFY", "TRADEOFF", "DECISION_UNRESOLVED", "FOLLOWUP", "CONNECTION", "REMINDER", "TRANSLATION"),
        default_retention="REVIEW_TO_KEEP",
        # Balanced: <=1 per 4 min, <=3 per 15 min (Meeting 4.4). Active: 1-3 min with cap (master 5.2).
        budgets={"BALANCED": Budget(240, 3, 0.55), "ACTIVE": Budget(120, 6, 0.45)},
        presets=("Architecture review", "Team standup", "Customer discussion", "Strategy meeting", "Sales discovery", "Other"),
        extraction_kinds=("DECISION", "ACTION", "QUESTION", "RISK"),
        live_guidance="Priorities: decisions, trade-offs, commitments, risks, ownership. A proposal is never an agreement.",
    ),
    "LEARNING": ContextPolicy(
        context="LEARNING",
        allowed_kinds=("LEARN", "CLARIFY", "REMINDER", "CONNECTION", "TRANSLATION"),
        default_retention="REVIEW_TO_KEEP",
        # Learning 5.2: >=90 s apart, <=2 unsolicited content cards per 15 min in Balanced.
        budgets={"BALANCED": Budget(300, 2, 0.6), "ACTIVE": Budget(90, 4, 0.5)},
        presets=("Lecture", "Tutorial", "Seminar", "Workshop", "Talk/Seminar (research)", "Study group"),
        extraction_kinds=("CONCEPT", "QUESTION", "LESSON"),
        live_guidance="Help the learner follow concepts. Never claim the lecturer said something unless sourced; "
                      "say when visual material (board, slides) was not captured.",
    ),
    "INTERVIEW": ContextPolicy(
        context="INTERVIEW",
        allowed_kinds=("INTERVIEW_PRACTICE", "CLARIFY"),
        default_retention="REVIEW_TO_KEEP",
        budgets={"BALANCED": Budget(300, 2, 0.65), "ACTIVE": Budget(150, 4, 0.55)},
        max_live_words=36,
        voice_max_seconds=9,
        presets=("System design", "Behavioral", "Coding", "AI / ML", "Cloud architecture", "Product"),
        extraction_kinds=("QUESTION", "LESSON"),
        live_guidance="Only concise clarifying or framing nudges. Never draft full answers for the candidate.",
    ),
    "CONVERSATION": ContextPolicy(
        context="CONVERSATION",
        allowed_kinds=("CLARIFY", "FOLLOWUP", "CONNECTION", "REMINDER", "TRANSLATION"),
        default_retention="EPHEMERAL",
        budgets={"BALANCED": Budget(300, 2, 0.6), "ACTIVE": Budget(150, 4, 0.5)},
        sensitive_presets=("Trusted family discussion", "Personal coaching", "Medical consultation", "Legal consultation",
                           "Financial consultation"),
        presets=("Mentoring", "Networking", "Language exchange", "Everyday conversation", "Brainstorming",
                 "Trusted family discussion", "Personal coaching", "Medical consultation", "Legal consultation",
                 "Financial consultation"),
        extraction_kinds=("COMMITMENT", "QUESTION", "IDEA"),
        live_guidance="Low interruption. Respectful clarifying questions only. Never infer emotions, motives, "
                      "character or protected traits. Never suggest manipulative tactics.",
    ),
}


def policy_for(context: str) -> ContextPolicy:
    try:
        return POLICIES[context]
    except KeyError:
        raise preflight_failed("UNKNOWN_CONTEXT", "Choose Meeting, Learning, Interview or Conversation.")


def is_sensitive(context: str, preset: str | None) -> bool:
    return bool(preset) and preset in policy_for(context).sensitive_presets


@dataclass
class ConsentDecision:
    capture_permitted: bool
    ai_assistance_permitted: bool
    reasons: list[str]


def evaluate_consent(*, context: str, interview_mode: str | None, capture_source: str, capture_basis: str,
                     notices_attested: bool, ai_assistance_permitted: bool, disclosure_version: str,
                     org_policy: dict, tenant_region: str) -> ConsentDecision:
    """Recording permission, processing permission and AI-assistance permission are distinct choices
    (master 9.2). OS microphone permission is NOT participant consent (CON-011)."""
    s = get_settings()
    reasons: list[str] = []
    if capture_basis not in CAPTURE_BASES:
        raise preflight_failed("INVALID_CAPTURE_BASIS", "Choose how this capture is authorized.")
    if disclosure_version != s.processing_disclosure_version:
        raise preflight_failed("DISCLOSURE_OUTDATED", "Review the current processing disclosure before starting.",
                               {"current_version": s.processing_disclosure_version})

    capture = capture_source != "NONE" and capture_basis in PERMITTING_BASES and notices_attested
    if capture_source != "NONE" and not capture:
        reasons.append("CAPTURE_NOT_AUTHORIZED")
    if org_policy.get("disable_capture"):
        capture = False
        reasons.append("ORG_POLICY_DISABLES_CAPTURE")
    if tenant_region not in s.allowed_region_set():
        capture = False
        reasons.append("REGION_NOT_SUPPORTED")

    # Live AI assistance: Interview requires an explicit, separate "AI permitted" answer; unknown means no.
    if context == "INTERVIEW" and interview_mode == "LIVE":
        ai = bool(ai_assistance_permitted)
        if not ai:
            reasons.append("INTERVIEW_AI_NOT_PERMITTED")
    elif context == "INTERVIEW" and interview_mode == "REFLECTION":
        ai = False
    else:
        ai = bool(ai_assistance_permitted)
        if not ai:
            reasons.append("AI_NOT_PERMITTED")
    if org_policy.get("disable_live_ai"):
        ai = False
        reasons.append("ORG_POLICY_DISABLES_LIVE_AI")
    return ConsentDecision(capture, ai, reasons)


def require_live_ai(session: dict) -> None:
    """Invariant: interview_prohibited -> zero live coaching even when mic is permitted."""
    if not session["ai_assistance_permitted"]:
        raise policy_denied("LIVE_AI_NOT_PERMITTED",
                            "Live AI help is off for this session because it isn't permitted here.")


def validate_runtime_controls(*, context: str, assistance_mode: str, proactive_intensity: str, output_mode: str,
                              sensitive: bool, sensitive_opt_in: bool = False) -> tuple[str, str, str]:
    if assistance_mode not in ("LISTENER", "ASK", "COMPANION"):
        raise preflight_failed("INVALID_ASSISTANCE", "Choose Listener, Ask or Companion.")
    if proactive_intensity not in ("QUIET", "BALANCED", "ACTIVE"):
        raise preflight_failed("INVALID_INTENSITY", "Choose Quiet, Balanced or Active.")
    if output_mode not in ("TEXT", "PRIVATE_VOICE", "BOTH"):
        raise preflight_failed("INVALID_OUTPUT", "Choose Text, Private voice or Both.")
    # Intensity determines rate only when Companion is enabled (conflict ledger row 2).
    if assistance_mode != "COMPANION":
        proactive_intensity = "QUIET"
    # Sensitive contexts stay quiet without positive opt-in (master 2.3).
    if sensitive and not sensitive_opt_in and proactive_intensity != "QUIET":
        proactive_intensity = "QUIET"
    return assistance_mode, proactive_intensity, output_mode
