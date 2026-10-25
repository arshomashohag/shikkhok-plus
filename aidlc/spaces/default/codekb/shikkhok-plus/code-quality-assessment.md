# Code Quality Assessment

Everything in this file was run or read on 2026-10-22 against commit
`b14b1fa`. Where a figure is quoted, the command that produced it is named.

## Headline

This is a **high-quality codebase for its size**, and unusually so in one
specific respect: the checks it has are built to fail honestly. Gitleaks is
preceded by an assertion that the clone is deep enough to scan. The DEX scan
refuses to pass when it finds no `.dex` entries. The manifest gate parses XML
rather than grepping, because an earlier version matched the manifest's own
comment. Four contract gates ship committed violation fixtures proving they
can fire, plus a test proving the fixture and the gate call one function. The
coverage configuration has one exclusion and a paragraph explaining why a
configuration entry is reviewable where a `# pragma: no cover` is not. That
pattern — *check the check* — recurs often enough to be the codebase's
defining habit.

The weaknesses are **not in what was built; they are in what was never
started.** The entire Android quality toolchain the team practice names is
absent, there is no dependency lockfile on either surface, and no CVE
scanning exists anywhere. Three further items are drift: a strict-typing
island that was deferred and never added, an allowlist that outgrew its own
asserted count, and a CI step whose label describes a control it does not
perform.

---

## Test coverage

### Backend

| Floor | Target | Measured | Verdict |
|---|---|---|---|
| `app/money` branch coverage | **100%**, `fail_under = 100` | **100.00%** (198 statements, 56 branches, 0 missed) | **Met** |
| Everything else, line coverage | **80%** | **91%** (1,657 statements, 136 missed) | **Met with 11 points of headroom** |

`python3 -m pytest tests` — **615 tests, all passing, 35 seconds.**

The brief recorded 90.51%; the figure measured here is 91% on the same
package list. Both are comfortably above the floor and the small difference
is rounding or a since-added test.

The 100% on the money module is **real, not pragma-assisted.** There are no
inline `# pragma: no cover` comments in `app/money/` and exactly one
`exclude_also` entry in configuration: `assert_never\(unreachable\)`. That
construct is unreachable *because* mypy proves the `match` over
`LedgerEntryKind` is total, so adding a kind without extending the fold fails
the type check rather than the coverage run. The reasoning for allowing one
exclusion and the caution that "a second candidate is a design signal, not a
second exclusion" are both recorded in `pyproject.toml`.

### The three lowest-covered backend modules, and whether it matters

| Module | Line coverage | Assessment |
|---|---|---|
| `app/db/seed_staging.py` | **0%** | A manual `python -m` entry point for seeding a staging database. Genuinely untested. Low risk — it never runs in production and the production startup check refuses to start with the staging flag set — but it is the one module with no exercise at all |
| `app/db/session.py` | **32%** | `build_engine()` and the real connection path. The suite drives the app through `TestClient` against a container engine, so the production engine construction is not exercised. The post-deploy smoke set is the compensating control, and it is a real one |
| `app/batches/service.py` | **81%** | The lowest of the *feature* modules, and the most consequential of the three. Lines 363-388, 426 and 464-478 are uncovered — that is `create_batch`'s tail and parts of `add_enrollment`. This is the module the roster unit will extend |

### Integration tests are genuinely integrated

The suite starts a **real PostgreSQL 16 container** and migrates it with
**Alembic from zero**, not from a schema dump. Docker was reachable during
this scan and the integration suites ran: `tests/privacy`, `tests/db` and
`tests/batches` — **115 tests, passing, 15 seconds.**

It connects as the restricted non-superuser role `shikkhok_app`, and
`tests/privacy/conftest.py` enforces that by two independent mechanisms: a
collection reorder putting the meta-test first by name, and an autouse
fixture that re-checks `current_user` is not a superuser, that
`row_security` is on and that the policy exists, erroring the whole package
if any has slipped. This is the correct paranoia: a privacy probe suite run
as a superuser does not fail, it passes.

