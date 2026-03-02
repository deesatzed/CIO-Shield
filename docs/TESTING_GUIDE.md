# CIO-II Testing Guide

This guide covers automated and manual validation before release.
For complete per-feature coverage and release sign-off mapping, see:
- `docs/TEST_PLAN_FEATURE_MATRIX.md`

## Automated Tests

Run full suite:
```bash
cd /Volumes/WS4TB/CIO-II
PYTHONPATH=src python -m cognitiveio.cli requirements-check
pytest -q
./verify-mitigations.sh
```

Key covered areas:
- Decision invariants (hard stops, unknown profile, code profile, budget limits)
- Arbiter safety invariant (candidate ID must come from provided list)
- Runtime flow (suggest, accept, dismiss, undo)
- Protected context detector behavior
- Hotkey parsing and mac runtime availability checks
- App-aware apply/undo policy
- No-network guard in core runtime path

## Deterministic Product Demo Test

Run showpiece scenario:
```bash
./run_demo.sh
```

Expected outcomes:
1. Protected mode event is blocked
2. Suggest-only flow appears and can be accepted
3. Code profile has no intervention
4. Candidate-conflict ambiguity yields do-nothing
5. Trust circuit breaker appears after negative signals
6. Undo restores prior payload
7. Proof report and ledger are written locally

## Manual macOS QA (Native Mode)

Start runtime:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

Validate:
1. Accessibility permissions are granted
2. Menu bar status changes correctly:
- `CIO` normal
- `CIO-P` protected mode
- `CIO-II` panic pause
3. Suggestion behavior:
- appears only at boundary + idle pause
- `Tab` accepts
- `Esc` dismisses
4. Intervention budget:
- repeated dismissals trigger cooldown
- fast typing suppresses suggestions
5. Undo:
- panic/normal state does not break undo hotkey
- undo restores expected prior text

## Privacy + Audit Verification

Commands:
```bash
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --export-path ./ledger.json
PYTHONPATH=src python -m cognitiveio.cli proof-report
PYTHONPATH=src python -m cognitiveio.cli health-card
```

Verify:
- blocked events include reasons without raw keystroke stream
- stored events are minimized
- local-only artifacts are created under `~/.cognitiveio` (or `COGNITIVEIO_HOME`)

## Smoke Test Matrix for Release

1. `pytest -q` green
2. demo script green
3. mac native smoke pass
4. proof report generated
5. privacy ledger export generated
