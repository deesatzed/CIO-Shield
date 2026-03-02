# CIO-II

CIO-II is an on-device, trust-first writing assistant for macOS.

It uses the internal Apple FM on-chip model as a **constrained arbiter**:
- deterministic logic proposes known safe candidates
- Apple FM can select a candidate ID or choose `do_nothing`
- the model never generates replacement text

It is intentionally **not autocorrect** and more than typo cleanup:
- context-aware phrase expansion (`asap` -> `as soon as possible` in writing contexts)
- concept normalization (`api` -> `Application Programming Interface` where appropriate)
- secure secret-alias replacement (`{{SECRET:NAME}}`) with provider-backed resolution, rotation support, and redacted logs

## Main Benefit of the Internal Apple FM On-Chip LLM
Yes, this is a core architectural advantage.

The main benefit is better decisions in ambiguous gray-zone cases:
- deterministic rules surface candidate options
- Apple FM can rank/select only from those known candidates
- if confidence stays weak, it returns `do_nothing`

Practical outcome:
- fewer wrong interventions than aggressive autocorrect
- higher accept-rate and lower dismiss/undo rate on borderline cases
- no freeform text invention and no cloud dependency for arbitration
- measurable trust outcomes via local proof reports and privacy ledger

## What Problem It Solves
If you type a lot every day, small errors add up:
- repeated typos (`teh`, `recieve`, `wierd`)
- switching context between writing and fixing
- losing trust when tools rewrite text incorrectly

CIO-II reduces that friction while preserving your intent.

## Who This Is For
This project is for Mac users who:
- type frequently in email, docs, chat, and notes
- want assistance without cloud dependency
- care about auditability and safety controls
- have moderate technical comfort, but are not full-time software engineers

## Why Someone Would Use It (Benefits)
1. Fewer interruptions while writing:
- suggestions appear only at safe moments (word boundary + idle pause)
- no popups, no blocking dialogs
2. More trust than autocorrect:
- default is suggest-only
- you choose with `Tab` (accept) or `Esc` (dismiss)
- undo path is explicit and tracked
3. Better privacy posture:
- local-only storage
- privacy ledger of blocked/stored events
- no raw keystroke stream persisted
4. Predictable safety behavior:
- protected contexts block intervention
- unknown/code/terminal contexts default to no action
- panic hotkey can pause everything instantly

## Real Use Cases
1. Email and support replies:
- Benefit: catches repeated high-confidence typos without silently changing meaning
2. Writing documentation:
- Benefit: keeps flow; suggestion appears only when you pause naturally
3. Fast note-taking:
- Benefit: if typing is very fast, CIO-II suppresses suggestions to avoid noise
4. Sensitive workflows:
- Benefit: in password/protected contexts, it blocks capture and intervention
5. Mixed work (writing + coding):
- Benefit: in code/terminal profiles it does nothing, so identifiers are not touched

## What Makes It “Not Autocorrect”
1. Default mode is `suggest-only`, not silent replacement.
2. Unknown profile => `do_nothing`.
3. Code/terminal profile => `do_nothing`.
4. Candidate ambiguity => on-chip FM selector decides, or fail-safe `do_nothing`.
5. Apple FM path is selector-only:
- can choose from provided candidates
- or return `do_nothing`
- cannot invent replacement text
- is intended to improve ambiguous-case precision, not to generate text

## What Makes It More Than Autocomplete
1. Phrase intelligence:
- learns and serves reusable phrase patterns by context profile (email/docs/chat).
2. Concept intelligence:
- maps shorthand concepts to canonical terms safely (`mvp`, `api`, `sla`, etc.).
3. Hybrid assistance:
- suggest-first by default; optional auto-apply is tightly gated by confidence and safety policy.
4. Secure token workflows:
- supports alias-based insertion (`{{SECRET:...}}`) with provider lookup and no plaintext secret storage in ledger/report data.

## Safety and Privacy Model (Plain Language)
1. Protected Mode:
- If password field/excluded context is detected, CIO-II blocks action.
- Indicator state reflects this in native mode (`CIO-P`).
2. Panic key:
- Immediately pauses observation/intervention (`CIO-II` status in menu bar).
3. Local data:
- Stored in local SQLite under `~/.cognitiveio` (or configured path).
- Includes learned patterns, privacy ledger, and proof reports.
4. Auditability:
- `proof-report` shows accept/dismiss/undo/block rates.
- `privacy-ledger` shows blocked reasons and minimal event metadata.

