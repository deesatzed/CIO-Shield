"""Tests for context/app_context.py — the standalone AppContext dataclass."""
from cognitiveio.context.app_context import AppContext


def test_app_context_basic():
    ctx = AppContext(app_name="Mail")
    assert ctx.app_name == "Mail"
    assert ctx.bundle_id is None
    assert ctx.window_title is None


def test_app_context_all_fields():
    ctx = AppContext(app_name="Safari", bundle_id="com.apple.Safari", window_title="My Tab")
    assert ctx.app_name == "Safari"
    assert ctx.bundle_id == "com.apple.Safari"
    assert ctx.window_title == "My Tab"


def test_app_context_frozen():
    ctx = AppContext(app_name="Notes")
    try:
        ctx.app_name = "Other"  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
