## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T01:59:34Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/money-core/functional-design/rules.md > the 32 rules, all groups | Q7 decided this Unit raises `ValidationError` for bad input and `ConflictError` for a state-forbidden operation, but neither class name appears in any of the four outputs. Every refusal rule says only "refuse and raise". See note A. | Add a rule naming the two classes and assigning each refusal in BR1.1, BR4.1, BR4.5 and BR5.2 to one of them, so U2's handler finds them already raised correctly. | New |
| R-02 | Critical | construction/money-core/functional-design/functional-spec.md > 2.5 Allocate into n parts | `allocate` is specified only as "divide, distribute the remainder across the leading parts", which is ambiguous for a negative amount, which BR2.7 explicitly permits. See note B for the divergent outputs. | State that `allocate` refuses a negative amount, or define the division and remainder sign convention explicitly and add a negative worked example. | New |
| R-03 | Major | construction/money-core/functional-design/functional-spec.md > 3, S5 "A correction to the upstream illustration" | The spec says ADR-002 and B1's hypothesis state "2500 instead of 1500". Both actually state 3000 against 2000, which is the spec's own computed answer. The stale 2500/1500 figure is in team.md and domain-design/memory.md. See note C. | Correct the attribution to name team.md's Corrections entry, not ADR-002 and the bolt plan, and route the team.md fix to the learnings gate. | New |
| R-04 | Major | construction/money-core/functional-design/functional-spec.md > 2.8 Format for a locale, and rules.md BR5.4 | `format(locale)` requires locale data and Bangla digit rendering, which is configuration or a library this Unit's own "no settings, no I/O" claim does not account for. Left unstated, the B1 100%-branch-coverage and buildable-before-any-endpoint claims are at risk. | State what `format` may depend on and that the dependency carries no I/O and no settings read, or move formatting out of B1's coverage obligation. | New |
| R-05 | Major | construction/money-core/functional-design/functional-spec.md > 2.5 step 1, and 5.3 Zero | A part count below one has no stated behaviour. Step 1 says "receive a part count of one or more" without saying what happens otherwise, and 5.3 covers a zero amount but not a zero or negative `n`. | State that a part count below one is refused, and name which error class it raises. | New |
| R-06 | Major | construction/money-core/functional-design/functional-spec.md > 2.4 Apply a rate | The rate's domain is unbounded: a negative rate, a rate above one and a zero rate are all unspecified, and a negative rate silently produces a negative Money that BR2.7 then permits. | State the permitted rate domain and the behaviour outside it, including whether a negative rate is refused. | New |
| R-07 | Minor | construction/money-core/functional-design/functional-spec.md > 2.1 step 5 | The ten-integer-digit overflow refusal has no BR behind it and no error class, so the one construction rule with a numeric threshold is the one a reader cannot trace. | Give the magnitude bound its own rule, or fold it into the construction rule and name the raised class. | New |
| R-08 | Minor | construction/money-core/functional-design/functional-spec.md > 2.9 Serialize, and 5.4 Negative | The canonical wire form is defined as "no sign for a positive value", which leaves the negative wire form undefined although BR2.7 permits a negative Money to exist. | State whether a negative money value may cross the API, and if so its canonical string form. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| grep for ValidationError/ConflictError across the four outputs | No match in any output | Confirms the Critical finding on the error classes |
| allocate recomputation, the four tabled cases | All four reproduce exactly, sums exact | The non-negative allocation table is correct |
| allocate on a negative amount, two division conventions | Divergent splits, both exact-sum | Confirms the Critical finding on allocate |
| ADR-002 and bolt-plan B1 text against the S5 claim | Both read 3000/2000, not 2500/1500 | Confirms the Major misattribution finding |

### Summary

The arithmetic core is sound and the ledger identity is carried faithfully, but two gaps would survive into implementation: the error taxonomy Q7 decided reached none of the four outputs, and `allocate` is underspecified exactly where BR2.7 permits the input its specification does not cover, in a way the stated exact-sum test cannot catch.
