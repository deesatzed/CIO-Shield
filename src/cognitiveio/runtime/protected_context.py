from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple
import json


BLACKLISTED_APPS = {
    "1Password",
    "1Password 7",
    "LastPass",
    "Bitwarden",
    "Dashlane",
    "KeePassXC",
    "KeePassX",
    "Keychain Access",
    "Security",
}

SENSITIVE_APP_KEYWORDS = {
    "password",
    "keychain",
    "wallet",
    "authenticator",
}

PASSWORD_KEYWORDS = {
    "password",
    "passwd",
    "passphrase",
    "pin",
    "secret",
    "credentials",
    "secure",
}


class ProtectedContextDetector:
    """Best-effort protected context detector for hard privacy blocks."""

    def __init__(self, exclusion_path: Optional[Path] = None):
        self.exclusion_path = exclusion_path or (Path.home() / ".cognitiveio" / "exclusions.json")
        self.user_excluded_apps: Set[str] = self._load_user_exclusions()

        self._detector_uncertain = False

        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                AXUIElementCreateSystemWide,
                kAXDescriptionAttribute,
                kAXFocusedUIElementAttribute,
                kAXRoleAttribute,
            )
        except Exception:
            self._ax_available = False
            self._AXUIElementCopyAttributeValue = None
            self._AXUIElementCreateSystemWide = None
            self._kAXDescriptionAttribute = None
            self._kAXFocusedUIElementAttribute = None
            self._kAXRoleAttribute = None
            return

        self._ax_available = True
        self._AXUIElementCopyAttributeValue = AXUIElementCopyAttributeValue
        self._AXUIElementCreateSystemWide = AXUIElementCreateSystemWide
        self._kAXDescriptionAttribute = kAXDescriptionAttribute
        self._kAXFocusedUIElementAttribute = kAXFocusedUIElementAttribute
        self._kAXRoleAttribute = kAXRoleAttribute

    def _load_user_exclusions(self) -> Set[str]:
        if not self.exclusion_path.exists():
            return set()
        try:
            data = json.loads(self.exclusion_path.read_text(encoding="utf-8"))
            return set(data.get("excluded_apps", []))
        except Exception:
            return set()

    def _is_sensitive_app(self, app_name: str) -> Tuple[bool, str]:
        if app_name in BLACKLISTED_APPS:
            return True, "blacklisted_app"
        if app_name in self.user_excluded_apps:
            return True, "user_excluded"

        lower = app_name.lower()
        if any(k in lower for k in SENSITIVE_APP_KEYWORDS):
            return True, "sensitive_app_keyword"

        return False, "allowed"

    def _is_password_field(self) -> bool:
        self._detector_uncertain = False

        if (
            not self._ax_available
            or self._AXUIElementCreateSystemWide is None
            or self._AXUIElementCopyAttributeValue is None
            or self._kAXFocusedUIElementAttribute is None
            or self._kAXRoleAttribute is None
            or self._kAXDescriptionAttribute is None
        ):
            return False

        try:
            system_wide = self._AXUIElementCreateSystemWide()
            err, focused = self._AXUIElementCopyAttributeValue(
                system_wide,
                self._kAXFocusedUIElementAttribute,
                None,
            )
            if err or not focused:
                return False

            err, role = self._AXUIElementCopyAttributeValue(
                focused,
                self._kAXRoleAttribute,
                None,
            )
            if not err and str(role) == "AXSecureTextField":
                return True

            err, description = self._AXUIElementCopyAttributeValue(
                focused,
                self._kAXDescriptionAttribute,
                None,
            )
            if not err and description:
                d = str(description).lower()
                return any(k in d for k in PASSWORD_KEYWORDS)
        except Exception:
            self._detector_uncertain = True
            return False

        return False

    def check(self, app_name: str, conservative_on_uncertain: bool = False) -> Tuple[bool, str]:
        is_sensitive, reason = self._is_sensitive_app(app_name)
        if is_sensitive:
            return True, reason

        if self._is_password_field():
            return True, "password_field"

        if self._detector_uncertain and conservative_on_uncertain:
            return True, "detector_uncertain"

        return False, "allowed"
