# Code Generation Plan — D4 `teaching-and-recording`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices
**Plan approval**: required before any code is written

> **This unit is the largest of the six and the one that first stores
> children's data.** Six new tables, nineteen routes, seven screens, a device
> write queue, and the product's first optimistic-concurrency path. The upstream
> design is unusually complete: `rules.md` carries 41 rules each with a
> `violation_behaviour` that names its own test, and `security-design.md` § 10
> collects 24 verification obligations and marks the six that nothing automated
> checks. **This plan adds no design.** Where it makes a choice the design left
> open, § 9 says so by name.
>
> **Three things in this unit are built wrong by default**, and each gets its
> own step rather than a line inside a larger one: re-apply reusing the old
> mutation id (BR3.7), the band merge running one pass instead of repeating
> (§ 4.2), and the conflict code being emitted before authorization (§ 5.4).

## Sources

- [upstream] `functional-design/entities.md` — six new tables, three read-only
- [upstream] `functional-design/rules.md` — BR1.1–BR7.5, 41 rules
- [upstream] `functional-design/functional-spec.md` — the workflows
- [upstream] `nfr-design/security-design.md` — §§ 1–10, the probe matrix and the
  24 collected obligations
- [upstream] `nfr-design/observability-design.md` — § 4.1, the heartbeat
- [upstream] `nfr-design/reliability-design.md`, `scalability-design.md`,
  `performance-design.md`, `logical-components.md`
- [upstream] `nfr-requirements/` — the six documents; NFR ids traced in
  `traceability.json`
- [upstream] `infrastructure-design/infrastructure-specification.md` §§ 3.2, 3.3
  (the freshness decision), `monitoring-design.md` § 4.1
- [upstream] `inception/units-generation/unit-of-work.md` — D4's boundary
- [human] 2026-10-25 — the queue is built, stored as a serialized file with
  atomic rename; the freshness check enumerates every registered job
- [code] read 2026-10-25: `app/fees/commands.py`, `app/fees/` package layout,
  `app/api/`, `app/db/models.py` (`JobHeartbeat`, `FEE_GENERATION_JOB`),
  `app/governance/dispositions.py`, `app/contract/routes.py`,
  `migrations/versions/` (five revisions), `tests/fees/`, `pyproject.toml`
  (the four strict islands), and the Android source tree

---

## 1. What this unit ships

| Surface | Count | Notes |
|---|---|---|
| New tables | 6 | `session`, `attendance`, `attendance_submission`, `exam`, `mark`, `announcement` |
| Migrations | **1** | `0006`, all six tables, with a `NEW_TABLES` grant loop |
| Governance entries | 6 | 19 today → **25** |
| Backend packages | 2 new | `app/teaching/`, `app/marks/` |
| Routes | 19 | every one resolves a lens; **no `PUBLIC_ROUTES` entry** |
| Android screens | 7 | session list, session detail+roster, conflict resolution, exam list, mark entry, marksheet, guardian progress |
| Cron entries | 1 | session generation |
| Modified existing files | 4 | `commands.py`, `dispositions.py`, `models.py`, `user_data.sh.tftpl` |

**The `PUBLIC_ROUTES` frozenset is not touched.** It holds eight entries and
`tests/contract/test_route_lenses.py:76,104` asserts that count in two places,
so a D4 route added to it fails `make check` rather than passing quietly.

---

## 2. Build order

Ordered so each step is verifiable when it lands, and so the two steps that
cannot be proven without real PostgreSQL come after the schema exists.

| # | Step | Ordering |
|---|---|---|
| 1 [x] | Models and migration `0006` | — |
| 2 [x] | Governance entries (6) | — |
| 3 [x] | The freshness check enumerates jobs | **test-first** |
| 4 [x] | Session generation + the cron entry | **test-first** (BR1.3 idempotency) |
| 5 [x] | The lens-scoped read layer | **test-first** (BR5.1, BR5.2) |
| 6 [x] | The queued write path: version + replay | **test-first** (BR3.3, BR3.4, BR3.8) |
| 7 [x] | Exams, marks, supersession | **test-first** for BR4.2/BR4.5, after for the rest |
| 8 [x] | The marksheet: bands, thresholds, aggregates | **test-first** (disclosure) |
| 9 [x] | Announcements, student/guardian reads | test-after |
| 10 [x] | The API layer, 19 routes | test-after, over a test-first authz layer |
| 11 | Android: queue, then mappers, then screens | test-after |
| 12 | The Bangla per-screen rows, 7 | file check |

