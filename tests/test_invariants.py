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
