**Collaborator:** aidlc-quality-agent

## Contribution

This is a strong draft. The money-path reasoning is better than most teams
produce and the refusal to put a coverage floor on a surface nobody can review
is an honest call rather than a lazy one. My criticism concentrates on four
things: the `Ordering` sentence is not yet enforceable, the coverage model
measures the wrong thing in one place and nothing in another, the named test
obligations miss the three highest-risk surfaces in the product, and the CI
section defers a decision that has a platform-independent answer.

### 1. The `custom` split is sound; the `Ordering` sentence is not yet usable

The split itself is defensible, and for the right reason — not "money is
important" but "the expected values are knowable before the code exists". That
is the actual precondition for test-first, the draft states it correctly, and
the fee model being in known revision [D-18] makes a pinned arithmetic suite
the thing that de-risks the revision. The Compose argument is also right and
is not a rationalisation: a test-first Compose test written by someone learning
Compose asserts the author's model of the framework, and when it passes it
certifies that model. That is worse than no test. Accept the split.

What will decay is not the reasoning, it is the boundary. The `Ordering`
sentence enumerates seven items and then says "everything else". An enumeration
plus a catch-all is a gate that fails open: anything not on the list is
test-after, and the list cannot anticipate PU-6.9 carry-forward-versus-waive
being implemented as a UI affordance, or a lens rule arriving as a shared
dependency rather than as an endpoint change. Six weeks in, every new case will
argue itself into "everything else", which is exactly the decay the brief asks
about — not because anyone cheats, but because the catch-all is the default.

Replace the enumeration with a **predicate plus examples**, so a case the list
never anticipated still resolves. Proposed replacement for `Ordering`:

> Write the failing test first whenever **both** of these hold: the correct
> output is knowable from the requirement without having written the code, and
> a wrong answer is either a money error or an authorization error. In
> practice that is every change to the money module, every fee-cycle and
> payment-verification state transition (generation, carry-forward, partial and
> reduced approval, waiver, rejection), the `(enrollment_id, period)`
> idempotency constraint, and every lens-resolution or row-level-security rule,
> wherever that code lives. For everything else, implement the layer, then
> write and run that layer's tests before the Bolt is complete. A change that
> meets the predicate does not escape it by being implemented in Kotlin or in a
> route handler rather than in the money module.

Two additions the split needs to survive contact:

- **A ratchet on the Android surface.** The Compose exemption is justified by
  inexperience, which is a temporary condition and therefore needs an expiry,
  or it becomes permanent by default. State it: after the first two Android
  Bolts are merged and reviewed, ViewModel-level tests move to test-first for
  state-machine logic (loading/error/retry, role switching, the
  connectivity-failure retry prompt). Compose UI tests stay test-after
  indefinitely — that is fine; the exemption should cover the UI layer, not all
  Kotlin forever.
- **Name what "test-after" excludes.** Test-after is a cadence, not permission
  to write the test against the implementation's observed behaviour. The
  existing "tests that always pass are defects" line is the right instinct but
  too weak. Add: a test-after test is written from the acceptance criterion,
  and if writing it requires reading the implementation to know what to assert,
  the acceptance criterion is the defect.

### 2. Coverage model: right instrument on money, wrong absence on Kotlin

**100% branch on the money module is the right instrument**, and the draft's
reasoning (an 80% line floor can be met with the waiver branch wholly
unexecuted) is exactly correct. Two refinements:

- **100% branch coverage of a module is not the same as covering the money
  *rules*.** Branch coverage is satisfied by executing both arms of each `if`;
  it says nothing about boundary values, and the money defects that will
  actually hurt are boundary-shaped: the short-month clamp on day 29/30/31,
  `NUMERIC(12,2)` rounding at the half, zero-amount and negative-amount
  submissions, an approved amount exceeding the claimed amount, carry-forward
  arithmetic that must stay conservative across many periods. Keep 100% branch
  as the floor, and add the obligation that is not reducible to a percentage:
  **a named test per fee-cycle and payment state transition, and a documented
  boundary case per money input** (period boundaries, rounding half, zero,
  negative, over-claim). Consider a property-based test (Hypothesis) on the one
  invariant that holds across all of it — for any sequence of charges,
  approvals, carry-forwards and waivers, `charged - received - forgiven ==
  outstanding`, and `outstanding` never goes negative. That invariant catches
  the class of defect no enumerated example will.
