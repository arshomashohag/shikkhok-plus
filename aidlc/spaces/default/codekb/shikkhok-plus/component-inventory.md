# Component Inventory

Every backend package under `app/` and every Android package under
`android/src/main/kotlin/com/shikkhokplus/app/`, with what each owns. The
final section lists the feature areas that have **no code at all**, which for
this intent is as informative as the contents.

Component names below are the headings the rerun guard compares literally.

---

## Backend components

### app.main

**Owns the application object.** `create_app()` runs the startup
configuration check *before* wiring anything, builds the FastAPI app,
registers the single error handler, installs the request-scope middleware,
includes the routers, and publishes the shared `Money` and `ErrorEnvelope`
components into the generated document.

Two things here are load-bearing elsewhere:

- The middleware opens **one session and one correlation id per request**,
  commits on success, rolls back on any exception. No repository commits.
- Each included router is appended to `app.state.included_routers`, which is
  what both contract gates enumerate. A hardcoded list here was itself a
  defect: a conditionally registered router would be invisible to the gates
  while they reported clean.

Depends on: `app.config`, `app.db.session`, `app.errors`, and (lazily) every
router. 64 statements, 92% line coverage.

### app.config

**Owns the startup refusal.** `check_startup_configuration()` raises
`ConfigurationError` when a `production` process is missing a value whose
default would silently remove a guarantee: the staging OTP outbox being
enabled, an unset global daily SMS ceiling (the test default would become
the money ceiling), an SMS app hash that is not exactly 11 characters, an
unset OTP HMAC key, or an adapter selection that is not the real gateway.

Deliberately **not** a `TaxonomyError`: that hierarchy describes what a
*request* did. 100% coverage.

### app.api

**Owns the HTTP surface.** Five modules:

| Module | Routes | Lens |
|---|---|---|
| `auth.py` | `POST /v1/auth/otp`, `POST /v1/auth/verify`, `POST /v1/auth/refresh` | public, public, lens-exempt authenticated |
| `batches.py` | 6 routes — see `api-documentation.md` | `TeacherLens` on five, `GuardianLens` on one |
| `me.py` | `GET /v1/me` | none, explicitly allowlisted |
| `health.py` | `GET /health` | public |
| `staging.py` | `GET /staging/last-otp` | public, **not registered unless the environment permits it** |

`deps.py` is the authorization surface: `get_session`,
`authenticated_account` (verifies the bearer JWT, memoizes on
`request.state`), and the three lens dependencies `teacher_lens`,
`student_lens`, `guardian_lens`, each returning a lens that *carries the
scoping value*.

`batches.py` also holds `_to_wire` / `_from_wire`, the only place in the API
layer that converts between the domain `Money` and the wire `Money`.

### app.authz

**Owns the computed lens.** Five modules:

- `lenses.py` — the frozen dataclass hierarchy. `Lens(account_id)`,
  `TeacherLens(owner_id)`, `StudentLens`, `GuardianLens(child_enrollment_id
  | None)`. The optional child id is not degenerate: a guardian's first
  request has not selected a child, and the child arrives as a **path
  parameter** on later requests, never from a client hint.
- `resolve.py` — `available_lenses()` and `LensResolver`. **One SQL
  statement** returns the owner id, a student `EXISTS` and the guardian
  enrolment id. Memoized on `request.state` and nowhere else. No
  module-level dict, no `lru_cache`; their absence is asserted by a test.
- `summary.py` — `lens_summary()`, one statement returning all three
  **counts** for the lens picker. Documented as measured at 0.20 ms on
  50,000 accounts and 200,000 enrolments.
- `annotations.py` — `resolve_lens_type()`, the one function both contract
  gates use to decide whether a callable returns a lens. Handles string
  annotations (`from __future__ import annotations` makes every annotation a
  string), unions (counting only when *every* member qualifies) and
  `Annotated` wrappers. A resolution failure **raises** and is never
  swallowed.
- `rls.py` — `set_account_context` / `clear_account_context`, the only
  setters of the `app.account_id` session variable, using
  `set_config(..., true)` so the value is transaction-local and cannot leak
  across a pooled connection.

100% coverage on four of the five modules; `summary.py` is at 96%.

### app.auth

**Owns one-time-code authentication and the token lifecycle.**

- `ceilings.py` — four datastore-backed counters checked **narrowest
  first**, with the increment in the same statement as the check so a refused
  request never consumes a wider allowance. `PER_NUMBER_HOURLY = 3`,
  `PER_NUMBER_DAILY = 5`, `PER_IP_HOURLY = 10`, `GLOBAL_DAILY` from the
  environment (test default 500). A breach raises `CeilingBreach`, a
  `ConflictError` — never a `TransientError`, because retrying into a cost
  ceiling is exactly wrong.