**One caveat worth stating plainly.** `tests/conftest.py` skips the whole
integration suite with `allow_module_level=True` when no Docker daemon is
reachable. On a machine without Docker, `make check` passes having run none
of the row-level-security probes, none of the migration tests and none of
the roster tests — and the only signal is a pytest skip line. The skip is
reasonable (a backend-only change should not be unverifiable), but nothing
in CI asserts that Docker *was* present, so a runner image change that
dropped Docker would silently narrow the suite to its unit half. The project
applies exactly this "assert the precondition" reasoning to Gitleaks and not
to its own database suite.

### Android

**137 `@Test` functions across 14 files.** There is **no Kotlin coverage
report** of any kind — no JaCoCo, no Kover, nothing in `build.gradle.kts` —
which matters because the practice calls for Kotlin line coverage reported
from the first Android Bolt with **no decrease permitted** once three Android
Bolts have merged. Three have. There is no ratchet because there is no
number.

What **is** covered, and well:

- `MoneySerializerTest` and `NoFloatingPointTest` — the money boundary on
  the client, including loud failure on a JSON number.
- `AuthViewModelTest`, `AuthStateMapperTest`, `BatchesViewModelTest`,
  `RosterViewModelTest`, `RosterStateMapperTest` — the state machines,
  targeting the **mapping function** rather than an untargeted "the
  ViewModel", which is exactly what the practice asks for.
- `AuthScreenTest` and `RosterScreenTest` — Compose UI tests on the JVM via
  Robolectric, so the OTP-entry obligation is checkable in `make check`
  rather than only on a device.
- `MessageKeyCoverageTest` — keeps the client's message keys in step with
  `message-keys.json`.
- `AuthSurfaceRulesTest` — parses `uses-permission` elements rather than
  matching text, so the manifest comment that names `AD_ID` in order to
  forbid it does not trip the check.

### Named-test manifest

`tests/named_tests.toml` declares **36 obligations**, each with its
acceptance criterion, checked by an AST parse. The reasoning is sound and
not common: coverage measures whether branches *executed*, never whether the
right tests *exist*, and a missing named test whose branches another test
already covers is invisible to it.

---

## Linting, typing and static analysis

| Check | Result |
|---|---|
| `ruff check app tests` | **All checks passed** |
| `ruff format --check app tests` | **135 files already formatted** |
| `mypy app` | **Success: no issues found in 65 source files** |

Three clean runs. Ruff's selected rule sets are named rather than left at
the default — `E,F,W,I,UP,B,ASYNC,S,DTZ,BLE,D,RUF` — and the choice of each
is justified in a comment. `D` is on across the whole backend, which is why
every module, class and function carries a Sphinx docstring.

