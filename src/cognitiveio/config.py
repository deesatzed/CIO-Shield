from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from cognitiveio.experiments.ab_testing import ABConfig, assign_variant, default_user_key


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def resolve_app_home() -> Path:
    """Resolve writable local app home, preferring COGNITIVEIO_HOME then ~/.cognitiveio."""
    env_home = os.getenv("COGNITIVEIO_HOME")
    if env_home:
        env_path = Path(env_home).expanduser()
        if _is_writable(env_path):
            return env_path

    preferred = Path.home() / ".cognitiveio"
    if _is_writable(preferred):
        return preferred

    fallback = Path.cwd() / ".cognitiveio"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass
class Settings:
    # Product defaults: conservative and reversible.
    suggest_only: bool = True
    idle_pause_ms: int = 300
    suggestion_min_confidence: float = 0.80

    # Explicit opt-ins.
    auto_apply_enabled: bool = False
    auto_apply_min_confidence: float = 0.97

    # Optional Apple FM arbiter (still gated by variant/availability at runtime).
    apple_fm_enabled: bool = False
    apple_fm_gray_zone_low: float = 0.45
    apple_fm_gray_zone_high: float = 0.92
    apple_fm_timeout_seconds: float = 0.08  # 80ms contract (PRODUCT_CONTRACT.md).
    apple_fm_ab_enabled: bool = True
    apple_fm_variant: str = "A"  # A deterministic-only, B allows arbiter in gray-zone.

    # Safety defaults.
    fail_safe_unknown_profile: bool = True
    protected_mode_blocks_all: bool = True

    # Intervention budget and cooldown.
    max_suggestions_per_min: int = 8
    dismissals_before_cooldown: int = 3
    cooldown_seconds: int = 45
    candidate_conflict_max_gap: float = 0.08
    candidate_conflict_min_confidence: float = 0.55

    # Trust circuit breaker: dense rejection/undo signals trigger a temporary pause.
    trust_circuit_window_seconds: int = 120
    trust_circuit_negative_events: int = 4
    trust_circuit_cooldown_seconds: int = 90

    # Hotkeys (actual mac binding is runtime-adapter dependent).
    panic_hotkey: str = "ctrl+option+p"
    undo_hotkey: str = "ctrl+option+z"

    # Local paths.
    app_home: Path = resolve_app_home()

    @property
    def db_path(self) -> Path:
        return self.app_home / "cognitiveio.db"

    @property
    def report_dir(self) -> Path:
        p = self.app_home / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p


def settings_from_env() -> Settings:
    """Create settings with environment overrides for demo/ops usage."""
    s = Settings()
    s.apple_fm_enabled = os.getenv("COGNITIVEIO_ENABLE_APPLE_FM", "0") == "1"
    s.auto_apply_enabled = os.getenv("COGNITIVEIO_ENABLE_SOFT_AUTO", "0") == "1"
    s.apple_fm_ab_enabled = os.getenv("COGNITIVEIO_ENABLE_AB", "1") == "1"

    panic_hotkey = os.getenv("COGNITIVEIO_PANIC_HOTKEY", "").strip()
    if panic_hotkey:
        s.panic_hotkey = panic_hotkey

    undo_hotkey = os.getenv("COGNITIVEIO_UNDO_HOTKEY", "").strip()
    if undo_hotkey:
        s.undo_hotkey = undo_hotkey

    variant_idle = os.getenv("COGNITIVEIO_IDLE_PAUSE_MS")
    if variant_idle and variant_idle.isdigit():
        s.idle_pause_ms = int(variant_idle)

    forced_variant = os.getenv("COGNITIVEIO_ARB_VARIANT", "").strip().upper()
    if forced_variant in {"A", "B"}:
        s.apple_fm_variant = forced_variant
    elif s.apple_fm_ab_enabled:
        user_key = os.getenv("COGNITIVEIO_AB_USER_KEY", "").strip() or default_user_key()
        s.apple_fm_variant = assign_variant(
            user_key=user_key,
            cfg=ABConfig(state_path=s.app_home / "ab_variant.txt"),
        )
    else:
        # No A/B split: explicit fm-enabled flow behaves like variant B.
        s.apple_fm_variant = "B"
    return s
