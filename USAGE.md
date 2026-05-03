# CIO-Shield Usage Guide

CIO-Shield is a local typing assistant for macOS that catches typos, expands abbreviations, and blocks secret/PII leaks — all without sending data off your machine.

## How It Works

CIO-Shield watches what you type and offers suggestions when it detects:
- **Typos** — common misspellings like "teh" → "the"
- **Abbreviations** — shortcuts like "fyi" → "for your information"
- **Secrets about to leak** — API keys, credit cards, SSNs, tokens in clipboard/paste

It **never auto-corrects**. It suggests, you decide.

---

## Running CIO-Shield

### Headless Mode (no permissions needed)

```bash
cio-ii run --mode headless
```

This is the interactive terminal mode. You type one word at a time and see suggestions:

```
token> teh
Ghost suggestion: teh -> the [/accept | /dismiss]
token> /accept
Accepted: teh -> the
```

**Commands while in headless mode:**
| Command | What it does |
|---------|-------------|
| `/accept` | Accept the current suggestion |
| `/dismiss` | Reject the current suggestion |
| `/undo` | Undo the last accepted change |
| `/panic` | Emergency stop — pauses all suggestions |
| *(empty enter)* | Exit |

### Native macOS Mode (requires accessibility permission)

```bash
cio-ii run --mode mac
```

This intercepts real keystrokes system-wide. Suggestions appear as ghost text overlays. Accept with **Tab**, dismiss with **Esc**. Requires granting Accessibility permission in System Settings > Privacy & Security.

---

## Setting Up Your Vocabulary

### Seed the default library

```bash
cio-ii seed-language-assets
```

This loads 12 common abbreviations (fyi, asap, brb, etc.) and 7 typo corrections. It's a starting point — you'll want to add your own.

### Add custom phrases

```bash
cio-ii phrase-add "omw" "on my way" --profile chat
cio-ii phrase-add "addr" "123 Main St, Springfield, IL" --profile email_docs
cio-ii phrase-add "sig" "Best regards,\nJohn Smith" --profile email_docs
```

**Profiles** control where phrases activate:
| Profile | Apps where it works |
|---------|-------------------|
| `email_docs` | Mail, Safari, Notes, Notion, Google Docs |
| `chat` | Slack, Discord, Messages, Teams |

Phrases set for `chat` won't fire in email, and vice versa.

### Add typo corrections

```bash
cio-ii phrase-add "definately" "definitely" --profile email_docs
cio-ii phrase-add "seperate" "separate" --profile email_docs
```

### See all your phrases

```bash
cio-ii phrase-list
```

### Remove a phrase

```bash
cio-ii phrase-remove "omw"
```

---

## Secret & PII Protection

CIO-Shield has 21 built-in detection patterns that catch secrets before they leak into chat, email, or AI tools. This works automatically — no setup needed.

**What it detects:**

| Category | Examples |
|----------|---------|
| API keys | OpenAI (`sk-...`), AWS (`AKIA...`), GitHub (`ghp_...`), Stripe (`sk_live_...`) |
| Tokens | JWT (`eyJ...`), generic `password=`, `token=`, `secret=` labels |
| Financial | Credit cards (Visa, Amex), IBAN numbers |
| Identity | US SSN, UK National Insurance, email addresses, phone numbers |
| Network | IPv4, IPv6, MAC addresses |
| Crypto | Ethereum, Bitcoin, Litecoin wallet addresses |
| Keys | PEM private key headers |

When a secret is detected in text being processed, it's redacted to `[REDACTED_SECRET]` in all logs and audit trails. In native mode, paste operations containing secrets are blocked or flagged before reaching the destination app.

---

## Reports & Diagnostics

### Health overview

```bash
cio-ii health-card
```

Shows the system's overall confidence, architecture score, strongest/weakest areas, and kill criteria.

### Session metrics

```bash
cio-ii proof-report
```

Shows your last session's stats: how many suggestions were shown, accepted, dismissed, undone, and your accept rate.

### Session history & learning progress

```bash
cio-ii session-status
```

Shows your **onboarding state**:
- **Embryonic** — fewer than 15 suggestions seen (still learning your patterns)
- **Learning** — 15+ suggestions seen, accept rate below 35% (calibrating)
- **Mature** — 15+ suggestions, 35%+ accept rate (system is tuned to you)

