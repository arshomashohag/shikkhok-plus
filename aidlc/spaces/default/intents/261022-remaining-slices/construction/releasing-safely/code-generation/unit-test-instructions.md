# Unit Test Instructions — D6 `releasing-safely`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6's tests assert absences, and an absence is what no test asserts unless
> someone writes it deliberately.** `team.md` says deletion features are the
> ones most reliably shipped broken, *because nobody tests the absence of
> data* — so this file's organising question is not "is each behaviour
> covered" but **"would this test fail if the behaviour were absent?"**
>
> **Six tests here pass against the defect they exist to catch if written the
> obvious way.** Each is called out at its § below, and they are the reason
> this file is longer than the plan.

## Sources

- [upstream] this unit's `code-generation-plan.md` §§ 1–7
- [upstream] `nfr-design/security-design.md` § 7 (collected obligations)
- [team] `team.md` Testing Posture — the ordering predicate, the floors
- [code] read 2026-10-25: `tests/db/test_governance.py`,
  `tests/db/test_no_d5_migration.py`, `tests/db/migration_support.py`,
  `tests/conftest.py`, `tests/auth/test_endpoints.py`

---

## 1. The runner, verified before the first test

```
make check
```

The same entrypoint locally and in CI, which `team.md` names as the single
most important property of the gate for a solo build. Unit-scoped during
development:

```
pytest tests/governance tests/db/test_cascade_contradictions.py -x
```

**The integration suite must actually run.** `tests/conftest.py` skips it at
module level when no Docker daemon is reachable, and a skipped privacy suite
reports success. **Before trusting any result below, confirm the suite ran**
— a `..s` line where a probe should be is the failure mode this project has
already met once this session.

---

## 2. The ordering predicate, applied item by item

The contract's `ordering` is a **predicate, not a list**. Applied:

| Test | Output knowable from the requirement? | Wrong answer is money/authz? | **Order** |
|---|---|---|---|
| No contradicting cascade (§ 3) | yes — `DISPOSITIONS` names the expected set | yes — destroys another person's retained records | **first** |
| `verify()` filters on purpose (§ 4) | yes | yes — a sign-in code destroying an account | **first** |
| A later sign-in code does not shadow (§ 4) | yes | yes — same | **first** |
| Deletion scope is its own counter (§ 5) | yes | yes — locks a victim out of signing in | **first** |
| Deletion global sub-ceiling (§ 5) | yes | yes — denies sign-in to everyone | **first** |
| Teacher-with-batches refusal (§ 6) | yes | yes | **first** |
| Absence per table, both roles (§ 6) | yes — from the manifest | yes | **first** |
| `LIFE_OF_ACCOUNT` never purged (§ 7) | yes | yes — deletes the product's history | **first** |
| Migration `0007` applies (§ 3) | no — verified *through* § 3's test | — | after |
| Generator output shape (§ 8) | no | no | after |
| Purge chunking and idempotency (§ 7) | no | no | after |

**Eight test-first items.** That is high for this project, and it is the
predicate's doing rather than a preference: D6 is a unit about destruction
and authorization, which is exactly where both halves hold.

**Test-after here is a cadence, not permission to write the test against the
implementation.** Each test-after test is written from its acceptance
criterion; if writing it requires reading the implementation to know what to
assert, the criterion is the defect.

---

## 3. The cascade assertion

**File**: `tests/db/test_cascade_contradictions.py`
**Fixture**: `restricted_session` (existing — no new fixture, no new grant)

### What to assert

A recursive walk over `pg_constraint` from `account` following
`confdeltype = 'c'`, failing when a reachable table's `DISPOSITIONS` entry is
`RETAIN_WITH_BASIS`. **The failure message carries the path**, not just the
table.

### The vacuity trap

> **A test that queries `pg_constraint` and finds nothing passes.**

If the query is wrong — a typo in the `regclass` cast, a join that drops
rows, a recursion that never recurses — it returns an empty set and the
assertion `not contradictions` is satisfied. **It would have passed before
`0007` too, when three real contradictions existed.**

**So assert the query's own reach**, in the manner
`test_the_money_assertion_is_no_longer_vacuous` already establishes in this
repository:

- the walk reaches a **known** table at depth one (`profile`);
- the walk reaches a **known** table only via `owner → batch`;
- the total reachable count is **non-zero** and matches the manifest's
  cascade edges.

### Both states exercised

**Before `0007`: three contradictions. After: zero.** Stage the pre-state
with `tests/db/migration_support.py`'s helpers and assert the test *fails*
there. A test only ever seen passing is a test never seen working.

### Why `pg_constraint` and not `information_schema`

**Measured**: an ungranted table is invisible to the restricted role in
`information_schema` but visible in `pg_constraint`. A **comment states
this**, because switching to `information_schema.referential_constraints`
looks like a simplification and would silently narrow the gate — the exact
failure the governance suite's grant comment records.

---

## 4. Purpose-scoped codes

**File**: `tests/auth/test_otp_purpose.py`

| Test | Assertion |
|---|---|
| A sign-in code does not confirm a deletion | `issue(purpose=OTP_PURPOSE)`, present at the deletion route → refused, account survives |
| A deletion code does not sign in | the inverse |
| **A later sign-in code does not shadow a deletion code** | issue deletion, **then** issue sign-in, present the deletion code → **accepted** |
| A consumed deletion code cannot be replayed | present twice → second refused, no second deletion |
| Every existing call site still works | the built OTP suite stays green |

### The vacuity trap

> **A test that issues only one code passes against the shadowing defect.**

The shadowing bug only appears when **two codes exist for one number** and
the deletion one is older. A single-code test exercises
`ORDER BY ... LIMIT 1` with one row, where fetch-then-check and
filter-in-`WHERE` behave identically.

**The ordering in that third test is the test.** Reversing it tests nothing.

---

## 5. The deletion ceiling cascade

**File**: `tests/auth/test_deletion_ceilings.py`

| Test | Assertion |
|---|---|
| Each `del_*` scope refuses at its limit | 4th hourly, 6th daily, 11th per-prefix, 51st global |
| **Exhausting `del_number_day` leaves SIGN-IN working** | drain it, then `issue(purpose=OTP_PURPOSE)` → **succeeds** |
| **Draining `del_global_day` leaves SIGN-IN working** | drain it, then a sign-in code → **succeeds** |
| A refusal consumes nothing | the refusing scope's count is unchanged afterwards |
| `fire_ceiling_alert` fires on the global scope only | not on per-number or per-IP |
| The scope values fit the column | any insert exercises `String(16)` |

### The vacuity trap

> **A test asserting only that the deletion route refuses passes against the
> shared-counter defect.**

This is the single most important sentence in this file. If deletion reuses
`ScopeKind.NUMBER_*`, then draining it *also* refuses — correctly, from the
attacker's view — and a refusal-only test is green while a victim is locked
out of signing in.

**The assertion that distinguishes the two implementations is that SIGN-IN
STILL WORKS.** Two of the six tests above are written that way, and they are
the two that matter.

### Also assert

The four `del_*` rows are **purged** by `rate_limit_counter`'s existing
48-hour window — no new retention entry, and the purge's manifest-driven
test covers them without being edited.

---

## 6. The deletion paths

**Files**: `tests/governance/test_deletion.py`,
`tests/governance/test_deletion_refusal.py`

### Absence, enumerated from the manifest

```
for table, governance in DISPOSITIONS.items():
    HARD_DELETE          -> no row for this account remains
    RETAIN_WITH_BASIS    -> the row remains
    ANONYMIZE_IN_PLACE   -> the row remains with named fields cleared
```

**Derived from `DISPOSITIONS`, never a hand-written list** [BR1.3], so a
table added later with no deletion handling **fails without the test being
edited**.

### The vacuity trap

> **A test using only a guardian passes against the defect `0007` fixes.**

A guardian's link is already `SET NULL`; a student's was `CASCADE`. **Both
roles are asserted**, and the student case is the one that was broken.

> **A second trap: a deletion test with no retained rows asserts nothing
> about retention.** The fixture must create a seat with attendance, marks and
> a settled ledger before deleting, or every `RETAIN_WITH_BASIS` assertion is
> vacuously true over an empty set.

