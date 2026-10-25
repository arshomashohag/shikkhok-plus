# Business Rules — D3 `collecting-fees`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **The arithmetic is not a rule here, because it is already code.** The
> ledger fold, the credit cap and the carry pairing live in
> `app/money/_ledger.py` at 100% branch coverage. The rules below are the
> half that module deliberately refuses to hold: **when** an entry is
> written, **which** entries a decision produces, **what** the calendar says,
> and **who** may see the result. Where a rule restates an arithmetic
> property it is because the property must be true of the PERSISTED rows and
> not only of a fold over them.
>
> Rule IDs are unit-scoped, as in every unit of this project: D1 and D2 both
> number from `BR1.1` and so does D3.
>
> **Every figure in a `logic` or `notes` field below was computed**, by
> re-implementing the fold and running the case. None is asserted. This
> matters more here than anywhere else in the product: team memory records a
> carry-forward example that propagated to four files with a wrong number
> because nobody computed it.

## Sources

- [upstream] this stage's `functional-spec.md` — the workflows these rules sit in
- [upstream] this stage's `entities.md` — the tables these rules constrain
- [upstream] `inception/user-stories/stories.md` — AC1.14.1 through AC1.14.4
- [prior] `261016-.../inception/user-stories/stories.md` — AC5.1.x, AC5.2.x,
  AC5.3.x, AC5.4.x, AC6.1.x, AC6.3.x, AC6.4.x
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  FR5.1–FR5.9, FR6.1–FR6.13, FR7.2, FR9.1–FR9.3, FR10.1–FR10.4
- [prior] `261016-.../inception/domain-design/decisions.md` — ADR-002
- [code] `app/money/_ledger.py`, `app/money/_kinds.py`, `app/db/models.py`,
  `app/schemas/batches.py`, `tests/auth/test_ceilings.py`, read 2026-10-23

---

