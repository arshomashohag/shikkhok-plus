# Unit Test Instructions — `money-core` (U1)

**Stage**: code-generation (3.5)
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> This is the other half of what gets approved. The plan says what code
> exists; this says what proves it correct. For a module carrying 100% branch
> coverage and the product's whole financial surface, the tests are the
> deliverable at least as much as the code.

## Cadence

`team.md` sets a predicate rather than a list: **write the failing test first
whenever the correct output is knowable from the requirement without having
written the code, and a wrong answer would be a money error or an
authorization error.**

That predicate holds for **every test below**. The expected values all come
from `functional-spec.md`, computed at design time — so each test is a
specification that can be written correctly before any implementation exists.
Nothing here is written against an implementation.

---

## A. Named tests by area

### A.1 Construction and representation

| Test | Asserts | Rule |
|---|---|---|
| `test_float_construction_refused` | A float raises, by **type** not value | BR1.1 |
| `test_integral_float_also_refused` | `1000.0` is refused identically to `0.1` — the check is not value-dependent | BR1.1 |
| `test_string_and_int_accepted` | Exact decimal parse; integer is whole Taka | BR1.2 |
| `test_quantized_at_construction` | Three-decimal input quantizes to 2dp immediately | BR1.3 |
| `test_equal_values_hash_equally` | Quantization makes equality and hashing consistent | BR1.3, BR1.5 |
| `test_overflow_refused` | Eleven integer digits raises; ten is accepted | BR1.7 |
| `test_immutable` | No mutating operation exists on the surface | BR1.5 |
| `test_no_float_or_int_conversion` | `float(m)` and `int(m)` raise `TypeError` | BR1.6 |

### A.2 Arithmetic

| Test | Asserts | Rule |
|---|---|---|
| `test_add_subtract_money_only` | `Money + 5` is a type error | BR2.1 |
| `test_subtract_can_go_negative` | Permitted inside the module | BR2.7 |
| `test_apply_rate_rounds_half_up` | `333.33 × 0.5 = 166.665 → 166.67`, **not** `166.66` | BR3.1 |
| `test_apply_rate_refuses_float` | A float rate raises | BR2.10 |
| `test_apply_rate_refuses_negative` | A negative rate raises | BR2.10 |
| `test_apply_rate_permits_zero_and_above_one` | Both succeed — a late fee is a rate above one | BR2.10 |
| `test_allocate_exact_sum` | All four positive table rows from §2.5 | BR2.3 |
| `test_allocate_negative_magnitude_then_sign` | `−0.05 / 3 → −0.02, −0.02, −0.01`, summing exactly | **BR2.9** |
| `test_allocate_refuses_below_one` | `n = 0` and `n = −1` raise; never an empty list | BR2.8 |
| `test_sum_empty_is_zero` | Zero identity, not a failure | BR2.5 |
| `test_comparison_type_safe` | Comparing to `int` is a type error | BR2.6 |

> **`test_allocate_negative_magnitude_then_sign` is the one to not get wrong.**
> Both plausible implementations sum to exactly −0.05, so an exact-sum
> assertion alone passes against either. The test must assert the **specific
> parts**, in order.

### A.3 The ledger fold

| Test | Asserts | Rule |
|---|---|---|
| `test_negative_entry_amount_refused` | Sign belongs to the kind | BR4.1 |
| `test_unknown_kind_refused` | No default, no silent exclusion | NFR9.19 |
| `test_scenario_s1` … `test_scenario_s8` | **All eight worked scenarios** from §3, each with its computed derived quantities **and** the identity | BR4.3 |
| `test_credit_apply_is_min` | 1500 available against 1000 owed applies 1000, retains 500 — succeeds, never refuses | BR4.5 |
| `test_carry_forward_is_paired` | One operation produces both entries; no one-sided path exists | BR4.6 |
| `test_multi_period_carry` | **Three periods**: reads 3000, not 4000 | BR4.6 |
| `test_credit_attributed_to_settling_period` | A credit counts as received in the period whose charge it settles | BR4.7 |

