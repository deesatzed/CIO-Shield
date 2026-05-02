# CIO-II Implementation Roadmap

## Sprint 0: Scope Lock and Architecture (current)
- [x] Define product non-negotiables and invariants.
- [x] Build cross-repo ranked feature matrix.
- [x] Confirm single-app module topology:
  - `context`, `core`, `runtime`, `memory`, `evidence`, `ai`.
- [x] Confirm latency budget and fail-safe requirements.

Deliverables:
1. `docs/PRODUCT_CONTRACT.md`
2. `docs/FEATURE_MATRIX.md`
3. This roadmap

## Sprint 1: Trust Kernel
- [x] Add candidate conflict gating in decision engine.
- [x] Add trust circuit breaker cooldown after dense negative signals.
- [x] Preserve auditable blocked reasons in privacy ledger.
- [x] Add richer blocked reason aggregation in proof report and health card.
- [x] Add explicit trust-circuit sections in demo script.

## Sprint 2: UX Kernel
- [x] Maintain ghost suggestion only at boundary + idle.
- [x] Tighten intervention budget adaptively by typing speed.
- [x] Expand negative learning to include undo-weighted penalty.
- [x] Add quick user-facing “why no suggestion” status hints.

## Sprint 3: Learning Lifecycle
- [x] Add per-pattern lifecycle states (embryonic, viable, thriving, declining).
- [x] Promote only repeated successful patterns.
- [x] Decay stale patterns over time.
- [x] Keep all learning local and encrypted-at-rest compatible.

## Sprint 4: FM-First Arbiter + Proof
- [x] Make FM path ON by default for gray-zone security.
- [x] Default variant `B` (gray-zone arbiter) with AB disabled by default.
- [x] Add fail-closed behavior when FM is required but unavailable.
- [x] Enforce selector-only invariant tests (candidate id or null).
- [x] Extend proof report with trust metrics trendline.

## Quality Gates (must stay green every sprint)
1. `pytest -q`
2. No-network runtime assertion
3. Protected mode hard-stop tests
4. Unknown/code/terminal profile do-nothing tests
5. Undo correctness tests

## Release Checklist
1. Run demo script and verify expected outcomes.
2. Generate proof report and health card.
3. Review privacy ledger export shape.
4. Confirm docs: startup, testing, blog, contracts, roadmap.
