# CIO-II Launch: A Typing Assistant for macOS That Does Not Take Over

Today we are open-sourcing CIO-II.

It is a local-first typing assistant for macOS built around one rule:
help the user, but do not override user intent.

Most people have seen the same failure pattern with writing tools:
- autocorrect changes the wrong word
- the user notices too late
- trust is lost quickly

CIO-II is built to avoid that pattern.

## The Problem We Care About

People who type all day in email, documents, chat, and notes do not need flashy generation most of the time.
They need:
- fewer repetitive typo fixes
- fewer interruptions
- reliable behavior in sensitive contexts
- confidence that they can reverse changes immediately

That is the gap CIO-II focuses on.

## Who This Is For

CIO-II is designed for Mac users with moderate technical comfort, including:
- operations and support staff
- founders and product managers
- analysts and researchers
- students and writers
- anyone who types a lot but does not want AI to “take the wheel”

## Why CIO-II Is Different

### 1) Suggest-only by default
No silent rewrite.  
CIO-II shows a ghost suggestion and waits.

### 2) Hard safety blocks
In protected contexts, it blocks intervention instead of “trying anyway.”

### 3) Do-nothing is a first-class outcome
If confidence is weak, profile is unknown, or context is risky, CIO-II does nothing.

### 4) Undo is built in
Applied changes are reversible with explicit undo records.

### 5) Privacy is auditable
You can inspect local proof reports and privacy ledger events.

### 6) Optional Apple FM path is constrained
The arbiter can only choose from known local candidates or return do-nothing.
It cannot invent replacement text.

## Practical Examples

### Example: Email corrections without surprises
You type `teh` in Mail.  
At a natural pause, CIO-II offers `the`.  
You press `Tab` to accept or `Esc` to dismiss.

### Example: No interference while coding
You are in VS Code or Terminal.  
CIO-II defaults to `do_nothing` so identifiers and commands are not touched.

### Example: Sensitive context protection
You are in a password manager or protected field.  
CIO-II blocks capture and suggestions, and marks blocked state clearly.

### Example: Trust repair loop
If you keep dismissing or undoing, CIO-II enters a trust cooldown and stops nudging temporarily.

## Why This Matters Now

AI writing products are often optimized for generation volume.  
Users often need reliability, predictability, and reversible behavior more than raw generation.

CIO-II treats trust as an engineering constraint, not a marketing claim.

## What You Can Verify Yourself

Run the deterministic demo and inspect outputs:
- protected mode block
- suggest-only accept flow
- no intervention in code profile
- candidate-conflict do-nothing
- trust-circuit cooldown
- proof report and privacy ledger artifacts

## Quick Start

```bash
git clone https://github.com/deesatzed/CIO-II.git
cd CIO-II
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"
./run_demo.sh
```

Run tests:
```bash
pytest -q
```

Run native mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

See proof report:
```bash
PYTHONPATH=src python -m cognitiveio.cli proof-report
```

## What CIO-II Is Not

- It is not cloud-dependent by default.
- It is not free-form text generation pretending to be correction.
- It is not “always-on autocorrect.”
- It is not designed to modify code identifiers.

## What Feedback We Want

If you test CIO-II, the most useful feedback includes:
- exact app/context where behavior happened
- expected behavior vs actual behavior
- whether the action was acceptable, dismissible, or required undo
- privacy/safety concerns with concrete repro steps

## Closing

The long-term bet behind CIO-II is simple:
the most useful AI assistants will be the ones users trust in real work.

Trust comes from predictable triggers, hard safety boundaries, reversibility, and local auditability.

If that direction resonates, try CIO-II and tell us where it fails first.

Repo: https://github.com/deesatzed/CIO-II
