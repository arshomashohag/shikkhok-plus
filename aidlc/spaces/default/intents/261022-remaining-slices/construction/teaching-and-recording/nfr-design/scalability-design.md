# Scalability Design — D4 `teaching-and-recording`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **§ 2 is why this unit exists.** D4 does not move the scale ceiling and its
> growth is modest and computable. What it introduces is the product's **first
> optimistic concurrency path**, and the guarantee that path owes — *exactly
> one applies, N−1 are refused* — is the one property in this document that a
> sequential test cannot establish.
>
> Three distinct concurrency mechanisms land in this unit. They are designed
> in three separate subsections (§ 2.3, § 2.4, § 3.1) with a mapping table at
> § 2.1, because a design that blurs them invites the wrong one being reached
> for — and the right one is different for each hazard.
>
> Every figure below is computed in this file from an input stated here.

## Sources

- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.40–NFR6.58
- [upstream] `nfr-requirements/reliability-requirements.md` — NFR19.29,
  NFR19.33, NFR19.34, NFR19.39, NFR19.40, whose atomicity and idempotency
  guarantees the concurrency designs here enforce
- [upstream] `nfr-requirements/performance-requirements.md` — NFR20.24,
  NFR20.28, NFR20.29, the statement counts read against these row volumes
- [upstream] `nfr-requirements/security-requirements.md` — NFR14.62,
  NFR14.64, the replay and ordering properties § 2.5 must not break
- [upstream] `nfr-requirements/observability-requirements.md` — NFR25.18,
  NFR25.19, the counters that make the conflict rate answerable
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR17.4, NFR17.6
- [upstream] `functional-design/rules.md` — BR1.1, BR1.3, **BR3.3, BR3.4**,
  BR3.5, BR3.8, BR3.11, BR4.4, BR4.5
- [upstream] `functional-design/entities.md` — `Session`, `Attendance`,
  `AttendanceSubmission`, `Mark` and their constraints
- [upstream] `functional-design/functional-spec.md` §§ 2.1, 3.3, 3.4, **3.5**
- [upstream] `inception/delivery-planning/bolt-plan.md` — Bolt 4's confidence
  hypothesis
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.7,
  **§ B.8**
- [code] read 2026-10-24: `app/auth/otp.py:170`, `app/auth/tokens.py:234`,
  `app/fees/verification.py:117`, `app/db/models.py`,
  `tests/auth/test_ceilings.py:283`, `infra/modules/app/main.tf`

---

## 1. Growth, computed

### 1.1 The ceiling does not move [NFR6.40]

D4 adds no teacher, no student and no tenant. The ceiling remains **100
teachers and a few thousand students** [NFR6].

### 1.2 Row growth

Inputs, stated here: a batch of **8 to 20 students** [BR6.2]; a nominal
twice-weekly slot; 100 teachers at a nominal 5 batches each, giving **500
batches**. The nominal figures are assumptions, labelled in the closing
section.

| Table | Rate | Per batch per year | At 500 batches |
|---|---|---|---|
| `session` | 2 per week | 2 × 52 = **104** | **52,000** |
| `attendance` | 20 per session | 104 × 20 = **2,080** | **1,040,000** |
| `attendance_submission` | ≥ 1 per session held | ≥ **104** | ≥ **52,000** |
| `exam` | a nominal 10 per year | **10** | **5,000** |
| `mark` | 20 per exam + corrections | 10 × 20 = **200** | **100,000** |
| `announcement` | a nominal 2 per week | **104** | **52,000** |

### 1.3 `attendance` is the fastest-growing table, and no partitioning is designed [NFR6.41]

At roughly **one million rows a year** at the ceiling, `attendance` outgrows
every other table in the product. **No partitioning, archival or rollup is
designed for V1**, on the reasoning D3 recorded for the ledger [NFR20.14] and
re-checked here against D4's access pattern:

- a million rows is small for PostgreSQL;
- **every read is scoped to one session or one enrollment by an indexed key**;
- **no query in this unit scans the table** — which is the property that makes
  the first two safe rather than hopeful.

**Verifier: the statement-count assertions of `performance-design.md` § 2,
which fail if a read stops being key-scoped.** That is the real control: the
design is safe exactly while the access pattern holds, and the statement-count
test is what detects the access pattern changing.

**The trigger for revisiting**: a read that is not scoped by `session_id` or
`enrollment_id`. Stated so the decision has one.

### 1.4 Two tables grow append-only by design [NFR6.42, NFR6.43]

**`attendance_submission` grows at AT LEAST one row per session held**, more
under correction and conflict, because every accepted roster write appends a
row and **none is ever deleted**. This is deliberate: the row is the replay key
[§ B.7] and the version-increment guarantee [BR3.4], and both evaporate if old
rows are pruned.

