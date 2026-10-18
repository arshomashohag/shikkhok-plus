## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T06:58:07Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | app/money/_ledger.py > derive, per_cycle comprehension | The per-cycle floor silently discards relief, so outstanding overstates the debt whenever relief lands on a cycle already at zero. See note A | Attribute relief at enrollment level, or carry the discarded surplus into a term the identity and the per-cycle floor share | Resolved (reviewer) |
| R-02 | Critical | tests/money/test_ledger_property.py > well_formed_history | The generator cannot reach the histories where note A's defect occurs, so the identity test certifies a subset the system exceeds. See note B | Extend the generator to emit late relief against a relieved cycle, over-relief, and unpaired carries, or state the reachable-history contract and enforce it in the fold | Resolved (reviewer) |
| R-03 | Major | app/money/_ledger.py > carry_forward, apply_credit | `carry_forward` accepts any amount with no relation to what the origin period owes, so an over-carry manufactures debt. See note C | Compute the carried amount inside the module from the origin's derived balance, as `apply_credit` already does for credit | Resolved (reviewer) |
| R-04 | Major | tests/gates/test_import_gates.py > TestGate2Inward, pyproject.toml banned-api | Gate 2 is defeated by `importlib.import_module("decimal")`; Gate 1 misses the same bypass and any deferred in-function import. See note D | Add a dynamic-import check to the AST gate on both directions, and a fixture proving it fires | Resolved (reviewer) |
| R-05 | Minor | app/money/_money.py > apply_rate | A negative-zero rate is accepted and yields `-0.00`, which `is_negative()` reports False but `to_wire` emits as `-0.00`-adjacent state. See note E | Normalise the rate sign check to compare the value, not `is_signed()`, so `Decimal('-0')` is treated as zero | Resolved (reviewer) |
| R-06 | Minor | app/money/_money.py > allocate | `allocate` on a negative amount relies on `to_integral_value` with the ambient context rounding rather than the module's declared mode. See note F | Use the already-quantized `amount` directly rather than re-deriving paisa through a context-sensitive conversion | Resolved (reviewer) |
| R-07 | Critical | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/functional-design/rules.md > BR4.4 | BR4.4 mandates the sum of floored per-cycle figures and forbids flooring a signed sum; `derive` now does exactly what the rule forbids. See note A | Decide which is right, then make the other follow: revise BR4.4 with its rationale, or revert the total to the rule | New |
| R-08 | Critical | app/money/_ledger.py > derive, outstanding | Surplus relief in one period now offsets another period's genuine debt at enrollment level, the outcome BR4.4's rationale names. See note B | Separate surplus relief into its own non-negative term rather than letting it net against unrelated periods | New |
| R-09 | Major | tests/money/test_ledger.py > test_over_relieved_cycle, test_per_cycle_floors_are_kept_for_display | Two new tests assert the behaviour BR4.4 forbids, so the suite now pins the implementation against its own governing rule. See note C | Re-derive both expected values from whichever rule survives note A, and name the rule in each docstring | New |
| R-10 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/code-generation/code-summary.md > section D, items 1 and 3 | Section D describes the superseded per-cycle-floor behaviour; item 3's stated conclusion is now false against the code. See note F | Rewrite items 1 and 3 against the current fold, or record the change as a fifth finding in that section | New |
| R-11 | Minor | tests/money/test_ledger_property.py > well_formed_history | Every relief is capped at `total_outstanding`, so no generated history ever carries per-period surplus. See note D | Draw at least some relief against a period's own balance rather than the enrollment's, so the surplus shape is generated | New |

> R-01 Reviewer note: All three reproductions now behave as claimed. See note A for the rule conflict the fix created.

> R-02 Reviewer note: Generator reaches the previously unreachable shapes; the defect-restoration check is the right evidence. See note D.

> R-03 Reviewer note: Over-carry now raises when `origin_balance` is supplied; the optional default is acceptable here, see note E.

> R-04 Reviewer note: Literal dynamic targets resolve into the import set, computed targets are flagged, fixture fires. Verified.

> R-05 Reviewer note: Normalisation at construction. `-5.00` and `-0.001` both behave correctly; no legitimate value is altered.

> R-06 Reviewer note: `to_integral_value(rounding=ROUNDING)` removes the ambient-context dependency.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| pytest tests -q | 222 passed | Suite is green; it does not test the note A conflict |
| derive() probe, eight spec scenarios S1-S8 | All match spec values; identity balances | Note G: the fix breaks none of the eight |
| derive() probe, iteration-1 reproductions | 0.00 / 1600.00 / identity-unbalanced | Two fixed; the third is unproducible as claimed |
| derive() probe, over-waived cycle | total 0.00, per_cycle Apr 1000.00 | Confirms the note B offset |
| derive() probe, bare carry pair | total 0.00, per_cycle Apr 1000.00 | Confirms note F item 3 is now false |
| Money probe, apply_rate(Decimal('-0')) | 0.00, is_negative False | R-05 closed, no legitimate value changed |

### Summary

