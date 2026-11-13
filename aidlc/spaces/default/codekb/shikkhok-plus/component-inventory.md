# Component Inventory — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. One heading per component; the headings are the component names the Scope of Analysis block in `reverse-engineering-timestamp.md` records. Depth marks how closely this run read it: **deep** (read for this intent), **skimmed** (docstrings and inventory).

## Backend (`app/`)

### app.main
Application factory `create_app` (`app/main.py`): registers 27 routers, the staging outbox router only when enabled, request scope, error handlers, and publishes shared components (`Money`, `ErrorEnvelope`) into the OpenAPI document. Depends on every router. Depth: deep (registration).

### app.request_scope
`app/request_scope.py`, `app/config.py`, `app/logging_setup.py`, `app/web_origins.py`, `app/local_time.py`: per-request session and correlation id, mapping of database and validation failures to the envelope, startup configuration checks (JWT key set, OTP HMAC key), CORS allowlist for the web client, Bangladesh clock. Depth: skimmed.

### app.api
`app/api/*.py`: one router per area (accounts, admin, admin_auth, analytics, auth, batches, centres, credentials, deletion, expenses, extra_fees, fees, guardian, health, help, marks, me, mfa, my_classes, my_exams, notifications, payment_methods, payroll, staff, students, teaching, timetable, staging) plus `deps.py` (token and lens dependencies), `fee_line.py`, `html.py`. Handlers are thin: resolve a lens, call a service, map to a schema. Depth: deep for auth, accounts, credentials, me, deps, deletion; skimmed for the rest.

### app.accounts
Identity creation and the owner's own credentials. Strict mypy island.
- `identifier.py` — `Channel {PHONE, EMAIL}`, `Identifier` (value, `column`, `rate_key`, `as_params`), `canonical_email`
- `phone.py` — `canonical_phone` to `+8801XXXXXXXXX` (Latin or Bangla digits)
- `service.py` — `SignupRole`, `complete_signup` (inside verify), `create_account_rows` (account, profile under bound RLS context, owner, centre), `already_added` lookup (phone), `link_phone_seats` (student and guardian links, centre memberships)
- `contact.py` — add a phone or an email once, after a code; links seats only for a phone
- `passwords.py` — `sign_in`, `grant_setup`, `complete_setup`, `change_password`, `has_password`
- `decisions.py` — accept/decline per link, written to every seat of the student
- `mfa.py` — authenticator factor lifecycle; `clients.py` — app platform/version per account
Depends on `app.auth`, `app.authz.rls`, `app.centres`, `app.audit`, `app.db`. Depth: deep.

### app.auth
Authentication primitives (not a strict island).
- `otp.py` — `issue`, `consume_code`, `verify`, `account_for`; purposes `otp`, `deletion`, `contact`; 5-minute codes, 5 attempts
- `pending.py` — signup drafts (24 h), bound to one code
- `ceilings.py` — rate-limit cascades over `rate_limit_counter` (per identifier, /64, /48, global; signup, lookup, deletion, password-failure, verify-failure, dead-code, centre-creation scopes; send budgets)
- `tokens.py` — HS256 access (15 min), refresh rotation (30 d, family 90 d), scoped tokens (password setup 10 min, MFA challenge 5 min, admin 1 h)
- `passwords.py` (scrypt), `hashing.py` (HMAC for codes and refresh tokens), `mfa.py`, `mfa_crypto.py`, `totp.py`, `delivery.py` (send after response, budget at the door), `client_address.py` (/64, /48 buckets)
Depends on `app.accounts.identifier`, `app.gateway`, `app.audit`, `app.db`. Depth: deep for otp, pending, the ceilings API, tokens constants; skimmed for the rest.

### app.authz
Lens types and resolution. Strict island with `disallow_any_explicit`.
- `lenses.py` — `Lens`, `TeacherLens`, `StudentLens`, `GuardianLens`, `InvitationLens`, `MembershipLens`, `ClassTeacherLens`, `ExaminerLens`, `PlatformAdminLens`
- `resolve.py` — one statement, three EXISTS booleans, request-scoped memo; `summary.py` — counts for `GET /v1/me`
- `invitations.py` — the invitation grant set (pending and declined links, one per student)
- `classes.py` — class-teacher and examiner grants; `admin.py` — platform-admin allowlist by phone or email, edge secret, network allowlist
- `rls.py` — transaction-local `app.account_id`; `annotations.py` — return-annotation lens detection for the route gate
Depth: deep for invitations, rls, lens types; skimmed for resolve internals.

