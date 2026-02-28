import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Ensure test runs are local-write safe.
os.environ.setdefault("COGNITIVEIO_HOME", str(ROOT / ".cognitiveio_test"))
