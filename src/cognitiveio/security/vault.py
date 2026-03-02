from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Tuple


class SecretProvider(Protocol):
    name: str

    def get_secret(self, alias: str) -> Optional[str]:
        ...


@dataclass
class EnvSecretProvider:
    name: str = "env"
    prefix: str = "COGNITIVEIO_SECRET_"

    def get_secret(self, alias: str) -> Optional[str]:
        key = f"{self.prefix}{alias}"
        value = os.getenv(key)
        if value:
            return value
        return os.getenv(alias)


@dataclass
class CompositeSecretProvider:
    providers: Tuple[SecretProvider, ...]
    name: str = "composite"

    @classmethod
    def from_iterable(cls, providers: Iterable[SecretProvider]) -> "CompositeSecretProvider":
        return cls(tuple(providers))

    def get_secret(self, alias: str) -> Optional[str]:
        for provider in self.providers:
            value = provider.get_secret(alias)
            if value:
                return value
        return None

    def get_secret_with_provider(self, alias: str) -> tuple[Optional[str], str]:
        for provider in self.providers:
            value = provider.get_secret(alias)
            if value:
                return value, provider.name
        return None, "none"
