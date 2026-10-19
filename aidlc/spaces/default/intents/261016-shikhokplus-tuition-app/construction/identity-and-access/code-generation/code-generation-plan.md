# Code Generation Plan — `identity-and-access` (U3)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **THE WALKING SKELETON**
**Depth**: Comprehensive

> **The first Unit that runs.** A Compose screen calling a real FastAPI
> endpoint, reading a real PostgreSQL row, through a real OTP — not a mock
> at any layer.
>
> **Two things here are easy to build so they pass every test and are
> silently wrong**: a cached lens is indistinguishable from a computed one
> on every happy path, and a privacy suite run as superuser passes whether
> the policy is correct, broken, or absent. The step order below puts both
> where they fail loudly.

## Testing Contract

```json
{
  "version": 1,
  "methodology": "custom",
  "source": "team",
  "ordering": "Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
  "scope": "classic",
  "test_strategy": "comprehensive",
  "project_type": "greenfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt\nwithout its tests is not done.\n\n- **Methodology**: custom\n- **Methodology evidence**: The cadence genuinely differs by surface, and\n  recording a single uniform value would misdescribe what we actually do. Three\n  facts drive the split. (1) The money paths — fee-cycle arithmetic,\n  carry-forward, partial approval, waiver — have **mandatory** tests by stated\n  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than\n  I/O-shaped, and have expected values knowable before any implementation\n  exists. That is the exact precondition under which test-first pays: the test is\n  a specification we can write correctly without having written the code, and the\n  fee model is *already known to be in revision* [D-18], so a suite that pins the\n  arithmetic is what makes the next revision safe rather than frightening. (2) The\n  Compose UI surface is the opposite case. There is **no declared Kotlin or\n  Android experience** [OC-3], so a Compose test written before the\n  implementation is as likely to encode a misunderstanding of the framework as to\n  catch a defect, and when it passes it certifies that misunderstanding — worse\n  than no test. (3) The privacy boundary is structural rather than arithmetic\n  [D-7, TC-13] — enforced by table design, row-level security and distinct\n  response schemas — so its tests are adversarial probes against a built\n  boundary, which is inherently test-after. A uniform `tdd` would be a commitment\n  we would break on the Compose Bolts; a uniform `test-after` would weaken the\n  one surface where the requirement is explicit and the preconditions for\n  test-first are actually met. `custom` is the accurate value.\n- **Ordering**: Write the failing test first whenever **both** of these hold —\n  the correct output is knowable from the requirement without having written the\n  code, **and** a wrong answer would be a money error or an authorization error —\n  and for everything else implement the layer, then write and run that layer's\n  tests before the Bolt is complete.\n\nThat ordering is a **predicate, not a list**, and the distinction is the point:\nan enumeration plus \"everything else\" fails open, because every case nobody\nanticipated defaults to test-after. The following are *examples* of the\npredicate holding, not its boundary:\n\n- every change to the money module;\n- every fee-cycle and payment-verification state transition — generation,\n  carry-forward, partial and reduced approval, waiver, rejection;\n- the `(enrollment_id, period)` idempotency constraint;\n- every lens-resolution and row-level-security rule, wherever that code lives;\n- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,\n  leave existing dues standing, and leave the student active in other batches,\n  all three of which are money-adjacent and fail quietly;\n- the cross-batch dues query [PU-7.2], which is driven by outstanding balance\n  and not by active status, so students who left owing money still appear.\n\n**A change meeting the predicate does not escape it by being implemented in\nKotlin**, or in a route handler rather than in the money module. Where the code\nlives is not part of the test.\n\n**Test-after is a cadence, not permission to write the test against the\nimplementation.** A test-after test is written from the acceptance criterion. If\nwriting it requires reading the implementation to know what to assert, the\nacceptance criterion is the defect.\n\nSupporting bullets, which do not replace the two fields above:\n\n- **Backend coverage floor**: 80% line coverage, enforced in CI, with no\n  decrease permitted. This comes from the active `classic` scope at Comprehensive\n  test strategy and may not be weakened to make a step pass. **The authorization\n  layer is measured as branch coverage rather than line coverage** — lens\n  resolution is pure branching over teacher, student and guardian and owned-batch\n  membership, so line coverage on it is close to meaningless.\n- **The money module carries 100% branch coverage**, because the defects that\n  matter there live in the branches: the short-month clamp, the\n  carry-forward-versus-waive fork, the partial-approval path, the\n  zero-and-negative edges. An 80% line floor can be met while leaving the waiver\n  branch entirely unexecuted, which satisfies the number and misses the\n  requirement. Two things make that target honest rather than decorative: the\n  money module contains **no I/O, no session and no HTTP**, so 100% stays\n  reachable; and branch coverage is supplemented by obligations not reducible to\n  a percentage — a named test per fee-cycle and payment state transition, and a\n  documented boundary case per money input (period boundaries, rounding at the\n  half, zero, negative, an approved amount exceeding the claimed amount). We also\n  add one property-based test (Hypothesis) on the invariant that holds across all\n  of it: for any sequence of charges, approvals, carry-forwards and waivers,\n  `charged - received - forgiven == outstanding`, and `outstanding` never goes\n  negative. That invariant catches the class of defect no enumerated example\n  will.\n- **Android carries named obligations and no percentage floor.** Gating a surface\n  the reviewer cannot yet evaluate produces tests written to raise a number; that\n  is a reason to drop the *percentage*, not a reason to drop the *obligation*,\n  and this is the thinnest-reviewed part of the product. So:\n  - every ViewModel ships tests for its state machine — loading, success, error,\n    and the explicit retry path for a failed write [TC-8, D-9];\n  - every money-carrying model class ships a serialization test proving decode\n    from a JSON string and **loud failure** on a JSON number, because a lenient\n    decoder that quietly accepts a number and converts is the actual failure mode\n    and it passes a happy-path-only both-sides test;\n  - Kotlin line coverage is reported from the first Android Bolt, with **no\n    decrease permitted** once three Android Bolts have merged. A no-regression\n    ratchet gives the trend teeth without anyone inventing a target they cannot\n    justify.\n- **Test types by layer**: pytest for backend unit and integration tests, with\n  integration tests running against a **real PostgreSQL 16** container via\n  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,\n  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and\n  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin\n  ViewModel and repository tests, targeting the response-to-UiState mapping\n  function rather than an untargeted \"the ViewModel\". Compose UI tests for the\n  OTP entry path and the mid-class attendance path.\n- **Database tests connect as a restricted non-superuser role.** PostgreSQL\n  documents that superusers and table owners bypass row-level security entirely\n  [pg-rls], and the default test-container connection is `postgres`, a superuser.\n  A privacy-boundary suite run as superuser passes identically whether the policy\n  is correct, broken, or entirely absent — so the strongest test obligation we\n  have would certify nothing. Integration tests therefore connect as the same\n  restricted role the application uses, and a **meta-test asserts that\n  `current_user` is not a superuser and that row-level security is in force**\n  (`row_security` on, policy present) before the privacy suite runs.\n- **Privacy boundary tests are adversarial, and the API-level half is a\n  schema-wide invariant.** No teacher-lens response schema may contain any field\n  in the owner-private profile set, enforced by iterating the generated OpenAPI\n  schema rather than by remembering to write a test per endpoint — per-endpoint\n  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking\n  about it. The probe suite explicitly covers the IDOR shape: teacher A\n  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a\n  student requesting a fee cycle not their own. That is the vulnerability class a\n  scanner cannot find and the one most likely to exist, because finding it\n  requires knowing the intended policy.\n- **Schemathesis validates conformance, not correctness, and never counts as\n  privacy coverage.** A teacher-facing response schema that wrongly includes\n  profile fields is perfectly *conformant*. We keep Schemathesis for what it is\n  good at — unexpected 500s, type and required-field drift, auth present on every\n  route — and we add the check it cannot provide: **an OpenAPI schema-diff gate**,\n  where the committed schema must match the generated one and CI fails if they\n  diverge. A stale committed schema is worse than none, because the contract tests\n  then pass against fiction.\n- **Money representation is itself a test target.** Every money value crosses the\n  API as a JSON **string** [TC-7, D-20], asserted on both sides: the backend never\n  emits a JSON number for a money field, and the client rejects one.\n- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle\n  guarantee is a database constraint precisely because application-level guards\n  fail under concurrency [D-21, TC-12]; testing it by calling the job twice in\n  sequence would pass against the broken implementation the decision exists to\n  avoid. The test runs overlapping generations and asserts the **outcome** rather\n  than the absence of an exception: after N overlapping generations exactly one\n  row exists per `(enrollment_id, period)` and the ledger total is unchanged. It\n  also covers the case concurrency alone misses — the daily self-healing re-run\n  [PU-5.5] must be idempotent across *days*, so a cycle generated on the 1st is\n  not regenerated on the 2nd.\n- **Token lifecycle is tested as a state machine.** Refresh-token rotation with\n  reuse detection has a security-critical failure mode: present a rotated-out\n  token and the whole token family must be invalidated. Untested, this degrades\n  silently into non-rotating refresh tokens, because the happy path is identical.\n  We also test that refresh tokens are stored hashed, that access-token expiry is\n  actually enforced, and that a 15-minute-expired token is rejected.\n- **Both account-deletion paths are tested** [TC-19]: the in-app path and the\n  externally accessible route. Each must assert that deletion removes what the\n  Data Safety form claims it removes and retains only what the privacy policy\n  discloses [RC-4, RC-5], per each table's written disposition. Deletion features\n  are the ones most reliably shipped broken, because nobody tests the absence of\n  data.\n- **PU-3.6's mid-class speed requirement is not discharged by a correctness\n  test.** A Compose UI test asserts behaviour, not latency. Either the attendance\n  obligation is a **Macrobenchmark on a low-end device profile** (which also\n  serves TC-17), or PU-3.6 has no automated verification in V1 and carries an\n  explicit manual check in the pilot. Both are acceptable; silently using a\n  correctness test to discharge a performance requirement is not.\n- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:\n  Compose screenshot tests at the longest Bangla string, or an explicit\n  per-screen manual check. \"Must not break the layout\" currently has no verifier,\n  and an unverifiable obligation is a wish.\n- **One command, local and in CI.** `make check` or equivalent, the same\n  entrypoint in both places. For a solo build this is the single most important\n  property of the gate: a gate reproducible only by pushing is a gate that gets\n  bypassed. The blocking suite needs no secret to run locally, which means the\n  SMS gateway is stubbed in tests and the sandbox-credential question affects\n  staging only, never CI.\n- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if\n  minutes become a real constraint. Splitting by cost is cheaper than migrating by\n  platform, and the PR integration is where the only review happens. The Android\n  job is split from the backend job so a Kotlin build does not gate a backend PR,\n  dependencies are cached, the backend path stays under about ten minutes or it\n  will be skipped, and the per-month minute budget is stated and monitored\n  against [OC-4].\n- **A green `main`, not just a green PR.** With squash-merge and one reviewer, the\n  post-merge run on `main` is the only thing that catches a stale-base merge.\n- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.\n  Tests that always pass regardless of implementation are defects in their own\n  right and are rejected in review.\n\n---\n\n- The ledger invariant for the money module's property-based test is `total_charged - total_forgiven - (total_receipt + total_credit_grant) == total_outstanding - available_credit`, with `available_credit = credit_grant - credit_apply >= 0`, `total_outstanding >= 0`, and `sum(carry_forward) == sum(carried_out)`. This supersedes the earlier `charged - received - forgiven == outstanding`, which omitted carry-forward and predated credit, and an intermediate form that omitted credit_grant from cash in. Money received as credit is money received: cash in is receipts plus credit grants. (learned 2026-10-17) \n\n- Carry-forward is recorded two-sided — a `carried_out` entry relieves the originating period and a `carry_forward` entry charges the receiving one — so the two cancel at enrollment level. A one-sided carry counts the same debt in both periods: carrying 1000 into a second 1000 charge reads **3000 owed against a true 2000** — this figure was corrected on 2026-10-18, see the Corrections entry below; the earlier \"2500 against a true 1500\" reproduces under no implementation. A named test covers a multi-period carry, not only a single one, because a single carry can pass against a model that double-counts. (learned 2026-10-17, figure corrected 2026-10-18) \n\n- A money invariant is verified before it is recorded as satisfied, never asserted from reasoning alone: worked cases across every ledger operation, then randomized histories composing those operations in arbitrary order. This project's identity was wrong twice before randomized testing settled it, and it is the property-based test standing behind 100% branch coverage on the money module — an unverified invariant there certifies the arithmetic it was meant to check. (learned 2026-10-17)"
    }
  ],
  "obligations": {
    "strategy": "comprehensive",
    "strategy_volume": [
      "Ten to fifteen tests per component.",
      "Unit, integration, and E2E tests.",
      "Add performance and security tests when NFRs demand them."
    ],
    "scope_floor": [
      "Keep the existing test suite green.",
      "This scope adds no extra new-test floor beyond the selected test strategy."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "custom",
    "runner_step": "Bootstrap the minimal test runner/configuration and record the exact unit-scoped command.",
    "runner_ready_before_first_test": true,
    "testable_layers": [
      "Data model / database behavior",
      "Repository / data access",
      "Business logic",
      "API / endpoint",
      "Frontend behavior"
    ],
    "steps": [
      "Project structure and production configuration skeleton.",
      "Bootstrap the minimal test runner/configuration and record the exact unit-scoped command.",
      "Custom ordering - Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
      "Implementation and tests - preserve that exact ordering; do not convert it to layer-local TDD.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:f4aa2bdf0c63e875ce270a77c925a8267750ddf3fbb4687e062eef8e67c89f26",
  "contract_sha256": "sha256:e6177bc5e7766f133e4f6761f673165dae49441e9b7d6dcc42479afb0c5acb47"
}
```

