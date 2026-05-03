from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from cognitiveio.runtime.ax_geometry import AXCaretLocator


def mac_overlay_available() -> bool:
    try:
        from Cocoa import NSColor, NSFont, NSWindow  # noqa: F401
        return True
    except Exception:
        return False


class SuggestionPresenter:
    def show(self, token: str, replacement: str) -> None:
        raise NotImplementedError

    def hide(self) -> None:
        raise NotImplementedError

    def show_state(self, text: str) -> None:
        return

    def hide_state(self) -> None:
        return


def menu_bar_title_for_state(text: str) -> str:
    up = text.upper()
    if "PROTECTED MODE ACTIVE" in up:
        return "CIO-P"
    if up.startswith("PAUSED"):
        return "CIO-II"
    return "CIO"


def _default_state_text() -> str:
    return "Running - suggestions enabled."


class MenuBarStateIndicator:
    """Always-visible menu bar status indicator for safety state."""

    def __init__(self, callbacks: Optional[Dict[str, Callable[[], None]]] = None):
        from Cocoa import (
            NSMenu,
            NSMenuItem,
            NSObject,
            NSStatusBar,
            NSVariableStatusItemLength,
        )
        import objc

        self._status_bar = NSStatusBar.systemStatusBar()
        self._item = self._status_bar.statusItemWithLength_(NSVariableStatusItemLength)

        class _ActionHandler(NSObject):
            def initWithCallbacks_(self, cb_map):  # noqa: N802
                self = objc.super(_ActionHandler, self).init()
                if self is None:
                    return None
                self._cb_map = cb_map or {}
                return self

            def togglePause_(self, _sender):  # noqa: N802
                cb = self._cb_map.get("toggle_pause")
                if cb:
                    cb()

            def explainLast_(self, _sender):  # noqa: N802
                cb = self._cb_map.get("explain_last")
                if cb:
                    cb()

            def showRequiredSecrets_(self, _sender):  # noqa: N802
                cb = self._cb_map.get("show_required_secrets")
                if cb:
                    cb()

            def manageDotPhrases_(self, _sender):  # noqa: N802
                cb = self._cb_map.get("manage_dot_phrases")
                if cb:
                    cb()

        self._action_handler = _ActionHandler.alloc().initWithCallbacks_(callbacks or {})
        self._menu = NSMenu.alloc().init()
        self._state_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self._state_item.setEnabled_(False)
        self._menu.addItem_(self._state_item)
        self._menu.addItem_(NSMenuItem.separatorItem())

        self._pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause / Resume",
            "togglePause:",
            "",
        )
        self._pause_item.setTarget_(self._action_handler)
        self._menu.addItem_(self._pause_item)

        explain_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Explain Last Decision",
            "explainLast:",
            "",
        )
        explain_item.setTarget_(self._action_handler)
        self._menu.addItem_(explain_item)

        secrets_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Show Required Secrets",
            "showRequiredSecrets:",
            "",
        )
        secrets_item.setTarget_(self._action_handler)
        self._menu.addItem_(secrets_item)

        phrases_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Manage Dot-Phrases",
            "manageDotPhrases:",
            "",
        )
        phrases_item.setTarget_(self._action_handler)
        self._menu.addItem_(phrases_item)

        self._item.setMenu_(self._menu)

        self.set_state("")

    def set_state(self, text: str) -> None:
        title = menu_bar_title_for_state(text)
        current_text = text or _default_state_text()
        button = self._item.button()
        if button is not None:
            button.setTitle_(title)
            button.setToolTip_(current_text)
        self._state_item.setTitle_(f"State: {current_text}")
        paused = current_text.upper().startswith("PAUSED")
        self._pause_item.setTitle_("Resume Suggestions" if paused else "Pause Suggestions")

    def close(self) -> None:
        self._status_bar.removeStatusItem_(self._item)


class ConsoleSuggestionPresenter(SuggestionPresenter):
    def __init__(self):
        self._last_state: str = ""

    def show(self, token: str, replacement: str) -> None:
        print(f"Ghost suggestion: {token} -> {replacement} [/accept | /dismiss]")

    def hide(self) -> None:
        return

    def show_state(self, text: str) -> None:
        if text != self._last_state:
            print(text)
            self._last_state = text

    def hide_state(self) -> None:
        self._last_state = ""
        return


