# Entity Model — `money-core` (U1)

**Stage**: functional-design (3.4)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> **This Unit persists nothing.** It owns no table, no migration and no
> row. The block below describes **value semantics** — the shape and
> invariants of values that other Units persist, transmit and compute with.
> Every persisting Unit (U4, U7, U8) must honour these semantics; none of
> them may restate or reimplement them.

## Sources

- [stage] `functional-design-questions.md` — Q1 (value shape, not a table), Q2
  (the seven kinds as a closed set), Q3 (credit derived, never stored)
- [upstream] `inception/units-generation/unit-of-work.md` — U1 definition
- [upstream] `inception/delivery-planning/bolt-plan.md` — B1 DoD and confidence hypothesis
- [upstream] `inception/domain-design/decisions.md` — ADR-002
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [upstream] `inception/requirements-analysis/requirements.md` — FR5.1, FR5.2, FR5.9, NFR9
- [team] `## Code Style` → "Money as a type, on both surfaces"
- [team] `## Testing Posture` → money-module obligations
- [project] `## Forbidden` / `## Mandated` money rules

---

## Part A — Source of truth

```yaml
value_types:
  - name: Money
    kind: value_type
    persisted: false
    description: >
      A fixed-point monetary amount in Bangladeshi Taka. Defined by its
      attributes, not by identity: two Money values with equal amounts are
      interchangeable and equal. Immutable — every operation returns a new
      value and none mutates the receiver. This is the only money type
      permitted to cross any module boundary in either language surface.
    attributes:
      - name: amount
        logical_type: fixed_point_decimal
        required: true
        scale: 2
        description: >
          The amount, always carried at exactly two decimal places. Quantized
          at construction, never on read, so two values that compare equal
          also serialize identically and hash identically.
        constraints:
          - Exactly 2 decimal places after construction — not "at most 2"
          - Magnitude bounded by the storage contract of 12 total digits,
            i.e. 10 integer digits and 2 fractional digits
      - name: currency
        logical_type: implicit_constant
        required: true
        value: BDT
        description: >
          Not a stored attribute and not a field on the wire. There is no
          second currency in this system, so a currency field would be a
          column and a JSON key that is always the same value. Recorded here
          because "BDT is implicit" is a design decision a future reader must
          be able to find, not an omission.
    invariants:
      - id: MONEY-INV-1
        statement: Scale is exactly 2 at all times after construction.
      - id: MONEY-INV-2
        statement: >
          Equality, ordering and hashing are consistent with each other and
          with serialization. Two equal values produce the same wire string.
      - id: MONEY-INV-3
        statement: >
          Immutability. No operation mutates a Money value; every arithmetic
          operation returns a new one.
      - id: MONEY-INV-4
        statement: >
          A Money value MAY be negative in general. The type itself does not
          forbid a negative amount, because intermediate arithmetic legitimately
          produces one — the per-cycle formula computes a negative figure before
          the floor is applied, and a subtraction of a larger amount from a
          smaller one is a meaningful intermediate. See the sign discipline
          below for exactly where negatives are and are not allowed.
    sign_discipline:
      description: >
        Where a negative amount is permitted is a property of the CONTEXT,
        not of the type. Stating it per-context is deliberate: a blanket
        non-negative Money would make the per-cycle formula inexpressible
        and push the floor into every caller.
      negative_permitted:
        - context: Intermediate arithmetic
          rationale: >
            Subtraction may legitimately cross zero mid-calculation. The
            per-cycle outstanding formula subtracts received, forgiven,
            applied credit and carried-out from charged plus carried-in, and
            that expression is negative whenever a cycle was over-settled.
        - context: A signed difference a caller computes deliberately
          rationale: >
            A reconciliation delta or a variance is a signed quantity and
            the type must be able to carry one.
      negative_forbidden:
        - context: LedgerEntry.amount
          rule: Always >= 0. The sign lives in the kind, never in the amount.
          source: ADR-002
          violation: Rejected at construction of the entry, not at read time.
        - context: outstanding, per cycle and in total
          rule: Always >= 0. Floored at zero by the max(0, ...) in the formula.
          source: FR5.9, ADR-002
        - context: available_credit
          rule: >
            Always >= 0. Guaranteed by construction, not by a floor: credit is
            applied as min(available_credit, amount_owed), so apply can never
            exceed grant.
          source: ADR-002
        - context: A charged amount, a claimed amount or an approved amount
          rule: Always >= 0. A negative charge is a correction, expressed as a
            compensating entry of a different kind, never as a negative amount.
          source: ADR-002, FR9.1
    explicitly_unsupported:
      - operation: conversion to a binary floating-point number
        reason: >
          Not defined, in either direction. Construction from a float raises.
          This makes the float prohibition a property of the type rather than
          a rule somebody has to remember, and closes the gap a float ban alone
          leaves open — constructing a decimal FROM a float produces a decimal,
          so a type check passes while the value is already wrong.
        source: project.md NEVER-rule, TC-7, D-20, NFR9
      - operation: conversion to an integer
        reason: Silently discards the fractional part. Not defined.
      - operation: multiplication as an operator
        reason: >
          Multiplication is where rounding enters. Exposed only as a named
          operation that states its rounding, so no rounding is ever anonymous.
      - operation: division as an operator
        reason: >
          Not exposed until a requirement needs it. An unconstrained division
          is how a one-paisa discrepancy enters a ledger. Splitting is the
          allocation operation, whose parts sum exactly to the original.
      - operation: arithmetic with a bare number
        reason: >
          Addition and subtraction accept only Money. A bare number is a type
          error at build time, never a silent coercion.
      - operation: comparison against a bare number
        reason: >
          A type error. The zero constant exists so that a caller never needs
          to write a bare zero in a comparison.

enumerations:
  - name: LedgerEntryKind
    kind: enumeration
    persisted_by: U7 fee-cycles-and-ledger
    semantics_owned_by: U1 money-core
    description: >
      The seven kinds of append-only ledger entry. Amounts are ALWAYS
      non-negative; the sign lives in the kind. This Unit owns the arithmetic
      meaning of each kind — which side of the ledger identity it falls on and
      how it folds into a derived quantity — because that meaning is what the
      property test verifies. U7 owns the rows.
    closed: true
    extension_rule: >
      A sixth or eighth quantity is a new value here, not a schema migration.
      Adding one requires re-deriving the identity and re-running the property
      test, because a new kind that is not placed on a side of the identity
      silently breaks it.
    values:
      - value: charge
        meaning: >
          An amount billed to an enrollment for a period. The fee anchor is
          teacher-adjustable, so a charge is what was actually billed, not a
          fixed amount due.
        identity_side: debit_increases_obligation
        enrollment_identity_role: >
          Adds to total_charged, on the left-hand side of the enrollment
          identity.
        per_cycle_role: positive term
        source: FR5.1, ADR-002
      - value: receipt
        meaning: >
          Money actually received and applied against what was owed. Records
          only the APPLIED part of a payment — the excess becomes a separate
          credit_grant. This split is exactly why cash in is receipts PLUS
          credit grants.
        identity_side: credit_reduces_obligation
        enrollment_identity_role: >
          Part of total_cash_in, subtracted on the left-hand side.
        per_cycle_role: negative term
        source: FR5.1, ADR-002
      - value: carry_forward
        meaning: >
          A debt moved INTO this period from an earlier one. The receiving
          half of a two-sided carry.
        identity_side: internal_transfer
        enrollment_identity_role: >
          Does NOT appear in the enrollment-level identity at all. Moving a
          debt between periods is not an economic event. It cancels against
          carried_out.
        per_cycle_role: positive term
        source: FR5.1, ADR-002
      - value: carried_out
        meaning: >
          A debt moved OUT of this period to a later one. The relieving half
          of a two-sided carry. Never appended without its paired
          carry_forward.
        identity_side: internal_transfer
        enrollment_identity_role: >
          Does NOT appear in the enrollment-level identity. Cancels against
          carry_forward.
        per_cycle_role: negative term
        source: FR5.1, ADR-002
      - value: forgiveness
        meaning: >
          An amount the teacher waived. The obligation is extinguished without
          money arriving.
        identity_side: credit_reduces_obligation
        enrollment_identity_role: >
          Subtracted on the left-hand side, separately from cash in, because
          analytics must be able to exclude waivers from a collection-rate
          denominator.
        per_cycle_role: negative term
        source: FR5.1, AC6.3.3, ADR-002
      - value: credit_grant
        meaning: >
          Money received in excess of what was owed, held against the
          ENROLLMENT rather than any cycle. Appended alongside the receipt for
          the applied part when an approved payment exceeds the charge.
        identity_side: credit_reduces_obligation
        enrollment_identity_role: >
          Part of total_cash_in, subtracted on the left-hand side. This is the
          term whose omission made an earlier correction attempt fail on the
          very overpayment case that motivated it. Money received as credit is
          money received.
        per_cycle_role: >
          Not a per-cycle term. A credit granted in one period does not belong
          to that period; it belongs to the enrollment.
        source: FR5.9, AC6.3.7, ADR-002
      - value: credit_apply
        meaning: >
          Previously granted credit consumed against a later charge. Appended
          at an amount of min(available_credit, amount_owed), which is what
          keeps available credit non-negative by construction.
        identity_side: internal_transfer_against_credit
        enrollment_identity_role: >
          Does not appear directly on the left-hand side. It reduces
          available_credit on the right-hand side, which is how applying a
          credit moves value from the credit half to the settled half without
          changing the total.
        per_cycle_role: negative term
        source: FR5.9, AC6.3.8, AC8.3.4, ADR-002

computed_quantities:
  description: >
    Every quantity below is DERIVED by folding ledger entries. None is stored.
    This Unit owns the formulas and the property test that verifies them; U7
    owns the entries they fold over and U9 the analytics that read them.
  scope_enrollment:
    - name: total_charged
      formula: sum of amount over entries of kind charge
      constraints: [">= 0"]
    - name: total_forgiven
      formula: sum of amount over entries of kind forgiveness
      constraints: [">= 0"]
    - name: total_receipt
      formula: sum of amount over entries of kind receipt
      constraints: [">= 0"]
    - name: total_credit_grant
      formula: sum of amount over entries of kind credit_grant
      constraints: [">= 0"]
    - name: total_credit_apply
      formula: sum of amount over entries of kind credit_apply
      constraints: [">= 0"]
    - name: total_cash_in
      formula: total_receipt + total_credit_grant
      note: >
        Named explicitly because "cash in is receipts plus credit grants" is
        the single correction that makes the identity hold on an overpayment.
    - name: available_credit
      formula: total_credit_grant - total_credit_apply
      constraints: [">= 0"]
      guaranteed_by: >
        Construction, not a floor. Each apply is bounded by min(available_credit,
        amount_owed), so apply can never outrun grant.
    - name: total_outstanding
      formula: sum of per-cycle outstanding over every cycle of the enrollment
      constraints: [">= 0"]
      note: >
        The sum of already-floored per-cycle figures, NOT a floor applied to a
        sum. The distinction is load-bearing: one over-settled cycle must not
        silently offset another cycle's genuine debt.
  scope_cycle:
    - name: outstanding
      formula: >
        max(0, charged + carried_in - received - forgiven
               - credit_applied - carried_out)
      constraints: [">= 0"]
      note: >
        Each term is that cycle's sum for the corresponding kind. The
        credit_applied term was missing from an earlier correction attempt,
        which computed 1000 outstanding on a 1000 charge with 200 credit
        applied instead of 800.
  identity:
    id: LEDGER-IDENTITY
    statement: >
      total_charged - total_forgiven - (total_receipt + total_credit_grant)
        == total_outstanding - available_credit
    companions:
      - available_credit >= 0
      - total_outstanding >= 0
      - sum over carry_forward == sum over carried_out
    plain_english: >
      Every taka charged and not forgiven is either still owed or has been
      received — and anything received beyond what was owed is held as credit.
      Outstanding and credit are the two non-negative halves of one signed
      quantity, which is what makes the never-negative rule expressible at all.
    carry_forward_absence: >
      Neither carry kind appears in this identity. That is the correct result,
      not an oversight: moving a debt between periods is not an economic event.
      The companion equation is what keeps the two halves honest.
    verification_status: verified
    verification_evidence: >
      Re-verified at this stage independently of ADR-002: eight worked
      scenarios computed term by term (all pass), then 20,000 randomized
      enrollment histories composing charge, receipt, partial and over
      payment, waiver, two-sided single and multi-period carry, credit grant
      and credit apply in arbitrary order over one to six periods. Zero
      failures. Verified rather than asserted because this identity was wrong
      twice before randomized testing settled it.

non_entities:
  - name: FeeCycle
    owned_by: U7
    note: >
      Named here only to state what this Unit does NOT own. U1 computes a
      per-cycle outstanding figure; it does not know what a period is, when
      one generates, or that an idempotency constraint exists.
  - name: LedgerEntry
    owned_by: U7
    note: >
      U1 owns the arithmetic meaning of the kind and the non-negativity of the
      amount. U7 owns the row, its identifiers, its actor and its
      append-only-with-supersession discipline.
```