---

### How the predicate applies here

**Test-first when the correct output is knowable AND a wrong answer is a
money or authorization error.** On this Unit that covers most of it:

| Component | Predicate | Order |
|---|---|---|
| Lens resolution | **Authorization** | **Test-first** |
| The RLS meta-test | **Authorization** — gates every privacy test | **Test-first** |
| The seven abuse controls | **Money** (per-SMS billing) | **Test-first** |
| Token rotation + reuse | **Authorization** | **Test-first** |
| The privacy probe suite | **Authorization** | **Test-first** |
| The HMAC chokepoint | Neither — but trivially knowable | Test-after |
| The gateway adapter | Neither — contract shape | Test-after |
| The migration | Neither | Test-after |
| Compose screens | Neither, and `OC-3` warns against it | Test-after |

> The Compose row is `team.md`'s stated exception: with no declared Android
> experience, a Compose test written first is as likely to encode a
> misunderstanding of the framework as to catch a defect.

---

## Part 1 — Runner readiness and schema

- [ ] **Step 1 — Dependencies and packages.** Add `sqlalchemy`, `alembic`,
      `asyncpg`, `pyjwt`, `httpx`, `testcontainers[postgres]`. Create
      `app/auth/`, `app/gateway/`, `app/audit/`, `app/db/`, and the
      `app/authz/resolve.py` + `rls.py` modules.

