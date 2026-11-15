# Code Quality Assessment — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. Every status below was checked against a file in the repository this run. "Run this session" marks what was executed rather than read.

## What was run this session, and what was not

- **Run**: `ruff check app tests` — all checks passed; `ruff format --check app tests` — 548 files already formatted. The local Ruff is 0.16.9; CI pins 0.17.3 (`pyproject.toml`), so this is indicative, not the CI result.
- **Not run**: pytest and mypy. The Python dependencies (`fastapi`, `pytest`, `mypy` as modules) are not installed in this environment, and installing them was outside this stage's brief. Coverage figures below are the configured floors, not measurements from this run.
- **Counted**: about 2,190 backend test functions across 263 files; 1,822 Android `@Test` across 211 files; 61 web test files; 2 site test files.

## Quality ratings (3-point scale)

| Dimension | Rating | Evidence |
|---|---|---|
| Naming clarity | good | Module and function names state intent; docstrings carry the decision behind each rule |
| Function size | fair | Most functions are small; several modules are large single-purpose files (`app/auth/ceilings.py` 1,244 lines, `app/db/models.py` 3,315, `app/seed/scenario.py` 2,273, `app/fees/verification.py` 929, `app/api/teaching.py` 893) |
| Error handling | good | Closed five-class taxonomy, one handler, `message_key` not English, retryability on the class (`app/errors/`); integration boundaries handled per team.md |
| Test presence | good | Every package has a test directory; privacy, route, money and contract gates run in pytest; Android mapping functions and ViewModels tested |
| Duplication | fair | Parallel raw-SQL statements per link (`_LINK_GUARDIAN_SEATS`, `_LINK_STUDENT_SEATS`, `_LOOKUP_QUERY` halves) and two `_account_for`-style lookups (`batches.service._account_for`, `otp.account_for`) — each small, but each would need an email twin under the intent |
| Dead code | good | Zero TODO/FIXME/HACK; `account.deleted_at` is a documented unused column; `Profile.address` documented as written by nothing since 0016 |

## Mechanical controls: current state

| Control | State on 2026-11-13 | Evidence |
|---|---|---|
| Backend lint and format | In force | Ruff rule sets `E,F,W,I,UP,B,ASYNC,S,DTZ,BLE,D,RUF`; banned raw `decimal` outside `app/money`; `ban-relative-imports` |
| mypy | In force | `disallow_untyped_defs` globally; strict islands `app.money`, `app.schemas`, `app.authz`, `app.accounts`, `app.fees`. **`app.auth` is not strict** |
| Money boundary | In force | Ruff banned-api + AST import test; `fail_under = 100` branch on `app/money` (`Makefile` test target, `pyproject.toml`) |
| Backend coverage floor | In force (configured) | 80% line over an **explicit** `--cov` package list in `Makefile`; a new package must be added to that list or it is unmeasured |
| Route-lens gate | In force | `app/contract/routes.py`; `PUBLIC_ROUTES` asserted `== 14` |
| Privacy gate | In force | `app/contract/privacy.py`; owner-private set matched by name, hand-maintained; every `Profile` column asserted to be in it (`tests/privacy/test_profile_probes.py:206,238`) |
| RLS meta-test | In force | `tests/privacy/test_rls_meta.py`; restricted role `shikkhok_app` |
| Schema parity (models vs migrations) | In force | `tests/db/test_schema_parity.py` (ARC-1) |
| Governance manifest completeness | In force | `tests/db/test_governance.py`, `tests/governance/test_deletion.py` check `DISPOSITIONS` against the schema |
| OpenAPI schema diff | In force | `tests/contract/test_schema_diff.py`, `CONTRACT.md` |
| Message-key coverage | In force | `tests/contract/test_message_keys.py`, `message-keys.json`; raised keys must be literal strings at the raise site (`app/accounts/phone.py` comment) |
| Gitleaks with shallow-clone guard | In force | `check.yml:92-127` |
| Integration suite ran (Docker precondition + no skips) | In force | `check.yml:209` "Docker is available", `check.yml:251` "Every test ran" over the JUnit report |
| Android release gates (manifest allowlist, DEX scan) | In force | `android/release-gates.gradle.kts` |
| ZAP API scan before promotion | Built | `.github/workflows/security-scan.yml` |

