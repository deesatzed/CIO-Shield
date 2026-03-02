from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

from cognitiveio.context.profiles import (
    AppContext,
    PROFILE_CODE,
    PROFILE_TERMINAL,
    PROFILE_UNKNOWN,
    classify_profile,
)
from cognitiveio.policy.risk_scoring import RiskFlags, assess_risk, gate_action
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.config import Settings

try:
    from cognitiveio.ai.fm_arbiter import (
        Candidate as FMCandidate,
        decide_with_apple_fm,
    )
except Exception:
    FMCandidate = None  # type: ignore
    decide_with_apple_fm = None  # type: ignore


@dataclass
class Candidate:
    id: str
    before: str
    after: str
    count: int
    confidence: float


@dataclass
class BudgetState:
    suggestions_shown_recent: int = 0
    recent_dismissals: int = 0
    typing_fast: bool = False
    cooldown_until_ts: float = 0.0
    now_ts: float = 0.0


@dataclass
class Decision:
    action: str  # do_nothing | suggest | auto_apply
    replacement: Optional[str]
    chosen_candidate_id: Optional[str]
    confidence: float
    reason_tag: str


def _top_candidate(cands: List[Candidate]) -> Optional[Candidate]:
    if not cands:
        return None
    return sorted(cands, key=lambda c: (c.confidence, c.count), reverse=True)[0]


def _has_candidate_conflict(cands: List[Candidate], settings: Settings) -> bool:
    if len(cands) < 2:
        return False
    ordered = sorted(cands, key=lambda c: (c.confidence, c.count), reverse=True)
    top = ordered[0]
    second = ordered[1]
    if top.after.strip().lower() == second.after.strip().lower():
        return False
    if top.confidence < settings.candidate_conflict_min_confidence:
        return False
    gap = top.confidence - second.confidence
    return gap <= settings.candidate_conflict_max_gap


_log = logging.getLogger(__name__)

_DECISION_PATH_WARN_SECONDS = 0.005  # 5ms target (PRODUCT_CONTRACT.md).


async def decide(
    ctx: AppContext,
    flags: RiskFlags,
    candidates: List[Candidate],
    context_window: Optional[Dict[str, str]],
    metrics: Metrics,
    budget: BudgetState,
    settings: Settings,
    user_prefs: Optional[Dict[str, Any]] = None,
) -> Decision:
    t0 = time.perf_counter()
    result = await _decide_inner(
        ctx, flags, candidates, context_window, metrics, budget, settings, user_prefs
    )
    elapsed = time.perf_counter() - t0
    if elapsed > _DECISION_PATH_WARN_SECONDS:
        _log.warning(
            "Decision path took %.1fms (target <=5ms): reason=%s",
            elapsed * 1000,
            result.reason_tag,
        )
    return result


async def _decide_inner(
    ctx: AppContext,
    flags: RiskFlags,
    candidates: List[Candidate],
    context_window: Optional[Dict[str, str]],
    metrics: Metrics,
    budget: BudgetState,
    settings: Settings,
    user_prefs: Optional[Dict[str, Any]] = None,
) -> Decision:
    profile = classify_profile(ctx)
    risk = assess_risk(profile, flags)
    tier = gate_action(risk)

    if tier == "none":
        metrics.inc("blocked", 1)
        return Decision("do_nothing", None, None, 0.0, f"blocked:{risk.reason}")

    if profile in (PROFILE_CODE, PROFILE_TERMINAL):
        metrics.inc("blocked", 1)
        return Decision("do_nothing", None, None, 0.0, f"profile_block:{profile}")

    if profile == PROFILE_UNKNOWN and settings.fail_safe_unknown_profile:
        metrics.inc("blocked", 1)
        return Decision("do_nothing", None, None, 0.0, "unknown_profile")

    if budget.typing_fast:
        return Decision("do_nothing", None, None, 0.0, "typing_fast")

    if budget.suggestions_shown_recent >= settings.max_suggestions_per_min:
        return Decision("do_nothing", None, None, 0.0, "budget_cap")

    if (
        budget.recent_dismissals >= settings.dismissals_before_cooldown
        and budget.now_ts < budget.cooldown_until_ts
    ):
        return Decision("do_nothing", None, None, 0.0, "dismissal_cooldown")

    top = _top_candidate(candidates)
    if not top:
        return Decision("do_nothing", None, None, 0.0, "no_candidates")

    has_conflict = _has_candidate_conflict(candidates, settings)
    fm_variant_b = settings.apple_fm_variant.upper() == "B"
    fm_available = (
        settings.apple_fm_enabled
        and fm_variant_b
        and decide_with_apple_fm is not None
        and FMCandidate is not None
    )

    if has_conflict and not fm_available:
        metrics.inc("blocked", 1)
        return Decision("do_nothing", None, None, top.confidence, "candidate_conflict")

    # Optional Apple FM arbiter in confidence gray-zone or candidate-conflict branch.
    if (
        fm_available
        and (
            has_conflict
            or settings.apple_fm_gray_zone_low <= top.confidence <= settings.apple_fm_gray_zone_high
        )
    ):
        pkt = {
            "profile": profile,
            "context": context_window or {},
            "flags": flags.__dict__,
            "prefs": user_prefs or {},
            "policy": {"selector_only": True, "suggest_only_default": settings.suggest_only},
        }
        fm_candidates = [
            FMCandidate(id=c.id, before=c.before, after=c.after, count=c.count, confidence=c.confidence)
            for c in candidates[:5]
        ]
        fm_d = await decide_with_apple_fm(
            pkt, fm_candidates, timeout_seconds=settings.apple_fm_timeout_seconds
        )

        if fm_d.action == "do_nothing" or fm_d.chosen_candidate_id is None:
            return Decision("do_nothing", None, None, fm_d.confidence, fm_d.reason_tag)

        chosen = next((c for c in candidates if c.id == fm_d.chosen_candidate_id), None)
        if not chosen:
            return Decision("do_nothing", None, None, 0.0, "fm_chosen_not_found")

        action = cast(str, fm_d.action)
        if action == "auto_apply" and (settings.suggest_only or not settings.auto_apply_enabled):
            action = "suggest"

        if action == "suggest":
            metrics.inc("suggestion_shown", 1)
        if action == "auto_apply":
            metrics.inc("auto_applied", 1)

        return Decision(action, chosen.after, chosen.id, fm_d.confidence, fm_d.reason_tag)

    if (
        tier == "auto"
        and settings.auto_apply_enabled
        and not settings.suggest_only
        and top.confidence >= settings.auto_apply_min_confidence
    ):
        metrics.inc("auto_applied", 1)
        return Decision("auto_apply", top.after, top.id, top.confidence, "soft_auto")

    if top.confidence >= settings.suggestion_min_confidence:
        metrics.inc("suggestion_shown", 1)
        return Decision("suggest", top.after, top.id, top.confidence, "high_confidence")

    if settings.apple_fm_enabled and settings.apple_fm_variant.upper() != "B":
        return Decision("do_nothing", None, None, top.confidence, "fm_variant_gate")

    return Decision("do_nothing", None, None, top.confidence, "low_confidence")
