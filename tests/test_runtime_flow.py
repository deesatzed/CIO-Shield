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
    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))

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
