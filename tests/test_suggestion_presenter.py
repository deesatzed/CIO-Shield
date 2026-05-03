from cognitiveio.runtime.suggestion_presenter import (
    ConsoleSuggestionPresenter,
    SuggestionPresenter,
    _default_state_text,
    create_suggestion_presenter,
    mac_overlay_available,
    menu_bar_title_for_state,
)


def test_menu_bar_title_for_protected_state():
    assert menu_bar_title_for_state("Protected Mode Active - no capture, no suggestions.") == "CIO-P"


def test_menu_bar_title_for_paused_state():
    assert menu_bar_title_for_state("Paused - no capture, no suggestions.") == "CIO-II"


def test_menu_bar_title_for_normal_state():
    assert menu_bar_title_for_state("") == "CIO"


# ── Phase 3: Extended presenter tests ───────────────────────────────

def test_console_presenter_show(capsys):
    p = ConsoleSuggestionPresenter()
    p.show("teh", "the")
    captured = capsys.readouterr()
    assert "teh" in captured.out
    assert "the" in captured.out
    assert "/accept" in captured.out


def test_console_presenter_hide_no_raise():
    p = ConsoleSuggestionPresenter()
    p.hide()  # Should not raise


def test_console_presenter_show_state_deduplication(capsys):
    p = ConsoleSuggestionPresenter()
    p.show_state("Running - suggestions enabled.")
    p.show_state("Running - suggestions enabled.")  # duplicate
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.strip()]
    assert len(lines) == 1  # Only one print


def test_console_presenter_hide_state_resets(capsys):
    p = ConsoleSuggestionPresenter()
    p.show_state("Running - suggestions enabled.")
    p.hide_state()
    p.show_state("Running - suggestions enabled.")  # should print again
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.strip()]
    assert len(lines) == 2


def test_create_suggestion_presenter_console():
    p = create_suggestion_presenter(prefer_overlay=False)
    assert isinstance(p, ConsoleSuggestionPresenter)


def test_base_presenter_raises_not_implemented():
    p = SuggestionPresenter()
    try:
        p.show("a", "b")
        assert False, "Expected NotImplementedError"
    except NotImplementedError:
        pass
    try:
        p.hide()
        assert False, "Expected NotImplementedError"
    except NotImplementedError:
        pass
    # show_state and hide_state are no-ops on base, shouldn't raise
    p.show_state("test")
    p.hide_state()


# ── Extended coverage: non-Cocoa helper functions ──────────────────

def test_mac_overlay_available_returns_bool():
    result = mac_overlay_available()
    assert isinstance(result, bool)


def test_default_state_text():
    text = _default_state_text()
    assert "Running" in text
    assert "suggestions" in text.lower()


def test_menu_bar_title_variants():
    assert menu_bar_title_for_state("Running - suggestions enabled.") == "CIO"
    assert menu_bar_title_for_state("PROTECTED MODE ACTIVE") == "CIO-P"
    assert menu_bar_title_for_state("Paused by user") == "CIO-II"
    assert menu_bar_title_for_state("Trust cooldown active") == "CIO"


def test_create_suggestion_presenter_overlay_path():
    """create_suggestion_presenter with prefer_overlay=True on macOS."""
    p = create_suggestion_presenter(prefer_overlay=True)
    # Either CocoaOverlay or Console depending on system
    assert isinstance(p, SuggestionPresenter)
