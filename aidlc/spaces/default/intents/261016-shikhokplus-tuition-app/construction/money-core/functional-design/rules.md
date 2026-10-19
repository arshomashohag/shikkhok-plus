# Business Rules — `money-core` (U1)

**Stage**: functional-design (3.4)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

## Sources

- [stage] `functional-design-questions.md` — Q4 (carry-forward as one paired
  operation), Q5 (no division; `allocate`), Q6 (rounding in exactly two named
  places), Q7 (the two error classes this Unit raises)
- [upstream] `inception/requirements-analysis/requirements.md` — FR5.1, FR5.2, FR5.9, FR5.7, NFR9
- [upstream] `inception/domain-design/decisions.md` — ADR-002
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [upstream] `inception/delivery-planning/bolt-plan.md` — B1 DoD
- [team] `## Code Style` → "Money as a type, on both surfaces"
- [team] `## Testing Posture` → money-module obligations
- [project] `## Forbidden` / `## Mandated` money rules

---

## Part A — Source of truth

```yaml
rules:

  # ---- BR1.x — Construction and representation ----

  - id: BR1.1
    statement: >
      Constructing a Money value from a binary floating-point number is
      refused.
    category: validation
    applies_to: Money construction
    trigger: Any attempt to construct a Money value
    logic: >
      IF the supplied value is a binary floating-point number
      THEN refuse the construction and raise a validation failure
      ELSE accept a fixed-point decimal, a string, or an integer.
    violation_behaviour: >
      Raises at construction. Never coerced, never rounded into acceptability,
      never logged-and-continued. This is a build-or-crash boundary, not a
      warning.
    rationale: >
      Makes the float prohibition a property of the type rather than a rule a
      reviewer has to enforce. A solo build with one reviewer cannot rely on
      review for this.
    source: [project.md NEVER-rule, NFR9, FR5.7, TC-7, D-20, team: Code Style]

  - id: BR1.2
    statement: >
      Constructing the underlying fixed-point decimal from a floating-point
      number is forbidden anywhere in the module.
    category: constraint
    applies_to: The money module's internals
    trigger: Any decimal construction inside the module
    logic: >
      IF a fixed-point decimal is constructed from a floating-point value
      THEN the construction is forbidden, whether the float is a literal or a
      variable.
    violation_behaviour: >
      A literal float is caught by the configured lint rule and fails the
      build. A variable-valued float is caught by BR1.1, because such a value
      cannot reach a Money value by any other path.
    rationale: >
      This closes the gap that a float ban alone leaves open. Constructing a
      decimal from a float produces a decimal, so a type check passes while
      the value is already wrong — the classic case being a tenth, which has
      no exact binary representation.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR1.3
    statement: >
      A Money value is quantized to exactly two decimal places at
      construction.
    category: calculation
    applies_to: Money construction
    trigger: Every construction, without exception
    logic: >
      IF a Money value is constructed
      THEN its amount is quantized to exactly two decimal places immediately,
      using the module's single declared rounding mode (BR3.1).
    violation_behaviour: >
      Not reachable by a caller — quantization is unconditional. An
      unquantized value cannot exist.
    rationale: >
      Quantizing at construction rather than on read is what makes equality,
      ordering, hashing and serialization mutually consistent. An unquantized
      value makes two "equal" amounts hash differently and serialize
      differently, which bites in sets, in dictionary keys and on the wire.
    source: [team: Code Style, contract-summary §E.1, NFR9]

  - id: BR1.4
    statement: >
      Bangladeshi Taka is implicit. A Money value carries no currency
      attribute and no currency field crosses the boundary.
    category: policy
    applies_to: Money representation, in memory, in storage and on the wire
    trigger: Any representation of a money value
    logic: >
      IF a money value is represented anywhere
      THEN it carries an amount only; the currency is BDT by construction and
      is never transmitted, stored or compared.
    violation_behaviour: >
      A currency field appearing in a money representation is a design defect
      caught in review and by the schema diff gate.
    rationale: >
      There is no second currency in this system. A currency field would be a
      column and a JSON key whose value is always the same. Recorded as a rule
      rather than left unstated so the decision is findable.
    source: [NFR9, contract-summary §B.5]

  - id: BR1.5
    statement: >
      A Money value is immutable. Every operation returns a new value.
    category: constraint
    applies_to: Every Money operation
    trigger: Any arithmetic or transformation
    logic: >
      IF an operation is performed on a Money value
      THEN a new Money value is returned and the operand is unchanged.
    violation_behaviour: >
      Not reachable — the type exposes no mutating operation.
    rationale: >
      A value object is defined by its attributes. Mutation would make two
      values that were equal stop being equal without either being replaced,
      which is incoherent for a type used as a dictionary key.
    source: [team: Code Style, domain-design: Money component]

  - id: BR1.6
    statement: >
      Conversion of a Money value to a floating-point number or to an integer
      is not defined.
    category: constraint
    applies_to: The Money type's surface
    trigger: Any attempt to convert a Money value to a primitive number
    logic: >
      IF a caller attempts a conversion to a float or to an integer
      THEN the operation does not exist and the build fails.
    violation_behaviour: Build-time failure. Not a runtime check.
    rationale: >
      The float conversion would reintroduce the exact representation error
      BR1.1 excludes, by the back door. The integer conversion silently
      discards paisa.
    source: [contract-summary §E.1, project.md NEVER-rule]

  - id: BR1.7
    statement: >
      A value whose quantized magnitude exceeds ten integer digits is refused
      at construction.
    category: validation
    applies_to: Money construction
    trigger: Constructing a Money value
    logic: >
      IF the quantized magnitude requires more than ten integer digits
      THEN refuse the construction and raise a validation failure.
    violation_behaviour: ValidationError. The value is rejected, not truncated.
    rationale: >
      The storage contract is twelve total digits with two decimal places,
      leaving ten for the integer part. Refusing at construction means an
      unstorable value can never exist in memory, so the failure surfaces at
      the point the bad number was produced rather than at a database write
      far away from its cause. Truncating or saturating would silently alter
      an amount, which is the one thing a money type must never do.
    source: [contract-summary §B.5, entities.md storage contract]

  - id: BR1.8
    statement: >
      Every refusal in this module raises a validation failure, and only a
      validation failure. The module defines no envelope, no code string, no
      retryable flag and no HTTP status.
    category: policy
    applies_to: Every refusal path in the module
    trigger: Any refusal
    logic: >
      IF any operation in this module refuses
      THEN it raises a validation failure, because every refusal here is
      caused by the input itself.
    violation_behaviour: >
      An untyped or bare exception from this module is a defect, caught by the
      module's own tests which assert the class per refusal path. A refusal
      that is NOT a validation failure is a signal that state or I/O has
      entered the module, and is a reason to stop rather than to add a class.
    rationale: >
      team.md makes retryability a property of the class chosen at the raise
      site, read off the type by every layer above. U2 owns the five-class
      taxonomy and the envelope but is built after U1, so an untyped U1 would
      force U2 to retrofit the taxonomy across the module whose import
      boundary exists to keep it stable - and which is already under 100%
      branch coverage. Three of the five classes are structurally unreachable
      here. A conflict means a well-formed operation the current state
      forbids, and this module holds no state: no session, no repository, no
      stored balance, every operation a pure function of its arguments, so
      there is no world that can change underneath a caller. A transient
      failure means a retry may succeed, and BR6.1 bars the I/O that could
      produce one. A fatal failure is an assertion, not a raise site. What
      remains is the input being wrong. Note specifically that a credit
      application exceeding available credit is NOT a conflict: BR4.5
      computes the applied amount as min(available_credit, amount_owed), so
      over-application is unrepresentable rather than refused, and a raise on
      that condition would be dead code that the 100% branch coverage
      obligation could never cover.
    source: [team.md Error handling, functional-design-questions.md Q7, BR4.5, BR6.1]

  # ---- BR2.x — Arithmetic operations ----

  - id: BR2.1
    statement: >
      Addition and subtraction accept only another Money value.
    category: validation
    applies_to: Money addition and subtraction
    trigger: Any addition or subtraction
    logic: >
      IF the operand is a Money value THEN perform the operation and return a
      new Money value
      ELSE the operation is a type error.
    violation_behaviour: >
      A build-time type error, not a runtime coercion. Adding a bare number
      to a money value never silently works.
    rationale: >
      The failure mode this prevents is a bare number — a count, an index, a
      percentage expressed as a whole number — being added to an amount and
      producing a plausible wrong answer.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR2.2
    statement: >
      Multiplication is a named operation that states its rounding. There is
      no multiplication operator.
    category: calculation
    applies_to: Scaling a Money value by a rate
    trigger: Any scaling of an amount
    logic: >
      IF a caller needs to scale an amount by a rate
      THEN they invoke the named rate-application operation, which multiplies
      and then rounds the result to two decimal places using the module's
      single declared rounding mode (BR3.1), returning a new Money value.
    violation_behaviour: >
      A multiplication operator does not exist, so the alternative is a build
      failure rather than an unrounded or anonymously-rounded result.
    rationale: >
      Multiplication is the operation where rounding enters, and an operator
      lets rounding happen without the caller ever saying so. Forcing a named
      operation means every rounding in the system is at a call site somebody
      wrote deliberately. No anonymous rounding.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR2.3
    statement: >
      Division is not exposed. Splitting an amount is an allocation operation
      whose parts sum exactly to the original.
    category: calculation
    applies_to: Dividing or splitting a Money value
    trigger: Any requirement to split an amount into parts
    logic: >
      IF an amount must be split into a number of parts
      THEN the allocation operation returns that many Money values whose sum
      is exactly equal to the original amount, distributing the indivisible
      remainder one smallest-unit at a time across the leading parts
      ELSE no division operation exists.
    violation_behaviour: >
      A division operator does not exist. An allocation whose parts did not
      sum exactly to the original would be a defect caught by the named test.
    rationale: >
      An unconstrained division is how a one-paisa discrepancy enters a
      ledger: three equal shares of a sum that does not divide by three, each
      rounded independently, do not add back up. Exact-sum allocation makes
      the discrepancy structurally impossible rather than merely unlikely.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR2.4
    statement: >
      A zero constant exists on the type, and comparing a Money value against
      a bare number is a type error.
    category: constraint
    applies_to: Comparison of Money values
    trigger: Any comparison
    logic: >
      IF a caller compares against zero
      THEN they compare against the type's zero constant
      ELSE IF they compare against a bare number
      THEN the comparison is a type error.
    violation_behaviour: Build-time type error.
    rationale: >
      A bare zero in a comparison is the one place a raw number reliably
      creeps into otherwise-typed money code. Providing the constant removes
      the reason to write one; making the comparison a type error removes the
      option.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR2.5
    statement: >
      A summation operation with a zero identity exists on the type.
    category: calculation
    applies_to: Totalling a collection of Money values
    trigger: Any total across a collection
    logic: >
      IF a collection of Money values is totalled
      THEN the type's summation operation is used, which starts from the zero
      constant and returns zero for an empty collection
      ELSE a generic summation starting from a bare zero would either coerce
      or fail.
    violation_behaviour: >
      A generic summation over Money values fails at build time by BR2.1,
      because its implicit zero start value is a bare number.
    rationale: >
      A dues total across batches is the single operation most likely to be
      written as a generic sum with a bare-zero start. Providing the typed
      operation means the natural way to write it is also the correct way.
    source: [team: Code Style, contract-summary §E.1, FR7.2]

  - id: BR2.6
    statement: >
      Sign predicates live on the type.
    category: calculation
    applies_to: Testing the sign of a Money value
    trigger: Any sign test
    logic: >
      IF a caller needs to know whether an amount is zero or positive
      THEN they use the type's predicates
      ELSE sign-convention knowledge spreads across call sites.
    violation_behaviour: >
      A hand-rolled sign test using a bare number fails at build time by
      BR2.4.
    rationale: >
      Keeps the sign convention in one place, which matters because the sign
      discipline in this system is context-dependent rather than uniform.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR2.7
    statement: >
      The Money type itself permits a negative amount; non-negativity is
      enforced per context, not by the type.
    category: policy
    applies_to: Every money-carrying context
    trigger: Construction or computation of any money value
    logic: >
      IF the value is an intermediate arithmetic result or a deliberate signed
      difference THEN a negative amount is permitted
      ELSE IF the value is a ledger entry amount, an outstanding figure, an
      available-credit figure, a charged amount, a claimed amount or an
      approved amount
      THEN it must be non-negative, enforced at that context's own boundary.
    violation_behaviour: >
      A negative ledger entry amount is refused where the entry is
      constructed. A negative outstanding is impossible by BR4.4's floor. A
      negative available credit is impossible by BR4.5's construction.
    rationale: >
      A blanket non-negative type would make the per-cycle outstanding formula
      inexpressible, because that expression is genuinely negative before its
      floor is applied, and would push the floor into every caller — which is
      the leak the money boundary exists to prevent.
    source: [ADR-002, FR5.9, AC6.3.7]

  - id: BR2.8
    statement: >
      Allocation into fewer than one part is refused.
    category: validation
    applies_to: The allocate operation
    trigger: Calling allocate
    logic: >
      IF the requested part count is less than one
      THEN refuse and raise a validation failure.
    violation_behaviour: ValidationError. Never an empty list.
    rationale: >
      Returning an empty list for a count of zero would satisfy the exact-sum
      property vacuously for a zero amount and violate it for any other,
      turning a caller's arithmetic error into either a silent no-op or a lost
      amount. A count below one is a caller defect and is named as one.
    source: [team.md Code Style allocate, functional-spec.md §2.5]

  - id: BR2.9
    statement: >
      Allocation of a negative amount distributes the magnitude and then
      restores the sign to every part.
    category: calculation
    applies_to: The allocate operation
    trigger: Calling allocate with a negative amount
    logic: >
      IF the amount is negative
      THEN allocate the absolute value into the requested parts, then apply
      the negative sign to each resulting part.
    violation_behaviour: >
      None at runtime - this fixes an answer that would otherwise be
      implementation-defined. Asserted by a named test on a negative amount
      whose magnitude does not divide evenly.
    rationale: >
      BR2.7 permits negative Money, and the exact-sum property of BR2.3 holds
      under every reasonable reading of a negative split: floor division gives
      -0.02, -0.02, -0.01 for -0.05 into three, truncating division gives
      -0.01, -0.02, -0.02, and both sum to exactly -0.05. BR2.3's test
      therefore passes against either, so without this rule two implementers
      diverge permanently with no check failing. Allocating on the magnitude
      makes the negative case the mirror of the positive one.
    source: [functional-spec.md §2.5, BR2.3, BR2.7]

  - id: BR2.10
    statement: >
      A rate must be an exact decimal and must not be negative. A rate of zero
      or above one is permitted.
    category: validation
    applies_to: The apply_rate operation
    trigger: Calling apply_rate
    logic: >
      IF the rate is a binary floating-point number OR the rate is negative
      THEN refuse and raise a validation failure
      ELSE apply it, including rates of zero and rates greater than one.
    violation_behaviour: ValidationError.
    rationale: >
      A float rate is wrong before it is multiplied, for the same reason
      BR1.1 refuses a float amount. A negative rate would manufacture a
      negative Money that BR2.7 then permits to propagate - the exact defect
      class the sign rules exist to prevent - and a reduction is properly a
      compensating entry under BR4.1, never a negative rate. Rates above one
      are deliberately permitted: a late fee or a multi-month catch-up charge
      is such a rate, and refusing it would push that arithmetic outside the
      module boundary.
    source: [BR1.1, BR2.7, BR4.1, team.md Code Style apply_rate]

  # ---- BR3.x — Rounding ----

  - id: BR3.1
    statement: >
      The rounding mode is half-up, declared exactly once in this module.
    category: policy
    applies_to: Every rounding in the system
    trigger: Any operation that rounds — construction, rate application
    logic: >
      IF a money value must be rounded
      THEN a value exactly halfway between two representable amounts rounds
      away from zero to the larger magnitude, and this mode is read from the
      module's single declaration rather than restated at the call site.
    violation_behaviour: >
      A locally-specified rounding mode is a defect. There is exactly one
      declaration, so there is exactly one place to change it and exactly one
      place to read it.
    rationale: >
      This is a decision, not a default. The ambient default of the
      fixed-point decimal facility is banker's rounding — half to even —
      which is wrong for consumer-facing fee amounts: a teacher checking
      arithmetic by hand expects a half to round up. The divergence is real
      and was confirmed numerically at this stage: half-up and half-even
      differ at 0.005 (0.01 against 0.00), at 0.025 (0.03 against 0.02) and at
      1.005 (1.01 against 1.00). The choice is invisible once made and
      expensive to change after a ledger exists.
    source: [team: Code Style, contract-summary §E.1]

  - id: BR3.2
    statement: >
      No rounding happens anonymously.
    category: constraint
    applies_to: Every rounding site
    trigger: Any operation that could round
    logic: >
      IF an operation rounds
      THEN it is either construction (BR1.3) or the named rate application
      (BR2.2), both of which state the mode explicitly
      ELSE the operation does not exist.
    violation_behaviour: >
      Unreachable: the only operations that can round are the two named ones.
      Addition and subtraction of two two-place values never need to round,
      and allocation distributes rather than rounds.
    rationale: >
      "Where did this paisa go" is answerable only if the set of places that
      can round is small and enumerable.
    source: [team: Code Style]

  # ---- BR4.x — The ledger identity and its derived quantities ----

  - id: BR4.1
    statement: >
      A ledger entry amount is always non-negative. The sign lives in the
      kind.
    category: validation
    applies_to: Every ledger entry
    trigger: Construction of any ledger entry
    logic: >
      IF a ledger entry is constructed with a negative amount
      THEN refuse it. A correction is a compensating entry of the appropriate
      kind, never a negative amount on the original kind.
    violation_behaviour: >
      Refused at construction. A negative amount reaching the fold would
      invert a term's contribution to the identity silently.
    rationale: >
      Putting the sign in the kind rather than in the amount is what makes
      every derived quantity a plain sum of non-negative values, and makes
      "which side of the identity does this fall on" a property of the kind
      rather than of the row.
    source: [ADR-002, FR5.1]

  - id: BR4.2
    statement: >
      Every derived quantity is a fold over ledger entries. None is stored.
    category: calculation
    applies_to: All eight derived quantities
    trigger: Any read of a balance, a total or a status
    logic: >
      IF a balance is needed
      THEN it is computed by folding the relevant entries by kind
      ELSE no money column holds an answer.
    violation_behaviour: >
      A stored balance column is a design defect. It stores the answer, which
      is what made every new quantity a migration in the superseded model.
    rationale: >
      A sixth quantity becomes a new kind value rather than a schema change —
      which matters concretely, because this model is already on its second
      revision and the fee model is known to be in further revision.
    source: [ADR-002, FR5.1]

  - id: BR4.3
    statement: >
      The enrollment-level ledger identity, in its verified form.
    category: calculation
    applies_to: Every enrollment, after every ledger operation
    trigger: Any append to the ledger; continuously as an invariant
    logic: >
      IF the entries for an enrollment are folded by kind
      THEN the following holds exactly:
        total_charged - total_forgiven - (total_receipt + total_credit_grant)
          == total_outstanding - available_credit
      In plain English: every taka charged and not forgiven is either still
      owed or has been received, and anything received beyond what was owed is
      held as credit.
    violation_behaviour: >
      A failure of this equality is a defect in the money module, surfaced by
      the property test rather than discovered in a teacher's balance. It is
      never reconciled by adjusting a figure.
    rationale: >
      Cash in is receipts PLUS credit grants, because a receipt records only
      the APPLIED part of a payment and the excess arrives as a credit grant.
      Omitting the credit-grant term is precisely how an earlier correction
      attempt failed on the very overpayment case that motivated it. Neither
      carry kind appears here, which is the correct result: moving a debt
      between periods is not an economic event.
    source: [ADR-002, FR5.1, FR5.9, team: ledger invariant]

  - id: BR4.4
    statement: >
      Per-cycle outstanding never goes negative, and total outstanding is the
      sum of already-floored per-cycle figures.
    category: calculation
    applies_to: Every fee cycle and every enrollment
    trigger: Any computation of outstanding
    logic: >
      IF a cycle's outstanding is computed
      THEN it is max(0, charged + carried_in - received - forgiven
                        - credit_applied - carried_out)
      AND the enrollment's total outstanding is the sum of those floored
      per-cycle figures, never a floor applied to a signed sum.
    violation_behaviour: >
      A negative outstanding is a defect. The floor is part of the formula,
      not a presentation-layer clamp.
    rationale: >
      Two things. The credit-applied term was missing from an earlier
      correction attempt, which computed 1000 outstanding on a 1000 charge
      with 200 credit applied rather than 800. And flooring per cycle rather
      than per enrollment is load-bearing: flooring a signed sum would let one
      over-settled cycle silently offset another cycle's genuine debt.
    source: [ADR-002, FR5.9, AC6.3.7]

  - id: BR4.5
    statement: >
      Available credit is non-negative by construction, not by a floor.
    category: calculation
    applies_to: Every enrollment
    trigger: Any credit application
    logic: >
      IF credit is applied against an amount owed
      THEN the applied amount is min(available_credit, amount_owed), so
      total_credit_apply can never exceed total_credit_grant and
      available_credit = total_credit_grant - total_credit_apply >= 0 always.
    violation_behaviour: >
      A negative available credit means an apply outran its grant, which is a
      defect in the application logic rather than a figure to clamp.
    rationale: >
      Outstanding and credit are the two non-negative halves of one signed
      quantity. Guaranteeing the credit half by construction rather than by a
      floor is what makes the identity hold exactly rather than approximately:
      a floor would discard value and break the equality.
    source: [ADR-002, FR5.9, AC6.3.8]

  - id: BR4.6
    statement: >
      Carry-forward is two-sided and nets to zero at the enrollment level.
    category: constraint
    applies_to: Every carry-forward
    trigger: Carrying a debt from one period to a later one
    logic: >
      IF a debt is carried forward
      THEN append BOTH a carried_out entry relieving the originating cycle AND
      a carry_forward entry of the same amount charging the receiving cycle
      AND the invariant sum(carry_forward) == sum(carried_out) holds at the
      enrollment level at all times.
    violation_behaviour: >
      A one-sided carry double-counts the debt: it stands in the originating
      cycle's outstanding AND again in the receiving cycle's carried-in. The
      companion equation detects the imbalance; the property test catches it
      before it ships.
    rationale: >
      The two kinds are equal and cancel at the enrollment level, which is
      what makes carry-forward an internal transfer rather than a new charge,
      and is why neither kind appears in BR4.3. Computed at this stage, with
      a 1000 charge carried into a second 1000 charge: the two-sided model
      reads 2000 owed; a one-sided model reads 3000. With 500 of the first
      1000 paid: two-sided reads 1500, one-sided reads 2000. A multi-period
      carry must be covered by a named test and not only a single carry,
      because a single carry can pass against a model that double-counts.
    source: [ADR-002, FR5.1, team: Corrections]

  - id: BR4.7
    statement: >
      Credit belongs to the enrollment, not to a cycle.
    category: policy
    applies_to: Credit grant and credit apply
    trigger: An overpayment, or a later cycle generating against held credit
    logic: >
      IF an approved payment exceeds what was charged
      THEN append a receipt for the applied part and a credit_grant for the
      excess, the grant held against the enrollment
      AND when a later cycle is settled, the credit counts as received in the
      period whose charge it settles, not in the period it arrived.
    violation_behaviour: >
      Attaching credit to a cycle makes finding an enrollment's available
      credit a search rather than a lookup, and misattributes it in period
      analytics.
    rationale: >
      A credit granted in March does not belong to March; it belongs to the
      enrollment. The period-attribution half matters to the collection-rate
      arithmetic downstream, whose definition is itself still open — this
      rule is what the property test must be extended to cover when it
      settles.
    source: [ADR-002, FR5.9, AC6.3.7, AC6.3.8, AC8.3.4]

  - id: BR4.8
    statement: >
      The identity is verified before it is recorded as satisfied, never
      asserted from reasoning alone.
    category: policy
    applies_to: The ledger identity and any future change to it
    trigger: Stating, changing or extending the identity or the kind set
    logic: >
      IF the identity is stated or changed
      THEN it is verified by worked cases covering every ledger operation AND
      by randomized histories composing those operations in arbitrary order,
      before it is recorded as holding.
    violation_behaviour: >
      An unverified invariant standing behind the money module's branch
      coverage certifies the arithmetic it was meant to check. That is worse
      than no invariant, because it is trusted.
    rationale: >
      This project's identity was wrong twice before randomized testing
      settled it, and a reviewer's prescribed correction was itself wrong on
      four of twelve cases. Verification is the rule that caught both.
    source: [ADR-002, team: Corrections, team: Testing Posture]

  # ---- BR5.x — Serialization across the boundary ----

  - id: BR5.1
    statement: >
      Every money value crosses the API as a JSON string, in both directions,
      always.
    category: constraint
    applies_to: Every money field in every request and response
    trigger: Any serialization or deserialization at the API boundary
    logic: >
      IF a money value crosses the API
      THEN it is a JSON string of the form "1500.00": exactly two decimal
      places, no currency symbol, no thousands separator, no sign for a
      positive value, and Latin digits only — never Bangla numerals on the
      wire.
    violation_behaviour: >
      Emitting a JSON number for a money field is a defect. A float in transit
      is a permanently forbidden representation.
    rationale: >
      A JSON number is a double in most parsers, which reintroduces the
      representation error the whole type exists to exclude — at the one
      boundary where both sides are out of each other's sight.
    source: [NFR9, FR5.7, TC-7, D-20, contract-summary §B.5, project.md NEVER-rule]

  - id: BR5.2
    statement: >
      A JSON number in a money field is rejected loudly on decode.
    category: validation
    applies_to: Deserialization on both surfaces
    trigger: Decoding any money field
    logic: >
      IF a money field arrives as a JSON number rather than a string
      THEN reject the decode with an explicit failure
      ELSE IF it arrives as a string of the canonical form THEN accept it.
    violation_behaviour: >
      Loud failure, never silent coercion. A lenient decoder that quietly
      accepts a number and converts it is the actual failure mode, and it
      passes a happy-path test on both sides, which is why the negative test
      is a named obligation rather than an optional extra.
    rationale: >
      This is the check that catches a backend regression emitting a number
      AND a hand-written client model that forgot its serializer — two
      different defects, one assertion.
    source: [contract-summary §B.5, team: Testing Posture, team: Code Style]

  - id: BR5.3
    statement: >
      There is exactly one serialization chokepoint per boundary, and both
      live in this module.
    category: constraint
    applies_to: The API boundary and the storage boundary
    trigger: Any money value entering or leaving the system
    logic: >
      IF a money value crosses the API boundary
      THEN it passes through the module's single annotated API type
      ELSE IF it crosses the storage boundary
      THEN it passes through the module's single storage type mapping, which
      maps to a fixed-point decimal column of 12 total digits and 2 decimal
      places
      AND no per-field serializer and no per-model column declaration exists.
    violation_behaviour: >
      A per-field serializer or an independently-declared money column is a
      defect caught in review and by the schema diff gate.
    rationale: >
      A per-field serializer is how one endpoint eventually emits a number. An
      independently-declared column is how one model eventually declares too
      few digits or a float. One chokepoint each means a money value
      physically cannot enter or leave the system without passing through this
      module — which is what makes the boundary enforceable rather than
      aspirational.
    source: [contract-summary §E.1, team: Code Style, project.md ALWAYS-rule]

  - id: BR5.4
    statement: >
      Locale-aware formatting lives in this module. The server is the only
      thing deciding digit rendering and separator placement.
    category: policy
    applies_to: Any screen displaying a money value
    trigger: A response carrying a money value a screen will render
    logic: >
      IF a screen needs a formatted amount
      THEN the response carries BOTH the canonical amount string AND a
      separately formatted display string produced by this module's formatting
      operation, and the client renders the display string
      ELSE the client never formats the canonical amount itself.
    violation_behaviour: >
      A client formatting a money value is a layering defect: it is a decision
      about rendering under a Bangla locale taken on the surface that is least
      reviewable and least testable.
    rationale: >
      Digit rendering and separator placement under a Bangla locale are
      genuine decisions. Keeping them server-side keeps them in one testable
      place, and keeps the canonical value and its presentation distinct.
    source: [contract-summary §B.5, TC-15, TC-9, D-43, D-31]

  - id: BR5.5
    statement: >
      A money value is never compared on the client. The server sends a
      decision.
    category: policy
    applies_to: Every money-carrying response
    trigger: A screen needing to show a status derived from an amount
    logic: >
      IF a screen shows a status that depends on an amount
      THEN the response carries the server-computed status alongside the
      amount and the client switches on it
      ELSE the client would be computing a business rule.
    violation_behaviour: >
      A client-side comparison of a money value is a business rule rendered as
      if it were presentation, and is nearly invisible in review because it
      looks like UI code.
    rationale: >
      Stated here rather than only in the layering practice because this
      module's existence is what makes it enforceable: the client is handed a
      status and a display string, so it has nothing to compare with.
    source: [TC-9, D-31, contract-summary §B.5, project.md NEVER-rule]

  - id: BR5.6
    statement: >
      The formatting operation receives its locale as an explicit argument and
      never reads it from configuration, request context, environment or a
      process-wide default.
    category: constraint
    applies_to: The locale formatting operation
    trigger: Formatting a money value for display
    logic: >
      IF a money value is formatted
      THEN the locale is passed in by the caller
      ELSE the module would depend on application configuration.
    violation_behaviour: >
      A settings import inside the module, caught by the import-boundary check
      of BR6.1 and BR6.2.
    rationale: >
      This is the one operation that could plausibly acquire a settings
      dependency, and three of the Unit's load-bearing claims rest on it not
      doing so: no settings import, 100% branch coverage, and buildable and
      fully testable before any endpoint exists. A configuration-read locale
      would break all three at once - the module would need settings to
      construct, and its formatting branches would be reachable only by
      mutating global state in a test. Digit-shaping data comes from the
      language runtime's locale facilities or a pinned data table declared as
      an ordinary dependency, never from application configuration or a
      service lookup. The supported locale set is finite and known, so every
      branch is reachable by passing a value.
    source: [B1 DoD, BR6.1, TC-15, D-43]

  - id: BR5.7
    statement: >
      A negative money value cannot cross the API boundary; serializing one is
      refused.
    category: validation
    applies_to: The API serialization chokepoint
    trigger: Serializing a money value
    logic: >
      IF the value is negative
      THEN refuse and raise a validation failure
      ELSE render it in the canonical sign-free form.
    violation_behaviour: ValidationError at the point of emission.
    rationale: >
      The canonical wire pattern admits no sign, so there is no representation
      to emit. Every money quantity that legitimately crosses the API is one
      the sign rules already forbid to be negative - a ledger entry amount, an
      outstanding total, an available credit, a charged or approved amount -
      so a negative value reaching serialization means a sign rule was
      violated upstream or a floor was missed. Refusing here makes that a loud
      failure at emission rather than a string the client cannot parse against
      the contract's own pattern, or a silently dropped sign that displays a
      debt as a credit.
    source: [contract-summary §B.5 money pattern, BR2.7, BR4.4, BR4.5]

  # ---- BR6.x — The import boundary ----

  - id: BR6.1
    statement: >
      This module imports nothing from the API, persistence, repository,
      authorization or schema layers.
    category: constraint
    applies_to: The money module's imports
    trigger: Every build and every test run, from the first commit
    logic: >
      IF the money module imports from any of those layers
      THEN the build fails.
    violation_behaviour: >
      Fails the layered-import check. Not a review finding — a build failure.
    rationale: >
      This is the check that catches the PLAUSIBLE violation, which is not
      arithmetic in a view but somebody giving this module a database session
      "just to look up a batch's default fee". That single change destroys the
      testability story and the strict-typing story at once, and it is the
      reason the module is buildable and fully testable before any endpoint
      exists.
    source: [team: Code Style, contract-summary §E.1, project.md ALWAYS-rule]

  - id: BR6.2
    statement: >
      Raw fixed-point decimal arithmetic is confined to this module.
    category: constraint
    applies_to: The whole backend
    trigger: Every build, from the first commit
    logic: >
      IF code outside this module imports the raw decimal facility
      THEN the build fails, with the module itself re-permitted by an explicit
      exception.
    violation_behaviour: Build failure.
    rationale: >
      This is the load-bearing half of the boundary. Money arithmetic outside
      the module needs either a raw decimal or a float, and both are then
      blocked — so the ban on the one closes the door on the other.
    source: [team: Code Style, project.md ALWAYS-rule, contract-summary §E.1]

  - id: BR6.3
    statement: >
      Both boundary mechanisms are present from the first commit, not added
      after a violation.
    category: policy
    applies_to: The two checks in BR6.1 and BR6.2
    trigger: The first commit of this Unit
    logic: >
      IF this Unit is delivered
      THEN both the import-direction check and the layered-import test are
      present and demonstrably failing on a deliberate violation.
    violation_behaviour: >
      Delivering the module without both checks does not satisfy this Unit's
      definition of done.
    rationale: >
      The conditional framing inverts the economics. The checks cost roughly
      fifteen lines of configuration now, against the same fifteen lines later
      PLUS unwinding however much arithmetic leaked in between — and with the
      fee model already in revision, the leak would be inside code about to be
      rewritten. A gate nobody has seen fail is a gate nobody knows works.
    source: [team: Code Style, bolt-plan B1 DoD, project.md ALWAYS-rule]

  - id: BR6.4
    statement: >
      On the client surface, the money type is a decimal-backed value type and
      floating-point types are banned package-wide in the shared model package.
    category: constraint
    applies_to: The client's shared model package
    trigger: Every client build
    logic: >
      IF a money-carrying model declares a floating-point field
      THEN the build fails — by the compiler where a money type is expected,
      and by the package-wide static-analysis ban as a backstop.
    violation_behaviour: Build failure on both mechanisms.
    rationale: >
      The compiler does the real work: a floating-point value cannot be
      assigned where the money type is expected, with no custom rule needed.
      The package-scoped ban then degrades to a trivial backstop rather than
      requiring a tool to judge which fields "carry money" — which is exactly
      the judgement an unfamiliar reviewer cannot make.
    source: [team: Code Style, contract-summary §E.1, project.md NEVER-rule]
```

