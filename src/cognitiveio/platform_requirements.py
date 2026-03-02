from __future__ import annotations

from dataclasses import dataclass, field
import platform
import re
import shutil
import subprocess
from typing import Callable, List, Optional, Sequence, Tuple


CommandRunner = Callable[[Sequence[str]], Tuple[bool, str, str]]
FMProbe = Callable[[], Tuple[bool, str]]


@dataclass(frozen=True)
class PlatformRequirementConfig:
    min_macos: Tuple[int, int] = (26, 0)
    min_xcode: Tuple[int, int] = (26, 0)
    require_apple_silicon: bool = True
    require_full_xcode: bool = True
    require_fm_runtime_available: bool = True


@dataclass(frozen=True)
class RequirementCheck:
    name: str
    required: str
    current: str
    passed: bool
    details: str = ""


@dataclass
class RequirementReport:
    checks: List[RequirementCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(row.passed for row in self.checks)


def _default_runner(args: Sequence[str]) -> Tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "", "not found"
    except Exception as exc:
        return False, "", str(exc)

    ok = proc.returncode == 0
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return ok, out, err


def _parse_major_minor(raw: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"(\d+)\.(\d+)", raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _version_gte(current: Tuple[int, int], minimum: Tuple[int, int]) -> bool:
    return current >= minimum


def _default_fm_probe() -> Tuple[bool, str]:
    try:
        import apple_fm_sdk as fm
    except Exception as exc:
        return False, f"sdk_import_error:{exc.__class__.__name__}"

    try:
        model = fm.SystemLanguageModel(use_case=fm.SystemLanguageModelUseCase.GENERAL)
        ok, reason = model.is_available()
        if ok:
            return True, "available"
        return False, f"unavailable:{reason}"
    except Exception as exc:
        return False, f"probe_error:{exc.__class__.__name__}"


def evaluate_platform_requirements(
    *,
    config: PlatformRequirementConfig = PlatformRequirementConfig(),
    runner: CommandRunner = _default_runner,
    fm_probe: FMProbe = _default_fm_probe,
    system_name: Optional[str] = None,
    machine_arch: Optional[str] = None,
) -> RequirementReport:
    checks: List[RequirementCheck] = []

    system = system_name or platform.system()
    machine = machine_arch or platform.machine()
    checks.append(
        RequirementCheck(
            name="Operating system",
            required="macOS (Darwin)",
            current=system or "unknown",
            passed=system == "Darwin",
        )
    )

    if config.require_apple_silicon:
        checks.append(
            RequirementCheck(
                name="Apple chip architecture",
                required="arm64 (Apple Silicon)",
                current=machine or "unknown",
                passed=(system == "Darwin" and machine == "arm64"),
            )
        )

    macos_current = "unknown"
    macos_pass = False
    macos_details = "platform not Darwin"
    if system == "Darwin":
        ok, out, err = runner(["sw_vers", "-productVersion"])
        if ok and out:
            parsed = _parse_major_minor(out)
            macos_current = out
            if parsed is not None:
                macos_pass = _version_gte(parsed, config.min_macos)
                macos_details = ""
            else:
                macos_details = "unable to parse version"
        else:
            macos_details = err or "sw_vers failed"
    checks.append(
        RequirementCheck(
            name="macOS version",
            required=f">= {config.min_macos[0]}.{config.min_macos[1]}",
            current=macos_current,
            passed=macos_pass,
            details=macos_details,
        )
    )

    xcode_current = "not installed"
    xcode_pass = False
    xcode_details = ""
    if system == "Darwin":
        xcode_in_path = shutil.which("xcodebuild")
        if xcode_in_path is None:
            xcode_details = "xcodebuild not found in PATH"
        else:
            ok, out, err = runner(["xcodebuild", "-version"])
            if ok and out:
                first = out.splitlines()[0] if out.splitlines() else out
                xcode_current = first
                parsed = _parse_major_minor(first)
                if parsed is not None:
                    xcode_pass = _version_gte(parsed, config.min_xcode)
                else:
                    xcode_details = "unable to parse xcodebuild output"
            else:
                xcode_details = err or "xcodebuild -version failed"
    checks.append(
        RequirementCheck(
            name="Xcode version",
            required=f">= {config.min_xcode[0]}.{config.min_xcode[1]}",
            current=xcode_current,
            passed=xcode_pass,
            details=xcode_details,
        )
    )

    if config.require_full_xcode:
        dev_path = "unknown"
        dev_pass = False
        dev_details = "platform not Darwin"
        if system == "Darwin":
            ok, out, err = runner(["xcode-select", "-p"])
            if ok and out:
                dev_path = out
                dev_pass = "Xcode.app/Contents/Developer" in out and "CommandLineTools" not in out
                if not dev_pass:
                    dev_details = "active developer dir is not full Xcode"
                else:
                    dev_details = ""
            else:
                dev_details = err or "xcode-select -p failed"
        checks.append(
            RequirementCheck(
                name="Active developer directory",
                required="Full Xcode path (not CommandLineTools)",
                current=dev_path,
                passed=dev_pass,
                details=dev_details,
            )
        )

    if config.require_fm_runtime_available:
        fm_current = "not checked"
        fm_pass = False
        fm_details = ""
        if system == "Darwin" and (not config.require_apple_silicon or machine == "arm64"):
            fm_pass, fm_info = fm_probe()
            fm_current = "available" if fm_pass else "unavailable"
            fm_details = fm_info
        else:
            fm_current = "unsupported platform"
            fm_details = "requires macOS Apple Silicon"
        checks.append(
            RequirementCheck(
                name="Apple FM runtime availability",
                required="SystemLanguageModel available",
                current=fm_current,
                passed=fm_pass,
                details=fm_details,
            )
        )

    return RequirementReport(checks=checks)

