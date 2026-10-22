# Reverse Engineering Timestamp

## Run Record

- Date: 2026-10-22
- Commit: b14b1fab94768602a0e396e03ec32b079ffb9cf4

### What this run was

The first scan of this repository — the store check returned `NO_STORE`, so
this is a **full scan** creating all nine artifacts from scratch. Store
generation at the pre-scan snapshot: `none`.

The whole repository was analyzed. Build outputs, dependency folders and
tool caches were left unopened per the "What to Skip" rule, and AI-DLC's own
install (`.claude/` and the `aidlc/` workspace) is not the project's code
and was not scanned or documented.

### What was verified by running it, not by reading it

- `python3 -m pytest tests` — **615 passed**, 35 s
- `python3 -m pytest tests --cov=app.money --cov-branch` — **100.00%**
  branch, `fail_under = 100` reached
- the 13-package backend coverage run against `.coveragerc-backend` —
  **91%** line, floor 80%
- `python3 -m pytest tests/privacy tests/db tests/batches` — **115 passed**
  against a real PostgreSQL 16 container (Docker was reachable)
- `ruff check app tests` — all checks passed
- `ruff format --check app tests` — 135 files already formatted
- `mypy app` — no issues in 65 source files
- `openapi.json` parsed and reconciled against the four registered routers:
  12 operations, 11 paths, 19 component schemas, all matching

### Findings recorded in the artifacts

Three items of drift between a written decision and the code, documented in
`code-quality-assessment.md` with file and line:

1. `app.authz` is named as a mypy strict island and is not configured in
   `pyproject.toml`.
2. `PUBLIC_ROUTES` holds six entries under a comment stating "exactly five",
   and two of them allowlist `/account-deletion` paths that no handler
   registers.
3. The `check.yml` step labelled "Lockfile verification, Python side"
   performs an unpinned `pip install -e`.

No live security hole was found. The largest gaps are absences rather than
defects: no dependency lockfile on either application surface, no CVE
scanning anywhere, and the entire Android quality toolchain (ktlint,
spotless, detekt, `lint.xml`, Kotlin coverage, screenshot tests) unbuilt.

## Scope of Analysis

```yaml
scope_version: 1
kind: full
intent: remaining-slices
fingerprint: 7599d1532485cb8715d7d2aee3a583674ebb01d3
analyzed:
  paths:
    - ./
  components:
    - app.main
    - app.config
    - app.api
    - app.authz
    - app.auth
    - app.money
    - app.schemas
    - app.db
    - app.contract
    - app.errors
    - app.gateway
    - app.audit
    - app.governance
    - app.batches
    - core.model
    - core.network
    - core.designsystem
    - core.format
    - core.ui
    - feature.auth
    - feature.batches
    - feature.roster
    - MainActivity
    - infra (Terraform root)
    - infra.modules
    - infra.bootstrap
shallow:
  paths:
    - store_listing/
    - claude_design/
    - infra/modules/cdn/
    - infra/modules/network/
    - infra/modules/registry/
    - android/src/main/res/drawable/
    - android/src/main/res/mipmap-anydpi-v26/
```
