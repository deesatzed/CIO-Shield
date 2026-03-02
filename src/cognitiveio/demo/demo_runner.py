from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict

from cognitiveio.config import Settings
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.policy.risk_scoring import RiskFlags
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent


async def run_demo(settings: Settings) -> Dict[str, Any]:
    episodes_path = Path(__file__).with_name("demo_episodes.json")
    data = json.loads(episodes_path.read_text(encoding="utf-8"))

    settings_dict = {f.name: getattr(settings, f.name) for f in fields(Settings)}
    demo_settings = Settings(**settings_dict)
    for key, value in data.get("settings_overrides", {}).items():
        if hasattr(demo_settings, key):
            setattr(demo_settings, key, value)

    store = LocalStore(demo_settings.db_path)
    # Keep demo deterministic across repeated runs.
    store.delete_all()
    runtime = AppRuntime(settings=demo_settings, store=store)

    results = []
    for ep in data["episodes"]:
        for c in ep.get("candidates", []):
            # Seed local learning for deterministic demo using observed count.
            for _ in range(max(1, int(c.get("count", 1)))):
                store.upsert_pattern(c["before"], c["after"])

        flags_raw = ep.get("flags", {})
        flags = RiskFlags(
            password_field=bool(flags_raw.get("password_field", False)),
            blacklisted_app=bool(flags_raw.get("blacklisted_app", False)),
            detector_uncertain=bool(flags_raw.get("detector_uncertain", False)),
            user_excluded=bool(flags_raw.get("user_excluded", False)),
        )

        out = await runtime.process_event(
            RuntimeEvent(
                kind="boundary",
                app_name=ep["context"]["app_name"],
                token=ep.get("token", ""),
                boundary=ep.get("boundary", " "),
                idle_ms=int(ep.get("idle_ms", 350)),
                typing_fast=bool(ep.get("typing_fast", False)),
                flags=flags,
            )
        )

        actions = []
        single = ep.get("post_action")
        if single:
            actions.append(single)
        actions.extend(ep.get("post_actions", []))

        for action in actions:
            if action == "accept":
                out = await runtime.process_event(RuntimeEvent(kind="accept"))
            elif action == "dismiss":
                out = await runtime.process_event(RuntimeEvent(kind="dismiss"))
            elif action == "undo":
                out = await runtime.process_event(RuntimeEvent(kind="undo"))
            elif action == "accept_then_undo":
                await runtime.process_event(RuntimeEvent(kind="accept"))
                out = await runtime.process_event(RuntimeEvent(kind="undo"))

        results.append(
            {
                "name": ep["name"],
                "expected": ep.get("expected_action"),
                "actual": out.action,
                "message": out.message,
            }
        )

    report = runtime.build_report()
    report_dict = report.to_dict()
    store.save_proof_report(report_dict)

    report_path = settings.report_dir / "demo_proof_report.json"
    report_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    ledger_path = settings.app_home / "demo_privacy_ledger.json"
    store.export_privacy_ledger(ledger_path)

    store.close()
    return {
        "report": report,
        "ledger_path": str(ledger_path),
        "report_path": str(report_path),
        "episodes": results,
    }
