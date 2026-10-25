# Code Summary — D4 `teaching-and-recording`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices
**Built**: 2026-10-25, both surfaces, two agents on disjoint file sets

> **Every figure below was measured by the orchestrator after the build**, not
> copied from a build report. Where a reported claim did not survive checking,
> § 6 says so.

## Sources

- [upstream] `code-generation/code-generation-plan.md` — the approved plan,
  steps 1–12
- [upstream] `code-generation/unit-test-instructions.md` — the Testing Contract
  and the six load-bearing assertions
- [upstream] `functional-design/rules.md` — BR1.1–BR7.5
- [upstream] `nfr-design/security-design.md` § 10 — the 24 collected obligations
- [measured] 2026-10-25: `make check`, `./gradlew :android:testDebugUnitTest
  --rerun-tasks`, and direct inspection of `message-keys.json`, both
  `strings.xml` bundles, `dispositions.py` and `app/contract/routes.py`

---

## 1. The gates, as they actually printed

| Gate | Result |
|---|---|
| `make check` | **All gates passed** |
| Ruff format | 240 files already formatted |
| Ruff check | All checks passed |
| mypy | no issues in 105 source files |
| Backend suite | **1202 passed, 0 skipped, 0 failed** |
| Money module | **100.00%** branch, floor 100% |
| Backend coverage | **92.05%** line, floor 80% (was 91% before D4) |
| Kotlin suite | **378 tests, 0 skipped, 0 failures**, 28/28 tasks executed |
| detekt, spotless, lintDebug | green; `HardwareIds` fatal and did not fire |
| Published message keys | **35**, all mapped, `missing=[]` |
| String bundles | **234** each, parity held |
| `dispositions.py` | **25** entries (19 before) |
| `PUBLIC_ROUTES` | **8**, unchanged |

**Zero skips on both surfaces is the load-bearing number**, not the pass. Docker
was running throughout, so every database test executed against real
PostgreSQL 16; the Kotlin figure is from `--rerun-tasks`, because a cached
`BUILD SUCCESSFUL` is evidence about a previous run.

---

## 2. What shipped

**Backend** — `migrations/versions/0006_teaching_and_recording.py` creating six
tables with a `NEW_TABLES` grant loop; `app/teaching/` (generation, roster,
sessions, submissions, announcements, commands) and `app/marks/` (exams, entry,
results, marksheet, views); routers `app/api/teaching.py` and `app/api/marks.py`;
schemas; six governance entries; the session-generation cron entry at 01:00 UTC;
the freshness check converted to enumerate every registered job.

**Android** — `core/queue/` (four files; serialized file with atomic rename),
`feature/sessions/`, `feature/attendance/`, `feature/marks/`, seven screens,
`TeachingDto.kt` and `MarksDto.kt`, 58 new strings per bundle, 13 new message
keys, and seven rows in `docs/delivery/bangla-layout-check.md` with lengths
computed from `values-bn/strings.xml` rather than estimated.

**Routes: 25, not the plan's 19.** The same seven groups, decomposed
differently — reschedule, cancel and subject became three routes rather than one
session-write. None is public and every one resolves a lens.

---

## 3. The three default-wrong things, each proved able to fail

The plan named three things this unit builds wrong by default. Each was built
correctly **and** had its test proved capable of failing:

1. **Refusal ordering** — the lens and both state checks resolve before any
   version comparison. Probed with a matching *and* a non-matching version, plus
   a byte-identical equality over the real-id and invented-id refusals, plus an
   assertion that no enrollment id or name appears in a stranger's refusal.
2. **Replay scoped by both columns** — tested in both directions: a cross-account
   replay refuses *and* is specifically not a 200 carrying A's result; two
   accounts legitimately sharing a UUID both succeed.
3. **The band merge repeats** — both worked cases reproduce exactly, plus two
   Hypothesis properties at 250 examples.

**Concurrency guards were proved by breaking them**, not assumed:

- Replacing `ON CONFLICT DO NOTHING` with read-then-insert made 7 of 8 workers
  raise `IntegrityError`. **This exposed a weak test**: the constraint still
  protected the data, so a row-count assertion passed while a per-slot `except`
  swallowed the failures. Strengthened to `results == [0] * WORKERS`.
- Removing `WHERE attendance_version = :base` makes the race test fail on
  `uq_attendance_submission_version` — the second independent mechanism firing
  exactly as BR3.4 designed.
- On the client, injecting the BR3.7 defect (re-apply reusing the old mutation
  id) failed **five** tests across store, sync and ViewModel.

---

## 4. The band edge case, found by computing rather than reading

The orchestrator computed both worked examples instead of reading them. Both are
correct as written — but **generating width-20 edges the obvious way produces a
top band of `80-99`, so a student scoring full marks falls into no band** while
still counting in the average, the rank and the five-result threshold.

The build hit it twice: a first edge loop produced `(80,99)`, a second produced
a degenerate `(100,100)`. The rule that holds for every total is **"if what
remains after this band is less than a full band, this band runs to the top"**,
verified contiguous and covering for totals 1, 19, 20, 21, 39, 40, 50, 99, 100
and 101. **Bands are computed over the exam's own scale, never a percentage**,
so no second rounding decision hides in a conversion.

