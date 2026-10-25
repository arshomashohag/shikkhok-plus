# Performance Design — D3 `collecting-fees`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **The arithmetic is built and this design does not touch it.** `derive()`
> is one linear pass at 100% branch coverage. D3's performance design is
> about **how rows reach that fold**, and the only real decision is the shape
> of three statements.

## Sources

- [upstream] `construction/collecting-fees/nfr-requirements/performance-requirements.md`
  — NFR20.12–NFR20.23, NFR2.5, NFR3.4
- [upstream] `construction/collecting-fees/nfr-requirements/scalability-requirements.md`
  — NFR6.28, the row counts these query shapes are sized against
- [upstream] `construction/collecting-fees/nfr-requirements/tech-stack-decisions.md`
  — § 4 (`Money.format`), § 6 (SQLAlchemy event hooks)
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 2.4, 7, 11
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR3.5,
  BR6.1, BR6.2, BR6.6, BR7.1
- [upstream] `construction/collecting-fees/functional-design/entities.md` —
  `FeeCycle`, `LedgerEntry`, `PaymentClaim`, `ReminderEvent`
- [code] `app/money/_ledger.py:92-190`, `app/batches/service.py:440-495`,
  `app/authz/resolve.py:120-130`, read 2026-10-23

---

## 1. The fold is not re-designed, and that is the design

`derive()` takes `list[LedgerEntry]` and returns every derived quantity in one
pass: a single `for` at `_ledger.py:117`, a `match` closed by `assert_never`,
and both `defaultdict` accumulators filled inside that same loop. The only
iteration after it builds `per_cycle` over the **distinct periods**, which
months bound rather than entries.

| Requirement | Design |
|---|---|
| NFR20.12 — stays O(entries), single pass | D3 adds **no code inside `app/money/`** except `Money.format`, a pure formatter with no loop over entries |
| NFR20.13 — the per-cycle breakdown costs nothing extra | `derive()` already returns `per_cycle`. The rule: a caller wanting outstanding-per-period **reads `DerivedQuantities.per_cycle`**, never issues `GROUP BY period` and never folds twice |

**NFR20.13 is a prohibition on a plausible addition, so the design states what
is forbidden rather than what is added.** A reader who needs per-period
outstanding for the student's history screen has three options: read
`per_cycle` (correct), fold again with a period filter (a second pass), or
`GROUP BY period` in SQL (the arithmetic re-implemented outside the module that
owns it). Only the first is permitted, and it is already returned.

---

## 2. The three query shapes

This is the whole of D3's performance design. Each is a **bounded statement
count**, and the forbidden shape in each case is the per-row follow-up.

### 2.1 Batch-wide fee view — the teacher's screen [NFR20.16]

```
1. SELECT enrollment   WHERE batch_id = :batch       (the lens already scoped the batch)
2. SELECT fee_cycle    WHERE enrollment_id IN (:ids)
3. SELECT ledger_entry WHERE enrollment_id IN (:ids) ORDER BY enrollment_id
```

Then **group in Python by `enrollment_id` and call `derive()` once per
enrollment** over rows already in hand.

| Property | Why |
|---|---|
| **Three statements, constant in roster size** | The property NFR20.16 protects. Sixty students is three statements; so is six |
| The fold runs per enrollment, in Python | NFR20.16 is deliberate: a SQL `GROUP BY` would re-implement `derive()` in a second language, outside the import boundary and outside the 100% branch coverage |
| `ORDER BY enrollment_id` on statement 3 | Lets grouping be one pass over a sorted result rather than a dict accumulation. Either is correct; neither changes the statement count |

**The precedent is `list_batches`, stated precisely.**
`app/batches/service.py:440-495` runs three bounded statements — the batches,
one grouped aggregate over `Enrollment.batch_id.in_(batch_ids)`, one grouped
subject fetch over the same ids — **not one statement, and not one per batch**.
D3 copies the shape, not the aggregate: `list_batches` can aggregate in SQL
because a count is not money.

**Sizing, computed from this record's own figures.** At 60 students and 240
entries each — the five-year, four-per-month bound of NFR20.14 — statement 3
returns 60 × 240 = **14,400 rows** in one result set, and the Python side runs
60 `derive()` calls over 240 entries each: **14,400 loop iterations in total**,
the same work one fold over the same rows would do. Grouping adds one pass over
those 14,400 rows, so the view is two linear passes over 14,400 rows rather
than one. That is the cost NFR20.14 accepts.

