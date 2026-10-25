# Unit Test Instructions — D4 `teaching-and-recording`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **Three guarantees in this unit cannot be proven by a sequential test**, and
> each has shipped as a defect in this product already. A roster write guarded
> by a version check passes every sequential test against an implementation
> with **no guard at all**, because nothing ever contends — which is the exact
> shape of D3's double-crediting defect. § 3 is those three.
>
> **Six assertions in this unit are load-bearing rather than obvious**, in the
> sense that the natural assertion passes against the defect. § 4 is those six.

## Sources

- [upstream] `functional-design/rules.md` — every rule's `violation_behaviour`
  names its own assertion; this document does not restate them, it schedules them
- [upstream] `nfr-design/security-design.md` § 10 — 24 collected obligations,
  six marked as having no automated verifier
- [upstream] `nfr-design/reliability-design.md` § 5 — the `created_at` assertion
- [upstream] `nfr-requirements/` — the NFR ids
- [engine] `aidlc engine testing-posture resolve --stage code-generation --unit teaching-and-recording`
- [code] read 2026-10-25: `tests/fees/` (18 modules, the per-concern shape),
  `tests/conftest.py`, `tests/privacy/conftest.py`, `tests/db/test_governance.py`,
  `tests/contract/test_route_lenses.py`, `tests/named_tests.toml`

---

## 1. The runner

Unchanged and already configured. The exact commands:

| Purpose | Command |
|---|---|
| Everything, local and CI | `make check` |
| This unit's backend tests | `python -m pytest tests/teaching tests/marks -q` |
| The concurrency trio | `python -m pytest -q -k "races or concurrent"` |
| Android | `./gradlew :android:testDebugUnitTest` |

**`make check` is the single entrypoint in both places**, which for a solo
build is the most important property of the gate: one reproducible only by
pushing is one that gets bypassed.

**The integration suite skips wholesale when no Docker daemon is reachable**
(`tests/conftest.py`, module-level). On a machine without Docker, `make check`
passes having run none of the row-level-security probes and none of this unit's
concurrency tests. **A green run on such a machine is not evidence for anything
in § 3.** The CI precondition assertion that would close this is a repository-
wide item `team.md` assigns to "before D1" and it does not exist yet.

---

## 2. Methodology: the predicate, applied item by item

The contract's ordering is **a predicate, not a list**. Test-first wherever
*both* hold: the correct output is knowable from the requirement without having
written the code, **and** a wrong answer would be a money error or an
authorization error.

| Area | Predicate | Why |
|---|---|---|
| Freshness enumeration | **holds** | A non-enumerating checker fails silently; expected verdicts are stated in the design |
| Session generation idempotency | **holds** | The expected row count is in BR1.3 before any code |
| Lens resolution, six readers | **holds** | Authorization in the plainest sense; every expected outcome is tabulated in `security-design.md` § 2.2 |
| Version conflict + replay | **holds** | BR3.10/§ 5.4: a wrong ordering hands a stranger a roster in a 409 body |
| Refusal ordering | **holds** | Same |
| Mark range + partial index | **holds** | BR4.2's biconditional is knowable; a wrong answer publishes an absence the teacher never recorded |
| Marksheet bands + thresholds | **holds** | A band of one **is** a named mark — a disclosure, which is the authorization clause |
| Announcements | does not hold | No money, no authorization answer knowable in advance |
| Route plumbing | does not hold | Over an authz layer already proven test-first |
| Android queue + screens | does not hold | No Kotlin/Android experience [OC-3]; a Compose test written first is as likely to encode a framework misunderstanding as to catch a defect |

**No item escapes the predicate by being written in Kotlin or in a route
handler.** Nothing in D4's Kotlin scope meets it — the client computes no
balance and no authorization decision — but that is the predicate's content,
not an exemption by location.

**Test-after here is a cadence, not permission to write the test against the
implementation.** Every test-after test is written from its acceptance
criterion. If writing one requires reading the implementation to know what to
assert, the acceptance criterion is the defect and that is what gets fixed.

---

## 3. The three that a sequential test cannot prove

Each runs **N threads released together from a barrier**, against **real
PostgreSQL 16** via testcontainers, never SQLite. `tests/fees/test_generation_races.py`
and `tests/fees/test_verification_races.py` are the built shape to follow.

### 3.1 Generation idempotency [BR1.3, NFR6.51, NFR6.52]

`tests/teaching/test_generation_races.py`

- N overlapping generations for one batch → **exactly one** session row per
  `(batch_id, date, start_time)`.
- A re-run **on a later day** is idempotent too — the case concurrency alone
  misses, and the one the daily self-healing re-run needs.
- An **ad-hoc** session survives a generation pass with its `origin` unchanged
  and its attendance intact [BR1.4].

### 3.2 The version conflict [BR3.4, NFR6.44, NFR6.46]

`tests/teaching/test_attendance_races.py`

N rosters all carrying `base_attendance_version = V`, released together:

- exactly **one** 200 and **N−1** 409s;
- `attendance_version` is **V+1**, not V+N;
- the stored roster is **byte-identical** to the one that won — not merely
  "some roster is stored";
