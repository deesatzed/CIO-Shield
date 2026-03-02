# CIO-II Feature Test Plan

This plan defines how to assess each shipped feature in CIO-II for correctness, safety, security, UX, and release readiness.

## 1. Scope

Covered domains:
- Functional behavior
- Safety guardrails
- Security and privacy controls
- UX controls and explainability
- Reliability and regression stability

## 2. Test Environments

| Env ID | Environment | Purpose |
|---|---|---|
| E1 | macOS + `.[dev,mac]` | Full runtime: menu bar, hotkeys, native event tap, apply/undo behavior |
| E2 | Headless local/CI (`.[dev]`) | Core logic, CLI, runtime flow, persistence, security checks |
| E3 | Optional Apple FM enabled | Constrained arbiter checks and selector-only behavior |

## 3. Feature Coverage Matrix

| Feature ID | Feature | Test Type | Environment | Commands / Procedure | Pass Criteria | Evidence Artifact |
|---|---|---|---|---|---|---|
| F01 | Typo suggestion at safe boundaries | Unit + Integration | E2 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_suggest_accept_and_undo` | Suggestion appears only with boundary + idle threshold | Pytest output |
| F02 | Suggest-only default mode | Unit | E2 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_suggest_accept_and_undo` + verify default config values | No silent replacement unless explicit auto-apply decision path | Pytest output + config snapshot |
| F03 | Accept / dismiss controls | Integration + Manual | E1/E2 | Headless: run `PYTHONPATH=src python -m cognitiveio.cli run --mode headless`, use `/accept` and `/dismiss`; macOS: `Tab` / `Esc` | Correct state transitions and ledger event outcomes | Runtime logs + ledger rows |
| F04 | Undo behavior and negative learning | Unit + Integration | E2 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_undo_penalty_reduces_candidate_confidence` | Undo restores prior value and decreases future confidence | Pytest output |
| F05 | Panic pause/resume | Integration + Manual | E1 | Start mac mode, trigger panic hotkey or menu `Pause Suggestions` then `Resume Suggestions` | Paused state blocks suggestions and status text reflects state | Terminal output + menu state |
| F06 | Protected mode block | Unit | E2 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_protected_mode_blocks` | No suggestion or capture in protected context | Pytest output |
| F07 | Trust circuit breaker cooldown | Unit + Integration | E2/E1 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_trust_circuit_breaker_blocks_after_negative_spike` and observe mac status countdown | Cooldown engages after negative signal threshold, then blocks suggestions | Pytest output + status text |
| F08 | Phrase memory (dot-phrases like `.meW`, `.TS1`) | Unit + Integration | E2 | `PYTHONPATH=src pytest -q tests/language/test_phrase_memory.py` then CLI: `phrase-add`, `phrase-list`, `phrase-remove` | Trigger expansions stored and returned profile-aware | Pytest output + CLI table |
| F09 | Concept lexicon normalization | Unit | E2 | `PYTHONPATH=src pytest -q tests/language/test_language_assets_seed.py` | Concept suggestions exist and map to canonical forms | Pytest output |
| F10 | Context profile gating | Unit + Manual | E2/E1 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_candidate_conflict_is_logged_as_blocked` and manual checks in Terminal/VS Code contexts | No intervention in blocked/unknown profiles | Pytest output + manual log |
| F11 | Secret alias resolution at apply-time | Unit | E2 | `PYTHONPATH=src pytest -q tests/test_text_apply_policy.py::test_apply_replacement_registers_secret_alias` | Alias resolves from provider/env and applies replacement | Pytest output |
| F12 | Secret alias fail-closed messaging | Unit + Manual | E2/E1 | `PYTHONPATH=src pytest -q tests/test_text_apply_policy.py::test_apply_replacement_fails_when_secret_alias_unresolved` | Replacement blocked with explicit missing-alias reason | Pytest output + runtime message |
| F13 | Redaction of secrets in telemetry/reports | Unit | E2 | `PYTHONPATH=src pytest -q tests/security/test_secret_redaction.py` | No plaintext secret material in persisted outputs | Pytest output |
| F14 | Required secret alias inventory | Unit + CLI | E2 | `PYTHONPATH=src pytest -q tests/security/test_secret_alias_registry.py`; `PYTHONPATH=src python -m cognitiveio.cli required-secrets --limit 100` | Alias registry reflects observed required aliases | Pytest output + CLI table |
| F15 | Explain-last decision snapshot | Unit + CLI | E2 | `PYTHONPATH=src pytest -q tests/test_runtime_flow.py::test_runtime_last_decision_snapshot_persists_to_disk`; `PYTHONPATH=src python -m cognitiveio.cli explain-last` | Snapshot persisted and human-readable with decision metadata | Pytest output + CLI table |
| F16 | Menu bar actions | Manual | E1 | In mac mode, click each menu item: pause/resume, explain last, show required secrets, manage dot-phrases | Each action triggers expected runtime callback and status output | Manual QA checklist |
| F17 | Proof report, health card, privacy ledger | Integration | E2 | `proof-report`, `health-card`, `privacy-ledger --limit 25` | Artifacts generated and internally consistent | CLI outputs + JSON exports |
| F18 | Schema + encryption mode checks | Integration | E2 | `PYTHONPATH=src python -m cognitiveio.cli schema-check` and run with `COGNITIVEIO_DB_ENCRYPTION=off|optional|required` test cases | Startup and schema behavior matches policy | Command output |
| F19 | Deterministic demo flow | Integration | E2 | `./run_demo.sh` | All expected episodes and artifacts generated | Demo output + report files |
| F20 | End-to-end release verification | Integration | E2 | `./verify-mitigations.sh` | Full gate prints `✅ ALL MITIGATIONS VERIFIED` | Script output |

## 4. Execution Order

1. Static quality gate:
```bash
PYTHONPATH=src ruff check src tests
PYTHONPATH=src mypy src
```
2. Targeted feature tests for changed areas:
```bash
PYTHONPATH=src pytest -q tests/test_runtime_flow.py tests/test_text_apply_policy.py tests/language tests/security
```
3. Full regression:
```bash
PYTHONPATH=src pytest -q
```
4. Product smoke and readiness:
```bash
./run_demo.sh
PYTHONPATH=src python -m cognitiveio.cli schema-check
./verify-mitigations.sh
```
5. macOS manual UX pass (E1):
- Menu status and actions
- Hotkeys (`panic`, `undo`)
- Accept/dismiss behavior
- Protected mode and trust cooldown display

## 5. Required Test Data

| Data Set | Values |
|---|---|
| Typos | `teh`, `recieve`, `wierd` |
| Dot-phrases | `.meW`, `.TS1` |
| Concepts | `api`, `mvp`, `sla`, `llm` |
| Secret aliases | `WORK_EMAIL`, `WORK_PHONE`, `TEST_API_KEY`, `MISSING_ALIAS` |
| Negative signals | repeated `dismiss` + `undo` actions |

## 6. Release Sign-Off Checklist

- [ ] `ruff` passes
- [ ] `mypy` passes
- [ ] `pytest -q` passes
- [ ] `run_demo.sh` passes
- [ ] `schema-check` passes
- [ ] `verify-mitigations.sh` prints success
- [ ] macOS menu/hotkey manual QA complete
- [ ] `explain-last` and `required-secrets` validated in CLI
- [ ] privacy artifacts reviewed for redaction compliance

