import pytest

from cognitiveio.config import Settings
from cognitiveio.context.profiles import AppContext, PROFILE_UNKNOWN, classify_profile
from cognitiveio.core import decision_engine as de
from cognitiveio.core.decision_engine import BudgetState, Candidate, decide
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.policy.risk_scoring import RiskFlags


@pytest.mark.asyncio
async def test_password_field_blocks():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(password_field=True),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=1.0)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert "blocked" in d.reason_tag


@pytest.mark.asyncio
async def test_unknown_profile_fails_safe():
    ctx = AppContext(app_name="Totally New App")
    assert classify_profile(ctx) == PROFILE_UNKNOWN
    d = await decide(
        ctx=ctx,
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=1.0)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag in {"unknown_profile", "blocked:unknown_profile"}


@pytest.mark.asyncio
async def test_code_profile_fails_safe():
    d = await decide(
        ctx=AppContext(app_name="Visual Studio Code"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="recieve", after="receive", count=7, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(auto_apply_enabled=True, suggest_only=False),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert "profile_block" in d.reason_tag


@pytest.mark.asyncio
async def test_budget_cap_blocks_suggestion():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=7, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(suggestions_shown_recent=999, now_ts=1.0),
        settings=Settings(max_suggestions_per_min=8),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "budget_cap"


@pytest.mark.asyncio
async def test_candidate_conflict_blocks_without_fm():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=False, suggestion_min_confidence=0.8),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "candidate_conflict"


@pytest.mark.asyncio
async def test_candidate_conflict_uses_fm_variant_b(monkeypatch):
    called = {"n": 0}

    async def _fake(packet, candidates, **kwargs):  # noqa: ANN001
        called["n"] += 1
        return type(
            "X",
            (),
            {
                "action": "suggest",
                "chosen_candidate_id": "c2",
                "confidence": 0.74,
                "reason_tag": "fm_conflict_resolved",
            },
        )()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    assert d.action == "suggest"
    assert d.replacement == "ten"
    assert d.reason_tag == "fm_conflict_resolved"
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_fm_variant_a_blocks_arbiter(monkeypatch):
    called = {"n": 0}

    async def _fake(packet, candidates, **kwargs):  # noqa: ANN001
        called["n"] += 1
        return type(
            "X",
            (),
            {
                "action": "suggest",
                "chosen_candidate_id": "c1",
                "confidence": 0.6,
                "reason_tag": "fm_suggest",
            },
        )()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=4, confidence=0.6)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=True, apple_fm_variant="A", suggestion_min_confidence=0.9),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "fm_variant_gate"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_fm_variant_b_allows_arbiter(monkeypatch):
    called = {"n": 0}

    async def _fake(packet, candidates, **kwargs):  # noqa: ANN001
        called["n"] += 1
        return type(
            "X",
            (),
            {
                "action": "suggest",
                "chosen_candidate_id": "c1",
                "confidence": 0.61,
                "reason_tag": "fm_suggest",
            },
        )()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=4, confidence=0.6)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=True, apple_fm_variant="B", suggestion_min_confidence=0.9),
        user_prefs={},
    )
    assert d.action == "suggest"
    assert d.replacement == "the"
    assert d.reason_tag == "fm_suggest"
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_gray_zone_fails_closed_when_fm_required_and_unavailable(monkeypatch):
    monkeypatch.setattr(de, "decide_with_apple_fm", None)
    monkeypatch.setattr(de, "FMCandidate", None)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=4, confidence=0.60)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            fm_required_for_gray_zone=True,
            suggestion_min_confidence=0.50,
        ),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "fm_required_unavailable"


# ── Phase 5: Decision engine edge cases ─────────────────────────────

@pytest.mark.asyncio
async def test_typing_fast_blocks():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(typing_fast=True, now_ts=1.0),
        settings=Settings(),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "typing_fast"


@pytest.mark.asyncio
async def test_dismissal_cooldown_blocks():
    import time
    now = time.time()
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(
            recent_dismissals=5,
            cooldown_until_ts=now + 100,
            now_ts=now,
        ),
        settings=Settings(dismissals_before_cooldown=3),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "dismissal_cooldown"


@pytest.mark.asyncio
async def test_empty_candidates_returns_no_candidates():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "no_candidates"


@pytest.mark.asyncio
async def test_high_confidence_suggests_without_fm():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=False, suggestion_min_confidence=0.80),
        user_prefs={},
    )
    assert d.action == "suggest"
    assert d.replacement == "the"
    assert d.reason_tag == "high_confidence"


@pytest.mark.asyncio
async def test_low_confidence_does_nothing():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=2, confidence=0.30)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=False, suggestion_min_confidence=0.80),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "low_confidence"


@pytest.mark.asyncio
async def test_auto_apply_not_triggered_when_risk_tier_is_suggest():
    """Auto-apply requires gate_action='auto' (risk < 0.15), but default risk is 0.2.
    Even with auto_apply_enabled, high confidence is routed to 'suggest' not 'auto_apply'."""
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.98)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=False,
            auto_apply_enabled=True,
            suggest_only=False,
            auto_apply_min_confidence=0.97,
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    # Risk score 0.2 → tier "suggest" → auto_apply gate not reached → suggest path
    assert d.action == "suggest"
    assert d.reason_tag == "high_confidence"


