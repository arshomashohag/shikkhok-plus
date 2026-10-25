## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T01:57:31Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/.../functional-design/rules.md § "The sweep: every merged reader of the two link columns" | The sweep table marks the "privacy field list" (`app/contract/privacy.py`) as "unaffected" by D1. It is affected: `OWNER_PRIVATE_FIELDS` in that file is a hand-maintained `frozenset` (currently `{self_name, photo_ref}`), matched by field name, not a reflection of `Profile`'s columns. D1 adds `Profile.address`, a field the unit itself calls (in entities.md) "the most consequential single disclosure available in this product." Until `address` is added to that frozenset, the schema-wide teacher-lens privacy gate that BR3.2 relies on ("enforced structurally... the schema-wide invariant test already iterates every teacher-lens response schema") will not catch a future teacher-facing schema that leaks it — the same class of merged-code drift the unit's own sweep methodology exists to catch for the link columns. | Add `OWNER_PRIVATE_FIELDS` to the sweep table with disposition "must add `address`, D1" (or equivalent), and add a verification obligation in functional-spec.md §6 asserting `address` is in that set — matching the care already given to `student_account_id`/`guardian_account_id`. | New |
| R-02 | Minor | aidlc/.../functional-design/rules.md § sweep table, and functional-spec.md §2 (W2 step 5) | Two code citations in the merged-reader sweep do not match the live code read 2026-10-23: the function named `create_enrollment` at `app/batches/service.py:444` does not exist — the actual function is `add_enrollment` at line 438. `remove_enrollment` is at line 254, not 274 as cited (twice, in rules.md and functional-spec.md). `list_guardian_children` is at line 179, not 197. The analysis content for each is otherwise accurate against the live code. | Correct the function name (`add_enrollment`) and the three line numbers so a developer opening the file at the cited line lands on the right code. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability (sensor fire, traceability.json) | passed | 28 ACs, 0 GAP, every `BRx.y` target resolves in rules.md, no unexplained rule orphans |
| required-sections (entities.md, rules.md, functional-spec.md, frontend-components.md) | passed (all 4) | No required section missing |
| upstream-coverage (entities.md, rules.md, functional-spec.md, frontend-components.md) | passed (all 4) | Upstream artifacts cited adequately |

### Summary

The core of this unit — the acceptance state machine and its authorization consequence — is sound and is verified against the live code rather than asserted: `_LENS_QUERY` (app/authz/resolve.py) and `_SUMMARY_QUERY` (app/authz/summary.py) today grant and count purely on link existence with no decision predicate, exactly as BR1.1/BR1.2 claim is wrong and must be fixed; `is_dormant` (service.py:172) and `remove_enrollment`'s claimed-check (service.py:276) read `student_account_id` exactly as BR7.1/BR7.2 describe, and the mistyped-number recovery-path defect the unit exists to prevent is real in the current code. Scope boundaries against D2 (roster screen) and D3 (money consequences of decline) are each verified against unit-of-work.md and the story map and are accurate, including the one traceability `reverse` entry that crosses into another unit's AC (BR7.1 → AC2.5.1a, correctly assigned to D2). No circular dependencies, no contradictions among BR5.2/BR5.3, BR5.4/BR6.1, or BR1.3/BR5.5 — each potential tension is explicitly reconciled in the rule text itself. The one gap worth the human's attention before approving is the privacy-boundary omission above: the unit's own methodology (name every merged reader a new column affects) was applied faithfully to the link columns and not applied to the new `Profile.address` field against the hand-maintained privacy allowlist, on the exact axis (child-data privacy) this project treats as highest-stakes. Neither finding is Critical: the first is a documentation/test-coverage gap catchable by the code-generation stage reading `app/contract/privacy.py` directly, not a design flaw in the rule itself (BR3.2's stated mechanism is correct; the artifact just didn't follow through on applying it to its own new column), and the second is purely citation accuracy with no effect on the design's content.
