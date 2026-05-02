# CIO-II Shield: Dual-Tier Corporate Architecture — Build Plan

**Status**: Complete
**Created**: 2026-05-01
**Last Updated**: 2026-05-01

### Key Decisions Log

| Date | Decision | Choice |
|------|----------|--------|
| 2026-05-01 | Clipboard content-type handling | Text: full Shield scan. Image/binary: pass through, log metadata only |
| 2026-05-01 | Native language for performance layer | Swift only (reuses existing build pipeline, Apple ecosystem) |
| 2026-05-01 | Audit encryption at rest | AES-256-GCM via Swift CryptoKit (hardware-accelerated on Apple Silicon) |
| 2026-05-01 | Audit key derivation | Machine identity + corporate policy seed |
| 2026-05-01 | No Rust | Swift covers XPC, clipboard, crypto. Python for business logic. Two languages sufficient. |

---

## Overview

CIO-II is evolving from a typing assistant into **CIO-II Shield** — a real-time clipboard/paste interception layer that protects secrets, API keys, and PII from leaking to AI tools, Slack, email, etc.

Two tiers:
1. **Individual** — free/personal, works standalone on any Mac, zero config
2. **Corporate** — all employees use it, governance at the corporate level (policies, compliance, audit)

**Core principle**: All processing stays LOCAL on each employee's Mac. Secrets NEVER leave the machine. Corporate governance is achieved through locally-deployed read-only policy files, NOT centralized data collection.

---

## Architecture: Corporate Governance via Local Constraints

```
┌─────────────────────────────────────────────────────┐
│                 CORPORATE TIER                       │
│     (IT deploys policy via MDM/Jamf/Munki)          │
├─────────────────────────────────────────────────────┤
│ /Library/Application Support/CognitiveIO/           │
│   corporate_policy.json  (read-only, root-owned)    │
│                                                     │
│ Contains:                                           │
│  - Locked settings (encryption=required, etc.)      │
│  - Additional secret detection patterns             │
│  - Force-blocked apps (ChatGPT, Copilot, etc.)      │
│  - Retention policy (how long to keep audit data)   │
│  - Compliance export config                         │
│  - Post-session hook script path                    │
├─────────────────────────────────────────────────────┤
│              INDIVIDUAL TIER                         │
│         (Default when no policy file exists)         │
├─────────────────────────────────────────────────────┤
│ ~/.cognitiveio/user_prefs.json (user-editable)      │
│ COGNITIVEIO_* env vars (highest priority for user)  │
│ Local pattern learning, phrases, confidence tuning  │
└─────────────────────────────────────────────────────┘
```

**Precedence (security can only be strengthened, never weakened):**
1. Product defaults (baseline)
2. Corporate policy locks (cannot be overridden by user)
3. User preferences (additive only, cannot weaken corporate)
4. Environment variables (cannot weaken corporate)

---

## Clipboard Content-Type Handling

### Design Decision (2026-05-01)

| Content Type | Shield Action | Audit |
|---|---|---|
| **Text** (`public.utf8-plain-text`) | Full interception: scan for secrets, block to force-blocked apps, redact | Log categorical event (reason, app, pattern type — never content) |
| **Image/Screenshot** (`public.png`, `public.tiff`, etc.) | Pass through unmodified | Log metadata only (content_type, dimensions, byte_size, destination_app, source_hint) |
| **Binary/Other** | Pass through unmodified | Log metadata only (content_type, byte_size, destination_app) |

### Image/Screenshot Audit Metadata Fields

| Field | Example | Purpose |
|---|---|---|
| `content_type` | `public.png` | What format was pasted |
| `destination_app` | `ChatGPT` | Where it went |
| `destination_profile` | `ai_tool` | Profile classification |
| `pixel_dimensions` | `1920x1080` | Size hint (screenshot vs icon) |
| `byte_size` | `245760` | Data volume (categorical) |
| `source_hint` | `screenshot` or `copy` | Cmd+Shift+4 vs app copy |
| `timestamp` | ISO 8601 | When it happened |

**Never logged**: actual image data, pixel content, or any reconstructable visual.

**Rationale**: Corporate audit gets a complete record — "Employee pasted a 1920x1080 PNG screenshot into ChatGPT at 2:30pm" — without ever seeing the screenshot content.

---

## Native Swift Layer

### Architecture