- **100% is only sustainable if the module stays arithmetic.** Make it explicit
  that the money module contains no I/O, no session, no HTTP: that is already
  implied by [D-20]/[PU-5.6] but the coverage target is what makes it
  load-bearing. The moment a database call lands in there, 100% branch becomes
  unreachable honestly and will be waived rather than defended.

**The unfloored Android surface is defensible, but the draft defends it with
the wrong argument.** "Gating a surface the reviewer cannot yet evaluate
produces tests written to raise a number" is true, and it is a reason not to
set a *percentage*. It is not a reason to set *no obligation*, and the brief is
right to press: this is the thinnest-reviewed part of the product and an
unfloored, unobligated surface is where defects will actually accumulate.
Replace the percentage with a **named-obligation floor**, which is
gate-checkable and immune to number-gaming:

- Every ViewModel ships tests for its state machine: loading, success, error,
  and the explicit retry path for a failed write [TC-8, D-9].
- Every money-carrying model class ships a serialization test proving
  `BigDecimal` decode from a JSON string and rejecting a JSON number.
- Report Kotlin line coverage from the first Android Bolt, with **no decrease
  permitted** once three Android Bolts have merged. A no-regression ratchet
  gives the trend teeth without anyone inventing a target they cannot justify.

Also: the 80% backend line floor should be stated as **branch coverage, not
line coverage, for the authorization layer**. Lens resolution is pure branching
over teacher/student/guardian and owned-batch membership; line coverage on it
is close to meaningless.

### 3. Test types and tooling

**Real PostgreSQL 16 containers over SQLite: unambiguously correct**, and the
justification names the right four behaviours. Add the fifth, which is the one
that will actually bite: row-level security **only tests meaningfully when the
test connects as the application's non-superuser role**. RLS is bypassed by
table owners and by superusers, and the default container connection is
`postgres`. A privacy-boundary test suite running as superuser passes against a
completely absent policy. Make the rule: integration tests connect as the
same restricted role the application uses, and there is a meta-test asserting
`current_user` is not a superuser and that RLS is enforced (`row_security` on,
policy present) before the privacy suite runs. Without this, the strongest
test obligation in the draft silently certifies nothing.

Use **testcontainers** rather than a hand-rolled Compose fixture, and make the
container's migration path **Alembic from zero** rather than a schema dump —
that gives the migration path continuous exercise [D-18 makes this valuable]
and costs nothing extra.

**Schemathesis from the generated OpenAPI 3.1 schema: good, with one caveat.**
Schemathesis validates conformance to the schema; it does not validate that the
schema is right. Specifically it will not catch the privacy boundary, because a
teacher-facing response schema that wrongly includes profile fields is
*conformant*. Keep Schemathesis for what it is good at (unexpected 500s, type
and required-field drift, auth on every route) and do not let it be counted as
privacy-boundary coverage. Add one cheap, high-value check that is not
Schemathesis: a **schema-diff gate** — the committed OpenAPI schema must match
the generated one, and CI fails if they diverge. The draft already commits the
schema [D-26] but does not say anything enforces that the committed copy is
current; an out-of-date committed schema is worse than none, because the
contract tests then pass against fiction.

**JUnit plus Turbine: correct and sufficient.** Turbine is the right tool for
Flow-based state assertions and is not over-specified.

**Compose UI tests limited to attendance and OTP: correct scoping, wrong
instrument for the attendance risk.** PU-3.6 requires mid-class UX "fast enough
to use in a real class" — that is a latency requirement, and a Compose UI test
asserts behaviour, not speed. Either make the attendance obligation a
**macrobenchmark on a low-end device profile** (which also serves TC-17), or
concede that PU-3.6 has no automated verification in V1 and make it an explicit
manual check in the pilot. Both are acceptable; silently using a correctness
test to discharge a performance requirement is not.

