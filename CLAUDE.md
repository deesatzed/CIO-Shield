# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

CIO-II is an on-device, trust-first writing assistant for macOS (Apple Silicon). It uses the Apple FM on-chip model as a **constrained arbiter** — deterministic logic proposes safe candidates, Apple FM selects from those candidates or returns `do_nothing`. The model never generates replacement text. Core operation is local-only with no cloud dependency.

**Version**: 0.2.0
**Python**: 3.11+ (tested on 3.11, 3.12, 3.13)
**Platform**: macOS arm64 only (Darwin 26.0+, Xcode 26.0+)

## Build & Development Commands

### Setup
```bash
./bootstrap.sh                    # Creates .venv, installs deps, clones Apple FM SDK if needed
source .venv/bin/activate         # Activate venv (bootstrap does this internally)
```

### Running
```bash
./run.sh                                                    # Headless interactive mode
PYTHONPATH=src python -m cognitiveio.cli run --mode mac      # Native macOS event-tap mode
PYTHONPATH=src python -m cognitiveio.cli run --mode auto     # Auto (falls back to headless)
./run_demo.sh                                                # Deterministic demo
```

### Testing
```bash
pytest -q                                   # Full suite (331 tests, ~2.5s)
pytest -q --cov=cognitiveio --cov-report=term-missing  # With coverage (94%)
pytest -q -m "not live_fm"                  # Skip Apple FM live tests
pytest -q -m "not live_mac"                 # Skip macOS Accessibility live tests
pytest tests/test_invariants.py             # Single test file
pytest tests/security/ -q                   # Security test group
pytest tests/language/ -q                   # Language/phrase test group
pytest -q -k "test_protected"              # Run tests matching keyword
```

Tests use `COGNITIVEIO_HOME=.cognitiveio_test` (set in `tests/conftest.py`) for isolation. All tests use real SQLite via `tmp_path` — no mocks, no simulation. Two markers gate hardware-dependent tests: `live_fm` (Apple FM runtime) and `live_mac` (macOS Accessibility event tap).

### Linting & Type Checking
```bash
ruff check src tests              # Lint (100 char line length)
mypy src                          # Type check (Python 3.11 baseline)
```

### Verification Scripts
```bash
./verify-mitigations.sh           # Full pipeline: preflight + ruff + mypy + pytest + demo + schema + security + phrases + headless
./validate-user-journey.sh        # End-to-end user journey: seed assets, phrases, suggest/accept flow, reports, ledger
```

### CLI Utility Commands
```bash
PYTHONPATH=src python -m cognitiveio.cli requirements-check     # Platform preflight
PYTHONPATH=src python -m cognitiveio.cli proof-report            # Metrics summary
PYTHONPATH=src python -m cognitiveio.cli health-card             # Status overview
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
PYTHONPATH=src python -m cognitiveio.cli arbiter-status          # FM arbiter state
PYTHONPATH=src python -m cognitiveio.cli schema-check            # DB schema validation
PYTHONPATH=src python -m cognitiveio.cli explain-last            # Last runtime decision
PYTHONPATH=src python -m cognitiveio.cli seed-language-assets    # Seed typo/concept/phrase data
PYTHONPATH=src python -m cognitiveio.cli delete-all --confirm    # Factory reset
```

## Architecture

All source lives under `src/cognitiveio/`. The package is installed as editable (`pip install -e .`) with entry points `cio-ii` and `cognitiveio`.

### Module Topology (data flows top-down)

