# CIO-II

CIO-II is a local-first macOS typing copilot that is intentionally **not autocorrect**:
- suggest-only by default
- hard safety stops for protected contexts
- reversible actions with perfect undo records
- auditable privacy ledger and proof report
- optional Apple FM arbiter as selector-only (never free generation)
- app-aware apply adapters (keystroke/pasteboard/command-undo strategies)

## Why this app
It is designed to preserve user intent while reducing repetitive correction friction in everyday writing, without cloud dependency.

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./run_demo.sh
```

## uv environment setup (recommended)
`uv` can manage one local environment that includes this app, PyObjC runtime support, and optional Apple FM support.

```bash
cd /Users/o2satz/python-apple-fm-sdk/cioStart
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"

# Optional: install local python-apple-fm-sdk from parent repo source
uv pip install -e ..

# Optional: enable FM arbiter at runtime
export COGNITIVEIO_ENABLE_APPLE_FM=1
# Optional: force arbiter variant for demos (A or B)
export COGNITIVEIO_ARB_VARIANT=B
# Optional: override hotkeys
export COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p
export COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z
```

## Main commands
```bash
# Interactive headless runtime
./run.sh

# Explicit macOS event-tap mode (requires PyObjC + Accessibility permission)
PYTHONPATH=src python -m cognitiveio.cli run --mode mac

# Deterministic showpiece demo
./run_demo.sh

# Show latest local proof report
PYTHONPATH=src python -m cognitiveio.cli proof-report

# Show health card
PYTHONPATH=src python -m cognitiveio.cli health-card

# Show FM arbiter variant status
PYTHONPATH=src python -m cognitiveio.cli arbiter-status

# Show/export privacy ledger
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --export-path ./ledger.json

# Delete all local data
PYTHONPATH=src python -m cognitiveio.cli delete-all --confirm
```

## Safety defaults
- `suggest_only = true`
- `auto_apply_enabled = false`
- `apple_fm_enabled = false`
- `apple_fm_variant = A` (stable local assignment unless overridden)
- `unknown profile => do_nothing`
- `code/terminal profiles => do_nothing`

## PyObjC and Apple FM fit
- PyObjC (`.[mac]`) powers the native macOS event tap bridge (`--mode mac`).
- `python-apple-fm-sdk` is optional and only used by the selector-only arbiter path.
- If Apple FM SDK is missing or unavailable on device, decisions fail safe to deterministic `do_nothing/suggest` logic.

## Current macOS runtime behavior
- Ghost suggestions are shown via a lightweight Cocoa overlay when available (fallback: console indicator).
- A menu bar status indicator is always visible in mac mode:
  - `CIO` = running
  - `CIO-P` = Protected Mode active
  - `CIO-II` = paused via panic hotkey
- Accept (`Tab`) applies replacement with app-aware strategy:
  - keystroke synthesis by default
  - pasteboard-assisted insertion for selected text-heavy apps
- Undo (`Ctrl+Option+Z`) prefers native `Command+Z` in original app context, with manual fallback.

## Local data location
By default the app writes under `~/.cognitiveio`. If unavailable, it falls back to `./.cognitiveio`.
Override with:
```bash
export COGNITIVEIO_HOME=/path/to/local/dir
```

## Documentation
- `docs/CONTRACTS.md`
- `docs/ARCH_OPTIONS.md`
- `docs/DEPENDENCY_TRIBUNAL.md`
- `docs/COMPLEXITY_BUDGET.md`
- `docs/ADVERSARIAL_TEST_MATRIX.md`
- `docs/BUILD_PLAN_SHOWPIECE.md`
- `docs/DEMO_SCRIPT.md`
