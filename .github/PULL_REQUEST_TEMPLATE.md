## Summary
- Task ID(s): `T-XXX`
- Finding ID(s): `F-XXX`
- Priority: `P0|P1|P2|P3`

## Traceability
- Exact report quote(s) addressed:
  - `"..."`

## Verification Evidence
- [ ] `ruff check src tests`
- [ ] `mypy src`
- [ ] `pytest -q`
- [ ] `./verify-mitigations.sh`

## Security & Safety
- [ ] No plaintext secrets added to code, logs, or reports
- [ ] Secret alias paths tested (`{{SECRET:...}}`)
- [ ] Rollback steps validated

## Docs
- [ ] README/docs updated for behavior or config changes
- [ ] New env vars reflected in `.env.example`

## Rollout
- Feature flags:
  - `COGNITIVEIO_ENABLE_APPLE_FM=`
  - `COGNITIVEIO_DB_ENCRYPTION=`
- Monitoring signals:
  - acceptance/dismiss/undo rates
  - blocked reason distribution
