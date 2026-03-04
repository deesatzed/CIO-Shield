"""Phase 2c: Tests for policy/risk_scoring.py."""
from cognitiveio.policy.risk_scoring import RiskFlags, RiskAssessment, assess_risk, gate_action


class TestAssessRisk:
    def test_password_field_returns_1_0(self):
        result = assess_risk("email_docs", RiskFlags(password_field=True))
        assert result.risk_score == 1.0
        assert result.reason == "password_field"

    def test_blacklisted_app_returns_1_0(self):
        result = assess_risk("email_docs", RiskFlags(blacklisted_app=True))
        assert result.risk_score == 1.0
        assert result.reason == "excluded_app"

    def test_user_excluded_returns_1_0(self):
        result = assess_risk("email_docs", RiskFlags(user_excluded=True))
        assert result.risk_score == 1.0
        assert result.reason == "excluded_app"

    def test_unknown_profile_returns_0_9(self):
        result = assess_risk("unknown", RiskFlags())
        assert result.risk_score == 0.9
        assert result.reason == "unknown_profile"

    def test_detector_uncertain_returns_0_8(self):
        result = assess_risk("email_docs", RiskFlags(detector_uncertain=True))
        assert result.risk_score == 0.8
        assert result.reason == "detector_uncertain"

    def test_low_risk_returns_0_2(self):
        result = assess_risk("email_docs", RiskFlags())
        assert result.risk_score == 0.2
        assert result.reason == "low"

    def test_password_overrides_unknown_profile(self):
        result = assess_risk("unknown", RiskFlags(password_field=True))
        assert result.risk_score == 1.0
        assert result.reason == "password_field"


class TestGateAction:
    def test_high_risk_returns_none(self):
        assert gate_action(RiskAssessment(1.0, "password")) == "none"
        assert gate_action(RiskAssessment(0.9, "unknown")) == "none"
        assert gate_action(RiskAssessment(0.5, "threshold")) == "none"

    def test_medium_risk_returns_suggest(self):
        assert gate_action(RiskAssessment(0.2, "low")) == "suggest"
        assert gate_action(RiskAssessment(0.15, "borderline")) == "suggest"
        assert gate_action(RiskAssessment(0.49, "just_below")) == "suggest"

    def test_low_risk_returns_auto(self):
        assert gate_action(RiskAssessment(0.14, "very_low")) == "auto"
        assert gate_action(RiskAssessment(0.0, "zero")) == "auto"
