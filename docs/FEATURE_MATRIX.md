# CIO-II Feature Matrix (Cross-Repo Synthesis)

Scoring scale:
- `success_probability`: 0.00 to 1.00
- `value`: 0.00 to 1.00
- `latency_cost`: low / medium / high on hot path

## Ranked Candidates
| Rank | Enhancement | Source | success_probability | value | latency_cost | Decision |
|---|---|---|---:|---:|---|---|
| 1 | Failure signature learning (avoid repeated bad suggestions) | `the-associate` + `therealme` | 0.92 | 0.95 | low | Adopt |
| 2 | Confidence/conflict gating before intervention | `the-associate` | 0.90 | 0.93 | low | Adopt |
| 3 | Trust circuit breaker from user rejection density | `the-associate` + `logvams` | 0.89 | 0.91 | low | Adopt |
| 4 | Memory lifecycle (promote wins, demote stale patterns) | `the-associate` | 0.87 | 0.90 | low | Adopt |
| 5 | Adaptive assistance ladder routing | `the-associate` + `xplurx` | 0.85 | 0.89 | low | Adopt |
| 6 | Deterministic candidate arbitration with explicit tie-break | `the-associate` | 0.84 | 0.87 | low | Adopt |
| 7 | Structured diagnostic snapshots for trust audits | `the-associate` | 0.83 | 0.86 | medium | Adopt |
| 8 | Session profile and onboarding contract artifacts | `xplurx` | 0.80 | 0.82 | low | Adopted |
| 9 | Research/web augmentation in runtime decision path | mixed | 0.42 | 0.30 | high | Reject |
| 10 | Cloud-hosted memory/telemetry for runtime loop | mixed | 0.35 | 0.20 | high | Reject |

## Drift Guard
Exclude anything that shifts CIO-II away from real-time local typing assistance:
1. No cloud orchestration in core pipeline.
2. No heavyweight agent loop in keystroke path.
3. No speculative generation replacing user intent.
