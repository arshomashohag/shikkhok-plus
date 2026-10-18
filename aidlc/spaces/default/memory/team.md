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

**Construction is gated through the payment slice, then autonomous.** We review
each checkpoint up to and including PU-6, because the money and privacy surfaces
are where an unreviewed run of plausible-looking commits is most expensive to
unwind and the user is the only reviewer. From PU-7 onward Construction
continues automatically. Plan Approval, summary confirmation, verification
command selection and any failure remain human stops regardless.

Single trunk even once we have more than one environment: releases are gated by
tag and by environment-specific configuration, never by a long-lived release
branch.

---

## Walking Skeleton

**Yes — we build a thin end-to-end slice first.**

A walking skeleton here means: a Compose screen that calls a real FastAPI
endpoint, which reads a real PostgreSQL row, through real OTP-issued
authentication, running against the real Phase 1 Lightsail host. Not a mock at
any layer. The point is to prove that the pieces connect before any feature
depends on their connecting.

The skeleton is **PU-1, authentication and identity** — it is already slice 1
of the dependency order [intent-backlog], and everything else depends on it, so
there is no cheaper candidate. Specifically the skeleton proves:

- A typed phone number reaches the OTP issue endpoint, an SMS arrives through
  the real gateway, and the verify endpoint returns a working access token.
- An authenticated request resolves its role as a **computed lens** rather than
  a stored field [D-2, TC-11], which is the single most structurally unusual
  decision in the system and the one most likely to be mis-implemented quietly.
- The Android client holds a token, refreshes it, and renders a server-computed
  response with no business logic of its own [TC-9, D-31].

**This skeleton is deliberately larger than a minimal connectivity proof, and we
should be honest that it is.** All seven OTP abuse controls carry tests inside
the skeleton Bolt, before anything else is built. The reasoning is that these
controls live in PU-1 by architecture, they are the first thing built, each has
an explicit numeric threshold and is therefore mechanically testable, and
per-SMS billing makes abuse a direct attack on the project's wallet [D-33]. The
alternative — ship PU-1 to closed testing with untested rate limits and a live
SMS bill — is the worse trade. The seven, each with its adversarial test:

- 4th OTP request for one number inside an hour is refused; 6th inside a day is
  refused.
- 11th request from one IP inside an hour is refused.
- An OTP presented at 5m01s is refused; an OTP that verified once cannot verify
  again.
- The 6th verify attempt against one OTP is refused and the OTP is dead
  afterwards.
- The stored OTP value does not equal the transmitted one, so hashing is real
  rather than intended.
- Issue responses for a known and an unknown number are byte-identical. We
  assert the **structural** property — that the unknown-number path performs the
  same hash computation rather than returning early — and not a wall-clock
  bound, because a millisecond assertion is flaky and will be deleted the third
  time CI fails on it.
- The global daily SMS ceiling is enforced and its alert fires.

Two consequences we accept with that scope:

- **The rate-limit counters are datastore-backed, not per-process.** A
  per-process dictionary is the obvious implementation, it passes every test, and
  it silently stops working the moment there are two workers — which Phase 1 has,
  because a single Lightsail host still runs multiple Uvicorn workers. That is a
  correctness bug presenting as "the limit works in testing", so the datastore
  requirement is part of the skeleton rather than a later hardening.
- **The global ceiling needs a tier beneath it.** A global-only daily ceiling
  converts a financial attack into a total lockout of every legitimate teacher
  for the rest of the day. We add a per-number and per-IP-prefix sub-ceiling
  beneath the global one so the breaker degrades rather than cliff-edges, and we
  define what a legitimate user sees when it trips and whether any path to log in
  remains.

We also pull three things that are not strictly identity into the skeleton,
because deferring them is more expensive than carrying them:

- **One Alembic migration applied against a real Postgres**, so the migration
  path is proven before the schema is large enough to make a mistake expensive.
  The test container migrates with Alembic from zero rather than loading a schema
  dump, which gives the migration path continuous exercise at no extra cost.
- **Both language bundles present on the first screen** [TC-15, D-43]. Bangla
  text that breaks a layout is a per-screen problem; discovering it on screen one
  is how we avoid discovering it on screen forty.
- **JWT `kid` support and two valid verification keys.** Rotating the signing key
  without them force-logs-out every holder of a 30-day refresh token, at exactly
  the moment rotation is needed. It costs almost nothing now and is a mass-logout
  incident to retrofit later.

**The toolchain is sequenced so the skeleton does not become a toolchain Bolt.**
Skeleton-time: Ruff with its selected rule sets, mypy on the money module,
pytest with testcontainers, Gitleaks as a pre-commit hook and a CI job, and the
dependency lockfiles. Arriving with the Bolt that first needs them: Schemathesis
and the OpenAPI schema-diff gate, detekt, the Kotlin coverage report, the
manifest allowlist and DEX scan (the first Android release build), Syft, and the
ZAP baseline pass.

The skeleton is verified by the intent's recorded Construction Verification
Command, which must demonstrate the real end-to-end result on a device or
emulator against the real backend — not a passing test suite, and not a design
review. It then stops for the human's skeleton checkpoint approval before later
Units start.

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
  test-first are actually met. `custom` is the accurate value.
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
  and not by active status, so students who left owing money still appear.

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
  membership, so line coverage on it is close to meaningless.
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
  add one property-based test (Hypothesis) on the invariant that holds across all
  of it: for any sequence of charges, approvals, carry-forwards and waivers,
  `charged - received - forgiven == outstanding`, and `outstanding` never goes
  negative. That invariant catches the class of defect no enumerated example
  will.
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
- **Test types by layer**: pytest for backend unit and integration tests, with
  integration tests running against a **real PostgreSQL 16** container via
  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,
  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and
  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin
  ViewModel and repository tests, targeting the response-to-UiState mapping
  function rather than an untargeted "the ViewModel". Compose UI tests for the
  OTP entry path and the mid-class attendance path.
