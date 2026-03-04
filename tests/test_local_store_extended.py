"""Phase 1: Deep coverage tests for memory/local_store.py.

All tests use real SQLite via tmp_path — no mocks.
"""
import json
from pathlib import Path

from cognitiveio.memory.local_store import LocalStore


def _store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "test_extended.db")


# ── Error-pattern CRUD ──────────────────────────────────────────────

class TestUpsertPattern:
    def test_first_upsert_creates_embryonic_pattern(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        state = store.get_pattern_state("teh", "the")
        assert state is not None
        assert state["lifecycle_state"] == "embryonic"
        assert state["frequency"] == 1
        assert state["confidence"] == 0.1
        store.close()

    def test_repeated_upsert_increments_frequency(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(5):
            store.upsert_pattern("recieve", "receive")
        state = store.get_pattern_state("recieve", "receive")
        assert state is not None
        assert state["frequency"] == 5
        store.close()

    def test_upsert_increases_confidence(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("wierd", "weird")
        c1 = store.get_pattern_state("wierd", "weird")["confidence"]
        for _ in range(9):
            store.upsert_pattern("wierd", "weird")
        c2 = store.get_pattern_state("wierd", "weird")["confidence"]
        assert c2 > c1
        store.close()

    def test_upsert_case_insensitive(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("Teh", "the")
        store.upsert_pattern("teh", "the")
        state = store.get_pattern_state("teh", "the")
        assert state is not None
        assert state["frequency"] == 2
        store.close()

    def test_different_corrections_are_separate(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.upsert_pattern("teh", "ten")
        c1 = store.get_candidates_for_token("teh")
        afters = {c["after"] for c in c1}
        assert "the" in afters
        assert "ten" in afters
        store.close()


class TestGetCandidatesForToken:
    def test_returns_empty_for_unknown_token(self, tmp_path: Path):
        store = _store(tmp_path)
        result = store.get_candidates_for_token("xyzzyplugh")
        assert result == []
        store.close()

    def test_returns_candidates_sorted_by_confidence(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(10):
            store.upsert_pattern("teh", "the")
        for _ in range(3):
            store.upsert_pattern("teh", "ten")
        candidates = store.get_candidates_for_token("teh")
        assert len(candidates) == 2
        assert candidates[0]["confidence"] >= candidates[1]["confidence"]
        store.close()

    def test_candidate_dict_shape(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        c = store.get_candidates_for_token("teh")
        assert len(c) == 1
        row = c[0]
        assert set(row.keys()) == {"id", "before", "after", "count", "confidence", "age_days"}
        assert row["before"] == "teh"
        assert row["after"] == "the"
        store.close()

    def test_limit_param(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("foo", "bar")
        store.upsert_pattern("foo", "baz")
        store.upsert_pattern("foo", "qux")
        c = store.get_candidates_for_token("foo", limit=2)
        assert len(c) <= 2
        store.close()


class TestGetPatternState:
    def test_returns_none_for_missing(self, tmp_path: Path):
        store = _store(tmp_path)
        assert store.get_pattern_state("nope", "nah") is None
        store.close()

    def test_state_fields(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        state = store.get_pattern_state("teh", "the")
        assert set(state.keys()) == {
            "confidence", "frequency", "rejection_count",
            "success_count", "failure_count", "lifecycle_state", "last_transition",
        }
        store.close()


# ── Feedback & Undo ─────────────────────────────────────────────────

class TestRecordFeedback:
    def test_accepted_increments_success(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.record_feedback("teh", "the", accepted=True)
        state = store.get_pattern_state("teh", "the")
        assert state["success_count"] == 1
        assert state["failure_count"] == 0
        store.close()

    def test_rejected_increments_failure(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.record_feedback("teh", "the", accepted=False)
        state = store.get_pattern_state("teh", "the")
        assert state["failure_count"] == 1
        store.close()

    def test_accepted_raises_confidence(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        c_before = store.get_pattern_state("teh", "the")["confidence"]
        store.record_feedback("teh", "the", accepted=True)
        c_after = store.get_pattern_state("teh", "the")["confidence"]
        assert c_after >= c_before
        store.close()

    def test_rejected_lowers_confidence(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(5):
            store.upsert_pattern("teh", "the")
        c_before = store.get_pattern_state("teh", "the")["confidence"]
        store.record_feedback("teh", "the", accepted=False)
        c_after = store.get_pattern_state("teh", "the")["confidence"]
        assert c_after < c_before
        store.close()

    def test_feedback_on_missing_pattern_is_noop(self, tmp_path: Path):
        store = _store(tmp_path)
        # Should not raise
        store.record_feedback("nonexistent", "nope", accepted=True)
        store.record_feedback("nonexistent", "nope", accepted=False)
        store.close()

    def test_multiple_accepts_transitions_to_viable(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.record_feedback("teh", "the", accepted=True)
        store.record_feedback("teh", "the", accepted=True)
        store.record_feedback("teh", "the", accepted=True)
        state = store.get_pattern_state("teh", "the")
        assert state["lifecycle_state"] in {"viable", "thriving"}
        store.close()

    def test_many_rejects_transitions_to_declining(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(4):
            store.upsert_pattern("teh", "the")
        for _ in range(6):
            store.record_feedback("teh", "the", accepted=False)
        state = store.get_pattern_state("teh", "the")
        assert state["lifecycle_state"] == "declining"
        store.close()


class TestRecordUndoPenalty:
    def test_undo_increases_rejection_by_two(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        before = store.get_pattern_state("teh", "the")["rejection_count"]
        store.record_undo_penalty("teh", "the")
        after = store.get_pattern_state("teh", "the")["rejection_count"]
        assert after == before + 2
        store.close()

    def test_undo_reduces_confidence_by_30pct(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(8):
            store.upsert_pattern("teh", "the")
        c_before = store.get_pattern_state("teh", "the")["confidence"]
        store.record_undo_penalty("teh", "the")
        c_after = store.get_pattern_state("teh", "the")["confidence"]
        expected = max(0.01, c_before * 0.70)
        assert abs(c_after - expected) < 0.01
        store.close()

    def test_undo_on_missing_pattern_is_noop(self, tmp_path: Path):
        store = _store(tmp_path)
        store.record_undo_penalty("nonexistent", "nope")
        store.close()

    def test_undo_increments_failure_count_by_two(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.record_undo_penalty("teh", "the")
        state = store.get_pattern_state("teh", "the")
        assert state["failure_count"] == 2
        store.close()


# ── Aggregates ──────────────────────────────────────────────────────

class TestTopPatterns:
    def test_top_patterns_returns_by_frequency(self, tmp_path: Path):
        store = _store(tmp_path)
        for _ in range(5):
            store.upsert_pattern("teh", "the")
        for _ in range(3):
            store.upsert_pattern("wierd", "weird")
        top = store.top_patterns(limit=2)
        assert len(top) == 2
        assert top[0]["before"] == "teh"
        store.close()

    def test_top_patterns_empty_store(self, tmp_path: Path):
        store = _store(tmp_path)
        assert store.top_patterns() == []
        store.close()

    def test_top_patterns_includes_lifecycle(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        rows = store.top_patterns(limit=1)
        assert rows[0]["lifecycle_state"] == "embryonic"
        assert "success_count" in rows[0]
        assert "failure_count" in rows[0]
        store.close()


# ── Privacy Ledger ──────────────────────────────────────────────────

class TestPrivacyLedger:
    def test_log_and_retrieve_events(self, tmp_path: Path):
        store = _store(tmp_path)
        store.log_privacy_event(kind="blocked", reason="password_field", app_name="Mail")
        events = store.get_privacy_events(limit=10)
        assert len(events) == 1
        assert events[0]["kind"] == "blocked"
        assert events[0]["reason"] == "password_field"
        store.close()

    def test_events_ordered_newest_first(self, tmp_path: Path):
        store = _store(tmp_path)
        store.log_privacy_event(kind="blocked", reason="first")
        store.log_privacy_event(kind="blocked", reason="second")
        events = store.get_privacy_events(limit=10)
        assert events[0]["reason"] == "second"
        assert events[1]["reason"] == "first"
        store.close()

    def test_export_privacy_ledger(self, tmp_path: Path):
        store = _store(tmp_path)
        store.log_privacy_event(kind="blocked", reason="test_reason")
        export_path = tmp_path / "export.json"
        store.export_privacy_ledger(export_path)
        assert export_path.exists()
        data = json.loads(export_path.read_text(encoding="utf-8"))
        assert data["version"] == "1.0"
        assert "events" in data
        assert isinstance(data["events"], list)
        assert len(data["events"]) == 1
        store.close()

    def test_empty_ledger_export(self, tmp_path: Path):
        store = _store(tmp_path)
        export_path = tmp_path / "empty_export.json"
        store.export_privacy_ledger(export_path)
        data = json.loads(export_path.read_text(encoding="utf-8"))
        assert data["events"] == []
        store.close()

    def test_privacy_event_meta(self, tmp_path: Path):
        store = _store(tmp_path)
        store.log_privacy_event(
            kind="stored", reason="stored", app_name="Mail",
            event_type="suggestion_accepted", meta={"candidate_id": "c1"},
        )
        events = store.get_privacy_events(limit=1)
        assert events[0]["meta"]["candidate_id"] == "c1"
        store.close()


# ── Proof Reports ───────────────────────────────────────────────────

class TestProofReports:
    def test_save_and_retrieve_latest(self, tmp_path: Path):
        store = _store(tmp_path)
        report = {"accept_rate": 0.5, "minutes": 10.0}
        store.save_proof_report(report)
        latest = store.latest_proof_report()
        assert latest is not None
        assert latest["accept_rate"] == 0.5
        assert "timestamp" in latest
        store.close()

    def test_latest_returns_none_when_empty(self, tmp_path: Path):
        store = _store(tmp_path)
        assert store.latest_proof_report() is None
        store.close()

    def test_list_proof_reports_order(self, tmp_path: Path):
        store = _store(tmp_path)
        store.save_proof_report({"session": 1})
        store.save_proof_report({"session": 2})
        store.save_proof_report({"session": 3})
        reports = store.list_proof_reports(limit=10)
        assert len(reports) == 3
        assert reports[0]["session"] == 3  # newest first
        assert reports[2]["session"] == 1
        store.close()

    def test_list_proof_reports_limit(self, tmp_path: Path):
        store = _store(tmp_path)
        for i in range(5):
            store.save_proof_report({"idx": i})
        reports = store.list_proof_reports(limit=3)
        assert len(reports) == 3
        store.close()

    def test_list_proof_reports_empty(self, tmp_path: Path):
        store = _store(tmp_path)
        assert store.list_proof_reports() == []
        store.close()


# ── Utilities ───────────────────────────────────────────────────────

class TestHashToken:
    def test_hash_returns_16_hex_chars(self, tmp_path: Path):
        h = LocalStore.hash_token("teh")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_deterministic(self, tmp_path: Path):
        assert LocalStore.hash_token("hello") == LocalStore.hash_token("hello")

    def test_hash_different_for_different_tokens(self, tmp_path: Path):
        assert LocalStore.hash_token("hello") != LocalStore.hash_token("world")


class TestLogSecretAccess:
    def test_log_secret_access(self, tmp_path: Path):
        store = _store(tmp_path)
        store.log_secret_access("MY_SECRET", "env", "resolved")
        cur = store.conn.cursor()
        cur.execute("SELECT * FROM secret_access_events")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["alias"] == "MY_SECRET"
        assert rows[0]["status"] == "resolved"
        store.close()


class TestDeleteAll:
    def test_delete_all_clears_all_tables(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_pattern("teh", "the")
        store.log_privacy_event(kind="blocked", reason="test")
        store.save_proof_report({"test": 1})
        store.log_secret_access("alias", "env", "ok")
        store.register_secret_alias("ALIAS")
        store.upsert_phrase_pattern("hello", "hi")
        store.upsert_concept("receive", "recieve")

        store.delete_all()

        assert store.get_candidates_for_token("teh") == []
        assert store.get_privacy_events() == []
        assert store.latest_proof_report() is None
        assert store.list_secret_aliases() == []
        assert store.list_phrase_patterns() == []
        assert store.get_concept_candidates("recieve") == []
        store.close()


class TestDeriveLifecycleState:
    def test_embryonic(self):
        assert LocalStore._derive_lifecycle_state(
            success_count=0, failure_count=0, confidence=0.1
        ) == "embryonic"

    def test_viable(self):
        assert LocalStore._derive_lifecycle_state(
            success_count=3, failure_count=1, confidence=0.5
        ) == "viable"

    def test_thriving(self):
        assert LocalStore._derive_lifecycle_state(
            success_count=6, failure_count=1, confidence=0.80
        ) == "thriving"

    def test_declining(self):
        assert LocalStore._derive_lifecycle_state(
            success_count=1, failure_count=3, confidence=0.2
        ) == "declining"

    def test_high_failures_prevents_thriving(self):
        assert LocalStore._derive_lifecycle_state(
            success_count=6, failure_count=6, confidence=0.80
        ) != "thriving"


# ── Secret Alias Registry ──────────────────────────────────────────

class TestSecretAliasRegistry:
    def test_register_and_list(self, tmp_path: Path):
        store = _store(tmp_path)
        store.register_secret_alias("MY_KEY", "API key for service")
        aliases = store.list_secret_aliases()
        assert len(aliases) == 1
        assert aliases[0]["alias"] == "MY_KEY"
        assert aliases[0]["description"] == "API key for service"
        assert aliases[0]["usage_count"] == 1
        store.close()

    def test_repeat_register_increments_usage(self, tmp_path: Path):
        store = _store(tmp_path)
        store.register_secret_alias("MY_KEY")
        store.register_secret_alias("MY_KEY")
        aliases = store.list_secret_aliases()
        assert aliases[0]["usage_count"] == 2
        store.close()


# ── Phrase Patterns ─────────────────────────────────────────────────

class TestPhrasePatterns:
    def test_upsert_and_get(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_phrase_pattern(".sig", "Best regards,\nDr. Smith", profile="email_docs")
        candidates = store.get_phrase_candidates(".sig", profile="email_docs")
        assert len(candidates) == 1
        assert candidates[0]["after"] == "Best regards,\nDr. Smith"
        store.close()

    def test_list_and_delete(self, tmp_path: Path):
        store = _store(tmp_path)
        store.upsert_phrase_pattern(".hw", "Hello World", profile="chat")
        assert len(store.list_phrase_patterns(profile="chat")) == 1
        removed = store.delete_phrase_pattern(".hw", profile="chat")
        assert removed == 1
        assert len(store.list_phrase_patterns(profile="chat")) == 0
        store.close()

    def test_delete_nonexistent_returns_zero(self, tmp_path: Path):
        store = _store(tmp_path)
        assert store.delete_phrase_pattern("nope") == 0
        store.close()

    def test_upsert_phrase_pattern_update_path(self, tmp_path: Path):
        """Upserting the same phrase twice hits the UPDATE branch."""
        store = _store(tmp_path)
        store.upsert_phrase_pattern(".sig", "Best regards", profile="email_docs", confidence=0.5)
        store.upsert_phrase_pattern(".sig", "Best regards", profile="email_docs", confidence=0.7)
        candidates = store.get_phrase_candidates(".sig", profile="email_docs")
        assert len(candidates) == 1
        assert float(candidates[0]["confidence"]) >= 0.5
        store.close()


# ── Encryption mode tests ─────────────────────────────────────────

class TestEncryptionModes:
    def test_encryption_off_mode(self, tmp_path: Path):
        """mode=off uses plain sqlite3."""
        store = LocalStore(tmp_path / "off.db", encryption_mode="off")
        store.upsert_pattern("teh", "the")
        assert store.get_candidates_for_token("teh")
        store.close()

    def test_invalid_encryption_mode_falls_to_optional(self, tmp_path: Path):
        """Invalid mode normalizes to 'optional'."""
        store = LocalStore(tmp_path / "invalid.db", encryption_mode="bogus")
        store.upsert_pattern("teh", "the")
        assert store.get_candidates_for_token("teh")
        store.close()

    def test_optional_mode_no_key(self, tmp_path: Path):
        """Optional mode without key and without sqlcipher falls back to plain."""
        store = LocalStore(tmp_path / "optional_nokey.db", encryption_mode="optional")
        store.upsert_pattern("x", "y")
        assert store.get_candidates_for_token("x")
        store.close()


# ── Rejection filter test ──────────────────────────────────────────

class TestRejectionFilter:
    def test_recently_rejected_candidate_skipped(self, tmp_path: Path):
        """Candidates with >=4 rejections in last 300s are filtered out."""
        store = _store(tmp_path)
        for _ in range(5):
            store.upsert_pattern("foo", "bar")
        # Reject 4 times to trigger the filter
        for _ in range(4):
            store.record_feedback("foo", "bar", accepted=False)
        candidates = store.get_candidates_for_token("foo")
        # The candidate should be filtered out (rejected recently)
        assert len(candidates) == 0
        store.close()
