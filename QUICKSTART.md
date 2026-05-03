# CIO-Shield Quickstart

Get CIO-Shield running on your Mac in under 5 minutes.

## Prerequisites

- **macOS 15+** (Sequoia or later) on **Apple Silicon** (M1/M2/M3/M4)
- **Python 3.11+** (check with `python3 --version`)
- **uv** package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

If you don't have Python 3.11+, install via Homebrew:
```bash
brew install python@3.13
```

If you don't have `uv`:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 1: Clone

```bash
git clone https://github.com/deesatzed/CIO-Shield.git
cd CIO-Shield
```

## Step 2: Bootstrap

```bash
./bootstrap.sh
```

This creates a virtual environment, installs all dependencies, and runs a platform check. You'll see a table of PASS/FAIL checks at the end.

**Note**: The bootstrap will attempt to clone Apple's FM SDK. If it fails (private repo or unavailable), that's fine — the core functionality and all tests work without it.

After bootstrap, activate the environment:
```bash
source .venv/bin/activate
```

## Step 3: Verify Installation

Run the test suite to confirm everything works:

```bash
pytest -q
```

Expected output:
```
518 passed, 2 skipped in ~3s
```

The 2 skipped tests require Apple FM hardware runtime — this is normal.

### Run with coverage (optional)

```bash
pytest -q --cov=cognitiveio --cov-report=term-missing
```

Expected: **94% coverage** across all modules.

### Run linter and type checker (optional)

```bash
ruff check src tests
mypy src
```

Both should report zero errors.

## Step 4: Try It

### Interactive headless mode (no accessibility permissions needed)

```bash
cio-ii run --mode headless
```

Type phrases and see suggestions appear. Press `Ctrl+C` to exit.

### Run the demo

```bash
./run_demo.sh
```

Shows a deterministic walkthrough of the decision engine.

### Check system health

```bash
cio-ii health-card
cio-ii requirements-check
cio-ii policy-status
```

## What Just Happened?

You've installed CIO-Shield with:

| Component | What it does |
|-----------|-------------|
| 21 secret detection patterns | Catches API keys, tokens, credit cards, SSNs, crypto wallets, etc. |
| Decision engine | Deterministic suggestion path (< 5ms) |
| Session tracking | Adapts behavior based on your accept/dismiss rate |
| Audit writer | HMAC-signed local audit trail |
| Corporate policy | Optional MDM-deployed policy file for enterprise governance |

All processing is **local-only**. Nothing leaves your machine.

## Troubleshooting

### `uv: command not found`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Then restart your terminal or run:
source ~/.zshrc
```

### `python3: command not found` or version too old

```bash
brew install python@3.13
```

### Bootstrap fails on Apple FM SDK clone

This is expected if you don't have access to Apple's private FM SDK. The clone failure is non-blocking — all tests and core functionality work without it. If you see:

```
fatal: repository 'https://github.com/apple/python-apple-fm-sdk' not found
```

Ignore it. The bootstrap will still complete. CIO-Shield falls back to deterministic-only mode (no FM arbiter).

### Tests fail with `ModuleNotFoundError`

Make sure you activated the virtual environment:
```bash
source .venv/bin/activate
```

### Permission denied on `bootstrap.sh` or `run.sh`

```bash
chmod +x bootstrap.sh run.sh run_demo.sh
```

## Project Structure (Key Paths)

```
CIO-Shield/
├── src/cognitiveio/          # All source code
│   ├── security/
│   │   ├── patterns.json     # 21 secret detection patterns
│   │   └── redaction.py      # Pattern matching engine
│   ├── policy/corporate.py   # Corporate tier governance
│   ├── audit/writer.py       # HMAC-signed audit trail
│   ├── core/decision_engine.py
│   └── cli.py                # All CLI commands
├── tests/                    # 518 tests, no mocks
├── docs/                     # Architecture and deployment guides
├── bootstrap.sh              # One-command setup
└── CLAUDE.md                 # Full developer reference
```

## Next Steps

- Read `CLAUDE.md` for the full developer guide
- Read `docs/PRODUCT_CONTRACT.md` for runtime invariants
- Read `docs/CORPORATE_DEPLOYMENT_GUIDE.md` for enterprise deployment via MDM
- Run `cio-ii --help` to see all available commands
