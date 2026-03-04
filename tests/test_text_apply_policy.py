from pathlib import Path

from cognitiveio.core.undo_stack import UndoRecord
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.runtime.text_apply import MacTextApplier


class _RunningApp:
    def __init__(self):
        self.activated = False

    def activateWithOptions_(self, _opts):
        self.activated = True


class _RunningRegistry:
    app = _RunningApp()

    @staticmethod
    def runningApplicationsWithBundleIdentifier_(bundle_id):
        if bundle_id == "com.apple.mail":
            return [_RunningRegistry.app]
        return []


class FakeBridge:
    def __init__(self):
        self.actions = []
        self.kCGEventFlagMaskCommand = 1
        self.kCGHIDEventTap = 0
        self.synth_until_ts = 0.0
        self.NSRunningApplication = _RunningRegistry

    def _post_keycode(self, keycode, shift=False):
        self.actions.append(("key", keycode, shift))

    def _post_text(self, text):
        self.actions.append(("text", text))
        return True

    def _paste_text(self, text):
        self.actions.append(("paste", text))
        return True

    def CGEventCreateKeyboardEvent(self, _src, keycode, down):
        return {"keycode": keycode, "down": down}

    def CGEventSetFlags(self, event, flags):
        event["flags"] = flags

    def CGEventPost(self, _tap, event):
        self.actions.append(("post", event["keycode"], event.get("flags", 0), event["down"]))


def _record(bundle: str | None, pid: int | None = None):
    return UndoRecord(
        id="r1",
        ts=0.0,
        app_name="X",
        before="teh ",
        after="the ",
        app_bundle_id=bundle,
        app_pid=pid,
        cursor_pos=4,
        reason_tag="test",
    )


def test_manual_only_policy_uses_manual_replace():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)

    rec = _record("com.microsoft.VSCode", pid=1)
    ok, mode = applier.undo_record(rec, active_app={"name": "Mail", "bundle_id": "com.apple.mail", "pid": 2})

    assert ok is True
    assert mode == "manual_replace"
    assert any(a[0] in {"text", "paste"} for a in bridge.actions)


def test_native_same_process_uses_command_z_active():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)

    rec = _record("com.apple.mail", pid=42)
    ok, mode = applier.undo_record(rec, active_app={"name": "Mail", "bundle_id": "com.apple.mail", "pid": 42})

    assert ok is True
    assert mode == "command_z_active"
    posted = [a for a in bridge.actions if a[0] == "post"]
    assert len(posted) >= 2


def test_native_activation_fallback_uses_command_z_activated():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)

    rec = _record("com.apple.mail", pid=99)
    ok, mode = applier.undo_record(rec, active_app={"name": "Other", "bundle_id": "com.other.app", "pid": 2})

    assert ok is True
    assert mode == "command_z_activated"


def test_apply_replacement_fails_when_secret_alias_unresolved():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(
        before="token ",
        after="{{SECRET:MISSING_ALIAS}} ",
        app_name="Mail",
    )
    assert ok is False
    assert applier.last_unresolved_aliases == ["MISSING_ALIAS"]
    assert "Missing secret alias: MISSING_ALIAS" in applier.last_error


def test_apply_replacement_fails_with_empty_source_text():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(before="", after="value ", app_name="Mail")
    assert ok is False
    assert applier.last_error == "No source text to replace."


def test_apply_replacement_registers_secret_alias(tmp_path: Path, monkeypatch):
    class _Runtime:
        def __init__(self, store):
            self.store = store

    bridge = FakeBridge()
    store = LocalStore(tmp_path / "text_apply_alias.db")
    bridge.runtime = _Runtime(store)
    monkeypatch.setenv("COGNITIVEIO_SECRET_TEST_API_KEY", "sk_live_demo")

    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(
        before="token ",
        after="{{SECRET:TEST_API_KEY}} ",
        app_name="Mail",
    )
    assert ok is True
    aliases = store.list_secret_aliases(limit=5)
    assert aliases
    assert aliases[0]["alias"] == "TEST_API_KEY"
    store.close()


# ── Extended coverage tests ────────────────────────────────────────

def test_strategy_for_paste_preferred_app():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._strategy_for_app("Mail") == "pasteboard"
    assert applier._strategy_for_app("Slack") == "pasteboard"
    assert applier._strategy_for_app("Notes") == "pasteboard"
    assert applier._strategy_for_app("UnknownApp") == "keystroke"


def test_undo_policy_no_bundle_id():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._undo_policy(None) == "native_first"
    assert applier._undo_policy("") == "native_first"


def test_undo_policy_manual_only_bundles():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._undo_policy("com.microsoft.VSCode") == "manual_only"
    assert applier._undo_policy("com.apple.Terminal") == "manual_only"


def test_undo_policy_native_first_bundles():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._undo_policy("com.apple.mail") == "native_first"
    assert applier._undo_policy("com.tinyspeck.slackmacgap") == "native_first"


def test_apply_replacement_pasteboard_path():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(before="teh", after="the", app_name="Mail")
    assert ok is True
    assert any(a[0] == "paste" for a in bridge.actions)


def test_apply_replacement_keystroke_path():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(before="teh", after="the", app_name="UnknownApp")
    assert ok is True
    assert any(a[0] == "text" for a in bridge.actions)


class FailingBridge(FakeBridge):
    def _post_text(self, text):
        return False

    def _paste_text(self, text):
        return False


def test_apply_replacement_pasteboard_fallback_failure():
    bridge = FailingBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(before="teh", after="the", app_name="Mail")
    assert ok is False
    assert "Failed to apply" in applier.last_error


def test_apply_replacement_keystroke_fallback_failure():
    bridge = FailingBridge()
    applier = MacTextApplier(bridge)
    ok = applier.apply_replacement(before="teh", after="the", app_name="UnknownApp")
    assert ok is False
    assert "Failed to apply" in applier.last_error


def test_on_secret_access_no_runtime():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    # Should not raise even without runtime
    applier._on_secret_access("alias", "env", "resolved")


def test_on_secret_access_no_store():
    bridge = FakeBridge()
    bridge.runtime = type("R", (), {"store": None})()
    applier = MacTextApplier(bridge)
    applier._on_secret_access("alias", "env", "resolved")


def test_activate_bundle_no_bundle_id():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._activate_bundle(None) is False
    assert applier._activate_bundle("") is False


def test_activate_bundle_unknown_bundle():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    assert applier._activate_bundle("com.nonexistent.app") is False


def test_undo_record_native_same_bundle():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    rec = _record("com.apple.mail", pid=None)
    ok, mode = applier.undo_record(
        rec,
        active_app={"name": "Mail", "bundle_id": "com.apple.mail", "pid": None},
    )
    assert ok is True
    assert mode == "command_z_active"


def test_undo_record_native_fallback_to_manual():
    bridge = FakeBridge()
    applier = MacTextApplier(bridge)
    rec = _record("com.nonexistent.app", pid=100)
    ok, mode = applier.undo_record(
        rec,
        active_app={"name": "Other", "bundle_id": "com.other", "pid": 200},
    )
    assert ok is True
    assert mode == "manual_replace"
