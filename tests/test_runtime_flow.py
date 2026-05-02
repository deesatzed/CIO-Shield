import asyncio
from pathlib import Path

from cognitiveio.ai.fm_arbiter import validate_candidate_choice
from cognitiveio.config import Settings
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.policy.risk_scoring import RiskFlags
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent


def _runtime(tmp_path: Path, **settings_kwargs) -> AppRuntime:
    settings = Settings(app_home=tmp_path, **settings_kwargs)
    store = LocalStore(settings.db_path)
    for _ in range(12):
        store.upsert_pattern("teh", "the")
    return AppRuntime(settings=settings, store=store)


def test_runtime_protected_mode_blocks(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary",
                app_name="Mail",
                token="teh",
                boundary=" ",
                idle_ms=400,
                flags=RiskFlags(password_field=True),
            )
        )
    )
    assert out.action == "do_nothing"
    assert out.protected_mode is True


def test_runtime_suggest_accept_and_undo(tmp_path: Path):
    runtime = _runtime(tmp_path)

    out1 = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out1.action == "suggest"

    out2 = asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
    assert out2.action == "accept"

    out3 = asyncio.run(runtime.process_event(RuntimeEvent(kind="undo")))
    assert out3.action == "undo"


def test_runtime_undo_penalty_reduces_candidate_confidence(tmp_path: Path):
    runtime = _runtime(tmp_path, suggestion_min_confidence=0.30)
    baseline_candidates = runtime.store.get_candidates_for_token("teh")
    assert baseline_candidates
    baseline = baseline_candidates[0]["confidence"]

    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="undo")))

    lowered_candidates = runtime.store.get_candidates_for_token("teh")
    assert lowered_candidates
    lowered = lowered_candidates[0]["confidence"]
    assert lowered < baseline


def test_runtime_tracks_app_metadata_on_undo_record(tmp_path: Path):
    runtime = _runtime(tmp_path)
    asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary",
                app_name="Mail",
                app_bundle_id="com.apple.mail",
                app_pid=123,
                token="teh",
                boundary=" ",
                idle_ms=400,
            )
        )
    )
    asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
    rec = runtime.undo_stack.peek()
    assert rec is not None
    assert rec.app_name == "Mail"
    assert rec.app_bundle_id == "com.apple.mail"
    assert rec.app_pid == 123


def test_runtime_dismiss_feedback_reduces_repeat(tmp_path: Path):
    runtime = _runtime(tmp_path)

    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))

    # After repeated dismissals the runtime enters cooldown and stops suggesting.
    blocked = asyncio.run(
        runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400))
    )
    assert "cooldown" in blocked.message.lower() or blocked.action == "do_nothing"


def test_runtime_detector_uncertain_blocks_when_configured(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary",
                app_name="Mail",
                token="teh",
                boundary=" ",
                idle_ms=400,
                flags=RiskFlags(detector_uncertain=True),
            )
        )
    )
    assert out.action == "do_nothing"
    assert out.protected_mode is True


def test_runtime_trust_circuit_breaker_blocks_after_negative_spike(tmp_path: Path):
    runtime = _runtime(
        tmp_path,
        suggestion_min_confidence=0.30,
        trust_circuit_negative_events=2,
        trust_circuit_window_seconds=300,
        trust_circuit_cooldown_seconds=120,
    )

    # Negative signal 1: undo after a real accepted suggestion.
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="undo")))

    # Negative signal 2: dismissal of a new suggestion.
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))

    blocked = asyncio.run(
        runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400))
    )
    assert blocked.action == "do_nothing"
    assert "trust cooldown" in blocked.message.lower()
    assert runtime.trust_cooldown_remaining_seconds() > 0
    snapshot = runtime.last_decision_snapshot()
    assert snapshot.get("reason_tag") == "trust_circuit_breaker"
    assert int(snapshot.get("trust_cooldown_remaining_seconds", 0)) > 0


def test_runtime_last_decision_snapshot_persists_to_disk(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400))
    )
    assert out.action in {"suggest", "do_nothing"}

    snapshot = runtime.last_decision_snapshot()
    assert snapshot.get("token") == "teh"
    assert "reason_tag" in snapshot
    assert runtime.settings.report_dir.joinpath("latest_decision.json").exists()

    runtime._last_decision = {}
    loaded = runtime.last_decision_snapshot()
    assert loaded.get("token") == "teh"


