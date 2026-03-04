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


# ── Extended coverage tests ────────────────────────────────────────

def test_malformed_exclusions_file(tmp_path: Path):
    p = tmp_path / "exclusions.json"
    p.write_text("NOT VALID JSON {{", encoding="utf-8")
    det = ProtectedContextDetector(exclusion_path=p)
    assert det.user_excluded_apps == set()


def test_password_field_detection_consistent(tmp_path: Path):
    """_is_password_field returns a bool regardless of AX availability."""
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    result = det._is_password_field()
    assert isinstance(result, bool)


def test_is_password_field_without_ax(tmp_path: Path):
    """When AX is disabled, _is_password_field returns False."""
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    det._ax_available = False
    assert det._is_password_field() is False


def test_conservative_uncertain_path(tmp_path: Path):
    """When AX off + detector_uncertain + conservative → blocked."""
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    det._ax_available = False
    # Simulate: _is_password_field returns False but uncertainty flag set
    # _is_password_field resets _detector_uncertain at start, so we need to
    # patch it to keep the flag
    original = det._is_password_field

    def _patched():
        result = original()
        det._detector_uncertain = True  # simulate exception path
        return result

    det._is_password_field = _patched
    protected, reason = det.check("Mail", conservative_on_uncertain=True)
    assert protected is True
    assert reason == "detector_uncertain"


def test_not_conservative_when_uncertain(tmp_path: Path):
    """When conservative_on_uncertain=False, uncertainty doesn't block."""
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    det._ax_available = False

    original = det._is_password_field

    def _patched():
        result = original()
        det._detector_uncertain = True
        return result

    det._is_password_field = _patched
    protected, reason = det.check("Mail", conservative_on_uncertain=False)
    assert protected is False
    assert reason == "allowed"


def test_all_blacklisted_apps(tmp_path: Path):
    from cognitiveio.runtime.protected_context import BLACKLISTED_APPS
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    for app in BLACKLISTED_APPS:
        blocked, reason = det.check(app)
        assert blocked is True
        assert reason == "blacklisted_app"


def test_all_sensitive_keywords(tmp_path: Path):
    from cognitiveio.runtime.protected_context import SENSITIVE_APP_KEYWORDS
    det = ProtectedContextDetector(exclusion_path=tmp_path / "missing.json")
    for keyword in SENSITIVE_APP_KEYWORDS:
        app_name = f"My {keyword.title()} Tool"
        blocked, reason = det.check(app_name)
        assert blocked is True
        assert reason == "sensitive_app_keyword"
