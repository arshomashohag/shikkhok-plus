# Scalability Requirements — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **The concurrency section is this unit's reason for existing, and it is § 2.**
> D4 does not move the scale ceiling and its data growth is modest and
> computable. What it introduces is the product's **first optimistic
> concurrency path**, and the guarantee that path owes — *exactly one applies,
> N-1 are refused* — is the single requirement in this document that a
> sequential test cannot establish.
>
> Every figure below is computed in this file from a stated input.

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3. A bare `NFR6.32`, `NFR6.39` or
> `NFR20.21` below is a **citation** of an earlier unit's requirement, never an
> ID defined here.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ 2.1, 3.3, 3.4, **3.5**
- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.1, BR1.3, **BR3.3, BR3.4**, BR3.5, BR3.8, BR3.11, BR4.4, BR4.5
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  `Session`, `Attendance`, `AttendanceSubmission`, `Mark`
- [upstream] `inception/delivery-planning/bolt-plan.md` — Bolt 4's confidence
  hypothesis
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR6
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.7,
  **§ B.8**
- [code] `app/auth/otp.py:170`, `app/auth/tokens.py:234`,
  `app/fees/verification.py:117`, `app/db/models.py`,
  `tests/auth/test_ceilings.py` — read 2026-10-24

---

## 1. Growth

**NFR6.40** — D4 does not move the scale ceiling. It remains 100 teachers and
a few thousand students [NFR6]. **Verifier: none required; stated so the
figures below are read against a fixed ceiling.**

### Row growth, computed from stated inputs

Inputs: the batch size ceiling of **8 to 20 students** [BR6.2]; a nominal
twice-weekly slot; the two-month generation horizon [BR1.1]; 100 teachers at a
nominal 5 batches each. The nominal figures are this document's assumptions
and are labelled as such in the closing section.

| Table | Rate | Per batch per year | At 500 batches |
|---|---|---|---|
| `session` | 2 per week | 2 × 52 = **104** | **52,000** |
| `attendance` | 20 per session | 104 × 20 = **2,080** | **1,040,000** |
| `attendance_submission` | ≥ 1 per session held | ≥ **104** | ≥ **52,000** |
| `exam` | a nominal 10 per year | **10** | **5,000** |
| `mark` | 20 per exam, plus corrections | 10 × 20 = **200** | **100,000** |
| `announcement` | a nominal 2 per week | **104** | **52,000** |

**NFR6.41** — `attendance` is the fastest-growing table in the product at
roughly **one million rows a year** at the ceiling, and that is accepted
without partitioning, archival or a rollup for V1. The reasoning is the same
D3 recorded for the ledger [NFR20.14]: a million rows is small for PostgreSQL,
every read is scoped to one session or one enrollment by an indexed key, and
no query in this unit scans the table. **Verifier: the statement-count
assertions of `performance-requirements.md` § 2, which fail if a read stops
being key-scoped.**

**NFR6.42** — `attendance_submission` grows at **at least** one row per session
held, and more under correction and conflict, because **every accepted roster
write appends a row and none is ever deleted**. This is deliberate: the row is
the replay key [§ B.7] and the version-increment guarantee [BR3.4], and both
evaporate if old rows are pruned. Stated explicitly because "one row per
session" is the figure a reader assumes and it is a floor, not the rate.
**Verifier: review of the migration for the absence of any cleanup job.**

**NFR6.43** — `mark` grows **append-only with a supersession chain** [BR4.4],
so its rate is one row per seat per exam **plus one per correction**. A
correction never updates in place. **Verifier: a test asserting a correction
leaves the old row present with `superseded_by_id` set [BR4.4], and the partial
unique index of BR4.5 keeping exactly one live row.**

---

## 2. Concurrency — the requirement this unit exists to get right

### 2.1 The guarantee

**NFR6.44** — Of **N** attendance writes racing against the same
`attendance_version` V, **exactly one applies and N-1 are refused as
conflicts**. Never two applied. Never a silent overwrite. After the race,
`session.attendance_version` is **V+1 and not V+N**, and the stored roster is
byte-identical to the one that won [BR3.4].