---

## Part B — Rules summary

| ID | Category | Statement | Source |
|---|---|---|---|
| **BR1.1** | validation | Construction from a float is refused | project NEVER, NFR9, FR5.7 |
| **BR1.2** | constraint | Decimal-from-float construction is forbidden module-wide | team: Code Style |
| **BR1.3** | calculation | Quantized to exactly 2dp at construction | team: Code Style, NFR9 |
| **BR1.4** | policy | BDT implicit; no currency attribute or field | NFR9, §B.5 |
| **BR1.5** | constraint | Immutable; every operation returns a new value | team: Code Style |
| **BR1.6** | constraint | No float or integer conversion is defined | §E.1, project NEVER |
| **BR1.7** | validation | Magnitude beyond ten integer digits is refused | §B.5 storage contract |
| **BR1.8** | policy | One error class only: a validation failure, on every path | team: Error handling, Q7 |
| **BR2.1** | validation | Add and subtract accept only Money | team: Code Style |
| **BR2.2** | calculation | Multiplication is a named operation stating its rounding | team: Code Style |
| **BR2.3** | calculation | No division; allocation sums exactly to the original | team: Code Style |
| **BR2.4** | constraint | Zero constant exists; comparing to a number is a type error | team: Code Style |
| **BR2.5** | calculation | Summation with a zero identity exists on the type | team: Code Style, FR7.2 |
| **BR2.6** | calculation | Sign predicates live on the type | team: Code Style |
| **BR2.7** | policy | Negatives permitted by type, forbidden per context | ADR-002, FR5.9 |
| **BR2.8** | validation | Allocation into fewer than one part is refused | team: Code Style |
| **BR2.9** | calculation | Negative allocation splits magnitude, restores sign | BR2.3, BR2.7 |
| **BR2.10** | validation | Rate is exact and non-negative; zero and >1 allowed | BR1.1, BR2.7, BR4.1 |
| **BR3.1** | policy | Half-up rounding, declared once — not banker's rounding | team: Code Style |
| **BR3.2** | constraint | No rounding happens anonymously | team: Code Style |
| **BR4.1** | validation | Entry amounts are non-negative; sign lives in the kind | ADR-002, FR5.1 |
| **BR4.2** | calculation | Every derived quantity is a fold; none is stored | ADR-002, FR5.1 |
| **BR4.3** | calculation | **The ledger identity, verified form** | ADR-002, FR5.1, FR5.9 |
| **BR4.4** | calculation | Per-cycle outstanding never negative; total sums floored figures | ADR-002, FR5.9 |
| **BR4.5** | calculation | Available credit non-negative **by construction** | ADR-002, FR5.9 |
| **BR4.6** | constraint | Carry-forward is two-sided and nets to zero | ADR-002, FR5.1 |
| **BR4.7** | policy | Credit belongs to the enrollment, not a cycle | ADR-002, FR5.9, AC8.3.4 |
| **BR4.8** | policy | The identity is verified, never asserted | ADR-002, team: Corrections |
| **BR5.1** | constraint | Money crosses the API as a JSON string, always | NFR9, FR5.7, §B.5 |
| **BR5.2** | validation | A JSON number is rejected loudly on decode | §B.5, team: Testing Posture |
| **BR5.3** | constraint | Exactly one chokepoint per boundary, both in this module | §E.1, project ALWAYS |
| **BR5.4** | policy | Locale formatting is the server's job | §B.5, TC-15, TC-9 |
| **BR5.5** | policy | The client never compares a money value | TC-9, D-31, §B.5 |
| **BR5.6** | constraint | Locale is an argument, never configuration | B1 DoD, BR6.1 |
| **BR5.7** | validation | A negative value cannot cross the API boundary | §B.5 pattern, BR4.4 |
| **BR6.1** | constraint | No imports from API, persistence, repository, authz or schema | team: Code Style |
| **BR6.2** | constraint | Raw decimal arithmetic confined to this module | project ALWAYS |
| **BR6.3** | policy | Both boundary checks present from the first commit | team, B1 DoD |
| **BR6.4** | constraint | Client: decimal-backed value type, floats banned package-wide | team, §E.1 |
