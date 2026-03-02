# CIO-II Git Workflow

## Branch Naming
Use one branch per remediation task:

```bash
git checkout -b remediation/T-XXX-short-slug
```

Examples:
- `remediation/T-001-headless-fallback`
- `remediation/T-006-secret-redaction`

## Commit Template
Use the repository commit template:

```bash
git config commit.template .gitmessage-remediation.txt
```

Format:
- `fix(Px): <task title> [T-XXX]`

## Pull Requests
1. Link every PR to at least one `F-XXX` and `T-XXX`.
2. Include exact report quote(s) in the PR body.
3. Attach verification command output.
4. Document rollback path.

## Merge Requirements
1. CI must pass.
2. `./verify-mitigations.sh` must pass locally.
3. Security-sensitive changes require explicit reviewer acknowledgement.