### 2.2 Per-student and per-guardian fee view [NFR20.16]

```
1. SELECT fee_cycle    WHERE enrollment_id = :id
2. SELECT ledger_entry WHERE enrollment_id = :id
```

Two statements, one `derive()`. At the same five-year bound this folds **240
rows**.

**A guardian's read is the same two statements** against the child's enrollment
id, which `GuardianLens.child_enrollment_id` already carries
(`app/authz/resolve.py:120-130`) — so the lens supplies the scoping value and
the handler cannot compile the query without it.

### 2.3 Per-seat outstanding on the roster [NFR20.17]

This is what D2 deliberately left open, and the risk is that it is closed with
a query per seat: the roster is a list, so the per-row shape is the natural
one.

**It is closed by reusing 2.1's statements 2 and 3**, not by a new access path.

| Option | Statements for 60 seats | Verdict |
|---|---|---|
| `derive()` per seat, each fetching its own entries | 1 + 60 | **Rejected** — the N+1 shape, and the one D2 was careful not to create |
| The grouped fetch of 2.1, folded per seat | +2 over the roster's existing statements | **Chosen** |
| A `sum(CASE kind …)` aggregate in SQL | +1 | **Rejected**, and not for cost — see below |

**The third row is the one worth stating.** An aggregate looks cheapest and is
wrong for a reason that is not about cost: outstanding floors at zero **per
period and then sums** [BR3.5], so a signed `SUM` over all entries returns a
different number whenever one period is over-settled. `_ledger.py:174-178`
carries that reasoning and records that it took two wrong answers to reach.

---

## 3. The verifier [NFR20.18]

**A statement-count assertion, not a latency assertion.**

```
with count_statements(session) as counter:
    view = fee_view_for_batch(session, lens=lens, batch_id=batch.id)
assert counter.total == 3
```

| Property | Design |
|---|---|
| Mechanism | SQLAlchemy's `before_cursor_execute` event hook on the test engine, counting executions |
| Fixture | **Two roster sizes asserting the same count** — one seat and N seats. A single-size assertion passes against an N+1 implementation whenever N happens to equal the asserted number |
| What it asserts | The count, never the SQL text. A text assertion fails on a harmless rewrite and couples the test to the query it constrains |
| Where it lives | A shared helper, because D5's cross-batch dues query is the same obligation at a larger scale |

**The two-size fixture is what makes this a real verifier.** It is the same
defect class this project has recorded twice — a test whose name claims a
property it does not exercise. One roster size asserts "this ran three
statements"; two sizes assert "this runs the same number of statements however
many seats there are", which is the requirement.

**No latency target, and the reason is stated rather than omitted** [NFR20.18].
A millisecond assertion on a 2 GB shared host is flaky, and a flaky gate is a
bypassed gate. Nothing automated measures D3's fee-view latency; the property
that is verified is that cost does not scale with the roster.

---

## 4. Indexing [NFR20.19]

| Index | On | Why |
|---|---|---|
| Unique `(enrollment_id, period)` | `fee_cycle` | Supplies its own index. **It is the idempotency constraint first** and the read index incidentally |
| `(enrollment_id, period)` | `ledger_entry` | Every read filters on `enrollment_id`; the leading column serves both the single-enrollment read and the `IN (...)` grouped fetch |
| `(enrollment_id, status)` | `payment_claim` | The teacher's pending-claims view filters by status within a batch's enrollments |
| `(enrollment_id, period)` | `reminder_event` | The teacher-facing state is the **latest event per `(enrollment, period)`** [BR7.1], a lookup on exactly this pair |

**No index on `ledger_entry.kind`.** Seven values over a growing table is the
worst available selectivity, and no read path filters on kind alone: `derive()`
folds every entry for the enrollment and discriminates in Python. This is the
reasoning D2 recorded for its decision enums, applied again.

**No index on `payment_claim.transaction_id`.** Nothing looks a claim up by it;
it is displayed evidence. Indexing a claimant-authored personal reference would
also create a lookup path for a value NFR24.5 keeps out of logs.

---

## 5. Caching

**None**, and D3 is where the temptation is strongest.

