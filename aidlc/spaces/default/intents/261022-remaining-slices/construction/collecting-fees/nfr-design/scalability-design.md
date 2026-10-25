# Scalability Design — D3 `collecting-fees`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> At 100 teachers on one host, most of this design is a statement of what the
> product does **not** need. The one real design is **the concurrency
> mechanism and the two tests that prove it** — because D3 is the first unit
> whose writer is a job rather than a person, and because the obligation has
> been deferred since the practices were written.

## Sources

- [upstream] `construction/collecting-fees/nfr-requirements/scalability-requirements.md`
  — NFR6.26–NFR6.39, NFR7.6
- [upstream] `construction/collecting-fees/nfr-requirements/performance-requirements.md`
  — NFR20.14, the ledger-growth figures this file's capacity table rests on
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3.1, 3.2, 3.3
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR1.3,
  BR1.4, BR4.1, BR4.3, BR4.5, BR5.7
- [code] `app/db/models.py:292-311`, `tests/auth/test_ceilings.py:283-320`,
  `infra/modules/app/main.tf:323-335`, read 2026-10-23

---

## 1. Scaling architecture

| Axis | Design | Why not more |
|---|---|---|
| **Horizontal (app)** | Two Uvicorn workers on one host, unchanged | NFR6.26 does not move the ceiling: 100 teachers, a few thousand students |
| **Vertical** | The Phase 2 lever, not this unit's | |
| **Database** | Single PostgreSQL 16, no read replica | Every D3 read is enrollment-filtered and index-served; § 5's figures show why |
| **Partitioning / sharding** | **None** | `ledger_entry` is the first table that would ever justify one, and at 720,000 rows over five years it does not. A shard key is expensive to reverse |
| **Queue-based decoupling** | **None** | The only async-shaped work is the push dispatch, which is fire-after-commit and best-effort [NFR19.21, NFR19.23] |
| **Scheduled work** | **One daily job**, the product's first [NFR6.38] | |

**Stateless by construction, and D3 must not break it.** The app holds no
session state; the lens is resolved per request. D3's temptation is a
generation run that keeps progress in process memory — "which enrollments have
I done" — which would be worker-local and would make a restart mid-run lose
its place. **The run's progress is the committed rows themselves**, which is
what makes the job restartable, re-runnable and overlappable without any
coordination.

---

## 2. The concurrency mechanism

### 2.1 The constraint is the lock [NFR6.30]

```
UNIQUE (enrollment_id, period) ON fee_cycle
INSERT ... ON CONFLICT DO NOTHING
```

**An application-level "has this already run?" guard is forbidden**, because
it passes a sequential test and fails with two workers — and Phase 1 has two.

**The precedent is in this repository and D3 follows it rather than inventing
a second one.** `RateLimitCounter`'s `UniqueConstraint`
(`app/db/models.py:302-310`) carries the reasoning already:

> The unique constraint is what makes the atomic upsert-and-increment
> possible: two workers racing on the same window cannot both read a stale
> count, because the second one conflicts and updates instead.

D3 is the same shape with `DO NOTHING` in place of `DO UPDATE`.

### 2.2 The ordering that carries three guarantees [NFR6.31, NFR6.36, NFR6.37]

```
BEGIN
  INSERT INTO fee_cycle (...) ON CONFLICT DO NOTHING RETURNING id
  IF no row returned:  COMMIT and move on          ← the success path
  INSERT ledger_entry (charge, ...)
  compute available credit from this enrollment's fold
  INSERT ledger_entry (credit_apply, min(available, owed))   ← if positive
COMMIT
```

| Guarantee | Where it comes from |
|---|---|
| **No double charge** [NFR6.31] | The `charge` is appended **if and only if the insert created a row**. The row's creation is the idempotency token; the conflict path appends nothing |
| **Credit is never applied before the charge** [NFR6.36] | `min(available, owed)` computed before the charge is `min(available, 0)` and applies nothing — a **silent no-op**, not an error, which is why ordering is specified rather than left to the implementer |
| **Two workers cannot spend one credit twice** [NFR6.37] | Credit is enrollment-scoped [BR4.1], so two workers generating two periods for one enrollment could each see the same available credit. Only the worker whose insert created the row appends anything at all, so the insert-conflict gate serialises them |