### Why the ordering splits where it does

The Testing Contract's ordering is **a predicate, not a list**: test-first
wherever *both* the correct output is knowable from the requirement without
having written the code **and** a wrong answer is a money error or an
authorization error. Applied item by item rather than by surface:

**The predicate holds** for steps 3–8. Step 5 and step 6 are authorization in
the plainest sense — BR3.10 and § 5.4 make a wrong ordering hand a stranger a
class's roster in a 409 body, and the expected output of every probe in
`security-design.md` § 2.2 is stated in the design before any code exists. Step
8 is a disclosure boundary: a band of one is a named mark, and the merge's
expected output is computed in § 4.2 already. Steps 3 and 4 are authorization-
adjacent in the way the predicate's second clause actually bites — a silently
non-enumerating checker and a non-idempotent generator both fail *quietly*,
which is the property the clause is about.

**The predicate does not hold** for steps 9–11. Announcement rendering, the
route plumbing over an already-tested authz layer, and Compose UI have no money
or authorization answer knowable in advance, and `team.md` is explicit that a
Compose test written before the implementation is as likely to encode a
framework misunderstanding as to catch a defect.

**No item escapes the predicate by being in Kotlin.** Nothing in steps 11's
scope meets it — the Android queue holds no business rule, because the client
computes no balance and no authorization decision — but the exemption is from
the predicate's content, not from its reach.

---

## 3. Backend: the two new packages

### 3.1 `app/teaching/`

| Module | Holds |
|---|---|
| `generation.py` | BR1.1–BR1.4. Insert with `ON CONFLICT DO NOTHING` on `(batch_id, date, start_time)`; horizon = current calendar month + next |
| `roster.py` | BR1.5's four-clause predicate, as **one** indexed query |
| `sessions.py` | Create ad-hoc, reschedule (BR1.7), cancel, the topic write |
| `submissions.py` | **The queued write path.** BR3.3–BR3.8 |
| `announcements.py` | BR7.1 |
| `commands.py` | `main_generate_sessions()`, the cron entry point |

`submissions.py` is the unit's centre of gravity and is written as one function
with the sequence spelled in the order § 5.4 requires:

```
resolve lens  -> no reach: AuthorizationError(NOT_AVAILABLE)   [before anything]
replay check  -> (submitted_by_account_id, client_mutation_id) exists:
                 return the ORIGINAL stored result, 200, write nothing
state checks  -> cancelled session / inactive batch: ConflictError
conditional   -> UPDATE session SET attendance_version = :base + 1
                 WHERE id = :id AND attendance_version = :base
                 rowcount 0 -> ConflictError(ATTENDANCE_VERSION_CONFLICT)
apply         -> INSERT attendance_submission; upsert one attendance row per seat
                 all in ONE transaction
```

The replay lookup is scoped by **both** columns. A lookup on
`client_mutation_id` alone finds another account's row and returns it, which
§ 5.2 names as the implementation that ships as a silent success.

### 3.2 `app/marks/`

| Module | Holds |
|---|---|
| `exams.py` | BR4.1, including the subject-belongs-to-batch check |
| `entry.py` | BR4.2, BR4.4 (append + supersede in one transaction) |
| `results.py` | BR4.3's four states, two of them derived |
| `marksheet.py` | BR6.2–BR6.5. **Pure computation, no I/O and no session** |
| `progress.py` | BR6.6, ordered by exam date **in the query** |

`marksheet.py` takes a list of results and returns the published shape. Keeping
it free of I/O is what makes the property test over generated mark lists cheap,
and it mirrors why `app/money/` can hold 100% branch coverage.

### 3.3 Modified: `app/fees/commands.py`

Three changes, implementing the human's option B:

1. `main_check_freshness()` reads **every** `job_heartbeat` row and calls the
   already-parameterised `check_generation_freshness(session, job_name=...)`
   once per row. It returns 1 if **any** job is unhealthy.
