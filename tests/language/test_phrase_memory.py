from pathlib import Path

from cognitiveio.memory.local_store import LocalStore


def test_phrase_pattern_roundtrip(tmp_path: Path):
    store = LocalStore(tmp_path / "phrase.db")
    store.upsert_phrase_pattern("asap", "as soon as possible", profile="email_docs", confidence=0.9)
    cands = store.get_phrase_candidates("asap", profile="email_docs")
    assert cands
    assert cands[0]["after"] == "as soon as possible"
    assert float(cands[0]["confidence"]) >= 0.9
    store.close()


def test_phrase_profile_filtering(tmp_path: Path):
    store = LocalStore(tmp_path / "phrase_profile.db")
    store.upsert_phrase_pattern("fyi", "for your information", profile="email_docs", confidence=0.9)
    # Should not appear in terminal profile.
    cands = store.get_phrase_candidates("fyi", profile="terminal")
    assert cands == []
    store.close()


def test_phrase_list_and_delete(tmp_path: Path):
    store = LocalStore(tmp_path / "phrase_manage.db")
    store.upsert_phrase_pattern(".meW", "Best, Team", profile="email_docs", confidence=0.95)
    store.upsert_phrase_pattern(".meW", "Best, Team", profile="chat", confidence=0.8)

    all_rows = store.list_phrase_patterns(limit=10)
    assert len(all_rows) >= 2

    email_rows = store.list_phrase_patterns(profile="email_docs", limit=10)
    assert email_rows
    assert all(r["profile"] == "email_docs" for r in email_rows)

    removed_scoped = store.delete_phrase_pattern(".meW", profile="chat")
    assert removed_scoped == 1
    removed_all = store.delete_phrase_pattern(".meW")
    assert removed_all >= 1
    store.close()
