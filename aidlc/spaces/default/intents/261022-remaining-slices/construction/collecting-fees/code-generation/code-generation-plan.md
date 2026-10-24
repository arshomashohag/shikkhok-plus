# Code Generation Plan — D3 `collecting-fees`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

## Summary

- Builds: the fee system in full — five tables, calendar-month generation with
  a non-degrading clamp, the daily self-healing job behind a `user_data` cron
  entry, two-sided carry-forward, credit grant and apply, payment claims and
  verification with partial approval, the server-computed status enum, the
  shared FCM adapter, and the student and guardian fee views.
- Touches: `app/fees/` (new), `app/db/models.py`, `app/schemas/`, `app/api/`,
  `migrations/versions/0005_*`, `app/notifications/` (new),
  `infra/modules/app/user_data.sh.tftpl`, `openapi.json`, and
  `android/.../feature/fees/` (new).
- **Does not touch `app/money/`.** The arithmetic is built and proven; D3 is
  persistence, generation and API around it.
- Tests: ~75 backend of which **31 are RED-first**, ~20 Kotlin, 4 Bangla rows.

## Sources

- [upstream] `construction/collecting-fees/functional-design/entities.md`,
  `rules.md` (38 rules, BR1.1–BR7.2), `functional-spec.md`
- [upstream] `construction/collecting-fees/nfr-requirements/` — six documents,
  105 requirements
- [upstream] `construction/collecting-fees/nfr-design/` — six documents;
  `observability-design.md` § 1 and `reliability-design.md` §§ 5–6 are
  load-bearing
- [upstream] `construction/collecting-fees/infrastructure-design/` — three
  documents
- [prior] `261016-shikhokplus-tuition-app/inception/domain-design/decisions.md`
  — ADR-002, the ledger decision and the corrected invariant
- [code] `app/money/_ledger.py`, `app/money/_kinds.py`, `app/db/models.py`,
  `app/batches/service.py`, `app/errors/`, `app/authz/resolve.py`,
  `tests/db/test_governance.py`, `tests/auth/test_ceilings.py`,
  `infra/modules/app/user_data.sh.tftpl`, read 2026-10-24
- [human] The scheduler choice, taken 2026-10-24: **cron installed by
  `user_data.sh.tftpl`**

## Testing Contract

> Rendered by `aidlc engine testing-posture render` and pasted unchanged. The
> contract is identical to D1's and D2's — same methodology, same scope, same
> hash — because nothing in the affirmed posture changed between units. The
> `applicable_notes` array carries the full org and team posture text, which
> is what `contract_sha256` is computed over, so it is reproduced verbatim
> rather than summarised.

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

### How the custom ordering applies to D3

The predicate is **test-first when the output is knowable from the requirement
AND a wrong answer is a money or authorization error.** D3 is the unit where
that predicate holds for most of the work, which is the opposite of D2.

| Work | Cadence | Why |
|---|---|---|
| Period arithmetic and the clamp | **Test-first** | Pure calculation; every expected value is knowable from BR2.2's table before any code exists |
| Fee resolution and generation | **Test-first** | A wrong charge is a money error [BR1.1, BR2.4] |
| Idempotency under concurrency | **Test-first** | The guarantee is the constraint; a sequential test passes against the broken implementation it exists to prevent [BR1.3] |
| Decline semantics | **Test-first** | A guardian decline that stops generation, or a student decline that does not, is a money error [BR1.6, BR1.7] |
| Carry-forward and credit | **Test-first** | Two-sided pairing and `min(available, owed)` are knowable; a one-sided carry double-counts [BR3.1, BR4.4] |
| Claims and verification | **Test-first** | The shortfall formula and over-approval-becomes-credit are both money errors when wrong [BR5.3, BR4.2] |
| Lens scoping on the new tables | **Test-first** | Authorization error [BR6.4, NFR14.36] |
| Response shape, mappers, screens | Test-after | Rendering and serialization; a wrong answer is cosmetic |
| The cron entry and heartbeat | Test-after | Infrastructure glue; verified by an integration test that the command runs and stamps |

**31 of the ~75 backend tests are RED-first.** Where a step below is marked
**RED**, its test must fail before the implementation step that follows it.

---

## Steps

### Phase A — Runner, schema, governance

- [ ] **Step 1.** Verify the runner and record the unit-scoped commands in
      `unit-test-instructions.md`. Confirm `docker info` is reachable; D3's
      tests are overwhelmingly integration tests. No code changes.

- [ ] **Step 2.** `migrations/versions/0005_fee_system.py`: create
      `fee_cycle`, `ledger_entry`, `payment_claim`, `reminder_event` and
      `job_heartbeat`. `fee_cycle` carries **no money column** [BR1.2] and a
      unique constraint on `(enrollment_id, period)` [BR1.3]. `ledger_entry`
      amounts are `NUMERIC(12,2)` with a `CHECK (amount >= 0)` [BR3.4].
      Forward-only and backward-compatible.

