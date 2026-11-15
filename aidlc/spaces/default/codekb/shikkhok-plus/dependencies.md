# Dependencies — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. Declared versions are in `technology-stack.md`; this file records how dependencies are locked, scanned and updated, and how the internal packages depend on each other.

## External dependencies: locking and verification

| Surface | Lock | Verification | CI step |
|---|---|---|---|
| Python | `requirements.txt` (pip-compile from `pyproject.toml` extras `dev` + `api`, 2,039 `--hash=sha256` entries) | `pip install --require-hashes -r requirements.txt`, then `pip install -e . --no-deps` | `check.yml` "Install from the lockfile"; "Lockfile is current" re-compiles seeded from the committed file and diffs pins and hashes; `make lock` regenerates |
| Docker image | Base image pinned by digest; installs from the same `requirements.txt` with `--require-hashes` | Digest pin | `Dockerfile:31,49-61,74` |
| Android (Gradle) | `android/gradle.lockfile` (372 lines), `settings-gradle.lockfile` | `gradle/verification-metadata.xml` (663 components, sha256) | Gradle refuses an unverified artifact on any build |
| Web | `web/package-lock.json` | npm integrity hashes | `make web` runs `npm ci --no-audit --no-fund` then `npm run check` |
| Site | none — no dependencies (`site/package.json` declares no packages) | — | `make site` |
| Terraform | `infra/.terraform.lock.hcl`, `infra/bootstrap/.terraform.lock.hcl` (tracked; contents not opened) | provider hashes | `deploy.yml` plan |

## CVE scanning (two-speed model)

| Speed | Python | Android | Web | Image |
|---|---|---|---|---|
| Per push, annotating (`continue-on-error`) | `pip-audit --requirement requirements.txt --strict` (`check.yml:178`) | osv-scanner on the Gradle lockfiles (`check.yml:427`) | npm audit step (`check.yml:491`) | — |
| Release gate, blocking on Critical/High unless excepted | `deploy/cve_gate.py` over pip-audit JSON (`deploy.yml:239-248`, production only) | osv-scanner in `release-android.yml:163-181` through the same gate | production web job (`deploy.yml:1214` *comment*) | ECR image-scan findings through `cve_gate.py` (`deploy.yml:771-789`) |

Exceptions: `.security-exceptions.md` (dated rows; an expired row fails the gate on its own). It holds no exceptions today.

Not present: Dependabot or any automated update PRs (`.github/dependabot.yml` absent), a backend SBOM (`deploy.yml:766` `sbom: false`). The Android release attaches an SPDX SBOM from Syft (`release-android.yml:441-466`).

## External service dependencies

| Dependency | Failure handling | Evidence |
|---|---|---|
| PostgreSQL 16 (RDS) | Connection failure fails fast; serialization failure is a bounded retry; the `(enrollment_id, period)` conflict is the success path | team.md Error handling; `app/request_scope.py` |
| BulkSMSBD | One attempt, no retry; timeout recorded as unknown; daily send budgets checked at the send | `app/gateway/sms.py`, `app/auth/delivery.py` |
| Amazon SES (SMTP) | Own global daily email budget | `app/gateway/ses_smtp.py`, `app/auth/ceilings.py` `EMAIL_GLOBAL_DAILY` |
| FCM | Best-effort after commit; failure logged, not surfaced | `app/notifications/fcm.py` |

## Internal dependencies (backend package import graph)

Computed this run from `from app.<pkg>` imports (package level, self-imports dropped):

| Package | Imports |
|---|---|
| `accounts` | audit, auth, authz, centres, db, errors |
| `auth` | accounts (identifier only), audit, errors, gateway |
| `authz` | accounts (identifier/phone canonicalisers, in `admin.py` only), db, errors, money |
| `schemas` | accounts (identifier, phone, clients), auth (password bounds), money |
| `api` | every domain package, schemas, auth, authz, gateway |
| `students` | analytics, authz, batches, db, errors, money |
| `batches` | authz, db, errors, local_time, money, students |
| `centres` | authz, db, errors, teaching |
| `fees` | accounts, analytics, authz, db, errors, local_time, money, notifications, teaching |
| `teaching` | authz, batches, centres, db, errors, fees, local_time, notifications, schemas |
| `marks` | authz, centres, db, errors, local_time, notifications, schemas, teaching |
| `analytics` | authz, db, errors, fees, local_time, marks, money, teaching |
| `governance` | accounts, analytics, db, fees, money, teaching |
| `notifications` | authz, db, errors, local_time, money, teaching |
| `payroll` | authz, centres, db, errors, expenses, fees, local_time, money |
| `staff` | authz, centres, db, errors, local_time, money, teaching |
| `expenses` | analytics, authz, db, errors, fees, local_time, money |
| `guardians` | authz, db, errors, fees, local_time, money |
| `help` | accounts, errors |
| `admin` | accounts, audit, auth, authz, errors, help |
| `db` | config, money |
| `contract` | authz, main, money, schemas |
| `money` | nothing in `app` (enforced by an AST test) |

Package-level cycles (module-level imports do not loop; they are package pairs importing different modules of each other): accounts and auth (`auth/otp.py`, `pending.py`, `delivery.py` import `accounts.identifier`), accounts and authz (`authz/admin.py` imports the canonicalisers), batches and students, fees and teaching, centres and teaching, notifications and teaching, analytics and fees, config and gateway.

**Bearing on the username intent**: `app.accounts.identifier` is the shared leaf the identity code depends on — `auth.otp`, `auth.pending`, `auth.delivery`, `schemas.identifier`, `accounts.contact`, `accounts.passwords`, `api.deletion`. A change to `Identifier` or `Channel` reaches all of them; a username resolver kept outside `Identifier` reaches only `accounts.passwords` and the sign-in schema (*inferred*).

## Client-to-server dependencies

- Both clients depend on `openapi.json`: the web client generates `src/api/schema.d.ts` from it (`npm run gen:api`); the Android DTOs are hand-written in `core/network/*Dto.kt` and checked by tests against the contract (*inferred from `MessageKeyCoverageTest` and DTO tests*).
- Both clients depend on `message-keys.json`: every server `message_key` must have a string in each client (Android bundles 1,539 strings per language).
- The privacy policy depends on `app/governance/dispositions.py` through `scripts/generate_privacy_policy.py`.