**NFR6.37 is the non-obvious one.** The constraint is per `(enrollment,
period)`, so two *different* periods for one enrollment do not conflict with
each other — both inserts succeed, and both would compute credit against the
same pre-existing available balance. The design's answer: **within one run, one
enrollment's periods are generated sequentially in one worker**, with the fold
recomputed after each period's commit. Across two concurrent runs of the whole
job, each period is still claimed by exactly one worker via the constraint, so
the second worker's insert conflicts and it appends nothing — including no
`credit_apply`.

> **This is the one place where the constraint alone is insufficient and the
> design adds a rule.** The constraint serialises *per period*; spending one
> credit across *two periods* needs the sequential-within-enrollment rule
> above. Stated explicitly because it is exactly the kind of gap a reader
> would assume the constraint already closes.

### 2.3 The other concurrent path [NFR6.35]

Two verifications racing on one claim converge on **one** decision; the second
is a `ConflictError`. The mechanism is a conditional update:

```
UPDATE payment_claim SET status = 'verified', ... WHERE id = :id AND status = 'pending'
```

Zero rows updated means another verification won, and the handler raises
`ConflictError` — not a second set of ledger entries, because double-crediting
a payment is a money error and correction is a distinct path [BR5.7].

---

## 3. The concurrency test [NFR6.32, NFR6.33]

**The built precedent is `tests/auth/test_ceilings.py:283` —
`test_genuinely_concurrent_requests_never_exceed_the_limit` — and it is the
model.** What to copy, verbatim in spirit:

| Property | Value |
|---|---|
| Real threads against **real PostgreSQL** | testcontainers; SQLite emulates neither `ON CONFLICT DO NOTHING` nor the constraint |
| Released together from a `threading.Barrier(workers)` | So they contend on the same `(enrollment_id, period)` **at the same moment**, not merely in quick succession |
| `workers = 8` | The precedent's figure; enough to lose a race reliably on a shared host |
| The assertion is the **outcome**, not the absence of an exception | See below |
| The connection is the restricted role | The same `restricted_engine` fixture the precedent takes |

### The assertion [NFR6.33]

After N overlapping generations for one `(enrollment_id, period)`:

- **exactly one** `fee_cycle` row exists for that pair;
- the ledger's **charged total equals one period's charge** — not N times it;
- `derive()` over the enrollment's entries returns the outstanding one charge
  produces.

**Not an internal call count.** An assertion that the insert was attempted N
times and succeeded once couples the test to the implementation it exists to
constrain; the outcome assertion survives a rewrite.

### One detail not to copy

**The precedent does `import threading` inside the test function
(`test_ceilings.py:296`).** That is contrary to this project's standing rule
that imports go at the top of the file, it is pre-existing and harmless where
it sits, and it is **not D3's to fix** — but it is exactly the kind of detail
that travels with the good parts when a test is modelled on another. **D3's
concurrency test puts its imports at the top of its file.**

### The warning the precedent carries

The same file records, beside a test renamed after it was found to run two
checkers one after the other:

> A test whose NAME claims a property it does not exercise is worse than no
> test, because the next reader believes the property is covered.

A sequential two-run test here passes against an implementation with **no
atomicity at all** — the exact implementation the constraint exists to
prevent.

---

## 4. The across-days test [NFR6.34]

**Concurrency does not reach this case, and it is the one the daily
self-healing job depends on.** It is also the one that is easy to skip,
because the concurrency test looks like it covers generation.

| Step | Assertion |
|---|---|
| Run the job for day N | Cycles exist for the periods due through N |
| Run for day N+1 | Row set and ledger total **unchanged**, unless N+1 crossed a period boundary |
| Run for day N+1 **again** | Row set and ledger total **identical to the previous step** |

**Time is injected, not slept.** The job takes the current date as a parameter
with a default of today, so the test advances the clock by passing a date —
which also makes the period-boundary case testable without waiting a month.
A test that patched the system clock would be testing the patch.

**Two further cases this test shape makes cheap and the design requires:**

- **A gap**: run for day N, skip to day N+62, assert the two intervening
  period boundaries both generated — this is NFR19.10's self-healing property,
  verified here rather than only asserted.
- **A re-run after a gap heals it**: the third run changes nothing, which is
  what distinguishes "it caught up" from "it keeps catching up".

---

## 5. Growth and capacity

| Table | Growth rate | Five-year figure | Bound |
|---|---|---|---|
| `fee_cycle` | One row per generating enrollment per month | At 3,000 enrollments: 3,000/month, **36,000/year**, 180,000 over five years | Enrollments × months [NFR6.27] |
| `ledger_entry` | Two to four per enrollment per month | At four: 12,000/month, **144,000/year**, **720,000 over five years** | **Unbounded, accepted** [NFR6.28] |
| `payment_claim` | One per submission | Person-driven, below the ledger's | [NFR6.29] |
| `reminder_event` | One per reminder including failures | Teacher-driven, below the ledger's | [NFR6.29] |