- [ ] **Step 2 — Test runner readiness against a real database.** A
      `conftest.py` fixture starting a PostgreSQL 16 testcontainer,
      migrating from zero, creating the restricted role, and yielding a
      session **connected as that role**. Record the exact command.
      *A Red step is invalid without a runnable command; this is that
      check, and it is the first thing that must work.*

- [ ] **Step 3 — The first Alembic migration, from zero.** Seven owned
      tables plus `Owner` and `Enrollment` as **empty shells** [BR6.1].
      RLS enabled on `Profile` with its policy. The restricted role
      created, owning nothing.

- [ ] **Step 4 — `app/db/seed_skeleton.py`** [BR6.3]. A committed script
      inserting one `Owner` and one `Enrollment` row, run manually as a
      verification precondition and **never imported by application
      code**. A test asserts no application module imports it.

## Part 2 — The gate that makes every privacy test mean something

- [ ] **Step 5 — RED: the RLS meta-test** [BR3.3]. `current_user` is not a
      superuser; `row_security` is on; the policy exists on `Profile`.
      *Run it and confirm it fails before the migration adds the policy.*

- [ ] **Step 6 — GREEN.** Make Step 5 pass, and **order it first** in the
      privacy suite so nothing downstream runs without it.

      > A superuser bypasses RLS entirely and the default container
      > connection is `postgres`. Without this the whole privacy suite
      > passes against a missing policy.

