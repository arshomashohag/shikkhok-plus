## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-15T10:39:04Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | android/src/main/kotlin/com/shikkhokplus/app/core/network/SessionRenewal.kt > redeem and renew; caller android/src/main/kotlin/com/shikkhokplus/app/core/ui/UsernameAvailability.kt > withTimeoutOrNull | This unit makes authenticated lookups (gate, rename) routinely cancelled by the next keystroke or the 3 s bound. If the access token has expired, the cancel can land inside the refresh call. redeem swallows the cancellation as Unreachable, so a pair the server already rotated is never saved and the stored refresh token is stale. The next refresh then looks like token reuse and the server revokes the whole family, signing the person out. The summary files SessionRenewal as an out-of-unit follow-up, but this unit creates the cancelling caller. | Run renew (redeem plus tokens.save) inside withContext(NonCancellable), so the rotation completes whatever happens to the caller, and add a test that cancels a lookup mid-refresh and asserts the new pair is saved. Rethrowing alone is not enough, because the server has already rotated. Move the SessionRenewal item out of "Follow-ups". | New |
| R-02 | Minor | android/src/test/kotlin/com/shikkhokplus/app/navigation/UsernameGateRoutingTest.kt > Root composable; android/src/main/kotlin/com/shikkhokplus/app/MainActivity.kt > OutsideGraphRoot, UsernameGateRoot | The routing test re-implements the root in a harness. It shares rootRouteFor and FailedRecheckEffect with the app, but the real gate wiring is untested: the ViewModel key, onChosen, reread, endSession and the early return before the queue and unread effects. A change there passes every test. code-summary.md reads as if the app's own decision is under test. | Extract the AppRoot body that takes the route into an internal composable with injectable dependencies and drive that. Otherwise state in code-summary.md that the wiring in MainActivity is covered by review only. | New |
| R-03 | Minor | android/src/main/kotlin/com/shikkhokplus/app/feature/account/ChooseUsername.kt > ChooseUsernameStateMapper.afterReread; core/session/SessionViewModel.kt > recheckNow | afterReread(true) gives Done whenever the read arrived. recheckNow returns true even if the account still says username_required. The gate would then sit on Done, where submit ignores everything but Editing and the screen is dead. This is unlikely, because it needs the server to answer password_required and then flag required again. | Have recheckNow return whether the gate was lifted, not whether the read arrived. Map a still-required read to Editing with a retry. | New |
| R-04 | Minor | android/src/test/kotlin/com/shikkhokplus/app/NoSavedSecretsTest.kt > secretName regex | The scan flags only rememberSaveable variables named password, confirm, current, code, otp or secret. A secret held in `value`, `pin` or `pwd` passes. The scan reads no current offender, and the StateRestorationTester tests are the behavioural half. | Add a comment stating the name-based limit and add pin, pass and pwd. Or ban rememberSaveable on the password and code composables outright. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| testDebugUnitTest on UsernameAvailabilityCheckerTest, UsernameGateRoutingTest, NoSavedSecretsTest, IdentifierToStringTest, CallCancellationTest | PASS | The builder's pass claim holds for these classes. I did not run the full 2097. |
| Wire check against openapi.json | PASS | Username and contact requests carry values in POST bodies, including both availability lookups. MemberResponse.phone is nullable in the contract and in MemberDto. StudentUpdateBodySerializer writes JsonNull for EmailEdit.Clear. VerifyRequest.username and PasswordSignInRequest.login match. |
| Gate weakening check (detekt.yml, tests, floor) | PASS | detekt.yml only gains entries. No @Ignore added. No lint.xml, Gradle script or coverage floor change. |
| Gate routing and removability | PASS | One SessionUiState value routes the gate. The gate is routed before the picker. The queue drain and unread effects sit after the early return. Last-contact removal is decided by the server (account.contact.last_one). The fail-open window while the read is Failed is bounded and documented (NFR3.13). |
| Records honesty | PASS | The 14 layout rows match the doc, FR11.2 and NFR8.4 are stated as not discharged, and the manifest holds 130 paths. |

### Summary

The unit is structurally sound: the gate, the wire shapes, the masking and the structured-concurrency fixes in call{} and callDiscardingBody{} hold up, and no gate was weakened. The one Major is that the new cancel-heavy authenticated lookups meet a renewal path that swallows cancellation, which can lose a rotated refresh token and sign the person out. It should be fixed with a NonCancellable renewal and a test.
