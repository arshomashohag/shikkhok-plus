# Reliability Design — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 cannot corrupt data, so its reliability design is entirely about
> producing the right number** — and the defining property of a wrong number
> here is that **it balances**. A double-counted credit, a month grouped by
> the wrong column, a sum over the wrong kinds: each yields a figure that is
> internally consistent, passes every structural gate, and is simply false.
>
> Nothing mechanical catches that. **Three named tests do** [§ 1], and this
> document is mostly about making each one unable to pass against its defect.

## Sources

- [upstream] `nfr-requirements/reliability-requirements.md` — NFR19.48–
  NFR19.57
- [upstream] `functional-design/rules.md` — BR1.4, BR1.5, BR2.1, BR2.2,
  BR2.3, BR2.6, BR3.4, BR4.3
- [upstream] this stage's `performance-design.md` § 3 — why the fold is in
  Python
- [code] read 2026-10-25: `app/money/_ledger.py`, `app/money/_kinds.py`,
  `app/db/models.py:925-940`, `app/errors/_classes.py`

---

## 1. The three wrong numbers, and the test that each cannot pass

### 1.1 The double-counted credit [NFR19.50, BR2.1]

Cash in is `receipt + credit_grant`. Counting `credit_apply` adds the credit
twice — once on arrival, once on use.

**Design: the test asserts 2000 and specifically not 2500**, over the two
months `rules.md` BR2.1 computes. **The assertion that fails against the
defect is the total**, not month 1: month 1 is 1500 under both the correct
implementation and the defect, so a test that stops there passes.

**A second assertion covers a different defect, and computing it corrected
this design's first draft.** `amount` is non-negative with the sign in the
kind [`app/db/models.py:936-937`], so a `SUM(amount)` over a period adds
charges to receipts. The draft said the 2000/2500 case could not reach that
defect. **Run over BR2.1's own entries, it can:**

| | `charge` | `receipt` | `credit_grant` | `credit_apply` | cash in | `SUM(all)` |
|---|---|---|---|---|---|---|
| M1 | 1000 | 1000 | 500 | — | **1500** | 2500 |
| M2 | 1000 | 500 | — | 500 | **500** | 2000 |
| | | | | | **2000** | **4500** |

The total under charge-summing is 4500 against a correct 2000, so the
existing total assertion already fails against it.

**What the per-month column shows is why the assertion must be on the
total**, and the direction matters — a second draft of this paragraph had it
backwards. Month 1 alone:

| M1 earnings under | Figure |
|---|---|
| the correct fold | **1500** |
| charge-summing | 2500 — **caught** by any assertion pinning 1500 |
| counting `credit_apply` | **1500** — M1 has no apply, so the defect is invisible here |

**A per-month assertion on M1 catches charge-summing and misses the
double-count entirely**, because the defect this unit's central rule exists
to prevent leaves month 1 untouched. The total is where the two months
differ, which is the whole reason BR2.1's case spans two.

**The second assertion is therefore kept for coverage, not for a
coincidence**: a month whose charge and receipt **differ** separates
charge-summing from the correct fold without relying on the total, so the two
defects have independent failing assertions rather than one shared one.

### 1.2 The month grouped by the wrong column [NFR19.49, BR2.6]

**Design: the fixture is a late-recorded payment** — an entry whose `period`
is `2026-10` and whose `created_at` falls in November — asserted to count in
October.

**This is the likeliest wrong number in the unit**, because late recording is
the normal case: a teacher verifies October's cash in early November. Grouping
by `created_at` understates October, overstates November, and produces a trend
with a dip and a spike that never happened.

**A second fixture the requirement implies and the design states**: a
`carry_forward` entry, which lands on the **receiving** period
[`app/db/models.py:927-934`]. Its `created_at` is whenever generation ran, so
`created_at`-grouping scatters carries into arbitrary months. The carry case
fails against the defect even when no payment is late.

### 1.3 A failure reported as zero [NFR19.51]