A batch's fee view changes only when a cycle generates (monthly) or a claim is
verified (rarely). That is the textbook argument for caching it, and it is
exactly the staleness that would be worst here: **a cached balance that
disagrees with the ledger tells a person they owe the wrong amount.** The rule
is inherited — no cross-request cache [D1 NFR21.1] — and D3 seeks no exception.

**Nor a rollup table.** ADR-002 names a materialized rollup as the mitigation
*if* the fold bites [NFR20.15], and § 2.1's arithmetic says it does not.
Building it now creates the second source of truth `FeeCycle`'s thinness exists
to avoid [BR1.2], for a problem no figure in this record produces.

**What stays reserved**: append-only is what makes a rollup safe to add later,
because it can always be rebuilt from source. The mitigation stays available
without being built.

---

## 6. The generation job's cost [NFR20.20, NFR20.21, NFR20.22]

| Requirement | Design |
|---|---|
| NFR20.20 — commit per enrollment-period | One transaction per `(enrollment, period)`: insert the cycle, and **on a created row** append the `charge` and any `credit_apply`, then commit. A failure costs that one unit |
| NFR20.21 — cost bounded by candidates × periods | At 3,000 enrollments a normal day is **3,000 insert attempts**, nearly all of which conflict and do nothing. A three-day gap is still about 3,000, because three days usually spans **zero or one** period boundary |
| NFR20.22 — runs outside classroom hours | A scheduling-time property, held either way by the scheduler choice; see `reliability-design.md` § 6 |

**Credit application needs the enrollment's current fold**, which is one
`SELECT` of its ledger entries per enrollment being generated. That is **per
enrollment, not per row**, and it is unavoidable: `min(available, owed)` cannot
be computed without knowing the available credit. The design fetches **once per
enrollment** and reuses the fold across that enrollment's periods within the
run rather than re-fetching per period — which matters only in the recovery
case where one enrollment has several periods to generate, and which is exactly
the case a long outage produces.

---

## 7. Client [NFR2.5, NFR3.4, NFR20.23]

| Requirement | Design |
|---|---|
| NFR2.5 — device floor | New feature packages, **no new dependency**. The fee screens are Compose over the existing networking and serialization stack |
| NFR20.23 — no client arithmetic | Every balance and the status enum arrive **computed**. The ViewModel maps a response to a UI state; the composable renders it with no conditional over a domain value |
| NFR3.4 — Latin digits under Bangla | `Money.format(locale)` emits Latin digits, **agreeing** with `Numerals.kt` rather than deciding independently; `locale` governs grouping and the currency mark |

**NFR20.23 is the rule D3 is most likely to break, and the design names the
exact line**: `if (balance > 0) "Due"` is a business rule in presentation's
clothes. The fee status is a **server-computed enum** [BR6.1], so the client
switches on the enum and never on the amount. The first waiver separates the
two — a waived cycle has a zero balance and is not "Paid".

**The mechanical half is weaker than it should be, so it is stated plainly.**
The status enum arrives as a string the Kotlin side models as a sealed type, so
a composable comparing a `Money` to zero is a type-level oddity rather than a
natural line. But **there is no build gate asserting the absence of such a
comparison**: detekt is absent from this project [team: Code Style]. The
verifier for NFR20.23 is the ViewModel mapping test plus review, and review is
weaker than a gate on the surface this project names as the thinnest-reviewed.

---

## 8. `Money.format` stays inside the strict island

The method is added to `app/money/_money.py`: it takes a locale value and
returns a string, with **no I/O, no session and no HTTP**. That keeps
`app.money.*` importing nothing but `decimal` and its own value types, keeps
both import-boundary mechanisms green, and keeps 100% branch coverage reachable
— its branches being the locale cases, which are few and pure.

---

## Assumptions & Open Questions

- **Assumed**: the batch-wide fee view is **not paginated** in V1, on
  NFR20.11's reasoning (a citation of D2's requirement, not an ID defined
  here). What makes the absence safe is NFR20.23: because every figure is the
  server's, adding pagination later changes nothing a client computed.
- **Assumed**: the roster's per-seat outstanding is served by the fee view's
  grouped fetch rather than by widening the roster's own statements. Either
  satisfies NFR20.17; this one reuses a shape that already has the
  statement-count verifier attached.
- **Open, and D5's**: the cross-batch dues query — the same list-plus-fold
  across every batch a student belongs to, and the first read whose fold is not
  bounded by class size. It is where the shared statement-count helper earns
  its place.
