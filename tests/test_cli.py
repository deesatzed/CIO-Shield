"""Phase 4: CLI command tests using typer.testing.CliRunner.

All commands run against real LocalStore via tmp_path — no mocks.
"""
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cognitiveio.cli import app
import cognitiveio.cli as cli_module
from cognitiveio.config import Settings
from cognitiveio.memory.local_store import LocalStore

runner = CliRunner()


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch):
    """Patch CLI internals to use tmp_path as the app home.

    The Settings dataclass default for app_home is evaluated at module import
    time, so monkeypatch.setenv alone doesn't override it for CLI commands.
    We monkeypatch _get_store and settings_from_env to use tmp_path.
    """
    monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
    monkeypatch.setenv("COGNITIVEIO_ENABLE_APPLE_FM", "0")

    def _patched_get_store():
        settings = Settings(app_home=tmp_path, apple_fm_enabled=False)
        store = LocalStore(settings.db_path)
        return store, settings

    monkeypatch.setattr(cli_module, "_get_store", _patched_get_store)

    # Also patch settings_from_env for commands that call it directly
    def _patched_settings():
        return Settings(app_home=tmp_path, apple_fm_enabled=False)

    monkeypatch.setattr(cli_module, "settings_from_env", _patched_settings)
    return tmp_path


def _seed_store(home: Path) -> LocalStore:
    """Create and seed a real store in the given home directory."""
    db_path = home / "cognitiveio.db"
    store = LocalStore(db_path)
    for _ in range(8):
        store.upsert_pattern("teh", "the")
    store.record_feedback("teh", "the", accepted=True)
    store.record_feedback("teh", "the", accepted=True)
    return store


# ── Schema & status commands ────────────────────────────────────────

def test_schema_check(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["schema-check"])
    assert result.exit_code == 0
    assert "Schema check passed" in result.output


def test_arbiter_status(cli_env):
    result = runner.invoke(app, ["arbiter-status"])
    assert result.exit_code == 0
    assert "apple_fm_enabled=" in result.output


def test_requirements_check(cli_env):
    result = runner.invoke(app, ["requirements-check", "--no-strict"])
    assert result.exit_code == 0


# ── Report commands ─────────────────────────────────────────────────

def test_proof_report_empty(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["proof-report"])
    assert result.exit_code == 1
    assert "No proof report found" in result.output


def test_proof_report_with_data(cli_env):
    store = _seed_store(cli_env)
    store.save_proof_report({
        "minutes": 5.0, "suggestion_shown": 10, "suggestion_accepted": 6,
        "suggestion_dismissed": 3, "auto_applied": 0, "undone": 1, "blocked": 2,
        "interruption_rate_per_min": 2.0, "accept_rate": 0.6, "dismiss_rate": 0.3,
        "undo_rate": 0.0, "top_patterns": [], "top_block_reasons": [],
        "blocked_protected_context": 1, "blocked_trust_circuit": 0,
        "blocked_candidate_conflict": 0, "blocked_profile_or_unknown": 1,
    })
    store.close()
    result = runner.invoke(app, ["proof-report"])
    assert result.exit_code == 0
    assert "CIO-II - Proof Report" in result.output


def test_health_card_empty(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["health-card"])
    assert result.exit_code == 1
    assert "No proof report found" in result.output


def test_health_card_with_data(cli_env):
    store = _seed_store(cli_env)
    store.save_proof_report({
        "minutes": 5.0, "suggestion_shown": 10, "suggestion_accepted": 6,
        "suggestion_dismissed": 3, "auto_applied": 0, "undone": 1, "blocked": 2,
        "interruption_rate_per_min": 2.0, "accept_rate": 0.6, "dismiss_rate": 0.3,
        "undo_rate": 0.0, "blocked_trust_circuit": 0,
        "blocked_candidate_conflict": 0, "blocked_protected_context": 1,
    })
    store.close()
    result = runner.invoke(app, ["health-card"])
    assert result.exit_code == 0
    assert "Organism Health Card" in result.output


# ── Privacy ledger ──────────────────────────────────────────────────

def test_privacy_ledger_empty(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["privacy-ledger"])
    assert result.exit_code == 0
    assert "empty" in result.output.lower()


def test_privacy_ledger_with_events(cli_env):
    store = _seed_store(cli_env)
    store.log_privacy_event(kind="blocked", reason="test", app_name="Mail")
    store.close()
    result = runner.invoke(app, ["privacy-ledger"])
    assert result.exit_code == 0
    assert "Privacy Ledger" in result.output or "blocked" in result.output.lower()