- **Database tests connect as a restricted non-superuser role.** PostgreSQL
  documents that superusers and table owners bypass row-level security entirely
  [pg-rls], and the default test-container connection is `postgres`, a superuser.
  A privacy-boundary suite run as superuser passes identically whether the policy
  is correct, broken, or entirely absent — so the strongest test obligation we
  have would certify nothing. Integration tests therefore connect as the same
  restricted role the application uses, and a **meta-test asserts that
  `current_user` is not a superuser and that row-level security is in force**
  (`row_security` on, policy present) before the privacy suite runs.
- **Privacy boundary tests are adversarial, and the API-level half is a
  schema-wide invariant.** No teacher-lens response schema may contain any field
  in the owner-private profile set, enforced by iterating the generated OpenAPI
  schema rather than by remembering to write a test per endpoint — per-endpoint
  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking
  about it. The probe suite explicitly covers the IDOR shape: teacher A
  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a
  student requesting a fee cycle not their own. That is the vulnerability class a
  scanner cannot find and the one most likely to exist, because finding it
  requires knowing the intended policy.
- **Schemathesis validates conformance, not correctness, and never counts as
  privacy coverage.** A teacher-facing response schema that wrongly includes
  profile fields is perfectly *conformant*. We keep Schemathesis for what it is
  good at — unexpected 500s, type and required-field drift, auth present on every
  route — and we add the check it cannot provide: **an OpenAPI schema-diff gate**,
  where the committed schema must match the generated one and CI fails if they
  diverge. A stale committed schema is worse than none, because the contract tests
  then pass against fiction.
- **Money representation is itself a test target.** Every money value crosses the
  API as a JSON **string** [TC-7, D-20], asserted on both sides: the backend never
  emits a JSON number for a money field, and the client rejects one.
- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle
  guarantee is a database constraint precisely because application-level guards
  fail under concurrency [D-21, TC-12]; testing it by calling the job twice in
  sequence would pass against the broken implementation the decision exists to
  avoid. The test runs overlapping generations and asserts the **outcome** rather
  than the absence of an exception: after N overlapping generations exactly one
  row exists per `(enrollment_id, period)` and the ledger total is unchanged. It
  also covers the case concurrency alone misses — the daily self-healing re-run
  [PU-5.5] must be idempotent across *days*, so a cycle generated on the 1st is
  not regenerated on the 2nd.
- **Token lifecycle is tested as a state machine.** Refresh-token rotation with
  reuse detection has a security-critical failure mode: present a rotated-out
  token and the whole token family must be invalidated. Untested, this degrades
  silently into non-rotating refresh tokens, because the happy path is identical.
  We also test that refresh tokens are stored hashed, that access-token expiry is
  actually enforced, and that a 15-minute-expired token is rejected.
- **Both account-deletion paths are tested** [TC-19]: the in-app path and the
  externally accessible route. Each must assert that deletion removes what the
  Data Safety form claims it removes and retains only what the privacy policy
  discloses [RC-4, RC-5], per each table's written disposition. Deletion features
  are the ones most reliably shipped broken, because nobody tests the absence of
  data.
- **PU-3.6's mid-class speed requirement is not discharged by a correctness
  test.** A Compose UI test asserts behaviour, not latency. Either the attendance
  obligation is a **Macrobenchmark on a low-end device profile** (which also
  serves TC-17), or PU-3.6 has no automated verification in V1 and carries an
  explicit manual check in the pilot. Both are acceptable; silently using a
  correctness test to discharge a performance requirement is not.
- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:
  Compose screenshot tests at the longest Bangla string, or an explicit
  per-screen manual check. "Must not break the layout" currently has no verifier,
  and an unverifiable obligation is a wish.
- **One command, local and in CI.** `make check` or equivalent, the same
  entrypoint in both places. For a solo build this is the single most important
  property of the gate: a gate reproducible only by pushing is a gate that gets
  bypassed. The blocking suite needs no secret to run locally, which means the
  SMS gateway is stubbed in tests and the sandbox-credential question affects
  staging only, never CI.
- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if
  minutes become a real constraint. Splitting by cost is cheaper than migrating by
  platform, and the PR integration is where the only review happens. The Android
  job is split from the backend job so a Kotlin build does not gate a backend PR,
  dependencies are cached, the backend path stays under about ten minutes or it
  will be skipped, and the per-month minute budget is stated and monitored
  against [OC-4].
- **A green `main`, not just a green PR.** With squash-merge and one reviewer, the
  post-merge run on `main` is the only thing that catches a stale-base merge.
- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.
  Tests that always pass regardless of implementation are defects in their own
  right and are rejected in review.

---

- The ledger invariant for the money module's property-based test is `total_charged - total_forgiven - (total_receipt + total_credit_grant) == total_outstanding - available_credit`, with `available_credit = credit_grant - credit_apply >= 0`, `total_outstanding >= 0`, and `sum(carry_forward) == sum(carried_out)`. This supersedes the earlier `charged - received - forgiven == outstanding`, which omitted carry-forward and predated credit, and an intermediate form that omitted credit_grant from cash in. Money received as credit is money received: cash in is receipts plus credit grants. (learned 2026-10-17) <!-- cid:261016-shikhokplus-tuition-app:domain-design:6df0b3fb8b69277262b6aa832fd4ab4358c7865b045e40c93e78fa97f1d65507 -->

