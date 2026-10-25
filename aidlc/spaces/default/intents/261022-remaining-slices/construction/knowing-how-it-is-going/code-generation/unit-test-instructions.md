# Unit Test Instructions — D5 `knowing-how-it-is-going`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **Every defect this unit can ship produces a number that balances.** There
> is no constraint to violate, no migration to fail, no race to lose — a
> double-counted credit, a month grouped by the wrong column, a sum over the
> wrong kinds each yield a figure that is internally consistent and false.
> **`make check` cannot tell any of them from correct.**
>
> So this document is mostly about making each test **unable to pass against
> its own defect**, and § 3 lists the four assertions where the obvious form
> passes against the thing it is meant to catch.

## Sources

- [upstream] `functional-design/rules.md` — 22 rules, each
  `violation_behaviour` naming its own assertion
- [upstream] `nfr-design/reliability-design.md` § 1 — the three wrong numbers
- [upstream] `nfr-design/security-design.md` § 2 — the probe seeding table
- [upstream] `nfr-design/performance-design.md` § 1 — the statement-count
  property and its axis
- [engine] `aidlc engine testing-posture resolve --stage code-generation
  --unit knowing-how-it-is-going`
- [code] read 2026-10-25: `tests/fees/test_query_count.py:129-160`,
  `tests/fees/`, `tests/privacy/`, `tests/conftest.py`

---

## 1. The runner

| Purpose | Command |
|---|---|
| Everything, local and CI | `make check` |
| This unit's backend tests | `python -m pytest tests/analytics -q` |
| Android | `./gradlew :android:testDebugUnitTest --rerun-tasks` |

**`--rerun-tasks` is not optional on the Kotlin side.** D4 recorded a
`BUILD SUCCESSFUL in 643ms / 28 up-to-date` that executed nothing; a cached
pass is indistinguishable from a real one in the output a person reads.

**Docker must be running.** The integration suite skips wholesale without it
— D4 measured 24 of 28 skipped, exit 0. CI now asserts this; locally it is
on you, and **a green run without Docker is not evidence for anything in
§ 2**.

---

## 2. Methodology: the predicate, item by item

| Area | Predicate | Why |
|---|---|---|
| `seats.py`, the owned-seat join | **holds** | A wrong seat set returns **another teacher's data** — authorization. Expected membership is tabulated in `security-design.md` § 2 before any code |
| `earnings.py`, the kind fold | **holds** | A wrong fold is a **money** error, and `rules.md` BR2.1 computes the expected total |
| `dues.py`, membership and assembly | **holds** | BR1.2's predicate decides who a teacher chases for money |
| `upcoming.py` | **holds** | An unscoped `LIMIT 1` returns another teacher's exam — authorization |
| The privacy probes | **holds** | Every expected value is stated upstream |
| Routes and schemas | does not hold | Plumbing over a layer already proven |
| Android | does not hold | No Kotlin experience [OC-3]; a Compose test written first is as likely to encode a framework misunderstanding as to catch a defect |

**Test-after here is a cadence, not permission to write the test against the
implementation.** Each is written from its acceptance criterion.

---

## 3. The four assertions where the obvious form fails to catch its defect

**This section is the reason the document exists.**

### 3.1 Earnings: assert the TOTAL, not month one

`tests/analytics/test_earnings.py`

BR2.1's case: M1 charge 1000, receipt 1000, credit_grant 500; M2 charge
1000, credit_apply 500, receipt 500.

| M1 earnings under | Figure |
|---|---|
| the correct fold | **1500** |
| counting `credit_apply` | **1500** — M1 has no apply, so **the defect is invisible** |
| charge-summing | 2500 — caught by any assertion pinning 1500 |

**A per-month assertion on M1 misses the double-count entirely.** Assert the
**total: 2000, and specifically not 2500.** The total is where the two months
differ, which is why BR2.1's case spans two.

**Second assertion, for coverage not coincidence**: a month whose charge and
receipt **differ**, so charge-summing has an independent failing assertion
rather than sharing the total's.

### 3.2 Dues membership: the seat must be BOTH inactive AND owing

`tests/analytics/test_dues_membership.py`

