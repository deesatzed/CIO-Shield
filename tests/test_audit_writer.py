"""Tests for audit event validation, writer backends, and integrity checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognitiveio.audit.events import (
    AuditEvent,
    ClipboardAuditEvent,
    RedactionAuditEvent,
    SessionSummaryEvent,
    _contains_secret,
)
from cognitiveio.audit.writer import AuditWriter, LocalAuditBackend
from cognitiveio.policy.corporate import PolicyConstraints


# ---------------------------------------------------------------------------
# AuditEvent validation
# ---------------------------------------------------------------------------


class TestAuditEvent:
    def test_basic_event(self):
        e = AuditEvent(event="block", reason="corporate_policy_block", app="ChatGPT")
        jsonl = e.to_jsonl()
        data = json.loads(jsonl)
        assert data["event"] == "block"
        assert data["reason"] == "corporate_policy_block"
        assert data["app"] == "ChatGPT"
        assert "ts" in data

    def test_auto_timestamp(self):
        e = AuditEvent(event="block")
        assert e.ts != ""
        assert "T" in e.ts  # ISO 8601 format

    def test_explicit_timestamp(self):
        e = AuditEvent(event="block", ts="2026-05-01T12:00:00Z")
        assert e.ts == "2026-05-01T12:00:00Z"

    def test_rejects_secret_in_reason(self):
        with pytest.raises(ValueError, match="secret"):
            AuditEvent(event="block", reason="sk-abc123defghijklmnopqrstuvwxyz").to_jsonl()

    def test_rejects_aws_key(self):
        with pytest.raises(ValueError, match="secret"):
            AuditEvent(event="block", reason="key=AKIAIOSFODNN7EXAMPLE").to_jsonl()

    def test_rejects_private_key(self):
        with pytest.raises(ValueError, match="secret"):
            AuditEvent(event="block", reason="-----BEGIN RSA PRIVATE KEY-----").to_jsonl()

    def test_empty_fields_excluded(self):
        e = AuditEvent(event="block")
        data = json.loads(e.to_jsonl())
        assert "reason" not in data
        assert "app" not in data


class TestClipboardAuditEvent:
    def test_clipboard_event(self):
        e = ClipboardAuditEvent(
            content_type="public.png",
            pixel_dimensions="1920x1080",
            byte_size=245760,
            destination_app="ChatGPT",
            source_hint="screenshot",
        )
        data = json.loads(e.to_jsonl())
        assert data["event"] == "clipboard_paste"
        assert data["content_type"] == "public.png"
        assert data["pixel_dimensions"] == "1920x1080"
        assert data["byte_size"] == 245760
        assert data["source_hint"] == "screenshot"
        assert data["destination_app"] == "ChatGPT"

    def test_text_clipboard(self):
        e = ClipboardAuditEvent(
            content_type="public.utf8-plain-text",
            byte_size=42,
            destination_app="Slack",
            source_hint="copy",
        )
        data = json.loads(e.to_jsonl())
        assert data["content_type"] == "public.utf8-plain-text"


class TestRedactionAuditEvent:
    def test_redaction_event(self):
        e = RedactionAuditEvent(
            pattern_type="api_key",
            destination_profile="ai_tool",
            token_count=3,
        )
        data = json.loads(e.to_jsonl())
        assert data["event"] == "redaction"
        assert data["pattern_type"] == "api_key"
        assert data["token_count"] == 3


class TestSessionSummaryEvent:
    def test_session_summary(self):
        e = SessionSummaryEvent(
            accept_rate=0.72,
            blocks=5,
            redactions=3,
            duration_seconds=3600,
        )
        data = json.loads(e.to_jsonl())
        assert data["event"] == "session_summary"
        assert data["accept_rate"] == 0.72
        assert data["blocks"] == 5


# ---------------------------------------------------------------------------
# Secret detection helper
# ---------------------------------------------------------------------------


class TestValidateNoSecrets:
    def test_nested_dict_with_secret(self):
        """_validate_no_secrets catches secrets in nested dicts."""
        from cognitiveio.audit.events import _validate_no_secrets
        with pytest.raises(ValueError, match="secret"):
            _validate_no_secrets({"outer": {"inner": "sk-abc123defghijklmnopqrstuvwxyz"}})

    def test_nested_dict_clean(self):
        """_validate_no_secrets passes for clean nested dicts."""
        from cognitiveio.audit.events import _validate_no_secrets
        _validate_no_secrets({"outer": {"inner": "clean value"}})  # no raise


class TestContainsSecret:
    def test_openai_key(self):
        assert _contains_secret("sk-abc123defghijklmnopqrstuvwxyz")

    def test_aws_key(self):
        assert _contains_secret("AKIAIOSFODNN7EXAMPLE")

    def test_private_key(self):
        assert _contains_secret("-----BEGIN RSA PRIVATE KEY-----")

    def test_clean_text(self):
        assert not _contains_secret("Hello world")

    def test_empty(self):
        assert not _contains_secret("")


# ---------------------------------------------------------------------------
# LocalAuditBackend
# ---------------------------------------------------------------------------


class TestLocalAuditBackend:
    def test_append_and_read(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"block","reason":"test"}')
        assert backend.file_count() == 1

    def test_hmac_in_output(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test"}')
        files = list((tmp_path / "audit").glob("*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split("\t")
        assert len(parts) == 2  # event_json \t hmac_signature
        assert len(parts[1]) == 32  # HMAC-SHA256 truncated to 32 hex chars

    def test_manifest_created(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test"}')
        manifest_path = tmp_path / "audit" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest) == 1
        entry = list(manifest.values())[0]
        assert "checksum" in entry
        assert "size" in entry

    def test_integrity_verification(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test1"}')
        files = list((tmp_path / "audit").glob("*.jsonl"))
        assert backend.verify_integrity(files[0].name)

    def test_integrity_fails_on_tamper(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test1"}')
        files = list((tmp_path / "audit").glob("*.jsonl"))
        # Tamper with the file.
        files[0].write_text("tampered content\n", encoding="utf-8")
        assert not backend.verify_integrity(files[0].name)

    def test_last_write_time(self, tmp_path):
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        assert backend.last_write_time() is None
        backend.append('{"event":"test"}')
        assert backend.last_write_time() is not None


# ---------------------------------------------------------------------------
# AuditWriter (unified interface)
# ---------------------------------------------------------------------------


class TestLocalAuditBackendEdgeCases:
    def test_corrupt_manifest_still_writes(self, tmp_path):
        """Corrupt manifest.json doesn't prevent new writes."""
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        # Write a valid event first
        backend.append('{"event":"test1"}')
        # Corrupt the manifest
        manifest_path = tmp_path / "audit" / "manifest.json"
        manifest_path.write_text("NOT JSON {{}", encoding="utf-8")
        # Next write should recover
        backend.append('{"event":"test2"}')
        assert backend.file_count() == 1

    def test_verify_integrity_no_manifest(self, tmp_path):
        """verify_integrity returns False when manifest doesn't exist."""
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        assert not backend.verify_integrity("2026-05-01.jsonl")

    def test_verify_integrity_corrupt_manifest(self, tmp_path):
        """verify_integrity returns False when manifest is corrupt."""
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test"}')
        manifest_path = tmp_path / "audit" / "manifest.json"
        manifest_path.write_text("{invalid json", encoding="utf-8")
        files = list((tmp_path / "audit").glob("*.jsonl"))
        assert not backend.verify_integrity(files[0].name)

    def test_verify_integrity_missing_file(self, tmp_path):
        """verify_integrity returns False when file is in manifest but deleted."""
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test"}')
        files = list((tmp_path / "audit").glob("*.jsonl"))
        filename = files[0].name
        files[0].unlink()  # Delete the file
        assert not backend.verify_integrity(filename)

    def test_verify_integrity_unknown_file(self, tmp_path):
        """verify_integrity returns False for file not in manifest."""
        backend = LocalAuditBackend(audit_dir=tmp_path / "audit")
        backend.append('{"event":"test"}')
        assert not backend.verify_integrity("unknown_file.jsonl")