The six prior findings are all genuinely fixed and the eight worked scenarios still hold, but the R-01 fix was applied to the code without being applied to the rule that governs it: `rules.md` BR4.4 states in normative terms the exact arithmetic the fix replaced, and gives as its rationale the exact outcome the fix now produces.

**Note A — the fix contradicts BR4.4, which was never revised.** BR4.4's `logic` reads: the enrollment total "is the sum of those floored per-cycle figures, **never a floor applied to a signed sum**." Its `rationale` reads: "flooring per cycle rather than per enrollment is load-bearing: flooring a signed sum would let one over-settled cycle silently offset another cycle's genuine debt." `derive` now computes `_floor(Money.sum(cycle_charged.values()) - Money.sum(cycle_relieved.values()))`, which is a floor applied to a signed sum. The code comment at `_ledger.py:149-163` argues the case for the change and is a good argument, but it argues it in a source comment against a passed upstream contract that still says the opposite, and `code-generation-plan.md` records no departure. A developer reading `rules.md` and a developer reading `_ledger.py` now implement different arithmetic for the single most consequential number in the system. This is the finding; I am not asserting the rule is right and the code wrong. One of them has to move, deliberately and in writing.

**Note B — the offset BR4.4 warned about is real and now occurs.** `charge Mar 1000, receipt Mar 1000, forgiveness Mar 1000, charge Apr 1000` gives `total_outstanding` 0.00 with `per_cycle` `{Mar: 0.00, Apr: 1000.00}`. April's charge is genuine and unrelieved; March's surplus 1000 is a phantom created by relieving a period twice. A teacher looking at the enrollment sees nothing owed while the April row shows 1000 owed. Note that this is precisely the first of iteration 1's three reproductions, which the author reports as fixed — and it is fixed in the sense that the identity now balances, but the identity balancing is not the same as the number being right. The identity is satisfied here because the phantom surplus is counted on both sides. Whether this history is producible depends on U8's approval-reversal path, which does not exist yet; what is not in doubt is that if it is produced, the enrollment total understates the debt by 1000. A weaker form is unambiguously producible today and arithmetically correct: `charge Mar 1000, receipt Mar 1500, charge Apr 1000` gives total 500.00 against `sum(per_cycle)` 1000.00. 500 is right at enrollment level, and the two numbers disagreeing by design is defensible — but it is a decision that belongs in BR4.4, not only in a comment.

**Note C — the suite now pins the implementation against the rule.** `test_over_relieved_cycle`'s docstring says "surplus relieves the enrollment, not nothing" and asserts `total_outstanding == 0.00` on note B's history. `test_per_cycle_floors_are_kept_for_display` asserts total 500.00 against per-cycle sum 1000.00. Both are correct against the new code and both are refutations of BR4.4 as written. `team.md` records that a reviewer's prescribed fix is verified separately from the finding that prompted it; the same applies here one level up — the fix is verified, the rule it departs from is not.

**Note D — R-02 is genuinely closed, with one residual narrowing.** The rewrite is sound and the decisive evidence is the right evidence: restoring `outstanding = Money.sum(per_cycle.values())` makes the new suite fail where the old one passed 2000 examples. On the question of whether calling `derive()` inside the generator reintroduces R-02: it does not. R-02 was that the generator pre-enforced the invariants under test, so the assertions could not fail. Here `derive` is used only to pick admissible *inputs* — how much a teacher could plausibly pay — while every assertion (`_identity_holds`, the floors, carry pairing, `credit_apply <= credit_grant`) is computed from `EXPECTED_EFFECT` and the hand-written identity, independent of the fold. A generator that uses the implementation to stay inside the domain is a different thing from a generator that uses it to decide what the answer is. The residual narrowing is that every relief is capped at `total_outstanding` (the enrollment balance), so no generated history ever has a period relieved beyond its own charges — the note B shape is still outside the generated domain. That is why it is Minor rather than a reopening: drawing some relief against `per_cycle[target]` instead would reach it.

**Note E — `origin_balance` being optional is acceptable.** A caller omitting it gets the unchecked path, but this Unit has no callers, U7 owns them, and both the named test and the property generator pass it. The stronger shape would be to require it or compute it from a passed history, and that is worth doing when U7 lands; it is not a defect in U1 today.

**Note F — the stage artifact now describes behaviour that changed.** `code-summary.md` section D item 1 explains the Hypothesis counterexample as "the per-cycle floor working correctly: the floor discards an unmatched relief", which was the behaviour the fix removed at enrollment level. Item 3 states that a bare carry pair "does not" total zero, "the origin period floors at zero while the receiver is charged". I ran it: a bare `carried_out Mar 1000 / carry_forward Apr 1000` now gives `total_outstanding` 0.00. The stated conclusion is false against the current code, and it is the kind of false that a later reader trusts for having been written down as a finding.

**Note G — the eight spec scenarios are unaffected.** I recomputed S1-S8 against the current fold. Every outstanding, every available-credit figure and every per-cycle figure matches `functional-spec.md` §3 exactly, and the identity balances in all eight. No scenario's computed value in the spec disagrees with what the code produces. The eight are all histories where no period is relieved beyond its own charges, which is why the change is invisible to them — and also why they could not have caught either the original defect or this one.
