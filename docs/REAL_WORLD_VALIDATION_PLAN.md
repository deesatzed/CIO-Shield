# CIO-II Real-World Validation Plan

This plan defines exactly how to validate that CIO-II is working for a new user, with minimal confounders.

## 1) Goals

- Prove that CIO-II can detect boundaries and show/apply suggestions.
- Prove that local learning + feedback loop (`accept`, `dismiss`, `undo`) is active.
- Prove that platform and FM on-chip requirements are met.
- Separate CIO-II behavior from native app autocorrect behavior.

## 2) Automated Validation (No Confounders)

Run:

```bash
./validate-user-journey.sh
```

This script validates:
- platform preflight (`requirements-check`)
- phrase seeding + retrieval
- deterministic headless suggestion and accept flows
- latest decision snapshot generation
- proof-report generation
- health-card generation
- privacy-ledger event capture

Pass condition:
- Script prints `✅ USER JOURNEY VALIDATED`

## 3) Native Runtime Validation (macOS)

Run:

```bash
cio-ii run --mode mac
```

Then in a writing app (Notes or TextEdit):
- Type `teh ` and pause.
- Expect ghost suggestion and `Tab` accept behavior.
- Type `teh ` again and press `Esc` to dismiss.
- Press `ctrl+option+z` to test undo.
- Press `ctrl+option+p` to pause/resume and verify behavior changes.

Pass condition:
- Terminal logs show `suggest`, `accept`, `dismiss`, or `undo` events.

## 4) Confounder Control

For clean manual tests:
- Use plain-text mode where possible.
- Disable native spellcheck/autocorrect in test app during validation.
- Do not test inside terminal/code editors for suggestion behavior (those are intentionally blocked profiles).

## 5) Evidence Commands

After testing, run:

```bash
cio-ii explain-last --json
cio-ii proof-report
cio-ii health-card
cio-ii privacy-ledger --limit 25
```

Pass condition:
- `explain-last` has valid JSON with `action` and `reason_tag`.
- `proof-report` includes suggestion + block metrics.
- `privacy-ledger` includes expected stored/blocked events.

## 6) Failure Triage

If nothing happens while typing:
- Run `cio-ii requirements-check`
- Ensure app is not paused (`ctrl+option+p` toggles)
- Confirm typing app profile is not code/terminal
- Seed assets: `cio-ii seed-language-assets`
- Re-test with token `teh ` in Notes/TextEdit

If FM check fails with `sdk_import_error`:
- Run `./bootstrap.sh`

