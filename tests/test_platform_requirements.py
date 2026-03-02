from __future__ import annotations

from typing import Sequence, Tuple

from cognitiveio.platform_requirements import evaluate_platform_requirements


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