def test_privacy_ledger_export(cli_env):
    store = _seed_store(cli_env)
    store.log_privacy_event(kind="blocked", reason="test_export")
    store.close()
    export_path = cli_env / "ledger_export.json"
    result = runner.invoke(app, ["privacy-ledger", "--export-path", str(export_path)])
    assert result.exit_code == 0
    assert export_path.exists()
    data = json.loads(export_path.read_text(encoding="utf-8"))
    assert "events" in data


# ── Phrase commands ─────────────────────────────────────────────────

def test_phrase_add_and_list(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["phrase-add", ".sig", "Best regards"])
    assert result.exit_code == 0
    assert "Saved phrase" in result.output

    result = runner.invoke(app, ["phrase-list"])
    assert result.exit_code == 0
    assert ".sig" in result.output


def test_phrase_add_empty_trigger(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["phrase-add", " ", "expansion"])
    assert result.exit_code == 1
    assert "Trigger cannot be empty" in result.output


def test_phrase_add_empty_expansion(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["phrase-add", ".sig", " "])
    assert result.exit_code == 1
    assert "Expansion cannot be empty" in result.output


def test_phrase_remove_success(cli_env):
    _seed_store(cli_env).close()
    runner.invoke(app, ["phrase-add", ".hw", "Hello World"])
    result = runner.invoke(app, ["phrase-remove", ".hw"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_phrase_remove_not_found(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["phrase-remove", "nonexistent"])
    assert result.exit_code == 1
    assert "No matching" in result.output


def test_phrase_list_empty(cli_env):
    # Use a fresh store (no phrase commands run before)
    store = LocalStore(cli_env / "cognitiveio.db")
    store.close()
    result = runner.invoke(app, ["phrase-list"])
    assert result.exit_code == 0
    assert "No phrase patterns found" in result.output


# ── Data management ─────────────────────────────────────────────────

def test_delete_all_without_confirm(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["delete-all"])
    assert result.exit_code == 1
    assert "Refusing" in result.output


def test_delete_all_with_confirm(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["delete-all", "--confirm"])
    assert result.exit_code == 0
    assert "Deleted all" in result.output


def test_seed_language_assets(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["seed-language-assets"])
    assert result.exit_code == 0
    assert "Seeded language assets" in result.output


def test_explain_last_no_snapshot(cli_env):
    # Ensure report dir exists but no snapshot file
    (cli_env / "reports").mkdir(parents=True, exist_ok=True)
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 1
    assert "No decision snapshot found" in result.output


def test_explain_last_with_snapshot(cli_env):
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "action": "suggest", "reason_tag": "high_confidence",
        "app_name": "Mail", "profile": "email_docs", "token": "teh",
        "idle_ms": 400, "typing_fast": False,
        "trust_cooldown_remaining_seconds": 0, "candidates": [],
    }
    (report_dir / "latest_decision.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 0
    assert "high_confidence" in result.output


def test_explain_last_json_output(cli_env):
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {"action": "do_nothing", "reason_tag": "paused"}
    (report_dir / "latest_decision.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    result = runner.invoke(app, ["explain-last", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output.strip())
    assert parsed["action"] == "do_nothing"


# ── Extended CLI coverage tests ────────────────────────────────────

def test_explain_last_malformed_json(cli_env):
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest_decision.json").write_text("NOT JSON {{", encoding="utf-8")
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 1
    assert "Failed to parse" in result.output


def test_explain_last_invalid_type(cli_env):
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest_decision.json").write_text('"just a string"', encoding="utf-8")
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()


def test_explain_last_with_candidates(cli_env):
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "action": "suggest", "reason_tag": "high_confidence",
        "app_name": "Mail", "profile": "email_docs", "token": "teh",
        "idle_ms": 400, "typing_fast": False,
        "trust_cooldown_remaining_seconds": 0,
        "candidates": [
            {"id": "c1", "before": "teh", "after": "the", "confidence": 0.95},
        ],
    }
    (report_dir / "latest_decision.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 0
    assert "Candidate" in result.output
    assert "teh" in result.output


def test_required_secrets_empty(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["required-secrets"])
    assert result.exit_code == 0
    assert "No secret aliases" in result.output


def test_required_secrets_with_data(cli_env):
    store = _seed_store(cli_env)
    store.register_secret_alias("MY_KEY")
    store.close()
    result = runner.invoke(app, ["required-secrets"])
    assert result.exit_code == 0
    assert "MY_KEY" in result.output


def test_requirements_check_strict(cli_env):
    """requirements-check with --strict exits non-zero when checks fail on CI."""
    result = runner.invoke(app, ["requirements-check", "--strict"])
    # On CI/non-macOS, checks may fail → exit 1; on real macOS, may pass → exit 0
    assert result.exit_code in {0, 1}


def test_run_invalid_mode(cli_env):
    result = runner.invoke(app, ["run", "--mode", "invalid_mode"])
    assert result.exit_code == 1
    assert "Invalid mode" in result.output


def test_build_resolver():
    """Test the _build_resolver helper."""
    from cognitiveio.cli import _build_resolver
    resolver = _build_resolver(cache_ttl_seconds=60.0)
    assert resolver is not None
    assert resolver.cache_ttl_seconds == 60.0


def test_resolve_secret_ref_empty():
    """Test _resolve_secret_ref with empty input."""
    from cognitiveio.cli import _resolve_secret_ref
    from cognitiveio.security.resolver import SecretResolver
    resolver = SecretResolver()
    assert _resolve_secret_ref("", resolver) == ""


def test_resolve_secret_ref_no_alias():
    """Test _resolve_secret_ref with plain text (no alias)."""
    from cognitiveio.cli import _resolve_secret_ref
    from cognitiveio.security.resolver import SecretResolver
    resolver = SecretResolver()
    assert _resolve_secret_ref("plain_text", resolver) == "plain_text"


def test_resolve_secret_ref_unresolved():
    """Test _resolve_secret_ref returns empty when alias cannot be resolved."""
    from cognitiveio.cli import _resolve_secret_ref
    from cognitiveio.security.resolver import SecretResolver
    resolver = SecretResolver()
    result = _resolve_secret_ref("{{SECRET:MISSING}}", resolver)
    assert result == ""


def test_build_store(cli_env):
    """Test _build_store creates a real LocalStore."""
    from cognitiveio.cli import _build_store
    settings = Settings(app_home=cli_env, apple_fm_enabled=False)
    store = _build_store(settings)
    assert store is not None
    store.close()


def test_phrase_remove_all_profiles(cli_env):
    _seed_store(cli_env).close()
    runner.invoke(app, ["phrase-add", ".test", "Test Phrase", "--profile", "email_docs"])
    runner.invoke(app, ["phrase-add", ".test", "Test Phrase", "--profile", "chat"])
    result = runner.invoke(app, ["phrase-remove", ".test", "--all-profiles"])
    assert result.exit_code == 0
    assert "Removed" in result.output
    assert "*" in result.output


def test_phrase_add_with_custom_confidence(cli_env):
    _seed_store(cli_env).close()
    result = runner.invoke(app, ["phrase-add", ".greet", "Hello!", "--confidence", "0.80"])
    assert result.exit_code == 0
    assert "0.80" in result.output


def test_demo_command(cli_env):
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Demo Episodes" in result.output or "Saved" in result.output


def test_render_requirements_report():
    """Test _render_requirements_report with a real report object."""
    from cognitiveio.cli import _render_requirements_report
    from cognitiveio.platform_requirements import RequirementReport, RequirementCheck
    report = RequirementReport(checks=[
        RequirementCheck(name="OS", required="macOS", current="Darwin", passed=True),
        RequirementCheck(name="Chip", required="arm64", current="arm64", passed=True),
    ])
    _render_requirements_report(report)  # Should not raise


def test_print_requirements_remediation_fm():
    """Test _print_requirements_remediation with FM SDK import error."""
    from cognitiveio.cli import _print_requirements_remediation
    from cognitiveio.platform_requirements import RequirementReport, RequirementCheck
    report = RequirementReport(checks=[
        RequirementCheck(
            name="Apple FM runtime availability",
            required="SystemLanguageModel available",
            current="unavailable",
            passed=False,
            details="sdk_import_error:ModuleNotFoundError",
        ),
    ])
    _print_requirements_remediation(report)  # Should not raise


def test_requirements_check_with_remediation(cli_env):
    """requirements-check --no-strict prints remediation on failure."""
    result = runner.invoke(app, ["requirements-check", "--no-strict"])
    assert result.exit_code == 0


def test_seed_headless_defaults(cli_env):
    """Test _seed_headless_defaults populates store."""
    from cognitiveio.cli import _seed_headless_defaults
    store = LocalStore(cli_env / "cognitiveio.db")
    _seed_headless_defaults(store)
    candidates = store.get_candidates_for_token("teh")
    assert candidates
    store.close()


def test_run_headless_loop_commands(cli_env, monkeypatch):
    """Test _run_headless_loop processes commands via patched input()."""
    from cognitiveio.cli import _run_headless_loop
    from cognitiveio.runtime.app_runtime import AppRuntime

    settings = Settings(app_home=cli_env, apple_fm_enabled=False)
    store = LocalStore(settings.db_path)
    runtime = AppRuntime(settings=settings, store=store)

    inputs = iter(["/panic", "/undo", "/accept", "/dismiss", "teh", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    _run_headless_loop(runtime, settings, store, app_name="Mail")
    store.close()


def test_run_headless_empty_exit(cli_env, monkeypatch):
    """Test _run_headless_loop exits on empty input."""
    from cognitiveio.cli import _run_headless_loop
    from cognitiveio.runtime.app_runtime import AppRuntime

    settings = Settings(app_home=cli_env, apple_fm_enabled=False)
    store = LocalStore(settings.db_path)
    runtime = AppRuntime(settings=settings, store=store)

    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    _run_headless_loop(runtime, settings, store, app_name="Mail")
    store.close()


def test_resolve_secret_ref_resolved(monkeypatch):
    """Test _resolve_secret_ref with a resolvable alias."""
    from cognitiveio.cli import _resolve_secret_ref
    from cognitiveio.security.resolver import SecretResolver

    monkeypatch.setenv("COGNITIVEIO_SECRET_DB_KEY", "real_key_value")
    resolver = SecretResolver()
    result = _resolve_secret_ref("{{SECRET:DB_KEY}}", resolver)
    assert result == "real_key_value"


def test_schema_check_missing_tables(cli_env):
    """schema-check fails when tables are missing."""
    import sqlite3
    db_path = cli_env / "cognitiveio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS error_patterns (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    # _get_store creates all tables, so we need to patch it to return a raw store
    def _patched_get_store():
        # Recreate with only one table to simulate missing schema
        s = Settings(app_home=cli_env, apple_fm_enabled=False)
        conn2 = sqlite3.connect(str(s.db_path))
        conn2.row_factory = sqlite3.Row
        # Create a minimal store that has .conn but missing tables
        class FakeStore:
            def __init__(self):
                self.conn = conn2
            def close(self):
                conn2.close()
        return FakeStore(), s

    import cognitiveio.cli as cli_mod
    original = cli_mod._get_store
    cli_mod._get_store = _patched_get_store
    try:
        result = runner.invoke(app, ["schema-check"])
        assert result.exit_code == 1
        assert "Missing schema tables" in result.output
    finally:
        cli_mod._get_store = original


def test_run_headless_mode(cli_env, monkeypatch):
    """Test run command with headless mode exits cleanly."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    result = runner.invoke(app, ["run", "--mode", "headless"])
    assert result.exit_code == 0
    assert "Saved report" in result.output


def test_explain_last_with_non_dict_candidates(cli_env):
    """Test explain-last with a non-dict entry in candidates list (line 478 continue)."""
    report_dir = cli_env / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "action": "suggest", "reason_tag": "high_confidence",
        "app_name": "Mail", "profile": "email_docs", "token": "teh",
        "idle_ms": 400, "typing_fast": False,
        "trust_cooldown_remaining_seconds": 0,
        "candidates": [
            "not_a_dict",  # should be skipped (line 478)
            {"id": "c1", "before": "teh", "after": "the", "confidence": 0.95},
        ],
    }
    (report_dir / "latest_decision.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    result = runner.invoke(app, ["explain-last"])
    assert result.exit_code == 0
    assert "Candidate" in result.output


def test_requirements_check_strict_with_failing_report(cli_env, monkeypatch):
    """requirements-check --strict exits 1 and prints remediation when checks fail."""
    from cognitiveio.platform_requirements import RequirementReport, RequirementCheck

    failing_report = RequirementReport(checks=[
        RequirementCheck(name="Operating system", required="macOS", current="Linux", passed=False),
        RequirementCheck(
            name="Apple FM runtime availability",
            required="SystemLanguageModel available",
            current="unavailable",
            passed=False,
            details="sdk_import_error:ModuleNotFoundError",
        ),
    ])
    monkeypatch.setattr(cli_module, "evaluate_platform_requirements", lambda: failing_report)
    result = runner.invoke(app, ["requirements-check", "--strict"])
    assert result.exit_code == 1
