# Team-Level Rules

> This team's affirmed practices and corrections. Loaded after `org.md` as
> strict-additive guidance; contradictions with broader policy are rejected.
> Populated by the practices-discovery affirmation gate. Edit at the gate,
> not directly.

## Way of Working

We use **trunk-based development**. All work merges to `main` via short-lived
branches; a branch that cannot resolve within one to two days is a sign the
piece of work was cut too large, not a reason to keep the branch longer.

For Construction worktrees the base branch is `main` and the merge target is
`main`. We **squash-merge** each Bolt into `main`, so one Bolt becomes one
commit named by the Bolt slug, and `main` reads as the delivery-planning Bolt
sequence. The full intermediate history stays on the Bolt branch until that
worktree is discarded, and the audit log preserves the event sequence
regardless.

We work **solo**: the agent writes most of the code and the user reviews all of
it [OC-1]. Two consequences we accept deliberately:

- **Review is the only quality gate that sees intent.** Tests and linters catch
  what they are told to catch; the review catches whether the thing is the right
  thing. Where review depth is known to be shallow — the Android surface
  [OC-3] — we compensate with conventional choices, with tests an unfamiliar
  reviewer can read, and with checks that fail in CI rather than in review, not
  with more review.
- **Pull requests are a record, not a negotiation.** With one reviewer there is
  no approval quorum to wait for. We still open a PR per Bolt because the diff
  view is where review actually happens and because CI attaches its result
  there.

**Structural concerns are raised as they arise; naming and convention concerns
are not** [OC-6, D-45]. An agent that spots a schema, authorization or money
problem interrupts. An agent that would prefer a different variable name stays
quiet and lets the formatter and linter settle it.

**Where a rule is important, it is mechanical.** This is the organising
principle behind most of what follows, and it is a direct consequence of solo
work: a rule enforced by review is enforced by one stretched reviewer, and on
the Android surface by a reviewer still learning the platform. So the money
boundary is a type and an import check, the lens is a data dependency and a
route-enumeration test, the forbidden-identifier set is a manifest allowlist and
a bytecode scan, and the privacy boundary is a restricted database role. In each
case review remains the backstop and stops being the mechanism.

**A practice is not in force until its mechanism exists, and the practice file
says which unit carries it.** *(Added 2026-10-22.)* This is the correction the
built state forces. The 2026-10-16 practices were written before any code
existed and several named a mechanism without naming the Bolt that installs it;
the Walking Skeleton section's toolchain sequencing did this well for the
backend and badly for Android, which is exactly where the gap opened. Four
Units shipped with the backend mechanisms in place and the whole Android
quality toolchain absent, and nothing in the process noticed, because no
artifact owned the sentence "this is due in D-n". From here, a practice naming
a mechanical control names the deliverable unit that installs it, and a unit is
not complete while a control assigned to it is missing. The three reconciled
gaps below each carry such an assignment.

**Construction is autonomous for the remaining units.** *(Amended 2026-10-22.)*
The 2026-10-16 practice gated review through "the payment slice, then
autonomous", and that slice was the platform-subscription boundary, which no
longer exists — the app charges nobody. Delivery planning settled this [Q8] and
this practice follows it rather than contradicting it. The fee system remains in
full in D3 and remains the most consequential arithmetic in the product; it no
longer marks a *gating* boundary. Human stops that remain regardless: Plan
Approval, summary confirmation, verification-command selection, and any failure.

Single trunk even once we have more than one environment: releases are gated by
tag and by environment-specific configuration, never by a long-lived release
branch.

---

## Walking Skeleton

**The skeleton is built and does not recur.** B3 `identity-and-access` was the
walking skeleton and was human-checkpointed. It proved what it set out to
prove: a Compose screen against a real FastAPI endpoint against real PostgreSQL
through real OTP-issued authentication, with the lens computed per request
rather than stored, and all seven OTP abuse controls tested. The skeleton
ceremony does not repeat for D1–D6.

The 2026-10-16 skeleton section is retained in full as the record of what that
Unit was required to prove and what it did prove. Nothing in it is re-opened.

**What carries forward from it is the toolchain-sequencing clause, and it needs
a correction.** *(Amended 2026-10-22.)* The original read:

> **The toolchain is sequenced so the skeleton does not become a toolchain
> Bolt.** Skeleton-time: Ruff with its selected rule sets, mypy on the money
> module, pytest with testcontainers, Gitleaks as a pre-commit hook and a CI
> job, and the dependency lockfiles. Arriving with the Bolt that first needs
> them: Schemathesis and the OpenAPI schema-diff gate, detekt, the Kotlin
> coverage report, the manifest allowlist and DEX scan (the first Android
> release build), Syft, and the ZAP baseline pass.

Measured against the built state, the skeleton-time list was delivered except
for **the dependency lockfiles**, which were named as skeleton-time and never
landed. The deferred list fared worse: the schema-diff gate, the manifest
allowlist, the DEX scan and Syft all exist, while **detekt and the Kotlin
coverage report do not**, and nor do ktlint, spotless, `lint.xml` or any
screenshot harness. Schemathesis and the ZAP baseline also do not exist; ZAP is
assigned to D5 by the delivery plan, which is consistent.

The defect in the clause is "arriving with the Bolt that first needs them",
which names no Bolt. A Kotlin formatter is first *needed* by the first Kotlin
file, and three Android Bolts have now merged without one. The replacement
rule is the one stated under Way of Working: **a deferred control names the
deliverable unit that installs it.** The assignments this run makes are in the
Deployment and Code Style sections and are summarised here:

| Control | Named at | Assigned to |
|---|---|---|
| Python and Gradle lockfiles, Gradle checksum verification | skeleton-time, not delivered | **before D1** |
| CVE scanning, both speeds, and `.security-exceptions.md` | deployment practice, not delivered | **before D1** (per-push half), **D6** (release-gate half) |
| ktlint via spotless, detekt, `lint.xml`, Kotlin coverage ratchet | "the Bolt that first needs them", not delivered | **before D1** |
| Bangla layout verifier | testing posture, no verifier exists | **before D1** if screenshot-based; otherwise a per-screen manual check in each unit |
| Macrobenchmark harness and low-end profile | B4, incomplete | **D5**, per the delivery plan |
| ZAP baseline, backend SBOM, Trivy | deployment practice | **D5** and **D6**, per the delivery plan |

---

## Testing Posture

Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt
without its tests is not done.

