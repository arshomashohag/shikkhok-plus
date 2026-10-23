## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-23T05:05:27Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | android/src/main/kotlin/com/shikkhokplus/app/feature/invitations/ui/InvitationsScreen.kt > InvitationCard, the decline-button conditional | `if (row.state == AcceptanceState.PENDING)` branches the composable directly on a raw domain enum value rather than on a UI-state decision flag such as `canDecline`, which is the one place in the three new screens that compares a domain value instead of rendering a server-sent decision | Have the ViewModel/mapper derive a boolean (e.g. `showDecline`) onto `InvitationRow` or the UI state, and have the composable branch on that instead of on `AcceptanceState` directly | New |
| R-02 | Minor | android/coverage.gradle.kts > coverageExclusions | The new `**/ui/*Kt*` glob excludes any top-level-function class file in any `ui` package, not only Compose screen classes, so a future non-Compose helper placed under a `ui` package would be silently removed from the coverage denominator | Narrow the glob to the Compose screen naming convention actually in use (e.g. `**/ui/*ScreenKt*`) or document why the broader form is intentional | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| make check | Exit 0. ruff format/check clean, mypy clean (71 files), 700 backend tests passed, money module 100.00% branch coverage, backend overall 91.37% line coverage (floor 80%), Kotlin line coverage 45.93% against committed floor 45.84% | All gates pass as the code-summary claims; no coverage or quality gate was weakened to pass |
| traceability sensor | passed (fire_id 7ed84548) | Traceability from code-generation to upstream IDs resolves cleanly |

### Summary

Both granting queries (`_LENS_QUERY` in resolve.py, `_SUMMARY_QUERY` in summary.py) carry `decision = 'accepted'` inside the statement on both student and guardian branches, confirmed by direct read and corroborated by `tests/authz/test_acceptance_predicate.py` asserting both in one file. Signup (`app/accounts/service.py`) links seats via `_LINK_GUARDIAN_SEATS`, which sets only `guardian_account_id` and never touches a decision column — signing up is confirmed not accepting. The migration (`0004_acceptance_and_address.py`) adds both columns nullable, backfills conditionally from the pre-D1 link state, then sets `NOT NULL` with no `server_default` at any point — exactly as required to avoid silently withdrawing a working lens from already-signed-in students. The merged readers (`remove_enrollment`, roster `is_dormant`) both route through a single shared `_nobody_accepted` helper reading the decision columns rather than `student_account_id`. The signup ceiling cascade uses separate, narrowest-first, datastore-backed scopes with per-scope release on refusal, and the stated absence of a global signup scope is justified since the OTP cascade's own global ceiling already bounds the same SMS spend. `address` is present in `OWNER_PRIVATE_FIELDS`. The three Compose screens render from UI state with one minor exception (InvitationsScreen's decline-button visibility compares the raw `AcceptanceState` enum rather than a UI-state boolean); the two decline sheets correctly say opposite things about the fee per BR5.2, verified against the actual string resources. The Kotlin coverage exclusion change is legitimate: JaCoCo cannot see inside Compose-compiled composable bytecode under Robolectric, the screens remain genuinely verified by their own `*ScreenTest` suites, and the floor moved up rather than down. `make check` exits 0 with all coverage floors met.