**A test using only active owing seats passes against a query carrying
`inactive_from`** — the predicate D4's roster uses and D5 must not [BR1.2].
Both halves of Bolt 5's hypothesis, asserted together because one can pass
while the other fails:

- an **inactive, owing** seat **is present**;
- an **active, owing-nothing** seat **is absent**.

### 3.3 Month grouping: a late-recorded payment, and a carry

`tests/analytics/test_period_grouping.py`

- An entry whose `period` is `2026-10` and whose `created_at` falls in
  November **counts in October**. Late recording is the normal case — a
  teacher verifies October's cash in early November — and `created_at`
  grouping makes the trend show a dip and a spike that never happened.
- A **`carry_forward`** entry, which lands on the **receiving** period
  [`app/db/models.py:927-934`]. Its `created_at` is whenever generation ran,
  so `created_at` grouping scatters carries into arbitrary months — this
  case fails against the defect **even when no payment is late**.

### 3.4 Scope probes: assert the VALUE, and seed so a leak changes it

`tests/privacy/test_analytics_probes.py`

**A wrong scope on a sum returns a number that looks right.** Asserting "a
200 with a number" passes against a figure summed across two teachers.

| Probe | Seeding that makes a leak visible |
|---|---|
| Earnings | **B larger** — if A dominated, A's figure would barely move |
| Dues | **B has more owing seats** — a length assertion then changes |
| Trend | **Different periods** — a leak shows as A carrying a month A has no data in |
| Next exam | **B's exam SOONER** — if B's were later, correct and leaked both return A's |

**The next-exam row is wrong in both directions by default**: an unscoped
`LIMIT 1` returns *somebody's* soonest exam.

---

## 4. The statement-count property, on D5's own axis

`tests/analytics/test_query_count.py`

**Follow `tests/fees/test_query_count.py:129-160`'s shape** — it asserts
`at_two == at_twenty_five`, **a property rather than a literal**, and its
own comment says why: *"a correct change that moves the number does not
retire the check."*

**But change the dimension.** D3 grew **seats within one batch**; D5 is the
first unit to read across **every batch a teacher owns**. A test growing
seats within a single batch **passes against a correct-looking per-batch
loop**, which is BR1.6's trap. **Hold seats-per-batch fixed and grow
batches-per-teacher.**

**Also assert** the oldest-unpaid-period from the in-fold `per_cycle` map
**equals** the built `oldest_unpaid_period`'s value for the same seat
[NFR20.33] — so the reimplementation is pinned rather than merely cheap.

---

## 5. The rest

| Area | Module | Floor |
|---|---|---|
| Seat set | `test_seats.py` | 4 — ownership, declined excluded, no `inactive_from`, no `joined_on` |
| Dues rows | `test_dues.py` | 5 — amounts, batch names, the empty list, ordering, the period |
| Trend | `test_trend.py` | 3 — under two months returns nothing; two returns both; order is in the response |
| Next exam | `test_upcoming.py` | 4 — today counts, yesterday does not, the tiebreaker is stable, absent is a 200 |
| Four kinds of nothing | `test_absences.py` | 4 — a test per row, **status AND shape**; absent and zero are different wire shapes |
| Read-only | `test_no_writes.py` | 1 — table state unchanged across both reads |
| Snapshot | `test_snapshot.py` | 1 — a concurrent write during the read; figures internally consistent |
| Contract | `tests/contract/` | 3 — **empty parameter list** on both operations; no `collection_rate`; `PUBLIC_ROUTES` still 8 |
| Android | per feature | mapper state machines; the three absences rendered distinctly |

**No new governance test.** The built pair covers "25 entries, both
directions" with nothing added.

**`tests/db/`**: assert `migrations/versions/` carries no new revision.

---

## 6. Coverage

80% line floor, no decrease. **`app/analytics/earnings.py` and `dues.py`
hold no I/O**, so their arithmetic is testable at unit speed and carries the
higher branch target. Kotlin coverage reported, ratchet unchanged.

**A test that passes regardless of implementation is a defect in its own
right.** For each of § 3's four, break the implementation deliberately, watch
the test fail, restore — and say what you broke.