- **Methodology**: custom
- **Methodology evidence**: The cadence genuinely differs by surface, and
  recording a single uniform value would misdescribe what we actually do. Three
  facts drive the split. (1) The money paths — fee-cycle arithmetic,
  carry-forward, partial approval, waiver — have **mandatory** tests by stated
  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than
  I/O-shaped, and have expected values knowable before any implementation
  exists. That is the exact precondition under which test-first pays: the test is
  a specification we can write correctly without having written the code, and the
  fee model is *already known to be in revision* [D-18], so a suite that pins the
  arithmetic is what makes the next revision safe rather than frightening. (2) The
  Compose UI surface is the opposite case. There is **no declared Kotlin or
  Android experience** [OC-3], so a Compose test written before the
  implementation is as likely to encode a misunderstanding of the framework as to
  catch a defect, and when it passes it certifies that misunderstanding — worse
  than no test. (3) The privacy boundary is structural rather than arithmetic
  [D-7, TC-13] — enforced by table design, row-level security and distinct
  response schemas — so its tests are adversarial probes against a built
  boundary, which is inherently test-after. A uniform `tdd` would be a commitment
  we would break on the Compose Bolts; a uniform `test-after` would weaken the
  one surface where the requirement is explicit and the preconditions for
  test-first are actually met. `custom` is the accurate value. *Re-confirmed
  2026-10-22 against the built state: the money module shipped at 100% branch
  coverage with the property-based ledger test, and the privacy suite shipped as
  adversarial probes behind a superuser meta-check. The split described here is
  the split that was actually practised.*
- **Ordering**: Write the failing test first whenever **both** of these hold —
  the correct output is knowable from the requirement without having written the
  code, **and** a wrong answer would be a money error or an authorization error —
  and for everything else implement the layer, then write and run that layer's
  tests before the Bolt is complete.

That ordering is a **predicate, not a list**, and the distinction is the point:
an enumeration plus "everything else" fails open, because every case nobody
anticipated defaults to test-after. The following are *examples* of the
predicate holding, not its boundary:

- every change to the money module;
- every fee-cycle and payment-verification state transition — generation,
  carry-forward, partial and reduced approval, waiver, rejection;
- the `(enrollment_id, period)` idempotency constraint;
- every lens-resolution and row-level-security rule, wherever that code lives;
- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,
  leave existing dues standing, and leave the student active in other batches,
  all three of which are money-adjacent and fail quietly;
- the cross-batch dues query [PU-7.2], which is driven by outstanding balance
  and not by active status, so students who left owing money still appear;
- *(added 2026-10-22)* **acceptance state transitions in D1** — a seat moving
  from pending to accepted or declined grants or withholds a guardian lens, so
  a wrong answer is an authorization error and the predicate holds. This is the
  gap the re-cut exists to close and it is test-first.

**A change meeting the predicate does not escape it by being implemented in
Kotlin**, or in a route handler rather than in the money module. Where the code
lives is not part of the test.

**Test-after is a cadence, not permission to write the test against the
implementation.** A test-after test is written from the acceptance criterion. If
writing it requires reading the implementation to know what to assert, the
acceptance criterion is the defect.

Supporting bullets, which do not replace the two fields above:

- **Backend coverage floor**: 80% line coverage, enforced in CI, with no
  decrease permitted. This comes from the active `classic` scope at Comprehensive
  test strategy and may not be weakened to make a step pass. **The authorization
  layer is measured as branch coverage rather than line coverage** — lens
  resolution is pure branching over teacher, student and guardian and owned-batch
  membership, so line coverage on it is close to meaningless. *Measured
  2026-10-22: 91% overall against the 80% floor, 615 tests passing. Met with
  headroom.*
- **The money module carries 100% branch coverage**, because the defects that
  matter there live in the branches: the short-month clamp, the
  carry-forward-versus-waive fork, the partial-approval path, the
  zero-and-negative edges. An 80% line floor can be met while leaving the waiver
  branch entirely unexecuted, which satisfies the number and misses the
  requirement. Two things make that target honest rather than decorative: the
  money module contains **no I/O, no session and no HTTP**, so 100% stays
  reachable; and branch coverage is supplemented by obligations not reducible to
  a percentage — a named test per fee-cycle and payment state transition, and a
  documented boundary case per money input (period boundaries, rounding at the
  half, zero, negative, an approved amount exceeding the claimed amount). We also
  add one property-based test (Hypothesis) on the ledger invariant. *Measured
  2026-10-22: 100.00%, `fail_under = 100` configured. Met. The invariant in
  force is the corrected one recorded under Corrections, not the superseded
  `charged - received - forgiven == outstanding`.*
- **Android carries named obligations and no percentage floor.** Gating a surface
  the reviewer cannot yet evaluate produces tests written to raise a number; that
  is a reason to drop the *percentage*, not a reason to drop the *obligation*,
  and this is the thinnest-reviewed part of the product. So:
  - every ViewModel ships tests for its state machine — loading, success, error,
    and the explicit retry path for a failed write [TC-8, D-9];
  - every money-carrying model class ships a serialization test proving decode
    from a JSON string and **loud failure** on a JSON number, because a lenient
    decoder that quietly accepts a number and converts is the actual failure mode
    and it passes a happy-path-only both-sides test;
  - Kotlin line coverage is reported from the first Android Bolt, with **no
    decrease permitted** once three Android Bolts have merged. A no-regression
    ratchet gives the trend teeth without anyone inventing a target they cannot
    justify.

  **The first two obligations were met and the third was not.** *(Reconciled
  2026-10-22.)* 137 `@Test` functions across 14 files, targeting the mapping
  functions rather than untargeted ViewModels, which is what the practice asked
  for; `MoneySerializerTest` and `NoFloatingPointTest` cover the money boundary
  including loud failure on a JSON number. But there is **no Kotlin coverage
  report of any kind** — no JaCoCo, no Kover — and three Android Bolts have
  merged, so the ratchet that should now be in force has no number to ratchet.
  The obligation stands and the mechanism is assigned to **before D1**: a Kover
  report from the next Android Bolt, with the no-decrease rule arming on the
  first merged figure. Starting the ratchet now costs one plugin line and
  establishes the baseline before five more units of Kotlin land; starting it
  after D6 would baseline against the finished app and ratchet nothing.
- **Test types by layer**: pytest for backend unit and integration tests, with
  integration tests running against a **real PostgreSQL 16** container via
  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,
  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and
  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin
  ViewModel and repository tests, targeting the response-to-UiState mapping
  function rather than an untargeted "the ViewModel". Compose UI tests for the
  OTP entry path and the mid-class attendance path.
- **The integration suite must assert that it ran.** *(Added 2026-10-22.)*
  `tests/conftest.py` skips the whole integration suite at module level when no
  Docker daemon is reachable, so on a machine without Docker `make check` passes
  having run none of the row-level-security probes, none of the migration tests
  and none of the roster tests, signalling only a pytest skip line. The skip
  itself is reasonable. What is missing is the precondition assertion this
  project applies to Gitleaks and not to its own database suite: **CI asserts
  Docker was present and the integration suite actually ran.** A runner image
  change that dropped Docker would otherwise silently narrow the suite to its
  unit half, and the privacy boundary is the thing that would stop being tested.
  Costs one step; assigned to **before D1**.