2. The `log.critical` `extra` carries **the row's own `job_name`**, replacing
   the hardcoded `FEE_GENERATION_JOB` at `:251`.
3. A new verb is **not** added, and `main()`'s dispatch is unchanged. The host
   invocation at `user_data.sh.tftpl:470-478` stays a bare `check-freshness`
   with no argument — that is the property that made option B the choice.

**The zero-rows case is the one to get right.** With no heartbeat rows at all,
the loop body never runs and a naive implementation returns 0 — healthy — which
is the never-wired-scheduler failure arriving by a new route. The check treats
**an empty registry as unhealthy**, because a system with no registered job is
a system whose jobs are not registered.

`STALENESS_THRESHOLD` stays a single 48-hour module constant. Both jobs use 48
hours (`observability-design.md` §§ 287, 349), so a per-job registry would be
configuration for a difference that does not exist — the "decision wearing a
question's clothes" shape. It becomes a registry when two jobs disagree, and
that sentence is the trigger.

### 3.4 Modified: `app/governance/dispositions.py`

Six entries, transcribed from the prior catalogue, not invented:

| Table | Disposition | Basis source |
|---|---|---|
| `session` | per prior catalogue | batch history |
| `attendance` | `RETAIN_WITH_BASIS` | the enum's own docstring names attendance |
| `attendance_submission` | **= `attendance`'s** | holds nothing `attendance` does not |
| `exam` | `RETAIN_WITH_BASIS` | prior catalogue |
| `mark` | `RETAIN_WITH_BASIS` | the enum's docstring names marks |
| `announcement` | per prior catalogue | "stays with the batch's history" |

`RETENTION` is derived from `DISPOSITIONS` by comprehension (`:279-281`), so
this is **one entry per table, not two**. Each `basis` is prose a parent could
read, over the 20-character floor `test_every_disposition_states_a_basis`
enforces.

### 3.5 Migration `0006`

One migration, six tables, following `0005`'s shape exactly:

- a `NEW_TABLES` tuple and a grant loop over it, never six statements;
- the partial unique index on `mark` where `superseded_by_id IS NULL`;
- the `CHECK ((result_state = 'marked') = (marks IS NOT NULL))` biconditional;
- `UNIQUE (batch_id, date, start_time)`, `UNIQUE (session_id, enrollment_id)`,
  `UNIQUE (submitted_by_account_id, client_mutation_id)`,
  `UNIQUE (session_id, resulting_version)`;
- **no column on `batch`.** `marksheet_visible` is already built and non-null
  (`app/db/models.py:589`); a test asserts this migration touches no `batch`
  column.

The `marks <= exam.total_marks` bound spans a foreign key, so it is enforced in
the write path and asserted by a test, as `entities.md` states.

---

## 4. The API layer: 19 routes

Every route declares a dependency whose **return annotation is a `Lens`
subtype** — the built enumeration test matches on the annotation, not on a
function name — and scopes its query by the value the lens carries, never by an
id from the request body.

| Group | Routes | Lens |
|---|---|---|
| Sessions | list, detail, create ad-hoc, reschedule, cancel, topic write | Teacher |
| Attendance | roster read, **roster submit** | Teacher |
| Exams | list, create, edit | Teacher |
| Marks | exam results read, mark write, correction history | Teacher |
| Marksheet | batch marksheet, **toggle write** | Student/Guardian; Teacher for the toggle |
| Announcements | list, post, edit, delete | Teacher + Student/Guardian for the read |
| Family reads | student batch view, guardian batch view, guardian progress | Student, Guardian |

Two routes carry `client_mutation_id` and **no others**:
`POST /v1/sessions/{id}/attendance` and `PUT /v1/sessions/{id}/topic`. § B.7
names the four writes explicitly and says that enumerating them is what makes
the rule reviewable, so generalising it would contradict a decision rather than
extend one. A schema-level assertion over the generated OpenAPI document checks
exactly this pair.

**No response schema carries a `queue_state` field** (BR3.9), asserted by
iterating the document rather than per endpoint.

---

## 5. Android

### 5.1 The queue — the human's storage choice

