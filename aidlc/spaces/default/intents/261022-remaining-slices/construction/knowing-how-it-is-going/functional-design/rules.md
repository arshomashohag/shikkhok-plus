# Business Rules — D5 `knowing-how-it-is-going`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **Two rules in this file carry the unit's whole risk**, and both are
> arithmetic over rows that already exist rather than anything new:
>
> **BR2.1** — money received is `receipt + credit_grant` and **never**
> `credit_apply`. Counting the apply double-counts the credit, once when it
> arrived and again when it was spent, and every row still balances while it
> does so. The worked case in BR2.1 was **computed by running it**.
>
> **BR1.2** — the dues view is driven by outstanding balance and **not** by
> active status. Reusing D4's roster predicate silently drops exactly the
> people most worth chasing.
>
> Rule IDs are unit-scoped, as in every unit of this project: D5 numbers from
> `BR1.1` like D1 through D4.
>
> **Every figure in a `logic` or `notes` field below was computed**, not
> reasoned about. Team memory records a carry-forward figure that propagated
> to four files because nobody ran it.

## Sources

- [upstream] this stage's `entities.md` — the read models and the kind table
- [upstream] this stage's `functional-spec.md` — the workflows
- [upstream] `inception/requirements-analysis/requirements.md` — FR7.1–FR7.3,
  FR8.1, FR8.2, FR8.4, assumption A5
- [upstream] `inception/units-generation/unit-of-work.md` — D5's scope, OQ-2
- [prior] `261016-.../inception/user-stories/stories.md` — AC7.1.1–AC7.1.5,
  AC8.1.1, AC8.1.2, AC8.2.1, AC8.2.2, AC8.4.1–AC8.4.3
- [code] read 2026-10-25: `app/money/_kinds.py`, `app/money/_ledger.py`,
  `app/fees/views.py`, `app/fees/balances.py`, `app/contract/privacy.py`,
  `app/contract/routes.py`, `app/marks/exams.py`

---

