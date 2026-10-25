## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T16:36:39Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | android/src/main/kotlin/com/shikkhokplus/app/feature/roster/RosterStateMapper.kt line 129 | For a declined seat with no recorded guardian phone, `displayLabel = dto.guardianPhone ?: dto.displayName` falls back to the student's own name. A student-side decline shows that student's name on the row. BR2.3's own `violation_behaviour` text reads "A name is displayed for a person who has said the seat is not theirs" — the code produces exactly that outcome in the fallback branch. | Use a neutral placeholder (e.g. "declined — no number on file") for the no-phone fallback instead of the display name, or confirm with the business owner that BR2.3 is meant to admit this exception and amend BR2.3's statement and violation_behaviour to say so explicitly. | New |
| R-02 | Major | app/batches/service.py `_guardian_state` (around line 201) and BR2.2 in functional-design/rules.md | BR2.2 states "A link that does not exist reports absent, never pending" without qualifying which identifying field decides "does not exist." The code correctly treats a teacher-recorded-but-unsigned-up guardian (phone set, account id null) as pending, not absent — but this distinction is not written into BR2.2 itself, only into the code comment and code-summary.md. A future reader of rules.md alone would not learn this and could re-derive the wrong implementation, as code-summary.md admits was nearly done. | Add the phone-vs-account-id distinction to BR2.2's `logic` field in rules.md, not just to code comments, so the rule document itself carries the fact that caused the near-miss. | New |
| R-03 | Minor | android/src/main/kotlin/com/shikkhokplus/app/feature/batches/ui/BatchesScreen.kt line 193 | `state.rows.sumOf { it.enrollmentCount }` computes a client-side total across batches for the header subtitle. BR1.3 states "the response carries it AND the client never counts rows to derive it" with no stated exception for summing already-server-counted per-row values. The code-summary correctly flags this as noticed and pre-existing D1 scope, but it is left unresolved and it is the same shape the practice calls out for D3/D5 as the most consequential erosion path. | Either have the batch-list response carry a server-computed grand total, or add an explicit carve-out to BR1.3 stating that summing server-sent per-row counts for a display subtotal is permitted, so the rule and the code agree. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Direct code inspection of `_guardian_state`, `_is_removable`, `_roster_row` | Matches code-summary's claims | BR2.2, BR2.4, BR3.1 behavior verified as described |
| Direct inspection of `RosterStateMapper.displayLabel` and `BR2.3` | Contradiction found | See Critical finding above |
| `tests/test_named_test_manifest.py` Kotlin regex re-run against `GuardianHomeScreenTest.kt` | Matches all 4 named tests including the Back test | Manifest-extension claim verified correct |
| `tests/batches/test_removal_refusals.py` assertions | Pinned distinct `message_key` values plus a `!=` assertion | Mutation claim (converging keys fails 2/4) is credible from the assertions present |
| Re-derivation of longest Bangla string via the committed script | `roster_remove_claimed_remedy` = 145 chars, confirmed longest | Matches the code-summary's claim exactly |
| `add_enrollment` return-type change, single caller in `app/api/batches.py` | One caller, updated consistently | Deviation is real but contained, no orphaned caller |
| `US2.6`/`AC2.7.x` cross-record ID resolution | `US2.6` in this record's own unit-of-work story map = "Guardian child home and switcher"; `AC2.7.1-4` resolve only in the prior record (`261016-...`) as `US2.7` | The traceability note's explanation is internally consistent and the IDs do resolve, but only by reading two separate intent records — this is fragile, not broken |

### Summary

The backend decisions (guardian-absence keying, server-computed removability, one shared row builder) are well-reasoned, test-backed, and verified correct against the code. The one Critical finding is real and user-facing: a student who declines a seat with no guardian phone recorded will see their own name rendered on the teacher's roster row, which is precisely the exposure BR2.3 says must not happen — the rule names its own violation and the fallback branch falls into it. This is a role/case-dependent display defect of the same class this project has hit twice before (decline-copy, contrast-ratio claims), and it should be fixed or the rule explicitly amended before this is treated as done.
