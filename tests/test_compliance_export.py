"""Tests for compliance export report generation."""
from __future__ import annotations

import json

import pytest

from cognitiveio.memory.local_store import LocalStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / "test.db", encryption_mode="off")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComplianceExport:
    def test_empty_store_exports(self, store, tmp_path):
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out)
        assert out.exists()
        assert report["schema_version"] == 1
        assert "machine_id_hash" in report
        assert len(report["machine_id_hash"]) == 16

    def test_block_reasons_included(self, store, tmp_path):
        store.log_privacy_event(kind="blocked", reason="corporate_policy_block", app_name="ChatGPT")
        store.log_privacy_event(kind="blocked", reason="corporate_policy_block", app_name="Claude")
        store.log_privacy_event(kind="blocked", reason="password_field")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out)
        reasons = {r["reason"]: r["count"] for r in report["block_reasons"]}
        assert reasons["corporate_policy_block"] == 2
        assert reasons["password_field"] == 1

    def test_pattern_lifecycle_included(self, store, tmp_path):
        store.upsert_pattern("teh", "the")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out)
        assert "pattern_lifecycle" in report
        assert "embryonic" in report["pattern_lifecycle"]

    def test_secret_aliases_no_values(self, store, tmp_path):
        store.register_secret_alias("DB_PASSWORD", "database password")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out)
        aliases = report["secret_aliases"]
        assert len(aliases) == 1
        assert aliases[0]["alias"] == "DB_PASSWORD"
        assert aliases[0]["usage_count"] == 1
        # Must NOT contain actual secret values.
        report_text = json.dumps(report)
        assert "password" not in report_text.lower() or "DB_PASSWORD" in report_text

    def test_exclude_pattern_stats(self, store, tmp_path):
        store.upsert_pattern("teh", "the")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out, include_pattern_stats=False)
        assert "pattern_lifecycle" not in report

    def test_exclude_secret_registry(self, store, tmp_path):
        store.register_secret_alias("KEY", "key")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out, include_secret_registry=False)
        assert "secret_aliases" not in report

    def test_exclude_block_reasons(self, store, tmp_path):
        store.log_privacy_event(kind="blocked", reason="test")
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out, include_block_reasons=False)
        assert "block_reasons" not in report

    def test_rates_from_proof_report(self, store, tmp_path):
        store.save_proof_report({
            "accept_rate": 0.72,
            "dismiss_rate": 0.20,
            "undo_rate": 0.08,
            "minutes": 10,
            "suggestion_shown": 10,
            "suggestion_accepted": 7,
            "suggestion_dismissed": 2,
            "auto_applied": 0,
            "undone": 1,
            "blocked": 5,
            "interruption_rate_per_min": 1.0,
        })
        out = tmp_path / "report.json"
        report = store.export_compliance_report(out)
        assert "rates" in report
        assert report["rates"]["accept_rate"] == 0.72

    def test_output_is_valid_json(self, store, tmp_path):
        out = tmp_path / "report.json"
        store.export_compliance_report(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_creates_parent_dirs(self, store, tmp_path):
        out = tmp_path / "deep" / "nested" / "report.json"
        store.export_compliance_report(out)
        assert out.exists()
