from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from cognitiveio.policy.risk_scoring import RiskFlags
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent
from cognitiveio.runtime.protected_context import ProtectedContextDetector
from cognitiveio.runtime.suggestion_presenter import create_suggestion_presenter
from cognitiveio.runtime.text_apply import MacTextApplier


def mac_runtime_available() -> bool:
    try:
        from Cocoa import NSEvent, NSWorkspace  # noqa: F401
        from Quartz import CGEventTapCreate  # noqa: F401
        return True
    except Exception:
        return False


SPECIAL_KEYS = {
    51: "delete",
    53: "escape",
    36: "return",
    48: "tab",
    49: "space",
}

CHAR_TO_KEYCODE = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "\n": 36,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "\t": 48,
    " ": 49,
    "`": 50,
}

SHIFT_CHAR_BASE = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
}

HOTKEY_MOD_ALIAS = {
    "ctrl": "control",
    "control": "control",
    "opt": "option",
    "option": "option",
    "alt": "option",
    "shift": "shift",
    "cmd": "command",
    "command": "command",
}

HOTKEY_KEY_ALIAS = {
    "esc": "escape",
    "escape": "escape",
    "tab": "tab",
    "enter": "return",
    "return": "return",
    "space": "space",
}

KEY_NAME_TO_KEYCODE = {name: keycode for keycode, name in SPECIAL_KEYS.items()}


def parse_hotkey_spec(spec: str) -> Optional[Tuple[int, set[str]]]:
    raw = spec.strip().lower()
    if not raw:
        return None

    parts = [p.strip() for p in raw.split("+") if p.strip()]
    if not parts:
        return None

    mods: set[str] = set()
    key_name: Optional[str] = None
    for part in parts:
        normalized_mod = HOTKEY_MOD_ALIAS.get(part)
        if normalized_mod:
            mods.add(normalized_mod)
            continue

        if key_name is not None:
            return None
        key_name = HOTKEY_KEY_ALIAS.get(part, part)

    if key_name is None:
        return None

    if key_name in KEY_NAME_TO_KEYCODE:
        return KEY_NAME_TO_KEYCODE[key_name], mods

    if len(key_name) == 1 and key_name in CHAR_TO_KEYCODE:
        return CHAR_TO_KEYCODE[key_name], mods

    return None