### app.contract
CI gates over the generated OpenAPI document and registered routes: `privacy.py` (`OWNER_PRIVATE_FIELDS`, `FORBIDDEN_ACCOUNT_ID_FIELDS`, `STAFF_PRIVATE_FIELDS` with the `/v1/centre/staff` prefix, `OWN_ACCOUNT_FIELDS` exemption for `MeResponse.email`), `routes.py` (`PUBLIC_ROUTES` 14, `LENS_EXEMPT_AUTHENTICATED`, class-teacher and admin route sets), `money_schema.py`, `money_names.py`, `collection_number.py`, `serialize.py`, `emit.py`. Depth: deep for privacy and routes.

### app.schemas
Pydantic wire models, one module per area; strict island. Shared fields: `PhoneField`, `EmailField`, `IdentifierFields`, address fields, `Money`. Depth: deep for identifier, phone, auth, accounts, students; skimmed for the rest.

### app.db
`models.py` describes every table the migrations create (a parity test migrates a fresh database and compares); `money_type.py` (Money to `NUMERIC(12,2)`), `session.py`, `base.py` (naming convention), `roles.py` (`shikkhok_app` role, RLS key), `commands.py` (owner-role operator commands), `schema_compare.py`, `seed_staging.py`. Depth: deep for identity tables; skimmed elsewhere.

### app.errors
Five closed classes (`ValidationError`, `AuthorizationError`, `ConflictError`, `TransientError`, `FatalError`), code registry, one handler, a static exhaustiveness proof. Depth: skimmed.

### app.audit
Append-only `auth_audit_log` with a closed `AuthEvent` set and no free-form field (`app/audit/log.py`). Depth: skimmed.

### app.gateway
SMS protocol and BulkSMSBD adapter, null adapter (default), staging outbox, email protocol, SES SMTP adapter, HTML email, one-segment OTP template. Depth: skimmed.

### app.money
`Money` value type (no float, `ROUND_HALF_UP` declared once, 2 dp), ledger kinds and fold, allocation, settlement, payroll arithmetic, wire conversion. No I/O. 100% branch coverage. Depth: skimmed.

### app.fees
Fee cycles, generation job, claims, decisions, verification, received-by-hand, reminders, payment methods, submissions across children, extra fees and their ledger, status, payables, overdue, views, queue, seat locks. Strict island. Depth: skimmed.

### app.batches
Batches, enrollment seats, roster, periods; `_account_for(phone)` used by students too. Depth: skimmed except `_account_for`.

### app.students
A teacher's one list of students (`student` table) and the synchronized seats; create, enroll, update (relinks a changed number and resets that link to pending), remove/archive. Depth: deep for identity paths.

### app.guardians
A guardian's children grouped from accepted seats; a child's fee history. Depth: skimmed.

### app.centres
Coaching centres (owner kind `centre`), members invited by phone (`owner_member.invited_phone`), membership offers, `link_memberships`. Depth: skimmed except the phone link.

### app.staff
A centre's staff records (`staff` table, with `email` and staff address fields under the staff gate). Depth: skimmed.

### app.payroll
Salary lines, adjustments, approval, payments for centre staff. Depth: skimmed.

### app.expenses
Expenses, voids and the monthly in/out summary per owner. Depth: skimmed.

### app.teaching
Weekly schedules, nightly session generation, sessions, attendance and topics through queued submissions, announcements, calendar, assignment of teachers and rooms at centres, my-classes. Depth: skimmed.

### app.marks
Exams (create, edit, cancel, examiner), mark entry and corrections, result states, the anonymised marksheet, family and examiner views. Depth: skimmed.

### app.analytics
Dues, collections, earnings, today screen, upcoming exam, seat dashboards, owned-seat ledger reads. Depth: skimmed.

### app.notifications
In-app inbox, recipients, detail resolution, FCM push. Depth: skimmed.

### app.help
Help tickets for any account; the administrator's view of requester identity (`identity.py`: teacher names from teacher-facing columns, opaque label for students and guardians). Depth: skimmed (identity read).

