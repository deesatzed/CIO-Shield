from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RiskFlags:
    password_field: bool = False
    blacklisted_app: bool = False
    detector_uncertain: bool = False
    user_excluded: bool = False

@dataclass(frozen=True)
class RiskAssessment:
    risk_score: float
    reason: str

def assess_risk(profile: str, flags: RiskFlags) -> RiskAssessment:
    if flags.password_field:
        return RiskAssessment(1.0, "password_field")
    if flags.blacklisted_app or flags.user_excluded:
        return RiskAssessment(1.0, "excluded_app")
    if profile == "unknown":
        return RiskAssessment(0.9, "unknown_profile")
    if flags.detector_uncertain:
        return RiskAssessment(0.8, "detector_uncertain")
    return RiskAssessment(0.2, "low")

def gate_action(risk: RiskAssessment) -> str:
    if risk.risk_score >= 0.5:
        return "none"
    if risk.risk_score >= 0.15:
        return "suggest"
    return "auto"
