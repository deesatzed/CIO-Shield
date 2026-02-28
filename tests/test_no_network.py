from pathlib import Path
import re


def test_no_network_imports_in_core_runtime():
    root = Path(__file__).resolve().parents[1] / "src" / "cognitiveio"
    targets = [
        root / "core" / "decision_engine.py",
        root / "runtime" / "app_runtime.py",
        root / "memory" / "local_store.py",
        root / "policy" / "risk_scoring.py",
    ]
    forbidden = [r"\brequests\b", r"\bhttpx\b", r"\baiohttp\b", r"\burllib\b", r"\bopenai\b"]

    for f in targets:
        text = f.read_text(encoding="utf-8")
        for pat in forbidden:
            assert re.search(pat, text) is None, f"forbidden network import in {f.name}: {pat}"
