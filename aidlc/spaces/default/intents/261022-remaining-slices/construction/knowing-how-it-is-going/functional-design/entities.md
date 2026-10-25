# Entities — D5 `knowing-how-it-is-going`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 creates no table, adds no column, and ships no migration.** It is the
> only unit of the six with an empty schema change, and that is a finding
> rather than an omission: every figure it shows is derived from the ledger
> and the exam rows D3 and D4 already built [A5]. A unit that reads is still
> a unit — the risk here is **arithmetic over existing rows**, not storage.
>
> This document therefore reads as a **read model**: which existing tables
> each figure derives from, which columns drive it, and — the part that
> matters most — **which ledger kinds count as money received and which do
> not**. Getting that wrong overstates a teacher's headline earnings number,
> which is a money error on the most-looked-at screen in the product.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D5's scope, and
  OQ-2's carried decision
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — the five
  US rows that map here
- [upstream] `inception/requirements-analysis/requirements.md` — FR7.1–FR7.3,
  FR8.1, FR8.2, FR8.4, and assumption A5
- [upstream] `inception/domain-design/components.md`
- [prior] `261016-.../inception/user-stories/stories.md` — AC7.1.1–AC7.1.5,
  AC8.1.1, AC8.1.2, AC8.2.1, AC8.2.2, AC8.4.1–AC8.4.3
- [prior] `261016-.../inception/delivery-planning/external-dependency-map.md`
  — OQ-2 and its stated fallback
- [code] read 2026-10-25: `app/db/models.py` (`LEDGER_KIND_VALUES`,
  `LedgerEntryRow`, `FeeCycle`, `Exam`, `Enrollment`, `Batch`),
  `app/money/_kinds.py`, `app/money/_ledger.py`, `app/fees/views.py`
  (the D3 N+1 fix), `app/fees/balances.py`, `app/marks/exams.py`

---

## 1. Tables read, and nothing written

| Table | Read for | Written |
|---|---|---|
| `ledger_entry` | every figure in FR8.1, FR8.2, and the dues balance | **never** |
| `fee_cycle` | the period a dues row belongs to | **never** |
| `enrollment` | which seats are this teacher's, and the decision columns | **never** |
| `batch` | ownership, and the batch name on a dues row | **never** |
| `exam` | the next upcoming exam [FR8.4] | **never** |
| `batch_subject` | that exam's subject name | **never** |

**D5 adds no governance entry**, because it creates no table — the manifest
stays at 25. Stated rather than omitted, because every other unit of this
record added rows and an absent section reads as a forgotten obligation.

---

## 2. The ledger vocabulary, which is the whole design

The seven kinds are built and closed [`app/db/models.py:75-83`]. What D5 adds
is a **reading** of them, and the reading is where a wrong answer becomes a
wrong number on a teacher's screen.

| Kind | Money arrived? | In FR8.1 earnings? |
|---|---|---|
| `charge` | no — an obligation created | no |
| `receipt` | **yes** | **yes** |
| `credit_grant` | **yes** — money received in excess of what was owed | **yes** |
| `credit_apply` | **no** — held credit spent, received in an earlier month | **no** |
| `forgiveness` | no — a waiver is not cash | no |
| `carry_forward` | no — an accounting move between periods | no |
| `carried_out` | no — the other side of the same move | no |

**This is not this document's invention.** `app/money/_kinds.py:58-60` states
it in the built code: *"Cash in is receipts **plus** credit grants: money
received as credit is money received."* D5 is the first consumer of that
sentence.

### The double-count, computed rather than asserted

Running the case rather than reasoning about it, because this record carries a
carry-forward figure that reached four files before anyone executed it:

```
Month 1: owes 1000, student hands over 1500
         -> receipt 1000, credit_grant 500
Month 2: owes 1000, settled from held credit plus cash
         -> credit_apply 500, receipt 500

Cash in, M1 (receipt + credit_grant):  1500
Cash in, M2 (receipt + credit_grant):   500
                                       ----
Total:                                  2000   <- what was actually handed over

If credit_apply counted as cash in:
Cash in, M2 would read                 1000
Total would read                       2500   <- overstated by 500
```

