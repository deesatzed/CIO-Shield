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
    blocked_protected_context: int = 0
    blocked_trust_circuit: int = 0
    blocked_candidate_conflict: int = 0
    blocked_profile_or_unknown: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReportTrend:
    sessions: int
    accept_rate_delta: float
    dismiss_rate_delta: float
    interruption_rate_delta: float
    trust_blocks_delta: int
    conflict_blocks_delta: int
    latest_accept_rate: float
    latest_dismiss_rate: float
    latest_interruption_rate: float


def build_report(
    metrics: Metrics,
    top_patterns: List[Dict[str, Any]],
    top_block_reasons: List[Dict[str, Any]],
) -> ProofReport:
    s = metrics.snapshot()
    reason_map = {
        str(item.get("reason", "")): int(item.get("count", 0))
        for item in top_block_reasons
    }

    def _sum_reasons(prefixes: List[str], contains: List[str]) -> int:
        total = 0
        for reason, count in reason_map.items():
            if any(reason.startswith(p) for p in prefixes) or any(c in reason for c in contains):
                total += count
        return total

    protected = _sum_reasons(
        prefixes=["blocked:"],
        contains=["password", "excluded", "blacklisted_app", "user_excluded", "detector_uncertain"],
    )
    trust_circuit = reason_map.get("trust_circuit_breaker", 0)
    candidate_conflict = reason_map.get("candidate_conflict", 0)
    profile_or_unknown = _sum_reasons(
        prefixes=["profile_block:"],
        contains=["unknown_profile"],
    )

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
        blocked_protected_context=protected,
        blocked_trust_circuit=int(trust_circuit),
        blocked_candidate_conflict=int(candidate_conflict),
        blocked_profile_or_unknown=profile_or_unknown,
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
            lifecycle = str(p.get("lifecycle_state", "embryonic"))
            successes = int(p.get("success_count", 0))
            failures = int(p.get("failure_count", 0))
            lines.append(
                f"- {p['before']} -> {p['after']} (count {p['count']}, conf {p['confidence']:.2f}, "
                f"life {lifecycle}, s/f {successes}/{failures})"
            )
    if r.top_block_reasons:
        lines.append("\nTop block reasons:")
        for b in r.top_block_reasons[:5]:
            lines.append(f"- {b['reason']}: {b['count']}")
    lines.append(
        "\nSafety block breakdown: "
        f"protected={r.blocked_protected_context} "
        f"trust_circuit={r.blocked_trust_circuit} "
        f"candidate_conflict={r.blocked_candidate_conflict} "
        f"profile_or_unknown={r.blocked_profile_or_unknown}"
    )
    return "\n".join(lines)


def build_report_trend(history: List[Dict[str, Any]]) -> ReportTrend:
    if not history:
        return ReportTrend(0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0)

    latest = history[0]
    baseline = history[-1]
    return ReportTrend(
        sessions=len(history),
        accept_rate_delta=float(latest.get("accept_rate", 0.0)) - float(baseline.get("accept_rate", 0.0)),
        dismiss_rate_delta=float(latest.get("dismiss_rate", 0.0)) - float(baseline.get("dismiss_rate", 0.0)),
        interruption_rate_delta=float(latest.get("interruption_rate_per_min", 0.0))
        - float(baseline.get("interruption_rate_per_min", 0.0)),
        trust_blocks_delta=int(latest.get("blocked_trust_circuit", 0))
        - int(baseline.get("blocked_trust_circuit", 0)),
        conflict_blocks_delta=int(latest.get("blocked_candidate_conflict", 0))
        - int(baseline.get("blocked_candidate_conflict", 0)),
        latest_accept_rate=float(latest.get("accept_rate", 0.0)),
        latest_dismiss_rate=float(latest.get("dismiss_rate", 0.0)),
        latest_interruption_rate=float(latest.get("interruption_rate_per_min", 0.0)),
    )


def render_report_trend_text(trend: ReportTrend) -> str:
    if trend.sessions <= 1:
        return "Trendline: only one session recorded."
    return (
        "Trendline (latest vs baseline): "
        f"sessions={trend.sessions} "
        f"accept_delta={trend.accept_rate_delta:+.2%} "
        f"dismiss_delta={trend.dismiss_rate_delta:+.2%} "
        f"interrupt_delta={trend.interruption_rate_delta:+.2f}/min "
        f"trust_block_delta={trend.trust_blocks_delta:+d} "
        f"conflict_block_delta={trend.conflict_blocks_delta:+d}"
    )
