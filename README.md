# CIO-II

**Writing assistance powered by Apple's on-chip AI — not the cloud.**

[![CI](https://github.com/deesatzed/CIO-II/actions/workflows/ci.yml/badge.svg)](https://github.com/deesatzed/CIO-II/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![macOS arm64](https://img.shields.io/badge/macOS-arm64%20(Apple%20Silicon)-silver)
![Local Only](https://img.shields.io/badge/data-local%20only-green)

---

CIO-II is a local-first writing assistant for macOS that uses the **Apple Foundation Model running on your Mac's neural engine** to make smarter decisions about when and how to help you write.

To our knowledge, CIO-II is the **first open-source macOS application to use Apple's on-device Foundation Model** (`python-apple-fm-sdk` / `SystemLanguageModel`) for real-time writing assistance.

It does not generate text. It does not phone home. It watches you type and, only when it is confident, offers a suggestion you can accept with `Tab` or dismiss with `Esc`. If it is not confident, it does nothing.

## How It Works

When you type in an email or document, CIO-II watches for patterns it recognizes — common typos, phrase shortcuts you have configured, abbreviations that could be expanded. When it finds a match, it checks whether the context is safe for a suggestion.

If the situation is ambiguous — two plausible corrections, borderline confidence — CIO-II asks the **Apple Foundation Model running on your Mac's neural engine** to make the call. The model can only pick from options CIO-II already identified, or decide to do nothing. It cannot invent replacement text. It has 80 milliseconds to decide; if it cannot, the answer is do nothing.

You see a suggestion. Press `Tab` to accept, `Esc` to dismiss. That is it.

## Why This Is Different

|  | **CIO-II** | macOS Autocorrect | Grammarly | TextExpander |
|---|---|---|---|---|
| **On-device AI** | Apple FM on-chip neural engine | Basic dictionary | Cloud AI | No AI |
| **Suggests vs. replaces** | Suggest-only by default | Silent replacement | Inline rewrite | Trigger-based |
| **Works without internet** | Fully local | Yes | No | Yes |
| **Blocks in password fields** | Hard block, no capture | No | No | No |
| **Undo with audit trail** | Tracked and reversible | System undo only | No | No |
| **Learns from your corrections** | Local memory, adapts over time | No | Cloud profile | Manual |
| **Trust circuit breaker** | Backs off when you dismiss repeatedly | No | No | No |
| **Knows when to do nothing** | Unknown/code/terminal contexts = no action | No | No | No |
| **Open source** | Yes | No | No | No |

## What Problem It Solves

Most people have seen the same failure pattern with writing tools: autocorrect changes the wrong word, you notice too late, and trust is lost quickly.

If you type a lot every day, small friction adds up:
- Repeated typos that you fix manually every time (`teh`, `recieve`, `wierd`)
- Switching context between writing and fixing
- Losing trust when a tool silently rewrites what you meant to say

CIO-II reduces that friction while preserving your intent. The default is always to suggest, never to silently replace.

## Who This Is For

Mac users who type frequently and want assistance without surprises:
- Operations and support staff handling high-volume email
- Founders and product managers writing docs all day
- Analysts and researchers drafting reports
- Students and writers who need flow, not interruption
- Anyone who types a lot but does not want AI to "take the wheel"

You need moderate technical comfort to install it (command line), but you do not need to be a software engineer to use it.

## Real Examples

**Typo in Mail** — You type `teh` in an email. At a natural pause, CIO-II offers `the`. Press `Tab` to accept or `Esc` to dismiss.

**Writing in VS Code** — You are editing code. CIO-II detects a code profile and does nothing. Your identifiers and commands are never touched.

**Password field** — You are in a login form or password manager. CIO-II hard-blocks all capture and suggestions. The menu bar shows `CIO-P` (protected).

**Repeated dismissals** — You keep dismissing suggestions. CIO-II enters a trust cooldown and stops suggesting temporarily. The menu bar shows the countdown.

**Dot-phrase expansion** — You type `.meW` in an email and CIO-II expands it to your full work signature, including secret-alias fields that resolve at apply-time without ever storing plaintext.

**Ambiguous correction** — You type `wierd` and there are two plausible corrections. Instead of guessing, CIO-II asks the Apple FM model on your chip to pick the best one — or do nothing if confidence is low.

## Quick Start

```bash
git clone https://github.com/deesatzed/CIO-II.git
cd CIO-II
./bootstrap.sh
```

`bootstrap.sh` creates the virtual environment, installs dependencies, clones and builds the Apple FM SDK, and verifies your platform requirements.

Then try it:
```bash
# Run the deterministic demo (see all safety behaviors in action)
./run_demo.sh

# Start native macOS mode (menu bar, hotkeys, real-time suggestions)
cio-ii run --mode mac
```

## Verify It Works

```bash
./run_demo.sh                    # 7 demo episodes, all should match expected outcomes
cio-ii requirements-check        # All platform requirement rows show PASS
./verify-mitigations.sh          # Prints: ALL MITIGATIONS VERIFIED
./validate-user-journey.sh       # Prints: USER JOURNEY VALIDATED
```

---

# Reference

Everything below is detailed technical reference. Click any section to expand.

<details>
<summary><strong>Installation Details</strong></summary>

### Requirements
- Apple Silicon Mac (`arm64`)
- macOS 26.0+
- Python 3.11+
- `uv` installed ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- Apple Intelligence enabled (for on-chip FM runtime availability)

### Build Requirements (Apple FM SDK)
- Full Xcode 26.0+ (not only Command Line Tools)

### What bootstrap.sh Does
1. Creates `.venv` with Python 3.11+
2. Installs CIO-II and all dependencies
3. Clones `python-apple-fm-sdk` and builds it locally
4. Runs `requirements-check` to verify your platform

### Manual Apple FM SDK Install
If you need to install the SDK separately:
```bash
# Clone the SDK repo
git clone https://github.com/apple/python-apple-fm-sdk

# Install from the cloned folder
uv pip install -e ./python-apple-fm-sdk

# Or if the SDK repo is a sibling of CIO-II
uv pip install -e ../python-apple-fm-sdk

# Verify it works
python -c "import apple_fm_sdk; print(apple_fm_sdk.__file__)"
```

If the Apple FM SDK is unavailable, CIO-II remains fully functional in deterministic-only mode — it simply blocks ambiguous gray-zone interventions instead of routing them to the FM arbiter.

</details>

<details>
<summary><strong>Daily Commands</strong></summary>

```bash
# Start modes
cio-ii run --mode mac             # Native macOS mode (menu bar, hotkeys, event tap)
cio-ii run --mode auto            # Auto mode (falls back to headless if event tap unavailable)
./run.sh                          # Headless interactive mode
./run_demo.sh                     # Deterministic demo

# Reports and status
cio-ii proof-report               # Accept/dismiss/undo/block rates
cio-ii health-card                # System health overview
cio-ii arbiter-status             # Apple FM arbiter state
cio-ii requirements-check         # Platform requirement checks
cio-ii schema-check               # Database schema validation
cio-ii explain-last               # Latest runtime decision details
cio-ii explain-last --json        # Same, in JSON format

# Privacy
cio-ii privacy-ledger --limit 25              # View recent ledger events
cio-ii privacy-ledger --export-path ./ledger.json  # Export ledger to file

# Phrase management
cio-ii phrase-add ".meW" 'Best,\nYour Name' --profile email_docs --confidence 0.99
cio-ii phrase-list --profile email_docs
cio-ii phrase-remove ".meW" --profile email_docs

# Language assets
cio-ii seed-language-assets       # Seed common typo/concept/phrase patterns

# Secret inventory
cio-ii required-secrets --limit 100   # Show tracked secret alias names

# Reset
cio-ii delete-all --confirm       # Delete all local CIO-II data
```

</details>

<details>
<summary><strong>Dot-Phrase Examples</strong></summary>

### Work signature in email/docs context
```bash
cio-ii phrase-add ".meW" $'Best,\nYour Name\nYour Role\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99
```

### Prompt scaffold for technical analysis
```bash
cio-ii phrase-add ".TS1" "For these issues, complete an in-depth root cause analysis of the top 4 causes arranged by probability. For each cause, generate 3 mitigations arranged by probability. Lastly, reassess all outputs and develop the mitigation plan." --profile email_docs --confidence 0.97
```

### Secret aliases for signature fields
```bash
export COGNITIVEIO_SECRET_WORK_EMAIL='you@company.com'
export COGNITIVEIO_SECRET_WORK_PHONE='+1-555-555-1212'
```

### Using dot-phrases
Type `.meW` or `.TS1` followed by a boundary (space, enter, or punctuation). Press `Tab` to accept or `Esc` to dismiss.

</details>

<details>
<summary><strong>Native macOS UX and Controls</strong></summary>

### Menu bar states
- `CIO` — running normally
- `CIO-P` — protected mode active (password field or excluded app)
- `CIO-II` — paused (panic mode)

### Menu bar actions
- **Pause Suggestions / Resume Suggestions** — toggle panic mode
- **Explain Last Decision** — prints action, reason, profile, and token summary
- **Show Required Secrets** — prints tracked alias names from local registry
- **Manage Dot-Phrases** — prints current triggers and CLI commands

### Trust feedback
When trust cooldown is active, the status shows `Trust cooldown active (Ns)` with a live countdown.

### Suggestion controls
- `Tab` — accept suggestion
- `Esc` — dismiss suggestion
- Unresolved secret alias on accept is fail-closed with a clear message

### Hotkeys (default)
- Panic toggle: `ctrl+option+p`
- Undo: `ctrl+option+z`

</details>

<details>
<summary><strong>Safety and Privacy Model</strong></summary>

### Protected Mode
If a password field or excluded context is detected, CIO-II hard-blocks all capture and suggestions. The menu bar indicator shows `CIO-P`.

### Panic Key
`ctrl+option+p` immediately pauses all observation and intervention. Menu bar shows `CIO-II`.

### Local Data
All data is stored in local SQLite under `~/.cognitiveio` (or a configured path). This includes learned patterns, the privacy ledger, and proof reports. Nothing leaves your machine.

### Auditability
- `cio-ii proof-report` — shows accept/dismiss/undo/block rates with trendlines
- `cio-ii privacy-ledger` — shows blocked reasons and minimal event metadata
- No raw keystroke stream is ever persisted

### What CIO-II Will Never Do
- Silently replace text without showing you first (suggest-only is default)
- Intervene in code editors, terminals, or unknown applications
- Send data to a cloud service
- Store raw keystrokes
- Generate replacement text (the AI model can only select from known candidates)

</details>

<details>
<summary><strong>Environment Variables</strong></summary>

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

# Local store encryption mode: off | optional | required
export COGNITIVEIO_DB_ENCRYPTION=optional

# Optional DB key alias reference
export COGNITIVEIO_DB_KEY_REF='{{SECRET:COGNITIVEIO_DB_KEY}}'

# Env-backed secret source example
export COGNITIVEIO_SECRET_COGNITIVEIO_DB_KEY='replace-me'
```

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

**"No suggestions appear"**
- Check you are at a word boundary (space, punctuation)
- Check idle pause has been reached (default 300ms)
- Check profile is not code/terminal/unknown
- Check trust cooldown is not active

**"Mac mode doesn't work"**
- Grant Accessibility permission in macOS `System Settings > Privacy & Security > Accessibility` for your terminal or Python process

**"requirements-check fails"**
- Verify machine architecture is `arm64`
- Verify `sw_vers -productVersion` is 26.0+
- Verify `xcodebuild -version` is 26.0+
- Verify `xcode-select -p` points to `/Applications/Xcode.app/Contents/Developer`
- If details show `sdk_import_error:*`, run `./bootstrap.sh`

**"I want a clean reset"**
- Run `cio-ii delete-all --confirm`

**"I want deterministic-only mode (no FM)"**
- Set `COGNITIVEIO_ENABLE_APPLE_FM=0`

**"Accept says missing secret alias"**
- Run `cio-ii required-secrets` to see which aliases are needed
- Set the missing env vars (e.g., `export COGNITIVEIO_SECRET_WORK_EMAIL=...`)
- Retry accept

**"Too many do-nothing outcomes in ambiguous cases"**
- Ensure Apple FM SDK is installed: `cio-ii arbiter-status`
- Confirm `apple_fm_enabled=True` and `fm_required_for_gray_zone=True`

</details>

<details>
<summary><strong>Further Reading</strong></summary>

- `docs/PRODUCT_CONTRACT.md` — safety invariants and design guarantees
- `docs/FEATURE_MATRIX.md` — full feature list with priority and complexity
- `docs/STARTUP_PROCEDURES.md` — platform setup and detailed troubleshooting
- `docs/DEMO_SCRIPT.md` — what the deterministic demo covers
- `docs/BLOG_CIO_II_LAUNCH.md` — launch blog post

</details>