- [ ] **Step 3.** `app/governance/dispositions.py`: a disposition and a
      retention class for **all five** tables. `job_heartbeat` is hard delete,
      bounded [entities.md].
      *`tests/db/test_governance.py` iterates live `pg_tables` in both
      directions, so a missing row here is a red `make check`, not a note.*

- [ ] **Step 4.** `app/db/models.py`: the five ORM models, money columns
      through the existing `Money` `TypeDecorator`. `LedgerEntry.period` is a
      plain string, **not** a foreign key to `fee_cycle` — a `carry_forward`
      lands on a period whose cycle row may not exist yet [entities.md].

- [ ] **Step 5.** Run the migration tests and the governance tests. **Both
      must pass before Phase B.**

### Phase B — The calendar, test-first

- [ ] **Step 6. RED — periods and the clamp.** `tests/fees/test_periods.py`:
      `YYYY-MM` round-trips; `min(day, days_in_month)`; the stored anchor is
      **not** rewritten; anchor 31 gives 2027-01-31, 2027-02-28, 2027-03-31,
      and 2028-02-29 in a leap year; a NULL anchor means the last day.
      *(BR2.1, BR2.2, BR2.3)*

- [ ] **Step 7.** `app/fees/periods.py`: the period type and `due_date_for`.
      **No calendar knowledge enters `app/money/`** — `period` is opaque
      there [BR2.1].

- [ ] **Step 8. RED — fee resolution.** `tests/fees/test_resolution.py`: the
      enrollment fee when not NULL, else the batch default; **zero is a real
      fee and not "unset"**; both NULL refuses rather than charging zero.
      *(BR2.4)*

- [ ] **Step 9.** `app/fees/resolution.py`: `resolve_fee`. Returns `Money`.

- [ ] **Step 10.** Run Steps 6 and 8. **They must now pass.**

### Phase C — Generation, test-first

- [ ] **Step 11. RED — generation charges the resolved fee.**
      `tests/fees/test_generation.py`: one `charge` entry per enrollment per
      period at the resolved amount; the cycle row carries no money.
      *(BR1.1, BR1.2)*

- [ ] **Step 12. RED — idempotency is the constraint.** A second generation
      for the same `(enrollment_id, period)` conflicts and is a **success**,
      appending no second charge. *(BR1.3)*

- [ ] **Step 13. RED — concurrency.** `tests/fees/test_generation_races.py`:
      real threads released from a `threading.Barrier`, against real
      PostgreSQL, asserting the **outcome** — after N overlapping generations
      exactly one row per `(enrollment_id, period)` and the ledger total
      unchanged. Modelled on `tests/auth/test_ceilings.py:283`, but with
      **imports at the top of the file**; that file's `import threading`
      inside the function violates the standing rule and must not be copied.
      *(BR1.3, NFR19.8)*

- [ ] **Step 14. RED — self-healing across days.**
      `tests/fees/test_generation_across_days.py`: a missed day catches up on
      the next run, and a re-run on a later day appends nothing. **Time is
      injected, not raced** — this is the case Step 13 cannot reach.
      *(BR1.4)*

- [ ] **Step 15. RED — `inactive_from` generates the containing period in
      full.** A seat inactive mid-month is charged for that month and not the
      next. *(BR1.5)*

- [ ] **Step 16. RED — decline semantics, both directions.** A declined
      **student** link stops generation and reverses accrued cycles; a
      declined **guardian** link does **neither**. A pending seat generates.
      Un-declining resumes without resurrecting voided cycles.
      *(BR1.6, BR1.7, BR1.8, BR1.9)*
      *The asymmetry has already produced one defect in this project on the
      presentation side; it is tested from both roles here.*

- [ ] **Step 17.** `app/fees/generation.py`: `generate_for_period`, using
      `ON CONFLICT DO NOTHING` and per-enrollment commits so one bad row does
      not abort a run [NFR19.8]. **No application-level "has this run?"
      guard.**

- [ ] **Step 18.** Run Steps 11–16. **All must now pass.**

### Phase D — Carry-forward and credit, test-first

- [ ] **Step 19. RED — a carry is a pair in one transaction.** A
      `carry_forward` on the receiving period and a `carried_out` on the
      origin, committed together; a one-sided carry is impossible through the
      API. Worked case: carrying 1000 into a second 1000 charge reads
      **2000** owed, not 3000. *(BR3.1)*

- [ ] **Step 20. RED — a carry never exceeds what the origin owes.**
      *(BR3.2)*

