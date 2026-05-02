from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cognitiveio.audit.events import SessionSummaryEvent
from cognitiveio.audit.writer import AuditWriter
from cognitiveio.config import settings_from_env, settings_from_env_with_policy
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
from cognitiveio.platform_requirements import evaluate_platform_requirements
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


def _render_requirements_report(report) -> None:
    table = Table(title="Platform Requirements")
    table.add_column("Check")
    table.add_column("Required")
    table.add_column("Current")
    table.add_column("Status")
    table.add_column("Details")
    for row in report.checks:
        status = "PASS" if row.passed else "FAIL"
        table.add_row(row.name, row.required, row.current, status, row.details)
    console.print(table)


def _print_requirements_remediation(report) -> None:
    failed = {row.name: row for row in report.checks if not row.passed}

    fm_row = failed.get("Apple FM runtime availability")
    if fm_row and fm_row.details.startswith("sdk_import_error:"):
        console.print("Apple FM SDK is not installed in the active virtual environment.")
        console.print("Recommended:")
        console.print("  ./bootstrap.sh")
        console.print("Manual install options:")
        console.print("Install one of the following:")
        console.print("  git clone https://github.com/apple/python-apple-fm-sdk")
        console.print("  uv pip install -e ./python-apple-fm-sdk")
        console.print("  uv pip install -e ../python-apple-fm-sdk")
        console.print("  uv pip install -e /absolute/path/to/python-apple-fm-sdk")
        console.print("Then verify:")
        console.print('  python -c "import apple_fm_sdk; print(apple_fm_sdk.__file__)"')


@app.command()
def run(
    mode: str = typer.Option("auto", help="Run mode: auto, mac, or headless."),
    app_name: str = typer.Option("Mail", help="Simulated active app for headless mode."),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip platform requirement checks."),
):
    """Run local runtime in macOS event-tap mode or headless mode."""
    settings, policy = settings_from_env_with_policy()
    store = _build_store(settings)
    runtime = AppRuntime(settings=settings, store=store, policy=policy)
    audit_writer = AuditWriter(policy)

    if policy.is_corporate:
        console.print(f"[bold]CIO-II Shield[/bold] Corporate: {policy.organization_name}")
    else:
        console.print("[bold]CIO-II Shield[/bold] Individual tier")

    console.print(
        f"FM arbiter: enabled={settings.apple_fm_enabled} variant={settings.apple_fm_variant} "
        f"required_for_gray_zone={settings.fm_required_for_gray_zone} "
        "(on-chip selector-only)"
    )

    # Corporate retention pruning on startup.
    if policy.is_corporate and policy.retention.prune_on_startup:
        pruned = store.prune_by_retention(policy.retention.audit_retention_days)
        if pruned > 0:
            console.print(f"Pruned {pruned} events (retention: {policy.retention.audit_retention_days} days)")

    selected_mode = mode.lower().strip()
    if selected_mode not in {"auto", "mac", "headless"}:
        console.print("Invalid mode. Use: auto, mac, or headless.")
        raise typer.Exit(code=1)

    use_mac = selected_mode == "mac" or (selected_mode == "auto" and mac_runtime_available())

    try:
        if use_mac and not skip_preflight:
            preflight_report = evaluate_platform_requirements()
            _render_requirements_report(preflight_report)
            if not preflight_report.passed:
                _print_requirements_remediation(preflight_report)
                console.print("Platform requirements failed. Fix the FAIL rows or use --skip-preflight.")
                raise typer.Exit(code=1)

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

        # Log session summary to audit trail.
        try:
            audit_writer.log_event(SessionSummaryEvent(
                accept_rate=float(report_dict.get("accept_rate", 0.0)),
                blocks=int(report_dict.get("blocked", 0)),
                redactions=0,
            ))
        except Exception:
            pass
        audit_writer.close()

        # Run corporate post-session hook if configured.
        if policy.is_corporate and policy.hooks.post_session_script:
            import subprocess
            script = policy.hooks.post_session_script
            if Path(script).is_file():
                try:
                    subprocess.run([script], timeout=30, check=False)
                except Exception:
                    pass

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


