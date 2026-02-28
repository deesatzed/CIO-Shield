from cognitiveio.runtime.suggestion_presenter import menu_bar_title_for_state


def test_menu_bar_title_for_protected_state():
    assert menu_bar_title_for_state("Protected Mode Active - no capture, no suggestions.") == "CIO-P"


def test_menu_bar_title_for_paused_state():
    assert menu_bar_title_for_state("Paused - no capture, no suggestions.") == "CIO-II"


def test_menu_bar_title_for_normal_state():
    assert menu_bar_title_for_state("") == "CIO"
