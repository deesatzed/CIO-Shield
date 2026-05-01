# CIO-II Product Requirements Document

**Version**: 0.2.0
**Status**: PRD-Ready (all verification gates green)
**Platform**: macOS 26.0+ (Apple Silicon arm64 only)
**License**: TBD (open source)

---

## 1. Product Summary

CIO-II is a local-first, trust-first writing assistant for macOS that uses Apple's on-device Foundation Model as a constrained arbiter for ambiguous correction decisions. It does not generate text. It suggests corrections only when confident, fails closed when uncertain, and preserves full reversibility and auditability.

**First-of-kind claim (verified):** CIO-II is the first open-source macOS application to use Apple's on-chip Foundation Model (`python-apple-fm-sdk` / `SystemLanguageModel`) for real-time writing assistance.

---

## 2. Problem Statement

People who type extensively — operations staff, founders, analysts, researchers, students — experience recurring friction:
- Repeated manual typo correction (`teh`, `recieve`, `wierd`)
- Context-switching between writing and fixing
- Lost trust when autocorrect silently rewrites intent
- No control over when and how assistance is offered

Existing tools either silently replace (macOS Autocorrect), require cloud (Grammarly), or lack context awareness (TextExpander).

---

## 3. Target Users

Mac users with moderate technical comfort who type frequently:
- Operations and support staff (high-volume email)
- Founders and product managers (docs, communication)
- Analysts and researchers (reports, notes)
- Students and writers (flow-dependent work)
- Anyone who types a lot but does not want AI to "take the wheel"

**Excluded**: Users without Apple Silicon Macs, users who want aggressive AI text generation.

---

## 4. Core Value Proposition

| Dimension | CIO-II Approach |
|-----------|----------------|
| Privacy | Fully local. No cloud calls. No telemetry. |
| Trust | Suggest-only default. Backs off on rejection. Reversible. |
| Intelligence | Apple FM on-chip arbiter for gray-zone decisions |
| Safety | Hard blocks in passwords, code, terminals, unknown apps |
| Auditability | Proof reports, privacy ledger, explain-last diagnostics |

---

## 5. Functional Requirements

### 5.1 Core Decision Engine
- **FR-1**: Deterministic decision path completes within 5ms target
- **FR-2**: Candidates generated from local memory (typos, phrases, concepts)
- **FR-3**: Single high-confidence candidate triggers suggestion
- **FR-4**: Multiple candidates (gray-zone) route to FM arbiter
- **FR-5**: FM arbiter selects from candidate IDs or returns `do_nothing` within 80ms
- **FR-6**: FM unavailability in gray-zone fails closed to `do_nothing`

### 5.2 Safety and Privacy
- **FR-7**: Password fields and excluded apps trigger hard block (no capture, no suggestions)
- **FR-8**: Unknown, code, and terminal profiles default to `do_nothing`
- **FR-9**: No raw keystroke stream is persisted
- **FR-10**: Privacy ledger records blocked reasons with minimal metadata
- **FR-11**: Panic hotkey (`ctrl+option+p`) immediately halts all observation
- **FR-12**: Trust circuit breaker suppresses suggestions after dense dismissals/undos

### 5.3 User Experience
- **FR-13**: Suggestions appear only at word boundary + idle pause (default 300ms)
- **FR-14**: `Tab` accepts, `Esc` dismisses
- **FR-15**: Every applied change has a reversible undo record (`ctrl+option+z`)
- **FR-16**: Menu bar indicates state: `CIO` (running), `CIO-P` (protected), `CIO-II` (paused)
- **FR-17**: `cio-ii explain-last` prints decision rationale for latest action

### 5.4 Phrase and Concept System
- **FR-18**: Dot-phrase expansion (e.g., `.meW` → work signature) in email/docs profiles
- **FR-19**: Concept normalization (`api` → `Application Programming Interface`) with confidence gating
- **FR-20**: `{{SECRET:NAME}}` placeholders resolved at apply-time from env-backed vault
- **FR-21**: Unresolved secrets fail closed (accept blocked with explicit message)
- **FR-22**: Secret values redacted in all logs, reports, and ledger entries

### 5.5 Learning and Adaptation
- **FR-23**: Per-pattern lifecycle states (embryonic, viable, thriving, declining)
- **FR-24**: Successful patterns promoted, stale patterns decayed
- **FR-25**: Failure signature learning (avoid repeated bad suggestions)