> **`test_multi_period_carry` must be multi-period.** A single carry passes
> against a model that double-counts, because the error is still small enough
> to look plausible. The divergence only shows from the second carry on.

### A.4 Boundary cases (§5)

- **Rounding at the half**: all five sampled values from §5.2, each asserted
  against half-up — three of the five differ from banker's rounding, which is
  the point.
- **Zero**: zero charge legal; empty sum is zero; `allocate(0, n)` returns *n*
  zeros; any rate on zero is zero.
- **Negative**: permitted as a subtraction result; refused as an entry amount,
  an outstanding, an available credit.
- **Approved exceeding claimed**: charge 1000, claim 600, approve 1200
  produces exactly S6's entries.
- **Shortfall measured against charged, not claimed**: charge 1000, claim 900,
  approve 700 → shortfall **300**, not 200.

### A.5 Chokepoints

| Test | Asserts |
|---|---|
| `test_api_emits_canonical_string` | Two decimals, no separator, Latin digits, never a JSON number |
| `test_api_rejects_json_number` | Loud failure, no coercion |
| `test_api_refuses_negative` | No canonical representation exists for it |
| `test_storage_roundtrip` | Value survives the column mapping unchanged |

### A.6 Kotlin

| Test | Asserts |
|---|---|
| `MoneySerializerTest.decodes_json_string` | A string decodes to the value class |
| `MoneySerializerTest.fails_loudly_on_json_number` | **A JSON number throws** — the lenient-decoder case |

### A.7 Gates

| Test | Asserts |
|---|---|
| `test_gate1_fixture_fails` | The outward-import fixture is refused |
| `test_gate2_fixture_fails` | The decimal-import fixture is refused |
| `test_gate1_config_resolves` | The walked path is a real non-empty package |
| `test_gate2_config_scope` | The exception resolves to exactly the money module path, not a parent |

---

## B. The property test

**The specification, not a supplement.** This project's ledger identity was
wrong twice while satisfying its own worked examples.

```
total_charged − total_forgiven − (total_receipt + total_credit_grant)
    == total_outstanding − available_credit
```
with `available_credit >= 0`, `total_outstanding >= 0`,
`sum(carry_forward) == sum(carried_out)`.

Requirements on the test itself:

1. **Generators derive their kind set from the enumeration** [NFR9.20], so a
   kind added later appears in histories automatically.
2. **A hand-written expected effect per kind** [NFR9.25] — one worked case per
   kind asserting its effect on outstanding and available credit, **not read
   from the shared `identity_side` field the fold reads**. Without this, test
   and implementation agree by construction and a mis-sided kind passes.
3. Histories compose charge, receipt, under- and over-payment, waiver,
   single and multi-period carry, credit grant and credit apply, in arbitrary
   order, across one to six periods.

---

## C. Coverage

- **100% branch on `app/money/**`**, build-gated, **no exclusion pragmas**.
- The one sanctioned exception is the exhaustiveness assertion, written to
  **emit no coverable branch** (`assert_never` under a statically-proven
  total mapping) rather than excluded by comment.
- Scoped **by behaviour**: any module importing the money type and branching
  over money values is inside the obligation [NFR9.31a/b].

---

## D. The named-test manifest

Every test above appears in a committed manifest with **its acceptance
criterion**, e.g.:

```
test_multi_period_carry: a three-period carry reads 3000, not 4000
```

A CI check asserts every entry resolves to a test that exists and runs. The
criterion makes a trivially-asserting test visible to a reader as a mismatch —
no mechanism can detect that automatically.

---

## E. Not tested here

- **`format(locale)`** — not built, per the plan. No locale tests, no
  completeness check.
- **The two schema assertions** — authored as helpers against synthetic
  inputs is *not* in this plan either; they execute from B2 and B3, whose DoDs
  are amended to own them.
