## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T13:10:28Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/identity-and-access/nfr-design/security-design.md > G. The audit log | The document states the audit log "fails open: it must not fail the authentication it was recording" but specifies no mechanism for how a failed audit write avoids destroying the caller's own transaction. The built `write_audit` (`app/audit/log.py`) needed a `session.begin_nested()` savepoint to achieve this — without it, a failed audit INSERT aborts the whole PostgreSQL transaction, and the caller's later `commit()` silently issues a ROLLBACK and returns normally, so the caller believes it succeeded while losing its own writes. This was found and fixed during implementation (the code's own comment documents a reproduced failure: an OTP was sent whose code could never verify). The design document never describes this mechanism, so a developer reading only §G would implement the same bug the build caught. | Add a subsection to §G stating that `write_audit` must run inside a nested transaction (`SAVEPOINT`) so that a failed audit write rolls back only the audit insert, not the caller's transaction — this is the mechanism, not an implementation detail, because without it "fails open" is false under PostgreSQL's whole-transaction-abort semantics. | New |
| R-02 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/identity-and-access/nfr-design/security-design.md > C.1 The ceiling cascade | The atomic-upsert mechanism is specified for the increment (`ON CONFLICT ... DO UPDATE SET count = count + 1 RETURNING count`), and the design states a refusal must "consume nothing at all — including the scope that refused," but no mechanism is given for the release (undo) path that makes that true. The built `_release` (`app/auth/ceilings.py`) is a separate, non-atomic `UPDATE ... SET count = count - 1` executed and committed in its own statement after the refusing read — a read-then-write pattern that is not atomic the way the increment is, and the code needed a dedicated concurrency test (`test_genuinely_concurrent_requests_never_exceed_the_limit`) to confirm it does not let the limit slip under contention. | Add a short note to §C.1 describing the release path's mechanism (a separate `UPDATE ... count - 1` after a refusing read) and the concurrency guarantee it does or does not provide, so the atomicity claim in this section does not read as covering both directions of the counter. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|

### Summary

This stage shipped with no review. Of the two known divergences this review was asked to check, both are real design gaps rather than mere staleness: the design states a fail-open guarantee for the audit log without the mechanism (a transaction savepoint) that implementation discovered was required to actually deliver it, and it specifies atomicity only for the ceiling increment while leaving the release/undo path — which the build needed a dedicated race test to validate — unaddressed. Both findings are Major/Minor and do not individually or jointly cross the NOT-READY threshold (two Major findings would; this review has one Major and one Minor), but both should be folded into the document since the underlying mechanisms are now proven correct in code and the design should describe what was actually necessary to build, not what was assumed sufficient before building it. The rest of the document — the HMAC-vs-bcrypt measurement (correctly framed as machine-measured, and the conclusion is structural/asymptotic rather than numerically fragile), the privacy-boundary layering, and the token state machine — holds up against the built code.
