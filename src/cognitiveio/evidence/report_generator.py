from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from cognitiveio.evidence.metrics import Metrics


@dataclass
class ProofReport:
    minutes: float
    suggestion_shown: int
    suggestion_accepted: int
    suggestion_dismissed: int
    auto_applied: int
    undone: int
    blocked: int
    interruption_rate_per_min: float
    accept_rate: float
    dismiss_rate: float
    undo_rate: float
    top_patterns: List[Dict[str, Any]]
    top_block_reasons: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_report(
    metrics: Metrics,
    top_patterns: List[Dict[str, Any]],
    top_block_reasons: List[Dict[str, Any]],
) -> ProofReport:
    s = metrics.snapshot()
    return ProofReport(
        minutes=float(s["minutes"]),
        suggestion_shown=int(s["suggestion_shown"]),
        suggestion_accepted=int(s["suggestion_accepted"]),
        suggestion_dismissed=int(s["suggestion_dismissed"]),
        auto_applied=int(s["auto_applied"]),
        undone=int(s["undone"]),
        blocked=int(s["blocked"]),
        interruption_rate_per_min=float(s["interruption_rate_per_min"]),
        accept_rate=float(s["accept_rate"]),
        dismiss_rate=float(s["dismiss_rate"]),
        undo_rate=float(s["undo_rate"]),
        top_patterns=top_patterns,
        top_block_reasons=top_block_reasons,
    )


def generate_report_text(r: ProofReport) -> str:
    lines: List[str] = []
    lines.append("CIO-II - Proof Report (local)")
    lines.append(f"Session minutes: {r.minutes:.2f}")
    lines.append(
        f"Suggestions shown: {r.suggestion_shown}  accepted: {r.suggestion_accepted}  dismissed: {r.suggestion_dismissed}"
    )
    lines.append(f"Auto-applied: {r.auto_applied}  undone: {r.undone}")
    lines.append(f"Blocked events: {r.blocked}")
    lines.append(f"Interruption rate/min: {r.interruption_rate_per_min:.2f}")
    lines.append(
        f"Accept rate: {r.accept_rate:.2%}  Dismiss rate: {r.dismiss_rate:.2%}  Undo rate: {r.undo_rate:.2%}"
    )
    if r.top_patterns:
        lines.append("\nTop patterns:")
        for p in r.top_patterns[:5]:
            lines.append(
                f"- {p['before']} -> {p['after']} (count {p['count']}, conf {p['confidence']:.2f})"
            )
    if r.top_block_reasons:
        lines.append("\nTop block reasons:")
        for b in r.top_block_reasons[:5]:
            lines.append(f"- {b['reason']}: {b['count']}")
    return "\n".join(lines)
