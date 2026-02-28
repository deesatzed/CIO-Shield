from cognitiveio.runtime.mac_bridge import mac_runtime_available, parse_hotkey_spec


def test_mac_runtime_available_returns_bool():
    assert isinstance(mac_runtime_available(), bool)


def test_parse_hotkey_spec_basic():
    binding = parse_hotkey_spec("ctrl+option+p")
    assert binding is not None
    keycode, mods = binding
    assert keycode == 35
    assert mods == {"control", "option"}


def test_parse_hotkey_spec_aliases():
    binding = parse_hotkey_spec("cmd+shift+z")
    assert binding is not None
    keycode, mods = binding
    assert keycode == 6
    assert mods == {"command", "shift"}


def test_parse_hotkey_spec_invalid():
    assert parse_hotkey_spec("ctrl+foo+bar") is None
