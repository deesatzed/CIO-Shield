# Adversarial Test Matrix

## Hard stops
- password field => do_nothing
- excluded app => do_nothing
- unknown profile => do_nothing
- code/terminal profile => do_nothing

## Safety invariants
- no suggestion without boundary + idle threshold
- budget cap and dismissal cooldown enforced
- undo restores exact before/after payload
- FM arbiter candidate id must be in provided set

## Reliability
- paused mode blocks all interventions
- repeated dismissals reduce confidence and cool down
- no-network imports in core runtime path

## Chaos checks (planned)
- datastore unavailable for 60s
- dependency break in on-chip FM adapter
- 100x event rate burst in runtime queue
