# CIO-II Shield: Corporate Deployment Guide

## Overview

CIO-II Shield protects corporate secrets, API keys, and PII from leaking through clipboard paste operations to AI tools, chat applications, and email. All processing happens locally on each employee's Mac — no data ever leaves the machine.

This guide covers deploying CIO-II Shield in corporate mode via MDM (Jamf, Munki, Kandji, or similar).

---

## Architecture

```
Employee Mac
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  CIO-II Shield (user process)                                │
│  ├── Clipboard interception (text: scan, image: metadata)    │
│  ├── Secret pattern detection (built-in + corporate)         │
│  ├── Profile classification (force-block corporate apps)     │
│  └── Audit event generation (categorical only)               │
│                                                              │
│  Privileged Audit Helper (root daemon)                       │
│  ├── Receives events via XPC (local IPC, no network)         │
│  ├── AES-256-GCM encryption (CryptoKit, hardware-accel)     │
│  ├── HMAC-SHA256 tamper signatures                           │
│  ├── Append-only JSONL to root-owned directory               │
│  └── Secret value validation (rejects anything suspicious)   │
│                                                              │
│  Corporate Policy (read-only, MDM-deployed)                  │
│  └── /Library/Application Support/CognitiveIO/               │
│      ├── corporate_policy.json                               │
│      └── audit/{machine_id_hash}/*.jsonl                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Deployment Steps

### 1. Create Corporate Policy File

Create `corporate_policy.json` with your organization's settings:

```json
{
  "schema_version": 1,
  "organization_id": "your-org-id",
  "organization_name": "Your Organization",
  "policy_issued_at": "2026-05-01T00:00:00Z",
  "policy_expires_at": "2026-11-01T00:00:00Z",

  "settings_overrides": {
    "db_encryption_mode": "required",
    "suggest_only": true,
    "auto_apply_enabled": false
  },

  "pattern_library": {
    "additional_secret_patterns": [
      "YOUR_ORG_TOKEN_[A-Z0-9]{32}",
      "ghp_[A-Za-z0-9]{36}",
      "xoxb-[0-9]{10,13}-[A-Za-z0-9]{24}"
    ]
  },

  "profile_mandates": {
    "force_blocked_apps": ["ChatGPT", "Claude Desktop", "GitHub Copilot"],
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
    "post_session_script": ""
  }
}
```

### 2. Deploy via MDM

**Directory structure to deploy:**

```
/Library/Application Support/CognitiveIO/
├── corporate_policy.json          (root:wheel, 0644)
├── audit/                         (root:wheel, 0755)
└── logs/                          (root:wheel, 0755)

/Library/PrivilegedHelperTools/
└── com.cognitiveio.audit-helper   (root:wheel, 0755, code-signed)

/Library/LaunchDaemons/
└── com.cognitiveio.audit.plist    (root:wheel, 0644)

/Library/LaunchAgents/
└── com.cognitiveio.agent.plist    (root:wheel, 0644)
```

**MDM Configuration Profile (Jamf example):**

1. **Package**: Bundle CIO-II Shield as a macOS installer package (.pkg)
2. **Policy File**: Deploy `corporate_policy.json` to `/Library/Application Support/CognitiveIO/`
3. **Helper**: Deploy `com.cognitiveio.audit-helper` to `/Library/PrivilegedHelperTools/`
4. **LaunchDaemon**: Deploy `com.cognitiveio.audit.plist` to `/Library/LaunchDaemons/`
5. **LaunchAgent**: Deploy `com.cognitiveio.agent.plist` to `/Library/LaunchAgents/`

**Permissions setup script (run as postinstall):**

```bash
#!/bin/bash
BASEDIR="/Library/Application Support/CognitiveIO"
mkdir -p "$BASEDIR/audit"
mkdir -p "$BASEDIR/logs"
chown -R root:wheel "$BASEDIR"
chmod 0755 "$BASEDIR" "$BASEDIR/audit" "$BASEDIR/logs"
chmod 0644 "$BASEDIR/corporate_policy.json"
```

### 3. Build the Privileged Helper

```bash
cd helpers/com.cognitiveio.audit-helper
swift build -c release
# Output: .build/release/com.cognitiveio.audit-helper

# Code-sign for distribution
codesign --sign "Developer ID Application: Your Org" \
    --identifier com.cognitiveio.audit-helper \
    .build/release/com.cognitiveio.audit-helper
```

### 4. Verify Deployment

On an employee machine after MDM deployment:

```bash
# Check policy status
cio-ii policy-status

# Expected output:
# Tier: corporate
# Organization: Your Organization
# Force-Blocked Apps: ChatGPT, Claude Desktop, GitHub Copilot

# Check audit health
cio-ii audit-status