- Carry-forward is recorded two-sided — a `carried_out` entry relieves the originating period and a `carry_forward` entry charges the receiving one — so the two cancel at enrollment level. A one-sided carry counts the same debt in both periods: carrying 1000 into a second 1000 charge reads 2500 owed against a true 1500. A named test covers a multi-period carry, not only a single one, because a single carry can pass against a model that double-counts. (learned 2026-10-17) <!-- cid:261016-shikhokplus-tuition-app:domain-design:44c11f91434593f33b4220de52e9392af3193b382ff700d4712a14a2e53d1f85 -->

- A money invariant is verified before it is recorded as satisfied, never asserted from reasoning alone: worked cases across every ledger operation, then randomized histories composing those operations in arbitrary order. This project's identity was wrong twice before randomized testing settled it, and it is the property-based test standing behind 100% branch coverage on the money module — an unverified invariant there certifies the arithmetic it was meant to check. (learned 2026-10-17) <!-- cid:261016-shikhokplus-tuition-app:domain-design:5b3410a98e1ce3e465bc3d776f69599a1e0a35ad18c286fb10db08d25d89aa85 -->

## Guard Policy

<!-- Affirmed by the team. Mode: strict, relaxed, or off. Strict here holds for every intent, whatever one person asks in chat; relaxed or off here applies to every intent whose policy came from its scope, unless project.md or the person sets another; changing this line changes it. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

We **deploy on merge to staging**; production deploys are a separate, explicitly
triggered step. With a solo build the `org.md` default of "tech lead plus
product owner sign-off" has no meaning — the same person holds both roles — so
the gate is not an approval quorum but a **checklist the person completes**:
staging smoke passed, Alembic migration reviewed and reversible-or-forward-safe,
no open Critical or High dependency finding without a dated written exception,
and the manifest allowlist and DEX scan green on the release build.

**A staging Lightsail instance exists in Phase 1.** That takes Phase 1 hosting
from roughly USD 13 to roughly USD 25 per month against the USD 50 ceiling
[OC-4]. We pay it because staging is where a migration gets rehearsed before it
touches real teacher and child data, and there is no multi-AZ database to fail
over to if it does not.

Environment topology, matching the phased hosting decision [D-29]:

| Environment | Phase 1 (closed testing) | Phase 2 (launch) |
|---|---|---|
| Local | Docker Compose, Postgres 16 container | unchanged |
| Staging | Lightsail instance, containerized Postgres | Lightsail or small EC2, separate RDS or separate database |
| Production | — (closed testing is the audience) | Lightsail/EC2 container, RDS `db.t4g.micro`, Single-AZ |

**The budget decides the environment count, not preference.** Under USD 50/month
there is no room for three always-on duplicated stacks. Staging and production
share an instance class and differ by configuration and data, and we accept that
staging is not a performance-faithful copy of production. What staging must be
faithful about is **schema, migration path and authorization behaviour**, because
those are what a deploy can break irreversibly.

- **Migrations are forward-only and backward-compatible.** Alembic runs as a
  distinct, logged step before the new container serves traffic, never as a side
  effect of application start. A migration that cannot be rolled forward past a
  mistake is not merged. This matters more than usual because the fee model is
  known to be changing [D-18] and there is no failover.
- **The database is the thing we cannot roll back**, so it gets the
  belt-and-braces treatment: a verified `pg_dump` to S3 immediately before any
  production migration in Phase 1, and an RDS snapshot in Phase 2, with the
  restore path exercised at least once before launch. An untested backup is not a
  backup — and an unverified *upload* is not a backup either, so we assert object
  existence and non-trivial size after upload. A failed backup alerts: it is a
  fatal operational event even though no user notices.
- **Rollback is redeploying the previous immutable image tag.** Images are tagged
  with the commit SHA; `latest` is never deployed. This is also a supply-chain
  control, because it makes the deployed artifact identifiable. Recreate-style
  deployment is acceptable at this scale — 100 teachers on a single instance do
  not justify blue-green, and an ALB would consume a third of the budget before
  any compute [D-29]. We accept a short restart window and schedule production
  deploys outside Bangladesh classroom hours, because a dropped attendance write
  during a live class is exactly the failure a teacher will not forgive [D-9,
  TC-8].
- **A deploy is not done until smoke passes.** The post-deploy smoke set is the
  skeleton path end to end: OTP issue and verify against the real gateway,
  authenticated lens resolution, one read of a fee cycle, and a health endpoint
  reporting database connectivity and applied migration revision. Smoke failure
  triggers an immediate tag rollback, not an investigation on a live system.
- **The SMS cost circuit-breaker is a deployment concern, not only an
  application one** [D-33]. The global daily ceiling, its per-number and per-IP
  sub-ceilings, and the alert must be live and verified in staging before the auth
  slice reaches production. Non-production environments hold the gateway's test
  or sandbox credentials, so a staging run can never spend real money or message a
  real teacher.
- **Scanning runs at two speeds.** Secrets (Gitleaks) and dependency-lockfile or
  checksum-verification failures **block every push**, with no severity threshold
  and no exceptions: they are binary, near-zero false positive, and always
  actionable by the person who just pushed. Dependency CVEs **annotate on every
  push** at every severity as a PR comment, and **block at the release gate**,
  where each Critical and High is either fixed or carries a dated written
  exception in a committed `.security-exceptions.md`; an expired exception fails
  the release gate. The reason for two speeds rather than one hard per-push gate
  is specific: a solo developer who hits an unfixable transitive Critical
  mid-Bolt, with no triage path and no second reviewer, bypasses the gate once —
  and after one bypass it is decoration rather than a control. The exception note
  records reachability, because a High in a test-only or build-only dependency is
  not the same risk as one in the request path.
- **Dependency resolution is locked on both surfaces, because otherwise the
  scanners scan a version range rather than the build.** `uv.lock` (or a
  `requirements.txt` compiled by `uv pip compile`) for Python; Gradle dependency
  locking plus `dependencyVerification` checksums for Kotlin. The checksum
  verification is the only control we have that detects a tampered or substituted
  artifact in the Gradle supply chain, and it costs one generated file.
