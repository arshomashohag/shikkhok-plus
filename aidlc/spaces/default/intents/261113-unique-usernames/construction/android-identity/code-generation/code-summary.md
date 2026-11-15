# Code Summary — android-identity (U3)

Built against the approved plan (`code-generation-plan.md`, Steps 1–23; Step 24
is this file, `source-manifest.json` and `traceability.json`). Android only: no
backend file, dependency, lockfile, verification metadata, Gradle build script
or coverage floor changed. `source-manifest.json` lists all 130 paths.

## Files

- **Network and DTOs**: new `core/network/UsernameDto.kt`. Changed: `AuthDto` (`login`, verify-time `username`), `AccountsDto`, `CentreDto` (`phone` nullable, `invited_email`), `ProfileDto` (`username`, `username_required`), `RosterDto` (guardian email), `TeacherStudentDto`, and the HTTP repositories for auth, account, centres, roster, sign-up and teacher students.
- **Model**: `core/model/Identifier.kt`. Its `emailIsWellFormed` now uses the server's pattern, at most 254 characters, trimmed. New `core/model/EmailEdit.kt` (Unchanged / Set / Clear).
- **Session and routing**:
  - `SessionUiState.UsernameRequired(then)`, `SessionStateMapper`, and `SessionViewModel` (`recheck`, `recheckNow`).
  - New `navigation/RootRoute.kt` (`rootRouteFor`, `FailedRecheckEffect`). `MainActivity.AppRoot` and the routing test both use it.
- **Shared UI**: new `UsernameField`, `LoginField`, `AvailabilityHint`, and `UsernameAvailability` (the checker: 500 ms debounce, latest-wins, 3 s bound, stop after 429). `AutofillHint` gains `Username` and `NewUsername`.
- **Auth**:
  - One-field sign-in.
  - Sign-up with a username and live availability.
  - Verify-time username replacement: new `ReplacementStateMapper.kt` and `ui/ReplaceUsernameStep.kt`.
- **Account**: new `ChooseUsername` (the full-screen gate), `Username` (rename in Settings), `Contacts`, `ReplaceContact` and `RemoveContact`, each with its screen. More gains the rows Username and Phone and email.
- **Students, roster and centres**: student and guardian emails, contact line, roster guardian email, centre invite by email, and a member with an email only.
- **Resources and config**: Bangla and English strings for every new message key. `detekt.yml` `ForbiddenImport` adds `android.util.Log` and `io.ktor.client.plugins.logging.*`; entries were only added.
- **Docs**: `docs/delivery/bangla-layout-check.md` gains 14 U3 layout rows and an NFR8.4 timing table for 4 screens. All are marked **not yet checked**.

## Tests

Command: `./gradlew :android:testDebugUnitTest :android:detekt :android:lintDebug :android:spotlessCheck :android:verifyCoverageRatchet`.

- **Tests**: 2097, with 0 failed and 0 skipped. That is up from 1822 at the Step 1 baseline.
- **detekt, Android Lint, Spotless**: pass. Spotless covers Gradle scripts and XML only, by the 2026-10-22 decision; no formatter checks `.kt` files.
- **Coverage ratchet**: JaCoCo **90.39%** against the committed floor of **90.05%**. The floor is unchanged; the pristine-HEAD baseline was 89.99%.

**Test-first evidence** (each test was run before its implementation):

| Step | Tests | Result before implementation |
|---|---|---|
| 3 | `CentreDtoTest` | `9 tests completed, 2 failed`, both `JsonDecodingException` on a null `phone` |
| 4 | `SessionStateMapperTest`, `SessionViewModelTest`, `ProfileDtoTest` | `51 tests completed, 10 failed` |
| 5 | `UsernameGateRoutingTest` | `7 tests completed, 6 failed`, gate not routed |

**Named tests (NFR5.4).** The ratchet cannot show per-class gaps, and nothing automated checks that each class has tests, so this list is the record:

