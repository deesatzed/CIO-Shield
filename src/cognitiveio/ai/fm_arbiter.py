from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, cast

try:
    import apple_fm_sdk as fm
except Exception:
    fm = None

_log = logging.getLogger(__name__)

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


async def decide_with_apple_fm(
    packet: Dict[str, Any],
    candidates: List[Candidate],
    timeout_seconds: float = 0.08,
) -> ArbiterDecision:
    """
    Constrained arbiter:
    - choose candidate id from provided set OR null
    - never generate replacement text
    - enforces timeout (default 80ms per PRODUCT_CONTRACT.md)
    """
    if fm is None:
        return ArbiterDecision("do_nothing", None, 0.0, "fm_unavailable:sdk_missing")

    try:
        return await asyncio.wait_for(
            _fm_arbiter_call(packet, candidates),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        _log.warning("FM arbiter timed out after %.0fms", timeout_seconds * 1000)
        return ArbiterDecision("do_nothing", None, 0.0, "fm_timeout")
    except Exception:
        _log.warning("FM arbiter failed", exc_info=True)
        return ArbiterDecision("do_nothing", None, 0.0, "fm_error")


async def _fm_arbiter_call(
    packet: Dict[str, Any], candidates: List[Candidate]
) -> ArbiterDecision:
    """Inner FM call, separated so asyncio.wait_for can cancel it."""
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

    try:
        # Newer SDKs use `generating`, older ones may still use guide().
        out = await session.respond(prompt, generating=_Out)
    except TypeError:
        out = await session.respond(prompt, guide=fm.guide(_Out))
    action = getattr(out, "action", "do_nothing")
    chosen_candidate_id = getattr(out, "chosen_candidate_id", None)
    confidence = float(getattr(out, "confidence", 0.0))
    reason_tag = str(getattr(out, "reason_tag", "fm"))

    if action not in ("do_nothing", "suggest", "auto_apply"):
        action = "do_nothing"

    if not validate_candidate_choice(chosen_candidate_id, allowed_ids):
        return ArbiterDecision("do_nothing", None, 0.0, "fm_violation_invalid_candidate_id")

    return ArbiterDecision(cast(Action, action), chosen_candidate_id, confidence, reason_tag)