def test_runtime_candidate_conflict_is_logged_as_blocked(tmp_path: Path):
    runtime = _runtime(
        tmp_path,
        apple_fm_enabled=False,
        suggestion_min_confidence=0.8,
        candidate_conflict_max_gap=0.25,
    )
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")
    runtime.store.upsert_pattern("teh", "ten")

    out = asyncio.run(
        runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400))
    )
    assert out.action == "do_nothing"
    assert "candidate_conflict" in out.message

    events = runtime.store.get_privacy_events(limit=20)
    reasons = [str(e.get("reason")) for e in events if e.get("kind") == "blocked"]
    assert "candidate_conflict" in reasons


def test_arbiter_candidate_validator():
    assert validate_candidate_choice(None, ["a"])
    assert validate_candidate_choice("a", ["a", "b"])
    assert not validate_candidate_choice("x", ["a", "b"])


# ── Phase 6: Runtime edge cases ─────────────────────────────────────

def test_panic_toggle_pause_and_resume(tmp_path: Path):
    runtime = _runtime(tmp_path)
    assert runtime.paused is False

    out1 = asyncio.run(runtime.process_event(RuntimeEvent(kind="panic")))
    assert out1.action == "do_nothing"
    assert runtime.paused is True
    assert "Paused" in out1.message

    out2 = asyncio.run(runtime.process_event(RuntimeEvent(kind="panic")))
    assert out2.action == "do_nothing"
    assert runtime.paused is False
    assert "Resumed" in out2.message


def test_paused_blocks_boundary_event(tmp_path: Path):
    runtime = _runtime(tmp_path)
    asyncio.run(runtime.process_event(RuntimeEvent(kind="panic")))  # pause
    assert runtime.paused is True

    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out.action == "do_nothing"
    assert "Paused" in out.message or "ignored" in out.message.lower()


def test_accept_with_no_pending(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
    assert out.action == "do_nothing"
    assert "No suggestion" in out.message


def test_dismiss_with_no_pending(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))
    assert out.action == "do_nothing"
    assert "No suggestion" in out.message


def test_undo_with_no_pending(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="undo")))
    assert out.action == "do_nothing"
    assert "Nothing to undo" in out.message


def test_unknown_event_kind(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="teleport")))
    assert out.action == "do_nothing"
    assert "Unknown event kind" in out.message


def test_idle_threshold_not_met(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=50)
        )
    )
    assert out.action == "do_nothing"
    assert "Idle threshold" in out.message or "idle" in out.message.lower()


def test_non_boundary_character_rejected(tmp_path: Path):
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary="a", idle_ms=400)
        )
    )
    assert out.action == "do_nothing"
    assert "boundary" in out.message.lower() or "No boundary" in out.message


def test_build_report_returns_proof_report(tmp_path: Path):
    from cognitiveio.evidence.report_generator import ProofReport
    runtime = _runtime(tmp_path)
    asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    report = runtime.build_report()
    assert isinstance(report, ProofReport)
    assert report.suggestion_shown >= 0


# ── Extended runtime coverage ──────────────────────────────────────

def test_merge_candidates_dedup():
    """_merge_candidates merges duplicate (before, after) keeping higher confidence."""
    from cognitiveio.runtime.app_runtime import AppRuntime
    group1 = [
        {"id": "c1", "before": "teh", "after": "the", "count": 5, "confidence": 0.8},
    ]
    group2 = [
        {"id": "c2", "before": "teh", "after": "the", "count": 10, "confidence": 0.95},
    ]
    merged = AppRuntime._merge_candidates(group1, group2)
    assert len(merged) == 1
    assert float(merged[0]["confidence"]) == 0.95
    assert int(merged[0]["count"]) == 10


def test_merge_candidates_distinct():
    """_merge_candidates keeps distinct replacements separate."""
    from cognitiveio.runtime.app_runtime import AppRuntime
    group1 = [
        {"id": "c1", "before": "teh", "after": "the", "count": 5, "confidence": 0.8},
    ]
    group2 = [
        {"id": "c2", "before": "teh", "after": "ten", "count": 3, "confidence": 0.7},
    ]
    merged = AppRuntime._merge_candidates(group1, group2)
    assert len(merged) == 2


def test_is_boundary_chars():
    from cognitiveio.runtime.app_runtime import AppRuntime
    assert AppRuntime._is_boundary(" ") is True
    assert AppRuntime._is_boundary(".") is True
    assert AppRuntime._is_boundary("!") is True
    assert AppRuntime._is_boundary("a") is False
    assert AppRuntime._is_boundary("\n") is True


