"""Unit tests for fm_secret_scanner.py -- tests pure Python helpers and fail-closed behavior.

The FM SDK is NOT available in test environments. scan_with_fm() returns
FMScanResult(detected=False) when the SDK is missing -- this IS correct behavior
and is tested as such.

All helpers (_build_sanitized_prompt, _mask_high_entropy_tokens, _looks_high_entropy,
_parse_fm_output) are pure Python and are fully exercised with real inputs.
"""
from __future__ import annotations

import asyncio

import pytest

from cognitiveio.ai.fm_secret_scanner import (
    FMScanResult,
    SecretSpan,
    _build_sanitized_prompt,
    _looks_high_entropy,
    _mask_high_entropy_tokens,
    _parse_fm_output,
    scan_with_fm,
)


# ---------------------------------------------------------------------------
# Minimal data carrier for _parse_fm_output tests.
# This is NOT a mock -- it is a plain namespace object that carries the same
# attributes the FM SDK would return.  _parse_fm_output accepts `object` type
# and reads attributes via getattr, so any object with the right attrs works.
# ---------------------------------------------------------------------------
class _FakeOut:
    """Minimal attribute carrier for _parse_fm_output tests."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ===================================================================
# 1. Dataclass construction tests
# ===================================================================


class TestDataclasses:
    def test_fm_scan_result_defaults(self):
        """FMScanResult() has detected=False, empty spans list, empty reason_tag."""
        result = FMScanResult(detected=False)
        assert result.detected is False
        assert result.spans == []
        assert result.reason_tag == ""

    def test_secret_span_creation(self):
        """SecretSpan stores start, end, category, confidence correctly."""
        span = SecretSpan(0, 10, "api_key", 0.8)
        assert span.start == 0
        assert span.end == 10
        assert span.category == "api_key"
        assert span.confidence == pytest.approx(0.8)


# ===================================================================
# 2. scan_with_fm -- fail-closed behaviour when SDK is missing
# ===================================================================


class TestScanWithFM:
    def test_scan_with_fm_fail_closed(self):
        """scan_with_fm returns detected=False (fail-closed) when FM cannot classify.

        On machines without the FM SDK: reason_tag='fm_unavailable:sdk_missing'.
        On machines with the SDK but without the Neural Engine runtime:
        reason_tag may be 'fm_unavailable:*', 'fm_error', or 'fm_timeout'.
        Both are correct fail-closed behavior.
        """
        result = asyncio.run(scan_with_fm("OPENAI_API_KEY=sk-abc123def456"))
        assert result.detected is False
        assert any(tag in result.reason_tag for tag in ("fm_unavailable", "fm_error", "fm_timeout"))
        assert result.spans == []

    def test_scan_with_fm_empty_text(self):
        """Empty string input still returns a valid FMScanResult."""
        result = asyncio.run(scan_with_fm(""))
        assert result.detected is False
        assert isinstance(result, FMScanResult)

    def test_scan_with_fm_respects_timeout(self):
        """scan_with_fm with a very short timeout still returns without hanging."""
        result = asyncio.run(scan_with_fm("some text", timeout_seconds=0.01))
        assert result.detected is False
        # Should return quickly because SDK is missing (before timeout matters)
        assert isinstance(result, FMScanResult)


# ===================================================================
# 3. _looks_high_entropy -- character-class heuristic
# ===================================================================


class TestLooksHighEntropy:
    def test_looks_high_entropy_api_key(self):
        """A string with upper, lower, digit, and symbol chars (4 classes) -> True."""
        # sk- has symbol(-), upper(A-F), lower(a-z,s,k), digit(1-9)
        assert _looks_high_entropy("sk-ABCDef123456789xyz") is True

    def test_looks_high_entropy_normal_word(self):
        """A plain lowercase word has only 1 class -> False."""
        assert _looks_high_entropy("hello") is False

    def test_looks_high_entropy_short_mixed(self):
        """Short token with all 4 classes -> True (>=3 classes)."""
        # a=lower, B=upper, 1=digit, !=symbol
        assert _looks_high_entropy("aB1!") is True

    def test_looks_high_entropy_digits_only(self):
        """All-digit string has only 1 class -> False."""
        assert _looks_high_entropy("1234567890") is False

    def test_looks_high_entropy_two_classes(self):
        """A string with exactly 2 classes (upper + lower) -> False."""
        assert _looks_high_entropy("abcDEF") is False


# ===================================================================
# 4. _mask_high_entropy_tokens
# ===================================================================


class TestMaskHighEntropyTokens:
    def test_mask_high_entropy_tokens_masks_long(self):
        """A long high-entropy token is masked to first2...last2[Nc] format."""
        # The token after = is: sk-ABCDEFghij123456789xyz  (24 chars, 4 classes)
        line = "key=sk-ABCDEFghij123456789xyz"
        result = _mask_high_entropy_tokens(line)
        # The full secret should NOT appear in the output
        assert "sk-ABCDEFghij123456789xyz" not in result
        # The masked format includes the first 2 and last 2 characters
        assert "..." in result
        # Check that the [Nc] count format is present
        assert "c]" in result

    def test_mask_high_entropy_tokens_keeps_short(self):
        """Short low-entropy tokens are preserved unchanged."""
        line = "hello world"
        result = _mask_high_entropy_tokens(line)
        assert result == "hello world"

    def test_mask_high_entropy_tokens_preserves_delimiters(self):
        """Delimiters like = and spaces are preserved in the output."""
        line = "key=sk-ABCDEFghij123456789xyz value"
        result = _mask_high_entropy_tokens(line)
        # The = delimiter should still be present
        assert "=" in result
        # The word 'value' should be intact
        assert "value" in result
        # The word 'key' should be intact
        assert "key" in result


# ===================================================================
# 5. _build_sanitized_prompt
# ===================================================================


class TestBuildSanitizedPrompt:
    def test_build_sanitized_prompt_masks_secrets(self):
        """A long high-entropy secret value should be masked in the prompt."""
        secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        text = f"key={secret}"
        prompt = _build_sanitized_prompt(text)
        # The full raw secret should NOT appear in the prompt
        assert secret not in prompt
        # The prompt should still contain the system instruction text
        assert "secret-detection classifier" in prompt

    def test_build_sanitized_prompt_preserves_safe_text(self):
        """Safe (non-secret) text passes through to the prompt unchanged."""
        prompt = _build_sanitized_prompt("Hello world")
        assert "Hello world" in prompt

    def test_build_sanitized_prompt_detects_keywords(self):
        """Context keywords like 'password' are listed in the keywords section."""
        prompt = _build_sanitized_prompt("password=secret123")
        assert "password" in prompt
        # The keyword hint section should be present
        assert "Context keywords detected" in prompt

    def test_build_sanitized_prompt_multiline(self):
        """Multiline input is handled correctly with all lines processed."""
        text = "line1=safe_value\npassword=sk-ABCDEF1234567890ghijklmnop\nline3=ok"
        prompt = _build_sanitized_prompt(text)
        # The raw secret should be masked
        assert "sk-ABCDEF1234567890ghijklmnop" not in prompt
        # Safe lines should be present
        assert "line1" in prompt
        assert "line3" in prompt
        # password keyword should be detected
        assert "Context keywords detected" in prompt
        assert "password" in prompt


# ===================================================================
# 6. _parse_fm_output -- structured output parsing
# ===================================================================


class TestParseFMOutput:
    def test_parse_fm_output_valid_indices(self):
        """Valid segment indices produce correct SecretSpan objects."""
        out = _FakeOut(
            has_secrets=True,
            categories=["api_key"],
            segment_indices=[[0, 10]],
        )
        spans = _parse_fm_output(out, text_length=50)
        assert len(spans) == 1
        assert spans[0].start == 0
        assert spans[0].end == 10
        assert spans[0].category == "api_key"
        assert spans[0].confidence == pytest.approx(0.8)

    def test_parse_fm_output_invalid_indices(self):
        """Inverted indices (start > end) produce an empty span list."""
        out = _FakeOut(
            has_secrets=True,
            categories=["api_key"],
            segment_indices=[[20, 5]],
        )
        spans = _parse_fm_output(out, text_length=50)
        assert spans == []

    def test_parse_fm_output_clamps_bounds(self):
        """End index beyond text_length is clamped to text_length."""
        out = _FakeOut(
            has_secrets=True,
            categories=["api_key"],
            segment_indices=[[0, 999]],
        )
        spans = _parse_fm_output(out, text_length=10)
        assert len(spans) == 1
        assert spans[0].start == 0
        assert spans[0].end == 10

    def test_parse_fm_output_empty_output(self):
        """An object with no relevant attributes produces an empty list."""
        out = _FakeOut()
        spans = _parse_fm_output(out, text_length=50)
        assert spans == []
