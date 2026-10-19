## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T02:08:18Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/money-core/functional-design/rules.md > the 32 rules, all groups | Q7 decided this Unit raises `ValidationError` for bad input and `ConflictError` for a state-forbidden operation, but neither class name appears in any of the four outputs. Every refusal rule says only "refuse and raise". See note A. | Add a rule naming the two classes and assigning each refusal in BR1.1, BR4.1, BR4.5 and BR5.2 to one of them, so U2's handler finds them already raised correctly. | Unresolved |
| R-02 | Critical | construction/money-core/functional-design/functional-spec.md > 2.5 Allocate into n parts | `allocate` is specified only as "divide, distribute the remainder across the leading parts", which is ambiguous for a negative amount, which BR2.7 explicitly permits. See note B for the divergent outputs. | State that `allocate` refuses a negative amount, or define the division and remainder sign convention explicitly and add a negative worked example. | Resolved (reviewer) |
| R-03 | Major | construction/money-core/functional-design/functional-spec.md > 3, S5 "A correction to the upstream illustration" | The spec says ADR-002 and B1's hypothesis state "2500 instead of 1500". Both actually state 3000 against 2000, which is the spec's own computed answer. The stale 2500/1500 figure is in team.md and domain-design/memory.md. See note C. | Correct the attribution to name team.md's Corrections entry, not ADR-002 and the bolt plan, and route the team.md fix to the learnings gate. | Resolved (reviewer) |
| R-04 | Major | construction/money-core/functional-design/functional-spec.md > 2.8 Format for a locale, and rules.md BR5.4 | `format(locale)` requires locale data and Bangla digit rendering, which is configuration or a library this Unit's own "no settings, no I/O" claim does not account for. Left unstated, the B1 100%-branch-coverage and buildable-before-any-endpoint claims are at risk. | State what `format` may depend on and that the dependency carries no I/O and no settings read, or move formatting out of B1's coverage obligation. | Resolved (reviewer) |
| R-05 | Major | construction/money-core/functional-design/functional-spec.md > 2.5 step 1, and 5.3 Zero | A part count below one has no stated behaviour. Step 1 says "receive a part count of one or more" without saying what happens otherwise, and 5.3 covers a zero amount but not a zero or negative `n`. | State that a part count below one is refused, and name which error class it raises. | Resolved (reviewer) |
| R-06 | Major | construction/money-core/functional-design/functional-spec.md > 2.4 Apply a rate | The rate's domain is unbounded: a negative rate, a rate above one and a zero rate are all unspecified, and a negative rate silently produces a negative Money that BR2.7 then permits. | State the permitted rate domain and the behaviour outside it, including whether a negative rate is refused. | Resolved (reviewer) |
| R-07 | Minor | construction/money-core/functional-design/functional-spec.md > 2.1 step 5 | The ten-integer-digit overflow refusal has no BR behind it and no error class, so the one construction rule with a numeric threshold is the one a reader cannot trace. | Give the magnitude bound its own rule, or fold it into the construction rule and name the raised class. | Resolved (reviewer) |
| R-08 | Minor | construction/money-core/functional-design/functional-spec.md > 2.9 Serialize, and 5.4 Negative | The canonical wire form is defined as "no sign for a positive value", which leaves the negative wire form undefined although BR2.7 permits a negative Money to exist. | State whether a negative money value may cross the API, and if so its canonical string form. | Resolved (reviewer) |
| R-09 | Critical | construction/money-core/functional-design/functional-spec.md > 5.6 How this Unit refuses, row "A credit application exceeding available credit [BR4.5]" | BR4.5, entities.md and worked scenario S8 all state the apply is `min(available_credit, amount_owed)`, so an apply can never exceed the grant and this refusal cannot occur. See note A. | Either make over-application a real refusal by removing the clamp from BR4.5, entities.md and S8, or drop the row and state the module raises only validation failures. | New |
| R-10 | Major | construction/money-core/functional-design/functional-spec.md > 5.6 refusal table | BR5.7 refuses serializing a negative and rules.md assigns it `ValidationError`, but it has no row in the table that claims to assign every refusal path. See note B. | Add a BR5.7 row to the §5.6 table with its class, so the table covers every refusal the rules define. | New |

> R-01 Reviewer note: BR1.8 and §5.6 name both classes, but the sole `ConflictError` path is unreachable. See note A.

> R-02 Reviewer note: BR2.9 fixes the answer; recomputed, magnitude-then-sign matches the table on all rows.

> R-03 Reviewer note: §3/S5 now attributes the stale 2500/1500 to `team.md` Corrections and routes it to the learnings gate.

> R-04 Reviewer note: BR5.6 makes locale an argument and names the permitted data source.

> R-05 Reviewer note: BR2.8 refuses a count below one as a validation failure.

> R-06 Reviewer note: BR2.10 fixes the rate domain: float refused, negative refused, zero and above-one permitted.

> R-07 Reviewer note: BR1.7 carries the ten-integer-digit bound and names `ValidationError`.

> R-08 Reviewer note: BR5.7 refuses serializing a negative; consistent with the contract's sign-free pattern.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| allocate recomputation, magnitude-then-sign, 7 cases incl. negative and zero | All exact, sums match originals | BR2.9 and BR2.3 agree everywhere; R-02 and R-05 closed |
| grep ConflictError across the four outputs | One occurrence, functional-spec.md §5.6 only | The class is named in one place and raised by no specified path; supports the Critical finding |
| grep `min(available_credit` across the four outputs | rules.md BR4.5 and entities.md sign_discipline | Two outputs specify the clamp that makes the refusal unreachable |
| contract-summary.md Money pattern vs BR5.7 | `^[0-9]+\.[0-9]{2}$`, no sign accepted | BR5.7 is consistent with the contract; R-08 closed |
| §5.6 table rows vs refusal rules in rules.md | BR5.7 present in rules, absent from table | Supports the Major finding |

### Summary

Six of the eight prior findings are genuinely closed, and the two Criticals from iteration 1 are the split decision: `allocate` is now fully determined, but the error taxonomy was added on the reading of Q3 that the other three outputs contradict, leaving the module's only `ConflictError` unreachable by construction and its one new refusal rule unassigned to a class.
