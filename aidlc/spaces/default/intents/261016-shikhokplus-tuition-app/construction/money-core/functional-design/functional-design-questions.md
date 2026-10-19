# Functional Design Questions — money-core (U1)

**Stage**: functional-design (3.1)
**Unit**: U1 `money-core`
**Phase**: Construction
**Depth**: Comprehensive

> The decisions this Unit's design turns on. Each one was open in the sense
> that the upstream artifacts constrain it without settling it; each was
> decided against the affirmed practices and the verified ledger invariant
> rather than by preference.

---

## Q1 — Does this Unit model the ledger entry as an entity, or only the arithmetic over it?

U1 owns the Money type, the rounding mode and the ledger identity; U7
`fee-cycles-and-ledger` owns the entries and their persistence
[unit-of-work-story-map, US5.2]. The question is where the *shape* of a ledger
entry is specified. If U1 specifies it, U7 implements against it. If U7
specifies it, U1 cannot state the invariant over it.

[Answer]: U1 specifies the ledger entry as a value shape — kind, amount,
enrollment, period — and states the invariant over it, but persists nothing and
owns no table. The affirmed practice puts 100% branch coverage on this module
and requires it to import no ORM, no session and no settings, which is only
achievable if the entry is a value here. U7 owns the table, the constraint and
the writes.

---

## Q2 — Which of the seven entry kinds does U1 define, and does it validate the set?

The seven kinds are `charge`, `receipt`, `carry_forward`, `carried_out`,
`forgiveness`, `credit_grant`, `credit_apply` [ADR-002]. An eighth would break
the verified invariant.

[Answer]: U1 defines all seven as a closed set and rejects any other value. The
invariant is stated in terms of those seven and was verified against exactly
them; a kind U1 does not know about would be silently excluded from the sums,
which is the failure mode that produces a balance that looks right and is not.
Closed is the only safe shape.

---

## Q3 — Is `available_credit` a stored quantity or a derived one?

ADR-002 gives `available_credit = credit_grant - credit_apply`, with the
constraint `available_credit >= 0`.

[Answer]: Derived, never stored. The whole ledger is append-only with a derived
balance [ADR-002]; storing a credit total alongside the entries that produce it
creates a second source of truth that drifts. The `>= 0` constraint is enforced
at the point a `credit_apply` is proposed — an application exceeding the
available grant is refused — rather than by clamping the derived figure, because
clamping hides the defect that produced it.

---

## Q4 — How does the design express carry-forward's two-sidedness so it cannot be implemented one-sided?

A one-sided carry counts the same debt twice: carrying 1000 into a second 1000
charge reads 3000 owed against a true 2000.

[Answer]: As a single operation producing a *pair* of entries — `carried_out`
against the origin period and `carry_forward` against the receiving one — never
as two independently callable operations. The invariant
`sum(carry_forward) == sum(carried_out)` is then structurally true rather than
something a caller must remember. A named test covers a multi-period carry, not
only a single one, because a single carry passes against a model that
double-counts.

---

## Q5 — Does `Money` expose division?

The affirmed Code Style says division is not exposed until a requirement needs
it, and that splitting is `allocate(n)` with exact-sum remainder distribution.

[Answer]: No division operator. `allocate(n)` is specified in this Unit because
the requirement for it is foreseeable (splitting a fee across periods) and
specifying it later would mean specifying it under deadline. `apply_rate` covers
the multiplication case and names its rounding. An unconstrained `/` is how a
one-paisa discrepancy enters a ledger.

---

## Q6 — Where does rounding happen, and how many places can it happen?

`ROUND_HALF_UP`, declared once as a module constant, with values quantized to
2dp at construction.

[Answer]: Exactly two places, both named: construction (quantize to 2dp) and
`apply_rate` (the only operation that can produce more than 2dp). Addition,
subtraction and summation over already-quantized values cannot introduce a third
decimal, so they do not round and must not be written as if they might. Naming
the two places is what makes "no anonymous rounding" checkable.

---

## Q7 — What does the design say about the error taxonomy for money operations?

U2 `api-contract` owns the five-class taxonomy; U1 is built before U2.

[Answer]: U1 raises `ValidationError` for a malformed or out-of-domain input
(construction from a float, a negative where the kind forbids it, an unknown
entry kind) and `ConflictError` for a state-forbidden operation (a
`credit_apply` exceeding available credit). It defines no envelope and no HTTP
mapping — those are U2's. Naming the classes now means U2's handler finds them
already raised correctly rather than retrofitting them.

> **Correction, found at design review and recorded rather than absorbed.**
> The `ConflictError` half of this answer does not survive contact with the
> rest of the design, and the artifacts now say so. BR4.5 computes the applied
> credit as `min(available_credit, amount_owed)` — so a `credit_apply`
> exceeding available credit is not *refused*, it is **unrepresentable**,
> because the amount is computed rather than supplied. Worked scenario S8 is
> exactly that case and ends in a successful apply. A raise on that condition
> would be dead code, and under this module's 100% branch-coverage obligation
> an unreachable branch makes the target unmeetable.
>
> The answer above is kept as written because it is the confirmed input. What
> the design does: **one class, always — a validation failure.** Three of the
> five taxonomy classes are structurally unreachable in a module that holds no
> state and does no I/O. See `functional-spec.md` §5.6 and BR1.8, which carry
> the reasoning. The decision this answer was really making — *name the class
> now so U2 does not retrofit one later* — is honoured; only the count changed.

---

## Q8 — Is correction history (AC5.2.2) in scope for this Unit?

AC5.2.2 concerns the correction history of ledger entries.

[Answer]: No — deferred to U7, and recorded as **Deferred** in `traceability.json`
rather than claimed. Correction history is a property of entries and their
supersession, which requires persistence; this Unit persists nothing. Marking it
Deferred rather than covered is what keeps the coverage figure honest.

---

## Assumptions & Open Questions

None.

---

## Consolidated Summary Confirmation

The design decided above: a value-only money module owning the `Money` type,
the seven-kind closed ledger vocabulary, the verified balance invariant, the
two-sided carry-forward as a single paired operation, `allocate` and
`apply_rate` with their two named rounding points, and the two error classes it
raises. It persists nothing, imports no ORM or session, and defers correction
history to U7.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions

---