Zero is reserved for "nothing was received" [BR2.2]. **Design: no read path
returns a default on failure.** The specific shape to avoid is
`per_period.get(period, Money.ZERO)` at the response boundary — correct
*inside* the fold, where absence genuinely means zero, and wrong at the edge,
where absence can mean the read failed.

**Verifier: a test injecting a read failure and asserting the response is an
error.** A test asserting "the figure is zero when there is no data" passes
against both.

---

## 2. Four kinds of nothing, none collapsible

| Case | Response | Rule |
|---|---|---|
| Nobody owes | empty collection, 200 | BR1.5 |
| Nothing received | **zero as a value**, 200 | BR2.2 |
| Under two months of history | trend **absent**, 200 | BR2.3 |
| No upcoming exam | next exam **absent**, 200 | BR3.4 |

**Design statement: absent and zero are different wire shapes.** The trend is
absent — the field is not present — while earnings is `"0.00"`. Encoding
either as the other is the defect: an absent earnings block tells a teacher
their records are missing when they are complete; a zero-point trend implies
a direction from one observation.

**Verifier: a test per row, asserting the status AND the shape.** "Not a 200"
passes against all three wrong answers; "a 200" passes against the wrong
shape.

---

## 3. Errors, inherited unchanged

**Design: no new exception class, no new error code** [NFR19.54]. The only
refusal in this unit is the shared `NOT_AVAILABLE` `AuthorizationError` for a
non-teacher lens. There is no state-based refusal because D5 refuses no
write, and no conflict because it writes nothing.

**Retryability stays a property of the class, read in one place**
[NFR19.55]. No raise site in this unit sets it.

---

## 4. What cannot go wrong, and the test that keeps it so

**D5 performs no write** [NFR19.57]. The design obligation is not to be
careful about writes — it is to **assert their absence** with a test
comparing table state across the unit's reads, which fails on a write added
later by someone who has not read this document.

Inapplicable here, named so their absence is not read as oversight: partial
write rollback, forward-only migration, job self-healing, heartbeat
stamping, replay returning the original result, state-based refusals.

---

## 5. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Cash in excludes `credit_apply` [NFR19.50] | The 2000-not-2500 total, **plus** a charges-excluded assertion | yes |
| Month from `period` [NFR19.49] | A late-recorded payment **and** a carry-forward fixture | yes |
| Money arithmetic stays in `app/money/` [NFR19.48] | The built import-boundary checks | yes |
| A failure is not a zero [NFR19.51] | An injected read failure | yes |
| Four kinds of nothing [NFR19.52, NFR19.53] | A test per row, status and shape | yes |
| No new error class [NFR19.54] | The built error-contract test | yes |
| One snapshot per read [NFR19.56] | The concurrent-write test of scalability § 1 | yes |
| No write at all [NFR19.57] | A table-state comparison across the reads | yes |

---

## Assumptions & Open Questions

- **NFR19.51's failure mode has no known trigger in this product.** No
  upstream artifact describes how a ledger read fails. The requirement exists
  so the obvious `.get(period, ZERO)` at the response boundary is a named
  defect rather than a reasonable-looking line.
- **§ 1.1's justification was wrong twice before it was right, and both
  errors were found by computing rather than reasoning.** Draft one claimed
  the 2000/2500 case could not reach charge-summing; the total catches it
  (4500 against 2000). Draft two then claimed a per-month assertion would
  *pass* against charge-summing; it fails, correctly — M1 under charge-summing
  is 2500 and any assertion pinning 1500 catches it. **The real hazard is the
  reverse and is now stated: M1 under the credit-apply defect is 1500,
  identical to correct**, because M1 contains no apply. A per-month test
  therefore misses the defect BR2.1 exists to prevent. Each correction came
  from running the sums; neither came from re-reading the prose.
- **§ 1.2's carry-forward fixture is likewise this design's addition**, from
  reading the `period` docstring rather than the requirement.
- **No figure here was measured.** D5's code does not exist yet.
