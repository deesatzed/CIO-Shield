"""Tests for retention pruning logic."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cognitiveio.memory.local_store import LocalStore


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / "test.db", encryption_mode="off")
    yield s
    s.close()


class TestRetentionPrune:
    def test_prune_zero_days_noop(self, store):
        store.log_privacy_event(kind="blocked", reason="test")
        assert store.prune_by_retention(0) == 0

    def test_prune_negative_days_noop(self, store):
        store.log_privacy_event(kind="blocked", reason="test")
        assert store.prune_by_retention(-5) == 0

    def test_prune_removes_old_events(self, store):
        # Insert events with old timestamps directly.
        cur = store.conn.cursor()
        old_ts = (datetime.now() - timedelta(days=200)).timestamp()
        cur.execute(
            "INSERT INTO privacy_events (ts, kind, reason) VALUES (?, ?, ?)",
            (old_ts, "blocked", "old_event"),
        )
        cur.execute(
            "INSERT INTO proof_reports (ts, report_json) VALUES (?, ?)",
            (old_ts, '{"test": true}'),
        )
        cur.execute(
            "INSERT INTO secret_access_events (ts, alias, provider, status) VALUES (?, ?, ?, ?)",
            (old_ts, "TEST_KEY", "env", "resolved"),
        )
        store.conn.commit()

        # Also add a recent event.
        store.log_privacy_event(kind="stored", reason="recent")

        pruned = store.prune_by_retention(90)
        assert pruned == 3  # 1 privacy_event + 1 proof_report + 1 secret_access_event

        # Recent event should remain.
        events = store.get_privacy_events(limit=100)
        assert len(events) >= 1
        assert any(e["reason"] == "recent" for e in events)

    def test_prune_preserves_recent(self, store):
        store.log_privacy_event(kind="blocked", reason="recent_1")
        store.log_privacy_event(kind="blocked", reason="recent_2")
        pruned = store.prune_by_retention(1)
        assert pruned == 0

    def test_prune_returns_count(self, store):
        cur = store.conn.cursor()
        old_ts = (datetime.now() - timedelta(days=400)).timestamp()
        for i in range(10):
            cur.execute(
                "INSERT INTO privacy_events (ts, kind, reason) VALUES (?, ?, ?)",
                (old_ts, "blocked", f"old_{i}"),
            )
        store.conn.commit()
        pruned = store.prune_by_retention(30)
        assert pruned == 10