Stated explicitly because "one row per session" is the figure a reader assumes,
and it is a **floor, not the rate**.

**`mark` grows append-only with a supersession chain** [BR4.4] — one row per
seat per exam **plus one per correction**. A correction never updates in place.

**Verifier for both: review of the migration for the absence of any cleanup
job**, plus for `mark` a test asserting a correction leaves the old row present
with `superseded_by_id` set and the partial unique index keeping exactly one
live row.

---

## 2. Concurrency

### 2.1 The three mechanisms, mapped

| Mechanism | Hazard | Shape of the hazard | Enforced by | Designed in |
|---|---|---|---|---|
| `client_mutation_id` | **replay** | The same decision arriving twice | `UNIQUE (submitted_by_account_id, client_mutation_id)` | § 2.5 |
| `attendance_version` | **conflict** | A decision composed against stale state | `UPDATE ... WHERE attendance_version = :base` | § 2.3 |
| natural-key insert | **duplicate generation** | Two runs creating the same occurrence | `ON CONFLICT DO NOTHING` | § 3.1 |

**They are not interchangeable and the failures differ.** Using the version
check where replay protection is wanted lets a reconnect re-apply a decision
the teacher made once. Using replay protection where a conflict check is wanted
lets a stale roster silently overwrite a correction. Using `ON CONFLICT DO
NOTHING` on a roster write would make a conflict look like a success.

### 2.2 The guarantee [NFR6.44]

**Of N attendance writes racing against the same `attendance_version` V,
exactly one applies and N−1 are refused as conflicts. Never two applied.
Never a silent overwrite.**

After the race:

- `session.attendance_version` is **V+1**, and **not V+N**;
- exactly **one** `attendance_submission` row exists with
  `resulting_version = V+1`;
- the stored roster is **byte-identical to the one that won**.

### 2.3 The mechanism: a conditional update, not a lock [NFR6.46]

```sql
UPDATE session
   SET attendance_version = :base + 1
 WHERE id = :session_id
   AND attendance_version = :base
```

**Zero rows affected means someone else won.** The check and the write are one
statement, so **no window exists between them** — which is the whole property.
A read-then-write has a window and is the defect this design exists to prevent.

**A pessimistic lock is wrong for this path specifically**, and the reason is
not a general preference. The product already uses `SELECT ... FOR UPDATE` in
three places, each guarding a genuinely concurrent request — verified by
reading `app/auth/otp.py:170`, `app/auth/tokens.py:234` and
`app/fees/verification.py:117`. **Here the contender is not a concurrent
request but a stale one**, composed hours earlier on a phone with no
connectivity. There is no transaction to hold open across that gap.

**This is the product's first optimistic path.** Verified by reading
`app/db/models.py`: **no version column exists on any of the 18 tables today.**

**Design constraint: no `SELECT ... FOR UPDATE` and no read-then-write appears
on this path.** Verifier: § 2.6's concurrency test, plus review for the absence
of both.

### 2.4 The second, independent guarantee [NFR6.47]

`UNIQUE (session_id, resulting_version)` on `attendance_submission` asserts the
**same fact by a different mechanism**: two writes cannot both claim version
N+1.

**Its purpose is survival of a rewrite.** The conditional update is the live
control; the constraint is what keeps the guarantee true if somebody later
rewrites that statement into a read-then-write. Two independent mechanisms
pointing at one guarantee is this project's habit where a rule matters — the
money boundary has two, the forbidden-identifier set has two.

**Verifier: the constraint's presence in the migration, plus a test asserting
two submissions cannot both claim version N+1** — asserted directly, not only
as a by-product of the race.

### 2.5 Replay under concurrency is a separate guarantee [NFR6.50]

**Two concurrent submissions carrying the same
`(submitted_by_account_id, client_mutation_id)` produce exactly one submission
row and one version increment; the loser returns the winner's stored result
with `200` rather than raising** [BR3.8, § B.7].

**This is distinct from § 2.2 and must be tested separately.** § 2.2 races
*different* decisions; this races *the same* decision arriving twice — the
reconnect-replay case the queue makes routine. **An implementation can satisfy
one and fail the other**, which is exactly why two tests rather than one.

The design: the unique constraint is what resolves the race, and the loser's
handler catches the integrity error and **re-reads the winner's row** rather
than raising. `created_at` is untouched [NFR14.63].

### 2.6 The test shape, and why a sequential test establishes nothing [NFR6.45]

**Design statement: the guarantee of § 2.2 may not be discharged by a
sequential test, and a sequential happy-path test does not count as coverage
of it.**