**Suppressions are few and each is annotated.** Across `app/` there are
exactly **7**: two `# noqa: S105` on error-code constants that are not
credentials, one `# noqa: S104` on a `0.0.0.0` fallback for a missing client
host, two `# type: ignore` (one on a Groovy-style untyped XML access, one on
FastAPI's `add_exception_handler` signature) and two `# pragma: no cover`
(one on a branch `_walk` already filters, one on a manual entry point).
`warn_unused_ignores` is on globally, so an ignore that becomes unnecessary
fails the type check rather than living forever.

**Zero `TODO`, `FIXME`, `HACK` or `XXX` comments** in `app/`, `tests/`,
`android/src/`, `migrations/`, `infra/` or `scripts/`. The only grep hits
were the string `01XXXXXXXXX`, a phone-number input hint.

### What is missing from static analysis

- **Semgrep is absent.** The practice called for a small set of
  project-specific rules. Four of the five it named are in fact enforced by
  something stronger (Ruff banned-api, the pytest import gate, the
  route-enumeration gate, and the Kotlin value class making `Double`
  unassignable). The fifth — no `TelephonyManager` reference anywhere in
  Kotlin — is caught by the DEX scan at **release time only**, so a
  `TelephonyManager` call can live on `main` through every PR and be found
  on the release build.
- **Schemathesis is absent.** Named in the practice for unexpected 500s,
  type drift and auth-present-on-every-route. The schema-diff gate (the
  check the practice said Schemathesis *cannot* provide) is built; the
  conformance half is not.

---

## The Android toolchain gap

This is the single largest divergence between the written practice and the
built state, and it concentrates on the surface the practice itself
identifies as the thinnest-reviewed.

Verified absent by `grep` across every `.kts`, `.toml`, `.yml` and
`.properties` file in the repository:

| Tool | Practice | Built |
|---|---|---|
| **ktlint** (formatter) | required, `official` style | **absent** |
| **spotless** (runs ktlint; also covers `strings.xml` and the Gradle files) | required, "decided at project setup, because the first reformat is a whole-module diff" | **absent** |
| **detekt** (the `Double`/`Float` ban in `core/model`) | required as a backstop | **absent** |
| **`lint.xml`** raising `HardwareIds` to fatal | required as a complement to the DEX scan | **absent** |
| **Kotlin coverage report** with a no-decrease ratchet | required from the first Android Bolt | **absent** |
| **Compose screenshot tests** at the longest Bangla string | one of two named verifiers for the layout obligation | **absent** — no Paparazzi, no Roborazzi, no screenshot infrastructure |

Two consequences are worth stating precisely rather than generally.

1. **The Bangla layout obligation currently has no verifier.** Both string
   bundles are complete (53 strings each) and no user-facing string is
   hard-coded, which is the hard half. But the practice says the obligation
   needs "Compose screenshot tests at the longest Bangla string, or an
   explicit per-screen manual check", and neither exists. As the practice
   itself puts it, an unverifiable obligation is a wish.

2. **The release gates are excellent and they are the only Kotlin checks.**
   `android/release-gates.gradle.kts` is genuinely good work — the manifest
   gate parses XML after an earlier version matched its own comment; the DEX
   scan matches **whole identifiers** after a bare `contains` flagged
   `getSerialization` as device-identifier access; and it scans for the
   lowercase **value** `android_id` rather than the field name, found by
   deliberate defect injection when a planted `ANDROID_ID` read passed. But
   they run on `bundleRelease` only. Between commit and release, nothing
   checks Kotlin at all except `testDebugUnitTest`.

---

## Supply chain

Covered in full in `dependencies.md`. The short form:

- **Gitleaks is present, blocking, and guarded.** The step asserting the
  clone has at least two commits is the kind of control most projects do not
  think to add, and it is there because Gitleaks reports "no leaks found in
  partial scan" after reading zero bytes in a shallow clone.
- **No lockfile on either application surface.** No `uv.lock`, no
  `requirements.txt`, no `gradle.lockfile`, no
  `gradle/verification-metadata.xml`. Terraform is the one surface that is
  properly locked, and its `versions.tf` states the reasoning the other two
  do not act on.
- **No CVE scanning anywhere** — no Dependabot config, no `pip-audit`, no
  Trivy, no `osv-scanner`. `.security-exceptions.md` does not exist, which
  is at least consistent: nothing produces findings to except.
- **Syft SBOM** runs at the Android release gate only; the backend image has
  none.
- **No ZAP baseline pass.**

---

## CI/CD

Three workflows. `check.yml` runs `make check` — the same command locally
and in CI, which for a solo build is the single most important property of
the gate.

What is well-handled:

- The backend and Android jobs are **split**, so a Kotlin build never gates
  a backend change.
- Ten-minute and fifteen-minute timeouts, concurrency groups, and
  `cancel-in-progress` on checks but **not** on deploys (an interrupted
  `terraform apply` is worse than a slow one).
- CI authenticates to AWS by **OIDC**, not long-lived keys.
- `release-android.yml` writes the keystore from a base64 secret to
  `$RUNNER_TEMP`, **shreds it afterwards**, and verifies the bundle is
  signed before publishing.
- `deploy.yml` has a distinct plan job, prints what is about to be applied,
  and runs Alembic as a separate logged step before the new container serves.

Two findings:

1. **No `push` trigger on `check.yml`; nothing runs on merge.** This is
   deliberate and documented at length — the user instructed it on
   2026-10-19 — and the obligation moves to GitHub's "Require branches to be
   up to date before merging" under branch protection. That setting is
   repository configuration and **cannot be verified from the repository**.
   If it is off, a PR green against an older `main` can merge and break it,
   and the breakage is found by the next PR's run. The workflow comment is
   admirably honest about this; the risk is simply unverifiable from here.

2. **The step labelled "Step 2. Lockfile verification, Python side" is
   `python -m pip install -e ".[dev,api]"`** (`check.yml:88-90`) — an
   unpinned resolve. A label describing a control that does not exist is
   worse than no label, because the next reader checks the box.

---

## Specific findings

Stated plainly, with file and line. None of these is a live security hole;
three are drift between a written decision and the code.

### 1. `app.authz` is a declared mypy strict island and is not configured

`pyproject.toml` configures `app.money.*` and `app.schemas.*`. The comment
above the `app.schemas` override says `app.authz.*` "stays unconfigured
until U3 creates its resolvers, on B1's same reasoning." **U3 shipped;
`app/authz/resolve.py`, `summary.py`, `annotations.py` and `rls.py` all
exist.** The override was never added.

The reasoning for deferring was correct — an override naming a module that
does not exist is dead configuration — and the follow-up simply did not
happen. The gap is small in practice (`disallow_untyped_defs` is on
globally and `mypy app` is clean), but `strict = true` adds
`disallow_untyped_calls`, `no_implicit_reexport` and
`warn_return_any` on the module that decides authorization.

### 2. `PUBLIC_ROUTES` allowlists two routes that do not exist

`app/contract/routes.py:33-49`. The comment reads "Exactly five, and the
count is asserted: a sixth entry is a diff against a stated number rather
than a line appended to a growing list." **The frozenset holds six
entries.** Two of them —

```python
("GET", "/account-deletion"),
("POST", "/account-deletion"),
```

— are asserted present by `tests/contract/test_route_lenses.py:86-87`, and
**no handler registers either path anywhere.** Confirmed: the only
occurrences of the string in the codebase are those two lines, the two test
assertions, and a prose mention in `app/governance/dispositions.py:18`.

Nothing is reachable, so this is not an authorization hole. It is
pre-declared scope for the unbuilt deletion unit, and two things follow: the
allowlist is currently wider than the application, and the comment's stated
count no longer matches its contents. The deletion work should land handlers
against entries that already exist rather than adding new ones.

### 3. The error envelope is published but referenced by no operation

`app/main.py:144-182` injects `ErrorEnvelope` and `Money` into the generated
document explicitly, because FastAPI emits a component only when a route
references it and no route carries either on its declared responses. The
code is honest about being a stopgap: "This stays until a Unit whose routes
genuinely reference them lands, at which point it becomes a no-op rather
than a lie."

The effect is that a client author reading `openapi.json` sees the envelope
defined and learns from no operation that a 403 or a 409 returns it. It also
means a ZAP baseline pass driven from this schema would not know which error
shapes to expect. The fee and payment work is the first unit with declared
error responses and is the natural place to close it.

### 4. `batches → auth` cross-feature import on the client

`BatchesViewModel.kt` imports `com.shikkhokplus.app.feature.auth.AuthResult`.
A shared result type belongs in `core`. Trivial today; it is the shape that
spreads once a dozen features need the same type, and with no detekt nothing
would stop it.

### 5. `app/api/health.py` imports `get_session` from `app.api.auth`

Rather than from `app.api.deps`, where the other dependencies live
(`health.py:23`). Not a cycle and not a defect — a naming inconsistency
only, noted because the next router added will copy one of the two.

### 6. Declared Python is 3.12; the local interpreter is 3.13.2

The project targets 3.12 everywhere (`requires-python`, Ruff
`target-version`, mypy `python_version`, the Docker base) and CI pins 3.12.
The full suite passes on the local 3.13.2. A 3.13-only behaviour would pass
locally and fail in the container.

---

## Documentation quality

**Excellent, and in an unusual form.** There is no `README.md` at the
repository root, but there is `CONTRACT.md` (how and why the contract is
changed, including a measured finding that five interpreter processes
serializing one seven-element set produced five different orderings),
`infra/README.md`, `infra/bootstrap/README.md`, `infra/REGION-MIGRATION.md`,
`deploy/README.md`, `docs/legal/PRIVACY.md`, `docs/legal/README.md`,
`docs/delivery/vertical-slices.md` and `CHANGELOG.md`.

The primary documentation, though, is **in the docstrings**, and they are
dense with rejected alternatives: why the money `TypeDecorator` lives under
`app/db` and not `app/money`; why `schemas/money.py` is a `RootModel` and
not an `Annotated` alias; why `app.routes` could not be enumerated
directly; why the ceilings are checked narrowest-first and why global-first
"still looks like defence in depth"; why `disallow_any_explicit` is off on
`app.schemas`. Several record a defect that was actually found and how.

Two risks come with that style, worth naming because the codebase otherwise
invites trust:

- **A comment can go stale while the code around it stays correct.** Finding
  2 is exactly this: the "exactly five" comment is now wrong and nothing
  checks it. Where a comment states a number, the number is a claim.
- **Density raises the cost of a careless edit.** The `db/money_type.py`
  module docstring runs 26 lines before the first import. That is a feature
  for a reader and a cost for anyone moving code.

---

## Technical debt register

| # | Item | Severity | Effort | Where |
|---|---|---|---|---|
| 1 | No dependency lockfile on either application surface | **High** | S | repository root, `android/` |
| 2 | No CVE scanning at any speed | **High** | S | `.github/workflows/` |
| 3 | No ktlint, spotless or detekt on the thinnest-reviewed surface | **High** | S | `android/build.gradle.kts` |
| 4 | Bangla layout obligation has no verifier | **Medium** | M | `android/src/test/` |
| 5 | No Kotlin coverage report, so no ratchet | **Medium** | S | `android/build.gradle.kts` |
| 6 | `app.authz` strict island never configured | **Medium** | XS | `pyproject.toml` |
| 7 | `PUBLIC_ROUTES` allowlists two non-existent routes; comment's count is wrong | **Medium** | XS | `app/contract/routes.py:33-49` |
| 8 | CI step labelled "Lockfile verification" performs an unpinned resolve | **Medium** | XS | `.github/workflows/check.yml:88` |
| 9 | Error envelope published but referenced by no operation | **Medium** | S | `app/main.py:144-182` |
| 10 | `app/batches/service.py` at 81%, the lowest feature module | **Medium** | S | `tests/batches/` |
| 11 | Integration suite skips silently without Docker; nothing asserts it ran | **Medium** | XS | `tests/conftest.py:30-47` |
| 12 | No `lint.xml` raising `HardwareIds` to fatal | **Low** | XS | `android/` |
| 13 | No Schemathesis conformance pass | **Low** | M | `tests/contract/` |
| 14 | No ZAP baseline, no Trivy, no backend SBOM | **Low** | M | `.github/workflows/` |
| 15 | `app/db/seed_staging.py` at 0%, `session.py` at 32% | **Low** | S | `tests/db/` |
| 16 | `batches → auth` cross-feature import | **Low** | XS | `BatchesViewModel.kt` |
| 17 | No navigation library; `MainActivity` switches on state | **Low** now | M later | `MainActivity.kt` |
| 18 | Container bases pinned by tag, not digest | **Low** | XS | `Dockerfile` |
| 19 | Declared Python 3.12, local interpreter 3.13.2 | **Low** | XS | environment |

Items 3, 4, 5 and 12 are a single cluster — the Android quality toolchain —
and the plan already places the Macrobenchmark harness and the remaining
release-packaging work in one unit. Items 1 and 2 are a second cluster and
are the highest-value small change available in the repository.

---

## Invariant verification

Each project-mandated invariant, checked against the code rather than
assumed. This is the section the next unit's design should read first.

### Money is never float or double anywhere — **HONOURED, and mechanically**

Four independent mechanisms, none of them review:

1. `Money.__init__` raises on a `float` or a `bool`
   (`app/money/_money.py:60-68`). It catches the case no float ban catches:
   `Decimal(0.1)` produces a `Decimal` that passes a type check while
   already being wrong.
2. Ruff bans importing `decimal` and `decimal.Decimal` outside
   `app/money/**`, and `app/money/**` takes an explicitly **empty** ignore
   list so its permission comes from being the carve-out, not an exemption.
   `test_gate2_config_scope` asserts the carve-out resolves to exactly that
   path and never a parent.
3. `MoneyColumn` maps to `NUMERIC(12,2)` with `asdecimal=True` and
   `process_bind_param` **raises `TypeError`** on a bare `Decimal` or `int`.
   `MONEY_PRECISION` and `MONEY_SCALE` are declared once, so no model
   restates them — and `app/db/models.py` imports no `Decimal` at all.
4. On the wire, `Money` is a Pydantic `RootModel[str]` with pattern
   `^[0-9]+\.[0-9]{2}$` (**no sign**), and the schema gate asserts every
   money property `$ref`s that one component. Two name-matched backstops
   catch a money-named property emitted as a JSON number or as an
   unconstrained string — both holes found by *testing* the gate rather than
   reading it. The gate looks through `anyOf`/`allOf`/`oneOf`, `items` and
   `additionalProperties`, so the nullable shape the project actually uses
   (`fee_amount`) and a future `list[amount]` are both visible to it.

On the client, `@JvmInline value class Money(val amount: BigDecimal)` makes
a `Double` assignment a **compile error**, and `MoneySerializer` inspects
`JsonPrimitive.isString` rather than calling `.content`, so a JSON number
throws rather than coercing.

`ROUND_HALF_UP` is declared once in `_rounding.py`; multiplication is a
named `apply_rate` and not `__mul__`; division is not exposed. The module
imports nothing from the application and carries **100% branch coverage**.

*Residual gap, acknowledged in the code:* the two name-matched backstops
match a narrow token list, so a genuine money column named `tuition`,
`stipend` or `discount` is seen by neither. `app/contract/money_names.py`
records this explicitly rather than claiming completeness.

### No role column; role is a per-request computed lens — **HONOURED**

`grep` confirms no `role` column on any model. Migration `0002` *deletes*
the old `enrollment.role` guardian rows as part of the reshape that put both
links on one row.

`app/authz/resolve.py` computes all three lenses in **one SQL statement**
over `owner` and `enrollment`. The memo lives on `request.state` and nowhere
else; the file contains no module-level dict and no `lru_cache`, and
`tests/authz/test_memoization.py` asserts their absence rather than trusting
a reading. `LensResolver.__init__` holds no state beyond the session,
because an instance attribute holding resolved lenses would outlive the
request whenever the resolver does.

The client's `LensHint` travels **out** only, in `X-Lens-Hint`, and the
server response is self-describing. A hint naming an unsupported lens is
refused with `LENS_NOT_AVAILABLE`. `tests/authz/test_dual_role_cost.py`
proves one account resolves all three lenses in one statement;
`tests/batches/test_role_restricts_writes.py` proves a student is refused a
teacher's operations.

### Privacy enforced structurally in three layers — **HONOURED**

1. **Separate tables by writer.** `profile` holds only `self_name` and
   `photo_ref`, keyed by `account_id`.
2. **Row-level security.** Migration `0001` runs both
   `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY` on
   `profile` — `FORCE` matters, because RLS otherwise does not apply to the
   table owner, which is the connection migrations run as. The
   `profile_owner_only` policy reads `app.account_id`, set via
   `set_config(..., true)` so it is **transaction-local** and cannot leak
   across a pooled connection. `app/authz/rls.py` is the only setter, and
   its docstring states that a session-scoped set "looks identical in every
   single-request test".
3. **Response schemas.** `app/contract/privacy.py` walks the generated
   document from every teacher-lensed route's response model, recursing
   through `$ref`, `items` and the three combinators with a cycle guard, and
   fails on any field in `OWNER_PRIVATE_FIELDS` or
   `FORBIDDEN_ACCOUNT_ID_FIELDS`. The lens is read **from the route**, never
   guessed from the schema name, and `lens_types_of` returns a **set** — an
   earlier version returned the first match, so a dual-lens route could be
   classified guardian-facing and skip the gate entirely while the route
   gate correctly reported it lensed.

Tests connect as the restricted non-superuser role, with the meta-test
ordered first by two mechanisms.

### Every endpoint names its lens — **HONOURED**, with the caveat in Finding 2

`app/contract/routes.py` enumerates routes from
`app.state.included_routers` — recorded by `main.py` **as it includes** —
rather than from a hardcoded list, so a conditionally registered router
cannot be invisible. It matches on the dependency's **return annotation**
being a `Lens` subtype, walking sub-dependencies recursively, because a lens
is routinely nested inside a composed dependency. A resolution failure
**raises** naming the route; the docstring is explicit that a resolver
returning a default on failure would let every route pass.

This gate has already caught itself once: `isinstance(route, APIRoute)` over
`app.routes` matched **nothing** in this FastAPI version, and the gate
passed against zero routes. A test now cross-checks the route count against
the generated document. The privacy gate had the identical defect and was
fixed in the same sweep.

Two separate allowlists, which is the right structure. The caveat is Finding
2: `PUBLIC_ROUTES` currently allowlists two paths with no handler.

### No device or advertising identifier on Android — **HONOURED**

The merged manifest declares exactly `android.permission.INTERNET`, asserted
by a Gradle task that **parses XML** and that finalises `bundleRelease`.
Seven permissions are named as forbidden explicitly rather than left to the
allowlist, so the failure message says "AD_ID is present" rather than
"unexpected permission": `AD_ID`, `READ_SMS`, `RECEIVE_SMS`,
`READ_PHONE_STATE`, `READ_PHONE_NUMBERS`, and both location permissions.

The DEX scan runs on the **R8-minified** release archive, matching ten
identifiers as whole tokens. Both refinements came from real defects: a bare
`contains` flagged `getSerialization` and `getSerializedSize`, and a planted
`ANDROID_ID` read **passed** until the scan was changed to look for the
lowercase value `android_id`, because `Settings.Secure.ANDROID_ID` is a
compile-time constant that javac inlines. The task fails when it finds zero
`.dex` entries, so a scan that read nothing cannot report clean.

No analytics, crash-reporting or ads SDK appears in `libs.versions.toml` or
any build script. `allowBackup="false"`, so Auto Backup cannot copy
children's-adjacent data to a user's Google Drive.

*Caveat:* both gates run on `bundleRelease` only, and `lint.xml` raising
`HardwareIds` to fatal — the complement the practice names, which analyses
sources at build time — does not exist. A `TelephonyManager` call can sit on
`main` through every PR.

### No hardcoded credentials — **HONOURED**

Gitleaks runs blocking on every PR with a precondition assertion. `.jks`,
`.env` and `.env.*` are gitignored with `!.env.example` re-included. The
Android signing config reads four values from the environment and produces
an **unsigned** build when they are absent. The release workflow writes the
keystore to `$RUNNER_TEMP` and shreds it. The two `# noqa: S105`
suppressions are on error-code string constants, annotated "an error code,
not a credential", and both are genuine.

The one credential-shaped literal in the tree is
`RESTRICTED_PASSWORD = "test-only-restricted"` in `tests/conftest.py`,
annotated as a test-only value for a container destroyed with the session.
That is correct.

### Business rules stay server-side — **HONOURED so far**

`_roster_status()` (`app/api/batches.py:71-85`) returns `dormant`,
`inactive` or `active` rather than letting the client compare
`inactive_from` to today, and the docstring names that as "the erosion path
this function exists to close". `BatchesStateMapper` and
`RosterStateMapper` map a server response to a UI state; the composables
render it. No composable was found comparing a domain value.

This is the invariant most exposed by the work ahead: every fee screen is a
place where `if (balance > 0) "Due" else "Paid"` would look like UI code,
and with no detekt nothing mechanical would catch it. The server-sent status
enum is the established pattern and already has a precedent to copy.

---

## Sources

- [verified] `python3 -m pytest tests` — 615 passed, 35 s, 2026-10-22
- [verified] `python3 -m pytest tests --cov=app.money --cov-branch` —
  **100.00%**, `fail_under = 100` reached
- [verified] the 13-package backend coverage run — **91%**, floor 80%
- [verified] `python3 -m pytest tests/privacy tests/db tests/batches` —
  115 passed against a real PostgreSQL 16 container
- [verified] `ruff check` clean, `ruff format --check` clean (135 files),
  `mypy app` clean (65 files)
- [verified] 137 `@Test` functions across `android/src/test/`
- [verified] zero `TODO`/`FIXME`/`HACK`/`XXX` in source
- [verified] absence of ktlint, spotless, detekt, `lint.xml`, Kotlin
  coverage, screenshot testing, lockfiles, Dependabot, Semgrep,
  Schemathesis, Trivy and ZAP, by `grep` across all build scripts,
  workflows and version catalogues
- [code] `pyproject.toml`, `android/release-gates.gradle.kts`,
  `app/contract/`, `app/money/`, `app/authz/`,
  `migrations/versions/0001_initial_identity_schema.py`,
  `.github/workflows/check.yml`