`core/queue/`, holding:

| File | Holds |
|---|---|
| `QueuedWrite.kt` | The serializable item: target, payload, `base_version`, `client_mutation_id`, state |
| `QueueState.kt` | **Four** states: `Queued`, `Confirmed`, `Failed`, `Conflicted` |
| `QueueStore.kt` | **Serialized file + atomic rename** |
| `QueueSync.kt` | Automatic sync on connectivity, no teacher action |

**Atomic rename, concretely**: serialize to `queue.json.tmp` in the **same
directory**, `fsync`, then `File.renameTo(queue.json)`. Same directory because
a rename across filesystems is a copy, which is not atomic. A crash leaves
either the old complete file or the new complete file, never a truncated one —
which is the failure a plain overwrite has mid-class on a low-end device.

**`Failed` and `Conflicted` are visually distinct** (BR3.2, AC3.1.10).
`Conflicted` never schedules an automatic retry: retrying as-is is guaranteed
to be refused again, and a retry wrapper that strips the version would
overwrite.

**Re-apply composes a NEW write** with the **current** version and a **freshly
generated** `client_mutation_id` (BR3.7). Reusing the old id would hit the
replay path, return 200, and change nothing — reporting success for the exact
opposite of what the teacher asked. This gets its own test.

### 5.2 Screens and features

`feature/sessions/`, `feature/attendance/`, `feature/exams/`,
`feature/marks/`, extending the existing `feature/<name>/{StateMapper,
UiState,ViewModel,ui/}` convention. Seven screens, each with a row in
`docs/delivery/bangla-layout-check.md` (BR7.5) — **a screen with no row means
an incomplete unit.**

The conflict-resolution screen renders two rosters side by side, which is the
densest Bangla text this unit ships and the layout most likely to break at the
longest string.

**No composable contains a conditional on a domain value.** The server sends
decisions; `if (balance > 0) "Due"` is a business rule in presentation's
clothes. Every string goes in both `strings.xml` bundles.

---

## 6. Tests

Organised by what they prove. Counts are floors.

| Area | Tests | Shape |
|---|---|---|
| Session generation | 6 | incl. **BR1.3 concurrent**, ad-hoc untouched, BR1.2 history frozen |
| Roster predicate | 5 | one per BR1.5 clause plus the membership set |
| **Version conflict** | 4 | incl. **BR3.4 concurrent**, N threads from a barrier |
| **Replay** | 4 | incl. concurrent, cross-account, **`created_at` unmoved** |
| Refusal ordering | 2 | both a matching and a non-matching version |
| Atomic roster | 2 | fail on the k-th seat → **zero** rows, version unchanged |
| Marks | 7 | the biconditional CHECK, the bound, supersession, partial index |
| Marksheet | 9 | the worked case, the **property** test, two threshold tests, disjoint batches |
| Privacy probes | 12+ | six readers × (adversarial + positive), direct and join |
| IDOR equality | 2 | **byte-identical** bodies, not two independent refusals |
| Freshness | 4 | no row / stale / fresh under a non-default name, **plus a second job stale while the fee job is fresh** |
| Governance | 0 new | the built pair covers it once the six entries exist |
| Android | 20+ | queue persistence across restart, re-apply's fresh id, state mappers |

### The three that a sequential test cannot prove

Each runs N threads released together from a barrier against **real
PostgreSQL**, never SQLite:

1. **Generation idempotency** — exactly one row per `(batch_id, date, start_time)`.
2. **Version conflict** — exactly one 200 and N−1 409s; `attendance_version` is
   V+1 and **not** V+N; the stored roster is byte-identical to the winner's.
3. **Replay** — one submission row, one increment, `created_at` unmoved.

A roster write guarded by a version check **passes every sequential test
against an implementation with no guard at all**, because nothing ever
contends. That is the exact shape of D3's double-crediting defect.

### The assertions that are load-bearing rather than obvious

- **`created_at` unmoved.** A row-count assertion passes against an
  implementation that overwrites the original in place.
- **Byte-identical IDOR bodies.** Two independent "is a refusal" assertions
  both pass while the bodies differ, and the difference is the leak.