def test_strip_shared_boundary():
    from cognitiveio.runtime.app_runtime import AppRuntime
    # Both end with boundary char -> stripped
    b, a = AppRuntime._strip_shared_boundary("teh ", "the ")
    assert b == "teh"
    assert a == "the"

    # Different endings -> rstrip
    b2, a2 = AppRuntime._strip_shared_boundary("teh", "the")
    assert b2 == "teh"
    assert a2 == "the"


def test_no_local_candidates_path(tmp_path: Path):
    """When token has no candidates, runtime returns 'No local candidates'."""
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="zzzzz_no_match", boundary=" ", idle_ms=400)
        )
    )
    assert out.action == "do_nothing"
    assert "No local candidates" in out.message


def test_last_decision_snapshot_empty_on_fresh_runtime(tmp_path: Path):
    runtime = _runtime(tmp_path)
    snapshot = runtime.last_decision_snapshot()
    assert snapshot == {} or isinstance(snapshot, dict)


def test_recent_suggestions_cleanup(tmp_path: Path):
    """_recent_suggestions removes entries older than 60s."""
    import time
    runtime = _runtime(tmp_path)
    now = time.time()
    # Add some old timestamps
    runtime._suggestion_ts.append(now - 120)
    runtime._suggestion_ts.append(now - 90)
    runtime._suggestion_ts.append(now - 10)
    count = runtime._recent_suggestions(now)
    assert count == 1  # Only the one from 10s ago


def test_negative_signal_old_entries_cleaned(tmp_path: Path):
    """Old negative event timestamps are cleaned when outside the window."""
    import time
    runtime = _runtime(
        tmp_path,
        trust_circuit_window_seconds=60,
        trust_circuit_negative_events=100,
    )
    now = time.time()
    # Add entries older than window
    runtime._negative_event_ts.append(now - 200)
    runtime._negative_event_ts.append(now - 150)
    runtime._negative_event_ts.append(now - 5)
    runtime._record_negative_signal(now_ts=now)
    # Old entries should be cleaned, only recent ones remain
    assert len(runtime._negative_event_ts) == 2  # now-5 and now


def test_record_last_decision_write_exception(tmp_path: Path):
    """_record_last_decision handles write exceptions gracefully."""
    runtime = _runtime(tmp_path)
    # Point decision path to a read-only directory
    runtime._last_decision_path = tmp_path / "nonexistent_dir" / "impossible" / "file.json"
    # Should not raise
    runtime._record_last_decision(
        action="test",
        reason_tag="test_reason",
        app_name="Mail",
        profile="email_docs",
        token="teh",
        idle_ms=400,
        typing_fast=False,
    )


def test_last_decision_snapshot_fallback_exception(tmp_path: Path):
    """last_decision_snapshot returns {} when file is corrupt."""
    runtime = _runtime(tmp_path)
    runtime._last_decision = {}
    runtime._last_decision_path.parent.mkdir(parents=True, exist_ok=True)
    runtime._last_decision_path.write_text("NOT JSON {{", encoding="utf-8")
    snapshot = runtime.last_decision_snapshot()
    assert snapshot == {}


def test_cooldown_path(tmp_path: Path):
    """Dismissal streak triggers cooldown_until_ts."""
    runtime = _runtime(
        tmp_path,
        suggestion_min_confidence=0.30,
        dismissals_before_cooldown=2,
        apple_fm_enabled=False,
        # Set trust circuit high so it doesn't interfere
        trust_circuit_negative_events=100,
        trust_circuit_window_seconds=300,
        trust_circuit_cooldown_seconds=0,
    )

    # Suggest -> dismiss x2 -> cooldown
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)))
    asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))

    assert runtime._cooldown_until_ts > 0


def test_no_replacement_selected_path(tmp_path: Path, monkeypatch):
    """When decide() returns suggest but with None replacement, runtime returns no_replacement_selected."""
    from cognitiveio.core.decision_engine import Decision
    import cognitiveio.core.decision_engine as de_mod

    runtime = _runtime(tmp_path, apple_fm_enabled=False)

    async def _patched_decide(*args, **kwargs):
        # Return "suggest" with no replacement or candidate_id
        return Decision("suggest", None, None, 0.8, "patched_no_replacement")

    monkeypatch.setattr(de_mod, "_decide_inner", _patched_decide)

    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out.action == "do_nothing"
    assert "No replacement selected" in out.message


