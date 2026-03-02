from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

SECRET_ALIAS_RE = re.compile(r"\{\{SECRET:([A-Z0-9_]{3,64})\}\}")


def contains_secret_alias(text: str) -> bool:
    return bool(SECRET_ALIAS_RE.search(text))


def extract_secret_aliases(text: str) -> List[str]:
    return list(dict.fromkeys(SECRET_ALIAS_RE.findall(text)))


def replace_secret_aliases(
    text: str,
    resolver: Callable[[str], Optional[str]],
) -> Tuple[str, List[str]]:
    unresolved: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        alias = match.group(1)
        value = resolver(alias)
        if value is None:
            unresolved.append(alias)
            return match.group(0)
        return value

    replaced = SECRET_ALIAS_RE.sub(_replace, text)
    return replaced, unresolved
