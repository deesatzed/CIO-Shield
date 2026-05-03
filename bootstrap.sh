#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found. Install from https://docs.astral.sh/uv/"
  exit 1
fi

if [[ ! -d .venv ]]; then
  # Use system Python to ensure .pth files are processed correctly.
  # uv's managed Python distributions may skip .pth processing for editable installs.
  SYSTEM_PYTHON="$(command -v python3 || true)"
  if [[ -n "$SYSTEM_PYTHON" ]]; then
    uv venv .venv --python "$SYSTEM_PYTHON"
  else
    uv venv .venv
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate

uv pip install -e ".[dev,mac]"

if ! python -c "import apple_fm_sdk" >/dev/null 2>&1; then
  SDK_DIR="$ROOT_DIR/python-apple-fm-sdk"
  if [[ ! -d "$SDK_DIR" ]]; then
    git clone https://github.com/apple/python-apple-fm-sdk "$SDK_DIR"
  fi
  if [[ ! -d "$SDK_DIR/.git" ]]; then
    echo "Found $SDK_DIR but it is not a git clone. Remove or rename it, then rerun bootstrap.sh."
    exit 1
  fi
  uv pip install -e "$SDK_DIR"
fi

python -c "import cognitiveio" 2>/dev/null || {
  echo "ERROR: editable install failed — cognitiveio module not importable."
  echo "Try: rm -rf .venv && ./bootstrap.sh"
  exit 1
}

cio-ii requirements-check

echo ""
echo "Bootstrap complete."
echo "Run: source .venv/bin/activate && cio-ii run --mode headless"
