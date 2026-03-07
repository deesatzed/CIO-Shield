# CIO-II Testing Guide

This guide covers automated and manual validation before release.
For complete per-feature coverage and release sign-off mapping, see:
- `docs/TEST_PLAN_FEATURE_MATRIX.md`

## Test Suite Overview

**331 tests | 94% measured coverage | 26 modules at 100%**

All tests use real SQLite via `tmp_path` — no mocks, no simulation, no placeholders.

Coverage is measured with `pytest-cov` (configured in `pyproject.toml`).

## Automated Tests

Run full suite:
```bash
cd CIO-II   # your clone directory
source .venv/bin/activate

# Full suite with coverage
pytest -q --cov=cognitiveio --cov-report=term-missing

# Quick run (no coverage)
pytest -q

# Full verification pipeline
./verify-mitigations.sh
```

### Test Groups

```bash
# By test file
pytest tests/test_runtime_flow.py -v          # Runtime state machine (25 tests)
pytest tests/test_invariants.py -v            # Product contract invariants (21 tests)
pytest tests/test_cli.py -v                   # CLI commands (36 tests)
pytest tests/test_local_store_extended.py -v  # SQLite store (42 tests)
pytest tests/test_config.py -v               # Settings and env overrides (17 tests)
pytest tests/test_text_apply_policy.py -v    # Apply/undo policy (28 tests)
pytest tests/test_suggestion_presenter.py -v # Presenter behavior (11 tests)
pytest tests/test_platform_requirements.py -v # Platform checks (13 tests)
pytest tests/test_vault_resolver_extended.py -v # Secret resolution (14 tests)
pytest tests/test_fm_arbiter_unit.py -v      # FM arbiter non-live paths (7 tests)

# By domain
pytest tests/security/ -v                    # Security/redaction (11 tests)
pytest tests/language/ -v                    # Phrase/concept (13 tests)

# By keyword
pytest -q -k "test_protected"               # Run tests matching keyword
```

### Coverage Areas

| Domain | Key Test Files | Coverage |
|--------|---------------|----------|
| Decision engine | `test_invariants.py` | 93% (8 lines unreachable defensive code) |
| Runtime state machine | `test_runtime_flow.py` | 100% |
| CLI commands | `test_cli.py` | 94% (mac mode requires hardware) |
| SQLite store | `test_local_store_extended.py`, `test_memory_lifecycle.py` | 97% (SQLCipher optional) |
| Config/settings | `test_config.py` | 100% |
| Text apply/undo | `test_text_apply_policy.py` | 95% (bridge calls require hardware) |
| Risk scoring | `test_risk_scoring.py` | 100% |
| Profiles | `test_profiles.py` | 100% |
| Undo stack | `test_undo_stack.py` | 100% |
| Metrics | `test_reporting.py` | 100% |
| Health card | `test_reporting.py` | 100% |
| Report generator | `test_reporting.py` | 100% |
| A/B testing | `test_ab_testing.py` | 100% |
| Security (vault, resolver, aliases, redaction) | `test_vault_resolver_extended.py`, `tests/security/` | 100% |
| Language (phrases, concepts, assets) | `tests/language/` | 100% |
| Platform requirements | `test_platform_requirements.py` | 92% |
| FM arbiter | `test_fm_arbiter_unit.py` | 75% (inner call requires hardware) |
| Suggestion presenter | `test_suggestion_presenter.py` | 77% (Cocoa classes require GUI) |
| Protected context | `test_protected_context.py` | 73% (AX API requires permission) |

### Intentionally Uncovered (hardware-dependent, 133 lines)

| Module | Lines | Reason |
|--------|-------|--------|
| `suggestion_presenter.py` | 43 | Cocoa/AppKit (NSWindow, NSStatusBar, NSView) |
| `protected_context.py` | 20 | macOS Accessibility API (AXUIElement) |
| `fm_arbiter.py` | 16 | Apple FM SDK runtime (SystemLanguageModel) |
| `cli.py` (mac mode) | 20 | PyObjC + MacRuntimeBridge + event tap |
| `text_apply.py` (bridge) | 6 | macOS pasteboard/keystroke injection |
| `decision_engine.py` | 8 | Unreachable defensive guards + import fallback |
| `local_store.py` | 9 | SQLCipher (optional dep) + migration no-op |
| `platform_requirements.py` | 10 | Subprocess exceptions + system-specific paths |
| `demo_runner.py` | 1 | Standalone undo demo action (not in episodes) |

Hardware-dependent tests are gated behind markers:
```bash
pytest -m live_fm     # Apple FM SDK tests (skip by default)
pytest -m live_mac    # macOS Accessibility tests (skip by default)
```

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

## End-to-End User Journey

```bash
./validate-user-journey.sh
```

Seeds language assets, adds phrases, runs suggest/accept flow, generates reports, and verifies privacy ledger.

## Manual macOS QA (Native Mode)

Start runtime:
```bash
cio-ii run --mode mac
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
cio-ii privacy-ledger --limit 25
cio-ii privacy-ledger --export-path ./ledger.json
cio-ii proof-report
cio-ii health-card
```

Verify:
- blocked events include reasons without raw keystroke stream
- stored events are minimized
- local-only artifacts are created under `~/.cognitiveio` (or `COGNITIVEIO_HOME`)

## Smoke Test Matrix for Release

1. `ruff check src tests` green
2. `mypy src` green
3. `pytest -q` green (331 passed)
4. `pytest --cov=cognitiveio` shows >= 94%
5. `./run_demo.sh` green
6. `./verify-mitigations.sh` prints `ALL MITIGATIONS VERIFIED`
7. `./validate-user-journey.sh` green
8. mac native smoke pass (manual)
9. proof report generated
10. privacy ledger export generated
