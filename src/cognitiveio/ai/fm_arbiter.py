from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

try:
    import apple_fm_sdk as fm
except Exception:
    fm = None  # type: ignore

Action = Literal["do_nothing", "suggest", "auto_apply"]


@dataclass
class Candidate:
    id: str
    before: str
    after: str
    count: int
    confidence: float


@dataclass
class ArbiterDecision:
    action: Action
    chosen_candidate_id: Optional[str]
    confidence: float
    reason_tag: str


def validate_candidate_choice(chosen_candidate_id: Optional[str], allowed_ids: List[str]) -> bool:
    return chosen_candidate_id is None or chosen_candidate_id in allowed_ids


async def decide_with_apple_fm(packet: Dict[str, Any], candidates: List[Candidate]) -> ArbiterDecision:
    """
    Constrained arbiter:
    - choose candidate id from provided set OR null
    - never generate replacement text
    """
    if fm is None:
        return ArbiterDecision("do_nothing", None, 0.0, "fm_unavailable:sdk_missing")

    model = fm.SystemLanguageModel(use_case=fm.SystemLanguageModelUseCase.GENERAL)
    ok, reason = model.is_available()
    if not ok:
        return ArbiterDecision("do_nothing", None, 0.0, f"fm_unavailable:{reason}")

    session = fm.LanguageModelSession(model=model)
    allowed_ids = [c.id for c in candidates]

    @fm.generable
    class _Out:
        action: str
        chosen_candidate_id: Optional[str]
        confidence: float
        reason_tag: str

    prompt = (
        "You are a constrained typing arbiter. "
        "Return action and chosen_candidate_id only. "
        f"Allowed candidate ids: {allowed_ids}. "
        "If uncertain or risky, return do_nothing and null. "
        "Never invent a replacement string.\n\n"
        f"Packet: {packet}\n"
        f"Candidates: {[c.__dict__ for c in candidates]}"
    )

    out = await session.respond(prompt, guide=fm.guide(_Out))
    action = getattr(out, "action", "do_nothing")
    chosen_candidate_id = getattr(out, "chosen_candidate_id", None)
    confidence = float(getattr(out, "confidence", 0.0))
    reason_tag = str(getattr(out, "reason_tag", "fm"))

    if action not in ("do_nothing", "suggest", "auto_apply"):
        action = "do_nothing"

    if not validate_candidate_choice(chosen_candidate_id, allowed_ids):
        return ArbiterDecision("do_nothing", None, 0.0, "fm_violation_invalid_candidate_id")

    return ArbiterDecision(action, chosen_candidate_id, confidence, reason_tag)
