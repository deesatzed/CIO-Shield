"""Unit tests for ai/fm_arbiter.py — non-live paths (SDK missing, timeout, error, validation)."""
import pytest

from cognitiveio.ai.fm_arbiter import (
    ArbiterDecision,
    Candidate,
    decide_with_apple_fm,
    validate_candidate_choice,
)


# ── validate_candidate_choice ──────────────────────────────────────

def test_validate_none_choice():
    assert validate_candidate_choice(None, ["a", "b"]) is True


def test_validate_valid_choice():
    assert validate_candidate_choice("a", ["a", "b"]) is True


def test_validate_invalid_choice():
    assert validate_candidate_choice("x", ["a", "b"]) is False


def test_validate_empty_allowed():
    assert validate_candidate_choice("a", []) is False
    assert validate_candidate_choice(None, []) is True


# ── decide_with_apple_fm (SDK unavailable) ─────────────────────────

@pytest.mark.asyncio
async def test_fm_fails_closed_on_error():
    """FM arbiter returns do_nothing when SDK errors at runtime."""
    result = await decide_with_apple_fm(
        packet={"profile": "email_docs"},
        candidates=[Candidate(id="c1", before="teh", after="the", count=5, confidence=0.9)],
    )
    assert isinstance(result, ArbiterDecision)
    assert result.action == "do_nothing"
    # SDK may be missing (sdk_missing), or installed but broken (fm_error/fm_unavailable)
    assert result.reason_tag in {
        "fm_unavailable:sdk_missing",
        "fm_error",
        "fm_timeout",
    } or "unavailable" in result.reason_tag


# ── ArbiterDecision dataclass ──────────────────────────────────────

def test_arbiter_decision_fields():
    d = ArbiterDecision(action="suggest", chosen_candidate_id="c1", confidence=0.85, reason_tag="fm_suggest")
    assert d.action == "suggest"
    assert d.chosen_candidate_id == "c1"
    assert d.confidence == 0.85
    assert d.reason_tag == "fm_suggest"


# ── Candidate dataclass ───────────────────────────────────────────

def test_candidate_fields():
    c = Candidate(id="c1", before="teh", after="the", count=10, confidence=0.95)
    assert c.id == "c1"
    assert c.before == "teh"
    assert c.after == "the"
    assert c.count == 10
    assert c.confidence == 0.95
