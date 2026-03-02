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
