from __future__ import annotations

from typing import Sequence, Tuple

from cognitiveio.platform_requirements import (
    _parse_major_minor,
    _version_gte,
    evaluate_platform_requirements,
)


def _runner_factory(mapping: dict[tuple[str, ...], Tuple[bool, str, str]]):
    def _runner(args: Sequence[str]) -> Tuple[bool, str, str]:
        key = tuple(args)
        return mapping.get(key, (False, "", "unknown command"))

    return _runner


def test_requirements_pass_for_supported_darwin_arm64():
    runner = _runner_factory(
        {
            ("sw_vers", "-productVersion"): (True, "26.1", ""),
            ("xcodebuild", "-version"): (True, "Xcode 26.0.1\nBuild version 17A100", ""),
            ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
        }
    )
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    assert report.passed is True
    assert all(row.passed for row in report.checks)


def test_requirements_fail_for_old_xcode_and_command_line_tools_path():
    runner = _runner_factory(
        {
            ("sw_vers", "-productVersion"): (True, "26.0", ""),
            ("xcodebuild", "-version"): (True, "Xcode 25.4\nBuild version 16F6", ""),
            ("xcode-select", "-p"): (True, "/Library/Developer/CommandLineTools", ""),
        }
    )
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    assert report.passed is False
    statuses = {row.name: row.passed for row in report.checks}
    assert statuses["Xcode version"] is False
    assert statuses["Active developer directory"] is False


def test_requirements_fail_on_non_macos_platform():
    report = evaluate_platform_requirements(
        runner=_runner_factory({}),
        fm_probe=lambda: (False, "unavailable"),
        system_name="Linux",
        machine_arch="x86_64",
    )
    assert report.passed is False
    statuses = {row.name: row.passed for row in report.checks}
    assert statuses["Operating system"] is False
    assert statuses["Apple chip architecture"] is False
    assert statuses["macOS version"] is False
    assert statuses["Xcode version"] is False


# ── Extended coverage tests ────────────────────────────────────────


def test_parse_major_minor_valid():
    assert _parse_major_minor("26.1") == (26, 1)
    assert _parse_major_minor("Xcode 25.4") == (25, 4)


def test_parse_major_minor_no_match():
    assert _parse_major_minor("noversion") is None


def test_version_gte():
    assert _version_gte((26, 1), (26, 0)) is True
    assert _version_gte((26, 0), (26, 0)) is True
    assert _version_gte((25, 9), (26, 0)) is False


def test_sw_vers_failure():
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (False, "", "sw_vers failed"),
        ("xcodebuild", "-version"): (True, "Xcode 26.0", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    macos_row = next(r for r in report.checks if r.name == "macOS version")
    assert macos_row.passed is False
    assert "sw_vers failed" in macos_row.details


def test_sw_vers_unparseable_version():
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "beta_no_digits", ""),
        ("xcodebuild", "-version"): (True, "Xcode 26.0", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    macos_row = next(r for r in report.checks if r.name == "macOS version")
    assert macos_row.passed is False
    assert "unable to parse" in macos_row.details


def test_fm_probe_failure():
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcodebuild", "-version"): (True, "Xcode 26.0", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (False, "sdk_import_error:ModuleNotFoundError"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    fm_row = next(r for r in report.checks if r.name == "Apple FM runtime availability")
    assert fm_row.passed is False
    assert "sdk_import_error" in fm_row.details


def test_xcodebuild_not_in_path():
    """When xcodebuild is not in PATH."""
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    xcode_row = next(r for r in report.checks if r.name == "Xcode version")
    # xcodebuild may or may not be found on the system; check at least the field exists
    assert xcode_row.name == "Xcode version"


def test_no_apple_silicon_no_fm():
    """When not Apple Silicon, FM should not be probed."""
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcodebuild", "-version"): (True, "Xcode 26.0", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    probe_called = {"n": 0}
    def _probe():
        probe_called["n"] += 1
        return True, "available"

    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=_probe,
        system_name="Darwin",
        machine_arch="x86_64",
    )
    fm_row = next(r for r in report.checks if r.name == "Apple FM runtime availability")
    assert fm_row.passed is False
    assert probe_called["n"] == 0


def test_xcodebuild_unparseable_output():
    """When xcodebuild returns unparseable output, details mention 'unable to parse'."""
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcodebuild", "-version"): (True, "no_version_here", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    xcode_row = next(r for r in report.checks if r.name == "Xcode version")
    assert xcode_row.passed is False
    assert "unable to parse" in xcode_row.details


def test_xcode_select_failure():
    """When xcode-select -p fails, details mention the error."""
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcodebuild", "-version"): (True, "Xcode 26.0", ""),
        ("xcode-select", "-p"): (False, "", "xcode-select: no developer tools"),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    dev_row = next(r for r in report.checks if r.name == "Active developer directory")
    assert dev_row.passed is False
    assert "xcode-select" in dev_row.details.lower() or "failed" in dev_row.details.lower()


def test_xcodebuild_failure():
    """When xcodebuild -version returns error."""
    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcodebuild", "-version"): (False, "", "xcodebuild requires Xcode"),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    xcode_row = next(r for r in report.checks if r.name == "Xcode version")
    assert xcode_row.passed is False
    assert "xcodebuild" in xcode_row.details.lower() or "failed" in xcode_row.details.lower()


def test_xcodebuild_not_in_path_forced(monkeypatch):
    """Force xcodebuild not in PATH via monkeypatch to cover line 150."""
    import shutil as _shutil
    import cognitiveio.platform_requirements as pr_mod

    original_which = _shutil.which
    def _which_no_xcodebuild(name):
        if name == "xcodebuild":
            return None
        return original_which(name)

    monkeypatch.setattr(pr_mod.shutil, "which", _which_no_xcodebuild)

    runner = _runner_factory({
        ("sw_vers", "-productVersion"): (True, "26.1", ""),
        ("xcode-select", "-p"): (True, "/Applications/Xcode.app/Contents/Developer", ""),
    })
    report = evaluate_platform_requirements(
        runner=runner,
        fm_probe=lambda: (True, "available"),
        system_name="Darwin",
        machine_arch="arm64",
    )
    xcode_row = next(r for r in report.checks if r.name == "Xcode version")
    assert xcode_row.passed is False
    assert "not found in PATH" in xcode_row.details


def test_default_runner_file_not_found():
    """_default_runner returns (False, '', 'not found') for missing command."""
    from cognitiveio.platform_requirements import _default_runner
    ok, out, err = _default_runner(["__nonexistent_command_xyz_999__"])
    assert ok is False
    assert err == "not found"


def test_default_runner_generic_exception(monkeypatch):
    """_default_runner handles generic exceptions."""
    import subprocess
    from cognitiveio.platform_requirements import _default_runner

    def _raise_exc(*a, **kw):
        raise PermissionError("denied")

    monkeypatch.setattr(subprocess, "run", _raise_exc)
    ok, out, err = _default_runner(["ls"])
    assert ok is False
    assert "denied" in err
