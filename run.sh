#!/usr/bin/env bash
set -euo pipefail
export COGNITIVEIO_HOME="$(pwd)/.cognitiveio"
PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}" python -m cognitiveio.cli run
