# CIO-II: Intent-Preserving Typing Assistance for macOS

## Launch Post Draft

Today we are open-sourcing CIO-II, a local-first typing copilot for macOS designed around one principle: help without hijacking intent.

Most people have experienced autocorrect that changes meaning at the worst possible moment. CIO-II is built to do the opposite.

What makes CIO-II different:
- Suggest-only by default, not silent rewrite
- Hard protected mode in sensitive contexts
- Profile gating that defaults to do nothing when uncertain
- Perfect undo records for applied changes
- Local privacy ledger and proof reports
- Optional Apple Foundation Model arbiter that can only select from known local candidates

This is not “generate text and hope.”  
The arbiter path is constrained in code to pick candidate IDs from a precomputed local set or do nothing.

## Why this matters

Trust in writing tools is fragile.  
CIO-II treats trust as a first-class system invariant:
- predictable triggers (boundary + idle pause)
- reversible interventions
- explicit blocked-state visibility (`CIO-P`, `CIO-II`)
- no cloud dependency in the core runtime

## How to run

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

Run native macOS mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

## Invitation

If you care about AI UX, local-first privacy, and engineering for reversibility, we want your feedback.

- Try the demo
- Read the testing guide
- Open issues with concrete repro steps
- Propose profile/risk policy improvements

Repo: https://github.com/deesatzed/CIO-II
