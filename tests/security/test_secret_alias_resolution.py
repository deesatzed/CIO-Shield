from cognitiveio.security.resolver import SecretResolver
from cognitiveio.security.vault import CompositeSecretProvider, EnvSecretProvider


def test_secret_alias_resolves_from_env(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_STRIPE_API_KEY", "sk_test_12345")
    resolver = SecretResolver(
        provider=CompositeSecretProvider.from_iterable([EnvSecretProvider()]),
        cache_ttl_seconds=60.0,
    )
    resolved, unresolved = resolver.resolve_text("token={{SECRET:STRIPE_API_KEY}}")
    assert unresolved == []
    assert resolved == "token=sk_test_12345"


def test_secret_alias_missing_returns_unresolved():
    resolver = SecretResolver(
        provider=CompositeSecretProvider.from_iterable([EnvSecretProvider()]),
        cache_ttl_seconds=60.0,
    )
    resolved, unresolved = resolver.resolve_text("{{SECRET:MISSING_ALIAS}}")
    assert resolved == "{{SECRET:MISSING_ALIAS}}"
    assert unresolved == ["MISSING_ALIAS"]
