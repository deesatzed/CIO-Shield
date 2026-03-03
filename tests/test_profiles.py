from cognitiveio.context.profiles import (
    AppContext,
    PROFILE_CODE,
    PROFILE_EMAIL_DOCS,
    PROFILE_UNKNOWN,
    classify_profile,
)


def test_classify_profile_uses_bundle_id_when_app_name_is_localized():
    ctx = AppContext(app_name="Notas", bundle_id="com.apple.Notes")
    assert classify_profile(ctx) == PROFILE_EMAIL_DOCS


def test_classify_profile_prefers_bundle_override():
    ctx = AppContext(app_name="Notes", bundle_id="com.apple.Notes")
    overrides = {"com.apple.Notes": PROFILE_CODE, "Notes": PROFILE_UNKNOWN}
    assert classify_profile(ctx, overrides=overrides) == PROFILE_CODE


def test_classify_profile_falls_back_to_unknown_when_no_match():
    ctx = AppContext(app_name="CustomApp", bundle_id="com.example.custom")
    assert classify_profile(ctx) == PROFILE_UNKNOWN
