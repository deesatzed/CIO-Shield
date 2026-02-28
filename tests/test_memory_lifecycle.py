from pathlib import Path
from datetime import datetime, timedelta, UTC

from cognitiveio.memory.local_store import LocalStore


def _store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "cio_lifecycle.db")


def test_pattern_lifecycle_transitions(tmp_path: Path):
    store = _store(tmp_path)

    # Seed confidence/frequency so thriving is reachable after successes.
    for _ in range(8):
        store.upsert_pattern("teh", "the")

    state0 = store.get_pattern_state("teh", "the")
    assert state0 is not None
    assert state0["lifecycle_state"] == "embryonic"

    store.record_feedback("teh", "the", accepted=True)
    store.record_feedback("teh", "the", accepted=True)
    state1 = store.get_pattern_state("teh", "the")
    assert state1 is not None
    assert state1["lifecycle_state"] in {"viable", "thriving"}

    for _ in range(4):
        store.record_feedback("teh", "the", accepted=True)
    state2 = store.get_pattern_state("teh", "the")
    assert state2 is not None
    assert state2["lifecycle_state"] == "thriving"

    for _ in range(7):
        store.record_feedback("teh", "the", accepted=False)
    state3 = store.get_pattern_state("teh", "the")
    assert state3 is not None
    assert state3["lifecycle_state"] == "declining"

    store.close()


def test_top_patterns_include_lifecycle_fields(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_pattern("wierd", "weird")
    store.record_feedback("wierd", "weird", accepted=True)
    rows = store.top_patterns(limit=5)
    assert rows
    row = rows[0]
    assert "lifecycle_state" in row
    assert "success_count" in row
    assert "failure_count" in row
    store.close()


def test_stale_pattern_decay_reduces_candidate_confidence(tmp_path: Path):
    store = _store(tmp_path)
    for _ in range(8):
        store.upsert_pattern("recieve", "receive")

    fresh = store.get_candidates_for_token("recieve")
    assert fresh
    fresh_conf = float(fresh[0]["confidence"])

    old_ts = (datetime.now(UTC) - timedelta(days=180)).timestamp()
    store.conn.execute(
        "UPDATE error_patterns SET last_seen=? WHERE lower(error_pattern)=lower(?) AND lower(intended_pattern)=lower(?)",
        (old_ts, "recieve", "receive"),
    )
    store.conn.commit()

    stale = store.get_candidates_for_token("recieve")
    assert stale
    stale_conf = float(stale[0]["confidence"])
    assert stale_conf < fresh_conf
    assert float(stale[0]["age_days"]) > 100.0
    store.close()