- **`min(published band count) >= 3` over generated lists.** The worked case
  catches the regression; only the property form catches the single-pass bug.
- **Two separate threshold tests**, each holding the other condition satisfied.
  One test varying both passes while only one check exists.
- **Three absences on the toggle** — no exam count, no exam list, no empty
  array. Asserting "not a 200" passes against a 200 carrying an empty list.
- **A second job stale while the fee job is fresh.** This is what distinguishes
  an enumerating checker from one that checks the first row it finds.

### Coverage

80% line floor, no decrease, `make check` the single entrypoint locally and in
CI. `app/marks/marksheet.py` is pure computation and targets 100% branch, on
the money module's reasoning. The authorization layer is measured as **branch**
coverage — lens resolution is pure branching and line coverage on it is close
to meaningless. **Kotlin coverage is reported**; the ratchet arms on the first
merged figure.

---

## 7. Definition of done

- `make check` green: Ruff, Ruff format, mypy (including the **already-strict**
  `app.authz.*` island, which D4's six readers land inside), pytest, coverage,
  the schema-diff gate, governance both directions, route enumeration, the
  privacy field gate, the money-name gate.
- The committed OpenAPI schema regenerated and the diff reviewed.
- Six governance entries; `dispositions.py` at **25**.
- Seven rows in `docs/delivery/bangla-layout-check.md`.
- **No timing assertion anywhere on the attendance path** (BR7.4).

**No manual pilot check is required.** PU-3.6 was dropped at Q14.3 answer C;
D4 is not incomplete without it.

---

## 8. What this unit does not do

- No RLS policy on the six tables — none has a column naming its reader.
  `attendance_submission.submitted_by_account_id` names the **writer** and no
  read is ever scoped by it.
- No `PUBLIC_ROUTES` entry, no new error class, no new exception.
- No migration on `batch`.
- No announcement push — V1's named FCM triggers are the fee reminder and
  entered marks, and D3 built the adapter.
- No Macrobenchmark, no latency budget, no timing assertion.
- No queue encryption — recorded in § 7.2 as an acceptance, flagged for the
  human there.
- No Schemathesis, no screenshot harness, no Docker precondition assertion:
  repository-wide items the infrastructure design lists as open.

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

The same block appears in `unit-test-instructions.md`, where § 2 applies its
`ordering` predicate item by item across this unit.

---

## Assumptions & Open Questions

- **The cron hour is this plan's proposal: 01:00 UTC (07:00 Dhaka).** The
  design constrains it only to complete before the earliest plausible class and
  not to collide with the fee job's 02:00 UTC. No upstream artifact fixes it.
- **`STALENESS_THRESHOLD` stays one shared constant**, because both jobs use 48
  hours. This is a choice, with its trigger stated in § 3.3: it becomes a
  per-job registry when two jobs disagree.
- **An empty `job_heartbeat` registry is treated as unhealthy.** The design
  does not state this case. Returning healthy for "no jobs registered" would
  reintroduce the never-wired failure through the new enumeration path.
- **Two packages rather than one `app/teaching/`.** The design names no package
  layout. Marks and the marksheet are split out because `marksheet.py` is pure
  computation that must stay free of I/O for its coverage target, and burying it
  in a package full of session I/O invites a session parameter.
- **The generation horizon — current calendar month plus next — is the
  functional design's stated assumption**, not an upstream decision, and
  NFR20.29's 9,000-insert figure moves with it.
- **The band width of 20 is the functional design's choice**, not upstream.
- **Route count 19 is this plan's decomposition** of the workflows in
  `functional-spec.md`, which names the operations but not their route split.
- **`project.md`'s NEVER on local write queues contradicts its cited source.**
  NFR5 reads "Permitted for the mid-class path only"; the restatement dropped
  the scope. BR3.1 reconciles them and this plan builds the four-state queue.
  **For the human at a learnings gate; no memory file is edited here.**
- **Three upstream artifacts remain stale** and are the human's: `team.md`'s
  Android toolchain section and its `app.authz` note (the island **is**
  configured, `pyproject.toml:222-226`), and `team.md`'s PU-3.6 Macrobenchmark
  bullet, which names an obligation Q14.3 removed.
