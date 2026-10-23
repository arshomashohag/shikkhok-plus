## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T01:26:25Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/signing-up-and-joining/functional-design/functional-spec.md § entity relationships and § 5 (the migration) | D1's migration links accounts to `pending` seats (W2 step 5) and sets `student_account_id` non-null while `student_decision` stays `pending`. The merged `remove_enrollment` (`app/batches/service.py`) still gates removal on `record.student_account_id is not None` meaning "claimed", with no knowledge of the new decision columns. Once D1 ships, a teacher can no longer remove a pending-but-signed-up seat — exactly the mistyped-number recovery path AC1.15.2/AC2.5.1a exist to protect — even though D1 touches none of this. This is a regression in already-merged, routed code (`app/api/batches.py`) caused by D1's own schema change, not a D2 scope gap: `US2.5`/`AC2.5.1a` is validly assigned to D2 by the story map, but the *regression* in `remove_enrollment`'s existing claimed-check is caused by D1's migration landing before D2's fix, and no D1 artifact names `remove_enrollment` as a query D1 must update or explicitly leave broken-with-record. | Either update `remove_enrollment`'s claimed predicate in D1 to read the decision columns (`student_decision == 'accepted'` rather than `student_account_id is not None`), or explicitly document in functional-spec.md that this regression is a known, accepted gap until D2 lands, naming the interval during which teachers cannot remove a pending-but-linked seat. | New |
| R-02 | Major | construction/signing-up-and-joining/functional-design/functional-spec.md § 2 Workflows, W2 | The functional-spec documents the fix to the two lens-granting queries (`_LENS_QUERY`, `_SUMMARY_QUERY`) per ADR-014, but does not enumerate any other existing query that reads `student_account_id`/`guardian_account_id` as a proxy for "claimed" or "active" and that D1's schema change could silently break. `remove_enrollment` is one instance (see the Critical finding); the design gives no evidence a sweep for other such readers was performed, despite the project's own recorded learning ("Adding a column is not adding a behaviour. Name the queries that must start reading it...") applying directly here. | Add a short section to functional-spec.md (or entities.md) enumerating every existing query/service function that reads the two account-id columns on `Enrollment`, and state for each whether D1 must update it, D2/D3 will, or it is unaffected — closing the sweep the project's own learning calls for. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Manual cross-reference: ADR-009 through ADR-014 vs rules.md/entities.md | Consistent | Entity shapes, enum columns, no-default/conditional-backfill rationale, and the two-query fix all match the ADRs and the live code at `app/db/models.py`, `app/authz/resolve.py`, `app/authz/summary.py`, `app/batches/service.py:172`. |
| Manual check: BR5.2 vs BR5.3, BR5.4 vs BR6.1 | No contradiction found | BR5.3 is explicitly reconciled against BR5.2 in rules.md's own note (per-link data, one action moves both columns only when both links name the same account); BR5.4's accept-after-decline is a `declined→accepted` transition, not a reset to `pending`, so it does not conflict with BR6.1. |
| Manual check: traceability.json sample (AC1.11.3, AC1.2.1a/.2a/.3a, AC1.10.x) | Targets genuinely satisfy the criteria | BR1.1+BR1.2 jointly satisfy AC1.11.3; BR1.1/BR1.3/BR5.1 jointly satisfy the superseded AC1.2.1; no decorative mapping found in the sample checked. |
| Manual check: D1 schema-standalone claim ("D1 adds two columns, zero tables") | Confirmed against `app/db/models.py` | No `student_decision`, `guardian_decision`, or `profile.address` columns exist today; the claim is accurate, unlike a prior project incident of this kind. |
| Manual check: US1.14/AC1.14.x scoping (money consequences of decline) | Correctly out of scope | `unit-of-work.md` explicitly assigns US1.14 in full to D3 ("Inherits US1.14 in full... D1 sets the decision; D3 is where that decision first touches money"); the functional-spec's AC1.14.2a carve-out matches this. |
| Manual check: US2.5/AC2.5.1a scoping | Correctly assigned to D2 by `unit-of-work-story-map.md` | Confirms the Critical finding above is about an unstated *side effect* of D1's migration on merged code, not a missing D1 responsibility for US2.5 itself. |

### Summary

The rules, entities, and workflows are well-grounded in the ADRs and faithfully reflect the live code for the authorization fix the unit exists to deliver (ADR-014's two-query fix is correctly identified and specified). The blocking issue is a side effect the design does not acknowledge: linking an account to a still-pending seat (W2) changes the meaning of `student_account_id IS NOT NULL` everywhere else in the merged codebase, and at least one live, teacher-facing capability (`remove_enrollment`) silently breaks as a result, regressing the exact mistyped-number recovery path the unit is built to protect. This needs to be named and resolved (fixed or explicitly deferred) before the design is ready to build from.