### Privacy ledger

```bash
cio-ii privacy-ledger --limit 25
```

Shows the last 25 security-relevant events (blocks, redactions, trust circuit triggers). This is your audit trail — you can always see exactly what CIO-Shield did and why.

### Audit trail integrity

```bash
cio-ii audit-status
```

Shows audit file count, last write time, and tamper detection status (HMAC verification).

---

## Safety Features

### Profiles & Context Awareness

CIO-Shield classifies each app into a profile and applies different policies:

| Profile | Apps | Behavior |
|---------|------|----------|
| `email_docs` | Mail, Safari, Notes, Notion | Suggestions active |
| `chat` | Slack, Discord, Messages | Suggestions active |
| `code` | VSCode, Xcode, PyCharm | **No suggestions** (never interfere with code) |
| `terminal` | Terminal, iTerm | **No suggestions** |
| `unknown` | Unrecognized apps | **No suggestions** (fail-safe) |

### Trust Circuit Breaker

If you dismiss too many suggestions in a row, CIO-Shield automatically pauses ("cools down") to avoid being annoying. It resumes after the cooldown period.

### Panic Mode

Press the panic hotkey (`Ctrl+Option+P` by default) or type `/panic` in headless mode to instantly disable all suggestions. Press again to resume.

### Undo

Every accepted suggestion is reversible. Press `Ctrl+Option+Z` (native mode) or type `/undo` (headless) to restore the original text.

---

## Corporate Tier (Enterprise)

If your IT department has deployed a corporate policy file, CIO-Shield automatically enforces it:

```bash
cio-ii policy-status
```

Shows whether you're in Individual or Corporate tier, which apps are force-blocked, and what settings are locked.

Corporate policies can:
- Block specific apps (e.g., prevent any typing assistance in ChatGPT)
- Add company-specific secret patterns (e.g., internal API key formats)
- Enforce encryption on local data
- Set retention policies for audit data

You (the user) cannot weaken corporate security settings, but you can always add your own phrases and typo corrections on top.

---

## Environment Variables (Optional)

These override defaults if set in your shell:

| Variable | Default | What it does |
|----------|---------|-------------|
| `COGNITIVEIO_HOME` | `~/.cognitiveio` | Where local data is stored |
| `COGNITIVEIO_ENABLE_APPLE_FM` | `1` | Enable/disable the Apple FM arbiter |
| `COGNITIVEIO_IDLE_PAUSE_MS` | `300` | How long to wait after typing stops before suggesting |
| `COGNITIVEIO_PANIC_HOTKEY` | `ctrl+option+p` | Panic toggle hotkey |
| `COGNITIVEIO_UNDO_HOTKEY` | `ctrl+option+z` | Undo hotkey |

---

## Factory Reset

To delete all local data (patterns, phrases, session history, reports):

```bash
cio-ii delete-all --confirm
```

This cannot be undone. Seed data can be restored with `cio-ii seed-language-assets`.

---

## Command Reference

| Command | Purpose |
|---------|---------|
| `cio-ii run --mode headless` | Interactive terminal mode |
| `cio-ii run --mode mac` | Native macOS keystroke mode |
| `cio-ii seed-language-assets` | Load default typos and abbreviations |
| `cio-ii phrase-add TRIGGER EXPANSION` | Add a custom phrase |
| `cio-ii phrase-list` | Show all phrases |
| `cio-ii phrase-remove TRIGGER` | Remove a phrase |
| `cio-ii health-card` | System health overview |
| `cio-ii proof-report` | Last session metrics |
| `cio-ii session-status` | Onboarding progression |
| `cio-ii privacy-ledger` | Security event log |
| `cio-ii audit-status` | Audit trail health |
| `cio-ii policy-status` | Corporate policy details |
| `cio-ii requirements-check` | Platform compatibility check |
| `cio-ii arbiter-status` | Apple FM status |
| `cio-ii schema-check` | Database integrity check |
| `cio-ii explain-last` | Explain last decision |
| `cio-ii compliance-export` | Generate compliance report |
| `cio-ii retention-prune` | Prune old data |
| `cio-ii delete-all --confirm` | Factory reset |
| `cio-ii demo` | Run the deterministic demo |
