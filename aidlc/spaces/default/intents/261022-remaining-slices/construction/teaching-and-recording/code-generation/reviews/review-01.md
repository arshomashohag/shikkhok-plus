## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-24T23:50:36Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | app/api/teaching.py > write_session_topic | The topic write accepts a replay key and discards it. The request body declares `client_mutation_id`, the route binds it, and the call to `write_topic` never passes it on; `write_topic` in app/teaching/submissions.py has no such parameter and stores no submission row. The topic log therefore has no replay protection at all, while BR2.1 requires it to be a queued path carrying a replay key under the same rules as the roster. A device that resends a queued topic write after an uncertain response re-executes it: either it double-applies and consumes a version the client no longer tracks, or it is refused as a stale version. The roster path on the same screen handles the same situation correctly, so the two halves of one mid-class flow behave differently. | Give `write_topic` a `client_mutation_id` parameter, record each accepted topic write with a per-account uniqueness constraint on the replay key, return the stored result unchanged when the key is already present, and forward the field from the route. | New |
| R-02 | Major | tests/contract/test_teaching_contract.py > test_exactly_two_d4_request_bodies_carry_client_mutation_id | The one test guarding the replay-key rule reads the published schema and confirms exactly two request bodies declare the field. It passes while only one of the two is actually implemented, because it checks the declared shape and never that a resent key is honoured. This is what let the defect above survive a full suite. | Add a behavioural test per replay-key path that submits the same key twice and asserts the second call returns the first result and writes nothing, so the guarantee is checked rather than the field's presence. | New |
| R-03 | Minor | tests/teaching/test_api.py > the topic round-trip test | Every topic test generates a fresh replay key per call, so no test sends the same key twice on that path and nothing would fail if the field were removed from the body entirely. | Once the topic replay path is built, cover it with a resend test alongside the existing roster replay tests. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| (none listed for this stage) | n/a | Every finding was reached by reading the handlers against their services and the rules they cite. |

### Summary

Three of the four checks came back clean on direct reading, and the fourth found one real defect of the shape this unit was warned about. The refusal ordering in `submit_roster` is correct: `writable_session` runs before any version is compared, so the conflict body that carries the roster is unreachable by a stranger, and `tests/teaching/test_refusal_order.py` asserts that a stranger's refusal is byte-identical to one for an invented id. The replay lookup is scoped by both `submitted_by_account_id` and `client_mutation_id`, with a cross-account test asserting the second account is refused rather than handed the first account's result. The marksheet band edges absorb the remainder into the top band so a full mark stays in the distribution, and the merge loops until a full pass changes nothing. On routes, the marks side forwards every service parameter and mark correction is append-and-supersede rather than a flag, so D3's defect does not recur there. The topic write is where it does recur, in a new form: not a missing field but a bound field that is never forwarded, with the service lacking the parameter to receive it. The suite does not catch it because the one test covering the rule reads the schema rather than the behaviour, and because every topic test uses a fresh key. The unit's own code summary names the topic log as "the quiet second queued path, easy to forget"; it was remembered on the wire and forgotten in the server.