```
cli.py                          # Typer CLI: run, reports, phrase mgmt, diagnostics
  |
runtime/app_runtime.py          # Core state machine (events: boundary, accept, dismiss, undo, panic)
  |
  +-- runtime/mac_bridge.py     # macOS event tap, keycode map, text injection (pyobjc)
  +-- runtime/protected_context.py  # Password field / excluded app detection
  +-- runtime/suggestion_presenter.py  # Overlay (native) or console prompt
  +-- runtime/text_apply.py     # Text mutation with undo + secret resolution
  +-- runtime/ax_geometry.py    # Accessibility geometry helpers
  |
core/decision_engine.py         # Deterministic decision path (<=5ms target)
  |                               Risk gates, budget checks, conflict detection
  +-- ai/fm_arbiter.py          # Apple FM constrained selector (80ms timeout, fail-closed)
  |
context/profiles.py             # Profile classification: code, terminal, email_docs, chat, unknown
context/app_context.py          # App name, bundle ID, window title
  |
memory/local_store.py           # SQLite (optional SQLCipher) — patterns, events, reports
memory/language_assets.py       # Seeded typo/concept/phrase library
core/undo_stack.py              # Reversible change records with app metadata
  |
security/aliases.py             # {{SECRET:NAME}} parser and substitution
security/resolver.py            # Secret resolution with TTL cache
security/vault.py               # Secret provider abstraction (env-backed)
security/redaction.py           # Payload minimization for logs/ledger
  |
evidence/metrics.py             # Runtime counters (suggestions, accepts, dismissals, undo)
evidence/report_generator.py    # JSON proof report with trendlines
evidence/health_card.py         # Visual status card
  |
policy/risk_scoring.py          # Risk assessment (password, unknown profile, blacklist)
experiments/ab_testing.py       # A/B variant assignment
config.py                       # Settings dataclass, env resolution
platform_requirements.py        # macOS/Xcode/FM availability checks
```

### Critical Invariants (from docs/PRODUCT_CONTRACT.md)

These are non-negotiable runtime behaviors that must never be broken:

1. **Protected context always yields `do_nothing`** — password fields, excluded apps
2. **Unknown/code/terminal profiles default to `do_nothing`** — fail-safe
3. **Apple FM is selector-only** — can only choose from provided candidate IDs or `do_nothing`, never generates text
4. **FM unavailability in gray-zone fails closed** to `do_nothing`
5. **Undo targets exact before/after pair** — reversible on all paths
6. **Latency budget**: decision path <= 5ms, overlay <= 16ms, FM timeout <= 80ms
7. **Local-only**: no cloud dependency in core decision path, no network in hot path
8. **Suggest-only is default** — no silent rewrites

### Profile Classification Logic

Profile determines intervention policy. Located in `context/profiles.py`:
- `code` (VSCode, Xcode, PyCharm) -> `do_nothing`
- `terminal` (Terminal, iTerm) -> `do_nothing`
- `email_docs` (Mail, Safari, Notes, Notion) -> `suggest`
- `chat` (Slack, Discord, Messages) -> `suggest`
- `unknown` -> `do_nothing` (fail-safe)

### Decision Engine Flow

`core/decision_engine.py` `decide()` is async, target <= 5ms:
1. Risk gates (password, blacklist, unknown profile)
2. Budget/cooldown checks
3. Candidate generation from memory (typo corrections, phrase expansions, concept mappings)
4. If single high-confidence candidate -> suggest or auto-apply
5. If ambiguous (gray-zone) -> route to FM arbiter (or `do_nothing` if FM unavailable)
6. FM arbiter returns candidate ID or `do_nothing` within 80ms timeout

### Secret Resolution

Phrases can contain `{{SECRET:NAME}}` placeholders. On accept, `security/resolver.py` resolves from `COGNITIVEIO_SECRET_*` env vars via the vault provider. Unresolved secrets fail-closed (accept blocked). All secret metadata in ledger/reports is redacted.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`):
- Trigger: all pushes and pull requests
- Matrix: Python 3.11, 3.12, 3.13 on `macos-latest`
- Steps: ruff check, mypy, pytest with coverage, demo smoke test
- Repo: `https://github.com/deesatzed/CIO-II.git`

## Key Environment Variables

```bash
COGNITIVEIO_HOME=.cognitiveio              # Local data directory
COGNITIVEIO_ENABLE_APPLE_FM=0|1            # Toggle FM arbiter
COGNITIVEIO_FM_REQUIRED_FOR_GRAY_ZONE=1    # Fail-closed gray-zone (default)
COGNITIVEIO_ARB_VARIANT=A|B                # FM variant selection
COGNITIVEIO_DB_ENCRYPTION=off|optional|required
COGNITIVEIO_IDLE_PAUSE_MS=300              # Suggestion trigger delay
COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p     # Panic toggle
COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z      # Undo hotkey
COGNITIVEIO_SECRET_*=...                   # Env-backed secret provider values
```