def test_adaptive_idle_blocks_fast_typist(tmp_path: Path):
    """Fast typists get a higher effective idle threshold (1.5x by default)."""
    runtime = _runtime(tmp_path, idle_pause_ms=300, adaptive_idle_enabled=True)
    # 350ms idle with typing_fast=True -> effective threshold is 300*1.5=450ms -> blocked
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary", app_name="Mail", token="teh", boundary=" ",
                idle_ms=350, typing_fast=True,
            )
        )
    )
    assert out.action == "do_nothing"
    assert "idle" in out.message.lower() or "Idle threshold" in out.message


def test_adaptive_idle_allows_slow_typist(tmp_path: Path):
    """Slow typists use the base idle threshold — 350ms > 300ms should pass."""
    runtime = _runtime(tmp_path, idle_pause_ms=300, adaptive_idle_enabled=True)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary", app_name="Mail", token="teh", boundary=" ",
                idle_ms=350, typing_fast=False,
            )
        )
    )
    assert out.action == "suggest"


def test_adaptive_idle_disabled_uses_base(tmp_path: Path):
    """When adaptive_idle_enabled=False, fast typists use the base threshold for idle check.

    Note: typing_fast also triggers a separate block in the decision engine,
    so we test with typing_fast=False to isolate the idle threshold behavior.
    """
    runtime = _runtime(tmp_path, idle_pause_ms=300, adaptive_idle_enabled=False)
    # 350ms > 300ms base and typing_fast=False -> passes idle check
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary", app_name="Mail", token="teh", boundary=" ",
                idle_ms=350, typing_fast=False,
            )
        )
    )
    assert out.action == "suggest"

    # Now verify that with adaptive enabled and typing_fast=True,
    # 350ms < 450ms (300*1.5), so idle check blocks it
    runtime2 = _runtime(tmp_path, idle_pause_ms=300, adaptive_idle_enabled=True)
    out2 = asyncio.run(
        runtime2.process_event(
            RuntimeEvent(
                kind="boundary", app_name="Mail", token="teh", boundary=" ",
                idle_ms=350, typing_fast=True,
            )
        )
    )
    assert out2.action == "do_nothing"


def test_status_hint_paused(tmp_path: Path):
    """Paused state should produce a 'Paused' status hint."""
    runtime = _runtime(tmp_path)
    asyncio.run(runtime.process_event(RuntimeEvent(kind="panic")))  # pause
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out.status_hint == "Paused"


def test_status_hint_no_match(tmp_path: Path):
    """No local candidates should produce 'No match' status hint."""
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="zzzzz_none", boundary=" ", idle_ms=400)
        )
    )
    assert out.status_hint == "No match"


def test_status_hint_protected_field(tmp_path: Path):
    """Password field should produce 'Protected field' status hint."""
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(
                kind="boundary", app_name="Mail", token="teh", boundary=" ",
                idle_ms=400, flags=RiskFlags(password_field=True),
            )
        )
    )
    assert out.status_hint == "Protected field"


def test_status_hint_empty_on_suggest(tmp_path: Path):
    """Suggest action should have no status hint."""
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out.action == "suggest"
    assert out.status_hint == ""


def test_status_hint_code_profile(tmp_path: Path):
    """Code editor apps should produce 'Code/terminal' status hint."""
    runtime = _runtime(tmp_path)
    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Visual Studio Code", token="teh", boundary=" ", idle_ms=400)
        )
    )
    assert out.status_hint == "Code/terminal"


def test_auto_apply_path(tmp_path: Path, monkeypatch):
    """When decide() returns auto_apply with valid replacement, runtime auto-applies."""
    from cognitiveio.core.decision_engine import Decision
    import cognitiveio.core.decision_engine as de_mod

    runtime = _runtime(tmp_path, apple_fm_enabled=False, suggest_only=False, auto_apply_enabled=True)

    async def _patched_decide(*args, **kwargs):
        return Decision("auto_apply", "the", "c1", 0.99, "soft_auto")

    monkeypatch.setattr(de_mod, "_decide_inner", _patched_decide)

    out = asyncio.run(
        runtime.process_event(
            RuntimeEvent(kind="boundary", app_name="Mail", token="teh", boundary=" ", idle_ms=400)
        )
    )
    # auto_apply calls accept_pending internally
    assert out.action == "accept"
    snapshot = runtime.last_decision_snapshot()
    assert snapshot.get("reason_tag") == "soft_auto"
