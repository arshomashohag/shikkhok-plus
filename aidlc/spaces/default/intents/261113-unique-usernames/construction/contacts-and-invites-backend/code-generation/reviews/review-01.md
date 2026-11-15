## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-14T15:36:20Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | app/accounts/contact.py > _replace and _store (consume_contact_change before the taken check) | A replacement verify whose destination turns out to be held by another account still burns one of the five daily changes: `_store` commits the spent code and the counter upsert when it answers CONTACT_TAKEN. I reproduced it with a scratch test: after one 409 account.contact.taken, `rate_limit_counter` holds contact_chg_day = 1 for the account. BR5.6 says only a completed change counts and a failure leaves nothing counted; no test covers this path. | Run the taken check before `consume_contact_change`, or roll the counter back on the taken and IntegrityError paths. Add a test asserting the count is 0 after a taken refusal. | New |
| R-02 | Major | app/centres/service.py > add_invitation; app/centres/memberships.py > _LINK | One person can now hold two live memberships in one centre. A phone-only invitation and an email-only invitation for the same account pass the per-contact duplicate check and both link to that account. I reproduced it: the account holds a live teacher row and a live manager row in one centre. The class and examiner lens joins use `.first()` on `OwnerMember.account_id`, so with two accepted rows the lens can pick the wrong member and answer CLASS_REASSIGNED. Before U2 one phone per account made this impossible. | Refuse or skip a link or invitation when the target account already holds a live membership in that centre, for the invite path and for `link_memberships`. Add a unique index on (owner_id, account_id) for live rows if the design allows it. Add a test. | New |
| R-03 | Major | tests/governance/test_deletion_paths.py; tests/accounts/test_contact_change.py > test_no_contact_reaches_a_log_line_or_an_audit_row; code-generation/traceability.json (NFR3.1, NFR3.4) | Verifiers that NFR3.1 and NFR3.4 name are not built: the add-then-delete race (an authorization-predicate item, test-first) and the sentinel test over W1 to W3, W9 and deletion, since the NFR3.4 sentinel test covers contact changes only. traceability.json still marks both NFR3.1 and NFR3.4 as OK. The privacy and erasure guarantees are therefore not verified where the NFR asked. | Build the add-then-delete race test and extend the NFR3.4 sentinel test to the teacher-save, centre-invite, lookup and deletion paths. Mark the traceability rows honestly until then. | New |
| R-04 | Minor | app/centres/service.py > create_centre; app/schemas/centres.py > MemberResponse.invited_email | `create_centre` copies the creating account's own email into `owner_member.invited_email`, and `MemberResponse` returns it to every manager listing the centre. That puts one manager's account email in another manager's response, against BR1.4 ("never the account's email") and NFR3.3. BR1.9 chose this, so the design contradicts itself. | Either withhold `invited_email` for rows whose invitation was the manager's own sign-up, or amend BR1.4 and NFR3.3 to say this is intended. | New |
| R-05 | Minor | code-generation/code-summary.md (disclosed gaps); Makefile | The NFR8.3 EXPLAIN index-usability test and the NFR8.10 purge test are not built, and the NFR8.1, 8.2, 8.6, 8.7 and NFR7.2 figures rest on a manual staging run. The summary states this plainly. The gaps are acceptable for this stage only if the staging figures are recorded before merge. | Record the manual figures in the Bolt's PR description, or add the EXPLAIN test, which is cheap. | New |
| R-06 | Minor | app/students/service.py > find_or_create_student (revive path) calling _apply_identity | Reviving an archived student re-targets and resets links through `_apply_identity` without `_refuse_relink` or `_refuse_student_twice`. A changed contact on an accepted or erased link is therefore not refused, and a changed student email could violate `uq_enrollment_batch_student` as a 500. The phone-only revive behaved this way before U2, but email now widens it. | Apply the same refusals on revive, or record the revive path as an accepted exception in the spec. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check app tests | PASS | Clean. |
| mypy app | PASS | 240 source files clean. |
| pytest test_contact_matching.py and test_contact_change.py | PASS (28 passed) | Integration tests ran, none skipped. |
| scratch test: taken replacement leaves a count | FAIL (count 1, expected 0) | Confirms the BR5.6 finding. |
| scratch test: two live memberships, one account, one centre | FAIL (2 rows, expected 1) | Confirms the duplicate-membership finding. |

### Summary

The matcher, the single precedence rule, relink-blocked handling for recycled contacts, deletion markers, lock ordering (advisory keys before row locks, one helper) and the bounded retry (whole transaction, no side effects before commit, 55P03 not retried) all hold up under review. NOT-READY rests on three Major findings: the daily change counter is burned by a refused replacement, the cross-contact invitation path can give one account two live memberships in a centre, and NFR3.1 and NFR3.4 verifiers are missing while the traceability marks them OK.