```
Python (business logic)          Swift (performance + security)
┌──────────────────────┐        ┌─────────────────────────────────┐
│ cognitiveio package  │        │ com.cognitiveio.audit-helper    │
│                      │        │ (privileged LaunchDaemon)       │
│ decision_engine.py   │        │                                 │
│ app_runtime.py       │──XPC──►│ AuditWriter (append-only JSONL) │
│ cli.py               │        │ AES-256-GCM encryption          │
│ local_store.py       │        │ HMAC-SHA256 tamper signatures   │
│                      │        │ Clipboard content-type monitor  │
│ policy/corporate.py  │        │ Key derivation (machine+policy) │
└──────────────────────┘        └─────────────────────────────────┘
```

### Encryption: AES-256-GCM via CryptoKit

- **Algorithm**: AES-256-GCM (authenticated encryption with associated data)
- **Hardware acceleration**: Apple Silicon AES instructions (zero CPU overhead)
- **Key derivation**: `HKDF-SHA256(machine_serial + hardware_uuid + policy_seed)`
  - `machine_serial`: `IOPlatformSerialNumber` from IOKit
  - `hardware_uuid`: `IOPlatformUUID` from IOKit
  - `policy_seed`: from `corporate_policy.json` (corporate) or random per-install (individual)
- **Per-file nonce**: Random 12-byte nonce per JSONL file, stored in file header
- **AEAD tag**: 16-byte authentication tag per encrypted block
- **Rotation**: New key derived when policy file changes or on quarterly schedule

### Swift Components (all in `helpers/com.cognitiveio.audit-helper/`)

| File | Purpose |
|------|---------|
| `main.swift` | XPC listener entry point, LaunchDaemon lifecycle |
| `AuditCrypto.swift` | AES-256-GCM encrypt/decrypt, HKDF key derivation |
| `AuditWriter.swift` | Append-only JSONL writer with encryption + HMAC |
| `ClipboardMonitor.swift` | NSPasteboard observer, content-type detection, metadata extraction |
| `XPCProtocol.swift` | Protocol definition for Python ↔ Swift IPC |
| `Info.plist` | SMJobBless configuration, code-signing requirements |
| `Package.swift` | Swift Package Manager build definition |

### Python ↔ Swift Communication

- **XPC via subprocess**: Python sends JSON event via stdin to helper process
- **Fallback**: If helper unavailable (individual mode), Python writes audit directly using stdlib
- **No PyObjC dependency for XPC**: Uses `subprocess.Popen` with JSON line protocol for portability

```python
# Python side (audit/writer.py)
class XPCAuditBackend:
    def __init__(self):
        self._proc = subprocess.Popen(
            ["/Library/PrivilegedHelperTools/com.cognitiveio.audit-helper"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            bufsize=1,  # line-buffered
        )

    def append(self, event_json: str) -> None:
        self._proc.stdin.write(event_json.encode() + b"\n")
        self._proc.stdin.flush()
```

---

## Implementation Phases

### Phase 1: Policy Infrastructure [NEW files]
- **Status**: Complete
- **Files**:
  - `src/cognitiveio/policy/corporate.py` — NEW (core policy module)
  - `src/cognitiveio/policy/__init__.py` — MODIFY (add exports)

**Deliverables**:
- `PolicyConstraints` frozen dataclass with: organization_id, organization_name, tier, policy_expires_at, locked_settings, additional_secret_patterns, force_blocked_apps, force_blocked_bundles, force_profile_overrides, retention, compliance, hooks
- `RetentionPolicy` dataclass: audit_retention_days, prune_on_startup
- `ComplianceExportConfig` dataclass: enabled, include_pattern_stats, include_secret_registry, include_block_reasons
- `HookConfig` dataclass: post_session_script
- `load_corporate_policy()` — checks 3 paths in order, returns individual tier if none found
- `apply_corporate_settings(settings, policy)` — merges locks (only strengthens, never weakens)
- Policy file paths checked in order:
  1. `/Library/Application Support/CognitiveIO/corporate_policy.json` (MDM)
  2. `$COGNITIVEIO_CORPORATE_POLICY` env var (testing)
  3. `~/.cognitiveio/corporate_policy.json` (self-enrolled)

**Validation**: Unit tests for loading, expiry, merge, mandate enforcement

---

### Phase 2: Config Integration [MODIFY]
- **Status**: Complete
- **Files**: `src/cognitiveio/config.py`

**Deliverables**:
- `settings_from_env_with_policy() -> tuple[Settings, PolicyConstraints]`
- Existing `settings_from_env()` remains untouched (backward compat)

**Validation**: Existing 17 config tests still pass, new function tested

---

