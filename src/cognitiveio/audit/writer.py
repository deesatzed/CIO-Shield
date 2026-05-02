"""Dual-mode audit writer for CIO-II Shield.

Corporate mode: writes via subprocess to privileged Swift helper
  → /Library/Application Support/CognitiveIO/audit/
Individual mode: writes directly to ~/.cognitiveio/audit/

Audit files are daily JSONL with HMAC signatures for tamper detection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cognitiveio.audit.events import AuditEvent
from cognitiveio.policy.corporate import PolicyConstraints


# ---------------------------------------------------------------------------
# Helper path
# ---------------------------------------------------------------------------

_HELPER_PATH = Path("/Library/PrivilegedHelperTools/com.cognitiveio.audit-helper")


# ---------------------------------------------------------------------------
# Audit backends
# ---------------------------------------------------------------------------

class LocalAuditBackend:
    """Individual-mode backend: writes to ~/.cognitiveio/audit/ (user-owned)."""

    def __init__(self, audit_dir: Optional[Path] = None):
        self._audit_dir = audit_dir or (Path.home() / ".cognitiveio" / "audit")
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        # HMAC key derived from machine identity (individual mode — user-owned).
        self._hmac_key = self._derive_hmac_key()
        self._manifest_path = self._audit_dir / "manifest.json"

    @staticmethod
    def _derive_hmac_key() -> bytes:
        """Derive a stable HMAC key from machine identity."""
        import platform
        machine_id = f"{platform.node()}:{os.getuid()}"
        return hashlib.sha256(machine_id.encode("utf-8")).digest()

    def _today_file(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._audit_dir / f"{today}.jsonl"

    def append(self, event_json: str) -> None:
        """Append a single JSONL line with HMAC signature."""
        sig = hmac.new(self._hmac_key, event_json.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        line = f"{event_json}\t{sig}\n"
        filepath = self._today_file()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line)
        self._update_manifest(filepath)

    def _update_manifest(self, filepath: Path) -> None:
        """Update manifest.json with file checksums."""
        manifest: Dict[str, Any] = {}
        if self._manifest_path.exists():
            try:
                manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = {}

        name = filepath.name
        try:
            content = filepath.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            manifest[name] = {
                "checksum": checksum,
                "size": len(content),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except OSError:
            pass

        try:
            self._manifest_path.write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def verify_integrity(self, filename: str) -> bool:
        """Check if a file's checksum matches the manifest."""
        if not self._manifest_path.exists():
            return False
        try:
            manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        entry = manifest.get(filename)
        if not entry:
            return False

        filepath = self._audit_dir / filename
        if not filepath.exists():
            return False

        content = filepath.read_bytes()
        actual_checksum = hashlib.sha256(content).hexdigest()
        return actual_checksum == entry.get("checksum", "")

    @property
    def audit_dir(self) -> Path:
        return self._audit_dir

    def file_count(self) -> int:
        """Count JSONL audit files."""
        return len(list(self._audit_dir.glob("*.jsonl")))

    def last_write_time(self) -> Optional[float]:
        """Return mtime of most recent JSONL file."""
        files = sorted(self._audit_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            return files[0].stat().st_mtime
        return None


class XPCAuditBackend:
    """Corporate-mode backend: writes via subprocess to privileged Swift helper.

    The helper writes to /Library/Application Support/CognitiveIO/audit/
    which is root-owned and append-only. The helper also handles AES-256-GCM
    encryption and HMAC signing.

    Communication: JSON line protocol over stdin/stdout.
    """

    def __init__(self, helper_path: Optional[Path] = None):
        self._helper_path = helper_path or _HELPER_PATH
        self._proc: Optional[subprocess.Popen] = None
        self._start_helper()

    def _start_helper(self) -> None:
        """Start the privileged helper subprocess."""
        if not self._helper_path.exists():
            return
        try:
            self._proc = subprocess.Popen(
                [str(self._helper_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=1,  # line-buffered
            )
        except (OSError, subprocess.SubprocessError):
            self._proc = None

    @property
    def is_available(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def append(self, event_json: str) -> None:
        """Send event to the privileged helper for encrypted append."""
        if not self.is_available or self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write(event_json.encode("utf-8") + b"\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self._proc = None

    @property
    def audit_dir(self) -> Path:
        return Path("/Library/Application Support/CognitiveIO/audit")

    def file_count(self) -> int:
        audit_dir = self.audit_dir
        if not audit_dir.exists():
            return 0
        return len(list(audit_dir.glob("**/*.jsonl")))

    def last_write_time(self) -> Optional[float]:
        audit_dir = self.audit_dir
        if not audit_dir.exists():
            return None
        files = sorted(audit_dir.glob("**/*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            return files[0].stat().st_mtime
        return None

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


# ---------------------------------------------------------------------------
# AuditWriter (unified interface)
# ---------------------------------------------------------------------------

class AuditWriter:
    """Dual-mode audit writer that selects backend based on policy tier.

    Corporate mode: XPC to privileged helper (root-owned, encrypted, tamper-proof)
    Individual mode: Local JSONL files (user-owned, HMAC-signed)
    """

    def __init__(self, policy: PolicyConstraints, audit_dir: Optional[Path] = None):
        self._policy = policy
        if policy.is_corporate and _HELPER_PATH.exists():
            self._backend: LocalAuditBackend | XPCAuditBackend = XPCAuditBackend()
        else:
            self._backend = LocalAuditBackend(audit_dir=audit_dir)

    def log_event(self, event: AuditEvent) -> None:
        """Validate and append an audit event."""
        event_json = event.to_jsonl()
        self._backend.append(event_json)

    @property
    def audit_dir(self) -> Path:
        return self._backend.audit_dir

    @property
    def tier(self) -> str:
        return self._policy.tier

    def file_count(self) -> int:
        return self._backend.file_count()

    def last_write_time(self) -> Optional[float]:
        return self._backend.last_write_time()

    def verify_integrity(self, filename: str) -> bool:
        """Verify file integrity (only available for local backend)."""
        if isinstance(self._backend, LocalAuditBackend):
            return self._backend.verify_integrity(filename)
        return False

    def close(self) -> None:
        if isinstance(self._backend, XPCAuditBackend):
            self._backend.close()
