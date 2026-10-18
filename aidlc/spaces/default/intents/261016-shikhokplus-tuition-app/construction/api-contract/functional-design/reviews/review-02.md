## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T08:44:57Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/api-contract/functional-design/entities.md > `LensHintOutcome` constraints, vs. traceability.json coverage entry for `AC10.1.6` | See note A. `entities.md`'s `LensHintOutcome` says the server "refuses with authorization (403) and a dedicated code" when a client lens hint claims a lens the account's data does not support. The canonical acceptance criterion AC10.1.6 (`inception/user-stories/stories.md` line 628) says the opposite for the same trigger: "the server **ignores** it and resolves the lens from owned batches and enrollments" — no refusal at all. `traceability.json` marks AC10.1.6 "OK" against `BR1.1, BR1.5`, but neither rule mentions a lens hint, and no rule in `rules.md` governs this behaviour anywhere. | Reconcile the AC10.1.6-vs-entities.md contradiction explicitly (the project's own corrections rule requires this), write an actual rule that states which behaviour is contractual, and re-point AC10.1.6's traceability target at that rule instead of BR1.1/BR1.5, which are silent on it. | Resolved (reviewer) |
| R-02 | Minor | construction/api-contract/functional-design/rules.md > BR1.4 | See note B. Byte-identity is specified for the response but nothing requires the two code paths (lens-unreachable-but-exists vs. absent) to do equivalent work, unlike the OTP-issue precedent this rule is explicitly modelled on, which adds a structural same-hash-work requirement for exactly this reason. | Add a sentence analogous to the OTP rule requiring the two branches to perform structurally equivalent work (e.g. both query the same way before the lens check short-circuits), not only an identical response body. | Resolved (reviewer) |
| R-03 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/api-contract/functional-design/rules.md > BR1.4 and BR4.1 | BR1.4's structural-equivalence requirement (both branches must perform the same lookup work) has no committed fixture, no test, and no named owning Unit. BR4.1's fixture obligation covers only BR2.2, BR2.3, BR2.4 and BR3.1, correctly excluding BR1.4 since U2 has no lookup code to fixture — but nothing then hands this obligation to the Unit that will write the first lens-scoped lookup, unlike BR4.3's cross-Bolt obligation, which this same artifact names owners for. | Add an explicit handoff naming which Unit (the first to implement a lens-scoped resource lookup) must ship the structural-equivalence test, mirroring how BR4.3 names its owning artifacts — otherwise the rule most likely to be "fixed" back by an implementer has no mechanical check anywhere in the project. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/api-contract/functional-design/rules.md > Part B rules-summary table, BR4.3 row | The Part B summary table still reads "Four downstream artifacts contradict BR1.4 and must be amended," but BR4.3's own Part A statement and rationale were updated to "FIVE... DISCHARGED." The table is now inconsistent with the rule it summarizes. | Update the Part B table row for BR4.3 to say five artifacts and that they are amended/discharged, matching Part A. | New |

> R-01 Reviewer note: BR1.7 added, with a documented reconciliation of AC10.1.6 vs contract-summary B.4; entities.md and traceability.json now cite BR1.7 instead of nothing. See note A for residual scrutiny of the reconciliation itself.

> R-02 Reviewer note: BR1.4's `logic`/`violation_behaviour` now require both branches to perform the same lookup work, with an explicit, correctly-reasoned refusal of a wall-clock assertion. See note B for a gap this exposes.

### Validation Tool Results

No validation tools are listed for this stage's definition; manual cross-reference verification was performed instead (see Summary).

### Summary

Both prior findings are genuinely fixed: BR1.7 resolves the AC10.1.6/B.4 contradiction with a sound, FR1.4-grounded argument, and BR1.4 now requires equivalent lookup work on both branches with correctly structural (non-timing) phrasing. Cross-checked the unprompted BR4.3 change against all five named artifacts (bolt-plan.md's B2 DoD, B3/B7/B9 confidence hypotheses, and risk-and-sequencing-rationale.md's B3 checkpoint criterion) — all five are genuinely amended to require a byte-identical 403, so "discharged" is accurate, not overstated. The §2.6 insertion and §2.7/§2.8 renumbering are clean with no stale cross-references, and the 16-rule set is consistent across rules.md, functional-spec.md, entities.md and traceability.json. The one Major gap is that BR1.4's structural-equivalence clause, introduced to fix R-02, is itself left with no mechanical enforcement path to a future Unit — an implementer-facing risk but not one that blocks this Unit's own deliverables, so it does not cross the NOT-READY threshold.
