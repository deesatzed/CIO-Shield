# CIO-II Startup Procedures

This is the launch runbook for operating CIO-II safely and predictably on macOS.

## 1. Environment Setup

```bash
cd CIO-II   # your clone directory
./bootstrap.sh
```

`bootstrap.sh` creates `.venv`, installs CIO-II dependencies, installs `apple_fm_sdk` (cloning if needed), and runs `requirements-check`.

Apple FM path (recommended for FM-first secure gray-zone decisions):
```bash
# clone locally if you do not already have the SDK repo:
git clone https://github.com/apple/python-apple-fm-sdk

# install from cloned folder:
uv pip install -e ./python-apple-fm-sdk

# if sdk repo is sibling of CIO-II:
uv pip install -e ../python-apple-fm-sdk

# or install from any absolute local path:
uv pip install -e /absolute/path/to/python-apple-fm-sdk

# verify sdk import in active venv:
python -c "import apple_fm_sdk; print(apple_fm_sdk.__file__)"

export COGNITIVEIO_ENABLE_APPLE_FM=1
export COGNITIVEIO_ARB_VARIANT=B
```
Use this for on-chip gray-zone arbitration. Apple FM remains constrained to selecting known candidates or `do_nothing`.

## 2. First-Run Safety Validation

1. Start deterministic demo:
```bash
./run_demo.sh
```
2. Validate platform requirements:
```bash
cio-ii requirements-check
```
3. Run automated user-journey validation:
```bash
./validate-user-journey.sh
```
4. Confirm demo includes:
- Protected mode blocked event
- Suggest-only acceptance
- No code-profile intervention
- Candidate-conflict guard event
- Trust circuit breaker cooldown event
- Undo event
5. Print proof report:
```bash
cio-ii proof-report
```
6. Print health card:
```bash
cio-ii health-card
```
7. Seed common language assets:
```bash
cio-ii seed-language-assets
```
8. Add dot-phrase examples:
```bash
cio-ii phrase-add ".meW" $'Best,\nYour Name\nYour Role\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99
cio-ii phrase-add ".TS1" "For these issues, complete an in-depth root cause analysis of the top 4 causes arranged by probability. For each cause, generate 3 mitigations arranged by probability. Lastly, reassess all outputs and develop the mitigation plan." --profile email_docs --confidence 0.97
cio-ii phrase-list --profile email_docs
```
9. Validate explainability and secret inventory commands:
```bash
cio-ii explain-last
cio-ii required-secrets --limit 100
```

## 3. macOS Permissions and Runtime

1. Launch native mode:
```bash
cio-ii run --mode mac
```
For safer default behavior, use auto mode:
```bash
cio-ii run --mode auto
```
Both run commands execute platform preflight checks by default. Use `--skip-preflight` only for temporary diagnostics.
2. In macOS `System Settings -> Privacy & Security -> Accessibility`, allow Terminal/iTerm/Python host process.
3. Validate status indicator behavior:
- `CIO` while running normally
- `CIO-P` in protected context
- `CIO-II` when panic hotkey is engaged
4. Validate menu actions:
- `Pause Suggestions` / `Resume Suggestions`
- `Explain Last Decision`
- `Show Required Secrets`
- `Manage Dot-Phrases`

## 4. Hotkey and Profile Checks

Default hotkeys:
- Panic toggle: `ctrl+option+p`
- Undo: `ctrl+option+z`

Optional overrides:
```bash
export COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p
export COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z
export COGNITIVEIO_DB_ENCRYPTION=optional
export COGNITIVEIO_DB_KEY_REF='{{SECRET:COGNITIVEIO_DB_KEY}}'
export COGNITIVEIO_SECRET_COGNITIVEIO_DB_KEY='replace-me'
```

Profile expectations:
- Unknown app profile => do nothing
- Code/terminal => do nothing
- Protected contexts => no capture, no suggestions

## 5. Evidence and Privacy Checks

View latest ledger events:
```bash
cio-ii privacy-ledger --limit 25
```

Export ledger:
```bash
cio-ii privacy-ledger --export-path ./ledger.json
```

Reset local data:
```bash
cio-ii delete-all --confirm
```

## 6. Pre-Launch Checklist (Before Twitter/X)

1. `pytest -q` passes locally.
2. `./validate-user-journey.sh` passes locally.
3. `./run_demo.sh` output matches expected episodes.
4. `proof-report` and `health-card` generate correctly.
5. Protected mode and panic mode indicators verified in native mac mode.
6. README, testing guide, and blog post are up to date.
7. Repo pushed and publicly accessible on GitHub.
