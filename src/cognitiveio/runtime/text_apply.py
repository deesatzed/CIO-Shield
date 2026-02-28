from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from cognitiveio.core.undo_stack import UndoRecord


PASTE_PREFERRED_APPS = {
    "Mail",
    "Microsoft Outlook",
    "Slack",
    "Messages",
    "Discord",
    "Notes",
}

# manual_only: prefer deterministic replace for undo/apply.
# native_first: prefer Command+Z undo in original app context.
UNDO_POLICY_BY_BUNDLE = {
    "com.apple.mail": "native_first",
    "com.tinyspeck.slackmacgap": "native_first",
    "com.apple.MobileSMS": "native_first",
    "com.apple.Notes": "native_first",
    "com.microsoft.VSCode": "manual_only",
    "com.jetbrains.pycharm": "manual_only",
    "com.apple.Terminal": "manual_only",
    "com.googlecode.iterm2": "manual_only",
}


class MacTextApplier:
    """App-aware text apply/undo adapter for macOS key event flows."""

    def __init__(self, bridge: Any):
        self.bridge = bridge

    def _strategy_for_app(self, app_name: str) -> str:
        if app_name in PASTE_PREFERRED_APPS:
            return "pasteboard"
        return "keystroke"

    def _undo_policy(self, bundle_id: Optional[str]) -> str:
        if not bundle_id:
            return "native_first"
        return UNDO_POLICY_BY_BUNDLE.get(bundle_id, "native_first")

    def apply_replacement(
        self,
        before: str,
        after: str,
        app_name: str,
        app_bundle_id: Optional[str] = None,
    ) -> bool:
        del app_bundle_id
        if not before:
            return False

        self.bridge.synth_until_ts = time.time() + 0.35
        for _ in range(len(before)):
            self.bridge._post_keycode(51)

        strategy = self._strategy_for_app(app_name)
        if strategy == "pasteboard":
            if self.bridge._paste_text(after):
                return True
            return self.bridge._post_text(after)

        if self.bridge._post_text(after):
            return True
        return self.bridge._paste_text(after)

    def _activate_bundle(self, bundle_id: Optional[str]) -> bool:
        if not bundle_id:
            return False
        try:
            running = self.bridge.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
            if not running:
                return False
            app = running[0]
            app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
            time.sleep(0.06)
            return True
        except Exception:
            return False

    def _post_command_z(self) -> None:
        down = self.bridge.CGEventCreateKeyboardEvent(None, 6, True)  # z
        up = self.bridge.CGEventCreateKeyboardEvent(None, 6, False)
        self.bridge.CGEventSetFlags(down, self.bridge.kCGEventFlagMaskCommand)
        self.bridge.CGEventSetFlags(up, self.bridge.kCGEventFlagMaskCommand)
        self.bridge.CGEventPost(self.bridge.kCGHIDEventTap, down)
        self.bridge.CGEventPost(self.bridge.kCGHIDEventTap, up)

    def _native_undo(self) -> None:
        self.bridge.synth_until_ts = time.time() + 0.25
        self._post_command_z()

    def undo_record(self, rec: UndoRecord, active_app: Dict[str, Any]) -> Tuple[bool, str]:
        active_bundle = active_app.get("bundle_id")
        active_pid = active_app.get("pid")

        policy = self._undo_policy(rec.app_bundle_id)

        if policy == "manual_only":
            ok = self.apply_replacement(
                before=rec.after,
                after=rec.before,
                app_name=active_app.get("name", ""),
                app_bundle_id=active_bundle,
            )
            return ok, "manual_replace"

        # native_first path
        same_process = rec.app_pid is not None and active_pid == rec.app_pid
        same_bundle = rec.app_bundle_id and active_bundle == rec.app_bundle_id

        if same_process or same_bundle:
            self._native_undo()
            return True, "command_z_active"

        if self._activate_bundle(rec.app_bundle_id):
            self._native_undo()
            return True, "command_z_activated"

        ok = self.apply_replacement(
            before=rec.after,
            after=rec.before,
            app_name=active_app.get("name", ""),
            app_bundle_id=active_bundle,
        )
        return ok, "manual_replace"
