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
