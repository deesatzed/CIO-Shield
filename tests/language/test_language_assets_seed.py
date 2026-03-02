from pathlib import Path

from cognitiveio.memory.language_assets import seed_common_language_assets
from cognitiveio.memory.local_store import LocalStore


def test_seed_common_language_assets(tmp_path: Path):
    store = LocalStore(tmp_path / "seed_language.db")
    counts = seed_common_language_assets(store)
    assert counts["phrases"] > 0
    assert counts["concepts"] > 0

    phrase = store.get_phrase_candidates("asap", profile="email_docs")
    concept = store.get_concept_candidates("api", profile="email_docs")
    assert phrase
    assert concept
    store.close()
