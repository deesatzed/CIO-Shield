# Architecture Options

## Option A: Runtime-first local state machine (selected)
- Core: deterministic event pipeline + local SQLite memory.
- Pros: high safety, testability, low dependency risk.
- Cons: requires adapter work for native macOS capture UX.
- Score: Feasibility 5, Novelty 3, Resilience 4, Evolvability 5, Simplicity 4.

## Option B: Menu-bar native-first monolith
- Core: direct macOS hooks + UI + decisions in one process.
- Pros: fastest path to polished UX.
- Cons: high coupling, hard testing, regression risk.
- Score: Feasibility 4, Novelty 2, Resilience 2, Evolvability 2, Simplicity 2.

## Option C: Event-sourced append-only CRDT model
- Core: immutable events and deterministic reducers.
- Pros: auditability and replay.
- Cons: complexity overhead for v1.
- Score: Feasibility 3, Novelty 4, Resilience 5, Evolvability 4, Simplicity 2.

## Selection
Option A with selective ideas from C:
- keep deterministic runtime and replay-friendly events.
- avoid CRDT complexity in v1.
