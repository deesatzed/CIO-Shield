"""Integration tests for MacRuntimeBridge._shield_paste().

These tests use a FakePasteboard instead of NSPasteboard because:
- NSPasteboard is a macOS Cocoa API requiring Accessibility permissions
- It cannot be used in CI environments or without a running window server
- This is the OS hardware boundary — the ONE justified fake in the shield

The scanning logic in clipboard_shield.py is tested with ZERO fakes in
test_clipboard_shield.py.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class FakePasteboard:
    """Minimal stand-in for NSPasteboard.generalPasteboard()."""

    def __init__(self, initial_text: str = "") -> None:
        self._text: Optional[str] = initial_text or None

    def stringForType_(self, type_str: str) -> Optional[str]:
        return self._text

    def clearContents(self) -> None:
        self._text = None

    def setString_forType_(self, text: str, type_str: str) -> None:
        self._text = text


class FakeStore:
    """Minimal stand-in for LocalStore — records log_privacy_event calls."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def log_privacy_event(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class FakeSettings:
    """Minimal stand-in for Settings — disables enhanced paths for unit tests."""

    vault_enabled: bool = False
    fm_clipboard_shield_enabled: bool = False
    vault_retention_hours: int = 24
    vault_backfill_enabled: bool = False
    backfill_hotkey: str = "ctrl+option+b"


class FakeRuntime:
    """Minimal stand-in for AppRuntime."""

    def __init__(self) -> None:
        self.store = FakeStore()
        self.settings = FakeSettings()


def _make_bridge_stub(pasteboard: Optional[FakePasteboard] = None) -> Any:
    """Build a minimal object that has _shield_paste and required attributes."""
    from cognitiveio.runtime.mac_bridge import MacRuntimeBridge

    # We cannot fully construct MacRuntimeBridge without PyObjC.
    # Instead, bind _shield_paste as an unbound method to a stub object.
    stub = MagicMock(spec=[])
    stub._pasteboard = pasteboard
    stub.runtime = FakeRuntime()
    # Bind the real method
    stub._shield_paste = MacRuntimeBridge._shield_paste.__get__(stub, type(stub))
    return stub


def test_shield_paste_no_pasteboard():
    """When _pasteboard is None, _shield_paste returns immediately (no crash)."""
    bridge = _make_bridge_stub(pasteboard=None)
    bridge._shield_paste("Safari")  # Should not raise


def test_shield_paste_clean_text():
    """When clipboard has clean text, no redaction occurs."""
    pb = FakePasteboard("Hello world, normal text")
    bridge = _make_bridge_stub(pasteboard=pb)
    bridge._shield_paste("Safari")
    # Pasteboard unchanged
    assert pb.stringForType_("public.utf8-plain-text") == "Hello world, normal text"
    # No privacy events logged
    assert len(bridge.runtime.store.events) == 0


def test_shield_paste_with_secret():
    """When clipboard has a secret, it's replaced with redacted version."""
    secret_text = "Here is my key sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef ok"
    pb = FakePasteboard(secret_text)
    bridge = _make_bridge_stub(pasteboard=pb)
    bridge._shield_paste("Mail")
    # Pasteboard should now contain redacted text (not the original)
    current = pb.stringForType_("public.utf8-plain-text")
    assert current is not None
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in current
    assert "Here is my key" in current


def test_shield_paste_logs_privacy_event():
    """Verify privacy ledger entry is created when a secret is redacted."""
    secret_text = "token=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    pb = FakePasteboard(secret_text)
    bridge = _make_bridge_stub(pasteboard=pb)
    bridge._shield_paste("Slack")
    events = bridge.runtime.store.events
    assert len(events) == 1
    evt = events[0]
    assert evt["kind"] == "redaction"
    assert evt["reason"] == "clipboard_paste_redacted"
    assert evt["app_name"] == "Slack"
    assert evt["event_type"] == "clipboard_shield"
    assert evt["meta"]["match_count"] >= 1


def test_shield_paste_restores_clipboard():
    """After a short delay, original clipboard content is restored."""
    secret_text = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    pb = FakePasteboard(secret_text)
    bridge = _make_bridge_stub(pasteboard=pb)
    bridge._shield_paste("Notes")
    # Immediately after, clipboard has redacted version
    immediate = pb.stringForType_("public.utf8-plain-text")
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in (immediate or "")
    # Wait for restore thread (100ms + buffer)
    time.sleep(0.25)
    restored = pb.stringForType_("public.utf8-plain-text")
    assert restored == secret_text


def test_shield_paste_empty_clipboard():
    """When clipboard is empty, _shield_paste returns immediately."""
    pb = FakePasteboard("")
    bridge = _make_bridge_stub(pasteboard=pb)
    bridge._shield_paste("Safari")
    assert len(bridge.runtime.store.events) == 0