### Both paths, compared

The in-app and external paths are compared by their **surviving row sets**,
not against two hand-written expectations — the external route is the one
that drifts, and two independent expectations drift independently.

### The teacher refusal

| Test | Assertion |
|---|---|
| A teacher owning a batch is refused | refusal **and the account row still exists** |
| Nothing partial happened | every `owner`, `batch` and `enrollment` row intact |
| A teacher owning **no** batch can delete | the refusal is not over-broad |
| The refusal carries a `message_key` | not a contentless `_refused()` |

**The second assertion is the one that catches a cleanup-shaped
implementation**: a refusal raised *after* some rows are gone passes a
refusal-only test.

### The route count

`PUBLIC_ROUTES` still holds **eight**, and the count is asserted — twice,
already, since `eec0f92` on 2026-10-22.

**Correction, 2026-10-25**: these instructions said the comment reads
"Exactly five" against a frozenset of six. It does not, and has not since
before D6 began. The claim came from `team.md`'s drift note, which described
a defect and was never updated when that same day's commit fixed it. **I
repeated it without opening the file** — the exact failure these instructions
are written to catch, committed in the document that catches it.

What D6 does correct in that comment is the sentence *"Two of these have no
handler yet"*, which this unit falsifies.

---

## 7. The purge

**File**: `tests/governance/test_purge.py`

| Test | Assertion | Order |
|---|---|---|
| **`LIFE_OF_ACCOUNT` is never purged** | aged rows in all 18 tables survive a run | **first** |
| Each finite window deletes past its horizon | 7 tables, aged fixtures either side | after |
| Nothing inside the window is deleted | the boundary, both sides | after |
| Idempotent | a second run deletes **zero** | after |
| Bounded | a batch size, not "all matching rows" | after |
| Registers a heartbeat | a `job_heartbeat` row under its own name | after |
| D4's freshness check covers it **unedited** | the enumeration reports on it with no change | after |

### The vacuity trap

> **A purge test with no aged fixtures deletes nothing and passes.**

Every window test needs rows **older** than its horizon. A fixture set
created "now" exercises the retention logic's negative branch only — and the
job that deletes nothing is indistinguishable from the job that works.

**`LIFE_OF_ACCOUNT` is test-first** because the natural implementation —
iterate all tables, default window for those without one — deletes the
product's entire history on first run, and that is knowable before writing a
line.

---

## 8. The policy generator

**File**: `tests/governance/test_policy_generation.py`

| Test | Assertion |
|---|---|
| Deterministic | run twice, compare bytes |
| Drift fails | mutate a `basis`, regenerate, assert the gate fails |
| ADR-012's disclosure is present | asserted on **generated** output |
| The `account` entry's **basis** is correct | not only its disposition |
| Only the marker region changes | surrounding human prose byte-identical |

### The vacuity trap

> **Asserting the generator's output against a fixture it also produced is
> circular.** The disclosure assertions check for *substantive content* — that
> the text states a teacher-typed name survives deletion — not that output
> equals a recorded blob.

**NFR14.90 has no automated verifier** and is not pretended to: nothing stops
a human sentence outside the marker region contradicting the manifest. The
rival hand-written table is removed to shrink the surface; the obligation
remains partly manual and is recorded as such.

---

## 9. Floors

- **80% line coverage**, no decrease. Not weakened to make a step pass.
- **Money module: 100% branch, unchanged.** D6 adds no money arithmetic; the
  floor must still be met.
- **New authorization code measured as branch coverage** — the refusal is
  pure branching.
- **Every new test must be shown capable of failing.** For the eight
  test-first items this is inherent. For the test-after items, mutate the
  implementation once and confirm red before accepting green.

---

## Testing Contract

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

---

## Assumptions & Open Questions

- **The six vacuity traps are the substance of this file.** Each describes a
  test that is correct-looking, green, and blind to the defect it names.
- **No test here has been run**, because D6's code does not exist. The traps
  were identified from the built suite's own recorded near-misses rather
  than hypothesised.
- **`tests/governance/` is a proposed package name**; no upstream artifact
  names it.
