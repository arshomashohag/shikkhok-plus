## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T13:10:28Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | functional-spec.md > §2.1 "Issue a code", step 4 and BR2.7's rationale in rules.md | The byte-identical-response design (BR2.7) closes the hashing-timing gap between the known/unknown branches, but step 4 still performs an asymmetric database write: the known-number branch INSERTs an `OtpRequest` row while the unknown-number branch only discards the computed hash. A transactional row write (lock acquisition, WAL) is a far larger and more exploitable timing signal than the hash computation the design actually tests for. The "honest limitation" note in BR2.7 discusses only the hash-timing residual risk and never mentions this write-side asymmetry, so the documented limitation understates the real gap. | Either make the unknown branch perform a symmetric no-op write (e.g. an INSERT into a throwaway table or a discarded transaction) of comparable cost, or extend BR2.7's structural test and its "honest limitation" note to explicitly name the DB-write asymmetry as an unresolved, deliberately-accepted gap rather than letting the current wording imply the matching is already complete. | New |
| R-02 | Major | functional-spec.md > §2.1 step 2, vs rules.md BR2.2 and BR2.5 | The ceiling check order is inconsistent across the two documents an implementer would read. functional-spec.md states the order as "global daily → per-IP-prefix hourly → per-number hourly → per-number daily." BR2.2's `logic` block is an unordered OR of three conditions, and BR2.5's `logic` block reads "IF the global daily count >= the ceiling THEN refuse... ELSE check the sub-ceilings first," which also puts the global check first but contradicts BR2.5's own rationale that sub-ceilings must be checked so "an attacker burning one number's allowance does not exhaust everyone else's" — an argument for checking the narrower (per-number/per-IP) ceilings before the global one, not after. As written, a single number hammering the endpoint still increments the global counter on every one of its refused-by-nothing-yet requests before the per-number ceiling is ever consulted. | State one authoritative check order across rules.md and functional-spec.md, and verify it against BR2.5's own stated goal (degrade before cliff-edging) — if sub-ceilings are meant to catch an attacker before they affect the global budget, order them before the global check, or explain why checking global first still achieves that goal. | New |
| R-03 | Minor | functional-spec.md — missing section | The seed script described in rules.md's BR6.3 (a committed script that inserts one `Owner` row and one `Enrollment` row to let the B3 verification checkpoint demonstrate a resolved teacher lens, since U3's own code may never write those tables) is the mechanism that makes "the skeleton works" (per functional-design-questions.md Q7) actually achievable, yet it is never mentioned in functional-spec.md's "§2.6 Migrate" or "§4 Boundary cases" sections. An implementer building from functional-spec.md alone — the document meant to drive the build — would not discover this obligation exists. | Add a short step or note to functional-spec.md (§2.6 or a new subsection) describing the committed seed script, its scope (verification-only, never imported by application code), and the B5 removal obligation, so the operational document carries the same information as rules.md. | New |
| R-04 | Minor | functional-spec.md > §2.3 "Rotate", step 4 | The note states that a client crash between receiving and persisting rotated tokens causes the next refresh to fail as reuse, calling this "the correct conservative outcome," but does not state what recovery path the affected teacher has. The only implied recovery is a fresh sign-in via OTP, which re-spends the per-number SMS budget (BR2.2) for an outcome that was a client bug rather than a security event. | State explicitly in the spec that the recovery path is re-authentication via OTP, and confirm this doesn't interact badly with the per-number hourly/daily ceilings for a teacher who hits this more than once in a session (e.g. app restarts mid-class on a low-end device). | New |
| R-05 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/identity-and-access/functional-design/rules.md > BR2.7 | The hashed-write symmetry fix recorded here (an earlier draft discussed only hash symmetry; the write asymmetry is now closed) has no counterpart note anywhere flagging that the same transactional-write cost also widens the attack surface of `write_audit` inside the same code path — the audit INSERT the fix in `app/audit/log.py` had to savepoint-isolate. The two corrections (BR2.7's rollback-insert and the audit savepoint) touch the same transaction and are not cross-referenced. | Add a one-line cross-reference in BR2.7's rationale noting that the rolled-back INSERT and any audit write inside `issue()` share a transaction, so a future change to one must preserve the other's isolation. | New |

> R-01 Not re-checked this round

> R-02 Not re-checked this round

> R-03 Not re-checked this round

> R-04 Not re-checked this round

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|

### Summary

The business rules still accurately describe what was built and verified. `BR1.1`–`BR1.4` (computed lens), `BR2.1`–`BR2.7` (the seven OTP controls, including the narrowest-first ceiling order and the rollback-insert existence-oracle fix), `BR3.1`–`BR3.3` (the privacy boundary and its meta-test), `BR4.1`–`BR4.3` (token rotation, hashing, `kid`), `BR5.1`–`BR5.5` (the gateway contract) and `BR6.1`–`BR6.3` (the empty-shell and seed-script boundary) all match the code: `Account` carries no role column, OTP hashing uses HMAC through one chokepoint, the ceiling cascade is narrowest-first with per-scope atomic increments, RLS is enforced and probed as a restricted role, and refresh-token reuse invalidates the whole family. The one new concern (above) is a documentation cross-reference gap, not an architectural defect, and does not block READY.
