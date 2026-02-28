# CIO-II Startup Procedures

This is the launch runbook for operating CIO-II safely and predictably on macOS.

## 1. Environment Setup

```bash
cd /Users/o2satz/python-apple-fm-sdk/cioStart
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"
```

Optional Apple FM path:
```bash
uv pip install -e ..
export COGNITIVEIO_ENABLE_APPLE_FM=1
export COGNITIVEIO_ARB_VARIANT=B
```

## 2. First-Run Safety Validation

1. Start deterministic demo:
```bash
./run_demo.sh
```
2. Confirm demo includes:
- Protected mode blocked event
- Suggest-only acceptance
- No code-profile intervention
- Undo event
3. Print proof report:
```bash
PYTHONPATH=src python -m cognitiveio.cli proof-report
```
4. Print health card:
```bash
PYTHONPATH=src python -m cognitiveio.cli health-card
```

## 3. macOS Permissions and Runtime

1. Launch native mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```
2. In macOS `System Settings -> Privacy & Security -> Accessibility`, allow Terminal/iTerm/Python host process.
3. Validate status indicator behavior:
- `CIO` while running normally
- `CIO-P` in protected context
- `CIO-II` when panic hotkey is engaged

## 4. Hotkey and Profile Checks

Default hotkeys:
- Panic toggle: `ctrl+option+p`
- Undo: `ctrl+option+z`

Optional overrides:
```bash
export COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p
export COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z
```

Profile expectations:
- Unknown app profile => do nothing
- Code/terminal => do nothing
- Protected contexts => no capture, no suggestions

## 5. Evidence and Privacy Checks

View latest ledger events:
```bash
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
```

Export ledger:
```bash
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --export-path ./ledger.json
```

Reset local data:
```bash
PYTHONPATH=src python -m cognitiveio.cli delete-all --confirm
```

## 6. Pre-Launch Checklist (Before Twitter/X)

1. `pytest -q` passes locally.
2. `./run_demo.sh` output matches expected episodes.
3. `proof-report` and `health-card` generate correctly.
4. Protected mode and panic mode indicators verified in native mac mode.
5. README, testing guide, and blog post are up to date.
6. Repo pushed and publicly accessible on GitHub.