**Over-specified for a solo build**: nothing, with one exception — mypy strict
on three areas plus Ruff plus ktlint-or-spotless plus detekt plus dependency
scanning plus secret scanning plus Schemathesis is a lot of tooling to stand up
before PU-1 ships. Sequence it: Ruff, mypy on the money module, pytest with
testcontainers, and secret scanning are skeleton-time. Schemathesis, detekt,
the import-boundary lint and the Kotlin coverage report can arrive with the
Bolt that first needs them. Say so, or the skeleton Bolt turns into a
toolchain Bolt.

### 4. The named test obligations, and what is missing

The four named obligations are all correct and all aimed at real, stated risks.
Specifically:

- **Money-as-JSON-string on both sides**: right, and asserting it from the
  client side as well as the server side is the part people skip. Strengthen it
  from "the client decodes to `BigDecimal`" to "the client **fails loudly** on a
  JSON number for a money field" — a lenient decoder that accepts a number and
  converts is the actual failure mode, and it passes a both-sides test written
  only as a happy path.
- **Concurrent rather than sequential idempotency**: right, and the reasoning
  (a sequential test passes against the exact broken implementation the
  constraint exists to prevent) is precisely the point. Add that the test must
  assert the *outcome*, not just the absence of an exception: after N
  overlapping generations, exactly one row exists per `(enrollment_id, period)`
  and the ledger total is unchanged. And add the one case concurrency alone
  misses: the daily self-healing re-run [PU-5.5] must be idempotent across
  *days*, so a cycle generated on the 1st is not regenerated on the 2nd.
- **Adversarial privacy probes at both DB and API level**: right, and the
  strongest single obligation in the draft — conditional entirely on the
  non-superuser point in §3 above, without which the DB-level half is a
  no-op. Strengthen the API half from per-endpoint assertions to a
  **schema-wide invariant**: no teacher-lens response schema may contain any
  field in the owner-private profile set, enforced by iterating the generated
  schema rather than by remembering to write a test per endpoint. Per-endpoint
  tests fail to cover the endpoint added in PU-7 after everyone stopped
  thinking about it.

**What is missing.** Five obligations, roughly in order of how much they will
cost if omitted:

1. **The seven OTP abuse controls have no test obligation at all** [PU-1.2,
   architecture §7]. This is the largest gap in the draft. Every one of them is
   mechanically testable and each is a direct financial or security exposure:
   per-number limit (3/hour, 5/day), per-IP limit (10/hour), 5-minute
   single-use expiry, 5 verify attempts then lockout, **OTP stored hashed
   never plaintext and never logged**, **enumeration resistance — identical
   response body, status and timing for a known and an unknown number**, and
   the global daily SMS ceiling with its alert. These sit in PU-1, which is
   the walking skeleton, so they are the first thing built and currently the
   least-tested. The enumeration-resistance test in particular must assert
   response *equality*, and the timing property needs at least a coarse
   assertion or an explicit acknowledgement that constant-time is enforced by
   construction rather than by test. [D-33, architecture §7]
2. **Token lifecycle and refresh-rotation reuse detection** [architecture §7].
   Rotating refresh tokens with reuse detection is a state machine with a
   security-critical failure mode: present a rotated-out token and the family
   must be invalidated. Untested, this degrades silently into
   non-rotating refresh tokens, which nobody notices because the happy path is
   identical. Also: refresh tokens stored hashed, access token expiry actually
   enforced, and a 15-minute-expired token rejected.
3. **`inactive_from` date semantics** [PU-2.9]. "Mark inactive from a date, not
   a boolean" is explicitly flagged as a correctness trap: it must stop future
   fee cycles, leave existing dues standing, and leave the student active in
   other batches. All three are money-adjacent and all three fail quietly.
   Under my proposed `Ordering` predicate this is test-first, which is the
   right answer and which the draft's enumeration misses.
4. **Account deletion, both paths** [TC-19, PU-1.11/1.12]. Release-blocking and
   Play-audited. Needs a test that deletion actually removes what the Data
   Safety form claims it removes and retains only what the privacy policy
   discloses [RC-4, RC-5]. The externally accessible route is a second code
   path and needs its own test.
