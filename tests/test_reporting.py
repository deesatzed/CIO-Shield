from cognitiveio.evidence.health_card import build_health_card
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.evidence.report_generator import (
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