@pytest.mark.asyncio
async def test_terminal_profile_blocks():
    d = await decide(
        ctx=AppContext(app_name="Terminal"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert "profile_block" in d.reason_tag


@pytest.mark.asyncio
async def test_same_after_text_not_conflict():
    """Two candidates with the same 'after' text should not trigger conflict."""
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="the", count=5, confidence=0.85),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=False, suggestion_min_confidence=0.80),
        user_prefs={},
    )
    assert d.action == "suggest"
    assert d.replacement == "the"


@pytest.mark.asyncio
async def test_null_context_window_no_crash():
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(apple_fm_enabled=False),
        user_prefs=None,
    )
    assert d.action == "suggest"
    assert d.replacement == "the"


# ── Extended decision engine coverage ──────────────────────────────

@pytest.mark.asyncio
async def test_candidate_conflict_below_min_confidence():
    """No conflict when top candidate confidence is below min threshold."""
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.40),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.35),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=False,
            suggestion_min_confidence=0.30,
            candidate_conflict_min_confidence=0.55,
        ),
        user_prefs={},
    )
    # 0.40 < 0.55 min → no conflict → top candidate "the" with 0.40 >= 0.30 → suggest
    assert d.action == "suggest"
    assert d.replacement == "the"


@pytest.mark.asyncio
async def test_unknown_profile_blocked_by_risk_scoring():
    """Unknown profile gets risk=0.9 from assess_risk, blocked at tier='none' gate.
    The fail_safe_unknown_profile guard (lines 127-129) is a belt-and-suspenders
    defense that is unreachable with current risk scoring because unknown profile
    already scores 0.9 → gate 'none' → blocked at line 119-121."""
    d = await decide(
        ctx=AppContext(app_name="Totally New App"),
        flags=RiskFlags(),
        candidates=[Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=False,
            fail_safe_unknown_profile=False,
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    # Unknown profile → risk=0.9 → tier="none" → blocked regardless of fail_safe
    assert d.action == "do_nothing"
    assert "blocked" in d.reason_tag


@pytest.mark.asyncio
async def test_fm_conflict_resolved_auto_apply_downgraded(monkeypatch):
    """When FM returns auto_apply but suggest_only=True, downgrades to suggest."""
    called = {"n": 0}

    async def _fake(packet, candidates, **kwargs):
        called["n"] += 1
        return type("X", (), {
            "action": "auto_apply",
            "chosen_candidate_id": "c1",
            "confidence": 0.98,
            "reason_tag": "fm_auto",
        })()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            suggest_only=True,
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    assert d.action == "suggest"  # downgraded from auto_apply
    assert d.reason_tag == "fm_auto"
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_fm_do_nothing_result(monkeypatch):
    """When FM returns do_nothing, decision passes through."""
    async def _fake(packet, candidates, **kwargs):
        return type("X", (), {
            "action": "do_nothing",
            "chosen_candidate_id": None,
            "confidence": 0.3,
            "reason_tag": "fm_uncertain",
        })()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "fm_uncertain"


@pytest.mark.asyncio
async def test_fm_chosen_not_found(monkeypatch):
    """When FM picks a candidate ID that doesn't exist, returns fm_chosen_not_found."""
    async def _fake(packet, candidates, **kwargs):
        return type("X", (), {
            "action": "suggest",
            "chosen_candidate_id": "c_nonexistent",
            "confidence": 0.8,
            "reason_tag": "fm_suggest",
        })()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=Metrics(),
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    assert d.action == "do_nothing"
    assert d.reason_tag == "fm_chosen_not_found"


@pytest.mark.asyncio
async def test_fm_auto_apply_not_downgraded(monkeypatch):
    """When FM returns auto_apply AND suggest_only=False AND auto_apply_enabled=True,
    the action stays auto_apply and hits the auto_applied metric (line 198)."""
    async def _fake(packet, candidates, **kwargs):
        return type("X", (), {
            "action": "auto_apply",
            "chosen_candidate_id": "c1",
            "confidence": 0.99,
            "reason_tag": "fm_auto",
        })()

    monkeypatch.setattr(de, "decide_with_apple_fm", _fake)
    monkeypatch.setattr(de, "FMCandidate", Candidate)

    m = Metrics()
    d = await decide(
        ctx=AppContext(app_name="Mail"),
        flags=RiskFlags(),
        candidates=[
            Candidate(id="c1", before="teh", after="the", count=8, confidence=0.90),
            Candidate(id="c2", before="teh", after="ten", count=7, confidence=0.86),
        ],
        context_window=None,
        metrics=m,
        budget=BudgetState(now_ts=1.0),
        settings=Settings(
            apple_fm_enabled=True,
            apple_fm_variant="B",
            suggest_only=False,
            auto_apply_enabled=True,
            suggestion_min_confidence=0.80,
        ),
        user_prefs={},
    )
    assert d.action == "auto_apply"
    assert d.reason_tag == "fm_auto"
    assert m.c.auto_applied == 1