- exactly one `attendance_submission` row for that version, which the
  `UNIQUE (session_id, resulting_version)` constraint independently guarantees.

### 3.3 Replay under concurrency [BR3.8, NFR6.50, NFR19.34]

`tests/teaching/test_replay.py`

- The same body twice, **overlapping**: both return 200, one
  `attendance_submission` row, the version incremented **once**;
- **`created_at` unmoved** — see § 4.1;
- a **cross-account** replay (account B presenting account A's
  `client_mutation_id`) is refused and specifically is **not** a 200 carrying
  A's stored result [§ 5.2].

---

## 4. The six load-bearing assertions

Each is a case where the assertion a developer reaches for first passes against
the defect.

### 4.1 `created_at` unmoved on replay

A row-count assertion passes against an implementation that **overwrites the
original in place**: same row count, same version, the original decision's
timestamp destroyed. Assert the timestamp equality explicitly.

### 4.2 Byte-identical IDOR bodies

A guardian requesting a **non-child** enrollment id and a guardian requesting
an **invented** id must produce the same status, the same code and the same
body. **Assert equality over the two responses**, not two independent "is a
refusal" assertions — both of those pass while the bodies differ, and the
difference is the leak.

### 4.3 The band merge repeats

Assert `min(published band count) >= 3` **or zero bands published**, as a
property over generated mark lists (Hypothesis, as the ledger invariant does).

The worked case from `security-design.md` § 4.2 goes in as a named regression:
eight marks, band width 20, merging down to **one band of 8**. Only the
property form catches the single-pass bug — one merge pass can produce a
neighbour that is itself still under three.

### 4.4 Two threshold tests, not one

`tests/marks/test_marksheet_thresholds.py` — **a test per condition, each
holding the other satisfied**:

- four marked results, **all seats entered** → no comparison;
- eight marked results, **one seat `not_entered`** → no comparison.

A single test varying both at once passes while only one check is implemented.

### 4.5 Three absences on the toggle

With `marksheet_visible` false, assert the response carries **no exam count,
no exam list, and no empty marks array** — each individually. Asserting "not a
200" passes against a 200 carrying an empty list, and an empty marksheet still
discloses that exams exist and how many.

### 4.6 A second job stale while the fee job is fresh

`tests/fees/test_freshness_enumeration.py` — this is what distinguishes an
enumerating checker from one that reads the first row it finds. With the fee
job fresh and the session job stale, the check must report unhealthy **and name
the session job in the alert**.

Plus the existing three branches **under a non-default job name** (no row,
stale, fresh) — a test using the default name passes against a checker that can
only ever see the default name.

Plus **the empty registry**: zero `job_heartbeat` rows is **unhealthy**. The
loop body never runs, and a naive implementation returns 0, which reintroduces
the never-wired-scheduler failure through the new enumeration path.

---

## 5. The privacy probe matrix

`tests/privacy/test_teaching_probes.py`, following the built
`test_profile_probes.py` shape: **one boundary, four routes**, because an
implementation can block one and leave another open.

| Reader | Adversarial | Positive |
|---|---|---|
| Session roster | A declined seat is absent | An accepted seat is present |
| Session detail | Teacher A cannot read B's session | The owner reads it |
| Student attendance history | A pending seat reads nothing | An accepted student reads their own |
| Guardian attendance history | A declined guardian reads nothing | An accepted guardian reads their child's |
| Batch marksheet | Each lens refused on its own column | Each lens reads its own |
| Guardian progress | A non-child enrollment id is refused | The child's progress returns |

Each adversarial row is probed by **at least the direct and the join route** —
the join is the shape the real roster query has. Marks and attendance also
carry the **ORM traversal**, since those reads are ORM-shaped.

**The positive column is not decoration.** Without it the whole suite passes
against a policy that denies unconditionally, which is not the requirement.

**This suite runs as `APP_ROLE`**, a granted non-owner, non-superuser. The
built meta-test (`tests/privacy/test_rls_meta.py`) gates the package and
re-checks in an autouse fixture, because a probe suite running against a
missing policy reports a **pass** — the worst available outcome.

Three further probes, from § 2.4:

- a student reading another student's mark in the same exam;
- teacher A creating an exam with a `batch_subject_id` from teacher B's batch
  (refused, and refused as `NOT_AVAILABLE` rather than descriptively — naming
  the subject id as wrong is the oracle);
- teacher A reading teacher B's announcements.

---

## 6. Refusal ordering [§ 5.4, BR3.10]

`tests/teaching/test_refusal_order.py`

A caller with no lens on the session receives `NOT_AVAILABLE` and **never**
`ATTENDANCE_VERSION_CONFLICT` — run for **both a matching and a non-matching
version**.

Running both is the point: a probe using only a non-matching version cannot
distinguish correct ordering from an implementation that happens to check
authorization first by accident of control flow.

The hazard is concrete: `ATTENDANCE_VERSION_CONFLICT` carries `current_state`
in `error.details`, and `current_state` **is the roster**.

