from cognitiveio.evidence.health_card import build_health_card, render_health_card, OrganismHealthCard
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.evidence.report_generator import (
    ProofReport,
    build_report,
    build_report_trend,
    generate_report_text,
    render_report_trend_text,
)


def test_report_includes_block_breakdown():
    m = Metrics()
    m.inc("suggestion_shown", 10)
    m.inc("suggestion_accepted", 5)
    m.inc("suggestion_dismissed", 3)
    m.inc("blocked", 4)

    report = build_report(
        metrics=m,
        top_patterns=[],
        top_block_reasons=[
            {"reason": "trust_circuit_breaker", "count": 2},
            {"reason": "candidate_conflict", "count": 1},
            {"reason": "password_or_excluded", "count": 1},
            {"reason": "profile_block:code", "count": 1},
            {"reason": "unknown_profile", "count": 1},
        ],
    )

    assert report.blocked_trust_circuit == 2
    assert report.blocked_candidate_conflict == 1
    assert report.blocked_protected_context >= 1
    assert report.blocked_profile_or_unknown >= 2

    text = generate_report_text(report)
    assert "Safety block breakdown:" in text
    assert "trust_circuit=2" in text


def test_health_card_adapts_to_trust_signals():
    card = build_health_card(
        {
            "accept_rate": 0.4,
            "dismiss_rate": 0.2,
            "blocked": 5,
            "blocked_trust_circuit": 3,
            "blocked_candidate_conflict": 2,
            "blocked_protected_context": 1,
        }
    )
    assert "trust" in card.biggest_risk.lower()
    assert "confidence" in card.first_iteration_focus.lower() or "trust-circuit" in card.first_iteration_focus.lower()


def test_report_trendline_text():
    history = [
        {
            "accept_rate": 0.50,
            "dismiss_rate": 0.20,
            "interruption_rate_per_min": 3.0,
            "blocked_trust_circuit": 1,
            "blocked_candidate_conflict": 1,
        },
        {
            "accept_rate": 0.35,
            "dismiss_rate": 0.30,
            "interruption_rate_per_min": 4.1,
            "blocked_trust_circuit": 3,
            "blocked_candidate_conflict": 2,
        },
    ]
    trend = build_report_trend(history)
    text = render_report_trend_text(trend)
    assert "Trendline" in text
    assert "accept_delta=" in text


# ── Phase 3: Extended report tests ──────────────────────────────────

def test_generate_report_text_with_patterns():
    report = ProofReport(
        minutes=5.0, suggestion_shown=10, suggestion_accepted=6,
        suggestion_dismissed=3, auto_applied=1, undone=0, blocked=2,
        interruption_rate_per_min=2.0, accept_rate=0.6, dismiss_rate=0.3,
        undo_rate=0.0,
        top_patterns=[
            {"before": "teh", "after": "the", "count": 8, "confidence": 0.95,
             "lifecycle_state": "thriving", "success_count": 5, "failure_count": 1},
        ],
        top_block_reasons=[{"reason": "password_or_excluded", "count": 2}],
    )
    text = generate_report_text(report)
    assert "teh -> the" in text
    assert "Top patterns:" in text
    assert "life thriving" in text


def test_generate_report_text_no_patterns():
    report = ProofReport(
        minutes=1.0, suggestion_shown=0, suggestion_accepted=0,
        suggestion_dismissed=0, auto_applied=0, undone=0, blocked=0,
        interruption_rate_per_min=0.0, accept_rate=0.0, dismiss_rate=0.0,
        undo_rate=0.0, top_patterns=[], top_block_reasons=[],
    )
    text = generate_report_text(report)
    assert "CIO-II - Proof Report" in text
    assert "Top patterns:" not in text


def test_generate_report_text_empty_blocks():
    report = ProofReport(
        minutes=2.0, suggestion_shown=5, suggestion_accepted=3,
        suggestion_dismissed=2, auto_applied=0, undone=0, blocked=0,
        interruption_rate_per_min=2.5, accept_rate=0.6, dismiss_rate=0.4,
        undo_rate=0.0, top_patterns=[], top_block_reasons=[],
    )
    text = generate_report_text(report)
    assert "Safety block breakdown:" in text
    assert "Top block reasons:" not in text


