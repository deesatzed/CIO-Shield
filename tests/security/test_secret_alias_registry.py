from pathlib import Path

from cognitiveio.memory.local_store import LocalStore


def test_secret_alias_registry_tracks_usage(tmp_path: Path):
    store = LocalStore(tmp_path / "aliases.db")
    store.register_secret_alias("STRIPE_API_KEY", description="Stripe key")
    store.register_secret_alias("STRIPE_API_KEY")
    rows = store.list_secret_aliases(limit=10)
    assert rows
    assert rows[0]["alias"] == "STRIPE_API_KEY"
    assert rows[0]["usage_count"] >= 2
    assert rows[0]["description"] == "Stripe key"
    store.close()
