from cognitiveio.experiments.ab_testing import ABConfig, assign_variant, default_user_key


def test_assign_variant_persists(tmp_path):
    cfg = ABConfig(state_path=tmp_path / "ab_variant.txt")
    first = assign_variant("alice@example", cfg)
    second = assign_variant("bob@example", cfg)
    assert first in {"A", "B"}
    assert second == first


def test_default_user_key_is_non_empty():
    key = default_user_key()
    assert key
    assert "@" in key