- **Database tests connect as a restricted non-superuser role.** PostgreSQL
  documents that superusers and table owners bypass row-level security entirely
  [pg-rls], and the default test-container connection is `postgres`, a superuser.
  A privacy-boundary suite run as superuser passes identically whether the policy
  is correct, broken, or entirely absent — so the strongest test obligation we
  have would certify nothing. Integration tests therefore connect as the same
  restricted role the application uses, and a **meta-test asserts that
  `current_user` is not a superuser and that row-level security is in force**
  (`row_security` on, policy present) before the privacy suite runs. *Verified
  2026-10-22: built, as `shikkhok_app`, enforced by a collection reorder and an
  autouse re-check. This is the practice working exactly as written.*
- **Privacy boundary tests are adversarial, and the API-level half is a
  schema-wide invariant.** No teacher-lens response schema may contain any field
  in the owner-private profile set, enforced by iterating the generated OpenAPI
  schema rather than by remembering to write a test per endpoint — per-endpoint
  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking
  about it. The probe suite explicitly covers the IDOR shape: teacher A
  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a
  student requesting a fee cycle not their own.
- **Schemathesis validates conformance, not correctness, and never counts as
  privacy coverage.** We keep Schemathesis for what it is good at — unexpected
  500s, type and required-field drift, auth present on every route — and we add
  the check it cannot provide: **an OpenAPI schema-diff gate**, where the
  committed schema must match the generated one and CI fails if they diverge.
  *Built 2026-10-22: the schema-diff gate exists and works. Schemathesis itself
  does not. That is the right half to have built first — the practice says so —
  and the conformance half remains outstanding at Low severity, unassigned. We
  are not assigning it to a unit: it is a genuine nice-to-have, and naming a
  unit for it would be the same empty promise this run is correcting.*
- **Money representation is itself a test target.** Every money value crosses the
  API as a JSON **string** [TC-7, D-20], asserted on both sides.
- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle
  guarantee is a database constraint precisely because application-level guards
  fail under concurrency [D-21, TC-12]. The test runs overlapping generations
  and asserts the **outcome**: after N overlapping generations exactly one row
  exists per `(enrollment_id, period)` and the ledger total is unchanged. It also
  covers the case concurrency alone misses — the daily self-healing re-run
  [PU-5.5] must be idempotent across *days*. **This lands in D3 and has not been
  exercised yet**, because fee cycles are not built.
- **Token lifecycle is tested as a state machine.** Refresh-token rotation with
  reuse detection has a security-critical failure mode: present a rotated-out
  token and the whole token family must be invalidated.
- **Both account-deletion paths are tested** [TC-19]: the in-app path and the
  externally accessible route. Each must assert that deletion removes what the
  Data Safety form claims it removes and retains only what the privacy policy
  discloses [RC-4, RC-5], per each table's written disposition. Deletion features
  are the ones most reliably shipped broken, because nobody tests the absence of
  data. **This is D6** and neither path exists yet; `PUBLIC_ROUTES` already
  allowlists both, so D6 lands handlers against entries that exist rather than
  adding new ones.
- **PU-3.6's mid-class speed requirement is not discharged by a correctness
  test.** Either the attendance obligation is a **Macrobenchmark on a low-end
  device profile** (which also serves TC-17), or PU-3.6 has no automated
  verification in V1 and carries an explicit manual check in the pilot. Both are
  acceptable; silently using a correctness test to discharge a performance
  requirement is not. **The harness does not exist and is assigned to D5** by
  the delivery plan, while the attendance screen it measures lands in D4. That
  ordering is backwards and the delivery plan records it as an open question;
  this practice does not resolve it, it only insists the obligation is not
  discharged by a Compose correctness test in D4.
- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:
  Compose screenshot tests at the longest Bangla string, or an explicit
  per-screen manual check. "Must not break the layout" currently has no verifier,
  and an unverifiable obligation is a wish. *(Reconciled 2026-10-22.)* **The
  hard half is done and the verifier is absent.** Both bundles are complete at
  53 strings each and no user-facing string is hard-coded. But there is no
  Paparazzi, no Roborazzi, no screenshot infrastructure of any kind, and no
  written per-screen manual check either — so of the two verifiers the practice
  offered, neither exists, across three shipped screens. The practice's own
  sentence applies to itself: this obligation is currently a wish. Both options
  remain acceptable and the choice is the human's at this gate; what is not
  acceptable is a fourth, fifth and sixth unit of screens shipping with neither.
- **One command, local and in CI.** `make check` or equivalent, the same
  entrypoint in both places. For a solo build this is the single most important
  property of the gate: a gate reproducible only by pushing is a gate that gets
  bypassed. The blocking suite needs no secret to run locally. *Verified
  2026-10-22: `make check` is the CI entrypoint. Working as intended.*
- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if
  minutes become a real constraint. The Android job is split from the backend job
  so a Kotlin build does not gate a backend PR, dependencies are cached, and the
  backend path stays under about ten minutes. *Verified 2026-10-22: split, with
  ten- and fifteen-minute timeouts, concurrency groups and `cancel-in-progress`
  on checks but not on deploys. Built well.*
- **A green `main`, not just a green PR.** With squash-merge and one reviewer, a
  PR green against an older `main` can merge and break it. The post-merge run was
  removed on 2026-10-19 at the user's instruction ("don't run actions on merge"),
  and the obligation moves to GitHub's **"Require branches to be up to date
  before merging"** under branch protection. **That setting is repository
  configuration and cannot be verified from the repository.** If it is off, this
  obligation has no verifier. We flag it as the one practice whose status this
  run genuinely cannot establish; confirming it is a thirty-second check in the
  repository settings and worth doing before D1.
- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.
  Tests that always pass regardless of implementation are defects in their own
  right and are rejected in review.

---

## Guard Policy

<!-- Affirmed by the team. Mode: strict, relaxed, or off. Strict here holds for every intent, whatever one person asks in chat; relaxed or off here applies to every intent whose policy came from its scope, unless project.md or the person sets another; changing this line changes it. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

We **deploy to staging on an explicit dispatch**, not on merge. A deploy is an
action someone takes, with the ref and whether to migrate chosen at the time.
Production deploys are a separate, explicitly triggered step. With a solo build
the `org.md` default of "tech lead plus product owner sign-off" has no meaning —
the same person holds both roles — so the gate is not an approval quorum but a
**checklist the person completes**: staging smoke passed, Alembic migration
reviewed and reversible-or-forward-safe, no open Critical or High dependency
finding without a dated written exception, and the manifest allowlist and DEX
scan green on the release build.

