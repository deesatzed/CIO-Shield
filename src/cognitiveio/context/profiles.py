from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict

PROFILE_CODE = "code"
PROFILE_TERMINAL = "terminal"
PROFILE_EMAIL_DOCS = "email_docs"
PROFILE_CHAT = "chat"
PROFILE_UNKNOWN = "unknown"

@dataclass(frozen=True)
class AppContext:
    app_name: str
    bundle_id: Optional[str] = None
    window_title: Optional[str] = None

DEFAULT_PROFILE_MAP: Dict[str, str] = {
    "Visual Studio Code": PROFILE_CODE,
    "Xcode": PROFILE_CODE,
    "PyCharm": PROFILE_CODE,
    "Terminal": PROFILE_TERMINAL,
    "iTerm2": PROFILE_TERMINAL,
    "Mail": PROFILE_EMAIL_DOCS,
    "Microsoft Outlook": PROFILE_EMAIL_DOCS,
    "Safari": PROFILE_EMAIL_DOCS,
    "Google Chrome": PROFILE_EMAIL_DOCS,
    "Notes": PROFILE_EMAIL_DOCS,
    "Notion": PROFILE_EMAIL_DOCS,
    "Obsidian": PROFILE_EMAIL_DOCS,
    "Bear": PROFILE_EMAIL_DOCS,
    "Slack": PROFILE_CHAT,
    "Messages": PROFILE_CHAT,
    "Discord": PROFILE_CHAT,
}

def classify_profile(ctx: AppContext, overrides: Optional[Dict[str, str]] = None) -> str:
    if overrides and ctx.app_name in overrides:
        return overrides[ctx.app_name]
    return DEFAULT_PROFILE_MAP.get(ctx.app_name, PROFILE_UNKNOWN)