The reason is mechanical rather than stylistic: **a roster write guarded by a
version check passes every sequential test against an implementation with no
guard at all**, because nothing ever contends. The guard is invisible to a test
that never races. It would pass, it would be green, and it would certify
nothing.

**This is the exact shape of the worst defect D3 shipped** — a double-crediting
race on a path the database constraint did not cover, with every test calling
the service once. Eight racing verifications credited one payment eight times.

#### The designed shape

Copied from the built pattern at `tests/auth/test_ceilings.py:283`, which
releases **real threads from a barrier against real PostgreSQL via
testcontainers** and asserts the **outcome** rather than the absence of an
exception.

```python
# module scope, NOT inside the function
import threading

barrier = threading.Barrier(WORKERS)

def attempt(results: list[int], lock: threading.Lock) -> None:
    session = factory()
    try:
        barrier.wait(timeout=30)
        status = submit_roster(session, base_version=V, ...)
        with lock:
            results.append(status)
    finally:
        session.close()
```

Then assert, over the collected results:

| Assertion | Why it is not redundant |
|---|---|
| exactly one `200` | the "never two applied" half |
| exactly N−1 `409`s | catches a worker erroring for an unrelated reason |
| `attendance_version == V + 1` | catches N increments, the silent-overwrite shape |
| exactly one `attendance_submission` row | catches a second row with a duplicate version |
| the stored roster equals the winner's | catches a partial application |

**One deviation from the built pattern, stated deliberately.**
`tests/auth/test_ceilings.py:283` places `import threading` **inside the
function body**, which violates the project's imports-at-top rule. **The import
belongs at module scope here.** The pattern is worth copying; that line is not.

**Each worker needs its own session** — a shared session serialises the
workers and the test silently stops racing, which is the way this kind of test
most often becomes decoration.

### 2.7 Session-level granularity, and its stated cost [NFR6.48]

Granularity is **session-level**, inherited from ADR-006 and § B.8 rather than
chosen here. **Its cost is accepted explicitly: two devices marking DIFFERENT
students in the SAME session do conflict, and the second is refused.**

The alternatives are worse where it matters more:

| Granularity | Why rejected |
|---|---|
| Batch-level | Conflicts two unrelated sessions |
| Enrollment-level | Destroys AC3.1.5's atomic roster — per-seat versions are exactly the field granularity a roster deliberately does not have, and ADR-006 rejected per-field last-write-wins for that reason |

V1 has **no co-teaching** — a batch has one `owner_id` — so the conflicting
case is **one teacher on two devices**, which is the case ADR-006 was written
about.

**Verifier: none — this is a recorded acceptance, and stating it is the
point.** What makes the cost survivable is the conflict-resolution screen,
designed in `reliability-design.md` § 3.5.

### 2.8 Two counters, not one [NFR6.49]

**`topic_version` is a separate counter from `attendance_version`**, so a topic
write and a roster write for the same session do not conflict with each other.

One shared counter would **manufacture a conflict between two writes touching
disjoint columns** — a conflict the teacher cannot act on, because there is
nothing to compare and nothing to re-apply differently.

**Verifier: a test submitting a topic and a roster concurrently against the
same session and asserting BOTH apply.** The concurrent form is the one that
matters: sequentially, a shared counter also lets both succeed.

### 2.9 The mark-correction race [NFR6.53]

A mark correction is concurrency-safe by the **partial unique index** on
`(exam_id, enrollment_id) WHERE superseded_by_id IS NULL` [BR4.5]. Two
concurrent corrections cannot both leave a live row.

**Verifier: a concurrent-correction test asserting exactly one live row
survives** — barrier-released, for the reason in § 2.6.

Without the index, a correction that fails to set the old row's pointer leaves
**two live marks and the marksheet silently counts one student twice** —
which is also a disclosure defect, since the band counts would be wrong.

### 2.10 Interactive writes carry no version [NFR6.54]

Mark entry, exam creation, announcements, reschedule and the marksheet toggle
are **last-write-wins per field with correction history**, carry no version,
and cannot conflict [BR3.11].

**Stating this is what stops the queued-path rule from spreading.** Applied
everywhere, optimistic concurrency would make a teacher re-fetch before every
edit for no benefit.

**Verifier: a test asserting a mark write with no version field succeeds.**

---

## 3. The generation job as a concurrent surface

### 3.1 Idempotency is the constraint, not a guard [NFR6.51]

Session generation is idempotent by `UNIQUE (batch_id, date, start_time)` with
`ON CONFLICT DO NOTHING`, and **a conflict is the success path** [BR1.3].