> *Note on that checklist, 2026-10-22: its third line has never been checkable,
> because nothing produces dependency findings. It becomes checkable when the
> CVE gap below is closed, and not before. Until then that line of the release
> checklist is ticked against nothing.*

**A staging Lightsail instance exists in Phase 1**, taking Phase 1 hosting from
roughly USD 13 to roughly USD 25 per month against the USD 50 ceiling [OC-4].
Staging is where a migration gets rehearsed before it touches real teacher and
child data, and there is no multi-AZ database to fail over to if it does not.

Environment topology, matching the phased hosting decision [D-29]:

| Environment | Phase 1 (closed testing) | Phase 2 (launch) |
|---|---|---|
| Local | Docker Compose, Postgres 16 container | unchanged |
| Staging | Lightsail instance, containerized Postgres | Lightsail or small EC2, separate RDS or separate database |
| Production | — (closed testing is the audience) | Lightsail/EC2 container, RDS `db.t4g.micro`, Single-AZ |

**The budget decides the environment count, not preference.** What staging must
be faithful about is **schema, migration path and authorization behaviour**,
because those are what a deploy can break irreversibly.

- **Migrations are forward-only and backward-compatible.** Alembic runs as a
  distinct, logged step before the new container serves traffic, never as a side
  effect of application start. *Verified 2026-10-22: `deploy.yml` runs Alembic as
  a separate logged step, after a distinct plan job that prints what is about to
  be applied. Built as written.*
- **The database is the thing we cannot roll back**, so it gets the
  belt-and-braces treatment: a verified `pg_dump` to S3 immediately before any
  production migration in Phase 1, and an RDS snapshot in Phase 2, with the
  restore path exercised at least once before launch. An untested backup is not a
  backup — and an unverified *upload* is not a backup either, so we assert object
  existence and non-trivial size after upload. A failed backup alerts.
- **Rollback is redeploying the previous immutable image tag.** Images are tagged
  with the commit SHA; `latest` is never deployed. Recreate-style deployment is
  acceptable at this scale. We accept a short restart window and schedule
  production deploys outside Bangladesh classroom hours, because a dropped
  attendance write during a live class is exactly the failure a teacher will not
  forgive [D-9, TC-8]. *Verified 2026-10-22: SHA tagging in place, `latest` not
  deployed.*
- **A deploy is not done until smoke passes.** The post-deploy smoke set is the
  skeleton path end to end: OTP issue and verify against the real gateway,
  authenticated lens resolution, one read of a fee cycle, and a health endpoint
  reporting database connectivity and applied migration revision. Smoke failure
  triggers an immediate tag rollback, not an investigation on a live system.
- **The SMS cost circuit-breaker is a deployment concern** [D-33]. The global
  daily ceiling, its per-number and per-IP sub-ceilings, and the alert must be
  live and verified in staging before the auth slice reaches production.
  Non-production environments hold the gateway's test or sandbox credentials.

### Dependency locking — reconciled 2026-10-22

**The practice stands unchanged and becomes work in the next unit.** The
2026-10-16 text read:

> Dependency resolution is locked on both surfaces, because otherwise the
> scanners scan a version range rather than the build. `uv.lock` (or a
> `requirements.txt` compiled by `uv pip compile`) for Python; Gradle dependency
> locking plus `dependencyVerification` checksums for Kotlin. The checksum
> verification is the only control we have that detects a tampered or substituted
> artifact in the Gradle supply chain, and it costs one generated file.

None of it exists. Confirmed by direct check at commit `4e4b4d4`: no `uv.lock`,
no `requirements.txt`, no `gradle.lockfile`, no
`gradle/verification-metadata.xml`, no `dependencyLocking` call in any build
script. Terraform is the one properly locked surface, and `infra/versions.tf`
states the same reasoning the other two surfaces do not act on.

**The drift is measurable today, not hypothetical.** `pyproject.toml` asks for
`mypy>=1.11` and the installed version is **2.4.0** — a major version the
declaration admits and nobody chose. `fastapi>=0.115` resolved to 0.143.5,
`sqlalchemy>=2.0` to 2.1.5. Two installs a month apart produce different builds.
`pytest-mock` 3.14.1 is installed and undeclared, and on an unlocked project
there is no way to tell from the repository whether that is ambient or a real
undeclared dependency.

**Worse than the absence is the label.** `.github/workflows/check.yml:88` is
headed `# Step 2. Lockfile verification, Python side.` and its body is
`python -m pip install -e ".[dev,api]"`, an unpinned resolve. A label describing
a control that does not exist is worse than no label, because the next reader
ticks the box. On a solo build the next reader is the same person six months
later, with no colleague to contradict them.

**Cost to close now**: small. `uv pip compile` produces the Python pin file and
the CI step becomes a real install from it; `dependencyLocking` plus
`./gradlew dependencies --write-locks` and
`--write-verification-metadata sha256` produce the two Gradle files. Measured in
hours, not days, and it is almost entirely generated rather than authored. The
one judgement call is how often the lock is refreshed, which the weekly grouped
update PRs below already answer.

**Cost to leave**: it compounds in two directions. The build becomes
less reproducible with every dependency added across six units, and — the
decisive one — **it nullifies the CVE scanning below before that is even
built.** A scanner pointed at `mypy>=1.11` reports on a range; a scanner
pointed at a lockfile reports on the build. Closing the CVE gap while leaving
this one produces findings nobody can act on and a release gate that blocks on
fiction.

**Assigned to: before D1**, and before the CVE work, because it is that work's
precondition. **Recommendation: this becomes work.**

### Dependency CVE scanning — reconciled 2026-10-22

**The practice stands unchanged, its per-push half becomes work now, its
release-gate half lands with D6.** The 2026-10-16 text specified two speeds:

> Secrets (Gitleaks) and dependency-lockfile or checksum-verification failures
> **block every push**, with no severity threshold and no exceptions. Dependency
> CVEs **annotate on every push** at every severity as a PR comment, and **block
> at the release gate**, where each Critical and High is either fixed or carries
> a dated written exception in a committed `.security-exceptions.md`; an expired
> exception fails the release gate.

The reasoning given for two speeds rather than one hard gate remains exactly
right and is the reason not to simplify this now: a solo developer who hits an
unfixable transitive Critical mid-Bolt, with no triage path and no second
reviewer, bypasses the gate once, and after one bypass it is decoration.

**Nothing exists.** No Dependabot config, no `pip-audit`, no Trivy, no
`osv-scanner`, no `gradle dependencyCheck`, no `.security-exceptions.md`.
Confirmed by direct check. Nothing in this repository would notice a known CVE
in a direct or transitive dependency, on either surface, at any point between
commit and store. The `.security-exceptions.md` absence is at least internally
consistent: nothing produces findings to except.