### Phase 3: Profile + Decision Engine [MODIFY]
- **Status**: Complete
- **Files**:
  - `src/cognitiveio/context/profiles.py`
  - `src/cognitiveio/core/decision_engine.py`

**Deliverables**:
- New constant: `PROFILE_BLOCKED_BY_POLICY = "blocked_by_policy"`
- `classify_profile()` gains optional `policy` param
- If app in `policy.force_blocked_apps` or bundle in `policy.force_blocked_bundles` → return `blocked_by_policy`
- `decide()` gains optional `policy` param
- If profile is `blocked_by_policy` → return `do_nothing` with reason `corporate_policy_block`

**Validation**: Existing profile + invariant tests pass, new policy block tests added

---

### Phase 4: Redaction Enhancement [MODIFY]
- **Status**: Complete
- **Files**: `src/cognitiveio/security/redaction.py`

**Deliverables**:
- `redact_text()` gains `extra_patterns: Optional[List[re.Pattern]] = None` param
- Corporate patterns applied in addition to built-in patterns (additive, never subtractive)

**Validation**: Existing redaction tests pass, new corporate pattern tests

---

### Phase 5: Compliance & Retention [MODIFY]
- **Status**: Complete
- **Files**: `src/cognitiveio/memory/local_store.py`

**Deliverables**:
- `prune_by_retention(days: int) -> int` — delete events older than N days, return count
- `export_compliance_report(policy, output_path) -> dict` — redacted aggregate JSON containing:
  - Block reason summary (counts by type)
  - Pattern lifecycle stats (embryonic/viable/thriving/declining distribution)
  - Secret alias names + usage counts (NOT values)
  - Accept/dismiss/undo rates
  - Machine ID hash (non-reversible)

**Validation**: Prune logic tested, export format validated

---

### Phase 6: Runtime Integration [MODIFY]
- **Status**: Complete
- **Files**:
  - `src/cognitiveio/runtime/app_runtime.py`
  - `src/cognitiveio/runtime/protected_context.py`

**Deliverables**:
- `AppRuntime.__init__()` accepts optional `policy` param, passes to `classify_profile()` and `decide()`
- `ProtectedContextDetector` accepts optional `corporate_blocked_apps` and `corporate_blocked_bundles` sets

**Validation**: Existing 25 runtime tests + 11 protected context tests pass unchanged

---

### Phase 7: Audit Module + Swift Helper [NEW files]
- **Status**: Complete
- **Files**:
  - `src/cognitiveio/audit/__init__.py` — NEW
  - `src/cognitiveio/audit/writer.py` — NEW (dual-mode audit writer, Python XPC client)
  - `src/cognitiveio/audit/events.py` — NEW (AuditEvent dataclass, validation)
  - `helpers/com.cognitiveio.audit-helper/Package.swift` — NEW (SPM build)
  - `helpers/com.cognitiveio.audit-helper/Sources/main.swift` — NEW (XPC listener)
  - `helpers/com.cognitiveio.audit-helper/Sources/AuditCrypto.swift` — NEW (AES-256-GCM + HKDF)
  - `helpers/com.cognitiveio.audit-helper/Sources/AuditWriter.swift` — NEW (encrypted append-only JSONL)
  - `helpers/com.cognitiveio.audit-helper/Sources/ClipboardMonitor.swift` — NEW (content-type detection)
  - `helpers/com.cognitiveio.audit-helper/Sources/XPCProtocol.swift` — NEW (IPC protocol)
  - `helpers/com.cognitiveio.audit-helper/Info.plist` — NEW (SMJobBless config)
  - `helpers/launchd/com.cognitiveio.audit.plist` — NEW (LaunchDaemon)
  - `helpers/launchd/com.cognitiveio.agent.plist` — NEW (LaunchAgent KeepAlive)

**Deliverables**:
- `AuditEvent` dataclass with validation (rejects events containing secret values)
- `AuditWriter` with two backends:
  - Corporate: writes via subprocess JSON-line protocol to Swift helper → `/Library/Application Support/CognitiveIO/audit/`
  - Individual: writes directly to `~/.cognitiveio/audit/` (user-owned, unencrypted)
- `ClipboardAuditEvent` for image/binary paste metadata logging
- Swift helper with AES-256-GCM encryption (CryptoKit, hardware-accelerated)
- HKDF-SHA256 key derivation from machine identity + policy seed
- HMAC-SHA256 signature per JSONL line (tamper detection)
- Manifest.json with checksums