**Also assert the conflict is never logged with its roster** [NFR24.15]: the
conflict is interesting, so it will be logged; the error body already carries
the roster; and the obvious implementation logs the error body.

---

## 7. The rest

| Area | Module | Floor |
|---|---|---|
| Roster predicate | `tests/teaching/test_roster.py` | 5 — one per BR1.5 clause plus the membership set |
| Atomic roster | `tests/teaching/test_atomic_write.py` | 2 — fail on the k-th of 12 seats → **zero** rows and an unchanged version, not k−1 |
| Schedule history | `tests/teaching/test_schedule_changes.py` | 2 — BR1.2: four sessions byte-identical after a slot change |
| State refusals | `tests/teaching/test_state_refusals.py` | 2 — cancelled session, inactive batch; **assert existing rows are untouched** |
| Reschedule | `tests/teaching/test_reschedule.py` | 2 — same id, topic and attendance survive |
| Topic log | `tests/teaching/test_topic.py` | 3 — incl. BR2.2 unlogged vs logged-empty |
| Marks | `tests/marks/test_entry.py` | 7 — the biconditional CHECK, the upper bound, supersession, the partial index rejecting a second live row |
| Result states | `tests/marks/test_result_states.py` | 3 — three seats differing only in `joined_on` and row presence |
| Marksheet | `tests/marks/test_marksheet.py` | 5 — no per-student collection in the **schema**, absences excluded, disjoint two-batch scope |
| Guardian progress | `tests/marks/test_progress.py` | 3 — absent contributes no value; ordering asserted **in the response** |
| Announcements | `tests/teaching/test_announcements.py` | 4 — incl. **no expiry column and no scheduled job** |
| Contract | `tests/contract/` additions | 2 — `client_mutation_id` on **exactly** two D4 bodies; **no** `queue_state` anywhere |
| Android queue | `QueueStoreTest.kt` | 6 — persistence across restart, atomic rename under a simulated crash, four distinct states, **re-apply's fresh id** |
| Android mappers | per feature | state machine incl. the explicit retry path for a failed write |

**Governance needs no new test.** The built pair in `tests/db/test_governance.py`
covers both directions once the six entries exist, and the reachability pair
covers the grant. Writing a new one would duplicate a built control.

**`tests/db/test_migration_0006.py`** asserts the migration touches **no column
of `batch`** — `marksheet_visible` is already built and non-null.

---

## 8. Coverage

- **80% line floor**, CI-enforced, no decrease. May not be weakened to make a
  step pass.
- **`app/marks/marksheet.py` targets 100% branch.** It is pure computation with
  no I/O, no session and no HTTP, which is what makes 100% reachable — the same
  property that makes it true of `app/money/`.
- **The authorization layer is measured as branch coverage**, not line: lens
  resolution is pure branching over teacher, student, guardian and owned-batch
  membership, so line coverage on it is close to meaningless.
- **Kotlin coverage is reported**, with the no-decrease ratchet arming on the
  first merged figure.
- A red suite blocks. Coverage below floor blocks. Schema drift blocks. **A
  test that passes regardless of implementation is a defect in its own right.**

---

## 9. What is not tested, stated plainly

From `security-design.md` § 10, the six obligations with no automated verifier.
Listed so none is mistaken for covered:

| Obligation | Status |
|---|---|
| IDOR **timing** equality | Structural — one shared refusal path. **Not asserted**; a timing assertion on a shared host is flaky in both directions and would get muted |
| The RLS decision for D4's six tables | A recorded decision; the probes are what enforce the boundary |
| The RLS re-open trigger | **Nothing watches it.** The trigger is a column naming a reader |
| Queue encryption | A recorded acceptance [§ 7.2], flagged for the human |
| No child name or mark in a log line | **Nothing automated checks it.** Only the conflict-log shape has a test |
| No latency assertion on the attendance path | Review. This is the **deliberate position**, not a gap — PU-3.6 was dropped at Q14.3 answer C |

**The last row is an obligation to assert an absence.** D4 ships no
Macrobenchmark, no timing budget and no timing assertion on the attendance
path, and no correctness test is presented as discharging one.

---

## Testing Contract

Copied verbatim from
`aidlc engine testing-posture resolve --stage code-generation --unit teaching-and-recording`.

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

- **Test counts are floors, not targets.** The strategy asks five to eight per
  component; the concurrency and privacy areas exceed it because the design
  names more obligations than that, and no area is padded to reach a number.
- **`tests/teaching/` and `tests/marks/` mirror the two source packages**,
  following `tests/fees/`'s per-concern module shape. The design names no test
  layout.
- **The empty-registry case in § 4.6 is this document's addition.** The
  infrastructure design specifies enumeration but does not state what zero rows
  means. Treating it as healthy would reintroduce the never-wired failure.
- **No test in this unit asserts a latency, a duration or a timing budget.**
  That is BR7.4's requirement and § 9's last row, not an omission.
- **Nothing here was executed.** Docker is unavailable in this session, so every
  claim about a built test is from reading the file. The suite is specified, not
  measured.