```yaml
rules:

  # ==================================================================
  # Group 1: the cross-batch dues view. Who appears, and who does not.
  # ==================================================================

  - id: BR1.1
    statement: >
      The dues view returns every seat across every batch this teacher
      owns whose outstanding balance is above zero, with the amount,
      the batch and the period the debt starts in.
    category: calculation
    applies_to: DuesRow
    trigger: The teacher opens the dues view.
    logic: >
      IF a seat's derived total_outstanding > 0
      AND its batch's owner matches the lens's owner_id
      THEN it appears, with its outstanding amount, its batch name and
      its oldest unpaid period.
    violation_behaviour: >
      A teacher chasing payment works from a list that omits someone,
      which is the whole content of FR7.1. Assertable: three seats
      across two batches with outstanding 0, 500 and 1200 produce
      exactly two rows, carrying 500 and 1200 and naming their own
      batches.
    source: FR7.1, AC7.1.1

  - id: BR1.2
    statement: >
      Membership is driven by outstanding balance and NEVER by active
      status. A student who left owing money still appears.
    category: constraint
    applies_to: DuesRow
    trigger: Building the dues membership set.
    logic: >
      IF a seat has inactive_from set and still owes money
      THEN it appears
      AND the query applies NO predicate on inactive_from at all.
    violation_behaviour: >
      **This is the rule an implementation breaks by reusing D4's
      roster predicate**, which excludes a seat inactive before the
      session date -- correct there, and here it drops exactly the
      people most worth chasing. Assertable, and it must be asserted
      with a seat that is BOTH inactive AND owing: a test using only
      active owing seats passes against a query carrying the predicate.
    source: FR7.2, AC7.1.2
    notes: >
      The inverse of the trap D4 recorded, where reusing BR1.5's
      predicate made the `joined_after` state unreachable. Same lesson
      from the other side: **a predicate that reads as shared is two
      predicates that happen to agree in some clauses.**
      .
      **The built predicate has FOUR clauses, not three**
      [`app/teaching/roster.py:244-253`]: batch ownership,
      `inactive_from`, `student_decision`, and `joined_on`. D5 shares
      ownership and `student_decision`; it drops `inactive_from`
      [BR1.2]; and it drops `joined_on` too, for the same reason —
      a seat that joined after some session date can still owe money,
      and a dues view has no session date to compare against. **Two of
      four clauses carry over, not three of three.** Stated precisely
      because an approximate comparison is how the wrong predicate gets
      reused by someone checking the table rather than the code.

  - id: BR1.3
    statement: >
      A seat that owes nothing does not appear, whether it is active or
      not.
    category: constraint
    applies_to: DuesRow
    trigger: Building the dues membership set.
    logic: >
      IF a seat's total_outstanding is zero or negative
      THEN it does not appear.
    violation_behaviour: >
      A dues view listing everyone is not a dues view. Assertable
      together with BR1.2's case, because the two are the opposite
      halves of one predicate and a test covering one can pass against
      an implementation failing the other: an ACTIVE seat owing nothing
      is absent, and an INACTIVE seat owing money is present.
    source: FR7.2, AC7.1.3

  - id: BR1.4
    statement: >
      The dues view is computed on open. No generate step, no refresh
      action, no stored or cached rollup.
    category: policy
    applies_to: DuesRow
    trigger: The read.
    logic: >
      IF the dues view is requested
      THEN it derives from the ledger as it stands at that moment
      AND no scheduled job, materialised table or cache serves it.
    violation_behaviour: >
      A stale figure about money is worse than a slow one: a teacher
      chases a debt already paid, or fails to chase one just incurred.
      Assertable: record a receipt that clears a balance, re-read the
      view in the same test, assert the row is gone with no intervening
      job.
    source: FR7.3, AC7.1.4

  - id: BR1.5
    statement: >
      Nobody owing anything is an empty list with a defined empty
      state, never an error and never an absent response.
    category: validation
    applies_to: DuesRow
    trigger: The read, when no seat owes.
    logic: >
      IF no seat has an outstanding balance
      THEN return an empty collection with a 200.
    violation_behaviour: >
      A 404 or an error would read to a client as a failure, and the
      teacher would see a retry prompt for the best possible news.
      Assertable: a teacher with batches but no debts gets 200 and an
      empty collection.
    source: FR7.3, AC7.1.5

  - id: BR1.6
    statement: >
      The dues read issues a constant number of statements regardless
      of how many seats the teacher has.
    category: constraint
    applies_to: The dues query
    trigger: Any dues read.
    logic: >
      IF the dues view is built
      THEN the ledger is read with ONE `IN (:seat_ids)` select and
      folded in memory, following the shape D3 arrived at after its
      N+1 defect
      AND no function taking a single enrollment_id is called per row.
    violation_behaviour: >
      **The specific trap is reusing a correct function at the wrong
      granularity**: `app/fees/balances.py:72` `oldest_unpaid_period`
      takes one enrollment_id and calls `derive_for_enrollment`, so one
      call per dues row is a query per seat. At the scale ceiling --
      five batches of up to twenty seats -- that is up to a hundred
      statements for one screen. Assertable as a statement-count
      assertion following D3's NFR20.18, never a latency assertion,
      which on one small instance is flaky.
    source: NFR20.16 (D3's established shape), AC7.1.4
    notes: >
      The oldest unpaid period comes from the SAME in-memory
      `per_cycle` fold the outstanding balance comes from -- the
      minimum period whose balance is above zero. Same definition as
      the built function, no second query.

  - id: BR1.7
    statement: >
      A seat whose student link is declined does not appear in the dues
      view, whatever it owes.
    category: authorization
    applies_to: DuesRow
    trigger: Building the dues membership set.
    logic: >
      IF student_decision is `declined`
      THEN the seat is excluded
      AND this is the ONE clause D5 shares with D4's roster predicate
      besides batch ownership.
    violation_behaviour: >
      The mistyped-digit case: a seat someone declined because it was
      never theirs keeps appearing on a list of people to chase for
      money. Assertable: a declined seat with an outstanding balance is
      absent, which a test using only pending and accepted seats cannot
      distinguish from a query missing the clause.
    source: ADR-009, FR7.1
    notes: >
      Stated as its own rule because an earlier draft carried it only
      in the workflow sketch of `functional-spec.md` § 2.1. A clause
      that appears in a diagram and in no rule is a clause nothing
      obliges anyone to implement.

  # ==================================================================
  # Group 2: earnings. The unit's money risk, and it is arithmetic.
  # ==================================================================

  - id: BR2.1
    statement: >
      Money received in a period is `receipt` plus `credit_grant`, and
      NEVER `credit_apply`.
    category: calculation
    applies_to: MonthlyEarnings
    trigger: Computing earnings for any period.
    logic: >
      IF folding ledger entries for a period
      THEN sum the amounts of entries whose kind is `receipt` or
      `credit_grant`
      AND exclude `credit_apply`, `charge`, `forgiveness`,
      `carry_forward` and `carried_out`.
    violation_behaviour: >
      **Counting `credit_apply` double-counts the credit** -- once when
      it arrived as a grant and again when it was spent -- and every
      row still balances while it does so, because the apply is a real
      entry for a real amount. The teacher's headline earnings figure
      is silently overstated. Assertable with the computed case below.
    source: FR8.1, A5, `app/money/_kinds.py:58-60`
    notes: >
      **Not this design's invention.** The built money module states it:
      *"Cash in is receipts plus credit grants: money received as
      credit is money received."* D5 is the first consumer of that
      sentence.
      .
      **BR2.1 and AC8.3.4 take OPPOSITE sides on when a credit counts,
      and that is stated here rather than discovered later.** AC8.3.4
      reads: *"a credit applied from an earlier overpayment counts as
      received in the period whose charge it settles, not in the period
      it arrived."* BR2.1 ships the exact reverse for earnings: a
      credit counts **on arrival** as `credit_grant` and never on use.
      .
      **Both are right for their own figure**, which is why this is a
      conflict to record rather than one to resolve. Earnings answer
      "how much money came in this month", and the money arrived in the
      month the student handed it over. A collection ratio answers
      "what proportion of what I charged this period did I collect",
      and there the credit settles THIS period's charge. The same
      ledger fact belongs to different months in the two figures.
      .
      **The consequence, if OQ-2 closes in AC8.3.4's favour**: the
      earnings figure and the collection rate will disagree about which
      month a credit belongs to, on the same screen. That is defensible
      and must be *stated on the screen* rather than left for a teacher
      to find. Flagged for the human with OQ-2, because it changes what
      closing OQ-2 costs: it is not only "define the arithmetic" but
      "decide whether two figures may use different month conventions".
      .
      **Worked case, computed by running it rather than asserted.**
      Month 1: the seat owes 1000 and the student hands over 1500,
      producing `receipt` 1000 and `credit_grant` 500. Month 2: the
      seat owes 1000, settled as `credit_apply` 500 plus `receipt` 500.
      .
      Cash in for M1 is 1000 + 500 = **1500**. Cash in for M2 is
      500 + 0 = **500**. The total is **2000**, which is exactly what
      the student handed over (1500 + 500).
      .
      Counting `credit_apply` as cash in would make M2 read
      500 + 500 = 1000 and the total **2500** -- overstated by exactly
      the 500 credit, counted twice.
      .
      **The test asserts 2000 and specifically not 2500.** Asserting
      only "the total is positive" or "M1 is 1500" passes against the
      defect.

  - id: BR2.6
    statement: >
      A ledger entry belongs to the month its `period` key names, never
      the month its `created_at` falls in.
    category: calculation
    applies_to: MonthlyEarnings, EarningsTrend
    trigger: Grouping ledger entries into months.
    logic: >
      IF entries are grouped for an earnings figure
      THEN the grouping key is the entry's `period` string
      AND `created_at` is never used to decide which month an entry
      counts in.
    violation_behaviour: >
      **The two disagree whenever a payment is recorded late**, which
      is the normal case rather than an edge: a teacher verifying
      October's cash on 2 November produces an entry whose `period` is
      October and whose `created_at` is November. Grouping by
      `created_at` moves that money into November, understating October
      and overstating November — and the trend then shows a dip and a
      spike that never happened. Assertable: an entry with period
      `2026-10` and a November `created_at` counts in October.
    source: FR8.1, FR8.2
    notes: >
      `period` is a **plain string on the ledger row, not a foreign
      key** [`app/db/models.py:927`], so this grouping needs no join to
      `fee_cycle` — which is what keeps the overview's statement count
      as small as the dues view's. Period keys are fixed width, so
      lexical order is chronological order and the grouping is a sort
      rather than a parse.
      .
      **This also decides what "this month" means for FR8.1**: the
      current period key, which is the server's calendar month. A
      device-supplied month would let a phone's clock change a
      teacher's reported earnings.

  - id: BR2.2
    statement: >
      Zero earned is a value, not an empty state.
    category: policy
    applies_to: MonthlyEarnings
    trigger: A month with no money received.
    logic: >
      IF a period has no `receipt` and no `credit_grant`
      THEN return zero as the received amount
      AND never an absent field, a null, or an empty-state marker.
    violation_behaviour: >
      Rendering zero as "no data" tells a teacher their records are
      missing when they are complete, in the month they most need to
      know the number is really zero. Assertable: a teacher with
      batches, seats and charges but no receipts in the period gets a
      received value of 0.00, not a null and not an omitted field.
    source: FR8.1, AC8.1.2

  - id: BR2.3
    statement: >
      Fewer than two months of history returns no trend.
    category: calculation
    applies_to: EarningsTrend
    trigger: Building the monthly series.
    logic: >
      IF fewer than 2 periods have ledger history
      THEN return no trend
      AND do NOT return a one-point series.
    violation_behaviour: >
      A single point is not a trend, and a one-point chart implies a
      direction it cannot know. Assertable as two cases, because one
      can pass while the other fails: one month of history returns no
      trend, two months returns both points.
    source: FR8.2, AC8.2.2

  - id: BR2.4
    statement: >
      The monthly series is ordered by period ascending in the query,
      never sorted in the client.
    category: constraint
    applies_to: EarningsTrend
    trigger: Returning the series.
    logic: >
      IF the series is returned
      THEN it is already in date order
      AND the client renders the order it is given.
    violation_behaviour: >
      A client sorting a domain list is the second of the five erosion
      paths `team.md` names, and the one most easily reached on a chart
      screen. Assertable: the response order is asserted in the
      response, not in the client.
    source: FR8.2, AC8.2.1, team Code Style on layer boundaries
    notes: >
      Period keys are fixed width, so lexical order IS chronological
      order -- `app/fees/views.py:347-350` relies on the same property
      and states it. No date parsing is needed to sort.

  - id: BR2.5
    statement: >
      Earnings span every batch the teacher owns, and no batch they do
      not.
    category: authorization
    applies_to: MonthlyEarnings, EarningsTrend, DuesRow
    trigger: Any analytics read.
    logic: >
      IF an analytics figure is computed
      THEN its seat set is scoped by the lens's owner_id
      AND never by a batch id taken from the request.
    violation_behaviour: >
      A figure spanning another teacher's batches discloses their
      business. Assertable: two teachers with disjoint batches and
      different receipts each read only their own total, and a
      request naming the other's batch is refused.
    source: FR8.1, TC-11, D-2

  # ==================================================================
  # Group 3: the next exam.
  # ==================================================================

  - id: BR3.1
    statement: >
      The next exam is the soonest exam dated today or later across
      every batch the teacher owns.
    category: calculation
    applies_to: NextExam
    trigger: The teacher opens the overview.
    logic: >
      IF exams exist with date >= today in the teacher's batches
      THEN return the one with the smallest date
      AND include its title, batch name, subject name, date and whole
      days remaining.
    violation_behaviour: >
      A past exam shown as upcoming, or tomorrow's exam missed because
      the comparison excluded today. Assertable with a boundary case:
      an exam dated TODAY is upcoming, and one dated yesterday is not.
    source: FR8.4, AC8.4.1

  - id: BR3.2
    statement: >
      Days remaining is whole days, computed server-side.
    category: calculation
    applies_to: NextExam
    trigger: Returning the next exam.
    logic: >
      IF the exam is dated D and today is T
      THEN days_remaining is the whole number of days from T to D
      AND an exam dated today reports 0, not 1 and not null.
    violation_behaviour: >
      A client computing it from a date uses the device clock, which
      this product rules out for decisions, and disagrees across time
      zones. Assertable: exams dated today, tomorrow and in seven days
      report 0, 1 and 7.
    source: FR8.4, AC8.4.1, TC-9

  - id: BR3.3
    statement: >
      Two exams on the same date are separated by a stated
      deterministic key, not by arbitrary ordering.
    category: constraint
    applies_to: NextExam
    trigger: Two or more exams share the soonest date.
    logic: >
      IF two exams tie on date
      THEN order by (date, created_at, exam_id) and return the first
      AND the same data returns the same exam on every call.
    violation_behaviour: >
      "Deterministic" with no key named is how two implementations
      disagree while both satisfying the criterion, and how one
      implementation disagrees with itself after a query-plan change.
      Assertable: two exams on one date return the same exam across
      repeated reads, and specifically the one with the earlier
      created_at.
    source: FR8.4, AC8.4.3
    notes: >
      The key is this design's choice; AC8.4.3 requires determinism and
      names no key. `created_at` before `exam_id` so the tiebreak is
      meaningful to a person rather than an opaque uuid comparison,
      with `exam_id` as the final total order.

  - id: BR3.4
    statement: >
      No future exam is an empty state, not an error.
    category: validation
    applies_to: NextExam
    trigger: The read, when no exam is dated today or later.
    logic: >
      IF no upcoming exam exists
      THEN return an absent next-exam with a 200.
    violation_behaviour: >
      A teacher between terms sees a failure instead of "nothing
      scheduled". Assertable: a teacher with batches and only past
      exams gets 200 with no exam.
    source: FR8.4, AC8.4.2

  # ==================================================================
  # Group 4: what this unit does not do.
  # ==================================================================

  - id: BR4.1
    statement: >
      D5 ships NO `collection_rate` field while OQ-2 is open.
    category: policy
    applies_to: The analytics response schema
    trigger: Any proposal to add the field.
    logic: >
      IF a collection_rate field is proposed
      THEN it is refused while OQ-2 is open
      AND no provisional arithmetic is shipped in its place.
    violation_behaviour: >
      A field is additive under `/v1/`; a wrong number pinned into an
      installed client cannot be withdrawn. Assertable as the absence
      of the field from the generated OpenAPI document.
    source: OQ-2, external-dependency-map
    notes: >
      **What is open is narrower than "the arithmetic is unwritten".**
      US8.3 carries five criteria specifying it in full. What is open
      is that **FR8.3's definition is annotated open to correction and
      AC8.3.4's credit rule postdates it**, so the five criteria may
      not be consistent with the requirement they cite. That needs the
      human's judgement, not someone's commitment -- which is the test
      `team.md` gives for a real open question.

  - id: BR4.2
    statement: >
      D5 creates no table, adds no column and ships no migration.
    category: constraint
    applies_to: The schema
    trigger: Unit completion.
    logic: >
      IF D5 is complete
      THEN `migrations/versions/` has no new revision
      AND `app/governance/dispositions.py` still holds 25 entries.
    violation_behaviour: >
      Stated as an absence because a materialised rollup is the obvious
      optimisation and it would contradict BR1.4. Assertable as a file
      check plus the governance count.
    source: A5, AC7.1.4

  - id: BR4.3
    statement: >
      D5 adds no money arithmetic. Every amount comes from the built
      fold.
    category: constraint
    applies_to: Every figure in this unit
    trigger: Any money value.
    logic: >
      IF a money value is produced
      THEN it comes from `derive()` or a sum of `Money` values
      AND no new function is added to `app/money/`.
    violation_behaviour: >
      A second place that knows how to add money is a second place that
      can disagree with the first. The built import-boundary checks
      already forbid raw `decimal` outside `app/money/**`, so this
      fails `make check` rather than review.
    source: project MANDATED rule on confining money arithmetic

  - id: BR4.4
    statement: >
      Every route in this unit resolves a teacher lens, and no response
      carries an owner-private profile field or a global account id.
    category: authorization
    applies_to: Every route in this unit
    trigger: Any request.
    logic: >
      IF a route in this unit is defined
      THEN it declares a dependency whose return annotation is a Lens
      subtype
      AND its response exposes an enrollment_id, never a
      student_account_id.
    violation_behaviour: >
      A dues list is a list of people and is the natural place to leak
      a student's self-authored name to a teacher. Assertable by the
      two built gates with no new mechanism: the route-enumeration test
      and `app/contract/privacy.py`'s schema-wide invariant. D5 adds
      NOTHING to `PUBLIC_ROUTES`, which holds eight entries with the
      count asserted in two places.
    source: TC-11, TC-13, D-2, D-5

  - id: BR4.5
    statement: >
      Every screen this unit ships has a row in the per-screen check
      table before the unit is complete.
    category: policy
    applies_to: Every screen in this unit
    trigger: Unit completion.
    logic: >
      IF this unit adds a screen
      THEN it gets a row in `docs/delivery/bangla-layout-check.md`
      AND a screen with no row means an incomplete unit.
    violation_behaviour: >
      Assertable as a file check rather than a judgement. The screens
      this unit adds are the cross-batch dues list and the teacher
      overview carrying earnings, the trend and the next exam.
    source: FR0.2, TC-15, D-43
    notes: >
      **The earnings figure is the one to check hardest** for Bangla
      layout: a money amount rendered in Bangla numerals under a long
      Bangla label is the densest short string this unit shows, and it
      sits on the screen a teacher opens most.
```

---

## Rules summary

| ID | Category | What it settles |
|---|---|---|
| BR1.1 | calculation | Who appears in the dues view |
| BR1.2 | constraint | **Balance, not active status — the rule reuse breaks** |
| BR1.3 | constraint | Owing nothing means absent, active or not |
| BR1.4 | policy | Computed on open; no cache, no generate step |
| BR1.5 | validation | Nobody owing is an empty list, not an error |
| BR1.6 | constraint | **Constant statement count; the per-row function trap** |
| BR1.7 | authorization | A declined seat never appears, whatever it owes |
| BR2.1 | calculation | **`receipt + credit_grant`, never `credit_apply`** |
| BR2.6 | calculation | **Grouped by `period`, never `created_at`** |
| BR2.2 | policy | Zero earned is a value |
| BR2.3 | calculation | One point is not a trend |
| BR2.4 | constraint | Ordered in the query, never in the client |
| BR2.5 | authorization | Scoped by the lens's owner, never a request id |
| BR3.1 | calculation | The soonest exam dated today or later |
| BR3.2 | calculation | Whole days, computed server-side |
| BR3.3 | constraint | A stated tiebreaker, not arbitrary order |
| BR3.4 | validation | No upcoming exam is an empty state |
| BR4.1 | policy | **No `collection_rate` while OQ-2 is open** |
| BR4.2 | constraint | No table, no column, no migration |
| BR4.3 | constraint | No new money arithmetic |
| BR4.4 | authorization | Every route names its lens; no profile fields |
| BR4.5 | policy | A per-screen row per screen |

## Assumptions & Open Questions

- **The `(date, created_at, exam_id)` tiebreaker in BR3.3 is this design's
  choice.** AC8.4.3 requires determinism and names no key.
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
- **OQ-2 stays open and BR4.1 holds.** What is open is narrower than it
  reads: the arithmetic is specified across five criteria, but FR8.3's
  definition is annotated open to correction and AC8.3.4's credit rule
  postdates it, so the criteria may not be consistent with their own
  requirement. **For the human.**
- **BR2.1's worked case was computed by running it**, not reasoned about.
  Both totals — 2000 correct and 2500 under the defect — were produced by
  executing the fold over the stated entries.
- **No rule in this file states a latency, a duration or a timing budget.**
  BR1.6 is a statement-count rule, which is D3's established shape and
  deliberately not a performance assertion.
