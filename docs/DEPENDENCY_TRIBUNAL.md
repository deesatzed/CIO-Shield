# Dependency Tribunal

## `typer`, `rich`
- Charge: CLI surface and readable reports.
- Verdict: Acquitted.
- Replacement path: Python stdlib argparse + plain print.

## `sqlite3` (stdlib)
- Charge: local persistence.
- Verdict: Acquitted.
- Replacement path: JSONL append-only files.

## `python-apple-fm-sdk` (core on-chip arbiter)
- Charge: on-device arbiter in gray zone.
- Verdict: Required for full FM-first ambiguous-case handling.
- Failure mode: unavailable or policy violation.
- Replacement path: fail-closed `do_nothing` in gray-zone.

## `pyobjc` (future runtime adapter)
- Charge: native macOS capture/apply hooks.
- Verdict: Probationary (adapter boundary only).
- Replacement path: headless mode + manual input adapters.
