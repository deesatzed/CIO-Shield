from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

PROFILE_CODE = "code"
PROFILE_TERMINAL = "terminal"
PROFILE_EMAIL_DOCS = "email_docs"
PROFILE_CHAT = "chat"
PROFILE_UNKNOWN = "unknown"
PROFILE_BLOCKED_BY_POLICY = "blocked_by_policy"

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

DEFAULT_BUNDLE_PROFILE_MAP: Dict[str, str] = {
    "com.microsoft.VSCode": PROFILE_CODE,
    "com.apple.dt.Xcode": PROFILE_CODE,
    "com.jetbrains.pycharm": PROFILE_CODE,
    "com.apple.Terminal": PROFILE_TERMINAL,
    "com.googlecode.iterm2": PROFILE_TERMINAL,
    "com.apple.mail": PROFILE_EMAIL_DOCS,
    "com.microsoft.Outlook": PROFILE_EMAIL_DOCS,
    "com.apple.Safari": PROFILE_EMAIL_DOCS,
    "com.google.Chrome": PROFILE_EMAIL_DOCS,
    "com.apple.Notes": PROFILE_EMAIL_DOCS,
    "notion.id": PROFILE_EMAIL_DOCS,
    "md.obsidian": PROFILE_EMAIL_DOCS,
    "net.shinyfrog.bear": PROFILE_EMAIL_DOCS,
    "com.tinyspeck.slackmacgap": PROFILE_CHAT,
    "com.apple.MobileSMS": PROFILE_CHAT,
    "com.hnc.Discord": PROFILE_CHAT,
    "com.discordapp.Discord": PROFILE_CHAT,
}


def classify_profile(
    ctx: AppContext,
    overrides: Optional[Dict[str, str]] = None,
    policy: Optional[object] = None,
) -> str:
    """Classify an app context into a profile string.

    When a corporate policy is provided, apps/bundles in the force-blocked
    lists are classified as ``blocked_by_policy`` before any other check.
    """
    # Corporate policy force-blocks take highest priority.
    if policy is not None:
        blocked_apps: FrozenSet[str] = getattr(policy, "force_blocked_apps", frozenset())
        blocked_bundles: FrozenSet[str] = getattr(policy, "force_blocked_bundles", frozenset())
        if ctx.app_name in blocked_apps:
            return PROFILE_BLOCKED_BY_POLICY
        if ctx.bundle_id and ctx.bundle_id in blocked_bundles:
            return PROFILE_BLOCKED_BY_POLICY

    if overrides:
        if ctx.bundle_id and ctx.bundle_id in overrides:
            return overrides[ctx.bundle_id]
        if ctx.app_name in overrides:
            return overrides[ctx.app_name]
    if ctx.bundle_id and ctx.bundle_id in DEFAULT_BUNDLE_PROFILE_MAP:
        return DEFAULT_BUNDLE_PROFILE_MAP[ctx.bundle_id]
    return DEFAULT_PROFILE_MAP.get(ctx.app_name, PROFILE_UNKNOWN)
