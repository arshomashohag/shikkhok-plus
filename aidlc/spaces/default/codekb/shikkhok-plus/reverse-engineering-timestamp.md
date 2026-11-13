# Reverse Engineering Timestamp

## Run Record

- Date: 2026-11-13
- Commit: cb20fd12abf7dcb3100730f2f9aabc852fd552af

### What this run was

A **full rescan** for intent `261113-unique-usernames`, replacing the store built on 2026-10-22 at `b14b1fa` wholesale. The repository has grown since then (coaching centres, staff, payroll, expenses, extra fees, help centre, two-step verification, verify-first sign-up, email identity and passwords, class-change notifications; migrations 0018-0033), so every artifact was rebuilt from this run. The prior store was read for orientation only.

Collaborators were off: one developer agent did both the code scan (`inception/reverse-engineering/developer-scan.md` in the intent record) and this synthesis.

Depth was not uniform, and the Scope of Analysis block says so: the identity, sign-in, invitation, privacy-gate and schema areas the intent touches were read deeply; the other domain packages, the clients' non-identity features, infrastructure and workflows were read at module-docstring and inventory depth and are listed under `shallow.paths`. Build output, dependency folders, tool caches, the AI-DLC install and workspace, and the AI-tool scratch file `claude` were left unopened. `claude_design/` holds AI design-tool HTML mockups and is recorded as shallow reference, not as code.

### What was verified by running it

- `ruff check app tests` — all checks passed (local Ruff 0.16.9; CI pins 0.17.3)
- `ruff format --check app tests` — 548 files already formatted
- `openapi.json` parsed: OpenAPI 3.1.0, 150 paths, 174 operations, 226 component schemas
- Backend package import graph computed from the source (`dependencies.md`)

### What was not run

pytest and mypy: the Python dependencies are not installed in this environment. Test and coverage statements are counts and configured floors, not results from this run.

### Main findings

Recorded in `code-quality-assessment.md` (findings U1-U17 for the username change request, and the state of every control team.md assigned "before D1"). In short: the lockfiles, both CVE-scanning speeds, the Android quality toolchain, the `app.authz` strict island and the `PUBLIC_ROUTES` count have landed since 2026-10-22; Dependabot and a backend SBOM have not; the Bangla layout obligation is discharged by a manual table and nothing automated. For the intent: sign-in identity is a closed phone-or-email type, teacher recording and seat matching are phone-only, and there are no dormant teacher-created accounts in the current code despite prose that says there are.

## Scope of Analysis

```yaml
scope_version: 1
kind: full
intent: unique-usernames
fingerprint: b2b153221d369075481a09309061d20cbccf4897
analyzed:
  paths:
    - ./
  components:
    - app.main
    - app.request_scope
    - app.api
    - app.accounts
    - app.auth
    - app.authz
    - app.contract
    - app.schemas
    - app.db
    - app.errors
    - app.audit
    - app.gateway
    - app.money
    - app.fees
    - app.batches
    - app.students
    - app.guardians
    - app.centres
    - app.staff
    - app.payroll
    - app.expenses
    - app.teaching
    - app.marks
    - app.analytics
    - app.notifications
    - app.help
    - app.admin
    - app.governance
    - app.seed
    - migrations
    - android.core
    - android.feature.auth
    - android.feature.account
    - android.feature.profile
    - android.feature.invitations
    - android.feature.other
    - web.app
    - web.admin
    - site
    - infra
    - deploy
    - ci.workflows
    - scripts
shallow:
  paths:
    - app/fees/
    - app/money/
    - app/marks/
    - app/teaching/
    - app/analytics/
    - app/payroll/
    - app/expenses/
    - app/staff/
    - app/notifications/
    - app/gateway/
    - app/seed/
    - app/errors/
    - app/admin/
    - android/src/main/kotlin/com/shikkhokplus/app/feature/
    - web/src/features/teacher/
    - web/src/features/family/
    - web/src/admin/
    - site/
    - infra/
    - .github/workflows/deploy.yml
    - .github/workflows/release-android.yml
    - .github/workflows/security-scan.yml
    - docs/
    - store_listing/
    - claude_design/
```
