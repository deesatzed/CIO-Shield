"""Tests for session profile tracking, warmth state, and onboarding lifecycle."""
from __future__ import annotations

from pathlib import Path

import pytest

from cognitiveio.config import Settings
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent


# ---------------------------------------------------------------------------
# LocalStore session methods
# ---------------------------------------------------------------------------


class TestLocalStoreSessionMethods:
    def test_start_session(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("sess_001")
        row = store.get_session("sess_001")
        assert row is not None
        assert row["session_id"] == "sess_001"
        assert row["warmth_state"] == "embryonic"
        assert row["end_ts"] is None
        store.close()

    def test_update_session(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("sess_002")
        store.update_session(
            "sess_002",
            suggestions_shown=20,
            suggestions_accepted=10,
            suggestions_dismissed=5,
            dominant_app="Mail",
            dominant_profile="email_docs",
        )
        row = store.get_session("sess_002")
        assert row is not None
        assert row["suggestions_shown"] == 20
        assert row["suggestions_accepted"] == 10
        assert row["dominant_app"] == "Mail"
        assert row["warmth_state"] == "mature"  # 10/20 = 50% >= 35%
        store.close()

    def test_end_session(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("sess_003")
        assert store.get_session("sess_003")["end_ts"] is None
        store.end_session("sess_003")
        row = store.get_session("sess_003")
        assert row["end_ts"] is not None
        store.close()

    def test_list_sessions(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("sess_a")
        store.start_session("sess_b")
        store.start_session("sess_c")
        sessions = store.list_sessions(limit=2)
        assert len(sessions) == 2
        store.close()

    def test_session_count(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        assert store.session_count() == 0
        store.start_session("sess_x")
        store.start_session("sess_y")
        assert store.session_count() == 2
        store.close()

    def test_get_session_missing(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        assert store.get_session("nonexistent") is None
        store.close()

    def test_duplicate_session_id_ignored(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("dup_001")
        store.start_session("dup_001")  # INSERT OR IGNORE
        assert store.session_count() == 1
        store.close()

    def test_delete_all_clears_sessions(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("to_delete")
        assert store.session_count() == 1
        store.delete_all()
        assert store.session_count() == 0
        store.close()


# ---------------------------------------------------------------------------
# Warmth state derivation
# ---------------------------------------------------------------------------


class TestWarmthState:
    def test_embryonic_below_threshold(self):
        assert LocalStore.derive_warmth_state(5, 3) == "embryonic"

    def test_embryonic_zero(self):
        assert LocalStore.derive_warmth_state(0, 0) == "embryonic"

    def test_learning_threshold_met_low_accept(self):
        # 15 shown, 3 accepted = 20% < 35%
        assert LocalStore.derive_warmth_state(15, 3) == "learning"

    def test_mature_threshold_met_good_accept(self):
        # 15 shown, 8 accepted = 53% >= 35%
        assert LocalStore.derive_warmth_state(15, 8) == "mature"

    def test_mature_exact_threshold(self):
        # 20 shown, 7 accepted = 35% >= 35%
        assert LocalStore.derive_warmth_state(20, 7) == "mature"

    def test_learning_just_below_threshold(self):
        # 20 shown, 6 accepted = 30% < 35%
        assert LocalStore.derive_warmth_state(20, 6) == "learning"

    def test_overall_warmth_no_sessions(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        assert store.overall_warmth_state() == "embryonic"
        store.close()

    def test_overall_warmth_with_sessions(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        store.start_session("s1")
        store.update_session("s1", suggestions_shown=20, suggestions_accepted=15)
        assert store.overall_warmth_state() == "mature"
        store.close()

    def test_overall_warmth_mixed_sessions(self, tmp_path: Path):
        store = LocalStore(tmp_path / "test.db", encryption_mode="off")
        # Lots of embryonic sessions
        for i in range(5):
            store.start_session(f"embryonic_{i}")
            store.update_session(f"embryonic_{i}", suggestions_shown=2, suggestions_accepted=1)
        # Total: 10 shown, 5 accepted across 5 sessions -> embryonic (below 15 threshold)
        assert store.overall_warmth_state() == "embryonic"
        store.close()


# ---------------------------------------------------------------------------
# AppRuntime session integration
# ---------------------------------------------------------------------------


class TestAppRuntimeSession:
    @pytest.fixture
    def runtime_and_store(self, tmp_path: Path):
        settings = Settings(app_home=tmp_path, apple_fm_enabled=False)
        store = LocalStore(settings.db_path, encryption_mode="off")
        runtime = AppRuntime(settings=settings, store=store)
        yield runtime, store
        store.close()

    def test_session_created_on_init(self, runtime_and_store):
        runtime, store = runtime_and_store
        assert runtime.session_id
        row = store.get_session(runtime.session_id)
        assert row is not None
        assert row["warmth_state"] == "embryonic"

    def test_warmth_state_property(self, runtime_and_store):
        runtime, store = runtime_and_store
        assert runtime.warmth_state == "embryonic"

    @pytest.mark.asyncio
    async def test_boundary_event_tracks_app(self, runtime_and_store):
        runtime, store = runtime_and_store
        event = RuntimeEvent(
            kind="boundary",
            app_name="Mail",
            token="teh",
            boundary=" ",
            idle_ms=500,
        )
        await runtime.process_boundary_event(event)
        assert runtime._session_app_counter["Mail"] == 1

    @pytest.mark.asyncio
    async def test_build_report_flushes_session(self, runtime_and_store):
        runtime, store = runtime_and_store
        # Process a boundary event to populate counters
        event = RuntimeEvent(
            kind="boundary",
            app_name="Mail",
            token="teh",
            boundary=" ",
            idle_ms=500,
        )
        await runtime.process_boundary_event(event)

        runtime.build_report()
        row = store.get_session(runtime.session_id)
        assert row is not None
        assert row["end_ts"] is not None  # session ended
        assert row["dominant_app"] == "Mail"

    @pytest.mark.asyncio
    async def test_session_tracks_multiple_apps(self, runtime_and_store):
        runtime, store = runtime_and_store
        for _ in range(3):
            await runtime.process_boundary_event(
                RuntimeEvent(kind="boundary", app_name="Mail", token="x", idle_ms=500)
            )
        for _ in range(5):
            await runtime.process_boundary_event(
                RuntimeEvent(kind="boundary", app_name="Slack", token="y", idle_ms=500)
            )
        runtime._flush_session()
        row = store.get_session(runtime.session_id)
        assert row["dominant_app"] == "Slack"  # 5 > 3


# ---------------------------------------------------------------------------
# CLI session-status command
# ---------------------------------------------------------------------------


class TestSessionStatusCLI:
    def test_session_status_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from cognitiveio.cli import app
        import cognitiveio.cli as cli_module

        runner = CliRunner()
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))

        def _patched_get_store():
            settings = Settings(app_home=tmp_path, apple_fm_enabled=False)
            store = LocalStore(settings.db_path, encryption_mode="off")
            return store, settings

        monkeypatch.setattr(cli_module, "_get_store", _patched_get_store)

        result = runner.invoke(app, ["session-status"])
        assert result.exit_code == 0
        assert "embryonic" in result.output
        assert "No sessions recorded" in result.output

    def test_session_status_with_data(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from cognitiveio.cli import app
        import cognitiveio.cli as cli_module

        runner = CliRunner()
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))

        settings = Settings(app_home=tmp_path, apple_fm_enabled=False)
        store = LocalStore(settings.db_path, encryption_mode="off")
        store.start_session("test_sess_01")
        store.update_session(
            "test_sess_01",
            suggestions_shown=20,
            suggestions_accepted=12,
            dominant_app="Mail",
        )
        store.close()

        def _patched_get_store():
            s = Settings(app_home=tmp_path, apple_fm_enabled=False)
            return LocalStore(s.db_path, encryption_mode="off"), s

        monkeypatch.setattr(cli_module, "_get_store", _patched_get_store)

        result = runner.invoke(app, ["session-status"])
        assert result.exit_code == 0
        assert "mature" in result.output
        assert "Mail" in result.output
