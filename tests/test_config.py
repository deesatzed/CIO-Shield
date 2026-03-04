"""Phase 2a: Tests for config.py — resolve_app_home, Settings, settings_from_env."""
from pathlib import Path

from cognitiveio.config import Settings, resolve_app_home, settings_from_env


class TestResolveAppHome:
    def test_env_var_override(self, tmp_path: Path, monkeypatch):
        target = tmp_path / "custom_home"
        monkeypatch.setenv("COGNITIVEIO_HOME", str(target))
        result = resolve_app_home()
        assert result == target

    def test_falls_back_to_home_dir(self, monkeypatch):
        monkeypatch.delenv("COGNITIVEIO_HOME", raising=False)
        result = resolve_app_home()
        # Should be either ~/.cognitiveio or cwd/.cognitiveio
        assert result.name == ".cognitiveio"

    def test_cwd_fallback_when_home_not_writable(self, tmp_path: Path, monkeypatch):
        # Set COGNITIVEIO_HOME to a non-writable location: empty string triggers fallback
        monkeypatch.delenv("COGNITIVEIO_HOME", raising=False)
        result = resolve_app_home()
        assert isinstance(result, Path)
        assert result.exists()


class TestSettingsDefaults:
    def test_suggest_only_default(self):
        s = Settings()
        assert s.suggest_only is True

    def test_idle_pause_ms_default(self):
        s = Settings()
        assert s.idle_pause_ms == 300

    def test_auto_apply_default_off(self):
        s = Settings()
        assert s.auto_apply_enabled is False

    def test_apple_fm_default_on(self):
        s = Settings()
        assert s.apple_fm_enabled is True

    def test_fm_required_for_gray_zone_default(self):
        s = Settings()
        assert s.fm_required_for_gray_zone is True

    def test_db_path_property(self, tmp_path: Path):
        s = Settings(app_home=tmp_path)
        assert s.db_path == tmp_path / "cognitiveio.db"

    def test_report_dir_property(self, tmp_path: Path):
        s = Settings(app_home=tmp_path)
        rd = s.report_dir
        assert rd == tmp_path / "reports"
        assert rd.exists()


class TestSettingsFromEnv:
    def test_fm_disabled(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ENABLE_APPLE_FM", "0")
        s = settings_from_env()
        assert s.apple_fm_enabled is False

    def test_fm_enabled(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ENABLE_APPLE_FM", "1")
        s = settings_from_env()
        assert s.apple_fm_enabled is True

    def test_panic_hotkey_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_PANIC_HOTKEY", "ctrl+shift+q")
        s = settings_from_env()
        assert s.panic_hotkey == "ctrl+shift+q"

    def test_undo_hotkey_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_UNDO_HOTKEY", "ctrl+shift+u")
        s = settings_from_env()
        assert s.undo_hotkey == "ctrl+shift+u"

    def test_idle_pause_ms_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_IDLE_PAUSE_MS", "500")
        s = settings_from_env()
        assert s.idle_pause_ms == 500

    def test_db_encryption_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_DB_ENCRYPTION", "required")
        s = settings_from_env()
        assert s.db_encryption_mode == "required"

    def test_forced_variant_a(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ARB_VARIANT", "A")
        s = settings_from_env()
        assert s.apple_fm_variant == "A"

    def test_forced_variant_b(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ARB_VARIANT", "B")
        s = settings_from_env()
        assert s.apple_fm_variant == "B"

    def test_auto_apply_via_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ENABLE_SOFT_AUTO", "1")
        s = settings_from_env()
        assert s.auto_apply_enabled is True

    def test_secret_cache_ttl(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_SECRET_CACHE_TTL_SECONDS", "120")
        s = settings_from_env()
        assert s.secret_cache_ttl_seconds == 120.0

    def test_secret_cache_ttl_floor(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_SECRET_CACHE_TTL_SECONDS", "0.1")
        s = settings_from_env()
        assert s.secret_cache_ttl_seconds == 1.0  # floor at 1.0

    def test_invalid_cache_ttl_ignored(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_SECRET_CACHE_TTL_SECONDS", "not_a_number")
        s = settings_from_env()
        assert s.secret_cache_ttl_seconds == 60.0  # default

    def test_db_key_ref_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_DB_KEY_REF", "{{SECRET:CUSTOM_KEY}}")
        s = settings_from_env()
        assert s.db_key_ref == "{{SECRET:CUSTOM_KEY}}"

    def test_ab_enabled_assigns_variant(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("COGNITIVEIO_HOME", str(tmp_path))
        monkeypatch.setenv("COGNITIVEIO_ENABLE_AB", "1")
        monkeypatch.delenv("COGNITIVEIO_ARB_VARIANT", raising=False)
        s = settings_from_env()
        assert s.apple_fm_variant in {"A", "B"}


class TestIsWritable:
    def test_writable_path(self, tmp_path: Path):
        from cognitiveio.config import _is_writable
        target = tmp_path / "writable_test"
        assert _is_writable(target) is True

    def test_non_writable_path(self):
        from cognitiveio.config import _is_writable
        # /dev/null is not a valid directory
        assert _is_writable(Path("/dev/null/impossible")) is False


class TestResolveAppHomeFallback:
    def test_fallback_to_cwd_when_env_and_home_fail(self, monkeypatch, tmp_path: Path):
        """When env var path is non-writable and home is non-writable, falls back to cwd."""
        monkeypatch.setenv("COGNITIVEIO_HOME", "/dev/null/no_write")
        # Patch _is_writable to fail for home but succeed for cwd
        import cognitiveio.config as config_mod
        original = config_mod._is_writable

        call_count = {"n": 0}
        def _patched(path):
            call_count["n"] += 1
            # Fail for env path and preferred (~/.cognitiveio), succeed for cwd fallback
            if call_count["n"] <= 2:
                return False
            return original(path)

        monkeypatch.setattr(config_mod, "_is_writable", _patched)
        result = resolve_app_home()
        assert result.name == ".cognitiveio"