The guard is the sum invariant: published band counts must total exactly the
number of marked results. That catches a gap anywhere in the edge set rather
than only at the top.

---

## 5. Three defects found in work that was already reported green

**5.1 A cached `BUILD SUCCESSFUL`.** Re-running the Kotlin suite printed
`BUILD SUCCESSFUL in 643ms / 28 up-to-date` having executed nothing.
`--rerun-tasks` gave one failure. This is the Docker-skip family in a worse
form: a skip prints `s`, while a cached pass is indistinguishable from a real
one.

**5.2 Thirteen unmapped message keys.** The backend's raise sites published 13
keys the client had no string for. Two spellings differed from what the client
had pre-mapped, and **`error.topic_version_conflict` was not on its list at
all** — BR2.1's topic log is the quiet second queued path, easy to forget
because every discussion of the conflict mechanism uses attendance as its
example. Two agents built from the same design, on disjoint files, and still
disagreed on names; the contract test is what caught it.

**5.3 An unreachable client state, found while fixing 5.2.**
`marksheet.not_published` was absent from the failing list because the backend
**correctly never emits it**: the toggle-off case refuses through the same
shared `refuse()` as an unreachable seat, so a family cannot learn that a
marksheet exists and is merely hidden. The client had branched on that code, so
`MarksheetHidden`, `afterMarksheetHidden()`, a screen branch, a test tag and two
strings were all **unreachable** — dead code reading as working behaviour.
Removed, with a note recording why no such state exists.

**The replacement assertion is equality, not two refusals**: a hidden marksheet
and an unreachable seat must map to *equal* client states. Two independent "is a
failure" assertions would both pass while the rendered states differed. **An
oracle closed on the wire is not closed until the client stops distinguishing
the cases too.**

---

## 6. One claim that did not survive checking

The backend reported `tests/auth/test_ceilings.py::test_the_sixth_within_a_day_is_refused`
as a pre-existing failure and correctly proved it so by stashing every D4 change.
The diagnosis was right — but it was **fixed rather than accepted**.

The test anchored six hourly sends to `datetime.now(tz=UTC)`, so a run after
roughly 19:00Z crossed midnight, the daily window reset, and the sixth was
admitted. It passed every morning and failed every evening since B3. Anchored to
a fixed start-of-day; the test already controlled the hour offsets and merely
anchored them to a moving point. **Mutation-checked**: with `PER_NUMBER_DAILY`
raised to 50 it still fails, so the flake is gone without weakening the
assertion.

---

## 7. Decisions the plan did not settle

| Decision | Resolution |
|---|---|
| Cron hour | **01:00 UTC** (07:00 Dhaka), clear of the fee job's 02:00 |
| Mark correction statement count | **Three, not two.** Partial uniqueness can only be an index and PostgreSQL cannot defer one, while the self-referential FK refuses a forward pointer. Point the old row at itself, insert, then correct — one transaction, so the self-pointer is never observable |
| `EXAM_TOTAL_BELOW_RECORDED_MARK` | Lowering a total below a live recorded mark is refused; the bound spans the FK in that direction too |
| Band scale | The exam's own scale, never a percentage |
| Route count | 25, same seven groups |
| `error.*` prefix inconsistency | Kept: it matches the `fees.*` precedent of keying by error identity rather than module. Stated rather than left silent |

---

## 8. For the human, at the learnings gate

1. **BR4.3 and BR1.5 read as if they share a roster predicate, and they
   cannot.** BR1.5 excludes seats with `joined_on > date`, which would make
   `joined_after` **unreachable** — the state exists precisely to say "on the
   batch, could not have sat this exam" [AC4.1.5]. They share two clauses, not
   three.
2. **`project.md`'s NEVER on local write queues contradicts its cited source.**
   NFR5 reads "Permitted for the mid-class path only"; the restatement dropped
   the scope. BR3.1 reconciles it. No memory file was edited.
3. **`team.md` is stale in three places** — the Android toolchain section (five
   tools listed absent that all exist), the `app.authz` strict-island note (the
   island has been configured since 2026-10-22), and the PU-3.6 Macrobenchmark
   bullet (an obligation Q14.3 removed).
4. **`tests/fees/` had no `__init__.py`.** D4's `test_generation.py` collided by
   bare basename and errored at collection — which is how a whole suite silently
   stops running. Markers added to three test packages.
5. **The CI Docker precondition was built this session** and is no longer open.

---

## Assumptions & Open Questions

- **Nothing in this summary is a build report's claim repeated.** Every gate
  figure was re-run by the orchestrator; § 6 records the one reported claim that
  was corrected rather than accepted.
- **The `tests/auth/test_ceilings.py` fix is outside D4's approved steps.** It
  was a pre-existing flake failing D4's gate, fixed and mutation-checked rather
  than excused. Flagged because it is scope the plan did not name.
- **No timing assertion, latency budget or Macrobenchmark exists on the
  attendance path**, and that is BR7.4's requirement rather than an omission.
  The two structural properties stand in its place and both are asserted.
- **Six obligations remain with no automated verifier**, unchanged from the
  plan: IDOR timing, the RLS decision and its unwatched trigger, queue
  encryption, and no-child-name-or-mark-in-a-log.