5. **The cross-batch dues query** [PU-7.2]. Driven by outstanding balance, not
   active status — students who left owing money still appear. That is an easy
   `WHERE active` away from being wrong, it is the feature the user called
   non-negotiable [Q6], and it is the last thing built, when attention is
   lowest.

Lower priority but worth a line each: the forbidden-identifier set deserves a
**dependency-manifest check in CI** rather than a review habit [TC-3, TC-6,
RC-1] — "check before adding" is not verifiable after the fact; and the Bangla
layout obligation [TC-15, D-43] needs a concrete instrument (Compose
screenshot tests at the longest Bangla string, or an explicit per-screen manual
check), because "must not break the layout" currently has no verifier.

### 5. What the quality gate needs, independent of platform

The platform question is genuinely open and should stay open — the draft is
right that the GitHub Actions free allowance for a private repository is thin
and that Android builds are minute-expensive. But the gate is specifiable
without it, and specifying it is what makes the platform choice a cost
comparison rather than a design decision. The gate needs, in order:

1. **One command the human can run locally that is the same command CI runs.**
   This is the single most important property for a solo build: a gate that can
   only be reproduced by pushing is a gate that gets bypassed. `make check` or
   equivalent, same entrypoint both places.
2. **Blocking, in this order (fail fast on the cheap checks):** format and lint
   (Ruff, ktlint/spotless, detekt); type check (mypy on the declared strict
   areas); unit tests; the two coverage gates (backend 80% line / authorization
   branch, money module 100% branch, no-decrease on both); integration tests
   against the real Postgres container as the restricted role; contract tests
   plus the OpenAPI schema-diff check; secret scan; dependency scan with
   Critical/High blocking. A red suite blocks; coverage below floor blocks;
   schema drift blocks.
3. **Non-blocking but reported:** Kotlin coverage trend (ratcheting once three
   Android Bolts have merged), Compose UI and benchmark results.
4. **Required properties regardless of platform:** total wall time under ~10
   minutes for the backend path or it will be skipped; the Android job split
   from the backend job so a Kotlin build does not gate a backend PR; cached
   dependencies; a per-month minute budget stated and monitored, since minutes
   are a real cost against [OC-4]; no secret needed to run the blocking suite
   locally, which means the SMS gateway is stubbed in tests and the sandbox
   credential question [open] affects only staging, never CI.
5. **A green main, not just a green PR.** With squash-merge and one reviewer,
   the post-merge run on `main` is the only thing that catches a stale-base
   merge.

My own read on the platform, offered as input rather than a decision: GitHub
Actions for the pull-request gate (better PR integration, which is where the
only review happens), and if minute cost becomes real, move the Android build
to CodeBuild rather than moving the whole gate. Splitting by cost is cheaper
than migrating by platform.

### 6. What the interview must resolve

The draft's own open-questions list is honest and mostly complete. From my
remit, these are the ones that must be answered and the ones I would add:

1. **The methodology split** — accept `custom` with the predicate-based
   `Ordering` above, or choose uniform `test-after`. If the human prefers
   uniform `test-after`, the money-path mandate [TC-20] still binds and the
   cost is that the fee revision [D-18] gets harder; that trade should be
   stated to them, not absorbed.
2. **Whether the Android surface gets the named-obligation floor** (my §2) or
   genuinely nothing. This is a real choice with a real cost either way and the
   draft currently presents only one side of it.
3. **Whether the 80% line floor applies to Kotlin at all** — the draft flags
   this and it needs an explicit answer, because `org.md`'s scope default is
   silent on per-language application.
4. **Whether the OTP abuse-control tests are in the skeleton Bolt or the Bolt
   after.** They belong to PU-1, which is the skeleton. If they are in the
   skeleton, the skeleton is meaningfully larger than the draft describes; if
   they are not, PU-1 ships to closed testing with untested rate limits and a
   live SMS bill. The human should pick knowingly.
5. **CI platform and minute budget**, per §5 — and specifically whether a
   per-month CI spend counts against the USD 50 [OC-4] or is separate. This is
   not a detail; it decides whether the Android job can run on every push.
6. **Whether PU-3.6's mid-class speed requirement gets an automated
   verification** (macrobenchmark) or an explicit manual pilot check.