**NFR6.28 is a recorded acceptance with a stated reason, not an omission.**
An append-only financial record whose old rows are deleted no longer
reconstructs the balance it claims to derive. The ledger is **retained in
full by design**, and the formal record of that is the disposition row
[NFR10.15] rather than this table.

**The precedent that makes this worth stating twice**: `rate_limit_counter`
was found at D1 with a declared 48-hour retention and nothing enforcing it —
a decision made in the right place with nothing behind it. Here the position
is the opposite and deliberately so.

**Every read is enrollment-filtered**, so the figure that governs query cost
is **entries per enrollment** (240 at the five-year bound), not the table
total. 720,000 rows on `db.t4g.micro` with the leading-column index of
`performance-design.md` § 4 is unremarkable.

---

## 6. The job as a scaling surface [NFR6.38, NFR6.39, NFR7.6]

**D3 introduces the product's first scheduled job.** I searched `app/`,
`infra/`, `.github/workflows/` and the `Makefile` for a scheduler, cron,
APScheduler or Celery and found none; the one `cron` match is unrelated
(`infra/modules/cdn/main.tf`).

| Requirement | Design |
|---|---|
| NFR6.39 — safety does not depend on running exactly once | It may run twice, overlap itself, or miss three days. §§ 2–4 make all three safe, which is what permits the cheapest scheduler available |
| NFR7.6 — no recurring cost | Both candidate mechanisms run on the host that already exists. No managed scheduler, no second compute target, no new IAM |

**The scheduler choice itself is the human's and is not made here** — see
`reliability-design.md` § 6, which states what differs between the two options
and what holds either way.

**What this design does fix, because it is not the scheduler's to decide:**

- **The job is a management command taking no required arguments and safe to
  run at any time.** That is what makes a missed run recoverable by a person
  as well as by the next run, and it holds under either scheduler.
- **No leader election, no distributed lock, no advisory lock.** The
  constraint is the lock. Adding one would be a second coordination mechanism
  over a guarantee the database already provides, and the two would have to be
  reconciled during an incident.

### The capacity property the safety rests on

`infra/modules/app/main.tf:331-333` pins the group at
`min_size = max_size = desired_capacity = 1`, and its comment says so
deliberately: "not a scaling range that happens to start at one."

**At one instance neither scheduler option can fire twice.** If that capacity
is ever raised, both fire once per instance — and the only thing between that
and double-billing is the `(enrollment_id, period)` constraint with
`ON CONFLICT DO NOTHING`. That is the correct safety net, and it is why the
guarantee is specified against the constraint rather than against the
scheduler's uniqueness. **It should be a stated property rather than a happy
accident**, because raising capacity is an infrastructure edit that would not
otherwise prompt anyone to think about billing.

---

## 7. What D3 adds no scaling mechanism for

| Need | Why nothing is added |
|---|---|
| A read replica | Every D3 read is enrollment-filtered and index-served at the figures of § 5 |
| Partitioning `ledger_entry` by period | A real mechanism for a problem 720,000 rows does not produce |
| A job queue | The push adapter is best-effort with no retry queue [NFR19.23]; generation needs none [NFR6.39] |
| A cache or rollup | `performance-design.md` § 5; ADR-002 names the rollup as the mitigation if the fold ever bites, and it does not |
| Connection-pool changes | D3 adds one more concurrent workload class — the job — on a host with two workers. The job is one connection at a time |

---

## Assumptions & Open Questions

- **Assumed**: 3,000 enrollments as the working figure for "a few thousand
  students". NFR6 states the ceiling in words; 3,000 is its upper reading, so
  § 5's figures are the pessimistic ones.
- **Assumed**: four ledger entries per enrollment per month, matching the
  performance file's generous bound. A seat paying on time produces two.
- **Assumed**: one enrollment's periods are generated sequentially within a
  worker (§ 2.2). The alternative — parallelising within an enrollment — would
  need the credit computation to be serialised some other way, which is a
  mechanism this scale does not justify.
- **Open, and D5's**: the cross-batch dues query spans every batch a student
  belongs to rather than one teacher's batch, so it is the first read whose
  fold is not bounded by class size.