### 5.6 Diagnostics and Evidence
- **FR-26**: `cio-ii proof-report` — accept/dismiss/undo/block rates with trendlines
- **FR-27**: `cio-ii health-card` — system health overview
- **FR-28**: `cio-ii privacy-ledger` — auditable event log
- **FR-29**: `cio-ii requirements-check` — platform requirement validation
- **FR-30**: `cio-ii schema-check` — database schema integrity

---

## 6. Non-Functional Requirements

### 6.1 Performance
- Decision path: ≤ 5ms (deterministic)
- Overlay update: ≤ 16ms (frame budget)
- FM arbiter timeout: ≤ 80ms (then `do_nothing`)
- No synchronous disk-heavy operations on keystroke hot path

### 6.2 Reliability
- 331 automated tests, 94% code coverage
- No mocks in test suite — all tests use real SQLite
- 2 hardware-gated test markers (`live_fm`, `live_mac`) for CI flexibility
- Deterministic demo with 7 verified scenarios

### 6.3 Security
- Local-only data store (SQLite, optional SQLCipher encryption)
- No network calls in core decision path (verified by test)
- Secret alias system with fail-closed resolution
- Redaction engine for all diagnostic outputs

### 6.4 Compatibility
- macOS 26.0+ (Apple Silicon arm64)
- Python 3.11, 3.12, 3.13 (CI-tested)
- Graceful degradation without Apple FM SDK (deterministic-only mode)

---

## 7. Architecture Overview

```
CLI (Typer) → AppRuntime (state machine)
                ├── MacBridge (event tap, text injection)
                ├── ProtectedContext (password/exclusion detection)
                ├── SuggestionPresenter (overlay or console)
                └── TextApply (mutation + undo + secret resolution)

DecisionEngine (≤5ms deterministic path)
                ├── FMArbiter (80ms timeout, selector-only)
                ├── RiskScoring (gate tiers)
                └── ProfileClassifier (code/terminal/email/chat/unknown)

Memory (SQLite + optional SQLCipher)
                ├── LocalStore (patterns, events, lifecycle)
                ├── LanguageAssets (seeded typos, concepts, phrases)
                └── PrivacyLedger (blocked reasons, metadata)

Security
                ├── SecretVault (env-backed provider)
                ├── Resolver (TTL cache, fail-closed)
                └── Redaction (payload minimization)
```

---

## 8. Verified Quality Gates

| Gate | Status | Evidence |
|------|--------|----------|
| Platform requirements | PASS | macOS 26.5, Xcode 26.4, arm64, FM available |
| Ruff lint | PASS | All checks passed |
| Mypy type check | PASS | No issues in 37 source files |
| Test suite | PASS | 331 passed, 2 skipped (hardware-gated) |
| Code coverage | 94% | 2152 statements, 133 missed (hardware-dependent) |
| Demo scenarios | PASS | 7/7 episodes match expected |
| Mitigation verification | PASS | All 10 checks green |
| User journey validation | PASS | All 9 steps green |
| Dependency integrity | PASS | No conflicts |
| Schema check | PASS | Database schema valid |

---

## 9. Known Limitations (v0.2.0)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Requires macOS 26.0+ on Apple Silicon | Limits audience to recent Mac hardware | Graceful degradation without FM |
| Ghost suggestion UX not yet adaptive to typing speed | Fixed idle pause (300ms) | Configurable via env var |
| Learning not encrypted-at-rest by default | Data at local SQLite level security | SQLCipher optional dep available |
| No "why no suggestion" status hints | User may not understand inaction | `explain-last` command available |
| Requires Accessibility permission grant | Manual macOS Settings step | Documented in troubleshooting |

---

## 10. Release Criteria (v0.2.0)

- [x] All quality gates green
- [x] Apple FM arbiter verified live on-device
- [x] Demo script shows all safety behaviors
- [x] Proof report and privacy ledger generate valid artifacts
- [x] README accurate to verified capabilities
- [x] Blog post reflects real functionality
- [x] GitHub Actions CI configured (Python 3.11/3.12/3.13 matrix)
- [ ] GitHub repo public and accessible
- [ ] Apple FM SDK build instructions verified by external tester

---

## 11. Roadmap (Post v0.2.0)

| Priority | Feature | Status |
|----------|---------|--------|
| P1 | Adaptive idle pause from typing speed | Sprint 2 (planned) |
| P1 | "Why no suggestion" status hints | Sprint 2 (planned) |
| P2 | Encrypted-at-rest learning store | Sprint 3 (planned) |
| P2 | Session profile onboarding contract | Sprint 2 (planned) |
| P3 | Homebrew tap distribution | Future |
| P3 | SwiftUI preferences pane | Future |