- **Session**: `SessionStateMapperTest`, `SessionViewModelTest`, `UsernameGateRoutingTest`.
- **Username and contacts**: `ChooseUsernameViewModelTest`, `ChooseUsernameGateTest`, `UsernameStateMapperTest`, `UsernameViewModelTest`, `UsernameScreenTest`, `ContactsViewModelTest`, `ReplaceContactViewModelTest`, `RemoveContactViewModelTest`, `ContactsScreensTest`.
- **Availability**: `UsernameAvailabilityCheckerTest`, `AvailabilityMapperTest`, `UsernameFieldTest`, `AutofillHintTest`.
- **Auth and sign-up**: `ReplaceUsernameStepTest`, `HttpAuthLoginTest`, `UsernameDtoTest`. Extended: the auth, sign-up and password-flow mapper and ViewModel tests.
- **Data and network**: `ProfileDtoTest`, `CentreDtoTest`, `RosterDtoTest`, `HttpCentresRepositoryTest`, `StudentsStateMapperTest`, `EmailShapeTest`, `CallCancellationTest`. Extended: `WriteContractTest` and the HTTP repository tests.
- **Source scans**: `NoLoggingTest`, `IdentifierToStringTest`, `NoSavedSecretsTest`, `UsernameDeclarationScanTest`.

## Records this step owes (from the plan)

- **NFR9.1 correction.** `ContractConformanceTest` (every GET decodes an example built from `openapi.json`) and `WriteContractTest` (every write's method, path and body checked against `openapi.json`) already compare the client with the contract. Their example builder emits only the non-null arm of a nullable field, so a nullable server field that the client declares non-null passes both. That is how `MemberDto.phone` slipped through. `CentreDtoTest` now decodes the null case explicitly. Every new read and write is registered in both gates. NFR9.1's "nothing automated compares" understated these checks: the comparison exists, except for null arms.
- **Turbine substitution.** Turbine is not on the classpath, so sequence assertions collect the `StateFlow` into a list with `kotlinx-coroutines-test` (TSD-2).
- **Rename.** `ContactCard.value` and `RemoveContactUiState.Confirming.value` are now `contact`. The design calls the class `ContactCard(kind, contact)`.
- **Follow-ups, out of this unit's files.** The `catch (_: Exception)` sites in `HttpAttendanceRepository`, `SessionRenewal` and `TokenStore` still swallow `CancellationException`. This unit fixed the shared `call {}` and `callDiscardingBody {}` helpers, `HttpAuthRepository.logout` and the five `HttpRosterRepository` sites.
- **Follow-ups for U1/U2** (functional-spec § 9). `openapi.json` under-declares status codes for `/v1/me/contact`, `/v1/me/contact/remove`, `/v1/auth/verify` and `/v1/auth/password`.

## Deviations from the plan

1. **Step 2 is not a separate commit.** The builder was not allowed to commit. The patch is kept as a scratch file, and the unit lands as one squash commit in any case.
2. **`CallCancellationTest` uses the real dispatcher**, with a `CompletableDeferred` "reached" signal. Ktor's `MockEngineConfig.dispatcher` is deprecated at error level.
3. **`PasswordFlowMapperTest` flipped one assertion.** A trailing-dot email is now well-formed, because the client's check follows the server's pattern (Q5).
4. **Routing moved into `navigation/RootRoute.kt`** so that the app and the test share one decision. AppRoot's non-graph branches became the private composables `OutsideGraphRoot` and `UsernameGateRoot`, to stay under detekt's complexity limit.
5. **`FailedRecheckEffect` reads the lifecycle state as composition state**, so the 30 s wait runs on the composition clock and can be tested under virtual time.
6. **`SessionViewModel.recheckNow(): Boolean` was added.** It publishes only from `Failed` or `UsernameRequired`, and never publishes `Resolving`.
7. **`AuthStateMapper` was split into `ReplacementStateMapper.kt`** to satisfy detekt's `TooManyFunctions` rule. Behaviour is unchanged.
8. **Masking goes beyond the plan's list.** Masked `toString` overrides were added on `RosterRowDto` (which includes `feeAmount`), `IssueRequest`, `Identifier`, `MembersUiState`, `MemberLine`, `NewStudent`, `ProfileSummary`, `MoreActions`, `AccountRows` and the U3 UiStates. `IdentifierToStringTest` checks that each override exists and that it masks.
9. **`StudentUpdateBody` has a custom serializer**: `EmailEdit.Clear` writes an explicit JSON `null`, because `ApiClient.json` has `explicitNulls = false`.
10. **Reopening the remove sheet starts fresh.** Its ViewModel is keyed by an `opened` counter, so the sheet never shows the previous sheet's finished state.

## Not discharged (manual, stated plainly)

- **FR11.2, Bangla layout.** 14 rows; nothing automated checks Bangla layout.
- **NFR8.4, availability-hint latency on a low-end device.** 4 screens; nothing automated discharges it.
- Both rows are committed as **not yet checked**. They need a person with a low-end device in the Bangla locale.