The practice's own half is partly built and built well. **Gitleaks is present,
blocking, and guarded** by a step asserting the clone has at least two commits —
because Gitleaks reports "no leaks found in partial scan" after reading zero
bytes in a shallow clone. That is the project's defining habit working
correctly. The lockfile-failure half of the same blocking rule has nothing to
fail, per the gap above.

**Cost to close now**: small for the per-push half. `pip-audit` on the compiled
pin file and `osv-scanner` on the Gradle lockfile are each a CI step; Dependabot
is a config file, and the practice already specifies weekly grouped-by-ecosystem
PRs with the security channel left immediate, which is the setting that keeps
the backlog readable for one reviewer. The release-gate half needs the
`.security-exceptions.md` format, the expiry check and the Trivy pass, which is
genuinely D6 work and belongs there.

**Cost to leave**: this is a children's-data application [RC-1, RC-2, RC-3]
going to a Play Families track, handling phone numbers, attendance and marks. A
known-vulnerable transitive dependency reaching the store is the failure mode
with the worst consequence in the product, and it is the one failure mode the
project currently has no instrument for. Play's pre-launch report is the only
net, and the practice already names why that is not a control: by the time it
fires, the dependency is in the build.

**Assigned to: before D1** (per-push annotation, Dependabot, after lockfiles
land), **D6** (release-gate blocking, `.security-exceptions.md`, Trivy,
backend SBOM). **Recommendation: this becomes work**, sequenced after the
lockfiles.

### The rest, unchanged

- **An SBOM per release build** (Syft), attached to the Play release record. Not
  a merge gate. *Built for Android; the backend image has none. The backend half
  lands with D6 alongside Trivy.*
- **Dependency update PRs are weekly and grouped by ecosystem**, with the
  security-only channel left immediate.
- **Secrets never enter the repository or the image.** Environment variables in
  Phase 1, **SSM Parameter Store `SecureString`** in Phase 2. Each of the three
  named secrets — gateway credentials, JWT signing key, database URL — has a
  written, **exercised-once** rotation runbook. We do not mandate a rotation
  schedule; nobody solo keeps one, and an unkept schedule is worse than none.
- **Secrets leak through logs more often than through repositories.** Gateway
  request bodies are never logged at any level. The OTP never appears in any log
  line. Database URLs are redacted in connection-error output. Exception
  tracebacks are never returned to a client. Every error log carries the request
  or correlation id and **never** a phone number, an OTP or a token.
- **Production access is named, logged and bounded.** Production database access
  is via a named non-superuser role, never the application's own role; every
  interactive production session goes through a wrapper logging session start,
  the person and the stated reason to an append-only location; and **no
  production query result containing child-identifying data is copied into a
  local file, a chat, or an AI tool context.** That last one is a real exposure
  path in an agent-assisted build.
- **An append-only authentication audit log**, holding OTP issued, verify failed,
  verify succeeded, refresh rotated and refresh reuse detected, plus every
  interactive production database session. The audit log itself holds no OTP, no
  token and no child name. *Built at B3.*
- **One scripted DAST pass before the Play internal-track promotion**: an OWASP
  ZAP baseline scan against the staging host, driven from the committed OpenAPI
  3.1 schema. Trivy on the release image at the release gate. *Both absent;
  assigned to D5 and D6 respectively by the delivery plan.*
- **Play releases are their own cadence.** The AAB goes to an internal track
  first, then closed testing [OC-5]. The Data Safety form, the privacy policy,
  the Families target-audience declarations and **both account-deletion paths**
  [TC-19] are release-blocking V1 deliverables rather than follow-ups. Play's
  pre-launch report is the final net, never the control.
- **Client and server version independently and must stay compatible.** `/v1/`
  endpoints stay additive and the app handles unknown fields rather than failing
  to parse [D-26]. *CI authenticates to AWS by OIDC, not long-lived keys —
  verified built.*

---

## Code Style

We defer to committed tool configuration rather than to review preference. The
rule is that style is settled by a file in the repository, so review spends
itself on structure instead [OC-6, D-45].

### Backend (Python 3.12)

Unchanged and, on the evidence, working. Ruff (format and check) configured in
`pyproject.toml` with its rule sets named rather than defaulted —
`E,F,W,I,UP,B,ASYNC,S,DTZ,BLE,D,RUF`, with `PLR2004` scoped to the money and fee
modules and `"tests/**" = ["S101"]` present from the first commit. Ruff's `S`
ruleset is our SAST tool. Line length is **88 characters**, a deliberate
project-level departure from the user's global Python standard of 79, recorded
so it is not later mistaken for an oversight. Sphinx-style docstrings on every
module, class and function, enforced by Ruff's `D` rules across the whole
backend. Type hints mandatory on all parameters and return values.

*Verified 2026-10-22: `ruff check` clean, `ruff format --check` clean across 135
files, `mypy app` clean across 65 source files. Seven suppressions across `app/`,
each annotated. Zero `TODO`, `FIXME`, `HACK` or `XXX`. This section needs no
change.*

**Type checking: `disallow_untyped_defs = true` globally, with three strict
islands** — `strict = true` plus `disallow_any_explicit = true` on
`app.money.*`, `app.authz.*` and `app.schemas.*`; `warn_unused_ignores`,
`warn_redundant_casts` and `check_untyped_defs` globally.

> **Drift, 2026-10-22 — `app.authz` is a declared strict island and was never
> configured.** `pyproject.toml` configures `app.money.*` and `app.schemas.*`
> only. The comment above the `app.schemas` override says `app.authz.*` "stays
> unconfigured until U3 creates its resolvers, on B1's same reasoning" — and U3
> shipped: `app/authz/resolve.py`, `summary.py`, `annotations.py` and `rls.py`
> all exist. Deferring was correct, because an override naming a module that
> does not exist is dead configuration; the follow-up simply did not happen.
> The practical gap is small — `disallow_untyped_defs` is on globally and `mypy
> app` is clean — but `strict = true` adds `disallow_untyped_calls`,
> `no_implicit_reexport` and `warn_return_any` on the module that decides
> authorization, and D1's acceptance work extends exactly that module.
> **Effort: XS, one override block. Assigned to: before D1.** This is the same
> class of failure as the three large gaps, in miniature: a deferral with a
> stated trigger and nothing watching for the trigger.

**The strict region must not import the un-strict region.** `app.money` depends
on nothing but `decimal` and its own value types. `app.authz` depends on
repository *protocols*, not implementations.

### Money as a type, on both surfaces