**The overstatement is exactly the credit, counted once when it arrived and
again when it was spent.** It inflates the teacher's headline earnings figure
and it inflates it silently — every row balances, because `credit_apply` is a
real entry for a real amount.

**Verifier: a named test over this exact two-month case**, asserting 2000 and
not 2500. Test-first by the predicate: the correct output is knowable from the
requirement without the code, and a wrong answer is a money error.

---

## 3. The read models

Not tables. These are the shapes the three reads return, named so the rules
and the API have something to refer to.

```yaml
read_models:

  - name: DuesRow
    description: >
      One person who owes money, in one batch, right now [FR7.1]. The
      unit of the cross-batch dues view. **Membership is driven by
      outstanding balance and NOT by active status** [FR7.2]: a student
      who left owing money still appears, which is the single most
      load-bearing sentence in this unit.
    derived_from: [enrollment, batch, ledger_entry, fee_cycle]
    fields:
      - name: enrollment_id
        note: >
          The seat, never a global account id. A teacher-lens response
          carries no `student_account_id` [BR5.3 of D4, and the built
          privacy gate that enforces it].
      - name: display_name
        note: >
          What the TEACHER recorded, never a student-authored profile
          field. The built gate in `app/contract/privacy.py` fails the
          build on a teacher-lens schema carrying an owner-private
          field, so this is enforced rather than remembered.
      - name: batch_id
      - name: batch_name
        note: AC7.1.1 requires the batch, because the same person may owe in two.
      - name: outstanding
        type: Money
        note: >
          From `derive(entries).total_outstanding`, the built fold. D5
          computes no money arithmetic of its own and adds nothing to
          `app/money/`.
      - name: oldest_unpaid_period
        note: >
          Which period the debt starts in. **The built
          `oldest_unpaid_period` must NOT be called per row**: it takes
          one `enrollment_id` and calls `derive_for_enrollment`, so one
          call per dues row is a query per seat -- the exact N+1 § 4
          forbids, reached by reusing a correct function at the wrong
          granularity. D5 computes it from the SAME in-memory fold the
          outstanding balance comes from, as the minimum period whose
          per-cycle balance is above zero. Same definition, same
          `per_cycle` map, no second query.

  - name: MonthlyEarnings
    description: >
      Money actually received in one calendar month, across every batch
      this teacher owns [FR8.1]. **Zero is a value, not an empty state**
      [AC8.1.2] -- zero earned is a fact about the month, and rendering
      it as "no data" tells the teacher their records are missing when
      they are complete.
    derived_from: [ledger_entry, fee_cycle, enrollment, batch]
    fields:
      - name: period
        note: The fixed-width period key, so lexical order IS chronological order.
      - name: received
        type: Money
        note: "`receipt` + `credit_grant` for the period. See section 2."

  - name: EarningsTrend
    description: >
      The monthly series in date order [FR8.2]. **Fewer than two months
      returns no trend** [AC8.2.2], because a single point is not a
      trend -- and a one-point chart implies a direction it cannot know.
    derived_from: [MonthlyEarnings]
    fields:
      - name: months
        note: >
          Ordered by period ascending IN THE QUERY, never sorted in the
          client. A client sorting a domain list is the second of the
          five erosion paths `team.md` names.

  - name: NextExam
    description: >
      The soonest future exam across every batch this teacher owns
      [FR8.4]. Absent when none exists, which the client renders as a
      defined empty state [AC8.4.2].
    derived_from: [exam, batch, batch_subject]
    fields:
      - name: exam_id
      - name: title
      - name: batch_name
      - name: subject_name
      - name: date
      - name: days_remaining
        note: >
          **Whole days, computed server-side** [AC8.4.1]. A client
          computing it from a date would use the device clock, which
          this product already rules out for decisions [D4's BR3.3
          note], and would disagree across time zones.
```

---

## 4. What D5 reads that it must not widen