class CocoaOverlaySuggestionPresenter(SuggestionPresenter):
    """Minimal floating overlay near focused element or mouse pointer."""

    def __init__(self, menu_callbacks: Optional[Dict[str, Callable[[], None]]] = None):
        from Cocoa import (
            NSBackingStoreBuffered,
            NSColor,
            NSFont,
            NSMakeRect,
            NSScreen,
            NSStatusWindowLevel,
            NSTextField,
            NSWindow,
            NSWindowStyleMaskBorderless,
        )

        self.NSColor = NSColor
        self.NSFont = NSFont
        self.NSStatusWindowLevel = NSStatusWindowLevel

        rect = NSMakeRect(200, 200, 320, 28)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setHasShadow_(True)
        self.window.setLevel_(NSStatusWindowLevel)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setIgnoresMouseEvents_(True)

        self.label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 320, 28))
        self.label.setEditable_(False)
        self.label.setSelectable_(False)
        self.label.setBezeled_(False)
        self.label.setDrawsBackground_(True)
        self.label.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.1, 0.88))
        self.label.setTextColor_(NSColor.whiteColor())
        self.label.setFont_(NSFont.systemFontOfSize_(13.0))

        content = self.window.contentView()
        content.addSubview_(self.label)

        screen = NSScreen.mainScreen()
        frame = screen.frame() if screen else rect
        state_rect = NSMakeRect(float(frame.size.width - 430), float(frame.size.height - 24), 410, 20)
        self.state_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            state_rect,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.state_window.setOpaque_(False)
        self.state_window.setHasShadow_(False)
        self.state_window.setLevel_(NSStatusWindowLevel)
        self.state_window.setBackgroundColor_(NSColor.clearColor())
        self.state_window.setIgnoresMouseEvents_(True)

        self.state_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 410, 20))
        self.state_label.setEditable_(False)
        self.state_label.setSelectable_(False)
        self.state_label.setBezeled_(False)
        self.state_label.setDrawsBackground_(True)
        self.state_label.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.15, 0.75))
        self.state_label.setTextColor_(NSColor.whiteColor())
        self.state_label.setFont_(NSFont.boldSystemFontOfSize_(11.0))

        state_content = self.state_window.contentView()
        state_content.addSubview_(self.state_label)

        self._menu_indicator: Optional[MenuBarStateIndicator]
        try:
            self._menu_indicator = MenuBarStateIndicator(callbacks=menu_callbacks)
        except Exception:
            self._menu_indicator = None

        self._caret_locator = AXCaretLocator()

    def _preferred_point(self) -> Optional[Tuple[float, float]]:
        if self._caret_locator.available:
            pt = self._caret_locator.locate()
            if pt is not None:
                return pt.x, pt.y

        try:
            from Cocoa import NSEvent

            loc = NSEvent.mouseLocation()
            return float(loc.x + 12.0), float(loc.y + 12.0)
        except Exception:
            return None

    def show(self, token: str, replacement: str) -> None:
        self.label.setStringValue_(f"{token} -> {replacement}    Tab accept / Esc dismiss")
        pt = self._preferred_point()
        if pt:
            # Cocoa expects top-left point in global screen coords.
            self.window.setFrameTopLeftPoint_(pt)
        self.window.orderFrontRegardless()

    def hide(self) -> None:
        self.window.orderOut_(None)

    def show_state(self, text: str) -> None:
        self.state_label.setStringValue_(text)
        self.state_window.orderFrontRegardless()
        if self._menu_indicator is not None:
            self._menu_indicator.set_state(text)

    def hide_state(self) -> None:
        self.state_window.orderOut_(None)
        if self._menu_indicator is not None:
            self._menu_indicator.set_state("")


def create_suggestion_presenter(
    prefer_overlay: bool = True,
    menu_callbacks: Optional[Dict[str, Callable[[], None]]] = None,
) -> SuggestionPresenter:
    if prefer_overlay and mac_overlay_available():
        try:
            return CocoaOverlaySuggestionPresenter(menu_callbacks=menu_callbacks)
        except Exception:
            return ConsoleSuggestionPresenter()
    return ConsoleSuggestionPresenter()
