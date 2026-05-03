"""Corporate policy loading and enforcement for CIO-II Shield dual-tier architecture.

Policy file is a local JSON file deployed via MDM (Jamf/Munki/Kandji) or self-enrolled.
All processing is local — no network calls. Corporate governance strengthens safety,
never weakens it.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Tuple

from cognitiveio.config import Settings


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetentionPolicy:
    audit_retention_days: int = 90
    prune_on_startup: bool = False


@dataclass(frozen=True)
class ComplianceExportConfig:
    enabled: bool = False
    include_pattern_stats: bool = True
    include_secret_registry: bool = True
    include_block_reasons: bool = True


@dataclass(frozen=True)
class HookConfig:
    post_session_script: str = ""


@dataclass(frozen=True)
class BackfillPolicy:
    enabled: bool = True
    retention_hours: int = 24
    allowed_apps: FrozenSet[str] = frozenset()  # Empty = all internal apps
    requires_approval: bool = False


# ---------------------------------------------------------------------------
# Core policy dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyConstraints:
    """Immutable corporate policy constraints loaded from local JSON file."""

    organization_id: str = ""
    organization_name: str = ""
    tier: str = "individual"  # "individual" | "corporate"
    schema_version: int = 1
    policy_issued_at: str = ""
    policy_expires_at: str = ""

    # Settings the user cannot weaken (merged via apply_corporate_settings).
    locked_settings: Dict[str, Any] = field(default_factory=dict)

    # Corporate regex patterns for additional secret detection (additive only).
    additional_secret_patterns: Tuple[re.Pattern[str], ...] = ()

    # Apps/bundles where CIO-II hard-blocks all interventions.
    force_blocked_apps: FrozenSet[str] = frozenset()
    force_blocked_bundles: FrozenSet[str] = frozenset()

    # Force app→profile mapping overrides (corporate-mandated).
    force_profile_overrides: Dict[str, str] = field(default_factory=dict)

    # Audit data retention, compliance export, and hooks.
    retention: RetentionPolicy = RetentionPolicy()
    compliance: ComplianceExportConfig = ComplianceExportConfig()
    hooks: HookConfig = HookConfig()
    backfill: BackfillPolicy = BackfillPolicy()

    @property
    def is_corporate(self) -> bool:
        return self.tier == "corporate"

    @property
    def is_expired(self) -> bool:
        if not self.policy_expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.policy_expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return False


# ---------------------------------------------------------------------------
# Singleton default (individual tier)
# ---------------------------------------------------------------------------

_INDIVIDUAL_POLICY = PolicyConstraints()


# ---------------------------------------------------------------------------
# Policy file search paths (checked in order)
# ---------------------------------------------------------------------------

_CORPORATE_POLICY_PATHS: List[Path] = [
    Path("/Library/Application Support/CognitiveIO/corporate_policy.json"),
]


def _policy_search_paths() -> List[Path]:
    """Return ordered list of paths to check for a corporate policy file."""
    paths = list(_CORPORATE_POLICY_PATHS)

    # Environment variable override (for testing / CI).
    env_path = os.getenv("COGNITIVEIO_CORPORATE_POLICY", "").strip()
    if env_path:
        paths.insert(0, Path(env_path).expanduser())

    # Self-enrolled (user-placed).
    home_policy = Path.home() / ".cognitiveio" / "corporate_policy.json"
    paths.append(home_policy)

    return paths


# ---------------------------------------------------------------------------
# Policy parsing
# ---------------------------------------------------------------------------

def _compile_patterns(raw_patterns: List[str]) -> Tuple[re.Pattern[str], ...]:
    """Compile a list of regex strings, skipping any that fail to compile."""
    compiled: List[re.Pattern[str]] = []
    for raw in raw_patterns:
        try:
            compiled.append(re.compile(raw))
        except re.error:
            continue
    return tuple(compiled)


def _parse_policy(data: Dict[str, Any]) -> PolicyConstraints:
    """Parse a raw JSON dict into a PolicyConstraints instance."""
    schema_version = int(data.get("schema_version", 1))
    if schema_version < 1:
        return _INDIVIDUAL_POLICY

    org_id = str(data.get("organization_id", ""))
    org_name = str(data.get("organization_name", ""))
    if not org_id:
        return _INDIVIDUAL_POLICY

    issued_at = str(data.get("policy_issued_at", ""))
    expires_at = str(data.get("policy_expires_at", ""))

    # Settings overrides (locked).
    settings_overrides = data.get("settings_overrides", {})
    if not isinstance(settings_overrides, dict):
        settings_overrides = {}

    # Pattern library.
    pattern_lib = data.get("pattern_library", {})
    raw_patterns = pattern_lib.get("additional_secret_patterns", []) if isinstance(pattern_lib, dict) else []
    if not isinstance(raw_patterns, list):
        raw_patterns = []
    compiled_patterns = _compile_patterns([str(p) for p in raw_patterns])

    # Profile mandates.
    mandates = data.get("profile_mandates", {})
    if not isinstance(mandates, dict):
        mandates = {}
    blocked_apps = frozenset(str(a) for a in mandates.get("force_blocked_apps", []))
    blocked_bundles = frozenset(str(b) for b in mandates.get("force_blocked_bundles", []))
    profile_overrides = {}
    for k, v in mandates.get("force_profile_overrides", {}).items():
        profile_overrides[str(k)] = str(v)

    # Retention.
    ret_data = data.get("retention_policy", {})
    if not isinstance(ret_data, dict):
        ret_data = {}
    retention = RetentionPolicy(
        audit_retention_days=int(ret_data.get("audit_retention_days", 90)),
        prune_on_startup=bool(ret_data.get("prune_on_startup", False)),
    )

    # Compliance export.
    comp_data = data.get("compliance_export", {})
    if not isinstance(comp_data, dict):
        comp_data = {}
    compliance = ComplianceExportConfig(
        enabled=bool(comp_data.get("enabled", False)),
        include_pattern_stats=bool(comp_data.get("include_pattern_stats", True)),
        include_secret_registry=bool(comp_data.get("include_secret_registry", True)),
        include_block_reasons=bool(comp_data.get("include_block_reasons", True)),
    )

    # Hooks.
    hooks_data = data.get("hooks", {})
    if not isinstance(hooks_data, dict):
        hooks_data = {}
    hooks = HookConfig(
        post_session_script=str(hooks_data.get("post_session_script", "")),
    )

    # Backfill policy.
    bf_data = data.get("backfill_policy", {})
    if not isinstance(bf_data, dict):
        bf_data = {}
    backfill = BackfillPolicy(
        enabled=bool(bf_data.get("enabled", True)),
        retention_hours=int(bf_data.get("retention_hours", 24)),
        allowed_apps=frozenset(str(a) for a in bf_data.get("allowed_apps", [])),
        requires_approval=bool(bf_data.get("requires_approval", False)),
    )

    return PolicyConstraints(
        organization_id=org_id,
        organization_name=org_name,
        tier="corporate",
        schema_version=schema_version,
        policy_issued_at=issued_at,
        policy_expires_at=expires_at,
        locked_settings=dict(settings_overrides),
        additional_secret_patterns=compiled_patterns,
        force_blocked_apps=blocked_apps,
        force_blocked_bundles=blocked_bundles,
        force_profile_overrides=profile_overrides,
        retention=retention,
        compliance=compliance,
        hooks=hooks,
        backfill=backfill,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_corporate_policy() -> PolicyConstraints:
    """Load corporate policy from the first available path.

    Returns individual-tier defaults if no policy file is found or if the
    policy has expired.
    """
    for path in _policy_search_paths():
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                continue
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue

        policy = _parse_policy(data)

        # Expired policy degrades to individual tier.
        if policy.is_expired:
            return _INDIVIDUAL_POLICY

        return policy

    return _INDIVIDUAL_POLICY


# ---------------------------------------------------------------------------
# Settings merge (security can only be strengthened, never weakened)
# ---------------------------------------------------------------------------

# Fields where a corporate lock can ONLY strengthen security.
# True = more secure, False = less secure; so corporate can force True but
# user cannot override back to False.
_BOOLEAN_STRENGTH_MAP: Dict[str, bool] = {
    "suggest_only": True,               # True is more conservative.
    "fail_safe_unknown_profile": True,   # True blocks unknown profiles.
    "protected_mode_blocks_all": True,   # True blocks all in protected mode.
    "fm_required_for_gray_zone": True,   # True requires FM for gray-zone.
    "vault_enabled": True,
    "vault_backfill_enabled": True,
}

# Numeric fields where LOWER is MORE secure (e.g., fewer suggestions).
_NUMERIC_LOWER_IS_STRONGER = {
    "max_suggestions_per_min",
    "dismissals_before_cooldown",
}

# Numeric fields where HIGHER is MORE secure.
_NUMERIC_HIGHER_IS_STRONGER = {
    "cooldown_seconds",
    "trust_circuit_cooldown_seconds",
    "trust_circuit_negative_events",
    "trust_circuit_window_seconds",
    "idle_pause_ms",
    "suggestion_min_confidence",
    "auto_apply_min_confidence",
}

# String fields with specific allowed values that corporate can lock.
_STRING_LOCKABLE = {
    "db_encryption_mode",   # "required" is strongest.
}


def apply_corporate_settings(settings: Settings, policy: PolicyConstraints) -> Settings:
    """Merge corporate locked settings into user settings.

    Corporate can only STRENGTHEN security — never weaken it.
    If the policy is individual tier, returns settings unchanged.
    """
    if not policy.is_corporate:
        return settings

    for key, value in policy.locked_settings.items():
        if not hasattr(settings, key):
            continue

        current = getattr(settings, key)

        # Boolean: corporate can only set to the "stronger" direction.
        if key in _BOOLEAN_STRENGTH_MAP:
            strong_value = _BOOLEAN_STRENGTH_MAP[key]
            if value == strong_value:
                setattr(settings, key, value)
            continue

        # auto_apply_enabled: corporate can disable (False) but not enable.
        if key == "auto_apply_enabled" and value is False:
            settings.auto_apply_enabled = False
            continue

        # Numeric lower-is-stronger: corporate value applied if lower.
        if key in _NUMERIC_LOWER_IS_STRONGER:
            try:
                corp_val = type(current)(value)
                if corp_val <= current:
                    setattr(settings, key, corp_val)
            except (TypeError, ValueError):
                pass
            continue

        # Numeric higher-is-stronger: corporate value applied if higher.
        if key in _NUMERIC_HIGHER_IS_STRONGER:
            try:
                corp_val = type(current)(value)
                if corp_val >= current:
                    setattr(settings, key, corp_val)
            except (TypeError, ValueError):
                pass
            continue

        # db_encryption_mode: "required" > "optional" > "off".
        if key == "db_encryption_mode":
            strength_order = {"off": 0, "optional": 1, "required": 2}
            corp_strength = strength_order.get(str(value), -1)
            current_strength = strength_order.get(str(current), -1)
            if corp_strength > current_strength:
                settings.db_encryption_mode = str(value)
            continue

    return settings
