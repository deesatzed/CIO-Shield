# CIO-II Launch: A Context-Aware Writing Assistant for macOS That Does Not Take Over

Today we are open-sourcing CIO-II.

It is a local-first writing assistant for macOS built around one rule:
help the user, but do not override user intent.

Most people have seen the same failure pattern with writing tools:
- autocomplete/autocorrect changes the wrong word or phrase
- the user notices too late
- trust is lost quickly

CIO-II is built to avoid that pattern while still helping with real writing flow, not just typos.

## Main Benefit of the Optional Internal Apple FM LLM

Yes, this is still part of the architecture.

The primary benefit is improved precision in ambiguous gray-zone corrections:
- deterministic logic produces candidate options
- Apple FM is used as a constrained selector on those options
- it can also choose `do_nothing` when uncertainty remains

This is not about generating text. It is about making fewer wrong correction decisions in borderline cases while preserving the same safety and reversibility model.

## The Problem We Care About

People who type all day in email, documents, chat, and notes do not need flashy generation most of the time.
They need:
- fewer repetitive typo and phrase fixes
- fewer interruptions
- reliable behavior in sensitive contexts
- confidence that they can reverse changes immediately

That is the gap CIO-II focuses on.

## Who This Is For

CIO-II is designed for Mac users with moderate technical comfort, including:
- operations and support staff
- founders and product managers
- analysts and researchers
- students and writers
- anyone who types a lot but does not want AI to “take the wheel”

## Why CIO-II Is Different

### 1) Suggest-only by default
No silent rewrite.  
CIO-II shows a ghost suggestion and waits.

### 2) Hard safety blocks
In protected contexts, it blocks intervention instead of “trying anyway.”

### 3) Do-nothing is a first-class outcome
If confidence is weak, profile is unknown, or context is risky, CIO-II does nothing.

### 4) Undo is built in
Applied changes are reversible with explicit undo records.

### 5) Privacy is auditable
You can inspect local proof reports and privacy ledger events.

### 6) Optional Apple FM path is constrained
The arbiter can only choose from known local candidates or return do-nothing.
It cannot invent replacement text.
Its purpose is to improve ambiguous-case choice quality, not to increase intervention volume.

### 7) Context-aware phrase and concept intelligence
CIO-II is not just typo replacement:
- phrase expansion by context (email/docs/chat profiles)
- concept normalization for common shorthand terms (`api`, `sla`, `mvp`, `llm`)
- no intervention in code/terminal profiles

### 8) Secure secret alias workflows
CIO-II supports placeholder aliases like `{{SECRET:STRIPE_API_KEY}}`:
- alias-only tracking and audit (no plaintext secret persistence)
- provider-backed resolution at apply-time
- rotation-safe behavior (updated provider value is used without code edits)
- redaction in reports and ledger metadata

## Practical Examples

### Example: Email corrections without surprises
You type `teh` in Mail.  
At a natural pause, CIO-II offers `the`.  
You press `Tab` to accept or `Esc` to dismiss.

### Example: Phrase assistance without forced rewrite
You type `asap` in an email context.  
CIO-II can suggest `as soon as possible`, but still requires acceptance by default.

### Example: Dot-phrases for repeated writing blocks
You configure `.meW` for your work signature and `.TS1` for a technical analysis scaffold.  
In email/docs context, CIO-II can expand those patterns when you intentionally trigger them.

### Example: Concept clarity in documentation
You type `api` in docs/email context.  
CIO-II can offer `Application Programming Interface` when confidence is high.

### Example: No interference while coding
You are in VS Code or Terminal.  
CIO-II defaults to `do_nothing` so identifiers and commands are not touched.

### Example: Sensitive context protection
You are in a password manager or protected field.  
CIO-II blocks capture and suggestions, and marks blocked state clearly.

### Example: Secret placeholder insertion
You type a configured alias like `{{SECRET:STRIPE_API_KEY}}`.  
CIO-II resolves it through a secret provider at apply-time and redacts secret-like values from logs and reports.
If an alias is missing, CIO-II fails closed and shows an explicit message instead of inserting unresolved text.

### Example: Trust repair loop
If you keep dismissing or undoing, CIO-II enters a trust cooldown and stops nudging temporarily.
The macOS status now shows the live cooldown countdown.

### Example: Explainability from menu bar
Use the menu bar action `Explain Last Decision` to print the latest decision summary:
- action
- reason tag
- profile
- token
- trust cooldown remaining

### Example: Secret inventory from menu bar
Use `Show Required Secrets` to print alias names already observed by CIO-II.
This gives an operator-facing checklist for environment or vault provisioning.

## Why This Matters Now

AI writing products are often optimized for generation volume and aggressive autocomplete.  
Users often need reliability, predictability, and reversible behavior more than raw generation.

CIO-II treats trust as an engineering constraint, not a marketing claim.

## What You Can Verify Yourself

Run the deterministic demo and inspect outputs:
- protected mode block
- suggest-only accept flow
- no intervention in code profile
- candidate-conflict do-nothing
- trust-circuit cooldown
- proof report and privacy ledger artifacts
- schema check + language asset seeding

## Quick Start

```bash
git clone https://github.com/deesatzed/CIO-II.git
cd CIO-II
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev,mac]"
./run_demo.sh
PYTHONPATH=src python -m cognitiveio.cli seed-language-assets
PYTHONPATH=src python -m cognitiveio.cli schema-check
```

Run tests:
```bash
pytest -q
./verify-mitigations.sh
```

Run native mode:
```bash
PYTHONPATH=src python -m cognitiveio.cli run --mode mac
```

See proof report:
```bash
PYTHONPATH=src python -m cognitiveio.cli proof-report
```

Explain latest decision:
```bash
PYTHONPATH=src python -m cognitiveio.cli explain-last
PYTHONPATH=src python -m cognitiveio.cli explain-last --json
```

List required secret aliases:
```bash
PYTHONPATH=src python -m cognitiveio.cli required-secrets --limit 100
```

## What CIO-II Is Not

- It is not cloud-dependent by default.
- It is not free-form text generation pretending to be correction.
- It is not “always-on autocorrect.”
- It is not a blind autocomplete engine.
- It is not designed to modify code identifiers.

## What CIO-II Is

- A context-aware local writing assistant.
- A hybrid suggest-first system with strict safety gates.
- A phrase + concept helper for real writing workflows.
- A secure-by-default tool that treats secret handling, redaction, and auditability as product requirements.

## What Feedback We Want

If you test CIO-II, the most useful feedback includes:
- exact app/context where behavior happened
- expected behavior vs actual behavior
- whether the action was acceptable, dismissible, or required undo
- privacy/safety concerns with concrete repro steps

## Closing

The long-term bet behind CIO-II is simple:
the most useful AI assistants will be the ones users trust in real work.

Trust comes from predictable triggers, hard safety boundaries, reversibility, and local auditability.

If that direction resonates, try CIO-II and tell us where it fails first.

Repo: https://github.com/deesatzed/CIO-II