## Installation (Recommended: `uv`)

### Requirements
- Apple Silicon Mac (`arm64`)
- macOS `26.0+`
- Python 3.11+
- `uv` installed
- Apple Intelligence enabled (for on-chip FM runtime availability)

### Build Requirements (Apple FM SDK)
- Full Xcode `26.0+` (not only Command Line Tools)

### Setup
```bash
cd /Volumes/WS4TB/CIO-II
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"
```

Apple FM SDK for on-chip arbiter integration (builds local bindings):
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
```
If unavailable, CIO-II remains fail-safe and blocks ambiguous gray-zone interventions.

## First 10 Minutes (New User Walkthrough)
1. Run deterministic demo:
```bash
./run_demo.sh
```
2. Verify platform requirements:
```bash
PYTHONPATH=src python -m cognitiveio.cli requirements-check
```
3. Print proof report:
```bash
PYTHONPATH=src python -m cognitiveio.cli proof-report
```
4. Print health card:
```bash
PYTHONPATH=src python -m cognitiveio.cli health-card
```
5. View privacy ledger:
```bash
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
```
6. Try native macOS mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

## Daily Commands
```bash
# Headless interactive mode
./run.sh

# Auto mode (falls back to headless if mac event tap is unavailable)
# Runs platform preflight checks by default.
PYTHONPATH=src python -m cognitiveio.cli run --mode auto

# Native macOS event-tap mode (strict)
# Runs platform preflight checks by default.
PYTHONPATH=src python -m cognitiveio.cli run --mode mac

# Bypass preflight temporarily (not recommended)
PYTHONPATH=src python -m cognitiveio.cli run --mode mac --skip-preflight

# Demo mode
./run_demo.sh

# Reports
PYTHONPATH=src python -m cognitiveio.cli proof-report
PYTHONPATH=src python -m cognitiveio.cli health-card

# Privacy ledger
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --export-path ./ledger.json

# FM arbiter status
PYTHONPATH=src python -m cognitiveio.cli arbiter-status

# Check Apple chip/macOS/Xcode/FM runtime requirements
PYTHONPATH=src python -m cognitiveio.cli requirements-check

# Schema check
PYTHONPATH=src python -m cognitiveio.cli schema-check

# Seed common phrase/concept assets
PYTHONPATH=src python -m cognitiveio.cli seed-language-assets

# Explain latest runtime decision
PYTHONPATH=src python -m cognitiveio.cli explain-last
PYTHONPATH=src python -m cognitiveio.cli explain-last --json

# Show required secret aliases registered from suggestions
PYTHONPATH=src python -m cognitiveio.cli required-secrets --limit 100

# Add/list/remove phrase expansions
PYTHONPATH=src python -m cognitiveio.cli phrase-add ".meW" $'Best,\nYour Name\nYour Role\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99
PYTHONPATH=src python -m cognitiveio.cli phrase-list --profile email_docs
PYTHONPATH=src python -m cognitiveio.cli phrase-remove ".meW" --profile email_docs

# Delete all local CIO-II data
PYTHONPATH=src python -m cognitiveio.cli delete-all --confirm
```

## Dot-Phrase Examples
1. Work signature in email/docs context:
```bash
PYTHONPATH=src python -m cognitiveio.cli phrase-add ".meW" $'Best,\nYour Name\nYour Role\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99
```

2. Prompt scaffold for technical analysis:
```bash
PYTHONPATH=src python -m cognitiveio.cli phrase-add ".TS1" "For these issues, complete an in-depth root cause analysis of the top 4 causes arranged by probability. For each cause, generate 3 mitigations arranged by probability. Lastly, reassess all outputs and develop the mitigation plan." --profile email_docs --confidence 0.97
```

3. Secret aliases for signature fields:
```bash
export COGNITIVEIO_SECRET_WORK_EMAIL='you@company.com'
export COGNITIVEIO_SECRET_WORK_PHONE='+1-555-555-1212'
```

4. Use:
- Type `.meW` or `.TS1` followed by a boundary (space/enter/punctuation).
- Press `Tab` to accept or `Esc` to dismiss.

## Native macOS UX and Controls
1. Menu bar states:
- `CIO`: running
- `CIO-P`: protected mode active
- `CIO-II`: paused
2. Menu bar actions:
- `Pause Suggestions` / `Resume Suggestions`: toggle panic mode
- `Explain Last Decision`: prints action/reason/profile/token summary in terminal
- `Show Required Secrets`: prints tracked alias names from local registry
- `Manage Dot-Phrases`: prints quick CLI commands and current triggers
3. Trust feedback:
- if trust cooldown is active, status shows `Trust cooldown active (Ns)`
4. Suggestion controls:
- `Tab`: accept suggestion
- `Esc`: dismiss suggestion
- unresolved secret alias on accept is fail-closed with a clear status/terminal message
5. Hotkeys (default):
- panic toggle: `ctrl+option+p`
- undo: `ctrl+option+z`

## Runtime Defaults
- `suggest_only = true`
- `auto_apply_enabled = false`
- `apple_fm_enabled = true`
- `apple_fm_variant = B` by default
- `apple_fm_ab_enabled = false` by default
- `fm_required_for_gray_zone = true` (fail-closed if FM arbiter unavailable in gray-zone)
- unknown/code/terminal profiles default to `do_nothing`

## Environment Variables You May Actually Use
```bash
# Change local data location
export COGNITIVEIO_HOME=/path/to/local/dir