**Verifier: a concurrency test — N real threads released together from a
barrier, against real PostgreSQL via testcontainers — asserting exactly one
`200`, N-1 `409`s, the resulting version, and the stored roster. The existing
pattern to follow is `tests/auth/test_ceilings.py:283`, which D3's NFR6.32
already used.**

### 2.2 Why a sequential test establishes nothing here

**NFR6.45** — The guarantee of NFR6.44 **may not be discharged by a sequential
test**, and a sequential test of the happy path does not count as coverage of
it. **Verifier: the concurrency test itself; the requirement here is on the
test's shape, checkable in review.**

The reason is mechanical rather than stylistic: **a roster write guarded by a
version check passes every sequential test against an implementation with no
guard at all**, because nothing ever contends. The guard is invisible to a test
that never races. It would pass, it would be green, and it would certify
nothing.

**This is the exact shape of the worst defect D3 shipped** — a double-crediting
race on a path the database constraint did not cover, with every test calling
the service once. The project's affirmed posture already mandates the
concurrent shape for fee-cycle idempotency ("overlapping concurrent
generations, never sequential calls"), and the reasoning transfers to this
path without modification.

### 2.3 The mechanism, and its two independent guarantees

**NFR6.46** — The guarantee is enforced by a **conditional update**, not a
lock:

```
UPDATE session
   SET attendance_version = :base + 1
 WHERE id = :session_id
   AND attendance_version = :base
```

**Zero rows affected means someone else won.** The check and the write are one
statement, so no window exists between them. **Verifier: NFR6.44's concurrency
test, plus review that no `SELECT ... FOR UPDATE` and no read-then-write
appears on this path.**

A pessimistic lock is wrong for this path specifically, and the reason is not a
general preference: **the contender is not a concurrent request but a stale
one**, composed hours earlier on a phone with no connectivity. There is no
transaction to hold open across that gap. This is why D4 adds an optimistic
path to a product whose only three concurrency primitives today are
`SELECT ... FOR UPDATE` — at `app/auth/otp.py:170`, `app/auth/tokens.py:234`
and `app/fees/verification.py:117`, each guarding a genuinely concurrent
request.

**NFR6.47** — `UNIQUE (session_id, resulting_version)` on
`attendance_submission` is a **second, independent** guarantee of the same
fact, and it is what makes the guarantee survive somebody later rewriting the
conditional update into a read-then-write. **Verifier: the constraint's
presence in the migration, plus a test asserting two submissions cannot both
claim version N+1.**

Two independent mechanisms pointing at one guarantee is this project's habit
where a rule matters: the conditional update is the live control, the
constraint is the backstop.

### 2.4 The cost of session-level granularity, stated

**NFR6.48** — Granularity is **session-level**, inherited from ADR-006 and
§ B.8 rather than chosen here, and its cost is accepted explicitly: **two
devices marking different students in the same session do conflict**, and the
second is refused. **Verifier: none — this is a recorded acceptance, and
stating it is the point.**

The alternatives are worse where it matters more. Batch-level would conflict
two unrelated sessions. Enrollment-level would destroy AC3.1.5's atomic roster,
because per-seat versions are exactly the field granularity a roster
deliberately does not have — and ADR-006 rejected per-field last-write-wins for
that reason. V1 has no co-teaching (a batch has one `owner_id`), so the
conflicting case is one teacher on two devices, which is the case ADR-006 was
written about.

**NFR6.49** — `topic_version` is a **separate counter** from
`attendance_version`, so a topic write and a roster write for the same session
do not conflict with each other [entities.md]. **Verifier: a test submitting a
topic and a roster concurrently against the same session and asserting both
apply.** One shared counter would manufacture a conflict between two writes
touching disjoint columns — a conflict the teacher cannot act on, because
there is nothing to compare and nothing to re-apply differently.

### 2.5 Replay under concurrency

**NFR6.50** — Two **concurrent** submissions carrying the **same**
`(submitted_by_account_id, client_mutation_id)` produce exactly one submission
row and one version increment; the loser returns the winner's stored result
with `200` rather than raising [BR3.8, § B.7]. **Verifier: a barrier-released
concurrency test over the duplicate id, asserting one row, one increment, and
two `200` responses carrying the same result.**

This is distinct from NFR6.44 and must be tested separately. NFR6.44 races
*different* decisions; this races *the same* decision arriving twice — which is
the reconnect-replay case the queue makes routine. An implementation can
satisfy one and fail the other.

---

## 3. Other concurrent paths in this unit

**NFR6.51** — Session generation is idempotent by
`UNIQUE (batch_id, date, start_time)` with `ON CONFLICT DO NOTHING`, and a
conflict is the success path [BR1.3]. **Verifier: N threads released together
from a barrier leaving exactly one row per occurrence — the third distinct
concurrency test in this unit, and assertable only concurrently.**

**NFR6.52** — Generation is safe across **days** as well as across threads: a
missed day self-heals because the horizon is a function of the calendar rather
than of the last run, and re-running creates only what is absent [BR1.1,
BR1.4]. **Verifier: run generation twice on simulated consecutive days and
assert the row set is unchanged by the second run** — the case concurrency
alone does not reach, mirroring D3's NFR6.34.

**NFR6.53** — A mark correction is concurrency-safe by the **partial unique
index** on `(exam_id, enrollment_id) WHERE superseded_by_id IS NULL` [BR4.5].
Two concurrent corrections cannot both leave a live row. **Verifier: a
concurrent-correction test asserting exactly one live row survives.**

**NFR6.54** — Interactive writes carry no version and cannot conflict
[BR3.11]. Mark entry, exam creation, announcements, reschedule and the
marksheet toggle are last-write-wins per field with correction history.
**Verifier: a test asserting a mark write with no version field succeeds.**
Stating this is what stops the queued-path rule from spreading: applied
everywhere, optimistic concurrency would make a teacher re-fetch before every
edit for no benefit.

---

## 4. The generation job as a scaling surface

**NFR6.55** — Session generation inherits D3's job properties unchanged: its
correctness does not depend on running exactly once [NFR6.39], so it may run
twice, overlap itself or miss days, and needs no leader election, distributed
locking or exactly-once delivery. **Verifier: NFR6.51 and NFR6.52's tests.**

**NFR6.56** — The absence of double-firing risk depends on
`desired_capacity = 1` [`infra/modules/app/main.tf`]. If that capacity is ever
raised, both the fee job and the session job fire once per instance, and the
only thing between that and duplicate rows is the unique constraint. That is
the correct safety net and it is why the guarantee is specified against the
**constraint** rather than against the scheduler's uniqueness. **Verifier:
NFR6.51's concurrency test, which is exactly the multi-instance case in
miniature.** Stated as a property rather than left as a happy accident, because
a capacity change is an infrastructure edit that would not otherwise prompt
anyone to think about it.

---

## 5. Capacity planning

**NFR6.57** — D4 adds no compute, no database tier and no managed service, so
it adds nothing to the USD 50/month ceiling [OC-4, NFR7]. The session job runs
as a second cron entry on the host that already exists. **Verifier: the
absence of new resources in the Terraform diff.**

**NFR6.58** — The client's queue is bounded in practice by what one teacher can
compose while offline — on the computed figures, a roster of at most 20 entries
per session — so no queue-size ceiling, eviction policy or backpressure
mechanism is specified for V1. **Verifier: none; stated so the absence is a
decision.** A ceiling would need a discard rule, and discarding a teacher's
composed roster is precisely what BR3.6 forbids.

---

## Assumptions & Open Questions

- **The nominal figures in § 1 are this document's assumptions**, used to
  compute orders of magnitude: 5 batches per teacher, a twice-weekly slot, 10
  exams and 2 announcements a week per batch. I searched this record's
  `requirements.md`, the prior record's NFR6, and the feasibility constraint
  register, and found a ceiling of **100 teachers and a few thousand students**
  with no per-teacher batch count, slot count, exam count or posting rate
  anywhere. The requirements state the *shape* of each bound; the figures
  illustrate it.
- **N in NFR6.44 is not fixed by any upstream artifact.** BR3.4 says "N
  threads". A concrete N belongs to the test, and the requirement is the
  outcome property — one applied, N-1 refused — which holds at any N above one.
- **No load test, soak test or capacity benchmark is specified for V1**, by
  any unit of this product. D4 does not introduce one. The pilot is the
  measurement, which is consistent with `performance-requirements.md` § 5.