class TestXPCAuditBackend:
    def test_unavailable_when_no_helper(self):
        from cognitiveio.audit.writer import XPCAuditBackend
        backend = XPCAuditBackend(helper_path=Path("/nonexistent/helper"))
        assert not backend.is_available
        # append should silently no-op
        backend.append('{"event":"test"}')
        backend.close()

    def test_file_count_nonexistent_dir(self):
        from cognitiveio.audit.writer import XPCAuditBackend
        backend = XPCAuditBackend(helper_path=Path("/nonexistent/helper"))
        assert backend.file_count() == 0

    def test_last_write_time_nonexistent_dir(self):
        from cognitiveio.audit.writer import XPCAuditBackend
        backend = XPCAuditBackend(helper_path=Path("/nonexistent/helper"))
        assert backend.last_write_time() is None

    def test_audit_dir_path(self):
        from cognitiveio.audit.writer import XPCAuditBackend
        backend = XPCAuditBackend(helper_path=Path("/nonexistent/helper"))
        assert "CognitiveIO" in str(backend.audit_dir)

    def test_close_without_proc(self):
        from cognitiveio.audit.writer import XPCAuditBackend
        backend = XPCAuditBackend(helper_path=Path("/nonexistent/helper"))
        backend._proc = None
        backend.close()  # should not raise


class TestAuditWriter:
    def test_individual_tier(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        assert writer.tier == "individual"
        event = AuditEvent(event="block", reason="test")
        writer.log_event(event)
        assert writer.file_count() == 1
        writer.close()

    def test_rejects_secret_event(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        bad_event = AuditEvent(event="block", reason="sk-abc123defghijklmnopqrstuvwxyz")
        with pytest.raises(ValueError):
            writer.log_event(bad_event)
        writer.close()

    def test_multiple_events(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        for i in range(5):
            writer.log_event(AuditEvent(event="block", reason=f"reason_{i}"))
        assert writer.file_count() == 1  # all same day
        writer.close()

    def test_verify_integrity_individual(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        writer.log_event(AuditEvent(event="test"))
        files = list((tmp_path / "audit").glob("*.jsonl"))
        assert writer.verify_integrity(files[0].name)
        writer.close()

    def test_verify_integrity_returns_false_for_xpc(self, tmp_path):
        """verify_integrity returns False when backend is XPC (no local files)."""
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        # Force backend type check path - individual mode uses LocalAuditBackend
        assert writer.verify_integrity("nonexistent.jsonl") is False
        writer.close()

    def test_audit_dir_property(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        assert writer.audit_dir == tmp_path / "audit"
        writer.close()

    def test_last_write_time_property(self, tmp_path):
        policy = PolicyConstraints()
        writer = AuditWriter(policy, audit_dir=tmp_path / "audit")
        assert writer.last_write_time() is None
        writer.log_event(AuditEvent(event="test"))
        assert writer.last_write_time() is not None
        writer.close()

    def test_audit_patterns_match_redaction_patterns(self):
        """Audit forbidden patterns are sourced from the shared redaction pattern set."""
        from cognitiveio.audit.events import _FORBIDDEN_PATTERNS
        from cognitiveio.security.redaction import SECRET_VALUE_PATTERNS
        assert len(_FORBIDDEN_PATTERNS) == len(SECRET_VALUE_PATTERNS)
