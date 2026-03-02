from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cognitiveio.config import settings_from_env
from cognitiveio.demo.demo_runner import run_demo
from cognitiveio.evidence.health_card import build_health_card, render_health_card
from cognitiveio.evidence.report_generator import (
    ProofReport,
    build_report_trend,
    generate_report_text,
    render_report_trend_text,
)
from cognitiveio.memory.language_assets import seed_common_language_assets
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.policy.risk_scoring import RiskFlags
from cognitiveio.runtime.app_runtime import AppRuntime, RuntimeEvent
from cognitiveio.runtime.mac_bridge import MacRuntimeBridge, mac_runtime_available
from cognitiveio.security import CompositeSecretProvider, EnvSecretProvider, SecretResolver
from cognitiveio.security.aliases import contains_secret_alias

app = typer.Typer(add_completion=False)
console = Console()


def _build_resolver(cache_ttl_seconds: float) -> SecretResolver:
    provider = CompositeSecretProvider.from_iterable([EnvSecretProvider()])
    return SecretResolver(provider=provider, cache_ttl_seconds=cache_ttl_seconds)


def _resolve_secret_ref(raw_value: str, resolver: SecretResolver) -> str:
    if not raw_value:
        return ""
    if not contains_secret_alias(raw_value):
        return raw_value
    resolved, unresolved = resolver.resolve_text(raw_value)
    if unresolved:
        return ""
    return resolved


def _build_store(settings) -> LocalStore:
    resolver = _build_resolver(settings.secret_cache_ttl_seconds)
    db_key = _resolve_secret_ref(settings.db_key_ref, resolver)
    return LocalStore(
        settings.db_path,
        encryption_mode=settings.db_encryption_mode,
        db_key=db_key or None,
    )


def _get_store() -> tuple[LocalStore, object]:
    settings = settings_from_env()
    return _build_store(settings), settings


def _seed_headless_defaults(store: LocalStore) -> None:
    store.upsert_pattern("teh", "the")
    store.upsert_pattern("recieve", "receive")
    store.upsert_pattern("wierd", "weird")
    seed_common_language_assets(store)


def _run_headless_loop(runtime: AppRuntime, settings, store: LocalStore, app_name: str) -> None:
    console.print("[bold]CIO-II[/bold] local interactive headless mode")
    console.print("Type one token/phrase at a boundary. Empty input exits.")
    console.print("Commands: /panic, /undo, /accept, /dismiss")
    _seed_headless_defaults(store)

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


@app.command()
def run(
    mode: str = typer.Option("auto", help="Run mode: auto, mac, or headless."),
    app_name: str = typer.Option("Mail", help="Simulated active app for headless mode."),
):
    """Run local runtime in macOS event-tap mode or headless mode."""
    settings = settings_from_env()
    store = _build_store(settings)
    runtime = AppRuntime(settings=settings, store=store)
    console.print(
        f"FM arbiter: enabled={settings.apple_fm_enabled} variant={settings.apple_fm_variant} "
        f"required_for_gray_zone={settings.fm_required_for_gray_zone} "
        "(on-chip selector-only)"
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
            try:
                bridge = MacRuntimeBridge(runtime)
                bridge.start()
            except RuntimeError as exc:
                if selected_mode == "mac":
                    raise
                console.print(f"mac mode unavailable ({exc}); falling back to headless.")
                _run_headless_loop(runtime, settings, store, app_name)
        else:
            _run_headless_loop(runtime, settings, store, app_name)

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
            blocked_protected_context=int(report.get("blocked_protected_context", 0)),
            blocked_trust_circuit=int(report.get("blocked_trust_circuit", 0)),
            blocked_candidate_conflict=int(report.get("blocked_candidate_conflict", 0)),
            blocked_profile_or_unknown=int(report.get("blocked_profile_or_unknown", 0)),
        )
        console.print(generate_report_text(parsed))
        history = store.list_proof_reports(limit=6)
        trend = build_report_trend(history)
        console.print("\n" + render_report_trend_text(trend))
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
        f"apple_fm_ab_enabled={settings.apple_fm_ab_enabled} "
        f"fm_required_for_gray_zone={settings.fm_required_for_gray_zone}"
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