@app.command("requirements-check")
def requirements_check(
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Exit non-zero when requirements fail."),
):
    """Check Apple chip/macOS/Xcode and on-chip FM runtime requirements."""
    report = evaluate_platform_requirements()
    _render_requirements_report(report)
    if report.passed:
        console.print("All platform requirements are satisfied.")
        return
    _print_requirements_remediation(report)
    if strict:
        raise typer.Exit(code=1)


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


@app.command("policy-status")
def policy_status():
    """Show current CIO-II Shield tier, organization, and policy details."""
    from cognitiveio.policy.corporate import load_corporate_policy

    policy = load_corporate_policy()
    table = Table(title="CIO-II Shield Policy Status")
    table.add_column("Setting")
    table.add_column("Value")

    table.add_row("Tier", policy.tier)
    table.add_row("Organization ID", policy.organization_id or "(none)")
    table.add_row("Organization Name", policy.organization_name or "(none)")
    table.add_row("Schema Version", str(policy.schema_version))
    table.add_row("Issued At", policy.policy_issued_at or "(none)")
    table.add_row("Expires At", policy.policy_expires_at or "(none)")
    table.add_row("Expired", str(policy.is_expired))

    if policy.locked_settings:
        table.add_row("Locked Settings", json.dumps(policy.locked_settings, indent=2))
    else:
        table.add_row("Locked Settings", "(none)")

    if policy.force_blocked_apps:
        table.add_row("Force-Blocked Apps", ", ".join(sorted(policy.force_blocked_apps)))
    else:
        table.add_row("Force-Blocked Apps", "(none)")

    if policy.force_blocked_bundles:
        table.add_row("Force-Blocked Bundles", ", ".join(sorted(policy.force_blocked_bundles)))
    else:
        table.add_row("Force-Blocked Bundles", "(none)")

    table.add_row("Additional Secret Patterns", str(len(policy.additional_secret_patterns)))
    table.add_row("Retention Days", str(policy.retention.audit_retention_days))
    table.add_row("Prune on Startup", str(policy.retention.prune_on_startup))
    table.add_row("Compliance Export", str(policy.compliance.enabled))

    if policy.hooks.post_session_script:
        table.add_row("Post-Session Hook", policy.hooks.post_session_script)

    # Audit path.
    audit_writer = AuditWriter(policy)
    table.add_row("Audit Path", str(audit_writer.audit_dir))
    audit_writer.close()

    console.print(table)


@app.command("compliance-export")
def compliance_export(
    output: str = typer.Option("", "--output", help="Output path for compliance JSON."),
):
    """Generate a redacted compliance report from local data."""
    settings, policy = settings_from_env_with_policy()
    store = _build_store(settings)
    try:
        out_path = Path(output).expanduser() if output else settings.report_dir / "compliance_report.json"
        report = store.export_compliance_report(
            out_path,
            include_pattern_stats=policy.compliance.include_pattern_stats,
            include_secret_registry=policy.compliance.include_secret_registry,
            include_block_reasons=policy.compliance.include_block_reasons,
        )
        console.print(f"Compliance report saved: {out_path}")
        console.print(f"Machine ID hash: {report.get('machine_id_hash', 'N/A')}")
        block_reasons = report.get("block_reasons", [])
        if block_reasons:
            table = Table(title="Block Reason Summary")
            table.add_column("Reason")
            table.add_column("Count")
            for br in block_reasons:
                table.add_row(str(br["reason"]), str(br["count"]))
            console.print(table)
    finally:
        store.close()


