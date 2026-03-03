#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

FAILED=()
TMP_HOME="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_HOME"
}
trap cleanup EXIT

export COGNITIVEIO_HOME="$TMP_HOME"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"

run_step() {
  local name="$1"
  local cmd="$2"
  echo "==> $name"
  if ! bash -lc "$cmd"; then
    FAILED+=("$name")
    echo "FAILED: $name"
  else
    echo "PASSED: $name"
  fi
}

run_step "platform preflight" 'if [[ "$(uname -s)" == "Darwin" ]]; then python -m cognitiveio.cli requirements-check; else python -m cognitiveio.cli requirements-check --no-strict >/tmp/cio_requirements.out && rg -q "Platform Requirements" /tmp/cio_requirements.out; fi'
run_step "seed language assets" "python -m cognitiveio.cli seed-language-assets | rg -q 'Seeded language assets'"
run_step "add deterministic phrase" "python -m cognitiveio.cli phrase-add '.zz1' 'CIOII_TEST_PHRASE' --profile email_docs --confidence 0.99 | rg -q \"Saved phrase\""
run_step "verify phrase exists" "python -m cognitiveio.cli phrase-list --profile email_docs >/tmp/cio_phrase.out && rg -q '\\.zz1' /tmp/cio_phrase.out"
run_step "headless suggest and accept flow" "printf '.zz1\\n/accept\\n\\n' | python -m cognitiveio.cli run --mode headless --app-name Mail >/tmp/cio_headless.out && rg -q 'Ghost suggestion: .zz1 -> CIOII_TEST_PHRASE' /tmp/cio_headless.out && rg -q 'Accepted: .zz1 -> CIOII_TEST_PHRASE' /tmp/cio_headless.out"
run_step "explain last decision" "python -m cognitiveio.cli explain-last --json >/tmp/cio_explain.json && rg -q '\"action\"' /tmp/cio_explain.json && rg -q '\"reason_tag\"' /tmp/cio_explain.json"
run_step "proof report output" "python -m cognitiveio.cli proof-report >/tmp/cio_report.out && rg -q 'CIO-II - Proof Report' /tmp/cio_report.out"
run_step "health card output" "python -m cognitiveio.cli health-card >/tmp/cio_health.out && rg -q 'Organism Health Card' /tmp/cio_health.out"
run_step "privacy ledger events" "python -m cognitiveio.cli privacy-ledger --limit 20 >/tmp/cio_ledger.out && rg -q 'suggestion_accepted|suggestion_shown|suggestion_dismissed' /tmp/cio_ledger.out"

if [ "${#FAILED[@]}" -eq 0 ]; then
  echo "✅ USER JOURNEY VALIDATED"
  exit 0
fi

echo "❌ USER JOURNEY VALIDATION FAILED"
printf ' - %s\n' "${FAILED[@]}"
exit 1