```yaml
rules:

  # ==================================================================
  # Group 1: generation — when a cycle comes into existence.
  # ==================================================================

  - id: BR1.1
    statement: >
      A fee cycle generates for every enrollment whose seat is generating,
      once per calendar-month period, charging the resolved fee.
    category: calculation
    applies_to: FeeCycle, LedgerEntry
    trigger: The daily generation job, for each period at or before today.
    logic: >
      IF an enrollment is generating for this period (BR1.5, BR1.6)
      THEN insert a FeeCycle for (enrollment_id, period) with the due date
      from BR2.2
      AND append one `charge` LedgerEntry for the resolved fee (BR2.4)
      AND apply any available credit (BR4.5).
    violation_behaviour: >
      A teacher opens the fee screen at month start and sees nothing owed,
      or sees last month's figure. Assertable: for an enrollment with no
      `inactive_from` and an accepted or pending student link, after the
      job runs for period P exactly one FeeCycle row exists for (that
      enrollment, P) and the ledger's charged total for P equals the
      resolved fee.
    source: FR5.1, FR5.3, AC5.1.1

  - id: BR1.2
    statement: >
      FeeCycle carries no money column. Every quantity is derived from
      ledger entries.
    category: constraint
    applies_to: FeeCycle
    trigger: Any schema change touching FeeCycle.
    logic: >
      IF a quantity of money is needed for a cycle
      THEN derive it by folding that cycle's LedgerEntry rows
      AND never read it from a column on FeeCycle, because no such column
      exists.
    violation_behaviour: >
      A stored total becomes a second source of truth and drifts from the
      entries that produce it, silently and in the direction of whichever
      write path forgot to update it. Assertable: a test enumerates
      FeeCycle's columns and fails on any name outside
      {id, enrollment_id, period, due_date, created_at}.
    source: ADR-002, FR5.1
    notes: >
      The project already carries a correction that where a comment states
      a number the number is a claim. This is the column-set equivalent:
      the thinness is asserted by a test rather than by a docstring.

  - id: BR1.3
    statement: >
      Generation idempotency is the database unique constraint on
      (enrollment_id, period) with ON CONFLICT DO NOTHING, and a conflict
      is the success path.
    category: constraint
    applies_to: FeeCycle generation
    trigger: Inserting a cycle.
    logic: >
      IF a cycle row already exists for (enrollment_id, period)
      THEN the insert conflicts and does nothing
      AND generation CONTINUES without raising
      AND no second `charge` entry is appended for that period.
    violation_behaviour: >
      An application-level "has this already run?" guard passes a
      sequential test and double-charges under two workers, which Phase 1
      has. Assertable, and ONLY assertable concurrently: N threads released
      together from a barrier against real PostgreSQL leave exactly one row
      per (enrollment_id, period) and a charged total equal to one period's
      charge.
    source: FR5.4, AC5.1.2, AC5.1.6, project MANDATED rule
    notes: >
      The shape has a built precedent worth following rather than
      reinventing: `RateLimitCounter`'s UniqueConstraint in
      `app/db/models.py`, whose comment already explains that the
      constraint is what makes the atomic operation possible because the
      second worker conflicts instead of reading a stale value. D3 is the
      same shape with DO NOTHING in place of DO UPDATE.

  - id: BR1.4
    statement: >
      Generation runs daily and a missed day self-heals without producing
      duplicates.
    category: policy
    applies_to: The generation job
    trigger: The daily schedule.
    logic: >
      IF the job runs today
      THEN it considers every period from the enrollment's first generating
      period up to the current one
      AND inserts only those with no existing cycle
      AND is therefore safe to run any number of times on any number of
      days.
    violation_behaviour: >
      A missed day leaves a permanent hole that nothing ever fills, or a
      re-run double-charges every prior month. Assertable, and NOT covered
      by the concurrency test: run the job for day N, then for day N+1,
      then again for N+1, and assert the row set and the ledger total are
      identical after runs two and three.
    source: FR5.5, AC5.1.3

  - id: BR1.5
    statement: >
      A seat generates for the period CONTAINING `inactive_from`, and stops
      only for periods beginning strictly after it.
    category: calculation
    applies_to: Enrollment, FeeCycle generation
    trigger: Deciding whether a period generates.
    logic: >
      IF `inactive_from` is unset
      THEN generate
      ELSE IF `inactive_from` >= the first day of the period
      THEN generate IN FULL
      ELSE do not generate.
    violation_behaviour: >
      A student leaving on the 1st escapes the month's fee, or a student
      leaving on the 28th is billed for the next month too. Assertable:
      with `inactive_from` = 2027-02-15, period 2027-02 generates and
      2027-03 does not; with `inactive_from` = 2027-01-31, 2027-02 does
      not.
    source: FR5.3, FR5.6, AC5.1.4
    notes: >
      Computed, not asserted. A partial month is never prorated: the cycle
      stands in full and the teacher adjusts it through the charge
      adjustment path if they choose [FR5.6]. This rule is named in the
      affirmed testing posture as one that fails quietly.

  - id: BR1.6
    statement: >
      A `declined` STUDENT link stops generation from the moment of the
      decline, and the cycles already accrued are voided by a reversal
      entry rather than by deleting rows.
    category: policy
    applies_to: Enrollment, FeeCycle generation, LedgerEntry
    trigger: The student link's decision becomes `declined`; and every
      subsequent generation run.
    logic: >
      IF `student_decision` is `declined`
      THEN generate no further cycle for that seat
      AND for each existing cycle with an outstanding balance, append a
      `forgiveness` entry for that balance, which takes it to zero while
      leaving every original row intact.
    violation_behaviour: >
      Someone who said the seat is not theirs keeps accruing a debt nobody
      will ever collect, and a teacher chasing it is chasing a stranger.
      Assertable: a seat with a 1000 charge and a decline has outstanding
      0.00 afterwards, the `charge` row still exists, and the next job run
      adds no cycle.
    source: AC1.14.1, AC1.14.2, FR1.9f.1, FR1.9f.2
    notes: >
      `forgiveness` is the correct kind rather than a new one: it is the
      term the identity already carries for an obligation relieved without
      cash, and ADR-002 is explicit that a sixth quantity should be a new
      `kind` only when no existing one fits. Computed: charge 1000 plus
      forgiveness 1000 gives outstanding 0.00, credit 0.00, identity
      balanced.

  - id: BR1.7
    statement: >
      A `declined` GUARDIAN link does not affect generation at all. Only
      the guardian's own lens is withdrawn.
    category: policy
    applies_to: Enrollment, FeeCycle generation
    trigger: The guardian link's decision becomes `declined`.
    logic: >
      IF `guardian_decision` is `declined`
      THEN generation continues unchanged
      AND no reversal is written
      AND the student's obligation stands in full.
    violation_behaviour: >
      A guardian declining cancels the student's debt, so any student can
      clear their own fees by having a guardian refuse. Assertable: with
      `guardian_decision` = `declined` and `student_decision` = `accepted`,
      the next run generates a cycle and outstanding is unchanged.
    source: AC1.14.1a, FR1.9b, FR1.9f.1
    notes: >
      The asymmetry is the whole point and this project has already been
      bitten by its presentation half: a decline confirmation reading "the
      fee stops" was shown to guardians as well as students, telling a
      guardian a debt was cancelled when it was not. The rule is
      role-dependent and every surface that renders it must be checked
      against BOTH roles.

  - id: BR1.8
    statement: >
      Un-declining resumes generation from the acceptance date and never
      resurrects a voided cycle.
    category: policy
    applies_to: Enrollment, FeeCycle generation
    trigger: A declined link is later accepted.
    logic: >
      IF a previously declined student link becomes `accepted`
      THEN generation resumes for periods at or after the acceptance date
      AND the `forgiveness` entries written at BR1.6 are NOT reversed
      AND the previously voided cycles stay at zero.
    violation_behaviour: >
      Accepting a seat retroactively re-bills months the person was not
      participating in, which punishes correcting a mistake. Assertable:
      decline with 1000 accrued, then accept, then run generation — the
      earlier period's outstanding is still 0.00 and only periods from the
      acceptance date carry a charge.
    source: AC1.14.3, FR1.9f.3

  - id: BR1.9
    statement: >
      A `pending` seat generates. Pending is the normal state of a new
      seat, not a withheld one.
    category: policy
    applies_to: Enrollment, FeeCycle generation
    trigger: Deciding whether a seat generates.
    logic: >
      IF neither link is `declined`
      THEN generate, whether the student link is `pending` or `accepted`.
    violation_behaviour: >
      A teacher who adds a batch of students on Monday sees no fees for any
      of them until each installs the app, which makes the product useless
      for the one task it exists for. Assertable: a seat with both
      decisions `pending` generates a cycle.
    source: AC1.14.4, FR1.9f
    notes: >
      This is the money-side counterpart of D2's BR1.1, which marks
      declined per row and does NOT mark pending, for the same reason:
      declined is abnormal, pending is a seat nobody has opened yet.

  # ==================================================================
  # Group 2: the calendar and the resolved fee.
  # ==================================================================

  - id: BR2.1
    statement: >
      A period is a calendar month identified as `YYYY-MM`, and the money
      module holds no calendar knowledge.
    category: constraint
    applies_to: FeeCycle.period, LedgerEntry.period
    trigger: Writing or reading any period key.
    logic: >
      IF a period is needed
      THEN it is the calendar month as `YYYY-MM`, fixed width and lexically
      sortable
      AND all period arithmetic happens in this unit, never in `app.money`.
    violation_behaviour: >
      Calendar logic inside the money module breaks its stated boundary —
      "this module persists nothing… period arithmetic belongs to the unit
      that owns fee cycles" — and the import-boundary test fails.
      Assertable: the existing AST walk already asserts `app.money` imports
      nothing outside itself, and a `datetime` import there would be new.
    source: FR5.2, ADR-002, app/money/_ledger.py

  - id: BR2.2
    statement: >
      The due date is `min(fee_due_day, days_in_month)`, and the clamp does
      NOT degrade the stored anchor.
    category: calculation
    applies_to: FeeCycle.due_date
    trigger: Generating a cycle.
    logic: >
      IF generating period P for a batch whose anchor day is D
      THEN due_date = the day min(D, number_of_days_in(P)) of P
      AND `Batch.fee_due_day` is NOT rewritten.
    violation_behaviour: >
      Under a degrading clamp, one short month silently rewrites every
      future due date for that batch for ever. Assertable, and these are
      computed values: anchor 31 gives 2027-01-31, 2027-02-28, 2027-03-31,
      and 2028-02-29 in the leap year. A degrading implementation gives
      2027-03-28 on the third month and fails.
    source: FR5.2, FR2.1
    notes: >
      **This is a design choice the upstream did not make and it is stated
      rather than implied.** FR5.2 says periods are "clamped to the last day
      of months that lack it" and is silent on persistence. Non-degrading
      is chosen because it makes the due date a pure function of the stored
      anchor and the period — no hidden write, no order dependence, and a
      re-run of the self-healing job (BR1.4) cannot change an answer it
      already gave. Under a degrading clamp the job is no longer idempotent
      across days, which would contradict BR1.4.

  - id: BR2.3
    statement: >
      A NULL `fee_due_day` means the last day of the period.
    category: calculation
    applies_to: Batch.fee_due_day, FeeCycle.due_date
    trigger: Generating a cycle for a batch with no anchor day set.
    logic: >
      IF `fee_due_day` IS NULL
      THEN due_date = the last day of the period
      (equivalently, treat the anchor as 31 and apply BR2.2).
    violation_behaviour: >
      A null anchor reaches date construction and produces an error or a
      null due date on the one path in the product where failure is
      silent — nobody is watching a nightly job. Assertable: a batch with
      `fee_due_day` NULL generates a cycle whose due_date is 2027-02-28 for
      period 2027-02.
    source: app/schemas/batches.py (the column is nullable), FR5.2
    notes: >
      **An assumption, flagged for the human.** The column is nullable and
      nothing upstream says what a null means. Last-day is the only default
      that cannot make a fee due before the month it pays for has been
      taught, and it degrades to the same behaviour as an anchor of 31. Day
      1 and refusing to generate are both defensible. This changes when
      teachers who set no due day get paid.

  - id: BR2.4
    statement: >
      The charged fee is the enrollment's `fee_amount` when it is not NULL,
      otherwise the batch's `default_fee`. Zero is a real fee, not a
      missing one.
    category: calculation
    applies_to: Enrollment.fee_amount, Batch.default_fee, LedgerEntry
    trigger: Appending a `charge` entry.
    logic: >
      IF `Enrollment.fee_amount` IS NOT NULL
      THEN charge that amount, INCLUDING when it is zero
      ELSE charge `Batch.default_fee`.
    violation_behaviour: >
      Testing falsiness rather than NULL silently converts a teacher's
      deliberate permanent waiver into the batch default, which bills a
      student the teacher excused. Assertable: an enrollment with
      `fee_amount` = 0.00 on a batch with `default_fee` = 1000.00 generates
      a cycle whose charged total is 0.00.
    source: FR5.1, app/db/models.py
    notes: >
      The built model's own docstring already says "Zero is a real fee of
      zero, which is a waiver". This rule exists because that sentence
      constrains D3's code and lives in another unit's file.

  # ==================================================================
  # Group 3: ledger integrity on the persisted rows.
  # ==================================================================

  - id: BR3.1
    statement: >
      A carry is written as a pair in one transaction: a `carried_out` on
      the origin period and a `carry_forward` of equal amount on the
      receiving one.
    category: constraint
    applies_to: LedgerEntry
    trigger: Carrying a balance between periods.
    logic: >
      IF a balance is carried from period A to period B
      THEN append `carried_out` of X against A AND `carry_forward` of X
      against B, in one transaction, never one without the other.
    violation_behaviour: >
      A one-sided carry counts the same debt twice and the gap grows every
      period. Computed: carrying 1000 into a second 1000 charge gives
      outstanding 2000.00 two-sided and 3000.00 one-sided. Assertable at
      the table level: sum(carry_forward) == sum(carried_out) for every
      enrollment.
    source: ADR-002, FR5.1
    notes: >
      `app/money/_ledger.py:carry_forward()` already returns the pair from
      one call so a one-sided carry is unrepresentable in the arithmetic.
      This rule is the PERSISTENCE counterpart: the two rows must also be
      committed together, which is a transaction property the fold cannot
      enforce.

  - id: BR3.2
    statement: >
      A carry never exceeds what the origin period actually owes.
    category: validation
    applies_to: LedgerEntry
    trigger: Carrying a balance.
    logic: >
      IF the amount to carry exceeds the origin period's outstanding
      THEN refuse, because the receiver is charged in full while the origin
      is relieved only to its zero floor, and the surplus appears from
      nowhere.
    violation_behaviour: >
      Debt is manufactured. Assertable: carrying 1200 out of a period owing
      1000 raises rather than writing entries.
    source: ADR-002, app/money/_ledger.py
    notes: >
      Already enforced by the module when `origin_balance` is supplied. The
      rule for D3 is that D3 ALWAYS supplies it — which it can, since every
      carry the system has is produced from a computed balance.

  - id: BR3.3
    statement: >
      Ledger rows are append-only. A correction appends a compensating
      entry and marks the original superseded; nothing is updated or
      deleted.
    category: constraint
    applies_to: LedgerEntry
    trigger: Any correction to a recorded amount.
    logic: >
      IF a recorded entry was wrong
      THEN append a compensating entry of the appropriate kind
      AND set `superseded_by_id` on the original
      AND never UPDATE amount, kind, period or enrollment_id, and never
      DELETE.
    violation_behaviour: >
      The audit trail FR9.2 requires is destroyed, and a dispute has no
      shared record — which is the one thing the payment feature exists to
      provide. Assertable: after a correction, both rows exist and the
      original's amount is unchanged.
    source: FR9.1, FR9.2, ADR-002
    notes: >
      This satisfies FR9.1's "overwrite" because that requirement is a
      statement about what the teacher SEES, and gives FR9.2's
      previous-value-and-actor for free.

  - id: BR3.4
    statement: >
      Amounts are non-negative and the sign lives in the kind.
    category: validation
    applies_to: LedgerEntry.amount
    trigger: Appending any entry.
    logic: >
      IF an amount is negative
      THEN refuse the entry.
    violation_behaviour: >
      A negative amount inverts a term of the identity silently, so the
      balance is wrong and nothing raises. Assertable: a negative amount on
      any kind raises, and a database CHECK (amount >= 0) rejects it even
      if application code is bypassed.
    source: ADR-002, app/money/_ledger.py
    notes: >
      Enforced in the value type already. Restated because the TABLE needs
      its own CHECK: the fold cannot defend against a row inserted by a
      migration or a repair script.

  - id: BR3.5
    statement: >
      Outstanding never goes below zero, and the enrollment total is the
      sum of per-period floored figures rather than a floor applied to a
      signed sum.
    category: calculation
    applies_to: Derived balances
    trigger: Deriving any balance.
    logic: >
      IF a period is relieved beyond its charges
      THEN that period's outstanding is zero, not negative
      AND the enrollment's total outstanding is the sum of those floored
      per-period figures.
    violation_behaviour: >
      Flooring a signed sum lets one over-settled period silently cancel
      another period's genuine debt, so a student with a real arrear shows
      as clear. Assertable: a two-period history where one period is
      over-relieved and the other owes 500 reports 500.00, not less.
    source: ADR-002, FR5.9, AC6.3.7

  # ==================================================================
  # Group 4: credit.
  # ==================================================================

  - id: BR4.1
    statement: >
      Credit belongs to the enrollment, not to a cycle.
    category: constraint
    applies_to: LedgerEntry (credit_grant, credit_apply)
    trigger: Granting or applying credit.
    logic: >
      IF credit is granted or applied
      THEN it is held against the enrollment
      AND available credit is computed across every period, not within one.
    violation_behaviour: >
      Credit trapped in a closed period can never be spent, so an
      overpayment vanishes. Assertable: credit granted in 2027-01 is
      applied against a 2027-02 charge.
    source: ADR-002, FR5.9

  - id: BR4.2
    statement: >
      An approved amount exceeding what was CHARGED is accepted, with the
      excess recorded as credit and never as a negative balance.
    category: calculation
    applies_to: PaymentClaim verification, LedgerEntry
    trigger: Approving a payment for more than the cycle's charge.
    logic: >
      IF the approved amount exceeds what the cycle owes
      THEN append a `receipt` for what was owed
      AND a `credit_grant` for the remainder.
    violation_behaviour: >
      Outstanding goes negative, which the invariant forbids, or the excess
      is silently discarded and a guardian's money disappears. Computed: a
      1000 charge approved at 1200 gives outstanding 0.00 and credit
      200.00, with the identity balancing at -200 on both sides.
    source: FR5.9, AC6.3.7
    notes: >
      Cash in is `receipt + credit_grant`, not `receipt`. That is exactly
      where the first correction attempt recorded in ADR-002 failed, and it
      is why credit cannot simply be ignored on the received side.

  - id: BR4.3
    statement: >
      Available credit is applied automatically when the next cycle
      generates.
    category: calculation
    applies_to: FeeCycle generation, LedgerEntry
    trigger: Generating a cycle for an enrollment holding credit.
    logic: >
      IF available credit is greater than zero when a cycle generates
      THEN append a `credit_apply` of min(available_credit, amount owed)
      AND any remaining credit stays available for later periods.
    violation_behaviour: >
      A student who overpaid is billed in full the next month and has to
      ask for their own money back. Computed: 200.00 credit against a
      1000.00 charge leaves outstanding 800.00 and credit 0.00 — note 800,
      which is the figure the superseded per-cycle form computed as 1000.
    source: FR5.9, AC6.3.8

  - id: BR4.4
    statement: >
      Applied credit never exceeds available credit, because the applied
      amount is computed rather than supplied.
    category: constraint
    applies_to: LedgerEntry (credit_apply)
    trigger: Applying credit.
    logic: >
      IF credit is applied
      THEN the amount is min(available, owed), computed at the point of
      application
      AND no caller may pass an amount of their own choosing.
    violation_behaviour: >
      Over-application is representable and produces negative available
      credit, which the invariant forbids. Assertable: 1500.00 credit
      against a 1000.00 charge applies 1000.00 and leaves 500.00 available.
    source: ADR-002, app/money/_ledger.py
    notes: >
      `apply_credit()` already computes this. The rule binds D3's CALLERS:
      the amount is never read from a request body.

  - id: BR4.5
    statement: >
      Credit is applied after the charge is appended, within the same
      generation transaction.
    category: constraint
    applies_to: FeeCycle generation
    trigger: Generating a cycle for an enrollment holding credit.
    logic: >
      IF a cycle is generated and credit is available
      THEN append the `charge` first, then compute what is owed, then
      append the `credit_apply`, all in one transaction.
    violation_behaviour: >
      Applying before the charge computes min(available, 0) and applies
      nothing, so the credit is never spent; splitting the transaction can
      leave a charge with no application after a crash. Assertable: the two
      entries share a transaction and the post-generation balance is 800.00
      for the 1000/200 case.
    source: AC6.3.8, ADR-002

  # ==================================================================
  # Group 5: claims and verification.
  # ==================================================================

  - id: BR5.1
    statement: >
      A claim resolves to the oldest unpaid cycle at submission, and is
      refused with a stated reason where no open cycle exists.
    category: validation
    applies_to: PaymentClaim
    trigger: Submitting a payment claim.
    logic: >
      IF the enrollment has at least one cycle with an outstanding balance
      THEN resolve the claim to the OLDEST such cycle and store that period
      ELSE refuse with a stated reason, and never create a cycle to receive
      the payment.
    violation_behaviour: >
      Creating a cycle to receive a payment bills the student for a period
      that had not begun. Assertable: a claim against an enrollment with no
      open cycle is refused and no FeeCycle row is created; with two unpaid
      cycles the claim's stored period is the earlier one.
    source: FR6.2, AC6.1.5

  - id: BR5.2
    statement: >
      A claimed amount of zero or less is refused before the claim is
      recorded; an amount exceeding the balance is accepted.
    category: validation
    applies_to: PaymentClaim.claimed_amount
    trigger: Submitting a payment claim.
    logic: >
      IF the claimed amount is zero or negative
      THEN refuse before recording
      ELSE accept, INCLUDING when it exceeds the outstanding balance,
      because money may genuinely have been overpaid out of band and the
      teacher decides at verification.
    violation_behaviour: >
      Blocking an over-claim at submission makes a genuine overpayment
      unreportable, so the guardian's only route is a phone call — the
      thing the feature exists to remove. Assertable: 0 and -1 are refused;
      a claim of 5000 against a 1000 balance is recorded as pending.
    source: AC6.1.6, AC6.1.7, FR6.4

  - id: BR5.3
    statement: >
      The shortfall is `charged − approved`, never `claimed − approved`.
    category: calculation
    applies_to: PaymentClaim verification
    trigger: Approving a lesser amount than claimed.
    logic: >
      IF a verification approves an amount
      THEN the remaining obligation is what the cycle CHARGED minus what
      was approved
      AND the claimed amount does not enter the calculation at all.
    violation_behaviour: >
      Measuring against the claim lets a guardian change what is owed by
      changing what they assert. Computed: a 1000 charge with a 1500 claim
      approved at 600 leaves a shortfall of 400.00 — not 900.00.
      Assertable with exactly that case, which separates the two formulas.
    source: AC6.3.3, FR6.6, FR6.8
    notes: >
      A claim is an assertion; a charge is the obligation. Where they
      differ, only the charge matters to the balance.

  - id: BR5.4
    statement: >
      Approving less than was charged requires an explicit choice between
      carrying the shortfall forward and waiving it.
    category: validation
    applies_to: PaymentClaim.shortfall_disposition
    trigger: Approving an amount below the charge.
    logic: >
      IF a shortfall exists
      THEN `shortfall_disposition` is required
      AND `carried` writes the BR3.1 pair into the next period
      AND `waived` appends a `forgiveness` for the shortfall
      ELSE `shortfall_disposition` is NULL.
    violation_behaviour: >
      A default silently chooses for the teacher, and the two choices have
      opposite consequences for the student. Computed, both from a 1000
      charge approved at 600: carried leaves 0.00 in the origin period and
      400.00 in the next; waived leaves 0.00 and nothing carried.
      Assertable: a verification below the charge with no disposition is
      refused.
    source: FR6.8, AC6.3.3

  - id: BR5.5
    statement: >
      A verification writes its claim decision and its ledger entries in
      one transaction.
    category: constraint
    applies_to: PaymentClaim, LedgerEntry
    trigger: Approving or rejecting a claim.
    logic: >
      IF a verification is recorded
      THEN the claim's status, approved amount, disposition, verifier and
      timestamp are written together with every ledger entry the decision
      produced, in one transaction.
    violation_behaviour: >
      A partial commit leaves a claim marked approved with no money
      recorded, or money recorded against a claim still showing pending —
      and the ledger is append-only, so the second case cannot be tidied
      away. Assertable: an induced failure mid-verification leaves neither
      the status change nor any entry.
    source: FR6.7, team error handling

  - id: BR5.6
    statement: >
      Rejecting a claim records nothing as received and shows the
      submitter the rejection.
    category: policy
    applies_to: PaymentClaim
    trigger: Rejecting a claim.
    logic: >
      IF a claim is rejected
      THEN status becomes `rejected`
      AND NO ledger entry of any kind is appended
      AND the outcome is visible to the submitter.
    violation_behaviour: >
      A rejected claim that still moved money, or a rejection the submitter
      never sees and keeps believing was paid. Assertable: after a
      rejection the enrollment's ledger row count is unchanged and the
      outstanding balance is unchanged.
    source: AC6.3.4, FR6.6, FR6.9

  - id: BR5.7
    statement: >
      A corrected verification retains the previous decision and shows it
      to the teacher AND to that student and guardian.
    category: policy
    applies_to: PaymentClaim.previous_decision
    trigger: Correcting a verification.
    logic: >
      IF a teacher changes a verification
      THEN store the prior decision with its actor and timestamp
      AND append compensating ledger entries per BR3.3
      AND show the correction to the teacher and to the affected student
      and guardian.
    violation_behaviour: >
      Correction history hidden from the person whose money it concerns,
      which is the exact asymmetry FR9.2 forbids. Assertable: after a
      correction, the student-lens and guardian-lens payment-history
      responses both carry the prior decision.
    source: FR9.2, FR9.3, AC6.3.6, AC6.4.3

  # ==================================================================
  # Group 6: what the client is told.
  # ==================================================================

  - id: BR6.1
    statement: >
      The fee status is a server-computed enum. The client never derives it
      from a balance.
    category: constraint
    applies_to: Fee responses
    trigger: Returning any fee cycle to any client.
    logic: >
      IF a cycle is returned
      THEN the response carries its status as one of
      `paid | partly_paid | unpaid | waived`
      AND the client renders that value and never compares an amount to
      decide it.
    violation_behaviour: >
      `if (balance > 0) "Due" else "Paid"` is a business rule about what
      counts as due wearing presentation's clothes, and it diverges from
      the server the first time a waiver or a credit is involved — a fully
      waived cycle has a zero balance and is not "Paid". Assertable: the
      response schema carries the enum, and a Kotlin test asserts the UI
      state maps from it with no arithmetic.
    source: TC-9, D-31, AC5.3.1, FR5.8
    notes: >
      Named in the team practice as one of the two places this boundary
      will be tested hardest. D2's BR1.3 set the habit for counts; this is
      the same shape and more consequential.

  - id: BR6.2
    statement: >
      Every money value crosses the API as a JSON string, in both
      directions.
    category: constraint
    applies_to: All fee and payment responses and requests
    trigger: Serializing or parsing any money value.
    logic: >
      IF a money value crosses the boundary
      THEN it is a JSON string
      AND a JSON number is rejected LOUDLY rather than coerced.
    violation_behaviour: >
      A lenient decoder that quietly accepts a number and converts is the
      actual failure mode, and it passes a happy-path both-sides test.
      Assertable on both surfaces: the existing Python chokepoint, and the
      Kotlin serializer test proving loud failure on a JSON number.
    source: FR5.7, TC-7, D-20, project FORBIDDEN rule

  - id: BR6.3
    statement: >
      Payment claim status is one of four values the server sets:
      pending, approved in full, approved in part, or rejected.
    category: calculation
    applies_to: PaymentClaim.status
    trigger: Returning a claim to its submitter.
    logic: >
      IF a claim is returned
      THEN its status is the stored server-set value
      AND an approval below the claimed amount reads `approved_partial`
      together with the approved amount and the shortfall disposition.
    violation_behaviour: >
      A guardian cannot tell a partial approval from a full one, so a
      dispute has no shared record. Assertable: a 1500 claim approved at
      600 against a 1000 charge returns `approved_partial`, approved
      600.00, and the disposition the teacher chose.
    source: AC6.4.1, AC6.4.2, FR6.9

  - id: BR6.4
    statement: >
      The collection number is shown only to students and guardians
      enrolled in that teacher's batches, and where it is unset the payment
      form omits the destination step.
    category: authorization
    applies_to: Batch.collection_number
    trigger: Rendering the payment form.
    logic: >
      IF the viewer holds a student or guardian lens on an enrollment in
      that batch
      THEN the collection number may be shown
      ELSE never, and it appears in no listing and no search
      AND IF it is unset, omit the destination step and tell the person to
      ask the teacher how to pay.
    violation_behaviour: >
      A teacher's payment-collection number leaks beyond the people who
      need it to pay. Assertable: the field is absent from every response
      reachable without a student or guardian lens on that batch.
    source: FR6.12, FR6.13
    notes: >
      This is the one teacher-authored field deliberately exposed to
      students and guardians, and the exposure is bounded rather than
      incidental.

  - id: BR6.5
    statement: >
      The payment channel set is server-supplied data, not a client-side
      list.
    category: constraint
    applies_to: PaymentClaim.channel
    trigger: Rendering the payment form.
    logic: >
      IF the form needs the channel options
      THEN it reads them from the server
      AND the app ships no hardcoded list.
    violation_behaviour: >
      Adding a channel becomes an app release, and an installed Android app
      cannot be forced to update. Assertable: no Kotlin source contains the
      literal channel names.
    source: FR6.11, NFR16

  - id: BR6.6
    statement: >
      The server decides money digit rendering through `Money.format`, and
      the numerals it emits are Latin.
    category: constraint
    applies_to: Money formatting
    trigger: Rendering any money value for display.
    logic: >
      IF a money value is rendered
      THEN the server's formatting decides the digits
      AND the digits are Latin 0-9 even under a Bangla locale, because they
      are the app's own output rather than text a person typed.
    violation_behaviour: >
      Server and client disagree about digits, so the same amount reads
      differently on the fee screen and in a notification. Assertable: a
      formatted amount contains no character in the Bengali digit range.
    source: TC-15, D-43, android/.../core/format/Numerals.kt
    notes: >
      **A reconciliation, not a new decision.** The unit definition says
      `Money.format(locale)` "becomes blocking here", and the method does
      not exist in `app/money/_money.py` today. The client already settled
      the rule — `Numerals` says numbers the app shows are Latin and text
      people typed is untouched — so the server implementation must AGREE
      with that rather than introduce Bangla digits for money. Had this
      gone the other way, every amount would render in two different digit
      sets depending on which surface drew it.

  # ==================================================================
  # Group 7: reminders.
  # ==================================================================

  - id: BR7.1
    statement: >
      A reminder is recorded as an event, and the teacher-facing reminded
      state is derived as the latest event per (enrollment, period).
    category: constraint
    applies_to: ReminderEvent
    trigger: Sending a fee reminder.
    logic: >
      IF a reminder is sent
      THEN append an event carrying channel, time, actor and outcome
      AND derive "reminded N days ago" or "Never reminded" from the latest
      event for that (enrollment, period).
    violation_behaviour: >
      A boolean or a `last_reminded_at` column cannot express channel, a
      failed send, or a second reminder, and forces a migration when a
      second channel arrives. Assertable: two reminders for one period
      leave two rows, and the derived state reflects the later one.
    source: FR10.3, FR10.4

  - id: BR7.2
    statement: >
      Notification delivery never fails the operation that triggered it,
      and a failed send is recorded rather than swallowed.
    category: policy
    applies_to: The notification adapter
    trigger: Dispatching a push notification.
    logic: >
      IF a push send fails
      THEN record the event with outcome `failed`
      AND log it
      AND do NOT surface it to the user or roll back the triggering
      operation, which is dispatched after commit.
    violation_behaviour: >
      Either a failed push rolls back a recorded payment verification, or
      the failure vanishes entirely and nobody can tell a reminder was
      never delivered. Assertable: with the adapter forced to fail, the
      triggering write is committed and a `failed` event row exists.
    source: FR10.2, team error handling
    notes: >
      Best-effort FCM is the project's stated exception to "silent failures
      are not acceptable". The exception covers not SURFACING the failure;
      it does not cover failing to record it, which is why `outcome` is a
      column.
```