## Controls team.md assigned "before D1" — state found now

team.md recorded these as absent on 2026-10-22. Each has been re-checked against the repository at `cb20fd1`.

| Control | team.md 2026-10-22 | Found 2026-11-13 | Evidence |
|---|---|---|---|
| Python lockfile, CI installs from it | absent; `check.yml:88` mislabelled | **Landed.** Hash-pinned `requirements.txt`; CI installs with `--require-hashes` and checks currency; the step label now matches what it does | `requirements.txt` (2,039 hashes), `check.yml:128-176`, `Dockerfile:49-61` |
| Gradle lockfiles and checksum verification | absent | **Landed** | `android/gradle.lockfile`, `settings-gradle.lockfile`, `gradle/verification-metadata.xml` (663 components) |
| CVE scanning, per-push half | absent | **Landed**: pip-audit, osv-scanner (Android), npm audit (web), annotating only | `check.yml:178,427,491` |
| CVE scanning, release-gate half and `.security-exceptions.md` | assigned D6 | **Landed**: `deploy/cve_gate.py` over pip-audit, osv-scanner and ECR image-scan findings; exceptions file present, no rows. ECR image scanning stands in for the named Trivy | `deploy.yml:239-248,771-789`, `release-android.yml:163-181`, `.security-exceptions.md` |
| Dependabot (weekly, grouped) | absent | **Still absent** | no `.github/dependabot.yml` |
| Backend SBOM | assigned D6 | **Still absent** | `deploy.yml:766` `sbom: false`; Android SBOM exists (`release-android.yml:441`) |
| ktlint via spotless | absent | **Landed** | `android/build.gradle.kts` plugins, `check.yml:397` `spotlessCheck` |
| detekt (Double/Float ban, forbidden imports) | absent | **Landed**; detekt forbids `android.telephony.TelephonyManager` imports (commit-time half of the forbidden-identifier rule); Double/Float is still carried by `NoFloatingPointTest.kt` because detekt cannot express it without type resolution | `android/detekt.yml:66-97`, `check.yml:401` |
| `lint.xml` with `HardwareIds` fatal | absent | **Landed**, plus permission and security issues raised | `android/lint.xml`, `check.yml:410` `lintDebug` |
| Kotlin coverage ratchet | absent (Kover named) | **Landed with JaCoCo**, not Kover; floor 90.05 in `android/coverage-floor.txt`, `verifyCoverageRatchet` in CI | `android/coverage.gradle.kts:23`, `check.yml:417` |
| Bangla layout verifier | absent | **Manual per-screen check chosen 2026-10-22**, recorded as a table artifact. Nothing automated discharges this obligation; no screenshot harness exists (ARC-4 deferred in the 2026-11-11 sprint plan) | `docs/delivery/bangla-layout-check.md`, `docs/reviews/2026-11-11/sprint-plan.md` |
| `app.authz` mypy strict island | not configured | **Landed** (with `disallow_any_explicit`); `app.accounts` and `app.fees` added as further islands | `pyproject.toml:247,276,309` |
| `PUBLIC_ROUTES` comment states a count nothing checks | "five" over six entries | **Fixed**: comment reads "Exactly fourteen", the set holds 14, and three tests assert it. One stale message remains: `tests/contract/test_route_lenses.py:115` says "not 12" | `app/contract/routes.py:36`, `tests/contract/test_route_lenses.py:78,114-115`, `tests/governance/test_deletion_paths.py:156`, `tests/contract/test_analytics_contract.py:122` |
| "Require branches up to date" on `main` | unverifiable from the repo | Still unverifiable from the repository | GitHub repository setting |

## Technical debt and drift

