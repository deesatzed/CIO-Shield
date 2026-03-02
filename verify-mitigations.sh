#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

FAILED=()

run_step() {
  local name="$1"
  shift
  echo "==> $name"
  if ! "$@"; then
    FAILED+=("$name")
    echo "FAILED: $name"
  else
    echo "PASSED: $name"
  fi
}

run_shell_step() {
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

run_shell_step "platform preflight" 'if [[ "$(uname -s)" == "Darwin" ]]; then PYTHONPATH=src python -m cognitiveio.cli requirements-check; else PYTHONPATH=src python -m cognitiveio.cli requirements-check --no-strict >/tmp/cio_requirements.out; rg -q "Platform Requirements" /tmp/cio_requirements.out; fi'
run_step "ruff" ruff check src tests
run_step "mypy" mypy src
run_step "pytest" pytest -q
run_shell_step "demo smoke" 'TMP_HOME="$(mktemp -d)" && COGNITIVEIO_HOME="$TMP_HOME" PYTHONPATH=src python -m cognitiveio.cli demo >/tmp/cio_demo.out && rg -q "Trust circuit breaker" /tmp/cio_demo.out && rm -rf "$TMP_HOME"'
run_shell_step "dependency integrity" 'rg -q "\"rich>=13\\.5\\.2,<13\\.6\"" pyproject.toml && rg -q "pytest==8\\.4\\.1" pyproject.toml'
run_shell_step "schema check" 'PYTHONPATH=src python -m cognitiveio.cli schema-check'
run_shell_step "secret redaction tests" 'pytest -q tests/security/test_secret_redaction.py tests/security/test_secret_alias_resolution.py tests/security/test_encrypted_store.py'
run_shell_step "phrase + concept regression tests" 'pytest -q tests/language/test_phrase_memory.py tests/language/test_concept_lexicon.py'
run_shell_step "headless launch safety" "printf '\n' | ./run.sh >/tmp/cio_run.out && rg -q 'headless mode' /tmp/cio_run.out"

if [ "${#FAILED[@]}" -eq 0 ]; then
  echo "✅ ALL MITIGATIONS VERIFIED"
  exit 0
fi

echo "❌ VERIFICATION FAILED"
printf ' - %s\n' "${FAILED[@]}"
exit 1