---

## Rules summary

This table is a **derived view**. The YAML block above is the source of truth.

| ID | Category | Statement | Source |
|---|---|---|---|
| BR1.1 | calculation | A cycle generates per period, charging the resolved fee | FR5.1, AC5.1.1 |
| BR1.2 | constraint | FeeCycle carries no money column | ADR-002 |
| BR1.3 | constraint | Idempotency is the unique constraint; conflict is success | FR5.4, AC5.1.2 |
| BR1.4 | policy | Daily run; a missed day self-heals without duplicates | FR5.5, AC5.1.3 |
| BR1.5 | calculation | The period containing `inactive_from` generates in full | FR5.3, AC5.1.4 |
| BR1.6 | policy | A declined student link stops generation; accrued cycles are reversed | AC1.14.1, AC1.14.2 |
| BR1.7 | policy | A declined guardian link does not affect generation | AC1.14.1a |
| BR1.8 | policy | Un-declining resumes; voided cycles are not resurrected | AC1.14.3 |
| BR1.9 | policy | A pending seat generates | AC1.14.4 |
| BR2.1 | constraint | Periods are `YYYY-MM`; no calendar logic in the money module | FR5.2 |
| BR2.2 | calculation | Due date clamps to the month's last day, non-degrading | FR5.2, FR2.1 |
| BR2.3 | calculation | A NULL anchor day means the last day of the period | *assumption* |
| BR2.4 | calculation | Enrollment fee when not NULL, else batch default; zero is real | FR5.1 |
| BR3.1 | constraint | A carry is a pair in one transaction | ADR-002 |
| BR3.2 | validation | A carry never exceeds what the origin owes | ADR-002 |
| BR3.3 | constraint | Append-only; corrections compensate and supersede | FR9.1, FR9.2 |
| BR3.4 | validation | Amounts are non-negative; the sign is in the kind | ADR-002 |
| BR3.5 | calculation | Outstanding floors at zero per period, then sums | FR5.9 |
| BR4.1 | constraint | Credit belongs to the enrollment, not a cycle | ADR-002 |
| BR4.2 | calculation | Over-approval becomes credit, never a negative balance | AC6.3.7 |
| BR4.3 | calculation | Credit is applied automatically at next generation | AC6.3.8 |
| BR4.4 | constraint | Applied credit is computed as `min(available, owed)` | ADR-002 |
| BR4.5 | constraint | Credit is applied after the charge, same transaction | AC6.3.8 |
| BR5.1 | validation | A claim resolves to the oldest unpaid cycle, or is refused | AC6.1.5 |
| BR5.2 | validation | Zero or negative refused; over-claim accepted | AC6.1.6, AC6.1.7 |
| BR5.3 | calculation | The shortfall is `charged − approved` | AC6.3.3 |
| BR5.4 | validation | A shortfall requires an explicit carry-or-waive choice | FR6.8 |
| BR5.5 | constraint | Verification and its entries commit together | FR6.7 |
| BR5.6 | policy | Rejection records nothing and is shown to the submitter | AC6.3.4 |
| BR5.7 | policy | A corrected verification is visible to both parties | FR9.2, AC6.4.3 |
| BR6.1 | constraint | Fee status is a server-computed enum | TC-9, AC5.3.1 |
| BR6.2 | constraint | Money crosses the API as a JSON string | FR5.7, TC-7 |
| BR6.3 | calculation | Claim status is one of four server-set values | AC6.4.1 |
| BR6.4 | authorization | The collection number is bounded to enrolled viewers | FR6.13 |
| BR6.5 | constraint | The channel set is server-supplied | FR6.11 |
| BR6.6 | constraint | `Money.format` emits Latin digits, agreeing with the client | TC-15 |
| BR7.1 | constraint | A reminder is an event; state is the latest per period | FR10.3 |
| BR7.2 | policy | Delivery never fails the trigger; a failure is recorded | FR10.2 |

## The three rules most likely to be implemented wrongly

Stated plainly, because each has a plausible wrong version that passes a
happy-path test.

1. **BR5.3 — the shortfall base.** `claimed − approved` is the intuitive
   formula and it is wrong. The case that separates them: a 1000 charge, a
   1500 claim, approved at 600. The correct shortfall is **400.00**; the wrong
   one gives 900.00. A test using a claim equal to the charge cannot tell them
   apart, which is why the named boundary case uses one where they differ.

2. **BR3.1 — one-sided carry.** Writing only the `carry_forward` leaves the
   origin period still owing. Computed: 1000 carried into a second 1000 charge
   reads **2000.00** two-sided and **3000.00** one-sided. The enrollment-level
   check `sum(carry_forward) == sum(carried_out)` catches it immediately.

3. **BR2.4 — falsiness on a zero fee.** `enrollment.fee_amount or batch.default_fee`
   is the idiomatic Python line and it converts a deliberate zero into the
   batch default. The test is `IS NOT NULL`, and the named case is an
   enrollment at 0.00 on a batch defaulting to 1000.00.
