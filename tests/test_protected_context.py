from pathlib import Path
import json

from cognitiveio.runtime.protected_context import ProtectedContextDetector


def test_blacklisted_app_is_blocked(tmp_path: Path):
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    blocked, reason = det.check("1Password")
    assert blocked is True
    assert reason == "blacklisted_app"


def test_user_excluded_app_is_blocked(tmp_path: Path):
    p = tmp_path / "exclusions.json"
    p.write_text(json.dumps({"excluded_apps": ["MySecretApp"]}), encoding="utf-8")

    det = ProtectedContextDetector(exclusion_path=p)
    blocked, reason = det.check("MySecretApp")
    assert blocked is True
    assert reason == "user_excluded"


def test_sensitive_keyword_app_is_blocked(tmp_path: Path):
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    blocked, reason = det.check("Acme Password Vault")
    assert blocked is True
    assert reason == "sensitive_app_keyword"


def test_normal_app_not_blocked(tmp_path: Path):
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    blocked, reason = det.check("Mail")
    assert blocked is False
    assert reason in {"allowed", "detector_uncertain"}
