from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cognitiveio.config import settings_from_env
from cognitiveio.demo.demo_runner import run_demo
from cognitiveio.evidence.health_card import build_health_card, render_health_card
from cognitiveio.evidence.report_generator import ProofReport, generate_report_text
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.policy.risk_scoring import RiskFlags
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent
from cognitiveio.runtime.mac_bridge import MacRuntimeBridge, mac_runtime_available

app = typer.Typer(add_completion=False)
console = Console()


def _get_store() -> tuple[LocalStore, object]:
    settings = settings_from_env()
    return LocalStore(settings.db_path), settings


@app.command()
def run(
    mode: str = typer.Option("auto", help="Run mode: auto, mac, or headless."),
    app_name: str = typer.Option("Mail", help="Simulated active app for headless mode."),
):
    """Run local runtime in macOS event-tap mode or headless mode."""
    settings = settings_from_env()
    store = LocalStore(settings.db_path)
    runtime = AppRuntime(settings=settings, store=store)
    console.print(
        f"FM arbiter: enabled={settings.apple_fm_enabled} variant={settings.apple_fm_variant} "
        f"(A=deterministic, B=arbiter-gray-zone)"
    )

    selected_mode = mode.lower().strip()
    if selected_mode not in {"auto", "mac", "headless"}:
        console.print("Invalid mode. Use: auto, mac, or headless.")
        raise typer.Exit(code=1)

    use_mac = selected_mode == "mac" or (selected_mode == "auto" and mac_runtime_available())

    try:
        if use_mac:
            if not mac_runtime_available():
                console.print("PyObjC is not available; cannot run in mac mode.")
                raise typer.Exit(code=1)
            bridge = MacRuntimeBridge(runtime)
            bridge.start()
        else:
            console.print("[bold]CIO-II[/bold] local interactive headless mode")
            console.print("Type one token at a time. Empty input exits.")
            console.print("Commands: /panic, /undo, /accept, /dismiss")

            while True:
                token = input("token> ").strip()
                if token == "":
                    break

                if token == "/panic":
                    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="panic")))
                    console.print(out.message)
                    continue
                if token == "/undo":
                    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="undo")))
                    console.print(out.message)
                    continue
                if token == "/accept":
                    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="accept")))
                    console.print(out.message)
                    continue
                if token == "/dismiss":
                    out = asyncio.run(runtime.process_event(RuntimeEvent(kind="dismiss")))
                    console.print(out.message)
                    continue

                # Lightweight on-the-fly learning seed for demonstration.
                if token.lower() in {"teh", "recieve", "wierd"}:
                    mapping = {"teh": "the", "recieve": "receive", "wierd": "weird"}
                    store.upsert_pattern(token, mapping[token.lower()])

                out = asyncio.run(
                    runtime.process_event(
                        RuntimeEvent(
                            kind="boundary",
                            app_name=app_name,
                            token=token,
                            boundary=" ",
                            idle_ms=settings.idle_pause_ms + 60,
                            typing_fast=False,
                            flags=RiskFlags(),
                        )
                    )
                )
                console.print(out.message)

    finally:
        report = runtime.build_report()
        report_dict = report.to_dict()
        store.save_proof_report(report_dict)
        out_path = settings.report_dir / "latest_run_report.json"
        out_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
        console.print(f"Saved report: {out_path}")
        store.close()


@app.command()
def demo():
    """Run deterministic showpiece demo and persist proof artifacts."""
    settings = settings_from_env()
    result = asyncio.run(run_demo(settings))

    table = Table(title="Demo Episodes")
    table.add_column("Episode")
    table.add_column("Expected")
    table.add_column("Actual")
    table.add_column("Message")

    for item in result["episodes"]:
        table.add_row(item["name"], str(item.get("expected")), str(item.get("actual")), item.get("message", ""))

    console.print(table)
    console.print(generate_report_text(result["report"]))
    console.print(f"\nSaved privacy ledger to: {Path(result['ledger_path'])}")
    console.print(f"Saved proof report to: {Path(result['report_path'])}")


@app.command("proof-report")
def proof_report():
    """Print latest local proof report."""
    store, _settings = _get_store()
    try:
        report = store.latest_proof_report()
        if not report:
            console.print("No proof report found.")
            raise typer.Exit(code=1)

        parsed = ProofReport(
            minutes=float(report["minutes"]),
            suggestion_shown=int(report["suggestion_shown"]),
            suggestion_accepted=int(report["suggestion_accepted"]),
            suggestion_dismissed=int(report["suggestion_dismissed"]),
            auto_applied=int(report["auto_applied"]),
            undone=int(report["undone"]),
            blocked=int(report["blocked"]),
            interruption_rate_per_min=float(report["interruption_rate_per_min"]),
            accept_rate=float(report["accept_rate"]),
            dismiss_rate=float(report["dismiss_rate"]),
            undo_rate=float(report["undo_rate"]),
            top_patterns=list(report.get("top_patterns", [])),
            top_block_reasons=list(report.get("top_block_reasons", [])),
        )
        console.print(generate_report_text(parsed))
    finally:
        store.close()


@app.command("health-card")
def health_card():
    """Generate and print current organism health card from latest report."""
    store, _settings = _get_store()
    try:
        report = store.latest_proof_report()
        if not report:
            console.print("No proof report found.")
            raise typer.Exit(code=1)
        card = build_health_card(report)
        console.print(render_health_card(card))
    finally:
        store.close()


@app.command("privacy-ledger")
def privacy_ledger(
    limit: int = typer.Option(25, help="Number of latest events to display."),
    export_path: str = typer.Option("", help="Optional path to export JSON ledger."),
):
    """View and export privacy ledger (stored/blocked events only)."""
    store, _settings = _get_store()
    try:
        events = store.get_privacy_events(limit=limit)
        if not events:
            console.print("Privacy ledger is empty.")
        else:
            table = Table(title=f"Privacy Ledger (latest {len(events)})")
            table.add_column("Timestamp")
            table.add_column("Kind")
            table.add_column("Reason")
            table.add_column("App")
            table.add_column("Event Type")

            for e in events:
                table.add_row(
                    str(e["ts"]),
                    str(e["kind"]),
                    str(e["reason"]),
                    str(e.get("app_name", "")),
                    str(e.get("event_type", "")),
                )
            console.print(table)

        if export_path:
            p = Path(export_path).expanduser()
            store.export_privacy_ledger(p)
            console.print(f"Exported ledger to: {p}")
    finally:
        store.close()


@app.command("arbiter-status")
def arbiter_status():
    """Print local Apple FM arbiter flag + stable A/B variant."""
    settings = settings_from_env()
    console.print(
        f"apple_fm_enabled={settings.apple_fm_enabled} "
        f"apple_fm_variant={settings.apple_fm_variant} "
        f"apple_fm_ab_enabled={settings.apple_fm_ab_enabled}"
    )


@app.command("delete-all")
def delete_all(confirm: bool = typer.Option(False, "--confirm", help="Required confirmation flag.")):
    """Delete all locally stored patterns, ledger events, and proof reports."""
    if not confirm:
        console.print("Refusing delete-all without --confirm")
        raise typer.Exit(code=1)

    store, _settings = _get_store()
    try:
        store.delete_all()
        console.print("Deleted all local CIO-II data.")
    finally:
        store.close()


if __name__ == "__main__":
    app()