---

## 7. What is not tested, stated plainly

| Obligation | Status |
|---|---|
| No child name, money amount or dues row in a log | **Review only.** No scanner exists, and one built for this unit would imply coverage it lacks |
| No alert on a wrong figure | **Undetectable** without a second source of truth |
| The `bundletool` proxy's difference from Play's figure | **A human comparison at the first release** |
| ZAP's authenticated surface | **Not covered.** The scan carries no token |
| No latency assertion on any path | **The deliberate position**, not a gap |

---

## Testing Contract

Copied verbatim from
`aidlc engine testing-posture resolve --stage code-generation --unit knowing-how-it-is-going`.

- `contract_sha256`: `sha256:3e5ed58e58959c39e4f534bf45533286315a0ec4e7adda70a17544b1e976e78a`
- `input_sha256`: `sha256:ead71391fd1b965e6ba93466891a92ee7c79f56c4c5890f84e9ca14257ae5bc9`

```json
{
  "version": 1,
  "methodology": "custom",
  "source": "team",
  "ordering": "Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
  "scope": "classic",
  "test_strategy": "standard",
  "project_type": "brownfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt\nwithout its tests is not done.\n\n- **Methodology**: custom\n- **Methodology evidence**: The cadence genuinely differs by surface, and\n  recording a single uniform value would misdescribe what we actually do. Three\n  facts drive the split. (1) The money paths — fee-cycle arithmetic,\n  carry-forward, partial approval, waiver — have **mandatory** tests by stated\n  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than\n  I/O-shaped, and have expected values knowable before any implementation\n  exists. That is the exact precondition under which test-first pays: the test is\n  a specification we can write correctly without having written the code, and the\n  fee model is *already known to be in revision* [D-18], so a suite that pins the\n  arithmetic is what makes the next revision safe rather than frightening. (2) The\n  Compose UI surface is the opposite case. There is **no declared Kotlin or\n  Android experience** [OC-3], so a Compose test written before the\n  implementation is as likely to encode a misunderstanding of the framework as to\n  catch a defect, and when it passes it certifies that misunderstanding — worse\n  than no test. (3) The privacy boundary is structural rather than arithmetic\n  [D-7, TC-13] — enforced by table design, row-level security and distinct\n  response schemas — so its tests are adversarial probes against a built\n  boundary, which is inherently test-after. A uniform `tdd` would be a commitment\n  we would break on the Compose Bolts; a uniform `test-after` would weaken the\n  one surface where the requirement is explicit and the preconditions for\n  test-first are actually met. `custom` is the accurate value. *Re-confirmed\n  2026-10-22 against the built state: the money module shipped at 100% branch\n  coverage with the property-based ledger test, and the privacy suite shipped as\n  adversarial probes behind a superuser meta-check. The split described here is\n  the split that was actually practised.*\n- **Ordering**: Write the failing test first whenever **both** of these hold —\n  the correct output is knowable from the requirement without having written the\n  code, **and** a wrong answer would be a money error or an authorization error —\n  and for everything else implement the layer, then write and run that layer's\n  tests before the Bolt is complete.\n\nThat ordering is a **predicate, not a list**, and the distinction is the point:\nan enumeration plus \"everything else\" fails open, because every case nobody\nanticipated defaults to test-after. The following are *examples* of the\npredicate holding, not its boundary:\n\n- every change to the money module;\n- every fee-cycle and payment-verification state transition — generation,\n  carry-forward, partial and reduced approval, waiver, rejection;\n- the `(enrollment_id, period)` idempotency constraint;\n- every lens-resolution and row-level-security rule, wherever that code lives;\n- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,\n  leave existing dues standing, and leave the student active in other batches,\n  all three of which are money-adjacent and fail quietly;\n- the cross-batch dues query [PU-7.2], which is driven by outstanding balance\n  and not by active status, so students who left owing money still appear;\n- *(added 2026-10-22)* **acceptance state transitions in D1** — a seat moving\n  from pending to accepted or declined grants or withholds a guardian lens, so\n  a wrong answer is an authorization error and the predicate holds. This is the\n  gap the re-cut exists to close and it is test-first.\n\n**A change meeting the predicate does not escape it by being implemented in\nKotlin**, or in a route handler rather than in the money module. Where the code\nlives is not part of the test.\n\n**Test-after is a cadence, not permission to write the test against the\nimplementation.** A test-after test is written from the acceptance criterion. If\nwriting it requires reading the implementation to know what to assert, the\nacceptance criterion is the defect.\n\nSupporting bullets, which do not replace the two fields above:\n\n- **Backend coverage floor**: 80% line coverage, enforced in CI, with no\n  decrease permitted. This comes from the active `classic` scope at Comprehensive\n  test strategy and may not be weakened to make a step pass. **The authorization\n  layer is measured as branch coverage rather than line coverage** — lens\n  resolution is pure branching over teacher, student and guardian and owned-batch\n  membership, so line coverage on it is close to meaningless. *Measured\n  2026-10-22: 91% overall against the 80% floor, 615 tests passing. Met with\n  headroom.*\n- **The money module carries 100% branch coverage**, because the defects that\n  matter there live in the branches: the short-month clamp, the\n  carry-forward-versus-waive fork, the partial-approval path, the\n  zero-and-negative edges. An 80% line floor can be met while leaving the waiver\n  branch entirely unexecuted, which satisfies the number and misses the\n  requirement. Two things make that target honest rather than decorative: the\n  money module contains **no I/O, no session and no HTTP**, so 100% stays\n  reachable; and branch coverage is supplemented by obligations not reducible to\n  a percentage — a named test per fee-cycle and payment state transition, and a\n  documented boundary case per money input (period boundaries, rounding at the\n  half, zero, negative, an approved amount exceeding the claimed amount). We also\n  add one property-based test (Hypothesis) on the ledger invariant. *Measured\n  2026-10-22: 100.00%, `fail_under = 100` configured. Met. The invariant in\n  force is the corrected one recorded under Corrections, not the superseded\n  `charged - received - forgiven == outstanding`.*\n- **Android carries named obligations and no percentage floor.** Gating a surface\n  the reviewer cannot yet evaluate produces tests written to raise a number; that\n  is a reason to drop the *percentage*, not a reason to drop the *obligation*,\n  and this is the thinnest-reviewed part of the product. So:\n  - every ViewModel ships tests for its state machine — loading, success, error,\n    and the explicit retry path for a failed write [TC-8, D-9];\n  - every money-carrying model class ships a serialization test proving decode\n    from a JSON string and **loud failure** on a JSON number, because a lenient\n    decoder that quietly accepts a number and converts is the actual failure mode\n    and it passes a happy-path-only both-sides test;\n  - Kotlin line coverage is reported from the first Android Bolt, with **no\n    decrease permitted** once three Android Bolts have merged. A no-regression\n    ratchet gives the trend teeth without anyone inventing a target they cannot\n    justify.\n\n  **The first two obligations were met and the third was not.** *(Reconciled\n  2026-10-22.)* 137 `@Test` functions across 14 files, targeting the mapping\n  functions rather than untargeted ViewModels, which is what the practice asked\n  for; `MoneySerializerTest` and `NoFloatingPointTest` cover the money boundary\n  including loud failure on a JSON number. But there is **no Kotlin coverage\n  report of any kind** — no JaCoCo, no Kover — and three Android Bolts have\n  merged, so the ratchet that should now be in force has no number to ratchet.\n  The obligation stands and the mechanism is assigned to **before D1**: a Kover\n  report from the next Android Bolt, with the no-decrease rule arming on the\n  first merged figure. Starting the ratchet now costs one plugin line and\n  establishes the baseline before five more units of Kotlin land; starting it\n  after D6 would baseline against the finished app and ratchet nothing.\n- **Test types by layer**: pytest for backend unit and integration tests, with\n  integration tests running against a **real PostgreSQL 16** container via\n  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,\n  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and\n  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin\n  ViewModel and repository tests, targeting the response-to-UiState mapping\n  function rather than an untargeted \"the ViewModel\". Compose UI tests for the\n  OTP entry path and the mid-class attendance path.\n- **The integration suite must assert that it ran.** *(Added 2026-10-22.)*\n  `tests/conftest.py` skips the whole integration suite at module level when no\n  Docker daemon is reachable, so on a machine without Docker `make check` passes\n  having run none of the row-level-security probes, none of the migration tests\n  and none of the roster tests, signalling only a pytest skip line. The skip\n  itself is reasonable. What is missing is the precondition assertion this\n  project applies to Gitleaks and not to its own database suite: **CI asserts\n  Docker was present and the integration suite actually ran.** A runner image\n  change that dropped Docker would otherwise silently narrow the suite to its\n  unit half, and the privacy boundary is the thing that would stop being tested.\n  Costs one step; assigned to **before D1**.\n- **Database tests connect as a restricted non-superuser role.** PostgreSQL\n  documents that superusers and table owners bypass row-level security entirely\n  [pg-rls], and the default test-container connection is `postgres`, a superuser.\n  A privacy-boundary suite run as superuser passes identically whether the policy\n  is correct, broken, or entirely absent — so the strongest test obligation we\n  have would certify nothing. Integration tests therefore connect as the same\n  restricted role the application uses, and a **meta-test asserts that\n  `current_user` is not a superuser and that row-level security is in force**\n  (`row_security` on, policy present) before the privacy suite runs. *Verified\n  2026-10-22: built, as `shikkhok_app`, enforced by a collection reorder and an\n  autouse re-check. This is the practice working exactly as written.*\n- **Privacy boundary tests are adversarial, and the API-level half is a\n  schema-wide invariant.** No teacher-lens response schema may contain any field\n  in the owner-private profile set, enforced by iterating the generated OpenAPI\n  schema rather than by remembering to write a test per endpoint — per-endpoint\n  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking\n  about it. The probe suite explicitly covers the IDOR shape: teacher A\n  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a\n  student requesting a fee cycle not their own.\n- **Schemathesis validates conformance, not correctness, and never counts as\n  privacy coverage.** We keep Schemathesis for what it is good at — unexpected\n  500s, type and required-field drift, auth present on every route — and we add\n  the check it cannot provide: **an OpenAPI schema-diff gate**, where the\n  committed schema must match the generated one and CI fails if they diverge.\n  *Built 2026-10-22: the schema-diff gate exists and works. Schemathesis itself\n  does not. That is the right half to have built first — the practice says so —\n  and the conformance half remains outstanding at Low severity, unassigned. We\n  are not assigning it to a unit: it is a genuine nice-to-have, and naming a\n  unit for it would be the same empty promise this run is correcting.*\n- **Money representation is itself a test target.** Every money value crosses the\n  API as a JSON **string** [TC-7, D-20], asserted on both sides.\n- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle\n  guarantee is a database constraint precisely because application-level guards\n  fail under concurrency [D-21, TC-12]. The test runs overlapping generations\n  and asserts the **outcome**: after N overlapping generations exactly one row\n  exists per `(enrollment_id, period)` and the ledger total is unchanged. It also\n  covers the case concurrency alone misses — the daily self-healing re-run\n  [PU-5.5] must be idempotent across *days*. **This lands in D3 and has not been\n  exercised yet**, because fee cycles are not built.\n- **Token lifecycle is tested as a state machine.** Refresh-token rotation with\n  reuse detection has a security-critical failure mode: present a rotated-out\n  token and the whole token family must be invalidated.\n- **Both account-deletion paths are tested** [TC-19]: the in-app path and the\n  externally accessible route. Each must assert that deletion removes what the\n  Data Safety form claims it removes and retains only what the privacy policy\n  discloses [RC-4, RC-5], per each table's written disposition. Deletion features\n  are the ones most reliably shipped broken, because nobody tests the absence of\n  data. **This is D6** and neither path exists yet; `PUBLIC_ROUTES` already\n  allowlists both, so D6 lands handlers against entries that exist rather than\n  adding new ones.\n- **PU-3.6's mid-class speed requirement is not discharged by a correctness\n  test.** Either the attendance obligation is a **Macrobenchmark on a low-end\n  device profile** (which also serves TC-17), or PU-3.6 has no automated\n  verification in V1 and carries an explicit manual check in the pilot. Both are\n  acceptable; silently using a correctness test to discharge a performance\n  requirement is not. **The harness does not exist and is assigned to D5** by\n  the delivery plan, while the attendance screen it measures lands in D4. That\n  ordering is backwards and the delivery plan records it as an open question;\n  this practice does not resolve it, it only insists the obligation is not\n  discharged by a Compose correctness test in D4.\n- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:\n  Compose screenshot tests at the longest Bangla string, or an explicit\n  per-screen manual check. \"Must not break the layout\" currently has no verifier,\n  and an unverifiable obligation is a wish. *(Reconciled 2026-10-22.)* **The\n  hard half is done and the verifier is absent.** Both bundles are complete at\n  53 strings each and no user-facing string is hard-coded. But there is no\n  Paparazzi, no Roborazzi, no screenshot infrastructure of any kind, and no\n  written per-screen manual check either — so of the two verifiers the practice\n  offered, neither exists, across three shipped screens. The practice's own\n  sentence applies to itself: this obligation is currently a wish. Both options\n  remain acceptable and the choice is the human's at this gate; what is not\n  acceptable is a fourth, fifth and sixth unit of screens shipping with neither.\n- **One command, local and in CI.** `make check` or equivalent, the same\n  entrypoint in both places. For a solo build this is the single most important\n  property of the gate: a gate reproducible only by pushing is a gate that gets\n  bypassed. The blocking suite needs no secret to run locally. *Verified\n  2026-10-22: `make check` is the CI entrypoint. Working as intended.*\n- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if\n  minutes become a real constraint. The Android job is split from the backend job\n  so a Kotlin build does not gate a backend PR, dependencies are cached, and the\n  backend path stays under about ten minutes. *Verified 2026-10-22: split, with\n  ten- and fifteen-minute timeouts, concurrency groups and `cancel-in-progress`\n  on checks but not on deploys. Built well.*\n- **A green `main`, not just a green PR.** With squash-merge and one reviewer, a\n  PR green against an older `main` can merge and break it. The post-merge run was\n  removed on 2026-10-19 at the user's instruction (\"don't run actions on merge\"),\n  and the obligation moves to GitHub's **\"Require branches to be up to date\n  before merging\"** under branch protection. **That setting is repository\n  configuration and cannot be verified from the repository.** If it is off, this\n  obligation has no verifier. We flag it as the one practice whose status this\n  run genuinely cannot establish; confirming it is a thirty-second check in the\n  repository settings and worth doing before D1.\n- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.\n  Tests that always pass regardless of implementation are defects in their own\n  right and are rejected in review.\n\n---"
    }
  ],
  "obligations": {
    "strategy": "standard",
    "strategy_volume": [
      "Five to eight tests per component.",
      "Unit tests plus integration tests for key boundaries.",
      "Add E2E, performance, or security tests when requirements demand them."
    ],
    "scope_floor": [
      "Keep the existing test suite green.",
      "This scope adds no extra new-test floor beyond the selected test strategy."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "custom",
    "runner_step": "Verify the existing test runner/configuration and record the exact unit-scoped command.",
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
      "Verify the existing test runner/configuration and record the exact unit-scoped command.",
      "Custom ordering - Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
      "Implementation and tests - preserve that exact ordering; do not convert it to layer-local TDD.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:ead71391fd1b965e6ba93466891a92ee7c79f56c4c5890f84e9ca14257ae5bc9",
  "contract_sha256": "sha256:3e5ed58e58959c39e4f534bf45533286315a0ec4e7adda70a17544b1e976e78a"
}
```

## Assumptions & Open Questions

- **Test counts are floors.** The strategy asks five to eight per component;
  § 3's areas exceed it because the design names more obligations, and no
  area is padded to reach a number.
- **`tests/analytics/` mirrors `app/analytics/`**, following `tests/fees/`'s
  per-concern module shape.
- **No test in this unit asserts a latency, a duration or a timing budget.**
  That is NFR2.10's requirement, not an omission.
- **Nothing here was executed.** D5's code does not exist; the suite is
  specified, not measured.
