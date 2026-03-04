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


def test_safe_float_valid():
    from cognitiveio.memory.language_assets import _safe_float
    assert _safe_float(0.5, 0.8) == 0.5
    assert _safe_float("0.95", 0.8) == 0.95


def test_safe_float_invalid_returns_default():
    from cognitiveio.memory.language_assets import _safe_float
    assert _safe_float("not_a_number", 0.88) == 0.88
    assert _safe_float(None, 0.7) == 0.7