## Testing Patterns

**331 tests | 94% measured coverage | 26 modules at 100% | no mocks**

- `conftest.py` sets `COGNITIVEIO_HOME` to `.cognitiveio_test` and inserts `src/` into `sys.path`
- `asyncio_mode = "auto"` in pyproject.toml — async tests run automatically
- `pytest-cov` configured in `pyproject.toml` (`[tool.coverage.run]` and `[tool.coverage.report]`)
- All tests use real SQLite via `tmp_path` — no mocks, no simulation, no placeholders

### Test File Inventory

| File | Tests | Coverage Target |
|------|-------|-----------------|
| `test_invariants.py` | 21 | Product contract invariants, decision engine paths |
| `test_runtime_flow.py` | 25 | Runtime state machine, boundary events, trust circuit |
| `test_cli.py` | 36 | CLI commands via `typer.testing.CliRunner` |
| `test_local_store_extended.py` | 42 | SQLite CRUD, lifecycle, privacy ledger, phrases |
| `test_config.py` | 17 | Settings, env overrides, resolve_app_home |
| `test_text_apply_policy.py` | 28 | Apply/undo policy, secret resolution, bridge failures |
| `test_suggestion_presenter.py` | 11 | Console presenter, menu bar titles, state dedup |
| `test_undo_stack.py` | 8 | LIFO stack, overflow, peek/pop |
| `test_risk_scoring.py` | 8 | Risk assessment, gate_action tiers |
| `test_reporting.py` | 15 | Proof reports, health cards, trend rendering |
| `test_protected_context.py` | 11 | Protected context detection, exclusion files |
| `test_profiles.py` | 8 | Profile classification, overrides |
| `test_platform_requirements.py` | 13 | Platform checks via injected runner/probe |
| `test_fm_arbiter_unit.py` | 7 | FM arbiter non-live paths, validation |
| `test_vault_resolver_extended.py` | 14 | Secret vault, resolver cache, composite providers |
| `test_app_context.py` | 3 | Frozen dataclass construction |
| `test_ab_testing.py` | 6 | A/B variant assignment |
| `test_no_network.py` | 1 | No network in core path |
| `test_memory_lifecycle.py` | 2 | Pattern lifecycle basics |
| `tests/security/` | 11 | Encryption, redaction, alias resolution |
| `tests/language/` | 13 | Phrase memory, concept lexicon, asset seeding |

### Intentionally Uncovered (hardware-dependent)

| Module | Lines | Reason |
|--------|-------|--------|
| `suggestion_presenter.py` | 43 | Cocoa/AppKit framework (NSWindow, NSStatusBar) |
| `protected_context.py` | 20 | macOS Accessibility API calls |
| `fm_arbiter.py` | 16 | Apple FM SDK hardware runtime |
| `cli.py` (mac mode) | 20 | PyObjC + MacRuntimeBridge event tap |
| `text_apply.py` (bridge) | 6 | macOS pasteboard/keystroke injection |
| `decision_engine.py` | 8 | Unreachable defensive guards + import fallback |
| `local_store.py` | 9 | SQLCipher encryption (optional dep) + migration no-op |

- Live tests (skipped by default) require `live_fm` or `live_mac` markers

## Documentation Map

In-depth documentation lives in `docs/`:
- `PRODUCT_CONTRACT.md` — non-negotiables, runtime invariants, latency budget
- `FEATURE_MATRIX.md` — ranked features with priority/complexity
- `IMPLEMENTATION_ROADMAP.md` — 4 sprints: trust kernel, UX, learning lifecycle, FM arbiter
- `TESTING_GUIDE.md` — automated + manual QA procedures
- `TEST_PLAN_FEATURE_MATRIX.md` — per-feature test coverage matrix
- `STARTUP_PROCEDURES.md` — platform setup and troubleshooting
- `GIT_WORKFLOW.md` — branching, review, release process
- `REAL_WORLD_VALIDATION_PLAN.md` — field test scenarios