class MacRuntimeBridge:
    """pyobjc-based system keystroke bridge that feeds AppRuntime."""

    def __init__(self, runtime: AppRuntime):
        if not mac_runtime_available():
            raise RuntimeError("PyObjC runtime unavailable")

        from Cocoa import NSEvent, NSRunningApplication, NSWorkspace
        from Quartz import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CFRunLoopRun,
            CGEventCreateKeyboardEvent,
            CGEventGetFlags,
            CGEventGetIntegerValueField,
            CGEventMaskBit,
            CGEventPost,
            CGEventSetFlags,
            CGEventTapCreate,
            CGEventTapEnable,
            kCFRunLoopCommonModes,
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskShift,
            kCGEventKeyDown,
            kCGEventTapOptionDefault,
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGKeyboardEventAutorepeat,
            kCGKeyboardEventKeycode,
            kCGSessionEventTap,
        )

        self.NSEvent = NSEvent
        self.NSRunningApplication = NSRunningApplication
        self.NSWorkspace = NSWorkspace

        self.CFMachPortCreateRunLoopSource = CFMachPortCreateRunLoopSource
        self.CFRunLoopAddSource = CFRunLoopAddSource
        self.CFRunLoopGetCurrent = CFRunLoopGetCurrent
        self.CFRunLoopRun = CFRunLoopRun

        self.CGEventCreateKeyboardEvent = CGEventCreateKeyboardEvent
        self.CGEventGetFlags = CGEventGetFlags
        self.CGEventGetIntegerValueField = CGEventGetIntegerValueField
        self.CGEventMaskBit = CGEventMaskBit
        self.CGEventPost = CGEventPost
        self.CGEventSetFlags = CGEventSetFlags
        self.CGEventTapCreate = CGEventTapCreate
        self.CGEventTapEnable = CGEventTapEnable

        self.kCFRunLoopCommonModes = kCFRunLoopCommonModes
        self.kCGEventFlagMaskAlternate = kCGEventFlagMaskAlternate
        self.kCGEventFlagMaskCommand = kCGEventFlagMaskCommand
        self.kCGEventFlagMaskControl = kCGEventFlagMaskControl
        self.kCGEventFlagMaskShift = kCGEventFlagMaskShift
        self.kCGEventKeyDown = kCGEventKeyDown
        self.kCGEventTapOptionDefault = kCGEventTapOptionDefault
        self.kCGHIDEventTap = kCGHIDEventTap
        self.kCGHeadInsertEventTap = kCGHeadInsertEventTap
        self.kCGKeyboardEventAutorepeat = kCGKeyboardEventAutorepeat
        self.kCGKeyboardEventKeycode = kCGKeyboardEventKeycode
        self.kCGSessionEventTap = kCGSessionEventTap

        self.runtime = runtime
        self.detector = ProtectedContextDetector()
        menu_callbacks = {
            "toggle_pause": self._menu_toggle_pause,
            "explain_last": self._menu_explain_last,
            "show_required_secrets": self._menu_show_required_secrets,
            "manage_dot_phrases": self._menu_manage_dot_phrases,
        }
        self.presenter = create_suggestion_presenter(prefer_overlay=True, menu_callbacks=menu_callbacks)
        self.applier = MacTextApplier(self)
        self.panic_binding = parse_hotkey_spec(self.runtime.settings.panic_hotkey) or (
            35,
            {"control", "option"},
        )
        self.undo_binding = parse_hotkey_spec(self.runtime.settings.undo_hotkey) or (
            6,
            {"control", "option"},
        )
        self._status_text = ""

        self._pasteboard = None
        self._saved_clipboard = None
        try:
            from Cocoa import NSPasteboard

            self._pasteboard = NSPasteboard.generalPasteboard()
        except Exception:
            self._pasteboard = None

        self.current_token = ""
        self.last_key_ts: Optional[float] = None
        self.key_intervals: Deque[float] = deque(maxlen=30)
        self.synth_until_ts = 0.0

        self.tap = None

    def _active_app_info(self) -> Dict[str, Any]:
        workspace = self.NSWorkspace.sharedWorkspace()
        active = workspace.activeApplication()
        if not active:
            return {"name": "", "bundle_id": None, "pid": None}
        return {
            "name": active.get("NSApplicationName", ""),
            "bundle_id": active.get("NSApplicationBundleIdentifier"),
            "pid": active.get("NSApplicationProcessIdentifier"),
        }

    def _modifiers(self, flags: int) -> List[str]:
        mods: List[str] = []
        if flags & self.kCGEventFlagMaskControl:
            mods.append("control")
        if flags & self.kCGEventFlagMaskAlternate:
            mods.append("option")
        if flags & self.kCGEventFlagMaskShift:
            mods.append("shift")
        if flags & self.kCGEventFlagMaskCommand:
            mods.append("command")
        return mods

    def _event_key(self, event, keycode: int) -> str:
        if keycode in SPECIAL_KEYS:
            return SPECIAL_KEYS[keycode]

        try:
            ns_event = self.NSEvent.eventWithCGEvent_(event)
            if ns_event:
                chars = ns_event.charactersIgnoringModifiers()
                if chars:
                    return str(chars)
        except Exception:
            pass

        return f"<{keycode}>"

    def _boundary_char(self, key: str) -> Optional[str]:
        if key == "space":
            return " "
        if key == "return":
            return "\n"
        if len(key) == 1 and key in {".", ",", "!", "?", ";", ":"}:
            return key
        return None

    def _is_boundary(self, key: str) -> bool:
        return self._boundary_char(key) is not None

    def _typing_fast(self) -> bool:
        if len(self.key_intervals) < 8:
            return False
        avg = sum(self.key_intervals) / len(self.key_intervals)
        return avg < 0.12

    def _char_to_key(self, ch: str) -> Tuple[Optional[int], bool]:
        if ch in CHAR_TO_KEYCODE:
            return CHAR_TO_KEYCODE[ch], False

        if ch.isalpha() and ch.lower() in CHAR_TO_KEYCODE:
            return CHAR_TO_KEYCODE[ch.lower()], ch.isupper()

        base = SHIFT_CHAR_BASE.get(ch)
        if base and base in CHAR_TO_KEYCODE:
            return CHAR_TO_KEYCODE[base], True

        return None, False

    def _post_keycode(self, keycode: int, shift: bool = False) -> None:
        down = self.CGEventCreateKeyboardEvent(None, keycode, True)
        up = self.CGEventCreateKeyboardEvent(None, keycode, False)
        if shift:
            self.CGEventSetFlags(down, self.kCGEventFlagMaskShift)
            self.CGEventSetFlags(up, self.kCGEventFlagMaskShift)
        self.CGEventPost(self.kCGHIDEventTap, down)
        self.CGEventPost(self.kCGHIDEventTap, up)

    def _post_command_v(self) -> None:
        # 'v' key with command flag to paste any unicode text safely.
        down = self.CGEventCreateKeyboardEvent(None, 9, True)
        up = self.CGEventCreateKeyboardEvent(None, 9, False)
        self.CGEventSetFlags(down, self.kCGEventFlagMaskCommand)
        self.CGEventSetFlags(up, self.kCGEventFlagMaskCommand)
        self.CGEventPost(self.kCGHIDEventTap, down)
        self.CGEventPost(self.kCGHIDEventTap, up)

    def _post_text(self, text: str) -> bool:
        for ch in text:
            keycode, shift = self._char_to_key(ch)
            if keycode is None:
                return False
            self._post_keycode(keycode, shift=shift)
        return True

    def _paste_text(self, text: str) -> bool:
        if self._pasteboard is None:
            return False
        try:
            self._saved_clipboard = self._pasteboard.stringForType_("public.utf8-plain-text")
            self._pasteboard.clearContents()
            self._pasteboard.setString_forType_(text, "public.utf8-plain-text")
            self._post_command_v()
            # Restore previous clipboard after paste.
            if self._saved_clipboard is not None:
                self._pasteboard.clearContents()
                self._pasteboard.setString_forType_(self._saved_clipboard, "public.utf8-plain-text")
            return True
        except Exception:
            return False

    def _replace_recent_text(self, before: str, after: str) -> bool:
        if not before:
            return False
        self.synth_until_ts = time.time() + 0.35
        for _ in range(len(before)):
            self._post_keycode(51)
        if self._post_text(after):
            return True
        return self._paste_text(after)

    def _set_status_text(self, text: str) -> None:
        if text == self._status_text:
            return
        self._status_text = text
        if text:
            self.presenter.show_state(text)
        else:
            self.presenter.hide_state()

    @staticmethod
    def _hotkey_matches(keycode: int, modset: set[str], binding: Tuple[int, set[str]]) -> bool:
        target_keycode, target_mods = binding
        return keycode == target_keycode and target_mods.issubset(modset)

    def _handle_pending_controls(self, keycode: int, mods: List[str]) -> bool:
        if not self.runtime.pending:
            return False

        # Tab accept
        if keycode == 48 and not mods:
            p = self.runtime.pending
            if p:
                ok = self.applier.apply_replacement(
                    before=f"{p.token}{p.boundary}",
                    after=f"{p.replacement}{p.boundary}",
                    app_name=p.app_name,
                    app_bundle_id=p.app_bundle_id,
                )
                if ok:
                    out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="accept")))
                    print(out.message)
                else:
                    reason = self.applier.last_error or "Unable to apply replacement."
                    print(f"Accept blocked: {reason}")
                    dismiss_out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="dismiss")))
                    print(dismiss_out.message)
                    self._set_status_text(f"Accept blocked - {reason}")
                self.presenter.hide()
            return True

        # Esc dismiss
        if keycode == 53 and not mods:
            out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="dismiss")))
            print(out.message)
            self.presenter.hide()
            return True

        return False

    def _handle_hotkeys(self, keycode: int, mods: List[str]) -> bool:
        modset = set(mods)

        # Configurable panic hotkey.
        if self._hotkey_matches(keycode, modset, self.panic_binding):
            self._menu_toggle_pause()
            return True

        # Configurable undo hotkey.
        if self._hotkey_matches(keycode, modset, self.undo_binding):
            rec = self.runtime.undo_stack.peek()
            if rec:
                active = self._active_app_info()
                ok, mode = self.applier.undo_record(rec, active_app=active)
                if ok:
                    out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="undo")))
                    print(f"{out.message} ({mode})")
            else:
                out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="undo")))
                print(out.message)
            self.presenter.hide()
            return True

        return False

    def _event_callback(self, proxy, event_type, event, refcon):
        del proxy, refcon
        try:
            now = time.time()
            if now < self.synth_until_ts:
                return event

            keycode = self.CGEventGetIntegerValueField(event, self.kCGKeyboardEventKeycode)
            autorepeat = self.CGEventGetIntegerValueField(event, self.kCGKeyboardEventAutorepeat)
            if autorepeat:
                return event

            flags = self.CGEventGetFlags(event)
            mods = self._modifiers(flags)

            if self._handle_hotkeys(keycode, mods):
                return None
            if self._handle_pending_controls(keycode, mods):
                return None

            active = self._active_app_info()
            app_name = active.get("name", "") or ""
            is_protected, reason = self.detector.check(app_name)

            key = self._event_key(event, keycode)

            # Any non-control input while suggestion is pending counts as implicit dismiss.
            if self.runtime.pending and key not in {"tab", "escape"} and "command" not in mods:
                out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="dismiss")))
                print(out.message)
                self.presenter.hide()

            idle_ms = 10000
            if self.last_key_ts is not None:
                dt = now - self.last_key_ts
                self.key_intervals.append(dt)
                idle_ms = int(dt * 1000)
            self.last_key_ts = now

            if is_protected:
                self.presenter.hide()
                self._set_status_text("Protected Mode Active - no capture, no suggestions.")
                # Boundary check still feeds runtime so blocking reasons are auditable.
                if self._is_boundary(key):
                    token = self.current_token
                    self.current_token = ""
                    out = asyncio.run(
                        self.runtime.process_event(
                            RuntimeEvent(
                                kind="boundary",
                                app_name=app_name,
                                app_bundle_id=active.get("bundle_id"),
                                app_pid=active.get("pid"),
                                token=token,
                                boundary=self._boundary_char(key) or " ",
                                idle_ms=idle_ms,
                                typing_fast=self._typing_fast(),
                                flags=RiskFlags(
                                    password_field=(reason == "password_field"),
                                    blacklisted_app=(reason == "blacklisted_app"),
                                    detector_uncertain=(reason == "detector_uncertain"),
                                    user_excluded=(reason == "user_excluded"),
                                ),
                            )
                        )
                    )
                    if out.protected_mode:
                        print(out.message)
                return event

            if self.runtime.paused:
                self._set_status_text("Paused - no capture, no suggestions.")
            else:
                cooldown = self.runtime.trust_cooldown_remaining_seconds()
                if cooldown > 0:
                    self._set_status_text(f"Trust cooldown active ({cooldown}s)")
                else:
                    self._set_status_text("")

            if key == "delete":
                self.current_token = self.current_token[:-1]
                return event

            if self._is_boundary(key):
                token = self.current_token
                self.current_token = ""
                out = asyncio.run(
                    self.runtime.process_event(
                        RuntimeEvent(
                            kind="boundary",
                            app_name=app_name,
                            app_bundle_id=active.get("bundle_id"),
                            app_pid=active.get("pid"),
                            token=token,
                            boundary=self._boundary_char(key) or " ",
                            idle_ms=idle_ms,
                            typing_fast=self._typing_fast(),
                            flags=RiskFlags(),
                        )
                    )
                )
                if out.action == "suggest" and self.runtime.pending:
                    self.presenter.show(self.runtime.pending.token, self.runtime.pending.replacement)
                else:
                    self.presenter.hide()
                    if out.protected_mode:
                        self._set_status_text("Protected Mode Active - no capture, no suggestions.")
                    elif out.status_hint:
                        self._set_status_text(out.status_hint)
                if out.action in {"suggest", "accept", "dismiss", "undo"} or "Protected Mode" in out.message:
                    print(out.message)
                return event

            if len(key) == 1 and key.isprintable():
                self.current_token += key

        except Exception as exc:
            print(f"mac bridge callback error: {exc}")

        return event

    def _menu_toggle_pause(self) -> None:
        out = asyncio.run(self.runtime.process_event(RuntimeEvent(kind="panic")))
        print(out.message)
        self.presenter.hide()
        if out.paused:
            self._set_status_text("Paused - no capture, no suggestions.")
            return
        cooldown = self.runtime.trust_cooldown_remaining_seconds()
        if cooldown > 0:
            self._set_status_text(f"Trust cooldown active ({cooldown}s)")
            return
        self._set_status_text("")

    def _menu_explain_last(self) -> None:
        snapshot = self.runtime.last_decision_snapshot()
        if not snapshot:
            print("No decision snapshot available yet.")
            self._set_status_text("No decision snapshot available.")
            return

        action = str(snapshot.get("action", "do_nothing"))
        reason = str(snapshot.get("reason_tag", "unknown"))
        profile = str(snapshot.get("profile", "unknown"))
        token = str(snapshot.get("token", ""))
        idle_ms = int(snapshot.get("idle_ms", 0))
        typing_fast = bool(snapshot.get("typing_fast", False))
        remaining = int(snapshot.get("trust_cooldown_remaining_seconds", 0))

        print(
            "Last decision:"
            f" action={action}"
            f" reason={reason}"
            f" profile={profile}"
            f" token='{token}'"
            f" idle_ms={idle_ms}"
            f" typing_fast={typing_fast}"
            f" trust_cooldown_remaining={remaining}s"
        )
        self._set_status_text(f"{action} ({reason})")

    def _menu_show_required_secrets(self) -> None:
        rows = self.runtime.store.list_secret_aliases(limit=100)
        if not rows:
            print("No required secret aliases recorded yet.")
            print("Tip: accept a suggestion containing {{SECRET:ALIAS}} to register aliases.")
            self._set_status_text("No required secret aliases.")
            return

        print("Required secret aliases (most recent first):")
        for row in rows:
            print(f"- {row['alias']} (usage={row['usage_count']})")
        self._set_status_text(f"Required secrets: {len(rows)} aliases")

    def _menu_manage_dot_phrases(self) -> None:
        rows = self.runtime.store.list_phrase_patterns(limit=12)
        print("Dot-phrase management commands:")
        print('PYTHONPATH=src python -m cognitiveio.cli phrase-add ".meW" "Best,\\nYour Name" --profile email_docs')
        print("PYTHONPATH=src python -m cognitiveio.cli phrase-list --profile email_docs")
        print("PYTHONPATH=src python -m cognitiveio.cli phrase-remove .meW --profile email_docs")
        if rows:
            print("Configured phrase triggers:")
            for row in rows:
                profile = row["profile"] or "*"
                print(f"- {row['before']} ({profile}) conf={row['confidence']:.2f}")
        else:
            print("No phrase patterns configured yet.")
        self._set_status_text("See terminal for dot-phrase commands.")

    def start(self) -> None:
        event_mask = self.CGEventMaskBit(self.kCGEventKeyDown)

        self.tap = self.CGEventTapCreate(
            self.kCGSessionEventTap,
            self.kCGHeadInsertEventTap,
            self.kCGEventTapOptionDefault,
            event_mask,
            self._event_callback,
            None,
        )
        if not self.tap:
            raise RuntimeError("Failed to create event tap. Check Accessibility permissions.")

        source = self.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        self.CFRunLoopAddSource(
            self.CFRunLoopGetCurrent(),
            source,
            self.kCFRunLoopCommonModes,
        )
        self.CGEventTapEnable(self.tap, True)

        print("macOS runtime started. Ctrl+C to stop.")
        print(
            "Hotkeys: "
            f"{self.runtime.settings.panic_hotkey} panic, "
            f"{self.runtime.settings.undo_hotkey} undo, "
            "Tab accept, Esc dismiss."
        )
        self.CFRunLoopRun()
