from __future__ import annotations

from typing import Any, Dict, List

from cognitiveio.memory.local_store import LocalStore

COMMON_PHRASES: List[Dict[str, object]] = [
    {"before": "asap", "after": "as soon as possible", "profile": "email_docs", "confidence": 0.92},
    {"before": "fyi", "after": "for your information", "profile": "email_docs", "confidence": 0.9},
    {"before": "imo", "after": "in my opinion", "profile": "chat", "confidence": 0.87},
    {"before": "idk", "after": "I do not know", "profile": "chat", "confidence": 0.84},
    {"before": "lmk", "after": "let me know", "profile": "email_docs", "confidence": 0.9},
    {"before": "ty", "after": "thank you", "profile": "chat", "confidence": 0.82},
    {"before": "brb", "after": "be right back", "profile": "chat", "confidence": 0.8},
    {"before": "eod", "after": "end of day", "profile": "email_docs", "confidence": 0.9},
    {"before": "eta", "after": "estimated time of arrival", "profile": "email_docs", "confidence": 0.88},
    {"before": "w/", "after": "with", "profile": "email_docs", "confidence": 0.82},
    {"before": "w/o", "after": "without", "profile": "email_docs", "confidence": 0.82},
    {"before": "pls", "after": "please", "profile": "email_docs", "confidence": 0.87},
]

COMMON_CONCEPTS: List[Dict[str, object]] = [
    {
        "canonical": "Application Programming Interface",
        "synonym": "api",
        "domain": "engineering",
        "profile": "email_docs",
        "confidence": 0.92,
    },
    {
        "canonical": "Service Level Agreement",
        "synonym": "sla",
        "domain": "operations",
        "profile": "email_docs",
        "confidence": 0.91,
    },
    {
        "canonical": "Service Level Objective",
        "synonym": "slo",
        "domain": "operations",
        "profile": "email_docs",
        "confidence": 0.9,
    },
    {
        "canonical": "Service Level Indicator",
        "synonym": "sli",
        "domain": "operations",
        "profile": "email_docs",
        "confidence": 0.9,
    },
    {
        "canonical": "Machine Learning",
        "synonym": "ml",
        "domain": "engineering",
        "profile": "email_docs",
        "confidence": 0.88,
    },
    {
        "canonical": "Large Language Model",
        "synonym": "llm",
        "domain": "engineering",
        "profile": "email_docs",
        "confidence": 0.9,
    },
    {
        "canonical": "Minimum Viable Product",
        "synonym": "mvp",
        "domain": "product",
        "profile": "email_docs",
        "confidence": 0.89,
    },
]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def seed_common_language_assets(store: LocalStore) -> dict[str, int]:
    phrase_count = 0
    concept_count = 0

    for item in COMMON_PHRASES:
        store.upsert_phrase_pattern(
            phrase_before=str(item["before"]),
            phrase_after=str(item["after"]),
            profile=str(item.get("profile", "")),
            confidence=_safe_float(item.get("confidence", 0.8), 0.8),
        )
        phrase_count += 1

    for item in COMMON_CONCEPTS:
        store.upsert_concept(
            canonical=str(item["canonical"]),
            synonym=str(item["synonym"]),
            domain=str(item.get("domain", "")),
            profile=str(item.get("profile", "")),
            confidence=_safe_float(item.get("confidence", 0.88), 0.88),
        )
        concept_count += 1

    return {"phrases": phrase_count, "concepts": concept_count}