**`ledger_entry` is read per enrollment and folded in memory**, following the
shape D3 arrived at after its N+1 defect [`app/fees/views.py:337-357`]: one
`IN (:seat_ids)` select, then a fold, never a query per seat. D5 widens the
seat set from one batch to every batch the teacher owns, which makes the
statement-count property **more** important rather than less: at the scale
ceiling a teacher has a nominal five batches of up to twenty seats, so a
per-seat query is up to a hundred statements for one screen.

**The dues query's membership predicate is the one place D5 departs from D4's
roster predicate**, and it departs deliberately:

| Predicate | D4's roster [BR1.5] | D5's dues [FR7.2] |
|---|---|---|
| `inactive_from` | **excludes** an inactive seat | **does not exclude** — a student who left owing still appears |
| `student_decision` | excludes `declined` | excludes `declined` |
| batch ownership | the lens's `owner_id` | the lens's `owner_id` |

**The `inactive_from` row is the difference and it is the requirement.** A
dues view that reuses the roster predicate silently drops exactly the people
most worth chasing. This is the inverse of the trap D4 recorded — there,
BR4.3's `joined_after` state was unreachable if BR1.5's predicate was reused —
and it is the same lesson: **a predicate that reads as shared is two
predicates that happen to agree in three clauses.**

---

## 5. What D5 does not ship

| Thing | Why |
|---|---|
| `collection_rate` | **OQ-2 is open.** See the Assumptions below |
| Any table, column or migration | Every figure derives from built rows [A5] |
| Any money arithmetic | `derive()` and `Money` are built; D5 adds nothing to `app/money/` |
| A Macrobenchmark harness | Closed by the human, 2026-10-23: PU-3.6 takes a manual pilot check in D4 |
| A stored or cached figure | Every read is computed on open [AC7.1.4]: no generate step, no refresh button, no materialised table |

**The last row is a requirement rather than a simplification.** AC7.1.4 says
the dues view "renders current data on open with no generate step", so a
cached or scheduled rollup would be a different product — and a stale figure
about money is worse than a slow one.

---

## Assumptions & Open Questions

- **OQ-2 remains open and `collection_rate` does not ship.** The decision is
  the prior record's and this design does not reopen it: *"a field is additive
  under `/v1/`, a wrong number pinned into an installed client cannot be
  withdrawn"* [external-dependency-map]. Worth recording precisely what is
  open, because it is **not** that the arithmetic is unwritten — US8.3 carries
  five criteria that specify it in full. It is that **FR8.3's definition is
  annotated open to correction, and AC8.3.4's credit rule postdates it**, so
  the five criteria may not be consistent with the requirement they cite. That
  is a question needing the human's judgement, not someone's commitment.
- **The period key's lexical order is chronological** because the keys are
  fixed width. D3's `app/fees/views.py:347-350` relies on the same property
  and states it; D5 inherits rather than re-establishes it.
- **"This month" is the server's calendar month in UTC** -- corrected
  2026-10-25 after review, which found the code and this assumption
  disagreed. An earlier draft said "the project's timezone", which
  Bangladesh is not: Dhaka is UTC+6, so for the first **6 hours of each
  month** (00:00-05:59 local on the 1st) the overview reports the
  PREVIOUS month's total labelled as this month, then self-corrects.
  **72 hours a year**, computed.
  .
  **The human chose to record it rather than change it** [2026-10-25],
  because D5 is CONSISTENT with `app/fees/generation.py` and
  `app/teaching/generation.py`, which both use UTC. Fixing one module
  would make two parts of the product disagree about which month it is.
  The boundary is a project-wide decision for a change of its own.
  **The code is right and this sentence was wrong**, which is the order
  that matters: a design assumption nothing checks is a claim.
- **The nominal five batches per teacher is D4's documented assumption**, not
  an upstream figure, and it is used here only to size the statement-count
  argument in § 4.
- **AC8.4.3's tiebreaker is specified as "deterministic" and no upstream
  artifact names the key.** This design proposes `(date, created_at, exam_id)`
  and `rules.md` states it as a rule rather than leaving it to the
  implementation, because "deterministic" with no key named is how two
  implementations disagree while both satisfying the criterion.
