from pathlib import Path

from cognitiveio.memory.local_store import LocalStore


def test_concept_lexicon_roundtrip(tmp_path: Path):
    store = LocalStore(tmp_path / "concepts.db")
    store.upsert_concept(
        canonical="Application Programming Interface",
        synonym="api",
        domain="engineering",
        profile="email_docs",
        confidence=0.9,
    )
    cands = store.get_concept_candidates("api", profile="email_docs")
    assert cands
    assert cands[0]["after"] == "Application Programming Interface"
    store.close()


def test_concept_profile_filtering(tmp_path: Path):
    store = LocalStore(tmp_path / "concepts_filter.db")
    store.upsert_concept(
        canonical="Service Level Agreement",
        synonym="sla",
        domain="ops",
        profile="email_docs",
        confidence=0.89,
    )
    cands = store.get_concept_candidates("sla", profile="terminal")
    assert cands == []
    store.close()
