"""Extended tests for security/vault.py and security/resolver.py to close coverage gaps."""
from cognitiveio.security.vault import CompositeSecretProvider, EnvSecretProvider
from cognitiveio.security.resolver import SecretResolver


# ── Vault tests ────────────────────────────────────────────────────

def test_env_secret_provider_prefixed(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_MY_KEY", "secret_val")
    provider = EnvSecretProvider()
    assert provider.get_secret("MY_KEY") == "secret_val"


def test_env_secret_provider_bare_fallback(monkeypatch):
    monkeypatch.delenv("COGNITIVEIO_SECRET_DIRECT_KEY", raising=False)
    monkeypatch.setenv("DIRECT_KEY", "bare_val")
    provider = EnvSecretProvider()
    assert provider.get_secret("DIRECT_KEY") == "bare_val"


def test_env_secret_provider_missing(monkeypatch):
    monkeypatch.delenv("COGNITIVEIO_SECRET_NONEXISTENT", raising=False)
    monkeypatch.delenv("NONEXISTENT", raising=False)
    provider = EnvSecretProvider()
    assert provider.get_secret("NONEXISTENT") is None


def test_composite_provider_returns_first_match(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_KEY1", "from_env")
    provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
    assert provider.get_secret("KEY1") == "from_env"


def test_composite_provider_returns_none_on_miss(monkeypatch):
    monkeypatch.delenv("COGNITIVEIO_SECRET_MISS", raising=False)
    monkeypatch.delenv("MISS", raising=False)
    provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
    assert provider.get_secret("MISS") is None


def test_composite_get_secret_with_provider_found(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_X", "val_x")
    provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
    value, name = provider.get_secret_with_provider("X")
    assert value == "val_x"
    assert name == "env"


def test_composite_get_secret_with_provider_not_found(monkeypatch):
    monkeypatch.delenv("COGNITIVEIO_SECRET_NOPE", raising=False)
    monkeypatch.delenv("NOPE", raising=False)
    provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
    value, name = provider.get_secret_with_provider("NOPE")
    assert value is None
    assert name == "none"


# ── Resolver tests ─────────────────────────────────────────────────

def test_resolver_cache_hit(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_CACHED", "cached_val")
    accessed = []
    resolver = SecretResolver(
        cache_ttl_seconds=300.0,
        on_access=lambda alias, prov, status: accessed.append((alias, status)),
    )
    # First call resolves
    v1 = resolver.resolve_alias("CACHED")
    assert v1 == "cached_val"
    assert accessed[-1] == ("CACHED", "resolved")

    # Second call hits cache
    v2 = resolver.resolve_alias("CACHED")
    assert v2 == "cached_val"
    assert accessed[-1] == ("CACHED", "cache_hit")


def test_resolver_cache_miss_logged(monkeypatch):
    monkeypatch.delenv("COGNITIVEIO_SECRET_ABSENT", raising=False)
    monkeypatch.delenv("ABSENT", raising=False)
    accessed = []
    resolver = SecretResolver(
        on_access=lambda alias, prov, status: accessed.append((alias, status)),
    )
    v = resolver.resolve_alias("ABSENT")
    assert v is None
    assert accessed[-1] == ("ABSENT", "missing")


def test_resolver_non_composite_provider():
    """When provider is a plain EnvSecretProvider (not Composite), code path differs."""
    provider = EnvSecretProvider()
    resolver = SecretResolver(provider=provider, cache_ttl_seconds=60.0)
    # This hits the non-composite branch in resolve_alias
    result = resolver.resolve_alias("NONEXISTENT_PLAIN")
    assert result is None


def test_resolver_default_provider():
    """When no provider is passed, defaults to CompositeSecretProvider."""
    resolver = SecretResolver()
    assert resolver.provider is not None


def test_resolver_resolve_text(monkeypatch):
    monkeypatch.setenv("COGNITIVEIO_SECRET_NAME", "Alice")
    resolver = SecretResolver()
    text, unresolved = resolver.resolve_text("Hello {{SECRET:NAME}}")
    assert text == "Hello Alice"
    assert unresolved == []
