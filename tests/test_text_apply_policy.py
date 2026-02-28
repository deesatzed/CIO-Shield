from types import SimpleNamespace

from cognitiveio.core.undo_stack import UndoRecord
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