@app.command("schema-check")
def schema_check():
    """Validate required local schema objects exist."""
    store, _settings = _get_store()
    try:
        cur = store.conn.cursor()
        cur.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table'
            """
        )
        existing = {str(r["name"]) for r in cur.fetchall()}
        required = {
            "error_patterns",
            "privacy_events",
            "proof_reports",
            "secret_access_events",
            "secret_alias_registry",
            "phrase_patterns",
            "concept_lexicon",
        }
        missing = sorted(required - existing)
        if missing:
            console.print(f"Missing schema tables: {', '.join(missing)}")
            raise typer.Exit(code=1)
        console.print("Schema check passed.")
    finally:
        store.close()


@app.command("seed-language-assets")
def seed_language_assets():
    """Seed common phrase and concept library for context-aware assistance."""
    store, _settings = _get_store()
    try:
        counts = seed_common_language_assets(store)
        console.print(
            f"Seeded language assets: phrases={counts['phrases']} concepts={counts['concepts']}"
        )
    finally:
        store.close()


@app.command("required-secrets")
def required_secrets(limit: int = typer.Option(100, help="Maximum aliases to display.")):
    """List required secret aliases observed in suggestions/workflows."""
    store, _settings = _get_store()
    try:
        rows = store.list_secret_aliases(limit=max(1, limit))
        if not rows:
            console.print("No secret aliases recorded yet.")
            return

        table = Table(title=f"Required Secret Aliases (count={len(rows)})")
        table.add_column("Alias")
        table.add_column("Usage")
        table.add_column("Last Seen")
        table.add_column("Description")

        for row in rows:
            ts = datetime.fromtimestamp(float(row["last_seen"])).isoformat(timespec="seconds")
            table.add_row(
                str(row["alias"]),
                str(row["usage_count"]),
                ts,
                str(row["description"] or ""),
            )
        console.print(table)
    finally:
        store.close()


@app.command("explain-last")
def explain_last(json_output: bool = typer.Option(False, "--json", help="Print raw JSON snapshot.")):
    """Explain the latest runtime decision from the local decision snapshot file."""
    settings = settings_from_env()
    snapshot_path = settings.report_dir / "latest_decision.json"
    if not snapshot_path.exists():
        console.print("No decision snapshot found. Run CIO-II and trigger at least one boundary event.")
        raise typer.Exit(code=1)

    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"Failed to parse decision snapshot: {exc}")
        raise typer.Exit(code=1) from exc

    if not isinstance(snapshot, dict):
        console.print("Decision snapshot is invalid.")
        raise typer.Exit(code=1)

    if json_output:
        console.print(json.dumps(snapshot, indent=2))
        return

    table = Table(title="Latest Decision Snapshot")
    table.add_column("Field")
    table.add_column("Value")
    ordered_fields = [
        "action",
        "reason_tag",
        "app_name",
        "profile",
        "token",
        "idle_ms",
        "typing_fast",
        "trust_cooldown_remaining_seconds",
    ]
    for field in ordered_fields:
        table.add_row(field, str(snapshot.get(field, "")))
    candidates = snapshot.get("candidates", [])
    table.add_row("candidates", str(len(candidates)) if isinstance(candidates, list) else "0")
    console.print(table)

    if isinstance(candidates, list) and candidates:
        cand_table = Table(title="Top Candidate Preview")
        cand_table.add_column("ID")
        cand_table.add_column("Before")
        cand_table.add_column("After")
        cand_table.add_column("Confidence")
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            cand_table.add_row(
                str(cand.get("id", "")),
                str(cand.get("before", "")),
                str(cand.get("after", "")),
                f"{float(cand.get('confidence', 0.0)):.2f}",
            )
        console.print(cand_table)


@app.command("phrase-add")
def phrase_add(
    trigger: str = typer.Argument(..., help="Trigger text, e.g. .meW"),
    expansion: str = typer.Argument(..., help="Expanded output text."),
    profile: str = typer.Option("email_docs", help="Context profile: email_docs, chat, or empty."),
    confidence: float = typer.Option(0.95, help="Initial confidence 0.0-1.0"),
):
    """Add or update a context-aware phrase expansion."""
    if not trigger.strip():
        console.print("Trigger cannot be empty.")
        raise typer.Exit(code=1)
    if not expansion.strip():
        console.print("Expansion cannot be empty.")
        raise typer.Exit(code=1)

    c = max(0.01, min(1.0, confidence))
    p = profile.strip()

    store, _settings = _get_store()
    try:
        store.upsert_phrase_pattern(
            phrase_before=trigger,
            phrase_after=expansion,
            profile=p,
            confidence=c,
        )
        console.print(
            f"Saved phrase: trigger='{trigger}' profile='{p or '*'}' confidence={c:.2f}"
        )
    finally:
        store.close()


@app.command("phrase-list")
def phrase_list(
    profile: str = typer.Option("", help="Optional profile filter."),
    limit: int = typer.Option(100, help="Maximum rows to show."),
):
    """List configured phrase expansions."""
    store, _settings = _get_store()
    try:
        rows = store.list_phrase_patterns(profile=profile.strip(), limit=max(1, limit))
        if not rows:
            console.print("No phrase patterns found.")
            return

        table = Table(title=f"Phrase Patterns (count={len(rows)})")
        table.add_column("Trigger")
        table.add_column("Expansion")
        table.add_column("Profile")
        table.add_column("Confidence")
        table.add_column("Frequency")

        for row in rows:
            table.add_row(
                str(row["before"]),
                str(row["after"]),
                str(row["profile"] or "*"),
                f"{float(row['confidence']):.2f}",
                str(row["frequency"]),
            )
        console.print(table)
    finally:
        store.close()


@app.command("phrase-remove")
def phrase_remove(
    trigger: str = typer.Argument(..., help="Trigger text to remove."),
    profile: str = typer.Option("email_docs", help="Profile for scoped removal."),
    all_profiles: bool = typer.Option(False, "--all-profiles", help="Remove across all profiles."),
):
    """Remove phrase expansions by trigger (profile-scoped by default)."""
    p = "" if all_profiles else profile.strip()
    store, _settings = _get_store()
    try:
        removed = store.delete_phrase_pattern(phrase_before=trigger, profile=p)
        if removed <= 0:
            console.print("No matching phrase patterns removed.")
            raise typer.Exit(code=1)
        scope = "*" if all_profiles else (p or "*")
        console.print(f"Removed {removed} phrase pattern(s) for trigger='{trigger}' profile='{scope}'.")
    finally:
        store.close()


if __name__ == "__main__":
    app()