7. **Which of the four strong candidates in `discovered-rules.md`'s open
   questions get promoted to rules** after affirmation. My view: the
   real-Postgres-as-restricted-role rule and the concurrency-not-sequential
   idempotency rule are the two that genuinely need to be permanent memory,
   because both describe a test that silently certifies nothing when done the
   obvious way. The 100% branch target and the JSON-string assertion are
   better as `team-practices.md` content — they are targets, and a target in
   `## Mandated` cannot be renegotiated when the money module is refactored.

One note on `discovered-rules.md` within my remit: the exclusion reasoning is
right and the file is appropriately conservative. `NEVER weaken a defined
coverage floor` is correctly included and correctly sourced to `org.md`. I would
add nothing to `## Forbidden` from the testing side except, if the human
affirms it, `NEVER run the privacy-boundary test suite as a database superuser
or table owner` — which sounds like a tooling detail and is actually the
difference between that suite meaning something and meaning nothing.

## Positions

- AGREE: The `custom` methodology split is sound and not a rationalisation —
  test-first is justified where expected values are knowable pre-implementation,
  and the Compose argument correctly identifies that a framework-naive test-first
  test certifies the author's misunderstanding.
- OBJECT: The `Ordering` sentence is an enumeration plus a catch-all, which
  fails open on every case the list did not anticipate; replace it with the
  predicate-plus-examples formulation in §1, and add an expiry on the Android
  exemption at the ViewModel layer.
- AGREE: 100% branch coverage on the money module is the right instrument, and
  the stated reason (an 80% line floor leaves the waiver branch unexecuted) is
  exactly correct.
- OBJECT: Branch coverage alone does not cover money *boundaries*; add a named
  test per state transition, documented boundary cases, and a property-based
  ledger invariant, and state that the money module stays I/O-free so 100%
  remains honestly reachable.
- OBJECT: An entirely unobligated Android surface is not defensible even though
  an unfloored one is; replace the percentage with named per-ViewModel and
  serialization obligations plus a no-decrease ratchet after three Android Bolts.
- OBJECT: The 80% floor on the authorization layer should be branch coverage,
  not line coverage — lens resolution is pure branching and line coverage on it
  is near-meaningless.
- AGREE: Real PostgreSQL 16 containers over SQLite, for the stated reasons.
- OBJECT: The privacy-boundary DB-level tests are a silent no-op unless they
  connect as the application's non-superuser role — RLS is bypassed by
  superusers and table owners, so add the restricted-role rule and a meta-test
  asserting RLS is actually in force.
- OBJECT: Schemathesis cannot detect the privacy boundary (an over-broad
  teacher response schema is schema-conformant), so it must not be counted as
  privacy coverage; add an OpenAPI schema-diff gate so the committed schema
  cannot go stale, and make the privacy assertion a schema-wide invariant
  rather than per-endpoint tests.
- OBJECT: A Compose UI test cannot discharge PU-3.6's mid-class speed
  requirement; either use a macrobenchmark on a low-end profile or declare it a
  manual pilot check.
- AGREE: Concurrent idempotency testing and both-sides money-as-JSON-string
  assertions are the right tests for the stated risks.
- OBJECT: The largest gap is that the seven OTP abuse controls have no test
  obligation at all, despite living in the walking-skeleton Unit and carrying
  direct financial exposure; refresh-token rotation reuse detection,
  `inactive_from` semantics, both account-deletion paths, and the
  balance-not-active-status cross-batch dues query are also unobligated.
- AGREE: The CI quality gate is specifiable independently of platform, and the
  draft is right to leave the platform open; my §5 states the gate, with one
  local-equals-CI command as its most important property for a solo build.
- OBJECT: The toolchain as listed is too much to stand up before the skeleton;
  sequence it so Ruff, mypy-on-money, pytest-with-testcontainers and secret
  scanning are skeleton-time and the rest arrive with the Bolt that needs them.
- AGREE: `discovered-rules.md` correctly excludes the agent's own testing
  proposals from permanent memory; of the four candidates, only the
  restricted-role integration-test rule and the concurrency-idempotency rule
  genuinely belong in `## Mandated`, because both describe a test that certifies
  nothing when written the obvious way.