**Verifier: N threads released together from a barrier leaving exactly one row
per occurrence — the third distinct concurrency test in this unit, and
assertable only concurrently.**

This follows the project's ALWAYS-rule for fee-cycle generation without
modification: a database constraint, never an application-level "has this
already run" guard.

### 3.2 Safe across days, not only across threads [NFR6.52]

**A missed day self-heals**, because the horizon is a function of the calendar
rather than of the last run [BR1.1, BR1.4], and re-running creates only what is
absent.

**Verifier: run generation twice on simulated consecutive days and assert the
row set is unchanged by the second run** — the case concurrency alone does not
reach, mirroring D3's NFR6.34.

### 3.3 No leader election, and the property that makes that safe [NFR6.55, NFR6.56]

The job's correctness **does not depend on running exactly once** [NFR6.39], so
it needs no leader election, no distributed locking and no exactly-once
delivery.

**The absence of double-firing today depends on `desired_capacity = 1`**
[`infra/modules/app/main.tf`]. If that capacity is ever raised, both the fee
job and the session job fire once per instance, and **the only thing between
that and duplicate rows is the unique constraint**.

**That is the correct safety net**, and it is why the guarantee is specified
against the **constraint** rather than against the scheduler's uniqueness.
Stated as a property rather than left as a happy accident, because **a capacity
change is an infrastructure edit that would not otherwise prompt anyone to
think about it**.

**Verifier: NFR6.51's concurrency test, which is exactly the multi-instance
case in miniature.**

---

## 4. Capacity

### 4.1 No new resource [NFR6.57]

D4 adds **no compute, no database tier and no managed service**, so it adds
nothing to the USD 50/month ceiling [OC-4]. The session job runs as a **second
cron entry on the host that already exists**, installed by `user_data.sh.tftpl`
[NFR1.7].

**Verifier: the absence of new resources in the Terraform diff.**

### 4.2 No queue ceiling on the device [NFR6.58]

The client's queue is bounded in practice by what one teacher can compose while
offline — on the computed figures, a roster of at most **20 entries per
session**. **No queue-size ceiling, eviction policy or backpressure mechanism
is designed for V1.**

**Verifier: none; stated so the absence is a decision.**

The reason it must stay absent: **a ceiling would need a discard rule, and
discarding a teacher's composed roster is precisely what BR3.6 forbids.** An
eviction policy here would be a business decision a sync layer is not
authorized to make.

### 4.3 No scaling mechanism is designed

The NFR design guide offers horizontal scaling, sharding, read replicas,
event-driven decoupling and CQRS. **None is applied, and that is a decision:**

| Pattern | Why not |
|---|---|
| Horizontal scaling | `desired_capacity = 1`; § 3.3 designs for a raise rather than performing one |
| Sharding | One million rows a year on one PostgreSQL instance [§ 1.3] |
| Read replicas | No read:write ratio problem; every read is key-scoped |
| Queue-based decoupling | The only queue is on the device, and it exists for connectivity rather than for load |
| CQRS | The marksheet is the one read model, and it is two statements [`performance-design.md` § 2.3] |

---

## Assumptions & Open Questions

- **The nominal figures in § 1.2 are this document's assumptions**, used to
  compute orders of magnitude: 5 batches per teacher, a twice-weekly slot, 10
  exams and 2 announcements a week per batch. I searched this record's
  `requirements.md`, the prior record's NFR6 and the feasibility constraint
  register, and found a ceiling of **100 teachers and a few thousand students**
  with no per-teacher batch count, slot count, exam count or posting rate
  anywhere. Each requirement states the *shape* of its bound; the figures
  illustrate it.
- **N in § 2.2 is not fixed by any upstream artifact.** BR3.4 says "N threads".
  A concrete N belongs to the test — the built ceilings pattern uses 8 — and
  the guarantee is the outcome property, which holds at any N above one.
- **No load test, soak test or capacity benchmark is designed for V1**, by this
  unit or any prior one. The pilot is the measurement, consistent with
  `performance-design.md` § 5.
- **The conflict rate is unmeasured and unmeasurable before the pilot.** § 2.7
  accepts a cost whose frequency nobody knows; `observability-design.md` § 3
  designs the counter that answers it, and the delivery plan records it as
  Bolt 4's confidence hypothesis. **If the rate turns out high, § 2.7's
  granularity decision is the thing to revisit** — and the counter is what
  makes that conclusion reachable rather than a matter of opinion.
- **I could not execute the built concurrency pattern.** Docker is unavailable
  in this session, so `tests/auth/test_ceilings.py:283` was read rather than
  run. The shape in § 2.6 is transcribed from that file, including the
  deviation I am deliberately not copying.