- [ ] **Step 21. RED — credit.** Over-approval becomes `credit_grant`, never
      a negative balance; credit belongs to the **enrollment**; the next
      generation applies `min(available, owed)` in the **same transaction as
      the charge**. Worked case: a 1000 charge with 200 credit leaves
      **800**. *(BR4.1–BR4.5)*

- [ ] **Step 22.** `app/fees/ledger_writer.py`: the persistence operations.
      **Calls `app/money/`'s `carry_forward` and `apply_credit`; implements
      neither.**

- [ ] **Step 23.** Run Steps 19–21. **All must now pass.**

### Phase E — Claims and verification, test-first

- [ ] **Step 24. RED — claim resolution and validation.** A claim resolves to
      the **oldest unpaid cycle** or is refused; zero and negative refused;
      an over-claim accepted. *(BR5.1, BR5.2)*

- [ ] **Step 25. RED — the shortfall is `charged − approved`.** The
      separating case: 1000 charged, 1500 claimed, 600 approved gives **400**,
      not 900. Measuring against the claim would let a payer change what they
      owe by changing what they assert. *(BR5.3)*

- [ ] **Step 26. RED — a shortfall requires an explicit carry-or-waive
      choice**, and verification plus its entries commit together.
      *(BR5.4, BR5.5)*

- [ ] **Step 27. RED — rejection and correction.** Rejection records no
      ledger entry and is visible to the submitter; a corrected verification
      is visible to both parties with its previous decision retained.
      *(BR5.6, BR5.7, BR3.3)*

- [ ] **Step 28.** `app/fees/claims.py` and `app/fees/verification.py`.

- [ ] **Step 29.** Run Steps 24–27. **All must now pass.**

### Phase F — API, authorization and the status enum

- [ ] **Step 30. RED — lens scoping on the new tables.** Adversarial probes
      as the restricted non-superuser role: teacher A against teacher B's fee
      cycle; a guardian against a non-child's; a student against a claim not
      theirs. Every pre-authorization refusal is the shared `NOT_AVAILABLE`.
      *(NFR14.36–.39, BR6.4)*

- [ ] **Step 31. RED — the collection number is bounded downward.** Visible
      only to a student or guardian lens on that batch; absent from every
      other response, every listing and every search. **This is the direction
      the built schema-wide invariant does not check.** *(BR6.4, NFR14.32)*

- [ ] **Step 32.** `app/schemas/fees.py`: response schemas. Money as a JSON
      **string** [BR6.2]; the server-computed fee status enum [BR6.1]; the
      four claim statuses [BR6.3]; the server-supplied channel set [BR6.5].

- [ ] **Step 33.** `app/api/fees.py`: the routes, each naming its lens. The
      route-enumeration test must pass unchanged.

- [ ] **Step 34.** Extend the registry test to
      `AUTH_403_CODES - ALLOWED_NON_RESOURCE == {NOT_AVAILABLE}`. **Not a
      whole-set equality** — `AUTH_403_CODES` holds two members today and
      `LENS_NOT_AVAILABLE` is not an oracle, so an equality would fail
      against a correct registry. *(security-design § 4)*

- [ ] **Step 35.** `Money.format(locale)`: **Latin digits**, agreeing with
      `Numerals.kt` rather than deciding independently. *(BR6.6)*

- [ ] **Step 36.** Run Steps 30–31. **Both must now pass.**

### Phase G — Reminders and the FCM adapter

- [ ] **Step 37.** `app/notifications/fcm.py`: the adapter, **beside the SMS
      gateway client and not inside `app/fees/`**. An adapter living in the
      fee feature is one D4 copies, producing the two-adapter outcome OQ-4
      exists to prevent. Best-effort, post-commit, failure logged and not
      surfaced, `UNREGISTERED` deletes the token, no device identifier.
      *(BR7.2, NFR11.2, NFR19.24)*

- [ ] **Step 38.** An import-boundary check: **no module under a feature
      package may define an FCM client.** Same shape as the money module's.
      Without it, OQ-4's failure mode is prevented only by D4's author
      remembering. *(NFR19.24)*

- [ ] **Step 39.** `ReminderEvent`: an append-only event; state is the latest
      per period. *(BR7.1)*

### Phase H — The scheduler and the heartbeat

- [ ] **Step 40.** `app/fees/commands.py`: `generate-fee-cycles` as a
      runnable entry point taking no arguments and safe to run at any time.

- [ ] **Step 41.** The `job_heartbeat` write: an upsert on `job_name`, in its
      **own transaction after the run's last enrollment-period has
      committed** — never inside one, because a run that generated 2,900 of
      3,000 did succeed at the 2,900.
      **Unconditional on outcome, conditional only on completion**: a run
      that finds nothing due still stamps, with `cycles_created = 0`.
      Generation is monthly, so most days legitimately create nothing, and
      stamping only on `> 0` would leave the row stale for weeks during
      correct operation and train the operator to mute the alert.
      *(NFR25.9, observability-design § 1.1a)*

