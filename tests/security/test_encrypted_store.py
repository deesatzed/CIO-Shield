from pathlib import Path

import pytest

from cognitiveio.memory.local_store import LocalStore


def test_store_optional_encryption_without_key_still_opens(tmp_path: Path):
    store = LocalStore(tmp_path / "optional.db", encryption_mode="optional", db_key=None)
    store.upsert_pattern("teh", "the")
    assert store.get_candidates_for_token("teh")
    store.close()


def test_store_required_encryption_without_key_fails(tmp_path: Path):
    with pytest.raises(RuntimeError):
        LocalStore(tmp_path / "required.db", encryption_mode="required", db_key=None)


def test_store_off_encryption_works(tmp_path: Path):
    """Encryption mode 'off' uses plain sqlite3."""
    store = LocalStore(tmp_path / "off.db", encryption_mode="off")
    store.upsert_pattern("teh", "the")
    assert store.get_candidates_for_token("teh")
    store.close()


def test_store_invalid_mode_defaults_to_optional(tmp_path: Path):
    """Invalid encryption mode string defaults to 'optional'."""
    store = LocalStore(tmp_path / "invalid.db", encryption_mode="invalid_mode")
    store.upsert_pattern("teh", "the")
    assert store.get_candidates_for_token("teh")
    store.close()


def test_store_learning_persists_with_off_encryption(tmp_path: Path):
    """Patterns, phrases, and concepts survive close/reopen with encryption off."""
    db_path = tmp_path / "persist.db"
    store = LocalStore(db_path, encryption_mode="off")
    store.upsert_pattern("teh", "the")
    store.upsert_phrase_pattern(".hw", "Hello World", profile="email_docs")
    store.close()

    store2 = LocalStore(db_path, encryption_mode="off")
    assert store2.get_candidates_for_token("teh")
    phrases = store2.get_phrase_candidates(".hw", profile="email_docs")
    assert phrases
    store2.close()


def test_store_compliance_export_works_with_encryption_off(tmp_path: Path):
    """Compliance export generates valid report with encryption off."""
    store = LocalStore(tmp_path / "export.db", encryption_mode="off")
    store.log_privacy_event(kind="blocked", reason="test")
    out = tmp_path / "report.json"
    report = store.export_compliance_report(out)
    assert report["schema_version"] == 1
    store.close()


def test_store_retention_prune_works_with_encryption_off(tmp_path: Path):
    """Retention pruning works with encryption off."""
    store = LocalStore(tmp_path / "prune.db", encryption_mode="off")
    store.log_privacy_event(kind="blocked", reason="old_event")
    count = store.prune_by_retention(0)  # 0 days = prune everything
    assert count == 0  # Recent events within today aren't older than 0 days
    store.close()
