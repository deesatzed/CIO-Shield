# CIO-II

CIO-II is a local-first typing assistant for macOS that is designed to be helpful without taking control away from you.

It is intentionally **not autocorrect**.

It is now also more than typo cleanup:
- context-aware phrase expansion (`asap` -> `as soon as possible` in writing contexts)
- concept normalization (`api` -> `Application Programming Interface` where appropriate)
- secure secret-alias replacement (`{{SECRET:NAME}}`) with provider-backed resolution, rotation support, and redacted logs

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
4. Candidate ambiguity => `do_nothing` unless optional safe arbiter path is enabled.
5. Optional Apple FM path is selector-only:
- can choose from provided candidates
- or return `do_nothing`
- cannot invent replacement text

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
- macOS
- Python 3.11+
- `uv` installed

### Setup
```bash
cd /Volumes/WS4TB/CIO-II
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"
```

Optional Apple FM (still off by default):
```bash
# install local python-apple-fm-sdk from parent repo
uv pip install -e ..
```

## First 10 Minutes (New User Walkthrough)
1. Run deterministic demo:
```bash
./run_demo.sh
```
2. Print proof report:
```bash
PYTHONPATH=src python -m cognitiveio.cli proof-report
```
3. Print health card:
```bash
PYTHONPATH=src python -m cognitiveio.cli health-card
```
4. View privacy ledger:
```bash
PYTHONPATH=src python -m cognitiveio.cli privacy-ledger --limit 25
```
5. Try native macOS mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

## Daily Commands
```bash
# Headless interactive mode
./run.sh

# Auto mode (falls back to headless if mac event tap is unavailable)
PYTHONPATH=src python -m cognitiveio.cli run --mode auto

# Native macOS event-tap mode (strict)
PYTHONPATH=src python -m cognitiveio.cli run --mode mac

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

# Schema check
PYTHONPATH=src python -m cognitiveio.cli schema-check

# Seed common phrase/concept assets
PYTHONPATH=src python -m cognitiveio.cli seed-language-assets

# Delete all local CIO-II data
PYTHONPATH=src python -m cognitiveio.cli delete-all --confirm
```

## Native macOS UX and Controls
1. Menu bar states:
- `CIO`: running
- `CIO-P`: protected mode active
- `CIO-II`: paused
2. Suggestion controls:
- `Tab`: accept suggestion
- `Esc`: dismiss suggestion
3. Hotkeys (default):
- panic toggle: `ctrl+option+p`
- undo: `ctrl+option+z`

## Runtime Defaults
- `suggest_only = true`
- `auto_apply_enabled = false`
- `apple_fm_enabled = false`
- `apple_fm_variant` is AB-assigned (`A` or `B`) unless forced via `COGNITIVEIO_ARB_VARIANT`
- unknown/code/terminal profiles default to `do_nothing`

## Environment Variables You May Actually Use
```bash
# Change local data location
export COGNITIVEIO_HOME=/path/to/local/dir

# Enable optional Apple FM arbiter
export COGNITIVEIO_ENABLE_APPLE_FM=1

# Force FM variant A or B
export COGNITIVEIO_ARB_VARIANT=B

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
3. “I want a clean reset”:
- run `delete-all --confirm`
4. “I only want local behavior”:
- leave Apple FM disabled (default)

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
- `docs/BLOG_CIO_II_LAUNCH.md`
- `docs/index.html`

## GitHub Pages (Optional)
To publish the docs landing page:
1. Open repo settings for `deesatzed/CIO-II`.
2. Go to `Pages`.
3. Set source to `Deploy from a branch`.
4. Select branch `main` and folder `/docs`.
5. Save.
