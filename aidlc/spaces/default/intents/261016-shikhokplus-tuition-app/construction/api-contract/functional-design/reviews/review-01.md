## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T08:37:40Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/api-contract/functional-design/entities.md > `LensHintOutcome` constraints, vs. traceability.json coverage entry for `AC10.1.6` | See note A. `entities.md`'s `LensHintOutcome` says the server "refuses with authorization (403) and a dedicated code" when a client lens hint claims a lens the account's data does not support. The canonical acceptance criterion AC10.1.6 (`inception/user-stories/stories.md` line 628) says the opposite for the same trigger: "the server **ignores** it and resolves the lens from owned batches and enrollments" — no refusal at all. `traceability.json` marks AC10.1.6 "OK" against `BR1.1, BR1.5`, but neither rule mentions a lens hint, and no rule in `rules.md` governs this behaviour anywhere. | Reconcile the AC10.1.6-vs-entities.md contradiction explicitly (the project's own corrections rule requires this), write an actual rule that states which behaviour is contractual, and re-point AC10.1.6's traceability target at that rule instead of BR1.1/BR1.5, which are silent on it. | New |
| R-02 | Minor | construction/api-contract/functional-design/rules.md > BR1.4 | See note B. Byte-identity is specified for the response but nothing requires the two code paths (lens-unreachable-but-exists vs. absent) to do equivalent work, unlike the OTP-issue precedent this rule is explicitly modelled on, which adds a structural same-hash-work requirement for exactly this reason. | Add a sentence analogous to the OTP rule requiring the two branches to perform structurally equivalent work (e.g. both query the same way before the lens check short-circuits), not only an identical response body. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| No stage-specified validation tools were listed for this dispatch | N/A | Findings are grounded in direct cross-reference of rules.md, functional-spec.md, entities.md, traceability.json against inception/contract-design/contract-summary.md, inception/domain-design/decisions.md (ADR-001), inception/user-stories/stories.md, and inception/delivery-planning/bolt-plan.md. |

### Summary

The previous iteration's six findings are genuinely fixed: BR3.1's split allowlists, BR2.4's two field sets (verified against ADR-001's own text), BR1.4/BR1.5's byte-identity strengthening (verified against bolt-plan.md, which has already been amended in B2/B3/B7/B9 to match — the cross-Bolt obligation BR4.3 records is not just promised but discharged upstream), BR2.2's `$ref`-based predicate, and BR3.2's named defeaters are all sound and well-evidenced. BR4.1's fixture-with-which-violation requirement correctly closes the trivial-pass hole for a Unit with no routes and no money endpoint. The blocking problem is new: marking AC10.1.6 "OK" in this revision surfaces a real contradiction between the upstream acceptance criterion (ignore an invalid lens hint, silently resolve correctly) and this Unit's own `LensHintOutcome` contract type (refuse with 403) — a contradiction that was present but harmless while AC10.1.6 was honestly Deferred, and is no longer harmless once the artifact claims to satisfy it against rules that never address the behaviour.