- **An SBOM per release build** (Syft), attached to the Play release record. Not
  a merge gate. It exists so that when a CVE lands on a shipped version we can
  answer "is it in the AAB on the store" in a minute rather than a day, which is
  what makes a post-release dependency incident tractable for one person.
- **Dependency update PRs are weekly and grouped by ecosystem**, with the
  security-only channel left immediate. Daily individual PRs on a two-language
  repo with one reviewer produce a backlog that gets closed unread.
- **Secrets never enter the repository or the image.** Environment variables in
  Phase 1, **SSM Parameter Store `SecureString`** in Phase 2 rather than Secrets
  Manager: SSM is free, and paying for rotation we have not wired up is the
  definition of a control that does not earn its place. Each of the three named
  secrets — gateway credentials, JWT signing key, database URL — has a written,
  **exercised-once** rotation runbook. We do not mandate a rotation schedule;
  nobody solo keeps one, and an unkept schedule is worse than none.
- **Secrets leak through logs more often than through repositories.** Gateway
  request bodies are never logged at any level, because a gateway call carries a
  phone number and often the OTP itself. The OTP never appears in any log line.
  Database URLs are redacted in connection-error output. Exception tracebacks are
  never returned to a client. Every error log carries the request or correlation
  id and **never** a phone number, an OTP or a token — phone numbers are
  children's-adjacent personal data under [RC-1, RC-2, RC-3], so this is a
  compliance rule rather than hygiene.
- **Production access is named, logged and bounded.** With no admin surface,
  every production operation — reading a stuck fee cycle, correcting a bad
  migration, investigating an OTP complaint — happens via SSH or `psql` against a
  live database holding children's names, attendance and marks. We will not build
  an admin surface at this budget, so instead: production database access is via a
  named non-superuser role, never the application's own role; every interactive
  production session goes through a wrapper logging session start, the person and
  the stated reason to an append-only location (`psql` with a logging wrapper and
  `log_statement = 'mod'` is enough); and **no production query result containing
  child-identifying data is copied into a local file, a chat, or an AI tool
  context.** That last one is a real exposure path in an agent-assisted build.
- **An append-only authentication audit log**, holding OTP issued, verify failed,
  verify succeeded, refresh rotated and refresh reuse detected, plus every
  interactive production database session. Not per-row access logging — that is
  disproportionate here and unaffordable in storage. But with zero audit logging
  the project cannot answer "was this child's data accessed improperly", which is
  the question both COPPA and GDPR-K assume we can answer and which a parent
  complaint will ask. The audit log itself holds no OTP, no token and no child
  name: an audit log that leaks what it audits is a common and self-defeating
  mistake.
- **One scripted DAST pass before the Play internal-track promotion**, not on
  every push: an OWASP ZAP baseline scan against the staging host, driven from the
  committed OpenAPI 3.1 schema so it exercises real authenticated routes rather
  than crawling blind, with one report reviewed by hand. Trivy on the release
  image at the release gate for base-image CVEs, not as a per-push gate.
- **Play releases are their own cadence.** The AAB goes to an internal track
  first, then closed testing [OC-5]. The Data Safety form, the privacy policy,
  the Families target-audience declarations and **both account-deletion paths**
  [TC-19] are release-blocking V1 deliverables rather than follow-ups [D-41,
  RC-4, RC-5, PU-8.7–PU-8.9]. Play review lead time is part of the release
  schedule, not a surprise at the end of it. Play's pre-launch report on the
  internal track is the final net, never the control: by the time it fires, the
  dependency is already in the build.
- **Client and server version independently and must stay compatible.** An
  installed Android app cannot be forced to update, so `/v1/` endpoints stay
  additive and the app handles unknown fields rather than failing to parse
  [D-26].

---

## Code Style

We defer to committed tool configuration rather than to review preference. The
rule is that style is settled by a file in the repository, so review spends
itself on structure instead [OC-6, D-45].

### Backend (Python 3.12)

- Formatter and linter: **Ruff** (format and check), configured in
  `pyproject.toml`. The decisive argument is not "one configuration file" but
  speed at the commit boundary: Ruff runs the whole backend in well under a
  second, which is what lets a pre-commit hook survive contact with a solo build.
  A Black-plus-Flake8-plus-isort chain is slow enough to get skipped, and a
  skipped check is not a check.
- **Ruff's rule sets are named, not left at the default.** "Ruff" without a
  selected rule set is roughly Flake8's defaults and catches almost none of what
  matters here. We select `E,F,W` (baseline), `I` (import order, replacing
  isort), `UP` (pyupgrade, keeping 3.12 idiom), `B` (bugbear — mutable default
  args are a real defect class in FastAPI dependency signatures), `ASYNC` (a sync
  SQLAlchemy call inside an `async def` silently serializes the whole event loop
  on a 2 GB Lightsail instance), `S` (the bandit subset), `DTZ` (naive datetimes
  — fee periods are calendar-month-with-clamp in a non-UTC country, and a naive
  `datetime.now()` eventually produces an off-by-one-day due date), `BLE001`
  (bare `except Exception`), and `RUF`. `PLR2004` (magic value comparison) is
  scoped to the money and fee modules only. `[tool.ruff.lint.per-file-ignores]`
  sets `"tests/**" = ["S101"]` from the first commit rather than retrofitting it.
- **Ruff's `S` ruleset is our SAST tool**, and we claim it explicitly rather than
  leaving it unconfigured: hardcoded passwords, `assert` in production paths, weak
  hashing, `subprocess` with `shell=True`, unsafe deserialization. Zero extra
  tooling and zero extra CI minutes, in a tool already chosen.
