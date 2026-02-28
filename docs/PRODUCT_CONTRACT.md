# CIO-II Product Contract

## Purpose
Build one macOS application that is predictably helpful, strictly local, and visibly safe.

## Non-Negotiables
1. UX dominance:
- Suggest-only is default.
- Suggestions appear only at word boundary and idle pause.
- No modal popups, no blocking flows, no surprise rewrites.
2. Security and privacy dominance:
- Hard block in password fields, excluded apps, and protected contexts.
- Data minimization only; no raw keystroke stream storage.
- Auditable privacy ledger with delete-all control.
3. Not-autocorrect proof:
- Unknown profile, code profile, and terminal profile default to do-nothing.
- Apple FM is optional and selector-only from known candidates or do-nothing.
- Every applied change must have a reversible undo record.
4. Local-only operation:
- No cloud dependency for core runtime decisions.
- No API keys required for baseline app function.

## Runtime Invariants
1. Protected context always yields `do_nothing`.
2. Missing profile classification yields `do_nothing`.
3. Candidate conflict without safe arbiter path yields `do_nothing`.
4. Undo must target the exact recorded before/after pair.
5. Any failure in optional FM path must fail safe to deterministic logic.

## Latency Budget
1. Decision path (deterministic): <= 5ms target.
2. Overlay update: <= 16ms frame budget target.
3. Optional FM arbiter timeout: <= 80ms, then `do_nothing`.
4. No synchronous disk-heavy operations on hot keystroke path.

## Safety Controls
1. Panic hotkey pauses observation and intervention instantly.
2. Trust circuit breaker suppresses intervention when dismiss/undo spikes.
3. Menu bar indicator must always reflect running, paused, and protected states.