@app.command("retention-prune")
def retention_prune(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview or execute pruning."),
    days: int = typer.Option(0, "--days", help="Override retention days (0 = use policy default)."),
):
    """Prune local data older than the retention policy window."""
    settings, policy = settings_from_env_with_policy()
    retention_days = days if days > 0 else policy.retention.audit_retention_days
    if retention_days < 1:
        console.print("No retention policy configured (days=0).")
        return

    store = _build_store(settings)
    try:
        if dry_run:
            # Count events that would be pruned.
            from datetime import datetime as dt
            cutoff = dt.now().timestamp() - (retention_days * 86400.0)
            cur = store.conn.cursor()
            cur.execute("SELECT COUNT(*) AS cnt FROM privacy_events WHERE ts < ?", (cutoff,))
            events_count = int(cur.fetchone()["cnt"] or 0)
            cur.execute("SELECT COUNT(*) AS cnt FROM proof_reports WHERE ts < ?", (cutoff,))
            reports_count = int(cur.fetchone()["cnt"] or 0)
            cur.execute("SELECT COUNT(*) AS cnt FROM secret_access_events WHERE ts < ?", (cutoff,))
            secrets_count = int(cur.fetchone()["cnt"] or 0)
            total = events_count + reports_count + secrets_count
            console.print(f"[DRY RUN] Would prune {total} rows older than {retention_days} days:")
            console.print(f"  privacy_events: {events_count}")
            console.print(f"  proof_reports: {reports_count}")
            console.print(f"  secret_access_events: {secrets_count}")
        else:
            pruned = store.prune_by_retention(retention_days)
            console.print(f"Pruned {pruned} rows older than {retention_days} days.")
    finally:
        store.close()


@app.command("audit-status")
def audit_status():
    """Show audit trail health: file count, last write, and integrity check."""
    from cognitiveio.policy.corporate import load_corporate_policy

    policy = load_corporate_policy()
    audit_writer = AuditWriter(policy)

    table = Table(title="Audit Trail Status")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Tier", audit_writer.tier)
    table.add_row("Audit Path", str(audit_writer.audit_dir))
    table.add_row("JSONL File Count", str(audit_writer.file_count()))

    last_write = audit_writer.last_write_time()
    if last_write:
        ts_str = datetime.fromtimestamp(last_write).isoformat(timespec="seconds")
        table.add_row("Last Write", ts_str)
    else:
        table.add_row("Last Write", "(no files)")

    # Integrity check on latest file.
    audit_dir = audit_writer.audit_dir
    if audit_dir.exists():
        files = sorted(audit_dir.glob("*.jsonl"), reverse=True)
        if files:
            latest_name = files[0].name
            integrity = audit_writer.verify_integrity(latest_name)
            table.add_row("Latest File", latest_name)
            table.add_row("Integrity Check", "PASS" if integrity else "FAIL / N/A")
        else:
            table.add_row("Latest File", "(none)")
            table.add_row("Integrity Check", "N/A")
    else:
        table.add_row("Latest File", "(audit dir not found)")
        table.add_row("Integrity Check", "N/A")

    audit_writer.close()
    console.print(table)


@app.command("session-status")
def session_status(
    limit: int = typer.Option(10, "--limit", help="Number of recent sessions to show."),
):
    """Show session history with warmth state and onboarding progression."""
    store, settings = _get_store()
    try:
        sessions = store.list_sessions(limit=limit)
        overall = store.overall_warmth_state()

        # Summary.
        console.print(f"[bold]Onboarding State[/bold]: {overall}")
        console.print(f"Total sessions: {store.session_count()}")
        console.print()

        if not sessions:
            console.print("No sessions recorded yet.")
            return

        table = Table(title="Recent Sessions")
        table.add_column("Session ID")
        table.add_column("Started")
        table.add_column("Warmth")
        table.add_column("Shown")
        table.add_column("Accepted")
        table.add_column("Dismissed")
        table.add_column("Accept Rate")
        table.add_column("Dominant App")
        for s in sessions:
            start_ts = s.get("start_ts", 0)
            started = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M") if start_ts else "?"
            shown = int(s.get("suggestions_shown", 0))
            accepted = int(s.get("suggestions_accepted", 0))
            dismissed = int(s.get("suggestions_dismissed", 0))
            rate = f"{accepted / max(shown, 1):.0%}" if shown > 0 else "-"
            table.add_row(
                str(s.get("session_id", ""))[:12],
                started,
                str(s.get("warmth_state", "embryonic")),
                str(shown),
                str(accepted),
                str(dismissed),
                rate,
                str(s.get("dominant_app", "")),
            )
        console.print(table)
    finally:
        store.close()


if __name__ == "__main__":
    app()