def test_report_trend_single_session():
    history = [{"accept_rate": 0.5, "dismiss_rate": 0.2, "interruption_rate_per_min": 1.0,
                "blocked_trust_circuit": 0, "blocked_candidate_conflict": 0}]
    trend = build_report_trend(history)
    assert trend.sessions == 1
    text = render_report_trend_text(trend)
    assert "only one session" in text.lower()


def test_report_trend_empty_history():
    trend = build_report_trend([])
    assert trend.sessions == 0
    assert trend.accept_rate_delta == 0.0


def test_report_trend_multi_session_deltas():
    history = [
        {"accept_rate": 0.7, "dismiss_rate": 0.1, "interruption_rate_per_min": 2.0,
         "blocked_trust_circuit": 0, "blocked_candidate_conflict": 0},
        {"accept_rate": 0.5, "dismiss_rate": 0.3, "interruption_rate_per_min": 4.0,
         "blocked_trust_circuit": 2, "blocked_candidate_conflict": 1},
    ]
    trend = build_report_trend(history)
    assert trend.sessions == 2
    assert trend.accept_rate_delta > 0  # 0.7 - 0.5 = 0.2
    assert trend.dismiss_rate_delta < 0  # 0.1 - 0.3 = -0.2
    text = render_report_trend_text(trend)
    assert "sessions=2" in text


def test_proof_report_to_dict_roundtrip():
    report = ProofReport(
        minutes=3.0, suggestion_shown=5, suggestion_accepted=3,
        suggestion_dismissed=2, auto_applied=0, undone=0, blocked=1,
        interruption_rate_per_min=1.67, accept_rate=0.6, dismiss_rate=0.4,
        undo_rate=0.0, top_patterns=[], top_block_reasons=[],
        blocked_protected_context=1, blocked_trust_circuit=0,
        blocked_candidate_conflict=0, blocked_profile_or_unknown=0,
    )
    d = report.to_dict()
    assert d["minutes"] == 3.0
    assert d["suggestion_shown"] == 5
    assert d["blocked_protected_context"] == 1
    assert isinstance(d["top_patterns"], list)


def test_metrics_zero_division_safety():
    m = Metrics()
    snap = m.snapshot()
    assert snap["accept_rate"] == 0.0
    assert snap["dismiss_rate"] == 0.0
    assert snap["undo_rate"] == 0.0


def test_metrics_inc_unknown_raises():
    m = Metrics()
    try:
        m.inc("nonexistent_metric")
        assert False, "Should have raised AttributeError"
    except AttributeError:
        pass


def test_build_health_card_no_trust_blocks():
    card = build_health_card({
        "accept_rate": 0.7, "dismiss_rate": 0.1, "blocked": 0,
        "blocked_trust_circuit": 0, "blocked_candidate_conflict": 0,
        "blocked_protected_context": 0,
    })
    assert "false positive" in card.biggest_risk.lower()
    assert "precision" in card.first_iteration_focus.lower() or "suggestion" in card.first_iteration_focus.lower()


def test_render_health_card_all_fields():
    card = OrganismHealthCard(
        application="CIO-II", sota_confidence=7.0, architecture_score=19.0,
        evolution_readiness=3.5, complexity_budget_used=45,
        ethical_risk_level="Low", strongest_organ="Decision + Safety Gates",
        weakest_organ="Pattern confidence calibration",
        biggest_risk="Trust circuit breaker activations",
        biggest_blind_spot="Cross-app cursor restore edge cases",
        first_iteration_focus="Reduce trust-circuit activations",
        kill_criteria="If accept_rate < 0.20 for 30 consecutive sessions",
    )
    text = render_health_card(card)
    assert "CIO-II" in text
    assert "7.0/10" in text
    assert "19.0/25" in text
    assert "45/100" in text
    assert "Kill criteria:" in text