1. **Stale "dormant account" prose.** `app/db/models.py:452-454` says an account is "Created dormant when a teacher records a number, activated on first successful sign-in"; `app/auth/otp.py` (in `verify`) comments "Activate if dormant. This is what lets a student or guardian claim a record a teacher created". Since verify-first sign-up (0031) and the teacher-student list (0018), no code path creates an account for a teacher-recorded person; only `app/db/seed_staging.py:100` inserts an unverified account. `activated_at` is therefore set in the same transaction that creates every real account. Under project.md ("where a comment states a ... scope, the number is a claim"), this is prose that nothing checks and that a reader would trust.
2. **Stale assertion message** at `tests/contract/test_route_lenses.py:115` ("not 12" under `== 14`).
3. **`app.auth` outside the strict islands** while it holds code issue, verify, password hashing and tokens.
4. **Large modules**: `app/auth/ceilings.py` (1,244 lines) holds every ceiling cascade; adding username ceilings grows it further. `rate_limit_counter.scope_kind` is `String(16)` and `scope_value` 64 characters (`app/db/models.py:715-716`), which bounds new scope names and keys.
5. **Column names interpolated from a closed literal** (`Identifier.column` in `app/auth/otp.py:account_for`, `app/accounts/contact.py`), suppressed with `# noqa: S608`. Safe while the set is closed; it is exactly where a third kind would widen it.
6. **Dependabot and backend SBOM absent** (above).
7. **55 suppressions** (`# noqa`, `type: ignore`) under `app/`; those sampled carry a reason.

## Findings bearing directly on the username change request

Recorded here once; `architecture.md` and the developer scan cite them.

