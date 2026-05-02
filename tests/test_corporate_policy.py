"""Tests for corporate policy loading, parsing, expiry, merge, and enforcement."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from cognitiveio.config import Settings, settings_from_env_with_policy
from cognitiveio.context.profiles import (
    AppContext,
    PROFILE_BLOCKED_BY_POLICY,
    PROFILE_EMAIL_DOCS,
    PROFILE_UNKNOWN,
    classify_profile,
)
from cognitiveio.core.decision_engine import BudgetState, Candidate, decide
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.policy.corporate import (
    PolicyConstraints,
    _compile_patterns,
    _parse_policy,
    apply_corporate_settings,
    load_corporate_policy,
)
from cognitiveio.policy.risk_scoring import RiskFlags, assess_risk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample_policy_dict(**overrides) -> dict:
    base = {
        "schema_version": 1,
        "organization_id": "test-corp",
        "organization_name": "Test Corporation",
        "policy_issued_at": "2026-01-01T00:00:00Z",
        "policy_expires_at": "2027-01-01T00:00:00Z",
        "settings_overrides": {"db_encryption_mode": "required", "suggest_only": True},
        "pattern_library": {
            "additional_secret_patterns": ["ACME_TOKEN_[A-Z0-9]{32}", "ghp_[A-Za-z0-9]{36}"]
        },
        "profile_mandates": {
            "force_blocked_apps": ["ChatGPT", "Claude Desktop"],
            "force_blocked_bundles": ["com.openai.chatgpt"],
        },
        "retention_policy": {"audit_retention_days": 180, "prune_on_startup": True},
        "compliance_export": {
            "enabled": True,
            "include_pattern_stats": True,
            "include_secret_registry": True,
            "include_block_reasons": True,
        },
        "hooks": {"post_session_script": "/usr/local/bin/test-hook.sh"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# PolicyConstraints dataclass
# ---------------------------------------------------------------------------


class TestPolicyConstraints:
    def test_default_is_individual(self):
        p = PolicyConstraints()
        assert p.tier == "individual"
        assert not p.is_corporate
        assert not p.is_expired
        assert p.organization_id == ""

    def test_corporate_tier(self):
        p = PolicyConstraints(tier="corporate", organization_id="corp-1")
        assert p.is_corporate
        assert p.organization_id == "corp-1"

    def test_is_expired_past(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        p = PolicyConstraints(policy_expires_at=yesterday)
        assert p.is_expired

    def test_is_expired_future(self):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        p = PolicyConstraints(policy_expires_at=tomorrow)
        assert not p.is_expired

    def test_is_expired_empty(self):
        p = PolicyConstraints(policy_expires_at="")
        assert not p.is_expired

    def test_is_expired_invalid(self):
        p = PolicyConstraints(policy_expires_at="not-a-date")
        assert not p.is_expired

    def test_frozen(self):
        p = PolicyConstraints()
        with pytest.raises(AttributeError):
            p.tier = "corporate"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pattern compilation
# ---------------------------------------------------------------------------


class TestCompilePatterns:
    def test_valid_patterns(self):
        result = _compile_patterns(["ACME_[A-Z]+", "ghp_[A-Za-z0-9]{36}"])
        assert len(result) == 2
        assert result[0].search("ACME_TOKEN")

    def test_invalid_pattern_skipped(self):
        result = _compile_patterns(["valid_[A-Z]+", "[invalid("])
        assert len(result) == 1

    def test_empty_list(self):
        assert _compile_patterns([]) == ()


# ---------------------------------------------------------------------------
# Policy parsing
# ---------------------------------------------------------------------------


class TestParsePolicy:
    def test_full_policy(self):
        p = _parse_policy(_sample_policy_dict())
        assert p.is_corporate
        assert p.organization_id == "test-corp"
        assert p.organization_name == "Test Corporation"
        assert len(p.additional_secret_patterns) == 2
        assert "ChatGPT" in p.force_blocked_apps
        assert "com.openai.chatgpt" in p.force_blocked_bundles
        assert p.retention.audit_retention_days == 180
        assert p.compliance.enabled
        assert p.hooks.post_session_script == "/usr/local/bin/test-hook.sh"

    def test_missing_org_id_returns_individual(self):
        p = _parse_policy({"schema_version": 1})
        assert not p.is_corporate

    def test_invalid_schema_version(self):
        p = _parse_policy({"schema_version": 0, "organization_id": "x"})
        assert not p.is_corporate

    def test_missing_fields_use_defaults(self):
        p = _parse_policy({"schema_version": 1, "organization_id": "x"})
        assert p.is_corporate
        assert p.retention.audit_retention_days == 90
        assert not p.compliance.enabled
        assert len(p.additional_secret_patterns) == 0

    def test_bad_types_handled(self):
        d = _sample_policy_dict()
        d["settings_overrides"] = "not a dict"
        d["pattern_library"] = 42
        d["profile_mandates"] = None
        p = _parse_policy(d)
        assert p.is_corporate
        assert len(p.locked_settings) == 0

    def test_bad_types_retention_compliance_hooks(self):
        """Non-dict values for retention, compliance, hooks default gracefully."""
        d = _sample_policy_dict()
        d["retention_policy"] = "bad"
        d["compliance_export"] = 42
        d["hooks"] = [1, 2, 3]
        p = _parse_policy(d)
        assert p.is_corporate
        assert p.retention.audit_retention_days == 90
        assert not p.compliance.enabled
        assert p.hooks.post_session_script == ""

    def test_bad_patterns_non_list(self):
        """Non-list additional_secret_patterns defaults to empty."""
        d = _sample_policy_dict()
        d["pattern_library"] = {"additional_secret_patterns": "not a list"}
        p = _parse_policy(d)
        assert p.is_corporate
        assert len(p.additional_secret_patterns) == 0

    def test_profile_overrides_parsed(self):
        """force_profile_overrides are parsed from mandates."""
        d = _sample_policy_dict()
        d["profile_mandates"]["force_profile_overrides"] = {"Slack": "blocked_by_policy"}
        p = _parse_policy(d)
        assert p.force_profile_overrides.get("Slack") == "blocked_by_policy"


# ---------------------------------------------------------------------------
# Loading from file
# ---------------------------------------------------------------------------


class TestLoadCorporatePolicy:
    def test_no_file_returns_individual(self, monkeypatch):
        monkeypatch.delenv("COGNITIVEIO_CORPORATE_POLICY", raising=False)
        p = load_corporate_policy()
        assert not p.is_corporate

    def test_load_from_env_path(self, tmp_path, monkeypatch):
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(_sample_policy_dict()), encoding="utf-8")
        monkeypatch.setenv("COGNITIVEIO_CORPORATE_POLICY", str(policy_file))
        p = load_corporate_policy()
        assert p.is_corporate
        assert p.organization_id == "test-corp"

    def test_expired_policy_returns_individual(self, tmp_path, monkeypatch):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        policy_file = tmp_path / "expired.json"
        policy_file.write_text(
            json.dumps(_sample_policy_dict(policy_expires_at=yesterday)),
            encoding="utf-8",
        )
        monkeypatch.setenv("COGNITIVEIO_CORPORATE_POLICY", str(policy_file))
        p = load_corporate_policy()
        assert not p.is_corporate

    def test_invalid_json_skipped(self, tmp_path, monkeypatch):
        policy_file = tmp_path / "bad.json"
        policy_file.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("COGNITIVEIO_CORPORATE_POLICY", str(policy_file))
        p = load_corporate_policy()
        assert not p.is_corporate

    def test_non_dict_json_skipped(self, tmp_path, monkeypatch):
        policy_file = tmp_path / "array.json"
        policy_file.write_text("[1,2,3]", encoding="utf-8")
        monkeypatch.setenv("COGNITIVEIO_CORPORATE_POLICY", str(policy_file))
        p = load_corporate_policy()
        assert not p.is_corporate


# ---------------------------------------------------------------------------
# Settings merge (security can only be strengthened)
# ---------------------------------------------------------------------------


class TestApplyCorporateSettings:
    def test_individual_policy_no_change(self):
        s = Settings()
        p = PolicyConstraints()
        result = apply_corporate_settings(s, p)
        assert result.db_encryption_mode == "optional"

    def test_corporate_strengthens_encryption(self):
        s = Settings()
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"db_encryption_mode": "required"},
        )
        result = apply_corporate_settings(s, p)
        assert result.db_encryption_mode == "required"

    def test_corporate_cannot_weaken_encryption(self):
        s = Settings()
        s.db_encryption_mode = "required"
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"db_encryption_mode": "optional"},
        )
        result = apply_corporate_settings(s, p)
        assert result.db_encryption_mode == "required"

    def test_corporate_forces_suggest_only(self):
        s = Settings()
        s.suggest_only = False
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"suggest_only": True},
        )
        result = apply_corporate_settings(s, p)
        assert result.suggest_only is True

    def test_corporate_cannot_disable_suggest_only(self):
        s = Settings()
        s.suggest_only = True
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"suggest_only": False},
        )
        result = apply_corporate_settings(s, p)
        assert result.suggest_only is True

    def test_corporate_disables_auto_apply(self):
        s = Settings()
        s.auto_apply_enabled = True
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"auto_apply_enabled": False},
        )
        result = apply_corporate_settings(s, p)
        assert result.auto_apply_enabled is False

    def test_corporate_lower_budget_cap(self):
        s = Settings()  # max_suggestions_per_min = 8
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"max_suggestions_per_min": 4},
        )
        result = apply_corporate_settings(s, p)
        assert result.max_suggestions_per_min == 4

    def test_corporate_cannot_raise_budget_cap(self):
        s = Settings()  # max_suggestions_per_min = 8
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"max_suggestions_per_min": 20},
        )
        result = apply_corporate_settings(s, p)
        assert result.max_suggestions_per_min == 8

    def test_corporate_higher_cooldown(self):
        s = Settings()  # cooldown_seconds = 45
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"cooldown_seconds": 120},
        )
        result = apply_corporate_settings(s, p)
        assert result.cooldown_seconds == 120

    def test_unknown_setting_ignored(self):
        s = Settings()
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"nonexistent_field": "value"},
        )
        result = apply_corporate_settings(s, p)
        assert not hasattr(result, "nonexistent_field")

    def test_lower_numeric_invalid_value_ignored(self):
        """Non-numeric value for lower-is-stronger field is ignored."""
        s = Settings()
        original = s.max_suggestions_per_min
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"max_suggestions_per_min": "not_a_number"},
        )
        result = apply_corporate_settings(s, p)
        assert result.max_suggestions_per_min == original

    def test_higher_numeric_invalid_value_ignored(self):
        """Non-numeric value for higher-is-stronger field is ignored."""
        s = Settings()
        original = s.cooldown_seconds
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"cooldown_seconds": "bad_value"},
        )
        result = apply_corporate_settings(s, p)
        assert result.cooldown_seconds == original

    def test_lower_numeric_applies_when_lower(self):
        """Lower-is-stronger: corporate value applied when strictly lower."""
        s = Settings()
        s.dismissals_before_cooldown = 5
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"dismissals_before_cooldown": 2},
        )
        result = apply_corporate_settings(s, p)
        assert result.dismissals_before_cooldown == 2

    def test_higher_numeric_applies_when_higher(self):
        """Higher-is-stronger: corporate value applied when strictly higher."""
        s = Settings()
        s.suggestion_min_confidence = 0.5
        p = PolicyConstraints(
            tier="corporate",
            locked_settings={"suggestion_min_confidence": 0.9},
        )
        result = apply_corporate_settings(s, p)
        assert result.suggestion_min_confidence == 0.9


# ---------------------------------------------------------------------------
# Profile classification with policy
# ---------------------------------------------------------------------------


class TestProfileClassificationWithPolicy:
    def test_blocked_by_app_name(self):
        ctx = AppContext(app_name="ChatGPT")
        policy = PolicyConstraints(
            tier="corporate",
            force_blocked_apps=frozenset(["ChatGPT"]),
        )
        assert classify_profile(ctx, policy=policy) == PROFILE_BLOCKED_BY_POLICY

    def test_blocked_by_bundle_id(self):
        ctx = AppContext(app_name="SomeApp", bundle_id="com.openai.chatgpt")
        policy = PolicyConstraints(
            tier="corporate",
            force_blocked_bundles=frozenset(["com.openai.chatgpt"]),
        )
        assert classify_profile(ctx, policy=policy) == PROFILE_BLOCKED_BY_POLICY

    def test_non_blocked_app_normal(self):
        ctx = AppContext(app_name="Mail")
        policy = PolicyConstraints(
            tier="corporate",
            force_blocked_apps=frozenset(["ChatGPT"]),
        )
        assert classify_profile(ctx, policy=policy) == PROFILE_EMAIL_DOCS

    def test_no_policy_normal(self):
        ctx = AppContext(app_name="Mail")
        assert classify_profile(ctx) == PROFILE_EMAIL_DOCS

    def test_no_policy_unknown(self):
        ctx = AppContext(app_name="RandomApp")
        assert classify_profile(ctx) == PROFILE_UNKNOWN


# ---------------------------------------------------------------------------
# Risk scoring with blocked_by_policy
# ---------------------------------------------------------------------------


class TestRiskScoringWithPolicy:
    def test_blocked_by_policy_risk(self):
        risk = assess_risk("blocked_by_policy", RiskFlags())
        assert risk.risk_score == 1.0
        assert risk.reason == "corporate_policy_block"


# ---------------------------------------------------------------------------
# Decision engine with policy
# ---------------------------------------------------------------------------


class TestDecisionEngineWithPolicy:
    @pytest.mark.asyncio
    async def test_corporate_policy_blocks_app(self):
        ctx = AppContext(app_name="ChatGPT")
        policy = PolicyConstraints(
            tier="corporate",
            force_blocked_apps=frozenset(["ChatGPT"]),
        )
        candidates = [
            Candidate(id="1", before="teh", after="the", count=5, confidence=0.95)
        ]
        metrics = Metrics()
        budget = BudgetState()
        settings = Settings()

        decision = await decide(
            ctx=ctx,
            flags=RiskFlags(),
            candidates=candidates,
            context_window=None,
            metrics=metrics,
            budget=budget,
            settings=settings,
            policy=policy,
        )
        assert decision.action == "do_nothing"
        assert "corporate_policy_block" in decision.reason_tag

    @pytest.mark.asyncio
    async def test_no_policy_normal_flow(self):
        ctx = AppContext(app_name="Mail")
        candidates = [
            Candidate(id="1", before="teh", after="the", count=10, confidence=0.95)
        ]
        metrics = Metrics()
        budget = BudgetState()
        settings = Settings()

        decision = await decide(
            ctx=ctx,
            flags=RiskFlags(),
            candidates=candidates,
            context_window=None,
            metrics=metrics,
            budget=budget,
            settings=settings,
        )
        assert decision.action in {"suggest", "auto_apply"}


# ---------------------------------------------------------------------------
# settings_from_env_with_policy integration
# ---------------------------------------------------------------------------


class TestSettingsFromEnvWithPolicy:
    def test_returns_tuple(self, monkeypatch):
        monkeypatch.delenv("COGNITIVEIO_CORPORATE_POLICY", raising=False)
        settings, policy = settings_from_env_with_policy()
        assert isinstance(settings, Settings)
        assert isinstance(policy, PolicyConstraints)
        assert not policy.is_corporate

    def test_with_corporate_policy(self, tmp_path, monkeypatch):
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(_sample_policy_dict()), encoding="utf-8")
        monkeypatch.setenv("COGNITIVEIO_CORPORATE_POLICY", str(policy_file))
        settings, policy = settings_from_env_with_policy()
        assert policy.is_corporate
        assert settings.db_encryption_mode == "required"
