# Developer Code Scan — shikkhok-plus (full rescan, 2026-11-13)

Commit scanned: `cb20fd12abf7dcb3100730f2f9aabc852fd552af`. Intent: `261113-unique-usernames`.
Collaborators are off, so this scan and the nine-artifact synthesis come from the same agent.

## Developer Code Scan Results

### Scan Coverage

- **Analyzed deeply** (read in full, or read the parts the intent touches and the module docstrings of everything else):
  - `app/accounts/` (identifier, phone, contact, service, passwords; docstrings and signatures of decisions, clients, mfa)
  - `app/auth/` (otp, pending, the structure of ceilings, tokens lifetimes and algorithm; docstrings of the rest)
  - `app/api/auth.py`, `app/api/accounts.py`, `app/api/credentials.py`, `app/api/me.py`, `app/api/deps.py` (auth dependencies), `app/api/deletion.py` (in-app path)
  - `app/authz/` (invitations, rls, lens types, resolve/summary signatures)
  - `app/contract/privacy.py`, `app/contract/routes.py`
  - `app/schemas/identifier.py`, `app/schemas/phone.py`, `app/schemas/auth.py`, `app/schemas/students.py`, and the phone fields of `app/schemas/batches.py` and `app/schemas/centres.py`
  - `app/db/models.py` (Account, Profile, OtpRequest, PendingSignup, Owner, OwnerMember, Student, Enrollment, plus the class index)
  - `app/students/service.py` (identity and relink paths), `app/batches/service.py` (`_account_for`), `app/centres/memberships.py` (phone link)
  - `app/governance/dispositions.py` (identity tables), `app/help/identity.py`, `app/main.py` (router registration)
  - `migrations/versions/0032_email_identity_and_passwords.py`, the RLS part of `0001`
  - `pyproject.toml`, `requirements.txt` (header and hash count), `Dockerfile` (base images), `.github/workflows/check.yml` (lockfile, CVE, Docker-precondition and junit steps), `.security-exceptions.md`, `deploy/cve_gate.py` (header)
  - `android/build.gradle.kts` (plugins), `android/lint.xml`, `android/detekt.yml` (forbidden imports), `android/coverage.gradle.kts` (header), `android/coverage-floor.txt`, `gradle/libs.versions.toml`
  - Android `core/model/Identifier.kt`, `feature/auth/AuthUiState.kt`, `feature/auth/AuthViewModel.kt` (interface), `feature/account/AccountViewModels.kt`, `feature/profile/ui/DeleteAccountScreen.kt` (confirmation)
  - Web `web/package.json`, `web/src/features/auth/identifier.ts`, `web/src/features/auth/SignUp.tsx` (the already-added lookup)
  - `openapi.json` (parsed: every operation and its 2xx response schema)
  - `tests/` (directory layout, test counts per directory, the privacy-gate and PUBLIC_ROUTES assertions)
- **Skimmed only** (module docstrings and file inventory, not every line):
  - `app/fees/`, `app/money/`, `app/marks/`, `app/teaching/`, `app/analytics/`, `app/payroll/`, `app/expenses/`, `app/staff/`, `app/centres/service.py`, `app/notifications/`, `app/help/tickets.py`, `app/admin/`, `app/gateway/`, `app/seed/`, `app/errors/`, `app/db/` (other than models)
  - `migrations/versions/` other than 0032 and the RLS block of 0001 (file names and line counts)
  - `android/src/` other than the files above (package tree), `web/src/` other than the files above (feature tree), `site/`
  - `infra/` (module list, database encryption and engine), `deploy/` (README head), `.github/workflows/deploy.yml`, `release-android.yml`, `security-scan.yml` (job and step names)
  - `docs/` (delivery, legal, reviews 2026-11-11 security head and sprint plan, superpowers plans), `store_listing/`, `scripts/`
  - `claude_design/`: five self-contained HTML design mockups exported from an AI design tool (bundled fonts, no code the app uses); kept as design reference, not project code