- **Semgrep carries a small set of project-specific rules.** The value is not the
  generic OWASP ruleset; it is rules encoding *this project's* invariants, which
  no generic scanner knows: no decimal arithmetic on money outside the designated
  module, no route handler without an explicit lens dependency, no
  `TelephonyManager` reference anywhere in Kotlin, no `Double` or `Float` in a
  money-carrying data class.
- **Line length is 88 characters.** This is a **deliberate project-level
  departure** from the user's stated global Python standard of 79, recorded here
  so it is not later mistaken for an oversight. 88 is Ruff's and Black's default;
  adopting it means the formatter runs unconfigured on the one setting most likely
  to be mis-set, and the choice is made at project setup because changing it later
  reformats every file and makes every subsequent diff unreadable against
  history.
- **Type checking: `disallow_untyped_defs = true` globally, with three strict
  islands.** The global baseline is what makes partial strictness coherent rather
  than decorative: mypy strictness is mostly a property of what a module can
  *see*, so "strict on the money module" while it imports unchecked code yields
  either a wall of `Call to untyped function` errors silenced with
  `# type: ignore`, or `Any` flowing in from the un-strict side and strict mode
  checking nothing of consequence. With every function everywhere annotated, the
  remaining strict-only settings are genuinely local. `strict = true` plus
  `disallow_any_explicit = true` on `app.money.*`, `app.authz.*` and
  `app.schemas.*`; `warn_unused_ignores`, `warn_redundant_casts` and
  `check_untyped_defs` globally. `warn_unused_ignores` in particular stops a
  `# type: ignore` added on a hard afternoon from living forever after it became
  unnecessary.
- **The strict region must not import the un-strict region.** `app.money` depends
  on nothing but `decimal` and its own value types — no ORM, no session, no
  settings. `app.authz` depends on repository *protocols*, not implementations.
  One architectural rule buys both the type story and the money boundary.
- Naming: `snake_case` for functions and variables, `PascalCase` for classes,
  `UPPER_CASE` for constants — language-idiomatic, no project-wide rename rules.
- **Sphinx-style docstrings on every module, class and function**, enforced by
  Ruff's `D` rules across the whole backend rather than by review opinion. Every
  parameter documented with `:param x:`, every return value with `:return:`,
  every exception a caller must handle with `:raises:`. No `:type:` or `:rtype:`
  — the type hints carry that, and duplicating them creates two things to keep
  in step. Keep parameter descriptions brief: a well-named parameter needs a
  clause, not a sentence.

  This is the team's standing Python standard and it applies uniformly. A
  narrower variant was proposed during this stage — module docstrings everywhere
  but function docstrings only in `app/money/**` and `app/authz/**` — on the
  argument that mandating one per public function produces signature
  restatements that drift and mislead. That argument was considered and
  **rejected**: the standard applies as written, and a drifting docstring is a
  reason to update it in the same change, not a reason to omit it.

  `:raises:` carries extra weight here beyond the general rule, because the
  error taxonomy below is only usable if raise sites declare which class they
  raise.
- Type hints are mandatory on all parameters and return values.

### Money as a type, on both surfaces

**Money is a type, not a number.** This supersedes a lint-rule approach, because
a lint rule has to know which values carry money — exactly what an unfamiliar
reviewer cannot see.

In Python, `Money` is a frozen value object wrapping a `Decimal` with BDT
implicit, and it is the only money type that crosses the module boundary:

- No `__float__`, no `__int__`, and construction from a float raises. The
  float prohibition becomes a property of the type rather than a rule someone
  enforces. This also closes the gap no float ban catches: `Decimal(0.1)`
  produces a `Decimal`, so a type check passes while the value is already wrong.
  We additionally ban `Decimal(<float>)` construction (Ruff `RUF032` covers the
  float-literal case; a variable-valued float is handled by the type).
- `__add__` and `__sub__` accept only `Money`, so mypy catches `money + 5`
  instead of it quietly working.
- **Multiplication is not `__mul__`.** `Money * x` is where rounding enters, so it
  is a named method forcing the caller to say what they mean:
  `apply_rate(rate: Decimal) -> Money`, rounding with the module's single mode.
  No anonymous rounding.
- **Division is not exposed** until a requirement needs it. If a requirement needs
  splitting an amount, that is `Money.allocate(n)` returning a list whose sum is
  exactly the original, by the standard remainder-distribution method. An
  unconstrained `/` is how a one-paisa discrepancy enters a ledger.
