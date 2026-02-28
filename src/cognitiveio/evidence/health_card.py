from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class OrganismHealthCard:
    application: str
    sota_confidence: float
    architecture_score: float
    evolution_readiness: float
    complexity_budget_used: int
    ethical_risk_level: str
    strongest_organ: str
    weakest_organ: str
    biggest_risk: str
    biggest_blind_spot: str
    first_iteration_focus: str
    kill_criteria: str


def build_health_card(report: Dict[str, Any]) -> OrganismHealthCard:
    accept_rate = float(report.get("accept_rate", 0.0))
    blocked = int(report.get("blocked", 0))
    dismiss_rate = float(report.get("dismiss_rate", 0.0))

    sota_conf = min(10.0, max(1.0, 4.0 + accept_rate * 4.0 - dismiss_rate * 2.0))
    architecture_score = 20.0 if blocked > 0 else 17.0
    evolution_readiness = 3.8
    complexity_budget_used = 72

    ethical_risk = "Low" if blocked > 0 else "Medium"

    return OrganismHealthCard(
        application="CIO-II",
        sota_confidence=sota_conf,
        architecture_score=architecture_score,
        evolution_readiness=evolution_readiness,
        complexity_budget_used=complexity_budget_used,
        ethical_risk_level=ethical_risk,
        strongest_organ="Decision + Safety Gates",
        weakest_organ="macOS capture adapter integration",
        biggest_risk="False positives in high-velocity typing contexts",
        biggest_blind_spot="Cross-app cursor restore edge cases",
        first_iteration_focus="Improve suggestion precision in email/docs while reducing dismissals",
        kill_criteria="If accept_rate < 0.20 for 30 consecutive sessions",
    )


def render_health_card(card: OrganismHealthCard) -> str:
    lines = []
    lines.append("CIO-II - Organism Health Card")
    lines.append(f"Application: {card.application}")
    lines.append(f"SOTA confidence: {card.sota_confidence:.1f}/10")
    lines.append(f"Architecture score: {card.architecture_score:.1f}/25")
    lines.append(f"Evolution readiness: {card.evolution_readiness:.1f}/5")
    lines.append(f"Complexity budget used: {card.complexity_budget_used}/100")
    lines.append(f"Ethical risk: {card.ethical_risk_level}")
    lines.append(f"Strongest organ: {card.strongest_organ}")
    lines.append(f"Weakest organ: {card.weakest_organ}")
    lines.append(f"Biggest risk: {card.biggest_risk}")
    lines.append(f"Biggest blind spot: {card.biggest_blind_spot}")
    lines.append(f"First iteration focus: {card.first_iteration_focus}")
    lines.append(f"Kill criteria: {card.kill_criteria}")
    return "\n".join(lines)