**Audit event types**:
```jsonl
{"ts":"...","event":"block","reason":"corporate_policy_block","app":"ChatGPT","profile":"ai_tool"}
{"ts":"...","event":"redaction","pattern_type":"api_key","destination_profile":"ai_tool","token_count":2}
{"ts":"...","event":"clipboard_image","content_type":"public.png","dimensions":"1920x1080","byte_size":245760,"destination_app":"ChatGPT","source_hint":"screenshot"}
{"ts":"...","event":"session_summary","accept_rate":0.72,"blocks":5,"redactions":3}
```

**What is NEVER written**: secret values, clipboard contents, raw keystrokes, actual text, file paths with user data

**Validation**: Writer tests for both backends, event validation tests

---

### Phase 8: CLI Commands [MODIFY]
- **Status**: Complete
- **Files**: `src/cognitiveio/cli.py`

**Deliverables**:
- `cio-ii policy-status` — show tier, org, locked settings, blocked apps, audit path
- `cio-ii compliance-export [--output path]` — generate summary from audit JSONL
- `cio-ii retention-prune [--dry-run|--execute]` — prune old data
- `cio-ii audit-status` — show audit health (file count, last write, tamper check)
- Update `run` command to use `settings_from_env_with_policy()` and instantiate `AuditWriter`

**Validation**: CLI runner tests for each new command

---

### Phase 9: Tests + Documentation [NEW + VERIFY]
- **Status**: Complete
- **Files**:
  - `tests/test_corporate_policy.py` — NEW (~25 tests)
  - `tests/test_audit_writer.py` — NEW (~15 tests)
  - `tests/test_compliance_export.py` — NEW (~10 tests)
  - `tests/test_retention_prune.py` — NEW (~5 tests)
  - `docs/CORPORATE_DEPLOYMENT_GUIDE.md` — NEW

**Validation checklist**:
- [x] All 331+ existing tests pass (zero interface breakage) — 419 passed, 2 skipped
- [x] New corporate tests pass (~88 new tests across 4 files + CLI)
- [x] Coverage at 92% (see gap analysis below)
- [x] `verify-mitigations.sh` → ALL MITIGATIONS VERIFIED
- [x] `validate-user-journey.sh` → USER JOURNEY VALIDATED
- [x] `cio-ii policy-status` works (shows "Individual" with no policy file)
- [x] Deploy test policy file → `cio-ii policy-status` shows "Corporate"
- [x] `cio-ii compliance-export` generates valid JSON
- [x] `cio-ii retention-prune --dry-run` shows what would be pruned

**Coverage gap analysis (92% vs 94% target)**:
The 2% drop is attributable to hardware-dependent code that cannot be tested without the native runtime:
- `audit/writer.py` XPCAuditBackend (65%) — requires Swift privileged helper binary
- `runtime/protected_context.py` (73%) — macOS Accessibility API calls
- `runtime/suggestion_presenter.py` (77%) — Cocoa/AppKit framework

These are the same category as the pre-existing intentionally uncovered modules documented in CLAUDE.md. The XPCAuditBackend specifically requires the compiled Swift helper at `/Library/PrivilegedHelperTools/com.cognitiveio.audit-helper` which is a corporate deployment artifact.

---

## Policy File Schema (corporate_policy.json)

```json
{
  "schema_version": 1,
  "organization_id": "acme-corp",
  "organization_name": "Acme Corporation",
  "policy_issued_at": "2026-05-01T00:00:00Z",
  "policy_expires_at": "2026-08-01T00:00:00Z",

  "settings_overrides": {
    "db_encryption_mode": "required",
    "suggest_only": true,
    "auto_apply_enabled": false
  },

  "pattern_library": {
    "additional_secret_patterns": [
      "ACME_TOKEN_[A-Z0-9]{32}",
      "ghp_[A-Za-z0-9]{36}",
      "xoxb-[0-9]{10,13}-[A-Za-z0-9]{24}"
    ]
  },

  "profile_mandates": {
    "force_blocked_apps": ["ChatGPT", "Claude Desktop"],
    "force_blocked_bundles": ["com.openai.chatgpt"]
  },

  "retention_policy": {
    "audit_retention_days": 180,
    "prune_on_startup": true
  },

  "compliance_export": {
    "enabled": true,
    "include_pattern_stats": true,
    "include_secret_registry": true,
    "include_block_reasons": true
  },

  "hooks": {
    "post_session_script": "/usr/local/bin/cio-audit-to-splunk.sh"
  }
}
```

---

## Key Design Guarantees