| # | Finding | Evidence | Why it matters for the CR |
|---|---|---|---|
| U1 | **Sign-in key is phone-or-email, as a closed type.** `PasswordSignInRequest` inherits `IdentifierFields` ("exactly one of phone and email"); `sign_in` resolves through `otp.account_for(Identifier)`; failures are counted on `Identifier.rate_key` | `app/schemas/identifier.py`, `app/schemas/auth.py`, `app/accounts/passwords.py:sign_in`, `app/auth/otp.py:account_for` | "One sign-in field accepts username, phone or email" needs a new request shape and server-side classification; the per-identifier ceiling needs a username key that cannot collide with a phone value or an `e:` email key |
| U2 | **`IdentifierFields` is shared by nine request types** (`IssueRequest`, `VerifyRequest`, `PasswordSignInRequest`, `SignupRequest`, `DeletionRequest`, `AdminOtpRequest`, `AdminVerifyRequest`, `ContactRequest`, `ContactVerifyRequest`) | `app/schemas/auth.py`, `accounts.py`, `deletion.py`, `admin.py`, `app/api/credentials.py` | Changing it changes every one of them; a separate sign-in schema is narrower (*inferred*) |
| U3 | **No dormant teacher-recorded accounts exist.** Teacher-recorded people are numbers on `student`, `enrollment` and `owner_member`; accounts are created only at verify | `app/accounts/service.py`, `app/students/service.py:seat_for`, finding 1 above | The CR's "dormant accounts carry no username until claimed; sign-up on a recorded identifier claims that account" maps onto the existing verify-first sign-up plus `link_phone_seats`, not onto existing rows without a username |
| U4 | **Recording and matching are phone-only.** `student`/`enrollment` have `student_phone`/`guardian_phone` and no email columns; `owner_member.invited_phone` only; `_LINK_GUARDIAN_SEATS`, `_LINK_STUDENT_SEATS`, `_LOOKUP_QUERY`, `batches.service._account_for`, `students.service._apply_identity`, `centres.memberships.link_memberships` all match on phone; `GET /v1/accounts/already-added` takes `phone` only; the web sign-up looks up only for the phone kind | `app/db/models.py:1046-1047,1167-1168,978`, `app/accounts/service.py`, `app/centres/memberships.py:129`, `web/src/features/auth/SignUp.tsx:176-198` | Email invitations and "re-matching when a person adds a contact later" need email columns, email twins of every link statement (or one generalized matcher), an email form of the lookup, and teacher request/response fields |
| U5 | **Adding an email links nothing.** `contact.attach` calls `link_phone_seats` only `if identifier.is_phone` | `app/accounts/contact.py` | The re-match on a later-added email is new behaviour, and must keep "links, never decisions" [BR5.1] |
| U6 | **Username storage vs row-level security.** `profile` has `ENABLE` and `FORCE ROW LEVEL SECURITY` with policy `profile_owner_only` on `app.account_id` | `migrations/versions/0001_initial_identity_schema.py:261-266`, `app/authz/rls.py` | A pre-authentication lookup by username (sign-in, availability) cannot read `profile`; a username on `account` is outside RLS and protected only by the response-schema gate |
| U7 | **The privacy gate will not enrol a username automatically.** `OWNER_PRIVATE_FIELDS` is hand-maintained by field name; the auto-enrolment test covers `Profile` columns only. The admin contract keeps its own forbidden list (`phone`, `email`) | `app/contract/privacy.py:75-85`, `tests/privacy/test_profile_probes.py:206,238`, `tests/contract/test_admin_contract.py:39-40` | `username` must be added by hand to `OWNER_PRIVATE_FIELDS` and to the admin contract's list; a column on `account` gets no automatic membership test unless one is written |
| U8 | **Name collisions in the gate.** `email` is in `STAFF_PRIVATE_FIELDS` (allowed only under `/v1/centre/staff`, with a pairwise exemption for `MeResponse.email`) | `app/contract/privacy.py:104-125` | Teacher-recorded student or guardian emails must be named distinctly (e.g. `student_email`), or the staff gate fails |
| U9 | **Case-insensitive uniqueness has no precedent beyond lowercase canonicalisation.** `account.email` is stored lowercased with a plain `UNIQUE`; no `citext`, no functional index | `app/accounts/identifier.py:canonical_email`, migration 0032 `uq_account_email` | A username shown as typed but unique case-insensitively needs either a canonical column or a `lower()` unique index — a schema decision, with a parity-test entry in `app/db/models.py` |
| U10 | **Sign-up draft carries no username.** `pending_signup` has unique `phone`/`email` and the form fields; a draft is created for every request, including for identifiers that already have an account | `app/db/models.py:779-830`, `app/auth/pending.py` | A username chosen at sign-up must ride in the draft; two concurrent drafts on one username, and a username taken between draft and verify, need a defined outcome at `complete_signup` (today: `DuplicateNumber` for a clashing phone/email) |
| U11 | **No removal path for phone or email.** Contacts are add-once, never replaced or removed; the database CHECK `ck_account_has_identifier` requires at least one | `app/accounts/contact.py` docstring, `app/db/models.py:503-507` | "Cannot remove its last one" is a new capability with an existing database backstop; removing a phone also raises what happens to seats linked through it (U4) |
| U12 | **Public-route allowlist is counted.** An availability-check route would be public; three tests assert `len(PUBLIC_ROUTES) == 14` | `app/contract/routes.py`, tests listed above | Adding the route moves the count and its justification comment in the same change |
| U13 | **Availability is an existence oracle by nature**, unlike OTP issue, sign-up and password sign-in, which answer identically [BR2.7] | `app/api/auth.py`, `app/api/accounts.py` | Needs its own ceilings (per IP, per /48, global), as the already-added lookup has (`LOOKUP_*` scopes) |
| U14 | **Reserved names need a governance entry.** Any new table must appear in `DISPOSITIONS` and the generated privacy policy; the `account` row is hard-deleted | `app/governance/dispositions.py`, `scripts/generate_privacy_policy.py` | Holding an erased person's old username for a cooling-off period retains an identifier after deletion; a digest instead of the name, and a retention class, are the decisions to make |
| U15 | **Existing accounts have no "username required" signal.** `MeResponse` and `VerifyResponse` carry no such field; both clients branch on `has_password` today | `app/api/me.py`, `app/schemas/auth.py`, Android `feature/auth`, web `features/auth` | "Pick a username at next sign-in while identifier sign-in keeps working" needs a server-computed flag (decisions stay server-side [TC-9]) |
| U16 | **Deletion confirms by phone or email.** In-app deletion asks the person to type their phone (or email for an email-only account); the external route takes phone or email | `android/.../feature/profile/ui/DeleteAccountScreen.kt:96-103`, `app/schemas/deletion.py` | Whether a username may confirm or request deletion is a decision; today neither path knows usernames |
| U17 | **The explicit coverage package list** in `make test` | `Makefile` test target | A new backend package for usernames must be added to the `--cov` list or its code is outside the 80% floor |