# Generate compliance report
cio-ii compliance-export --output /tmp/compliance.json
```

---

## Policy File Schema Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | int | Yes | Must be `1` |
| `organization_id` | string | Yes | Unique org identifier |
| `organization_name` | string | No | Human-readable org name |
| `policy_issued_at` | ISO 8601 | No | When policy was created |
| `policy_expires_at` | ISO 8601 | No | When policy expires (degrades to individual) |

### `settings_overrides`

Corporate can only **strengthen** settings, never weaken them.

| Setting | Type | Strengthening Direction |
|---------|------|------------------------|
| `suggest_only` | bool | `true` is stronger |
| `auto_apply_enabled` | bool | `false` is stronger |
| `fail_safe_unknown_profile` | bool | `true` is stronger |
| `protected_mode_blocks_all` | bool | `true` is stronger |
| `fm_required_for_gray_zone` | bool | `true` is stronger |
| `db_encryption_mode` | string | `required` > `optional` > `off` |
| `max_suggestions_per_min` | int | Lower is stronger |
| `cooldown_seconds` | int | Higher is stronger |
| `trust_circuit_cooldown_seconds` | int | Higher is stronger |

### `pattern_library.additional_secret_patterns`

Array of regex strings. Each is compiled and applied **in addition to** built-in patterns:
- OpenAI keys (`sk-...`)
- AWS keys (`AKIA...`)
- Generic API key/password patterns
- Private key headers

Invalid regex patterns are silently skipped (logged but not fatal).

### `profile_mandates`

| Field | Type | Description |
|-------|------|-------------|
| `force_blocked_apps` | string[] | App names to hard-block |
| `force_blocked_bundles` | string[] | Bundle IDs to hard-block |

### `retention_policy`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `audit_retention_days` | int | 90 | Delete audit data older than this |
| `prune_on_startup` | bool | false | Auto-prune on CIO-II launch |

### `compliance_export`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | false | Enable compliance export |
| `include_pattern_stats` | bool | true | Include pattern lifecycle distribution |
| `include_secret_registry` | bool | true | Include secret alias names (never values) |
| `include_block_reasons` | bool | true | Include block reason counts |

### `hooks`

| Field | Type | Description |
|-------|------|-------------|
| `post_session_script` | string | Path to script run after each CIO-II session |

---

## Audit Data Collection

### What Is Collected (Categorical Only)

```jsonl
{"event":"block","ts":"2026-05-01T14:30:01Z","reason":"corporate_policy_block","app":"ChatGPT","profile":"ai_tool"}
{"event":"redaction","ts":"2026-05-01T14:30:15Z","pattern_type":"api_key","destination_profile":"ai_tool","token_count":2}
{"event":"clipboard_paste","ts":"2026-05-01T14:31:00Z","content_type":"public.png","pixel_dimensions":"1920x1080","byte_size":245760,"destination_app":"ChatGPT","source_hint":"screenshot"}
{"event":"session_summary","ts":"2026-05-01T15:00:00Z","accept_rate":0.72,"blocks":5,"redactions":3}
```

### What Is NEVER Collected

- Secret values
- Clipboard contents (text or image)
- Raw keystrokes
- Actual text that was corrected/suggested
- File paths containing user data
- Anything that could reconstruct what the user typed
- Image pixel data

### Pulling Audit Data

CIO-II itself NEVER makes outbound network calls. Corporate IT pulls audit data using existing endpoint management tools:

1. **MDM Script**: Scheduled `rsync`/`scp` from `/Library/Application Support/CognitiveIO/audit/` to SIEM
2. **osquery/Fleet**: Query JSONL files as a virtual table
3. **Endpoint Agent**: Existing Kolide/Fleetsmith agent reads the audit directory
4. **Manual**: `cio-ii compliance-export` generates a summary JSON

---

## Encryption

### At-Rest Encryption (AES-256-GCM)

- Algorithm: AES-256-GCM (authenticated encryption)
- Hardware: Apple Silicon AES instructions (zero CPU overhead)
- Key derivation: HKDF-SHA256 from machine serial + hardware UUID + organization_id
- Per-file nonce: Random 12-byte nonce
- AEAD tag: 16-byte authentication tag per block

### Tamper Detection (HMAC-SHA256)

Each JSONL line is signed with HMAC-SHA256. The signing key is held by the privileged helper daemon (root-owned process). Employees cannot modify audit data without detection.

---

## Troubleshooting

### Policy Not Loading

```bash
# Check if policy file exists
ls -la "/Library/Application Support/CognitiveIO/corporate_policy.json"

# Validate JSON syntax
python3 -m json.tool "/Library/Application Support/CognitiveIO/corporate_policy.json"

# Check CIO-II status
cio-ii policy-status
```

### Audit Helper Not Running

```bash
# Check LaunchDaemon status
launchctl list | grep cognitiveio

# Check helper binary
ls -la /Library/PrivilegedHelperTools/com.cognitiveio.audit-helper

# Check logs
cat "/Library/Application Support/CognitiveIO/logs/audit-helper.err"
```

### Employee Sees "Individual" Instead of "Corporate"

1. Verify policy file exists at the correct path
2. Check `policy_expires_at` — expired policies degrade to individual
3. Verify `organization_id` is set (required for corporate tier)
4. Check file permissions: must be readable by the user

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `cio-ii policy-status` | Show tier, org, locked settings, blocked apps |
| `cio-ii compliance-export [--output path]` | Generate redacted compliance report |
| `cio-ii retention-prune [--dry-run\|--execute]` | Prune old audit data |
| `cio-ii audit-status` | Show audit health (file count, integrity) |
| `cio-ii run` | Start CIO-II Shield (auto-detects tier) |