- [ ] **Step 42.** `app/fees/commands.py`: `check-generation-freshness`,
      emitting `log.critical` when there is no row or the row is older than
      48 hours. *(NFR25.9)*

- [ ] **Step 43.** `infra/modules/app/user_data.sh.tftpl`: the cron entry,
      invoking `docker compose run --rm api generate-fee-cycles` — the same
      shape as the Alembic step at line 325. **Provisioned by Terraform, never
      added by hand over SSM**: the ASG replaces the instance on every deploy,
      so a hand-added entry is silently wiped and generation stops with
      nothing failing.
      **The freshness check is a separate entry and must not be cron**, or
      both die together. *(infrastructure-specification § 3)*

- [ ] **Step 44.** An integration test that the command runs end to end and
      stamps the heartbeat, including the zero-cycles case.

### Phase I — Android

- [ ] **Step 45.** `core/network`: fee DTOs. Money decodes from a JSON
      **string** and **fails loudly on a JSON number**.

- [ ] **Step 46.** `feature/fees`: `FeeStateMapper` as a pure object in
      `RosterStateMapper`'s shape; the status enum maps **exhaustively or
      fails**, matching `STATUS_KEYS`.

- [ ] **Step 47.** `FeeUiState` and the fee screens. Every decision is a
      mapper field; **no composable compares a domain value** — no
      `if (balance > 0) "Due"`, which is a business rule in presentation's
      clothes.

- [ ] **Step 48.** Mapper and screen tests, and the money serialization test.

- [ ] **Step 49.** Strings for every new screen in **both** `values/` and
      `values-bn/`; `message-keys.json` and `MessageKeys.kt` kept in step.

### Phase J — Contract, documentation, traceability

- [ ] **Step 50.** Regenerate and commit `openapi.json`; the schema-diff gate
      must pass. Add the declared error responses, which closes the
      published-envelope-referenced-by-no-operation gap D2 recorded.

- [ ] **Step 51.** Named-manifest entries in `tests/named_tests.toml` for
      every RED-first obligation, each with its criterion and rule id.

- [ ] **Step 52.** Four rows in `docs/delivery/bangla-layout-check.md`, one
      per new screen, each naming its longest string.

- [ ] **Step 53.** `ruff format`, `ruff check`, `mypy app` clean. Sphinx
      docstrings on every new module, class and function. **`app.fees.*`
      joins the strict-mypy islands**, and the long-deferred `app.authz.*`
      override lands with it.

- [ ] **Step 54.** Write `code-summary.md`, `traceability.json` and
      `source-manifest.json`. Run the full `make check`.

**At Step 54, read the money module's coverage**: it must still be 100.00%
branch. D3 adds no code there, so any drop means something imported it
wrongly rather than that a test is missing.

---

## Story-to-step traceability

| Story | Steps |
|---|---|
| US5.1 generation | 6–18, 40–44 |
| US5.2 carry-forward | 19–23 |
| US5.3 credit | 21–23 |
| US6.1 claims | 24, 28 |
| US6.3 verification | 25–29 |
| US5.3/5.4 views | 30–36, 45–48 |
| US1.14 decline | 16 |
| FR10 reminders | 37–39 |
| FR0.2 strings | 49, 52 |

---

## What this plan does NOT do

| Not built | Why | Owner |
|---|---|---|
| Any change to `app/money/` | The arithmetic is built and proven at 100% branch | — |
| A snapshot or ledger compaction | Unbounded growth is accepted for V1: 14,400 rows at five years is one linear pass | — |
| Deletion flows | Release-blocking with their own tests | **D6** |
| The cross-batch dues query | Spans every batch a student belongs to | **D5** |
| A metrics backend or alert delivery | `job_heartbeat` is queryable without one; delivery is the human's costed choice | — |
| Fixing the origin 502 | Not introduced by D3 and not D3's to change | recorded in `cicd-pipeline.md` § 4.2a |

---

## Assumptions & Open Questions

- **Assumed**: a NULL `fee_due_day` means the last day of the period
  [BR2.3]. Flagged for the human at Functional Design and not yet confirmed;
  it is the only default that cannot make a fee due before the month it pays
  for has been taught.
- **Assumed**: `Money.format(locale)` emits Latin digits, agreeing with the
  client's built `Numerals.kt` rather than deciding independently.
- **Open, and D6's**: OQ-1 — whether `PaymentClaim.transaction_id` survives
  the claimant's deletion. Shipped nullable, so the answer is not foreclosed
  and the schema needs no revisit either way.
- **Decided this turn by the human**: the scheduler is cron installed by
  `user_data.sh.tftpl`.