- **Left out** (not opened):
  - `claude` (a five-line file of AI-tool session-resume commands: AI-tool scratch, not project code)
  - AI-DLC's own install and workspace: `.claude/`, `aidlc/`, the AI-DLC block of `.gitignore`, `.mcp.json`
  - `.git/`, `.gradle/`, `build/`, `.kotlin/`, `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `**/.terraform/` (ignored or tool caches)
  - `web/package-lock.json` (lockfile contents; existence noted only), `web/src/api/schema.d.ts` (generated from `openapi.json`)

### Packages Found

- `shikkhokplus` (backend, `app/`) — FastAPI service — Python 3.12 — the whole server: identity, lenses, batches, students, fees, teaching, marks, centres, payroll, help, admin, governance
- `migrations/` — Alembic revision chain 0001..0033 — Python — the schema source of truth (`app/db/models.py` describes it; a parity test checks)
- `android` (Gradle module `:android`, namespace `com.shikkhokplus.app`) — Android app — Kotlin, Jetpack Compose — 375 main source files, 211 test files
- `shikkhokplus-web` (`web/`) — PWA client plus a separate admin build — TypeScript, React 19, Vite 7 — 249 source files, 61 test files
- `shikkhokplus-site` (`site/`) — public static site — Node build script, no runtime JavaScript
- `infra/` — Terraform root plus `infra/bootstrap/` and nine modules (network, registry, app, cdn, site, admin, database, email, seeder)
- `deploy/` — deploy-time scripts: `cve_gate.py`, `smoke.py`, `roll.sh`, staging compose file
- `scripts/` — `generate_privacy_policy.py` (privacy policy from the governance manifest), `release_notes.py`

### Build System

- **Type**: Make as the one entrypoint (`make check` = `lint typecheck test android android-quality web site infra-functions`), over hatchling/pip (Python), Gradle Kotlin DSL (Android), npm (web, site), Terraform (infra), Docker (image)
- **Config Files**: `Makefile`, `pyproject.toml`, `requirements.txt` (pip-compile, 2039 sha256 hashes), `alembic.ini`, `Dockerfile`, `docker-compose.yml`, `settings.gradle.kts`, `settings-gradle.lockfile`, `gradle.properties`, `gradle/libs.versions.toml`, `gradle/verification-metadata.xml`, `android/build.gradle.kts`, `android/gradle.lockfile`, `android/coverage.gradle.kts`, `android/release-gates.gradle.kts`, `web/package.json` + `package-lock.json`, `site/package.json`, `infra/versions.tf`
- **Build Dependencies**: `web` generates `src/api/schema.d.ts` from the root `openapi.json`; `openapi.json` is generated from the FastAPI app (`make openapi`) and gated by a schema-diff test; Android and web both read `message-keys.json` (server message-key contract); `scripts/generate_privacy_policy.py` reads `app/governance/dispositions.py`

### APIs Discovered

- REST/JSON (FastAPI) — `app/api/` (27 routers + a staging-only router) — 150 paths, 174 operations, 226 component schemas in the committed `openapi.json` (OpenAPI 3.1.0)
- HTML — `GET /account-deletion` (the external deletion page, `app/api/deletion.py`, `app/api/html.py`)
- Outbound — SMS (BulkSMSBD, `app/gateway/bulksmsbd.py`), email (Amazon SES over SMTP, `app/gateway/ses_smtp.py`), push (FCM, `app/notifications/fcm.py`)
- Seeder Lambda entrypoint — `app/seed/lambda_runtime.py` (non-production hosts)

### Frameworks & Libraries

- FastAPI — 0.162.0 — HTTP layer
- Pydantic — 2.14.2 — request/response schemas
- SQLAlchemy — 2.1.6 — ORM and raw SQL
- Alembic — 1.20.1 — migrations
- psycopg[binary] — 3.3.6 — PostgreSQL 16 driver
- PyJWT — 2.15.1 — HS256 access and scoped tokens
- cryptography — 50.0.2 — AES-256-GCM for authenticator secrets
- uvicorn[standard] — 0.54.0 — ASGI server
- httpx — 0.28.1 — outbound HTTP (SMS gateway)
- pytest 9.2.0, pytest-cov 7.1.0, hypothesis 6.170.13, testcontainers[postgres] 4.15.0 — tests
- ruff 0.17.3, mypy 2.4.1, pip-tools 7.6.2, pip-audit 2.10.1 — tooling
- Android: AGP 8.7.3, Kotlin 2.0.21, Compose BOM 2024.10.01, Ktor 2.3.12, kotlinx-serialization 1.7.3, WorkManager 2.9.1, security-crypto 1.1.0-alpha06, Robolectric 4.14.1, spotless 6.25.0, ktlint 1.5.0, detekt 1.23.7
- Web: React 19.3.1, react-router 7.18.5, Vite 7.3.7, vite-plugin-pwa 1.3.0, Vitest 4.1.12, TypeScript 5.9.3, ESLint 9.39.5, Prettier 3.9.10, openapi-typescript 7.13.0

### Test Coverage

- **Test Directories**: `tests/` (29 subdirectories; about 2,190 test functions across 263 files: fees 315, auth 219, teaching 178, db 158, money 156, contract 144, accounts 142, marks 112, analytics 102, gates 96, batches 92, governance 79, gateway 50, authz 49, privacy 49, notifications 45, ...); `android/src/test/` (1,822 `@Test` across 211 files); `web/src/**/*.test.ts(x)` (61 files); `site/test/` (2 files)
- **Test Frameworks**: pytest + testcontainers PostgreSQL 16 (restricted role `shikkhok_app`), Hypothesis; JUnit + Turbine + Robolectric (Compose UI on the JVM); Vitest + Testing Library; `node --test`
- **Coverage Config**: present — `pyproject.toml [tool.coverage]` (app/money branch coverage, `fail_under = 100`), `.coveragerc-backend` (backend line floor), `android/coverage.gradle.kts` (JaCoCo) + `android/coverage-floor.txt` (90.05, ratchet task `verifyCoverageRatchet`)

### Code Quality Indicators

- **Linting**: Ruff (rule sets `E,F,W,I,UP,B,ASYNC,S,DTZ,BLE,D,RUF`, banned raw `decimal` outside `app/money`, no relative imports) in `pyproject.toml`; mypy with five strict islands (`app.money`, `app.schemas`, `app.authz`, `app.accounts`, `app.fees`); spotless + ktlint, detekt (`android/detekt.yml`), Android Lint (`android/lint.xml`, `HardwareIds` fatal); ESLint + Prettier (web)
- **CI/CD**: `.github/workflows/check.yml` (backend, image, android-unit, web, site jobs), `deploy.yml` (plan, infrastructure, release, web, site, admin), `release-android.yml`, `security-scan.yml` (ZAP API scan)
- **Documentation**: every Python module, class and function carries a Sphinx-style docstring (Ruff `D`), most with decision references ([BR..], [D-..], [C-..]); `deploy/README.md`, `infra/README.md`, `RESTORE.md`, `CONTRACT.md`, `web/README.md`, `site/README.md`, `android/RELEASE.md`, `docs/`

### Technical Debt Signals

- Stale "dormant account" prose: `app/db/models.py:452-454` ("Created dormant when a teacher records a number") and `app/auth/otp.py` comment "Activate if dormant" describe a behaviour no code path performs any more; only `app/db/seed_staging.py:100` inserts an account without verification
- Stale assertion message: `tests/contract/test_route_lenses.py:115` says "not 12" while asserting `len(PUBLIC_ROUTES) == 14`
- `app/auth/ceilings.py` is 1,244 lines; `app/db/models.py` 3,315; `app/seed/scenario.py` 2,273 — large but each single-purpose
- `app.auth` is not a mypy strict island although it holds the sign-in path (`otp.py`, `passwords.py`, `tokens.py`)
- No Dependabot configuration (`.github/dependabot.yml` absent); no backend SBOM (`deploy.yml:766` `sbom: false`)
- No screenshot harness: the Bangla layout obligation is discharged by a manual per-screen table (`docs/delivery/bangla-layout-check.md`)
- 55 `# noqa` / `type: ignore` suppressions under `app/`, each annotated where sampled; zero TODO/FIXME/HACK markers
- Raw-SQL column interpolation from a closed literal (`Identifier.column`) in `app/auth/otp.py`, `app/accounts/contact.py` (`# noqa: S608`): safe today because the value set is closed, and the exact place a third identifier kind would be added

