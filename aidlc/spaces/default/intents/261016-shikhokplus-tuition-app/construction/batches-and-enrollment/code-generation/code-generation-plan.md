# Code Generation Plan — `batches-and-enrollment` (U4)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`
**Depth**: Comprehensive

> **The first Unit with two teachers in it**, and the first migration
> that alters a table holding rows.
>
> **Three things here are easy to build so they pass every test and are
> silently wrong**: a fold that deletes guardian rows it cannot place, a
> removal check that treats an erased seat as unclaimed, and a
> query-count test whose fixture is too small to see N+1. The step order
> below puts each where it fails loudly.

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

**Test-first when the correct output is knowable AND a wrong answer is
a money or authorization error.**

| Component | Predicate | Order |
|---|---|---|
| The fold guard | **Data loss**, and the migration is irreversible | **Test-first** |
| `inactive_from` semantics | **Money** — U7 charges against it | **Test-first** |
| Removal's two conditions | **Authorization** — an erased seat must stay erased | **Test-first** |
| Guardian reachability | **Authorization** — cross-teacher leakage | **Test-first** |
| Cross-teacher isolation | **Authorization** | **Test-first** |
| The two money allowlists | **Money** — an allowlist that exempts too much silently retires the gate | **Test-first** (step 10) |
| The migration's mechanics | Neither, but irreversible | Test-first anyway |
| Room entities, Compose screens | Neither, and `OC-3` warns against it | Test-after |

---

## Part 1 — The migration, which cannot be rolled back

