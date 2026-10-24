## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-24T15:26:04Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | app/api/fees.py > record_verification, record_rejection | Neither route passes `correcting=True`, and `VerificationRequest` (app/schemas/fees.py) forbids extra fields and has no `correcting` field. A teacher re-deciding an already-verified claim always hits `_claim_the_decision`'s race guard and gets a 409 `CLAIM_ALREADY_VERIFIED`. | Add a client-settable `correcting` input (or a distinct correction route) and pass it through to `verify_claim`/`reject_claim`. | New |
| R-02 | Critical | functional-spec.md lines 397-409 vs app/api/fees.py | The committed state diagram asserts corrections (`approved_full --> approved_partial : corrected down`, etc.) and BR5.7/FR9.2 mandate every verification is correctable, but the built API makes every correction transition unreachable in production; `correcting=True` is exercised only by unit tests calling `verify_claim` directly. | Reconcile: either wire the API to the already-built correction mechanism, or revise rules.md/functional-spec.md to record the gap explicitly. | New |
| R-03 | Minor | app/fees/ledger_writer.py > void_accrued_cycles | Re-reading `student_decision` here is correct and verified as the only call site (app/fees/generation.py:359), but the docstring's claim that this defends against "a future caller" passing the wrong seat is not backed by any access-control or type-level enforcement beyond this one check. | No code change needed; consider noting this is a single-call-site invariant rather than a structural guarantee if the module ever gains a second caller. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Traceability sensor (per dispatch) | PASS except declared NFR25.10 GAP | Confirmed per dispatch notes; not re-litigated. |
| `make check` (per dispatch) | PASS, 91.69% backend, 100.00% money branch | Confirmed per dispatch notes; not re-litigated. |
| `pytest tests/fees/test_query_count.py tests/fees/test_decline_semantics.py` (re-run) | 12 passed | Confirms N+1 fix and decline semantics hold under direct re-execution. |
| `grep -rn "correcting=" app/ tests/` | Only `verification.py` internals and 4 test call sites | Confirms the correction path is unreachable from any route; this is the basis for the Critical findings above. |

### Summary

The arithmetic, idempotency, race-guard, N+1 fix, and layer-boundary work in D3 are sound and match their computed worked examples (400/2000/800/2027-03-31 all verified by reading the code against rules.md). The blocking issue is structural, not arithmetic: BR5.7 and FR9.2 make every verification correctable and the functional spec's own state diagram depends on it, but the HTTP surface gives a teacher no way to trigger `correcting=True` — the entire correction code path, including the money-reversal logic in `_reverse_prior_entries`, is dead in production and reachable only from the test suite. This is a real capability gap on a feature the requirements call mandatory, not merely an untested edge.

NOT-READY