### app.admin
Platform overview counts, teachers and centres listing, admin sign-in (SMS or email code then authenticator). Depth: skimmed.

### app.governance
Per-table deletion disposition and retention class (`dispositions.py`, test-enforced against the migrated schema), the one deletion function behind both deletion paths, retention purge, teacher footprint. Depth: deep for identity tables; skimmed elsewhere.

### app.seed
Realistic history seeder for non-production hosts (CLI and Lambda). Depth: skimmed.

### migrations
Alembic revisions 0001 (identity, RLS on `profile`, grants to the restricted role) through 0033 (class-change notifications); identity-relevant: 0001, 0004 (acceptance, address), 0008 (canonical phones), 0016 (structured address), 0018 (teacher students), 0028 (MFA), 0031 (verify-first signup, session end), 0032 (email identity and passwords). Depth: deep for 0032 and the RLS block of 0001; skimmed elsewhere.

## Android (`android/`)

### android.core
`core/model` (Money value class and string-only serializer, `Identifier` with `IdentifierKind {PHONE, EMAIL}`, `PostalAddress`, `Acceptance`), `core/network` (Ktor client, DTOs and `Http*Repository` per area, `TokenStore`, `SessionRenewal`, `ClientPlatform`), `core/session` (lens and workspace choice), `core/designsystem`, `core/format`, `core/ui`, `core/notify`, `core/offline`, `core/queue`, `core/settings`. Depth: deep for `Identifier`; skimmed elsewhere.

### android.feature.auth
Sign-in (password with a Phone | Email kind), code flow, choosing a password, authenticator step, sign-up with the already-added lookup by phone (`AuthViewModel`, `SignupViewModel`, state mappers, `ui/AuthScreen.kt`, `ui/SignupScreen.kt`, `ui/ChoosePasswordStep.kt`, `ui/AuthSecondStep.kt`). Depth: deep (state and repository interface).

### android.feature.account
Password change and add-contact flows (`AccountViewModels.kt`: `PasswordChangeViewModel`, `AddContactViewModel`). Depth: deep.

### android.feature.profile
Profile view and edit (name, address; phone shown read-only), in-app deletion confirming by typed phone, or email for an email-only account. Depth: deep for the deletion confirmation.

### android.feature.invitations
List, accept and decline seats. Depth: skimmed.

### android.feature.other
The remaining 31 feature packages (teacher, family, centre, class-teacher and examiner screens; see `code-structure.md`). Depth: skimmed.

## Web (`web/`, `site/`)

### web.app
React 19 PWA over `/v1`: `api/` (typed client from `openapi.json`), `features/auth` (SignIn, SignUp with the phone-only already-added lookup, PasswordCode, ChoosePassword, MfaStep, `identifier.ts` with `IdentifierKind = 'phone' | 'email'`), `features/account` (Settings, security: AddContact, Password, TwoStep), teacher, student, guardian, family, class-teacher and help features. Depth: deep for `identifier.ts` and the sign-up lookup; skimmed elsewhere.

### web.admin
Separate admin build (`web/src/admin`, `admin.html`, `vite.admin.config.ts`), served from its own hostname behind the admin edge. Depth: skimmed.

### site
Static public site built by `site/build.mjs`; no runtime JavaScript. Depth: skimmed.

## Delivery and operations

### infra
Terraform root and `bootstrap/` (budget, deploy role) plus modules network, registry (ECR), app (EC2 host, user data), cdn (CloudFront), site, admin, database (RDS PostgreSQL 16, encrypted), email (SES), seeder (Lambda). Depth: skimmed.

### deploy
`cve_gate.py` (release-gate CVE blocking against `.security-exceptions.md`), `smoke.py`, `roll.sh` (instance refresh), `docker-compose.staging.yml`, runbook README. Depth: skimmed.

### ci.workflows
`check.yml` (backend, image, android-unit, web, site), `deploy.yml` (plan, infrastructure, release, web, site, admin), `release-android.yml` (signed AAB, release gates, SBOM), `security-scan.yml` (ZAP API scan). Depth: deep for check.yml's control steps; skimmed elsewhere.

### scripts
`generate_privacy_policy.py` (policy text from the governance manifest), `release_notes.py` (from conventional commits). Depth: skimmed.