- **`ROUND_HALF_UP`**, declared once as a module constant. Python's `Decimal`
  default is `ROUND_HALF_EVEN` (banker's rounding), which is wrong for
  consumer-facing BDT fee amounts: a teacher checking arithmetic by hand expects
  half-up. This is a decision, not a default, and it is invisible once chosen and
  expensive to change after a ledger exists.
- The wrapped `Decimal` is **quantized to 2dp at construction**. An unquantized
  `Decimal` makes equality and `__hash__` inconsistent in ways that bite in sets
  and dict keys, and means two "equal" amounts can serialize differently.
- `Money.ZERO` exists as a constant so callers write `balance > Money.ZERO`
  rather than `balance > 0`, which removes the one place a bare `0` creeps in.
  Comparison is type-safe: comparing `Money` to `int` is a type error, not a
  surprise.
- `Money.sum(iterable)` exists with a zero identity, because a dues total across
  batches is the operation most likely to be written as a Python `sum()` with a
  `0` start value, which coerces or crashes.
- Predicates `is_zero()` and `is_positive()` live on the type, keeping
  sign-convention knowledge in one place.
- `Money.format(locale)` lives in the module, so the server is the only thing
  deciding digit rendering and separator placement under Bangla locale [TC-15,
  TC-9].

**The module owns both chokepoints every money value must pass anyway**: one
Pydantic annotated type reused by every schema (not a per-field
`field_serializer`, which is how one endpoint eventually emits a number), and a
SQLAlchemy `TypeDecorator` mapping `Money` to `NUMERIC(12,2)` (otherwise every
model independently declares its column type and one eventually declares
`Numeric(10,2)` or a `Float`). A money value physically cannot enter or leave the
system without passing through `app.money`. That is what makes the boundary
enforceable rather than aspirational.

In Kotlin, `Money` is a value class (`@JvmInline value class Money(val amount:
BigDecimal)`) with a kotlinx.serialization serializer that reads **only** a JSON
string and rejects a JSON number. A `Double` cannot be assigned to a `Money`
field — the compiler stops it, with no custom lint rule at all — and a backend
regression emitting a JSON number fails client decoding at runtime and in the
contract test, which also catches a hand-written client model that forgot the
annotation. The detekt rule then degrades to a trivial backstop: forbid `Double`
and `Float` across the whole `core/model` package, a package-scoped ban rather
than a semantic "money-carrying" judgement.

**The import boundary is checked from the first commit, not after a violation.**
The conditional framing inverts the economics: the check costs about fifteen
lines of config now, versus the same fifteen lines later *plus* unwinding
however much arithmetic leaked in the interim — and with the fee model already
in revision [D-18] the leak would be inside code about to be rewritten. Two
independent mechanisms, because they catch different things:

- **Import-direction check.** Ruff `flake8-tidy-imports` banned-api on raw
  `decimal` outside `app/money/**`, with `per-file-ignores` re-permitting it
  inside. Banning raw `decimal` imports outside the module is the load-bearing
  half, because money arithmetic outside the module needs either `Decimal` or a
  float, and both are then blocked.
- **A layered-import test.** One pytest test (import-linter, or about thirty
  lines walking the AST) asserting that `app.money` imports nothing from
  `app.api`, `app.db`, `app.repositories`, `app.authz` or `app.schemas`. This is
  the one that catches the *plausible* violation — not arithmetic in a view, but
  someone making `app.money` take a `Session` "just to look up the batch default
  fee", which destroys the testability and the mypy story in one commit.

The money module is consequently buildable and fully testable before any
endpoint exists, which is why 100% branch coverage is achievable there and would
not be elsewhere.

### Authorization: every endpoint names its lens

The failure mode is not a wrong lens, it is a **forgotten** lens — and a
dependency you forgot to add produces an endpoint that works perfectly and
authorizes nothing. That must fail in CI, in three layers:

- **The lens is a dependency that returns the value the handler needs**, not a
  side-effecting guard whose absence is invisible. `lens:
  Annotated[TeacherLens, Depends(teacher_lens_for_batch)]`, where `TeacherLens`
  carries the resolved `owner_id` the query needs. The handler then cannot
  *compile a query* without the lens, because the scoping value lives inside the
  lens object. This converts authorization from a precondition into a data
  dependency, and it is the single most valuable change in this section.
- **A route-enumeration test** asserting that every route resolves a lens, with
  `PUBLIC_ROUTES` an **explicit frozenset** containing exactly the OTP issue and
  verify endpoints, the health endpoint, and the external deletion route
  [TC-19]. The allowlist is the important half: adding a public endpoint means
  editing a list in a test, which is a reviewable, deliberate act. The check
  walks `route.dependant` recursively, because a lens may be nested inside a
  composed dependency, and matches on the dependency's **return annotation being
  a `Lens` subtype** rather than on the function's name — name-matching is how
  this check gets defeated by a rename. It runs against the real app object at
  collection time, so a new un-lensed endpoint reddens CI on the commit that adds
  it.
- **Response-schema separation as a lens rule, not only a privacy rule.** A lens
  type parameterizes which response models an endpoint may return, so a
  teacher-lens endpoint returning a `StudentPrivateResponse` is a mypy error.
  This is the layer that catches right-lens-wrong-data, which the other two do
  not.

One mechanical note, so nobody later "optimizes" this wrongly and nobody avoids
the necessary optimization out of fear of the rule: lens resolution hits the
database on every request, as [TC-11] requires, which makes it the hottest query
in the system on a single 2 GB instance. **Request-scoped memoization is
permitted — same account, same batch, resolved once per request. Cross-request
caching is forbidden.** A request-scoped memo is not a cached role.

### Layer boundaries: the API returns decisions, not inputs to decisions

[TC-9, D-31] put every business rule server-side and leave the client rendering.
Stated that way the rule is unfalsifiable; stated as **"if the client is
comparing a domain value, the server should have sent a decision"** it is
checkable, and it is the convention that prevents all five erosion paths we
expect:

1. **Badge and empty-state logic in composables.** The first screen showing a fee
   status will otherwise carry `if (balance > 0) "Due" else "Paid"` — a business
   rule about *what counts as due*, rendered as if it were presentation, and
   nearly invisible in review because it looks like UI code. The server sends
   `status: "due" | "paid" | "partial"` alongside the amount, and the client
   switches on a server-provided enum, never on a comparison.
2. **Client-side filtering and sorting of a domain list.** The cross-batch dues
   screen is defined by outstanding balance rather than active status [PU-7.2] —
   a business definition of who appears. List endpoints return the membership and
   order the server decided; the client may not filter or re-sort a domain list.
   Client-side sort is permitted only for purely lexical cases the server has
   declared unordered.
3. **Room as a shadow model.** Room is a read cache [TC-8, D-9]. Room entities
   mirror the API DTO shape one-to-one and carry no derived fields, only a
   `fetched_at` timestamp. Any derived value in a Room entity is a layering
   defect.
4. **Validation duplicated and then diverging.** Client-side validation is
   permitted for *format* only, never for *policy*, and every client-side check
   must have a server-side check that would also reject it. The client check is an
   optimization, never a gate.
5. **The lens hint shaping more than navigation.** [D-2] allows a client lens hint
   for UI shaping and forbids trusting it for authorization. The hint affects
   navigation only; the server response is self-describing and says which lens
   produced it. The client renders from the response, not from the hint it sent.

### Error handling

"Error handling at every integration boundary" is a statement of intent that
every implementer reads differently, so we fix the taxonomy instead.

**A closed exception hierarchy, defined once.** Five classes, chosen because they
map to five distinct caller behaviours:

| Class | Meaning | Caller behaviour | HTTP |
|---|---|---|---|
| `ValidationError` | The request is wrong | Fix and resubmit; never retry as-is | 400/422 |
| `AuthorizationError` | No lens grants this | Re-auth or stop; never retry | 401/403 |
| `ConflictError` | Valid request, state forbids it | Refetch and decide; retry is wrong | 409 |
| `TransientError` | May succeed if repeated | Retry with backoff | 503 |
| `FatalError` | Bug or unrecoverable | Do not retry; alert | 500 |

**Retryability is a property of the error class, not a judgement at the call
site.** That is what makes "recoverable distinguished from fatal" actionable: the
distinction is made once, at the raise site, by choosing a class, and every layer
above reads it off the type. One FastAPI exception handler maps the hierarchy to
responses, so no endpoint writes its own try/except for these.

**One error envelope, carrying the class so the client never infers it**:
`{"error": {"code": "FEE_CYCLE_ALREADY_SETTLED", "retryable": false,
"message_key": "..."}}`. Three deliberate choices. `retryable` is a
**server-provided boolean** — the client is forbidden business logic [TC-9], so
it does not decide retryability from an HTTP status, it is told. `code` is a
stable machine value, so the client switches on it and never on message text.
And **`message_key` rather than `message`**: a server-sent English `message`
cannot be localized by the client, and in a Bangla-first UI [TC-15, D-43] it
guarantees untranslated English error text. The user-facing string comes from
`strings.xml`; the server names which string.

**Per-boundary rules, because the four boundaries genuinely differ:**

- **SMS gateway** — the only boundary where a failure costs money and a retry may
  double-charge and double-message. The call is wrapped in one adapter [PU-1.4],
  a send is attempted **once with no automatic retry**, a timeout is recorded as
  `unknown` rather than `failed` because the SMS may have been delivered, and the
  user-facing path is "request a new OTP" rather than a silent resend. Automatic
  retry here is a bug, not resilience. The daily ceiling [D-33] is checked
  *before* the call, and a ceiling breach is a `ConflictError`, not a
  `TransientError` — retrying into a cost ceiling is exactly wrong.
- **Database** — three cases, not one. A constraint violation on
  `(enrollment_id, period)` is **not an error at all**: it is the
  `ON CONFLICT DO NOTHING` success path [D-21]. A serialization failure or
  deadlock is a `TransientError` with bounded retry of the whole transaction. A
  connection failure is a `TransientError` that must **not** be retried inside a
  request — it fails fast, because a 2 GB single instance under connection
  pressure gets worse, not better, if every request retries. One transaction per
  request, committed by the endpoint and never by a repository method, or a
  partial money write becomes possible.
- **FCM** — best-effort by nature. A failed push must **never** fail the operation
  that triggered it. Dispatch happens after commit, outside the request
  transaction, and its failure is **logged and not surfaced**. An `UNREGISTERED`
  response is not an error; it is a signal to delete the stored token [D-42].
  **This is the stated exception to "silent failures are not acceptable"**: at
  this boundary a logged non-fatal failure is the correct behaviour, and the rule
  says so explicitly rather than being implemented wrongly.
- **S3 backups** — covered under Deployment: failure alerts, and an unverified
  upload is not a backup.

**Two rules that make the taxonomy hold.** Never catch bare `Exception` except in
exactly two places — the FastAPI exception handler, and the scheduled
fee-generation job's top level, where a crash must not kill the daily run;
everywhere else catch the specific exception and re-raise as a taxonomy class,
enforced by Ruff `BLE001`. And every error log carries the correlation id and
never a phone number, an OTP or a token.

No hardcoded credentials, keys or secrets anywhere, ever.

### Android (Kotlin)

- Formatter: **ktlint with the `official` code style, run through spotless.**
  These are not alternatives — spotless is a Gradle plugin that *runs*
  formatters, ktlint is the formatter. Spotless gives `spotlessApply` and
  `spotlessCheck` uniformly and also covers the XML (`strings.xml`, with Bangla
  content) and the Gradle files, which ktlint alone does not. Decided at project
  setup, because the first reformat is a whole-module diff. **detekt** is a
  separate decision from the formatter and we take it, as the backstop described
  under money-as-a-type.
- **Conventional Google choices by default, with project constraints
  outranking them.** Deferring to the best-documented convention is right for the
  reason [OC-3] gives — reviewability, and applicable help when stuck. But the
  precedence must be stated, because samples conflict with our constraints in
  three named places: samples wire in Firebase Analytics and Crashlytics as a
  matter of course, which violates [TC-3, TC-6, D-37]; samples have no decimal
  money, so "what the sample does" is `Double` or a formatted string, and [TC-7]
  outranks it; and samples are offline-first, with a data layer built around a
  local write path that [TC-8, D-9] explicitly forbid in V1. So: **project
  constraints outrank the sample; the sample decides everything the constraints
  do not.** We also **pin which sample**, naming the repository and the
  commit or tag consulted in the practice, because `architecture-samples` and
  `nowinandroid` differ substantially and "whatever is current" is unpinnable a
  year from now.
- **File organization is by feature, with a layer split inside each feature**, not
  by layer at the top level. Top-level-by-layer means every Bolt touches every
  top-level package, so every diff spreads across the tree — and for a reviewer
  learning the framework, the most valuable property of a diff is that it is
  *localized*. The Bolt structure is already feature-shaped (PU-1 to PU-7 are
  vertical slices), so matching the layout to the Bolts makes "is this Bolt
  complete" answerable by looking at one folder, and makes the layering rule
  checkable within one feature folder against the three or four files next to it.

  ```
  feature/
    auth/        { ui/ (composables + screen), AuthViewModel.kt, AuthUiState.kt }
    batches/     { ui/, BatchesViewModel.kt, BatchesUiState.kt }
    attendance/  ...
    fees/        ...
  core/
    network/     { Retrofit service interfaces, DTOs, Money serializer }
    database/    { Room entities, DAOs }
    model/       { domain models incl. Money }
    designsystem/
    ui/          { shared composables }
  ```

  This is the `nowinandroid` shape (`feature/*` plus `core/*`), so it satisfies
  the defer-to-Google rule rather than contradicting it. But we keep it as
  **packages in ONE Gradle module for V1, not Gradle modules.** The sample uses
  roughly forty Gradle modules; replicating that multiplies build configuration
  and build time for a two-surface solo project and is a learning cost paid for
  nothing. One `:app` module with this package structure converts to modules
  later if ever needed. This is the one place we deliberately do not copy the
  sample.
- **Layering, with UI-state mapping given a home.** ViewModel holds UI state,
  repository holds data access, no business logic in either [TC-9, D-27]. The gap
  that rule leaves is where *UI-state mapping* lives — formatting a balance,
  deciding which empty state to render, choosing whether to show a badge. These
  are not business rules but they are decisions, and unassigned they land in
  composables where they are untestable. So: **the ViewModel maps a server
  response to a UI state data class, and that mapping is where all such decisions
  live.** A composable receives a UI state and renders it with no conditionals
  depending on domain values. That mapping function is the target of the
  Turbine and JUnit tests, rather than an untargeted "test the ViewModel", and
  "a composable that computes a fee balance is a bug" then generalizes correctly.
- Money is the `Money` value class described above — never `Double` or `Float`,
  never `BigDecimal` raw across a boundary.
- **No hardcoded user-facing strings.** Everything in `strings.xml` with Bangla
  and English from the first screen [TC-15, D-43]. Layouts must survive longer
  Bangla text, with a verifier rather than a hope.
- **The forbidden-identifier set is enforced by two failing build gates**, because
  review cannot see what a transitive SDK collects — a reviewer looking at
  `implementation("com.example:analytics:1.2")` in a Gradle diff cannot know it
  pulls an SDK reading `Settings.Secure.ANDROID_ID`, and that is precisely the
  risk [TC-3, TC-4, TC-6, D-37, D-35]:
  - **A merged-manifest permission allowlist**, as a Gradle task that fails the
    build: the release variant's merged manifest contains exactly an approved
    permission set and nothing else, and **asserts the absence of
    `com.google.android.gms.permission.AD_ID`**, which is the declaration Play's
    Families review looks for and which a transitive ads or analytics SDK adds
    silently via manifest merger. This also finally enforces our own
    `NEVER request SMS read permission` rule, which review alone did not.
  - **A scan of the minified release DEX** for forbidden framework references:
    `getImei`, `getSubscriberId`, `getSimSerialNumber`, `getLine1Number`,
    `Build.getSerial`, `getMacAddress`, `getBSSID`, `getSSID`,
    `AdvertisingIdClient`, `ANDROID_ID`. Method references survive minification
    because they are framework calls — obfuscation renames *our* symbols, not
    `android.telephony.TelephonyManager.getImei`. It runs on the **R8-minified
    release build**, not the debug build, because a debug build can differ in
    which dependencies are present and the release AAB is what ships. Roughly a
    thirty-line script, and the highest security value per hour available in this
    project.

  The allowlist alone is insufficient on its own: it catches an SDK that
  *declares* `AD_ID`, while one reading `ANDROID_ID` or calling `getImei`
  declares no permission at all. Android Lint's `HardwareIds` check is raised to
  `fatal` in `lint.xml` as a complement, not as the gate, since it analyses
  sources and may not reach into every third-party AAR.
- **An SDK admission note per new third-party dependency** — one committed
  paragraph recording what the SDK collects and the vendor's own disclosure link.
  The point is not the document; it is that the two gates generate findings and
  this is where the answer is recorded, so the Data Safety form is filled from it
  rather than from memory.

### Both surfaces

- **Deletion semantics are written down per table, and the privacy policy is
  generated from them.** "Delete the account" is underspecified against this data
  model in a way that matters: a student's attendance and marks were written by
  the *teacher* and are the teacher's record, while the same rows are the child's
  personal data. A guardian's erasure right and a teacher's legitimate business
  record are in direct tension, and [RC-5] already requires the privacy policy to
  state what is retained post-deletion and why. So every table holding
  child-identifying data carries a **written disposition** — hard delete,
  anonymize-in-place, or retain-with-stated-basis — decided at Domain Design and
  asserted by a test, and the privacy-policy text is generated from those
  dispositions rather than written independently of them. A privacy policy that
  contradicts the implementation is worse than a vague one.
- **A stated retention period per data class, with a scheduled purge.** We start
  with the auth records, where the answer is uncontroversial and the win is
  largest: OTP records, refresh tokens, failed-verify records and rate-limit
  counters are high-volume, contain phone numbers, and have an obviously short
  lifetime measured in days rather than months. The child academic records need
  the teacher's-record-versus-child's-data view resolved first. A retention
  policy with one unresolved row is still far better than none.
- Commits are conventional-commit shaped so the Bolt squash commit and release
  notes can be generated rather than written.
- The generated OpenAPI 3.1 schema is committed, so a contract change shows up as
  a reviewable diff instead of being invisible [D-26] — and the schema-diff gate
  keeps the committed copy current.

---

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
