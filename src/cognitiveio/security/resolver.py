from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from cognitiveio.security.aliases import replace_secret_aliases
from cognitiveio.security.vault import CompositeSecretProvider, EnvSecretProvider, SecretProvider

SecretAccessHook = Callable[[str, str, str], None]


@dataclass
class _CacheItem:
    value: str
    expires_at: float
    provider_name: str


class SecretResolver:
    def __init__(
        self,
        provider: Optional[SecretProvider] = None,
        cache_ttl_seconds: float = 60.0,
        on_access: Optional[SecretAccessHook] = None,
    ):
        if provider is None:
            provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
        self.provider = provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.on_access = on_access
        self._cache: Dict[str, _CacheItem] = {}

    def _now(self) -> float:
        return time.time()

    def resolve_alias(self, alias: str) -> Optional[str]:
        now = self._now()
        item = self._cache.get(alias)
        if item and item.expires_at >= now:
            if self.on_access:
                self.on_access(alias, item.provider_name, "cache_hit")
            return item.value

        provider_name = getattr(self.provider, "name", "unknown")
        if isinstance(self.provider, CompositeSecretProvider):
            value, provider_name = self.provider.get_secret_with_provider(alias)
        else:
            value = self.provider.get_secret(alias)

        status = "resolved" if value is not None else "missing"
        if self.on_access:
            self.on_access(alias, provider_name, status)

        if value is None:
            self._cache.pop(alias, None)
            return None

        self._cache[alias] = _CacheItem(
            value=value,
            expires_at=now + max(1.0, self.cache_ttl_seconds),
            provider_name=provider_name,
        )
        return value

    def resolve_text(self, text: str) -> Tuple[str, list[str]]:
        return replace_secret_aliases(text, resolver=self.resolve_alias)