Unchanged. **Money is a type, not a number.** In Python a frozen value object
wrapping a `Decimal` with BDT implicit: no `__float__`, no `__int__`,
construction from a float raises, `Decimal(<float>)` banned, `__add__` and
`__sub__` accept only `Money`, multiplication is the named `apply_rate` so no
anonymous rounding, division is not exposed (`Money.allocate(n)` when a
requirement needs splitting), `ROUND_HALF_UP` declared once, quantized to 2dp at
construction, `Money.ZERO`, `Money.sum`, `is_zero()`/`is_positive()`, and
`Money.format(locale)` so the server decides digit rendering under Bangla
locale. The module owns both chokepoints: one Pydantic annotated type reused by
every schema, and a SQLAlchemy `TypeDecorator` mapping `Money` to
`NUMERIC(12,2)`. In Kotlin, `Money` is a value class with a serializer that
reads **only** a JSON string and rejects a JSON number.

The import boundary is checked by two independent mechanisms pointing in
opposite directions: Ruff `flake8-tidy-imports` banned-api on raw `decimal`
outside `app/money/**`, and a pytest AST walk asserting `app.money` imports
nothing from `app.api`, `app.db`, `app.repositories`, `app.authz` or
`app.schemas`.

*Verified 2026-10-22: all of it built, both mechanisms present from the first
commit with fixtures proving each fires, and the money module at 100% branch
coverage. The strongest-built part of the codebase.*

### Authorization: every endpoint names its lens

Unchanged. The lens is a dependency that returns the value the handler needs, so
the handler cannot compile a query without it. A route-enumeration test asserts
every route resolves a lens, with `PUBLIC_ROUTES` an explicit frozenset, walking
`route.dependant` recursively and matching on the dependency's **return
annotation being a `Lens` subtype** rather than on a function name. Response
schemas are parameterized by lens type, so a teacher-lens endpoint returning a
`StudentPrivateResponse` is a mypy error. Request-scoped memoization is
permitted; cross-request caching is forbidden.

> **Drift, 2026-10-22 — the `PUBLIC_ROUTES` comment states a count the frozenset
> no longer matches.** `app/contract/routes.py:33-49` reads "Exactly five, and
> the count is asserted" and the frozenset holds six, two of them
> `("GET", "/account-deletion")` and `("POST", "/account-deletion")`, for which
> **no handler registers either path anywhere.** Nothing is reachable, so this
> is not an authorization hole; it is pre-declared D6 scope. Two things follow
> and both are worth recording: the allowlist is currently wider than the
> application, and **where a comment states a number, the number is a claim** —
> and this one is now false with nothing checking it. **Effort: XS. Fix the
> comment before D1; D6 lands handlers against the entries that already exist
> rather than adding new ones.**

### Layer boundaries: the API returns decisions, not inputs to decisions

Unchanged, and it carries more weight in D1–D6 than it has so far, because every
remaining unit ships screens. The checkable form is **"if the client is
comparing a domain value, the server should have sent a decision"**, and the
five erosion paths it prevents are: badge and empty-state logic in composables;
client-side filtering or sorting of a domain list; Room as a shadow model with
derived fields; validation duplicated and then diverging (client-side validation
is format-only, never policy); and the lens hint shaping more than navigation.

D3's fee status and D5's cross-batch dues are the two places this will be
tested hardest: `if (balance > 0) "Due" else "Paid"` is a business rule about
what counts as due, wearing presentation's clothes, and the dues list membership
is a server decision driven by outstanding balance rather than active status.

### Error handling

Unchanged. A closed five-class exception hierarchy — `ValidationError`,
`AuthorizationError`, `ConflictError`, `TransientError`, `FatalError` — where
**retryability is a property of the error class, not a judgement at the call
site**, mapped to responses by one FastAPI exception handler. One error envelope
carrying `code`, a server-provided `retryable` boolean, and `message_key` rather
than `message`, because a server-sent English string cannot be localized by the
client in a Bangla-first UI.

Per-boundary rules stand: the SMS gateway attempts a send **once with no
automatic retry**, records a timeout as `unknown` rather than `failed`, and
treats a ceiling breach as a `ConflictError` not a `TransientError`; the database
has three cases, where an `(enrollment_id, period)` constraint violation is the
success path, a serialization failure is a bounded transaction retry and a
connection failure fails fast; FCM is best-effort, dispatched after commit, and
its failure is **logged and not surfaced** — the stated exception to "silent
failures are not acceptable". Bare `Exception` is caught in exactly two places.

> **Note, 2026-10-22 — the envelope is published and referenced by no
> operation.** `app/main.py:144-182` injects `ErrorEnvelope` and `Money` into the
> generated document explicitly, because FastAPI emits a component only when a
> route references it. The code is honest about being a stopgap. The effect is
> that a client author reading `openapi.json` sees the envelope defined and
> learns from no operation that a 403 or 409 returns it — and a ZAP pass driven
> from that schema would not know which error shapes to expect. **D3 is the
> first unit with declared error responses and is the natural place to close
> it**, which turns the stopgap into a no-op rather than a lie, as its own
> comment anticipates.

### Android (Kotlin) — the toolchain gap, reconciled 2026-10-22