| Guarantee | How Enforced |
|-----------|-------------|
| No network in core path | No HTTP/DNS calls. Policy file is local filesystem read. |
| Secrets never leave machine | Compliance export contains alias NAMES only, never values |
| Images pass through, metadata logged | Only categorical metadata (type, size, dimensions) — never pixels |
| Corporate cannot weaken safety | `apply_corporate_settings` only allows strengthening |
| Individual tier unaffected | No policy file = identical behavior to today |
| Backward compatible | All new params default to None, all 331 tests pass unchanged |
| No new dependencies | Uses stdlib only (json, re, pathlib, subprocess) |
| Expired policy = individual | `is_expired` check → locks not applied |
| Employee cannot delete audit data | Protected audit partition (root-owned in corporate mode) |

---

## Audit Collection Model

### What Corporate CAN vs CANNOT See

| Corporate CAN audit | Corporate CANNOT see |
|--------------------|---------------------|
| Which apps triggered blocks (app name) | Raw keystrokes |
| How many secrets were redacted (count + type) | Secret VALUES |
| Accept/dismiss/undo rates | Unredacted text content |
| Image paste metadata (type, size, destination) | Image pixel content |
| Pattern category distribution | What the user actually typed |
| Trust circuit breaker events | Clipboard contents |
| Block reason counts | File paths with user data |
| Session duration and timing | Content of suggestions |

### Protected Audit Partition (Corporate Mode)

```
/Library/Application Support/CognitiveIO/audit/
├── {machine_id_hash}/
│   ├── 2026-05-01.jsonl       (append-only daily log)
│   ├── 2026-05-02.jsonl
│   └── ...
└── manifest.json              (index of files, checksums)
```

- Directory owned by `root:wheel` (created by MDM installer)
- CIO-II writes via privileged helper (XPC, local IPC)
- Employee user: read-only access (transparency)
- Only root/MDM can delete (retention pruning)

### Individual Mode

```
~/.cognitiveio/audit/
├── 2026-05-01.jsonl
└── manifest.json
```

- User-owned, user-deletable
- Same event format, no privileged helper needed

---

## Anti-Tampering Measures (Corporate)

| Threat | Mitigation |
|--------|-----------|
| Employee deletes audit files | Files owned by root, user has read-only |
| Employee modifies audit files | HMAC signature per line (key held by helper) |
| Employee kills CIO-II process | MDM ensures restart (launchd KeepAlive) |
| Employee uninstalls CIO-II | MDM detects removal, flags non-compliance |
| Employee disables event tap | CIO-II logs "accessibility_revoked" event |
| Privileged helper compromise | Code-signed, notarized, SMJobBless validates |

---

## Files Modified/Created Summary

| File | Action | Phase |
|------|--------|-------|
| `src/cognitiveio/policy/corporate.py` | NEW | 1 |
| `src/cognitiveio/policy/__init__.py` | MODIFY | 1 |
| `src/cognitiveio/config.py` | MODIFY | 2 |
| `src/cognitiveio/context/profiles.py` | MODIFY | 3 |
| `src/cognitiveio/core/decision_engine.py` | MODIFY | 3 |
| `src/cognitiveio/security/redaction.py` | MODIFY | 4 |
| `src/cognitiveio/memory/local_store.py` | MODIFY | 5 |
| `src/cognitiveio/runtime/app_runtime.py` | MODIFY | 6 |
| `src/cognitiveio/runtime/protected_context.py` | MODIFY | 6 |
| `src/cognitiveio/audit/__init__.py` | NEW | 7 |
| `src/cognitiveio/audit/writer.py` | NEW | 7 |
| `src/cognitiveio/audit/events.py` | NEW | 7 |
| `helpers/com.cognitiveio.audit-helper/main.swift` | NEW | 7 |
| `helpers/com.cognitiveio.audit-helper/Info.plist` | NEW | 7 |
| `helpers/launchd/com.cognitiveio.audit.plist` | NEW | 7 |
| `helpers/launchd/com.cognitiveio.agent.plist` | NEW | 7 |
| `src/cognitiveio/cli.py` | MODIFY | 8 |
| `tests/test_corporate_policy.py` | NEW | 9 |
| `tests/test_audit_writer.py` | NEW | 9 |
| `tests/test_compliance_export.py` | NEW | 9 |
| `tests/test_retention_prune.py` | NEW | 9 |
| `docs/CORPORATE_DEPLOYMENT_GUIDE.md` | NEW | 9 |
| `docs/CORPORATE_SHIELD_BUILD_PLAN.md` | NEW | — |
