## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-14T00:00:00Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | app/accounts/contact.py > _replace and _store (consume_contact_change before the taken check) | A replacement verify whose destination turns out to be held by another account still burns one of the five daily changes: `_store` commits the spent code and the counter upsert when it answers CONTACT_TAKEN. I reproduced it with a scratch test: after one 409 account.contact.taken, `rate_limit_counter` holds contact_chg_day = 1 for the account. BR5.6 says only a completed change counts and a failure leaves nothing counted; no test covers this path. | Run the taken check before `consume_contact_change`, or roll the counter back on the taken and IntegrityError paths. Add a test asserting the count is 0 after a taken refusal. | Resolved (reviewer) |
| R-02 | Major | app/centres/service.py > add_invitation; app/centres/memberships.py > _LINK | One person can now hold two live memberships in one centre. A phone-only invitation and an email-only invitation for the same account pass the per-contact duplicate check and both link to that account. I reproduced it: the account holds a live teacher row and a live manager row in one centre. The class and examiner lens joins use `.first()` on `OwnerMember.account_id`, so with two accepted rows the lens can pick the wrong member and answer CLASS_REASSIGNED. Before U2 one phone per account made this impossible. | Refuse or skip a link or invitation when the target account already holds a live membership in that centre, for the invite path and for `link_memberships`. Add a unique index on (owner_id, account_id) for live rows if the design allows it. Add a test. | Resolved (reviewer) |
| R-03 | Major | tests/governance/test_deletion_paths.py; tests/accounts/test_contact_change.py > test_no_contact_reaches_a_log_line_or_an_audit_row; code-generation/traceability.json (NFR3.1, NFR3.4) | Verifiers that NFR3.1 and NFR3.4 name are not built: the add-then-delete race (an authorization-predicate item, test-first) and the sentinel test over W1 to W3, W9 and deletion, since the NFR3.4 sentinel test covers contact changes only. traceability.json still marks both NFR3.1 and NFR3.4 as OK. The privacy and erasure guarantees are therefore not verified where the NFR asked. | Build the add-then-delete race test and extend the NFR3.4 sentinel test to the teacher-save, centre-invite, lookup and deletion paths. Mark the traceability rows honestly until then. | Resolved (reviewer) |
| R-04 | Minor | app/centres/service.py > create_centre; app/schemas/centres.py > MemberResponse.invited_email | `create_centre` copies the creating account's own email into `owner_member.invited_email`, and `MemberResponse` returns it to every manager listing the centre. That puts one manager's account email in another manager's response, against BR1.4 ("never the account's email") and NFR3.3. BR1.9 chose this, so the design contradicts itself. | Either withhold `invited_email` for rows whose invitation was the manager's own sign-up, or amend BR1.4 and NFR3.3 to say this is intended. | Unresolved |
| R-05 | Minor | code-generation/code-summary.md (disclosed gaps); Makefile | The NFR8.3 EXPLAIN index-usability test and the NFR8.10 purge test are not built, and the NFR8.1, 8.2, 8.6, 8.7 and NFR7.2 figures rest on a manual staging run. The summary states this plainly. The gaps are acceptable for this stage only if the staging figures are recorded before merge. | Record the manual figures in the Bolt's PR description, or add the EXPLAIN test, which is cheap. | Resolved (reviewer) |
| R-06 | Minor | app/students/service.py > find_or_create_student (revive path) calling _apply_identity | Reviving an archived student re-targets and resets links through `_apply_identity` without `_refuse_relink` or `_refuse_student_twice`. A changed contact on an accepted or erased link is therefore not refused, and a changed student email could violate `uq_enrollment_batch_student` as a 500. The phone-only revive behaved this way before U2, but email now widens it. | Apply the same refusals on revive, or record the revive path as an accepted exception in the spec. | Resolved (reviewer) |
| R-07 | Minor | app/centres/service.py add_invitation and app/centres/memberships.py _LINK (R-02 fix) | One live membership per account per centre is enforced by a read-then-insert check and a NOT EXISTS clause, with no unique index on live (owner_id, account_id). An invite racing a concurrent link of the same account can still leave two live rows. | Add a partial unique index on (owner_id, account_id) where revoked_at is null and account_id is not null, or record the residual race as accepted. | New |

> R-01 Reviewer note: app/accounts/contact.py _replace now checks the destination is free right after the code is consumed and before the day's count; a race at the unique index rolls the whole change back (keep_spent_code=False). The regression test in test_contact_change.py passes.

> R-02 Reviewer note: Both matcher statements in app/centres/memberships.py carry a NOT EXISTS live-membership clause, and add_invitation refuses an account already live in the centre with centre.member.already_invited. Tests in test_centres.py pass. A residual race is noted under New findings.

> R-03 Reviewer note: tests/accounts/test_contact_sentinels.py covers teacher save, centre invite, both lookups, replacement, removal and in-app deletion across logs, audit rows and error bodies. The add-then-delete race test in test_deletion_paths.py pins the deletion to wait on the account key. All pass.

> R-04 Reviewer note: Behaviour unchanged. The justification holds: the same row already carries the creator's phone, and the member list is visible only to the centre's managers. It is Minor and not blocking; the owner can accept it.

> R-05 Reviewer note: tests/accounts/test_contact_indexes.py EXPLAINs each email statement with seqscan off and tests the age-based purge of counters and replacement codes. Latency figures stay manual, and the artifacts now say plainly that nothing automated discharges them.

> R-06 Reviewer note: find_or_create_student now runs the same relink refusals and the student-twice-in-batch check as an edit before un-archiving. The test in test_students.py passes.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| pytest (sentinels, indexes, deletion paths, centres, students, contact change) | 108 passed, 0 failed | The fix round tests hold against a real PostgreSQL. |
| ruff check app tests | All checks passed | Lint is clean. |

### Summary

All three Major findings are fixed with passing, test-backed changes, and the Minor findings are either fixed or non-blocking. The only new concern is a narrow race on the one-live-membership rule that has no database constraint behind it.