---

## Part B — Summary

**This Unit persists nothing.** There is no table, no migration, no
identifier and no lifecycle. The block above is a specification of **value
semantics that the persisting Units must honour** — which is an unusual shape
for an entity model and is stated plainly rather than disguised as one.

What it owns is three things:

**`Money`, a value type.** Defined by its attributes rather than by identity,
immutable, always at exactly two decimal places, with Bangladeshi Taka
implicit because there is no second currency. The interesting part of its
specification is what it refuses: no float conversion in either direction, no
multiplication operator, no division operator, no arithmetic or comparison
with a bare number. Each refusal converts a rule somebody would otherwise have
to remember into a build-time failure.

On negatives, the model is deliberately precise rather than blanket. The
*type* permits a negative amount, because intermediate arithmetic legitimately
produces one — the per-cycle formula is negative before its floor is applied.
What forbids negatives is the **context**: a ledger entry's amount, an
outstanding figure and an available-credit figure are each non-negative, and
each for its own reason. A blanket non-negative type would make the per-cycle
formula inexpressible and push the floor into every caller, which is exactly
the leak the money boundary exists to prevent.

**`LedgerEntryKind`, a closed enumeration of seven values.** Amounts are
always non-negative and the sign lives in the kind. Three of the seven are
economic events that appear in the enrollment-level identity (`charge`,
`receipt`, `forgiveness`, with `credit_grant` joining the received side).
Two are internal transfers that cancel exactly (`carry_forward` and
`carried_out`), and one moves value between the credit half and the settled
half (`credit_apply`). U7 owns the rows; U1 owns what each kind *means
arithmetically*, because that meaning is what the property test verifies.

**The derived quantities and the identity that binds them.** Nothing is
stored; every balance is a fold over entries. The identity is stated in its
verified form, and the two places earlier attempts went wrong are recorded in
the block itself so the next reader cannot repeat them: cash in is receipts
**plus** credit grants, and the per-cycle formula needs its `credit_applied`
term.

The identity was **re-verified at this stage** rather than inherited on
trust — eight worked scenarios computed term by term, then 20,000 randomized
histories. Zero failures. This is the practice talking: a money invariant is
verified before it is recorded as satisfied, because an unverified invariant
standing behind 100% branch coverage certifies the arithmetic it was meant to
check.
