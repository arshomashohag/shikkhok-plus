# Code Structure — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. What each component does is in `component-inventory.md`; this file records layout, file classification and the patterns code follows.

## Repository layout

```text
./
  app/                 FastAPI backend (Python 3.12), ~70k lines with migrations and scripts
  migrations/          Alembic env + versions 0001..0033 (schema source of truth)
  tests/               pytest suite, 29 subdirectories mirroring app/ plus contract/, gates/, privacy/
  android/             Gradle module :android (Kotlin, Compose), src/main + src/test + src/debug
  gradle/              version catalogue, wrapper, verification-metadata.xml
  web/                 React PWA (src/) and admin build (src/admin), Vite configs
  site/                static public site: build.mjs, src/pages, src/partials, test/
  infra/               Terraform root, bootstrap/, modules/{network,registry,app,cdn,site,admin,database,email,seeder}
  deploy/              cve_gate.py, smoke.py, roll.sh, docker-compose.staging.yml, README
  scripts/             generate_privacy_policy.py, release_notes.py
  docs/                delivery/, legal/, reviews/2026-11-11/, superpowers/ plans and specs
  store_listing/       Play Store graphics
  claude_design/       AI design-tool HTML mockups (reference only, not built)
  .github/workflows/   check.yml, deploy.yml, release-android.yml, security-scan.yml
  openapi.json         generated contract (make openapi), gated by a schema-diff test
  message-keys.json    server message keys the clients must cover
  Makefile             the one entrypoint, local and CI
```

## Backend layout (`app/`)

| Layer | Location | Classification |
|---|---|---|
| Application object, request scope | `main.py`, `request_scope.py`, `config.py`, `logging_setup.py`, `web_origins.py`, `local_time.py` | Configuration / Middleware |
| HTTP handlers | `api/*.py` (one router per area) | Controller |
| Auth and lens dependencies | `api/deps.py` | Middleware |
| Wire models | `schemas/*.py` | Model (DTO) — strict mypy island |
| Domain services | `accounts/`, `students/`, `batches/`, `fees/`, `teaching/`, `marks/`, `centres/`, `staff/`, `payroll/`, `expenses/`, `analytics/`, `guardians/`, `notifications/`, `help/`, `admin/`, `governance/` | Service |
| Authentication primitives | `auth/` (otp, pending, ceilings, tokens, passwords, hashing, mfa, totp, delivery, client_address) | Service / Utility |
| Authorization | `authz/` (lenses, resolve, summary, invitations, classes, admin, annotations, rls) | Service — strict island |
| Money | `money/` (value type, ledger fold, allocation, settlement, payroll arithmetic, wire) | Model/Utility — strict island, 100% branch coverage |
| Persistence | `db/models.py` (all tables), `db/money_type.py`, `db/session.py`, `db/base.py`, `db/roles.py`, `db/commands.py`, `db/schema_compare.py`, `db/seed_staging.py` | Model / Repository |
| Errors | `errors/` (five classes, codes registry, handler, exhaustiveness proof) | Utility |
| Outbound adapters | `gateway/` (SMS protocol, BulkSMSBD, null, outbox, email, SES SMTP, templates) | Repository/Adapter |
| Audit | `audit/log.py` | Repository |
| CI gates over the app | `contract/` (privacy, routes, money_schema, money_names, collection_number, serialize, emit) | Test support (runs in pytest) |
| Seeder | `seed/` | Utility (non-production) |
| Migrations | `../migrations/versions/` | Migration |

Raw SQL is common and deliberate: many services issue `sa.text(...)` statements with bound parameters (e.g. `app/accounts/service.py` `_LINK_*_SEATS`, `app/authz/invitations.py` `_INVITATION_QUERY`). Column names reach SQL only from closed literals (`Identifier.column`), marked `# noqa: S608`.

## Android layout (`android/src/main/kotlin/com/shikkhokplus/app/`)

- `MainActivity.kt`, `navigation/` — single activity, Compose navigation graph
- `core/` — `model` (Money value class and serializer, Identifier, PostalAddress, Acceptance), `network` (Ktor client, one `Http*Repository` and DTO file per area, `TokenStore` on EncryptedSharedPreferences, `SessionRenewal`), `session` (lens and workspace selection), `designsystem`, `format`, `ui`, `notify` (WorkManager unread check), `offline`, `queue` (queued writes UI), `settings`
- `feature/<area>/` with `ui/` inside — 36 feature packages: `account`, `attendance`, `auth`, `batchdetail`, `batches`, `centres`, `classcalendar`, `collections`, `dashboard`, `dues`, `expenses`, `extrafees`, `fees`, `guardian`, `help`, `inbox`, `invitations`, `marks`, `mfa`, `myclasses`, `myexams`, `pay`, `paymentmethods`, `payroll`, `profile`, `record`, `roster`, `schedule`, `sessions`, `settings`, `staff`, `student`, `students`, `timetable`, `today`, `verify` (`verify` is payment verification, not code verification)
- Per feature: `<Area>Repository` interface, `<Area>UiState` sealed type, `<Area>StateMapper` (response to UiState — the unit-test target), `<Area>ViewModel`, `ui/<Area>Screen.kt`
- Resources: `res/values/strings.xml` and `res/values-bn/strings.xml` (1,539 strings each), night variants, fonts
- One Gradle module for V1 (team.md); quality toolchain in `android/build.gradle.kts`, `coverage.gradle.kts`, `release-gates.gradle.kts`, `detekt.yml`, `lint.xml`

## Web layout (`web/src/`)

- `api/` — `client.ts`, `endpoints.ts`, `tokens.ts`, `workspace.ts`, generated `schema.d.ts`
- `features/` — `auth` (SignIn, SignUp, PasswordCode, ChoosePassword, MfaStep, `identifier.ts`), `account` (Settings, Invitations, LensPicker, Workspaces, `security/` AddContact, Password, TwoStep), `teacher`, `student`, `guardian`, `family`, `classTeacher`, `help`, `common`
- `session/`, `shell/`, `ui/`, `core/` (format, money), `i18n/`, `pwa/`, `styles/`, `deploy/`, `test/`
- `admin/` — the separate admin app (own entry `admin.html`, `vite.admin.config.ts`)

## Patterns the code follows

- **Docstring as decision record**: every module opens with the why, citing decision ids ([BR..], [D-..], [C-..], [0032]). Changing behaviour means changing the docstring that justifies it.
- **Lens as data dependency**: handlers take a typed lens (`Annotated[TeacherLens, Depends(teacher_lens)]`) and scope queries by its ids; no handler reads a role.
- **Identifier as a tagged value**: `Identifier(channel, value)`; schema fields canonicalise on the way in (`PhoneField`, `EmailField`) so services see one spelling.
- **Same work on both branches**: unknown identifiers take the same writes and hashing as known ones (`otp.issue`, `passwords.verify_nothing`).
- **Ceilings before side effects**: rate-limit rows (`rate_limit_counter`) are consumed before any send or check (`app/auth/ceilings.py`).
- **Transaction-local RLS context**: `set_config(key, value, true)`, set at the exact write that needs it.
- **Closed error taxonomy**: five classes; retryability is a property of the class; `message_key`, never an English message.
- **Generated contract, committed**: `make openapi` regenerates `openapi.json`; the web client generates types from it.
- **Client mapping functions under test**: Android `*StateMapper` and web `mappers.ts` turn responses into UI state; composables and components hold no domain conditionals.