## Part 3 — Lens resolution (TEST-FIRST — authorization)

- [ ] **Step 7 — RED: the two tests that carry the rule** [BR1.2, BR1.3].
      An account gaining an `Owner` row has the teacher lens on its **next
      request**; an account losing its last `Enrollment` loses the student
      lens on its **next request**. Plus: no lens for an account with
      neither, and both lenses for an account with both.

- [ ] **Step 8 — RED: the memoization boundary** [BR1.4]. Two lookups in
      one request hit the database **once**; two requests hit it **twice**.

- [ ] **Step 9 — GREEN: `app/authz/resolve.py`.** One query returning
      three `EXISTS` booleans [NFR6.1], memoized on `request.state`.

- [ ] **Step 10 — GREEN: `app/authz/rls.py`.** Set
      `app.account_id` inside the request transaction.

- [ ] **Step 11 — The query-count assertion** [NFR6.3]. A count, never a
      duration.

## Part 4 — The seven abuse controls (TEST-FIRST — money)

- [ ] **Step 12 — RED: the ceiling cascade** [BR2.2, BR2.5]. 4th/hour and
      6th/day per number refused; 11th/hour per IP refused; the global
      ceiling refused with its alert. **Narrowest first**, and a refused
      request must not increment a wider counter.

- [ ] **Step 13 — RED: the two-worker test** [BR2.1]. The limit holds
      across two independent sessions — *this is the test that must fail
      against a per-process dictionary*.

- [ ] **Step 14 — GREEN: `app/auth/ceilings.py`.** One atomic upsert per
      scope, compared **after** the increment.

