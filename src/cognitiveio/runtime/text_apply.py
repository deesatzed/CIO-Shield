from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from cognitiveio.core.undo_stack import UndoRecord
from cognitiveio.security.aliases import contains_secret_alias, extract_secret_aliases
from cognitiveio.security.resolver import SecretResolver


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
        self.resolver = SecretResolver(on_access=self._on_secret_access)
        self.last_error = ""
        self.last_unresolved_aliases: list[str] = []

    def _on_secret_access(self, alias: str, provider: str, status: str) -> None:
        runtime = getattr(self.bridge, "runtime", None)
        store = getattr(runtime, "store", None)
        if store is None:
            return
        try:
            store.log_secret_access(alias, provider, status)
        except Exception:
            return

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
        self.last_error = ""
        self.last_unresolved_aliases = []
        del app_bundle_id
        if not before:
            self.last_error = "No source text to replace."
            return False

        target_after = after
        if contains_secret_alias(target_after):
            runtime = getattr(self.bridge, "runtime", None)
            store = getattr(runtime, "store", None)
            aliases = extract_secret_aliases(target_after)
            if store is not None:
                for alias in aliases:
                    try:
                        store.register_secret_alias(alias)
                    except Exception:
                        pass
            resolved_after, unresolved = self.resolver.resolve_text(target_after)
            if unresolved:
                # Fail closed when a required alias cannot be resolved.
                self.last_unresolved_aliases = list(unresolved)
                self.last_error = (
                    "Missing secret alias: "
                    + ", ".join(unresolved)
                    + ". Set COGNITIVEIO_SECRET_<ALIAS> or configure a vault provider."
                )
                return False
            target_after = resolved_after

        self.bridge.synth_until_ts = time.time() + 0.35
        for _ in range(len(before)):
            self.bridge._post_keycode(51)

        strategy = self._strategy_for_app(app_name)
        if strategy == "pasteboard":
            if self.bridge._paste_text(target_after):
                return True
            ok = self.bridge._post_text(target_after)
            if not ok:
                self.last_error = "Failed to apply replacement text."
            return ok

        if self.bridge._post_text(target_after):
            return True
        ok = self.bridge._paste_text(target_after)
        if not ok:
            self.last_error = "Failed to apply replacement text."
        return ok

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