- [ ] **Step 1 — RED: the fold guard.** A guardian row whose batch has
      a student count other than exactly one makes the migration
      **raise**. Four shapes: zero students (the seed script's shape),
      one (foldable), two (ambiguous), none-guardian. *Run it and
      confirm it fails before the guard exists.*

- [ ] **Step 2 — RED: the from-head migration test.** Upgrade to
      `0001`, **seed a dormant enrollment**, upgrade to head, assert
      the enrollment **still points at its account**.
      *Both the seeding and the value assertion are the requirement —
      an empty table makes rename and drop-and-recreate identical, and
      a row count passes against both.*

- [ ] **Step 3 — GREEN: `0002`.** ADD the five new columns, RENAME
      `account_id`, **guard**, fold, delete guardian rows, DROP `role`,
      then `Batch` / `BatchSubject` / `ScheduleSlot` /
      `HiddenBatchPreference`, the four indexes and the partial unique
      index.

- [ ] **Step 4 — `downgrade()` raises.** It can reverse the renames; it
      cannot reconstruct which student a deleted guardian row belonged
      to. A downgrade that looks like it worked would be reached for
      exactly when care matters most.

- [ ] **Step 5 — The lens-query correction**, in the same revision's
      code [BR5.0]. `_LENS_QUERY`'s guardian subquery reads
      `guardian_account_id`; `available_lenses` follows.

- [ ] **Step 6 — Narrow U3's no-writes test** to the explicit module
      list, rather than deleting it.

## Part 2 — The money gates' first real column

> **Two gates, not one**, and neither allowlist exists yet [BR3.3].

- [ ] **Step 7 — Observe BOTH false positives.** With `batch`
      migrated, run the governance suite **and** the schema gate, and
      record what each reports. *Expect `batch.fee_due_day` from the
      database gate and `fee_due_day numeric-money` from the schema
      gate — the latter confirmed by running
      `money_schema_violations` against a `BatchResponse` before this
      plan was written. Record what actually fires; a gate that
      reports nothing is a finding, not a pass.*

- [ ] **Step 8 — Unify the token lists.** `MONEY_NAME_TOKENS` is
      currently declared twice, in `app/contract/money_schema.py` and
      in `tests/db/test_governance.py`. One importable constant, and a
      test asserting both gates read it. **Without this, step 9's two
      allowlists can drift into protecting different column sets.**

- [ ] **Step 9 — BUILD the two allowlists** [BR3.3]. Neither exists:
      `money_schema_violations(app)` takes the app alone and
      `_money_columns(session)` filters on tokens alone, so each gains
      an exception parameter — `NON_MONEY_FIELDS` and
      `NON_MONEY_COLUMNS`, named per entry with a reason.
      **Not** a token deletion, which would turn the build green while
      retiring the check on every genuine fee column in U7 and U8.

- [ ] **Step 10 — RED for each allowlist.** An unlisted money-named
      column of the wrong type is **still reported** by each gate.
      *Without this the allowlists are indistinguishable from
      disabling the gates, which is exactly the fix step 9 forbids.*

- [ ] **Step 11 — Build the `TypeDecorator`** `team.md` specifies and
      B1 had no table to need.

## Part 3 — Authorization (TEST-FIRST)

- [ ] **Step 12 — RED: the two-teacher test.** One account enrolled
      with two teachers; neither roster shows the other's row.
      *The test B3 could not write.*

- [ ] **Step 13 — RED: guardian reachability** through
      `guardian_account_id`, never through the child. Plus the
      cardinality: distinct **children**, not enrollments.

- [ ] **Step 14 — RED: removal's two conditions.** Dormant **and never
      erased**. An erased seat has a NULL account again, so a null-only
      test deletes it and destroys the marker.

- [ ] **Step 15 — GREEN: the services** — batch, enrollment, removal,
      guardian children.

- [ ] **Step 16 — The `HISTORY_TABLES` registry** and the schema-driven
      test asserting every table referencing an enrollment appears in
      it, by FK **or** column name.

## Part 4 — `inactive_from` (TEST-FIRST — money)

- [ ] **Step 17 — RED: four named tests.** Nothing after; the
      containing period **in full**; other enrollments untouched; the
      comparison against the period **start**, never the due date.

- [ ] **Step 18 — GREEN.** U4 records; U7 reads. The tests pin the
      predicate against a stub so the semantics exist before the
      consumer.

## Part 5 — Endpoints and the query-count property

- [ ] **Step 19 — The routes**: batch CRUD, enrollment CRUD, student
      batch list, guardian children, child-scoped reads.

- [ ] **Step 20 — RED: the query-count property.** The count is the
      **same at N=2 and N=25**. Both fixtures under SQLAlchemy's
      500-row chunk boundary, or a correct build fails.

- [ ] **Step 21 — The four indexes**, asserted present.

## Part 6 — Android

- [ ] **Step 22 — Room**, entities mirroring the DTO plus `fetched_at`.
- [ ] **Step 23 — A test asserting no Room entity derives a field.**
- [ ] **Step 24 — Roster and child-selection screens**, both bundles.
- [ ] **Step 25 — `fetched_at` is rendered**, not merely stored.

## Part 7 — Verification

- [ ] **Step 26 — Delete `seed_skeleton.py`** and its tests.
- [ ] **Step 27 — `make check` green**, no floor weakened.
- [ ] **Step 28 — `source-manifest.json`.**

---

## Story-to-step traceability

| Story / AC | Steps |
|---|---|
| US2.1 — batch creation | 3, 15, 19 |
| US2.2 — add student | 15, 19 |
| US2.3 — edit | 15, 19 |
| US2.4 — `inactive_from` | 17, 18 |
| US2.5 — removal | 14, 15, 16 |
| US2.6 — student list | 19, 20 |
| US2.7 — guardian children | 13, 15, 19 |
| US2.8 — attribution | 12, 13 |
| US1.3 — dormant | 3, 14 |
| NFR9.32 — the money column | 7, 8, 9, 10, 11 |
| BR3.3 — the two allowlists | 7, 8, 9, 10 |
| BR5.0 — the lens correction | 5, 12 |
| NFR6.18 — the destructive rename | 2, 3 |

---

## What this Bolt does not build

- **No sessions, attendance, exams or marks** — U5's and U6's.
- **No fee cycles.** U4 records the anchor; U7 charges against it.
- **No deletion paths** — U11's. U4 ships the columns erasure writes.