# Disable Apple FM arbiter (deterministic-only fallback mode)
export COGNITIVEIO_ENABLE_APPLE_FM=0

# Force FM variant A or B
export COGNITIVEIO_ARB_VARIANT=B

# Require FM for gray-zone decisions (default = 1)
export COGNITIVEIO_FM_REQUIRED_FOR_GRAY_ZONE=1

# Override hotkeys
export COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p
export COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z

# Local store encryption mode: off|optional|required
export COGNITIVEIO_DB_ENCRYPTION=optional

# Optional db key alias reference (resolved from env or secret provider)
export COGNITIVEIO_DB_KEY_REF='{{SECRET:COGNITIVEIO_DB_KEY}}'

# Env-backed secret source example
export COGNITIVEIO_SECRET_COGNITIVEIO_DB_KEY='replace-me'
```

## Troubleshooting
1. “No suggestions appear”:
- check you are at a word boundary
- check idle pause is reached
- check profile is not code/terminal/unknown
- check trust cooldown is not active
2. “mac mode doesn’t work”:
- grant Accessibility permission in macOS settings for your terminal/python process
3. “requirements-check fails”:
- verify machine architecture is `arm64`
- verify `sw_vers -productVersion` is `26.0+`
- verify `xcodebuild -version` is `26.0+`
- verify `xcode-select -p` points to `/Applications/Xcode.app/Contents/Developer`
- if details show `sdk_import_error:*`, run:
  `git clone https://github.com/apple/python-apple-fm-sdk`
  `uv pip install -e ./python-apple-fm-sdk`
  or
  `uv pip install -e ../python-apple-fm-sdk`
  or `uv pip install -e /absolute/path/to/python-apple-fm-sdk`
4. “I want a clean reset”:
- run `delete-all --confirm`
5. “I want deterministic-only fallback mode”:
- set `COGNITIVEIO_ENABLE_APPLE_FM=0`
6. “Accept says missing secret alias”:
- run `PYTHONPATH=src python -m cognitiveio.cli required-secrets`
- set missing env vars like `COGNITIVEIO_SECRET_WORK_EMAIL=...`
- retry accept
7. “Too many do-nothing outcomes in ambiguous cases”:
- ensure Apple FM SDK is installed and available
- run `PYTHONPATH=src python -m cognitiveio.cli arbiter-status`
- confirm `apple_fm_enabled=True` and `fm_required_for_gray_zone=True`

## Testing and Release Readiness
```bash
pytest -q
./run_demo.sh
PYTHONPATH=src python -m cognitiveio.cli proof-report
PYTHONPATH=src python -m cognitiveio.cli health-card
./verify-mitigations.sh
```

## Documentation Map
- `docs/PRODUCT_CONTRACT.md`
- `docs/FEATURE_MATRIX.md`
- `docs/IMPLEMENTATION_ROADMAP.md`
- `docs/STARTUP_PROCEDURES.md`
- `docs/TESTING_GUIDE.md`
- `docs/DEMO_SCRIPT.md`
- `docs/GIT_WORKFLOW.md`
- `docs/TEST_PLAN_FEATURE_MATRIX.md`
- `docs/BLOG_CIO_II_LAUNCH.md`
- `docs/index.html`

## GitHub Pages (Optional)
To publish the docs landing page:
1. Open repo settings for `deesatzed/CIO-II`.
2. Go to `Pages`.
3. Set source to `Deploy from a branch`.
4. Select branch `main` and folder `/docs`.
5. Save.
