# CIO-II

**The first open-source macOS app to use Apple's on-device Foundation Model for writing assistance.**

[![CI](https://github.com/deesatzed/CIO-II/actions/workflows/ci.yml/badge.svg)](https://github.com/deesatzed/CIO-II/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![macOS arm64](https://img.shields.io/badge/macOS-arm64%20(Apple%20Silicon)-silver)
![Local Only](https://img.shields.io/badge/data-local%20only-green)
![331 tests](https://img.shields.io/badge/tests-331%20passed-brightgreen)
![94% coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)

---

## What It Is

CIO-II is a writing assistant that runs entirely on your Mac. It watches you type and, when confident, shows a suggestion you accept with `Tab` or dismiss with `Esc`.

When the decision is ambiguous — two plausible corrections, borderline confidence — it routes to the **Apple Foundation Model running on your Mac's neural engine**. The model picks the best option or decides to do nothing. It has 80 milliseconds. If it cannot decide, it does nothing.

The model **never generates text**. It can only select from candidates CIO-II already identified, or return "do nothing." This is the core safety guarantee.

---

## Why You Would Want This

**If you type a lot every day**, you know the pattern:
- You type `teh` for the 50th time this week and fix it manually
- Autocorrect silently changes "its" to "it's" in a sentence where you meant "its"
- You are in a password field and autocorrect overwrites your password
- You stop trusting the tool and turn it off entirely

CIO-II fixes this by being **trustworthy first**:

| Problem | CIO-II Solution |
|---------|----------------|
| Autocorrect silently changes words | CIO-II only **suggests** — never silently replaces |
| Corrections in code/terminal break things | CIO-II **does nothing** in code editors and terminals |
| Password fields get corrupted | CIO-II **hard-blocks** all capture in password fields |
| You can't undo what just happened | Every CIO-II change has a **tracked undo** (`ctrl+option+z`) |
| You dismiss suggestions but they keep coming | CIO-II **backs off** — trust circuit breaker pauses suggestions |
| Your typing data goes to a cloud server | CIO-II is **100% local** — no network calls, no telemetry |

---

## What It Can Do — Real Examples

### Typo correction in Mail

You are writing an email in Apple Mail. You type:

> "I'll send teh report by end of day"

At the natural pause after `teh`, CIO-II shows a ghost suggestion: `the`. You press `Tab` and the text becomes `the`. Press `Esc` and nothing changes.

**What happens under the hood**: CIO-II detects you are in an `email_docs` profile (Apple Mail), finds `teh` in its pattern memory with high confidence, and suggests the correction. No ambiguity, no FM call needed.

---

### Ambiguous correction with Apple FM arbiter

You type `wierd` in a document. CIO-II finds two candidates: `weird` and `wired`. Deterministic logic cannot choose — both are valid English words.

CIO-II asks the Apple FM model on your neural engine: "Given the context, which correction is appropriate — `weird` or `wired`? Or do nothing?"

The FM reads surrounding context, picks `weird`, and CIO-II shows the suggestion. If the FM is uncertain, it returns `do_nothing` and you see nothing.

**This entire decision takes under 80ms on the neural engine. No internet. No cloud.**

---

### No interference in VS Code

You are writing Python in VS Code:

```python
def teh_function():
    return wierd_value
```

CIO-II detects the `code` profile and does **nothing**. Your variable names, function names, and commands are never touched. This is a hard rule — code and terminal profiles always default to `do_nothing`.

---

### Password field protection

You navigate to a login page in Safari. You click the password field.

CIO-II immediately enters **Protected Mode**. The menu bar changes from `CIO` to `CIO-P`. All keystroke observation stops. No capture, no suggestions, no data recorded. When you leave the password field, normal operation resumes.

This is not a preference — it is a hard safety block that cannot be overridden.

---

### Dot-phrase expansion for repeated text blocks

You configure a work signature:

```bash
cio-ii phrase-add ".meW" $'Best regards,\nDr. Sarah Chen\nChief Medical Officer\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99
```

Now in any email or document, you type `.meW` followed by a space. CIO-II offers to expand it to your full signature. The `{{SECRET:WORK_EMAIL}}` placeholder resolves at apply-time from your environment variable — the actual email address is never stored in CIO-II's database.

If the secret is missing, CIO-II **refuses to insert** and shows an explicit error instead of pasting unresolved placeholder text.

---

### Technical analysis prompt scaffold

```bash
cio-ii phrase-add ".RCA" "For these issues, complete an in-depth root cause analysis of the top 4 causes arranged by probability. For each cause, generate 3 mitigations arranged by probability. Lastly, reassess all outputs and develop the mitigation plan." --profile email_docs --confidence 0.97
```

Type `.RCA` in a document and Tab to expand a full analysis scaffold you use repeatedly — without retyping it every time.

---

### Trust circuit breaker

You dismiss 3 suggestions in a row. CIO-II detects dense negative signals and enters a **trust cooldown**. The menu bar shows `Trust cooldown active (119s remaining)`.

During cooldown, CIO-II stops suggesting entirely. After the cooldown expires, it resumes — but with recalibrated confidence thresholds. If you keep dismissing, cooldowns get longer.

This prevents the "nagware" problem where a tool keeps interrupting you after you have made clear you do not want help right now.

---

### Concept normalization

You type `api` in an email context. CIO-II can suggest `Application Programming Interface` when the confidence and context indicate formal writing. In casual chat contexts, it leaves `api` alone.

Other examples: `sla` can expand to `Service Level Agreement`, `mvp` to `Minimum Viable Product` — but only in formal contexts and only as suggestions.

---

### Instant panic stop

At any time, press `ctrl+option+p`. CIO-II immediately stops all observation and intervention. The menu bar shows `CIO-II` (paused). Press again to resume. This is your kill switch — it works instantly regardless of what else is happening.

---

### Auditing what happened

```bash
# See accept/dismiss/undo/block rates
cio-ii proof-report

# See what CIO-II blocked and why
cio-ii privacy-ledger --limit 25

# See the last decision CIO-II made
cio-ii explain-last

# Export the ledger for review
cio-ii privacy-ledger --export-path ./my-audit.json
```

Every decision CIO-II makes is recorded locally and inspectable. You can always see exactly what happened and why.

---

## Requirements

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **Mac chip** | Apple Silicon (M1, M2, M3, M4) | `arm64` architecture required |
| **macOS** | 26.0 or later | Required for Apple FM runtime |
| **Xcode** | 26.0 or later (full install) | Command Line Tools alone is not enough |
| **Python** | 3.11+ | Tested on 3.11, 3.12, 3.13 |
| **uv** | Any recent version | Python package installer ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **Apple Intelligence** | Enabled in System Settings | Required for FM model availability |
| **Disk space** | ~500 MB | For venv + Apple FM SDK build |

**Without Apple FM SDK**: CIO-II still works in deterministic-only mode. It blocks ambiguous cases (returns `do_nothing`) instead of routing them to the FM arbiter. All other features work normally.

---

## Install

```bash
git clone https://github.com/deesatzed/CIO-II.git
cd CIO-II
./bootstrap.sh
```

`bootstrap.sh` does everything:
1. Creates a Python virtual environment
2. Installs CIO-II and all dependencies
3. Clones and builds the Apple FM SDK from `github.com/apple/python-apple-fm-sdk`
4. Runs platform requirement checks (all rows should show PASS)

### After install

```bash
# See the demo — 7 scenarios showing all safety behaviors
./run_demo.sh

# Start native macOS mode (menu bar icon, hotkeys, real-time suggestions)
cio-ii run --mode mac
```

**Important**: macOS will ask you to grant Accessibility permission. Go to `System Settings > Privacy & Security > Accessibility` and allow your terminal or Python process.

---

## Verify Everything Works

```bash
./run_demo.sh                    # 7 demo episodes — all should match expected
cio-ii requirements-check        # All rows show PASS
./verify-mitigations.sh          # Prints: ALL MITIGATIONS VERIFIED
./validate-user-journey.sh       # Prints: USER JOURNEY VALIDATED
```

---

## How It Works (Architecture)

```
You type in Mail/Safari/Notes
         |
         v
  Event Tap (macOS Accessibility API)
         |
         v
  Profile Detection: email_docs? code? terminal? password? unknown?
         |
         v
  [password/excluded] --> HARD BLOCK (CIO-P, no capture)
  [code/terminal/unknown] --> DO NOTHING
  [email_docs/chat] --> continue
         |
         v
  Decision Engine (<5ms deterministic path)
         |
         v
  [single high-confidence candidate] --> SUGGEST
  [multiple candidates, ambiguous] --> route to Apple FM arbiter
         |                                        |
         v                                        v
  FM picks best candidate           FM returns "do_nothing"
  or times out (80ms)               (uncertain = no action)
         |
         v
  Ghost suggestion shown
         |
    Tab = accept          Esc = dismiss
         |                     |
         v                     v
  Apply + undo record    Record dismissal
                         (feeds trust circuit)
```

---

## Daily Commands

```bash
# Start
cio-ii run --mode mac             # Native macOS mode (menu bar, hotkeys, event tap)
cio-ii run --mode auto            # Auto mode (falls back to headless if needed)

# Reports
cio-ii proof-report               # Accept/dismiss/undo/block rates
cio-ii health-card                # System health overview
cio-ii explain-last               # Last decision details
cio-ii explain-last --json        # Same, in JSON

# Privacy audit
cio-ii privacy-ledger --limit 25
cio-ii privacy-ledger --export-path ./ledger.json

# Phrase management
cio-ii phrase-add ".sig" 'Best,\nYour Name' --profile email_docs --confidence 0.99
cio-ii phrase-list --profile email_docs
cio-ii phrase-remove ".sig" --profile email_docs

# Diagnostics
cio-ii arbiter-status             # Apple FM state
cio-ii requirements-check         # Platform checks
cio-ii schema-check               # Database integrity

# Seed built-in patterns
cio-ii seed-language-assets       # Load common typos, concepts, phrases

# Reset everything
cio-ii delete-all --confirm       # Delete all local CIO-II data
```

---

## Menu Bar States

| Icon | Meaning |
|------|---------|
| `CIO` | Running normally — observing and ready to suggest |
| `CIO-P` | Protected mode — password field or excluded app detected, all capture blocked |
| `CIO-II` | Paused — panic key pressed, no observation or intervention |

---

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Tab` | Accept current suggestion |
| `Esc` | Dismiss current suggestion |
| `ctrl+option+p` | Panic toggle — immediately stop/resume all observation |
| `ctrl+option+z` | Undo last accepted change |

---

## What CIO-II Will Never Do

- Silently replace text without showing you first
- Intervene in code editors, terminals, or unknown applications
- Send any data to a cloud service
- Store raw keystrokes
- Generate replacement text (the AI can only select from known candidates)
- Suggest in password fields or excluded apps
- Keep suggesting after you clearly do not want help

---

## What CIO-II Is Not

- Not a cloud service (fully local)
- Not a text generator (no GPT-style completion)
- Not "always-on autocorrect" (suggest-only, backs off)
- Not for code editing (hard do-nothing in code profiles)
- Not cross-platform (macOS Apple Silicon only)

---

## Secret Aliases

Phrases can include `{{SECRET:NAME}}` placeholders that resolve from environment variables at apply-time:

```bash
# Set secrets in your shell profile
export COGNITIVEIO_SECRET_WORK_EMAIL='sarah@hospital.org'
export COGNITIVEIO_SECRET_WORK_PHONE='+1-555-867-5309'

# Use in a phrase
cio-ii phrase-add ".meW" $'Best,\nDr. Chen\n{{SECRET:WORK_EMAIL}}\n{{SECRET:WORK_PHONE}}' --profile email_docs --confidence 0.99

# Check which secrets are needed
cio-ii required-secrets --limit 100
```

Secrets are never stored in CIO-II's database. They resolve at the moment you press Tab. If a secret is missing, the accept is blocked with an explicit message.

---

## Configuration

```bash
# Change local data location (default: ~/.cognitiveio)
export COGNITIVEIO_HOME=/path/to/dir

# Disable Apple FM (deterministic-only mode)
export COGNITIVEIO_ENABLE_APPLE_FM=0

# Change suggestion trigger delay (default 300ms)
export COGNITIVEIO_IDLE_PAUSE_MS=300

# Override hotkeys
export COGNITIVEIO_PANIC_HOTKEY=ctrl+option+p
export COGNITIVEIO_UNDO_HOTKEY=ctrl+option+z

# Enable database encryption
export COGNITIVEIO_DB_ENCRYPTION=optional   # off | optional | required
```

---

## Troubleshooting

**"No suggestions appear"**
- Verify you are in an email/docs/chat context (not code/terminal)
- Wait for the idle pause (300ms after you stop typing)
- Check trust cooldown is not active: `cio-ii health-card`
- Seed patterns if fresh install: `cio-ii seed-language-assets`

**"Mac mode does not start"**
- Grant Accessibility permission: `System Settings > Privacy & Security > Accessibility`
- Ensure you are running from the venv: `source .venv/bin/activate`

**"requirements-check fails"**
- Machine must be arm64: `uname -m`
- macOS must be 26.0+: `sw_vers -productVersion`
- Full Xcode required (not just Command Line Tools): `xcodebuild -version`
- Run `./bootstrap.sh` to rebuild the Apple FM SDK

**"FM arbiter always returns do_nothing"**
- Check FM status: `cio-ii arbiter-status`
- Verify `apple_fm_enabled=True` and `fm_required_for_gray_zone=True`
- Ensure Apple Intelligence is enabled in System Settings

**"I want to start fresh"**
- Run `cio-ii delete-all --confirm`

---

## Tested Quality

| Metric | Value |
|--------|-------|
| Automated tests | 331 passed |
| Code coverage | 94% |
| Lint (ruff) | Clean |
| Type check (mypy) | Clean |
| Demo scenarios | 7/7 pass |
| CI matrix | Python 3.11, 3.12, 3.13 on macOS |
| Test approach | No mocks — all tests use real SQLite |

---

## Further Reading

- [`docs/PRD.md`](docs/PRD.md) — Product Requirements Document
- [`docs/PRODUCT_CONTRACT.md`](docs/PRODUCT_CONTRACT.md) — Safety invariants and design guarantees
- [`docs/FEATURE_MATRIX.md`](docs/FEATURE_MATRIX.md) — Ranked feature candidates
- [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) — Sprint roadmap
- [`docs/STARTUP_PROCEDURES.md`](docs/STARTUP_PROCEDURES.md) — Detailed platform setup
- [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md) — Test procedures
- [`docs/BLOG_CIO_II_LAUNCH.md`](docs/BLOG_CIO_II_LAUNCH.md) — Launch blog post

---

## License

MIT (see LICENSE file)
