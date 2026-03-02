from cognitiveio.security.redaction import redact_payload, redact_text


def test_redact_text_hides_alias_and_secret_values():
    raw = "token={{SECRET:OPENAI_API_KEY}} api_key=sk-abcdefghijklmnopqrstuvwx"
    out = redact_text(raw)
    assert "{{SECRET:OPENAI_API_KEY}}" not in out
    assert "[REDACTED_SECRET]" in out
    assert "sk-abcdefghijklmnopqrstuvwx" not in out


def test_redact_payload_hides_sensitive_keys():
    payload = {
        "candidate_id": "c1",
        "token": "secret-value",
        "nested": {"api_key": "sk-example", "note": "ok"},
    }
    out = redact_payload(payload)
    assert out["token"] == "[REDACTED_SECRET]"
    assert out["nested"]["api_key"] == "[REDACTED_SECRET]"
    assert out["nested"]["note"] == "ok"