- `otp.py` — `issue()` and `verify()`. `CODE_LIFETIME = 5 minutes`,
  `ATTEMPT_CEILING = 5`. Only the HMAC hash is stored; the issue response is
  byte-identical for a known and an unknown number.
- `hashing.py` — the HMAC construction and its key environment variable.
- `tokens.py` — `issue_pair()`, `verify_access_token()`, `rotate()`.
  `ACCESS_TOKEN_LIFETIME = 15 minutes`, `REFRESH_TOKEN_LIFETIME = 30 days`,
  HS256 with **`kid` support and a key map**, so the signing key can rotate
  without force-logging-out every holder of a 30-day refresh token. Refresh
  tokens are stored hashed; rotation detects reuse and invalidates the family.

### app.money

**Owns every money value and every money operation.** Imports `decimal` and
its own siblings, and nothing else — no ORM, no session, no settings, no
HTTP. This is what makes 100% branch coverage reachable here and nowhere
else.

- `_money.py` — the `Money` frozen value object. Construction from `float`
  or `bool` raises; the wrapped `Decimal` is quantized to two places at
  construction; negative zero is normalised. No `__float__`, no `__int__`.
- `_rounding.py` — `ROUNDING = ROUND_HALF_UP`, `EXPONENT`,
  `MAGNITUDE_LIMIT`, declared once.
- `_kinds.py` — `LedgerEntryKind`, the seven ledger kinds.
- `_ledger.py` — the ledger fold. The `match` over `LedgerEntryKind` is
  total and mypy proves it, which is why the one `assert_never` is the sole
  sanctioned coverage exclusion.
- `_errors.py` — `MoneyValidationError`.
- `wire.py` — `WIRE_PATTERN` (`^[0-9]+\.[0-9]{2}$`, **no sign**), `to_wire`,
  `parse`. `parse` rejects a JSON number **loudly** rather than coercing,
  because a lenient decoder passes a happy-path test on both sides while the
  value is already wrong.

**100% branch coverage, enforced with `fail_under = 100` and no inline
pragmas.**

### app.schemas

**Owns the Pydantic request and response models.** `auth.py`, `batches.py`,
`errors.py`, `money.py`. A mypy strict island (`strict = true`, with
`disallow_any_explicit` deliberately off and the reasoning recorded at
length in `pyproject.toml`: Pydantic's `BaseModel` is generic over `Any`, so
the flag would produce one unavoidable error per model).

`money.py` holds the single shared `Money` component — a `RootModel[str]`,
not an `Annotated` alias, because an alias inlines and leaves no component
for the `$ref` gate to check. The pattern is **imported from**
`app.money.wire`, never restated.

### app.db

**Owns persistence.**

- `models.py` — 13 mapped classes across 579 lines: `Account`, `Profile`,
  `OtpRequest`, `VerifyAttempt`, `RefreshToken`, `RateLimitCounter`,
  `AuthAuditLog`, `Owner`, `Enrollment`, `Batch`, `BatchSubject`,
  `ScheduleSlot`, `HiddenBatchPreference`. Imports no `Decimal` — money
  columns are annotated `Mapped[Money]` via `MoneyColumn`.
- `money_type.py` — the `MoneyType` `TypeDecorator`. `MONEY_PRECISION = 12`,
  `MONEY_SCALE = 2`, declared once so no model restates them.
  `process_bind_param` raises `TypeError` on a bare `Decimal` or `int`.
- `roles.py` — `APP_ROLE = "shikkhok_app"` and
  `SESSION_ACCOUNT_KEY = "app.account_id"`, shared by the migration, the
  request path and the meta-test.
- `session.py` — `build_engine()`. **32% coverage**; the real connection path
  is not exercised by the suite, which drives the app through `TestClient`
  against a container engine.
- `base.py` — the declarative base.
- `seed_staging.py` — a manual `python -m` entry point. **0% coverage**, and
  the only backend module with none.

### app.contract

**Owns the four CI gates over the generated document.** Described in full in
`architecture.md`. `routes.py` (route enumeration + the two allowlists),
`privacy.py` (schema-wide forbidden-field walk), `money_schema.py` (`$ref`
predicate + two name-matched backstops + `*_display` pairing),
`money_names.py` (the shared money-name vocabulary and its two keyed
exemption maps), `serialize.py` (canonical serialization), `emit.py` (the
`python -m` entry point, excluded from the coverage floor because its body
*is* the subprocess the determinism test invokes).

### app.errors