## Handoff Summary

- **Intent-relevant finding**: identity is a closed two-channel type. `app/accounts/identifier.py` defines `Channel {PHONE, EMAIL}` and `Identifier.column -> Literal["phone","email"]`, interpolated into SQL by `app/auth/otp.py` (`account_for`), `app/accounts/contact.py` (`already_has`, `attach`). Every identifying request inherits `app/schemas/identifier.py:IdentifierFields` ("exactly one of phone and email"), including `PasswordSignInRequest`, `IssueRequest`, `VerifyRequest`, the contact routes and `DeletionRequest`. Password sign-in (`app/accounts/passwords.py:sign_in`) resolves the account through `otp.account_for` and rate-limits on `Identifier.rate_key` (phone raw, email `e:`+sha256). There is no username anywhere in the schema, models, clients or migrations.
- **Intent-relevant finding**: there are no dormant teacher-recorded accounts in the current code. A teacher records numbers on `student.student_phone`/`guardian_phone`, the synchronized `enrollment.student_phone`/`guardian_phone`, and `owner_member.invited_phone`; an `account` row is created only by verify-first signup (`app/accounts/service.py:complete_signup`, inside `otp.verify`). "Claiming" is `link_phone_seats` (`app/accounts/service.py`), run at account creation and when a phone is added through `/v1/me/contact/verify`. Matching is phone-only everywhere: `_LINK_GUARDIAN_SEATS`, `_LINK_STUDENT_SEATS`, `_LOOKUP_QUERY`, `batches.service._account_for`, `students.service._apply_identity`, `centres.memberships.link_memberships`. Adding an email links nothing (`contact.attach` links only `if identifier.is_phone`).
- **Intent-relevant finding**: the privacy gate's owner-private set (`app/contract/privacy.py:75`) is matched by field name and hand-maintained; `tests/privacy/test_profile_probes.py` enrols every `Profile` column automatically, but a column on `account` would not be enrolled. `profile` has `FORCE ROW LEVEL SECURITY` keyed on `app.account_id` (migration 0001), so a username read before authentication (sign-in lookup) cannot live on `profile` without a policy change.
- **Risks / follow-up**:
  - `PUBLIC_ROUTES` is asserted at exactly 14 in three test files (`tests/contract/test_route_lenses.py:78,114`, `tests/governance/test_deletion_paths.py:156`, `tests/contract/test_analytics_contract.py:122`); a public availability-check route moves all three.
  - A new table (a reserved-username hold) must get an entry in `app/governance/dispositions.py` (a test iterates the migrated schema) and flows into the generated privacy policy; holding an erased person's username conflicts with the `account` row's hard delete unless stored as a non-reversible digest.
  - `rate_limit_counter.scope_kind` is `String(16)` and `scope_value` 64 characters: new ceiling kinds must fit, and a username key needs its own prefix so it cannot collide with a phone or `e:` key.
  - Uniqueness today is plain `UNIQUE` on canonical lowercase values (`uq_account_email`); there is no `citext` and no functional index pattern to copy.
  - "Cannot remove the last phone or email" has no current counterpart: no removal path exists (`contact.py` adds only); `ck_account_has_identifier` enforces at least one at the database.
  - Not verified by running in this session: pytest and mypy (the Python dependencies are not installed in this environment). Ruff 0.16.9 (CI pins 0.17.3) reported all checks passed and 548 files formatted.