The conventions stand unchanged: **conventional, well-documented Google choices
by default, with project constraints outranking the sample** where they conflict
(no Firebase Analytics or Crashlytics [TC-3, TC-6, D-37]; decimal money, not the
sample's `Double` [TC-7]; no offline-first local write path [TC-8, D-9]), with
the sample repository and commit pinned. **File organization is by feature with
a layer split inside each feature**, as `feature/*` plus `core/*`, kept as
packages in **one** Gradle module for V1 rather than the sample's forty modules.
**The ViewModel maps a server response to a UI state data class** and that
mapping is where UI-state decisions live; a composable receives a UI state and
renders it with no conditionals depending on domain values. Money is the `Money`
value class. **No hardcoded user-facing strings**; `strings.xml` with Bangla and
English from the first screen. **The forbidden-identifier set is enforced by two
failing build gates** — the merged-manifest permission allowlist asserting the
absence of `AD_ID`, and the minified-release DEX scan for the ten identifiers —
with Android Lint's `HardwareIds` raised to `fatal` as a complement. **An SDK
admission note per new third-party dependency.**

*Verified built, and built well: the structure is exactly as specified, the
release gates are the strongest work in the repository (the manifest gate parses
XML after an earlier version matched its own comment; the DEX scan matches whole
identifiers after a bare `contains` flagged `getSerialization`; it scans for the
lowercase value `android_id` after a planted read passed), both string bundles
are complete at 53 strings, and `MessageKeyCoverageTest` keeps the client's keys
in step with the server's.*

**And the entire quality toolchain is absent.** Confirmed by direct check across
every `.kts`, `.toml`, `.yml` and `.properties` file at commit `4e4b4d4`:

| Tool | Practice says | Built |
|---|---|---|
| **ktlint**, `official` style | required | **absent** |
| **spotless** (runs ktlint; also covers `strings.xml` and the Gradle files) | required, "decided at project setup, because the first reformat is a whole-module diff" | **absent** |
| **detekt** (`Double`/`Float` ban in `core/model`) | required as the money backstop | **absent** |
| **`lint.xml`** raising `HardwareIds` to fatal | required as a complement to the DEX scan | **absent** |
| **Kotlin coverage report** with a no-decrease ratchet | required from the first Android Bolt | **absent** |
| **Compose screenshot tests** at the longest Bangla string | one of two named verifiers | **absent** |

`android/build.gradle.kts` declares four plugins: the Android application
plugin, Kotlin Android, Kotlin serialization and the Compose compiler. No
quality plugin of any kind.

**The consequence the practice itself predicts.** This lands on the surface the
practice names as the thinnest-reviewed [OC-3], and it produces one concrete
hole beyond style: **the release gates are the only Kotlin checks and they run
on `bundleRelease` only.** Between commit and release, nothing checks Kotlin
except `testDebugUnitTest`. A `TelephonyManager` reference — forbidden by
[TC-4, D-35] and by a `NEVER` in `project.md` — can sit on `main` through every
PR and be found at release time, on the build that was about to ship. The
practice named Semgrep for exactly this case and Semgrep is also absent; of the
five project-specific rules Semgrep was to encode, four turned out to be
enforced by something stronger (Ruff banned-api, the pytest import gate, the
route-enumeration gate, and the Kotlin value class), and the fifth is this one.

**Two signs the team already knows.** `NoFloatingPointTest.kt` is a hand-written
file-scanning backstop whose docstring says "Detekt will carry the same rule
once it arrives with the packaging Bolt. This test exists now because the rule
is needed from the first commit that ships a model class, not from the Bolt that
happens to install detekt." That is the right instinct and it is also the gap in
one sentence: the rule was needed from the first commit, the mechanism was
assigned to a Bolt, and the Bolt did not arrive. Separately,
`BatchesViewModel.kt` imports `AuthResult` from `feature.auth` — a cross-feature
import of a result type that belongs in `core`. Trivial today, and it is the
shape that spreads once a dozen features need the same type, with nothing in the
build to stop it.

**Cost to close now**: small, and smaller than it will ever be again. Spotless
with ktlint `official` is a plugin block and a config stanza; detekt is a plugin
and a short rule file; `lint.xml` is one `<issue id="HardwareIds"
severity="fatal"/>` element; Kover is a plugin line plus a report task. The one
real cost is **the first `spotlessApply`, which reformats the whole module** —
32 Kotlin source files today. That is a reviewable one-commit diff now. After
six more units of screens it is a diff nobody reads, which is precisely the
argument the 2026-10-16 practice made for deciding the formatter at project
setup.

**Cost to leave**: it compounds with every remaining unit, and all six ship
Android screens — D1 signup and acceptance, D2 roster and guardian view, D3 fee
and payment screens, D4 attendance and marks, D5 insights, D6 deletion flows.
This is the single clearest sequencing fact in this run: **the Android toolchain
is cheapest to close before D1 and most expensive after D6.** Leaving it also
leaves the `TelephonyManager` commit-time hole open across every one of those
units, on a children's-data app whose Families declaration depends on that rule
holding.

**Assigned to: before D1**, as one small toolchain change landing ahead of the
unit rather than inside it, so the whole-module reformat is its own reviewable
commit and does not hide inside a feature diff. **Recommendation: this becomes
work.**

### Both surfaces

Unchanged. **Deletion semantics are written down per table and the privacy
policy is generated from them** — hard delete, anonymize-in-place, or
retain-with-stated-basis, decided at Domain Design and asserted by a test, with
the policy text generated from the dispositions rather than written independently
of them. **A stated retention period per data class, with a scheduled purge**,
starting with the auth records. **Commits are conventional-commit shaped** so
the Bolt squash commit and release notes can be generated. **The generated
OpenAPI 3.1 schema is committed**, so a contract change shows up as a reviewable
diff, with the schema-diff gate keeping the committed copy current. *Both of the
last two verified built.*

> **One environment note, 2026-10-22, not a practice change.** The project
> targets Python 3.12 everywhere — `requires-python`, Ruff `target-version`,
> mypy `python_version`, the Docker base, and the CI pin — while the local
> interpreter is 3.13.2. The full suite passes locally; a 3.13-only behaviour
> would pass locally and fail in the container. Worth knowing, costs nothing to
> state, and a matching local interpreter is the cheapest fix.
## Forbidden

<!-- Team-specific forbidden patterns -->

## Mandated

<!-- Team-specific mandates -->

## Corrections

<!-- Self-learning loop appends here. -->
- A reviewer's prescribed fix is verified before it is applied, separately from the finding that prompted it. A finding can be correct while its suggested remedy is wrong: here the finding was real and the prescribed patch failed four of twelve cases, which would have replaced one wrong invariant with another that the next reader trusted more for having been through review. (learned 2026-10-17) <!-- cid:261016-shikhokplus-tuition-app:domain-design:06f1c1a568bc474b6ba154903a4413559be52021ab85950cad1d684ad82c5378 -->
- When a Unit must read a table another Unit owns, the fix is schema scope on the reading Unit, not a dependency edge. The reading Unit's migration creates the table empty and never writes it; the owning Unit keeps its behaviour and extends its columns. An edge in the reverse direction of an existing one makes the graph cyclic while describing nothing real. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:units-generation:044413d7483d15f68f3af586c5c68eda5fe571e62b4c7ce1e1c73bcb0fac1c68 -->
- A Unit boundary is a delivery boundary, not a component boundary. Splitting one component across two Units does not reopen a component-boundary ADR, but the decomposition must say so explicitly and name why the mechanism the ADR protected is not duplicated. Left unsaid, every split reads as a contradiction of an ADR to the next reader. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:units-generation:c81072067c0291f0b17dc5ebdb1f1fe4f37ab0e1703fd5dc819180b77d99ab45 -->
- A claim that a Unit runs standalone must answer the schema question explicitly, not infer it from data-emptiness. Empty is not absent: a query against a table that does not exist fails, so every table a Unit reads must be created by some migration that runs no later than that Unit. This nearly shipped a walking skeleton that could not pass its own verification command. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:units-generation:b52a9f08ecbb94c7707018c016860561b1d09086aa3485f33fd40d2774b4a360 -->
- Read the format contract before writing a file a tool will parse, rather than inferring it from a rejection message. The reviewer protocol states its findings-table contract explicitly, including that New-findings tables carry no ID and no Status column because the engine assigns identifiers itself, and that oversized cells break the parse. Guessing cost four attempts where reading cost one minute. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:units-generation:161971787c361e9ca63a13fe1d1446bb5f9fadd0e23dda92aadff2331ece92a1 -->
- In a modular monolith, a boundary is a contract when a violation fails CI, not only when a wire is involved. Import boundaries, serialization chokepoints and schema-level CI gates are specified as contracts; in-process edges that carry no enforced rule are enumerated once with the reason rather than each given a spec that describes nothing. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:contract-design:5e74270cfb6d6070acf32eca24ce2a748d0e234a914f174803ae42d01141325a -->
- An open question that carries a proposed default is a decision wearing a question's clothes. The test is whether the answer needs judgement or evidence nobody has yet, or merely needs someone to commit. If the latter, decide it: leaving it open makes every downstream artifact that depends on it provisional, and flagging is cheap enough to become a way of avoiding the decision. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:contract-design:b5f6f40dc4b34db6ecfd3f7cb6ce8035154f722582159aff80318879fc745ef5 -->
- When two sections of one specification give instructions that appear to conflict, reconcile them explicitly rather than leaving both correct-but-unreconciled. A reader follows one section, not the whole document: the error taxonomy marking a 401 non-retryable while the auth section instructed a replay was self-consistent only to someone who read both. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:contract-design:4a46177fb782fc56359ca151b64c8ab7aedb0892604a47a7068a5ea6ec39426b -->
- When a tool rejects a file it parses, read the parser's implementation under .claude/tools/ rather than inferring the contract from the error message or the protocol prose. The reviewer findings parser validates each Prior-findings row for an ID matching R-<digits> and a Now value from five literal words, so a placeholder row fails and an empty table is correct for a first review. Guessing cost six attempts across two stages. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:contract-design:4142564f324459c38a507d91413c404b461218af910d17b8dbdedc1a3e0bed07 -->
- A dependency DAG records data and call dependencies; a tooling prerequisite is a third kind it does not express. Before sequencing, check whether any Unit's stated obligation is dischargeable only by a harness another Unit owns. Here the mid-class latency obligation was dischargeable only by a Macrobenchmark whose harness belonged to a different Unit, which settled that Unit's placement on firmer grounds than the scheduling argument. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:delivery-planning:af57f14cfdbf04ba6a02690ed176932ee26c6af5ed1162f529376232ec392b22 -->
- Do not apply a weighted scoring model where the dependency graph forces most positions, every item is Must Have so cost of delay is constant, and job sizes span one step. The scores would dress up a decision the geometry already made. Record the decision not to score, with its reasoning, rather than omitting the model silently — a silent omission reads as an oversight. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:delivery-planning:0bb18777367093e32bb9271a65ec8b3ef41aca8c7a2a25c1011dfe0ca1a862c0 -->
- When a Unit is both topologically terminal and release-blocking, resolve the tension by splitting what it contains rather than moving it. The enforcing mechanism moves to the earliest Unit that can host it, creating a per-Unit obligation checked from that point; what genuinely cannot be done until the end stays at the end. Name the scope this adds to the earlier Unit rather than absorbing it quietly. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:delivery-planning:422b9ef7a0a1ad0ebee6371c69180a07ec5ff3806e7af25f8851e27900d54ba9 -->
- Re-ask an affirmed practice when the thing it names has changed shape. A practice gated Construction through "the payment slice" when that slice was a proto-Unit; after decomposition it was a differently-numbered Unit. Translating silently would have been a guess carrying a practice's authority. Asking cost one question and removed the ambiguity permanently. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:delivery-planning:c1fb9aaaf6b476d1a2d49c85e400da3d2d46fef64ae8915e7d747d639310fd92 -->
- The carry-forward illustration reads: carrying 1000 into a second 1000 charge gives 2000 owed two-sided and 3000 one-sided. An earlier form of this rule paired 2500 against a true 1500, which reproduces under no implementation — 1500 is the two-sided answer to the 500-carried case and 2500 is the one-sided answer to neither, so the pair mixed two cases and made the rule's own example unfalsifiable. The two-sided design it illustrates was always correct; only the figure was wrong, and it had propagated to four files before anyone computed it. A worked example asserted rather than computed is the exact failure the quality bar exists to catch, and it was committed while writing the rule that warns against it. (learned 2026-10-18) <!-- cid:261016-shikhokplus-tuition-app:functional-design:47085c395af7fd6e24585c4ac388d216c2b53f8dd306ff9270afbce8a1627b68 -->
- When a state is renamed, collapsed or added, sweep every artifact for criteria naming the OLD state, not only the stories about the change. Here dormant collapsed into pending, and the most consequential miss was a removal criterion in a different story group: permitting removal only while dormant forbade removing any seat a teacher creates, which blocked the recovery path from the exact exposure the change existed to close. (learned 2026-10-22) <!-- cid:261022-remaining-slices:user-stories:d997093953a4dfb620fb34d38259976fee88b9562c7039353ab51063a00cbfb1 -->
- A table header asserting that figures were measured is itself a claim, and a wrong number whose verdict happens to be right is invisible. Every contrast ratio in this stage's first accessibility table was estimated under a header reading "Measured against the tokens, not estimated"; all twelve were wrong and all twelve verdicts still passed, so nothing surfaced it until someone recomputed. Compute the number or do not state it. (learned 2026-10-22) <!-- cid:261022-remaining-slices:refined-mockups:2c9313eb38c40c45bd9bc14e511294f170bd0df8065f9aa540559be3abb0e5ee -->
- When a rule differs by role, copy written once serves one role and misleads the other. One decline confirmation saying "the fee stops" was shown to students and guardians alike, while the rule says a guardian's decline leaves the student's obligation intact: the screen told a guardian a debt was cancelled when it was not. A role-dependent rule is checked against every screen it reaches, not only the screen where it was written. (learned 2026-10-22) <!-- cid:261022-remaining-slices:refined-mockups:bef8d0b28274cd52a75326d662625489282787bc57180d19acf803c495d11c55 -->
- Adding a column is not adding a behaviour. Name the queries that must start reading it, because the ones already granting access go on granting it on the old evidence. Here two separate statements in different modules granted lenses, GET /v1/me read the one not examined, and the acceptance model would have shipped as columns nobody read with the exposure it exists to close still open. (learned 2026-10-22) <!-- cid:261022-remaining-slices:domain-design:3c3b494c47833f64b0b1db39dde8aab988924917c96f495d52374eff53ad62f0 -->
- Before asserting how a change fits built code, read the code. Two claims in one stage's first draft were confidently wrong in the same way: a plain column default would have withdrawn a working lens from every signed-in student, and a per-enrollment grant was described as a fourth scalar in a query that returns scalars for one account. (learned 2026-10-22) <!-- cid:261022-remaining-slices:domain-design:f3a1c50025237bc181e577fce67b7b8c0bae2c757f7c31c1cf88f32cdd6350d7 -->