**Owns the five-class taxonomy and the one handler.** `_classes.py`
(`TaxonomyError` and the five subclasses), `codes.py` (the registry, with
`NOT_AVAILABLE` deliberately covering both "unreachable" and "absent", and
`auth_status_for()` pairing codes to statuses), `handler.py` (the single
FastAPI handler), `_exhaustive.py` (the `assert_never` machinery proving the
handler's match is total).

### app.gateway

**Owns the SMS boundary** — the only boundary where a failure costs money and
a retry may double-charge.

- `sms.py` — the `SmsGateway` protocol.
- `bulksmsbd.py` — the real adapter. Asserts `https` in its constructor. One
  send attempt, **no automatic retry**; a timeout is recorded as `unknown`
  rather than `failed`, because the SMS may have been delivered.
- `null.py` — the default adapter, so a misconfigured process fails *toward
  not sending*. `ADAPTER_ENV` and `REAL_ADAPTER_SENTINEL` live here and are
  read by the startup check.
- `outbox.py` — the staging outbox. Three independent mechanisms gate it.
- `template.py` — the message body, including the SMS Retriever app hash.

### app.audit

**Owns the append-only authentication audit log.** `log.py` writes
`otp_issued`, `verify_failed`, `verify_succeeded`, `refresh_rotated`,
`refresh_reuse_detected`, each carrying the correlation id and **never** a
phone number, an OTP or a token.

### app.governance

**Owns the per-table deletion and retention manifest.**
`dispositions.py` holds `DISPOSITIONS` (one `TableGovernance` per table:
`Disposition` ∈ {`HARD_DELETE`, `ANONYMIZE_IN_PLACE`, `RETAIN_WITH_BASIS`},
a `RetentionClass`, and a one-sentence `basis` the privacy policy is
generated from) and `RETENTION`. A test iterates the **migrated schema** and
fails on any live table without an entry.

The dispositions are **declared and not yet enforced**: the module's own
docstring says the deletion paths belong to the unbuilt unit. Declaring them
against the full schema once, rather than rediscovering them per table, is
deliberate.

### app.batches

**Owns batch and enrolment operations.**

- `service.py` — `create_batch`, `list_batches`, `list_roster`,
  `add_enrollment`, `remove_enrollment`, `set_inactive_from`,
  `list_guardian_children`, plus `_owned_batch` and `_owned_enrollment`. **No
  function here takes an `owner_id` parameter**: it comes from the lens or it
  does not exist, so there is nothing to forge. Raises `BatchNotFound` (an
  `AuthorizationError` carrying 404, deliberately indistinguishable from
  absence) and `EnrollmentNotRemovable` (a `ConflictError`). **81% coverage**
  — the lowest of the feature modules.
- `periods.py` — calendar-month period arithmetic with the short-month
  clamp. Present but **not yet consumed by any fee-cycle code**, because
  none exists.

---

## Android components

One Gradle module, `:android`, with `core/*` and `feature/*` packages inside
it.

### core.model

`Money.kt` — a `@JvmInline value class Money(val amount: BigDecimal)` with
`SCALE = 2`, the same `WIRE_PATTERN` as the server, `ZERO`, and
`Money.of(raw)` which `require`s the canonical form. The serializer is
attached **to the type**, not to each field, so a money field cannot be
declared without it.

`MoneySerializer.kt` — reads a JSON **string** and nothing else. Inspects
`JsonPrimitive.isString` rather than calling `.content`, which would succeed
on a number, and throws `SerializationException` on a number.

### core.network

`ApiClient.kt` — builds the one Ktor client. Base URL is **required, not
defaulted**, and `https` is asserted at construction (with a loopback
exemption for local development). The `Json` configuration is three
decisions: `ignoreUnknownKeys = true` so an installed app survives an
additive server deploy, `explicitNulls = false` so an absent optional is
omitted rather than sent as null, and `isLenient = false` so an unquoted
number where a money string belongs fails loudly.

`AuthDto.kt`, `RosterDto.kt` — the wire DTOs. `HttpAuthRepository.kt`,
`HttpRosterRepository.kt` — the two repositories. `TokenStore.kt` —
`EncryptedSharedPreferences` for the 30-day refresh token, chosen over plain
`SharedPreferences` which leaves a long-lived credential readable via adb on
a rooted phone.

### core.designsystem

`Color.kt`, `Theme.kt`, `Type.kt`, `Spacing.kt`, `Surfaces.kt`,
`OtpField.kt`, `PaymentStateChip.kt`, `PaymentStateIcon.kt`. The payment-state
components exist ahead of any payment feature — they render a server-provided
status enum rather than comparing a balance.

### core.format

`Numerals.kt` — digit rendering for the Bangla locale.

### core.ui

`CreateForms.kt` — shared create-form composables. The delivery plan
describes these as bare text fields that the batch-creation screen will
replace.

### feature.auth

`AuthViewModel.kt`, `AuthUiState.kt`, `AuthStateMapper.kt` (the mapping
function the tests target, rather than an untargeted "the ViewModel"),
`MessageKeys.kt`, `LensHint.kt`, `ui/AuthScreen.kt`.

`LensHint` is worth naming: the hint travels **out** in an `X-Lens-Hint`
header to say which lens the person picked, and nothing travels **in** on
the strength of it. The server response is self-describing and names the
lens that produced it.

### feature.batches

`BatchesViewModel.kt`, `BatchesUiState.kt`, `BatchesStateMapper`,
`ui/BatchesScreen.kt`.

### feature.roster

`RosterViewModel.kt`, `RosterUiState.kt`, `RosterStateMapper.kt`,
`ui/RosterScreen.kt`.

### MainActivity

The single Activity. Screen one is OTP entry; it switches between
`AuthScreen`, `BatchesScreen` and `RosterScreen`. There is **no navigation
library** — the screen is selected by a `when` over state in the Activity.

---

## Infrastructure components

### infra (Terraform root)

`main.tf` composes five modules, with a `terraform_data` **budget guard**
that computes the monthly cost and refuses to apply above the ceiling. The
header records what is deliberately absent and prices each omission.

### infra.modules

- `network` — VPC, subnets, security groups. No NAT gateway.
- `registry` — ECR with separate lifecycle rules for tagged and untagged
  layers.
- `app` — the application host, instantiated **twice** (production and
  staging). Includes `user_data.sh.tftpl` and `deployment_state.tf`.
- `cdn` — CloudFront plus the ACM certificate in `us-east-1`.
- `database` — Phase 1 is a container on the app host; the Phase 2 RDS path
  is written and disabled.

### infra.bootstrap

The one thing run from a laptop: the S3 state bucket and the CI deploy role.
State and credentials cannot bootstrap themselves.

---

## Feature areas with NO code

This is the part of the inventory the six remaining deliverable units are
designed against. Each of the following has **no module, no table, no route
and no screen** anywhere in the repository.

| Area | Evidence of absence | Which unit needs it |
|---|---|---|
| **Account creation** | No `POST /v1/accounts` in `openapi.json`; no signup module under `app/`; no `address` or display-name column on `account` in `models.py` | D1 |
| **Seat acceptance** | No `student_accepted_at`, `guardian_accepted_at` or decline marker on `Enrollment`; the lens resolver reads nothing but the two account-id links | D1 |
| **Signup abuse ceilings** | `app/auth/ceilings.py` scopes cover the OTP path only | D1 |
| **Fee cycles** | No `fee_cycle` table, no generation job, no `(enrollment_id, period)` constraint. `app/batches/periods.py` has the arithmetic but nothing calls it | D3 |
| **Ledger** | No `ledger_entry` table. `app/money/_kinds.py` and `_ledger.py` define and fold the seven kinds **in memory only** | D3 |
| **Payment claims and verification** | No `payment_claim` table, no submit/approve/reject routes, no channel list | D3 |
| **`Money.format(locale)`** | Not present in `app/money/`; the module's docstring records it as deferred | D3 |
| **Push notification / FCM** | No `DeviceToken` table, no adapter, no dependency in `libs.versions.toml` | D3 owns it; D4 reuses it |
| **Sessions and attendance** | No `session`, `attendance` or `attendance_version` table; no offline queue; no `client_mutation_id` anywhere | D4 |
| **Exams and marks** | No `exam`, `mark` or marksheet table; no `superseded_by_id`; `batch.marksheet_visible` exists as a column with nothing reading it | D4 |
| **Insights** | No cross-batch dues query, no earnings, no collection rate | D5 |
| **Macrobenchmark harness** | No `benchmark/` module, no `androidx.benchmark` dependency, no low-end device profile. This is the **outstanding half of release packaging** and the only verifier the mid-class latency obligation can have | D5 |
| **Account deletion** | **`PUBLIC_ROUTES` allowlists `GET` and `POST /account-deletion` and no handler exists.** Both paths are release-blocking | D6 |
| **Scheduled purge** | `RetentionClass` values are declared; nothing enforces them | D6 |
| **Generated privacy-policy text** | `docs/legal/PRIVACY.md` exists and is hand-written; nothing generates it from `DISPOSITIONS` | D6 |

Two further absences are tooling rather than features, and are recorded in
`code-quality-assessment.md` because they bear on every unit: there is no
ktlint, spotless or detekt in the Android build, and no dependency lockfile
or checksum verification on either surface.

## Sources

- [code] `app/**/*.py` and `android/src/main/kotlin/**/*.kt`, read 2026-10-22
  at commit `b14b1fa`
- [verified] coverage figures from
  `python3 -m pytest tests --cov=... --cov-config=.coveragerc-backend`,
  run 2026-10-22
- [verified] absences confirmed by `grep` across `app/`, `android/src/`,
  `migrations/` and `openapi.json`
