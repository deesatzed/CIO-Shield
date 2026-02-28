# Contracts (SOTAppR-inspired)

## Feature: Protected Mode
Goal:
- 100% of password/excluded events must result in `do_nothing`.
- Verification: invariant tests + ledger blocked event count.

Constraints:
- Never store raw token content for blocked events.
- Must show explicit state: "Protected Mode Active".

Output:
- `RuntimeResult(action="do_nothing", protected_mode=true)`
- privacy ledger event: `kind=blocked` with reason.

Failure conditions:
- Catastrophic: any intervention in protected context.
- Degradation: missed indicator update.
- Recovery: force `protected_mode=true` and disable interventions.

## Feature: Suggest-only default
Goal:
- Suggestions only on boundary + idle threshold.
- Accept rate >= 40% after warm-up sessions.

Constraints:
- No auto-apply unless explicit opt-in.
- Suggestions capped per minute + cooldown after dismissals.

Output:
- `Decision(action=suggest)` + pending suggestion.

Failure conditions:
- Catastrophic: suggestion without boundary/idle gate.
- Degradation: high interruption rate.
- Recovery: tighten thresholds and budget caps.

## Feature: Undo
Goal:
- 1 hotkey/event reverts last applied change exactly.
- Verification: undo record before/after equality checks.

Constraints:
- Must capture precise before/after payload.

Output:
- `UndoRecord` pushed for every accepted/applied intervention.

Failure conditions:
- Catastrophic: undo changes wrong text.
- Recovery: disable apply path and keep suggest-only.

## Feature: Apple FM arbiter (optional)
Goal:
- Improve gray-zone decisions without invented replacements.

Constraints:
- Selector-only: candidate id from allowed set or null.
- Off by default.

Output:
- structured arbiter decision schema.

Failure conditions:
- Catastrophic: invalid candidate id accepted.
- Recovery: forced `do_nothing` and log violation.