- [ ] **Step 15 — RED then GREEN: expiry, single-use, attempt ceiling**
      [BR2.3]. 5m01s refused; a verified code cannot re-verify; the 6th
      attempt refused **and the code dead afterwards**.

- [ ] **Step 16 — `app/auth/hashing.py`** [BR2.4, NFR9.5]. The HMAC
      chokepoint. A test reads the stored column, asserts it differs from
      the transmitted code, **and that it is not reproducible without the
      key** — the second half is what distinguishes HMAC from a digest.

- [ ] **Step 17 — RED then GREEN: the existence oracle** [BR2.7]. Both
      branches byte-identical **and issuing the same statements** — the
      unknown branch performs the equivalent INSERT and rolls it back.

      > The write is the larger asymmetry. A test asserting only hashing
      > symmetry guards the quiet channel.

## Part 5 — Tokens (TEST-FIRST — authorization)

- [ ] **Step 18 — RED: the five-transition state machine** [BR4.1].
      Rotation; replay refused; **family invalidated**; hashed storage;
      15-minute expiry refused.

- [ ] **Step 19 — GREEN: `app/auth/tokens.py`.** JWT with `kid` and two
      valid verification keys [BR4.3]. **No role and no lens claim.**

## Part 6 — The privacy boundary (TEST-FIRST — authorization)

- [ ] **Step 20 — RED: the adversarial probes.** Not "does a teacher see
      the right name" but **"can a teacher reach the wrong one"**: a direct
      query, a join, an ORM traversal. Each returns zero rows.

- [ ] **Step 21 — GREEN.** The table split is already in Step 3; this
      confirms the policy actually denies.

## Part 7 — The gateway (test-after)

- [ ] **Step 22 — `app/gateway/sms.py`, `bulksmsbd.py`, `null.py`.**
      Success is `response_code == 202` **and nothing else** [BR5.1];
      `https` asserted in the constructor [BR5.2]; one attempt, no retry,
      timeout as `UNKNOWN` [BR5.3]; **the null adapter is the default**
      [BR5.4].

- [ ] **Step 23 — Gateway tests against a stub.** Including: an HTTP 200
      carrying an error code is **not** success; `error_message` is never
      logged; a non-https base URL raises.

- [ ] **Step 24 — The OTP template length assertion** [BR5.5]. Rendered
      template + the 11-character SMS Retriever app hash ≤ 160 GSM-7.

## Part 8 — Endpoints, audit and governance

- [ ] **Step 25 — The three endpoints.** `POST /v1/auth/otp`,
      `/verify`, `/refresh`, wired to the taxonomy U2 shipped.

- [ ] **Step 26 — `app/audit/log.py`** [BR6.2]. Append-only, a closed
      event enum, **no free-form field** — with a test asserting the
      dataclass has no `str` field but `correlation_id`.

- [ ] **Step 27 — The two Governance manifest files** and the
      schema-iterating test that every live table carries a disposition
      per actor and a retention class.

- [ ] **Step 28 — The money column type-and-precision assertion.** B1
      authored it and could not run it; B3 is the first Bolt with a schema.
      Iterate the **migrated** schema, **regardless of how a column was
      created**.

## Part 9 — Android

- [ ] **Step 29 — OTP entry via SMS Retriever.** No SMS read permission;
      the number is typed, never read from the SIM.

- [ ] **Step 30 — The lens switcher.** Sends a hint; decides nothing.

- [ ] **Step 31 — Both language bundles on screen one** [TC-15].

- [ ] **Step 32 — ViewModel state-machine tests** — loading, success,
      error, and the explicit retry path for a failed write.

## Part 10 — Verification

- [ ] **Step 33 — `make check` green**, with the new suites wired in and
      no floor weakened.

- [ ] **Step 34 — `source-manifest.json`.**

---

## Story-to-step traceability

| Story / AC | Steps |
|---|---|
| US1.1 — teacher signs in | 15, 16, 17, 25, 29 |
| US1.2 — dormant record claimed | 7, 9, 25 |
| US1.5 — owner-private profile | 3, 5, 6, 20, 21 |
| US1.8 — the code cannot be abused | 12–17 |
| US1.9 — role resolved per request | 7, 8, 9, 10, 11 |
| AC9.3.1 / AC9.3.3 — Latin numerals, Bangla layout | 24, 31 |
| NFR9.32 — the inherited column assertion | 28 |

---

## What this Bolt does not build

- **No batches or enrollments.** U4's. This Unit creates the tables empty
  and reads them.
- **No deletion.** U11's, deliberately, so the paths are specified once
  against the full schema.
- **No money.** U1 owns the type; none crosses this Unit's surface.
