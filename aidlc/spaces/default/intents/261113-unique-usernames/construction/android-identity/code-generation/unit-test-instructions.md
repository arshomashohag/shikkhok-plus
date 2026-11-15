# Unit Test Instructions — android-identity (U3)

## Framework and setup

- **Runner.** The JVM unit-test task `:android:testDebugUnitTest` from the
  repository root through the Gradle wrapper, the same task CI's `android-unit`
  job runs. Test dependencies are already declared in `android/build.gradle.kts`:
  `kotlin-test` and `kotlin-test-junit`, `kotlinx-coroutines-test`,
  `ktor-client-mock`, Robolectric, `compose-ui-test-junit4`. Nothing is added.
  **Turbine is not on the classpath and is not added** (tech-stack TSD-2).
- **Android SDK.** In this sandbox the SDK is at `/opt/android-sdk`. Export it
  for every command below:

  ```bash
  export ANDROID_HOME=/opt/android-sdk
  ```

- **Robolectric.** Tests that render Compose run under
  `@RunWith(RobolectricTestRunner::class)` with `@Config(sdk = [34])`, as
  `MessageKeyCoverageTest` and the existing screen tests do. The pinned
  `android-all-instrumented` jars are in the version catalogue, so no network
  fetch is needed when Gradle's caches are warm.
- **Dependency locking and checksum verification** are on
  (`android/gradle.lockfile`, `gradle/verification-metadata.xml`). Any new
  artifact would fail resolution; this unit adds none.
- Use `--no-daemon` as CI does, so a stale daemon cannot mask a change.

## Commands (this unit only)

Run from the repository root (`/workspace/shikkhok-plus`). Every command names
this unit's test classes exactly.

**Runner check and baseline (plan Step 1).** Run before the first test-first
step:

```bash
export ANDROID_HOME=/opt/android-sdk
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.core.session.SessionViewModelTest'
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.feature.auth.MessageKeyCoverageTest' \
  --tests 'com.shikkhokplus.app.core.network.WriteContractTest'
./gradlew :android:verifyCoverageRatchet --no-daemon
```

By reading the code, the second command is expected red before Step 7 (15
unmapped keys) and before Step 10 (`POST /v1/accounts` without `username`).
Record what it actually prints, and the ratchet's figure, in the code summary.

**Test-first steps (plan Steps 3–5).** Run each named class alone and record its
failing output before the matching implementation step:

```bash
export ANDROID_HOME=/opt/android-sdk
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.core.network.CentreDtoTest'
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.core.session.SessionStateMapperTest' \
  --tests 'com.shikkhokplus.app.core.session.SessionViewModelTest' \
  --tests 'com.shikkhokplus.app.core.network.ProfileDtoTest'
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.navigation.UsernameGateRoutingTest'
```

**This unit's whole test set:**

```bash
export ANDROID_HOME=/opt/android-sdk
./gradlew :android:testDebugUnitTest --no-daemon \
  --tests 'com.shikkhokplus.app.core.network.CallCancellationTest' \
  --tests 'com.shikkhokplus.app.core.network.CentreDtoTest' \
  --tests 'com.shikkhokplus.app.core.network.ProfileDtoTest' \
  --tests 'com.shikkhokplus.app.core.network.UsernameDtoTest' \
  --tests 'com.shikkhokplus.app.core.network.RosterDtoTest' \
  --tests 'com.shikkhokplus.app.core.network.TeacherStudentDtoTest' \
  --tests 'com.shikkhokplus.app.core.network.HttpAuthLoginTest' \
  --tests 'com.shikkhokplus.app.core.network.HttpSignupRepositoryTest' \
  --tests 'com.shikkhokplus.app.core.network.HttpAccountRepositoryTest' \
  --tests 'com.shikkhokplus.app.core.network.HttpCentresRepositoryTest' \
  --tests 'com.shikkhokplus.app.core.network.HttpTeacherStudentsRepositoryTest' \
  --tests 'com.shikkhokplus.app.core.network.WriteContractTest' \
  --tests 'com.shikkhokplus.app.core.network.ContractConformanceTest' \
  --tests 'com.shikkhokplus.app.core.session.SessionStateMapperTest' \
  --tests 'com.shikkhokplus.app.core.session.SessionViewModelTest' \
  --tests 'com.shikkhokplus.app.core.model.EmailShapeTest' \
  --tests 'com.shikkhokplus.app.core.ui.AvailabilityMapperTest' \
  --tests 'com.shikkhokplus.app.core.ui.UsernameAvailabilityCheckerTest' \
  --tests 'com.shikkhokplus.app.core.ui.AutofillHintTest' \
  --tests 'com.shikkhokplus.app.core.ui.UsernameFieldTest' \
  --tests 'com.shikkhokplus.app.core.designsystem.StringPlaceholderTest' \
  --tests 'com.shikkhokplus.app.feature.auth.MessageKeyCoverageTest' \
  --tests 'com.shikkhokplus.app.feature.auth.AuthStateMapperTest' \
  --tests 'com.shikkhokplus.app.feature.auth.AuthViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.auth.AuthScreenTest' \
  --tests 'com.shikkhokplus.app.feature.auth.PasswordFlowMapperTest' \
  --tests 'com.shikkhokplus.app.feature.auth.SignupStateMapperTest' \
  --tests 'com.shikkhokplus.app.feature.auth.SignupViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.auth.SignupScreenTest' \
  --tests 'com.shikkhokplus.app.feature.auth.ReplaceUsernameStepTest' \
  --tests 'com.shikkhokplus.app.feature.account.ChooseUsernameViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.account.ChooseUsernameGateTest' \
  --tests 'com.shikkhokplus.app.feature.account.UsernameStateMapperTest' \
  --tests 'com.shikkhokplus.app.feature.account.UsernameViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.account.UsernameScreenTest' \
  --tests 'com.shikkhokplus.app.feature.account.ContactsViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.account.ReplaceContactViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.account.RemoveContactViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.account.ContactsScreensTest' \
  --tests 'com.shikkhokplus.app.feature.profile.ProfileScreenTest' \
  --tests 'com.shikkhokplus.app.feature.students.StudentsViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.students.StudentDetailViewModelTest' \
  --tests 'com.shikkhokplus.app.feature.students.StudentsStateMapperTest' \
  --tests 'com.shikkhokplus.app.feature.roster.RosterStateMapperTest' \
  --tests 'com.shikkhokplus.app.feature.centres.CentresViewModelsTest' \
  --tests 'com.shikkhokplus.app.feature.centres.CentresScreensTest' \
  --tests 'com.shikkhokplus.app.navigation.UsernameGateRoutingTest' \
  --tests 'com.shikkhokplus.app.navigation.AccountRowsTest' \
  --tests 'com.shikkhokplus.app.navigation.DestinationTest' \
  --tests 'com.shikkhokplus.app.navigation.MoreActionsTest' \
  --tests 'com.shikkhokplus.app.NoLoggingTest' \
  --tests 'com.shikkhokplus.app.IdentifierToStringTest' \
  --tests 'com.shikkhokplus.app.NoSavedSecretsTest' \
  --tests 'com.shikkhokplus.app.UsernameDeclarationScanTest' \
  --tests 'com.shikkhokplus.app.ForbiddenIdentifiersTest'
```

**Static and build gates this unit touches:**

```bash
export ANDROID_HOME=/opt/android-sdk
./gradlew :android:detekt --no-daemon
./gradlew :android:lintDebug --no-daemon
./gradlew :android:spotlessCheck --no-daemon
./gradlew :android:verifyCoverageRatchet --no-daemon
```

- `detekt` carries the two new `ForbiddenImport` entries.
- `lintDebug` covers `MissingTranslation` (fatal) for the new strings and
  `HardwareIds` (fatal).
- `spotlessCheck` covers Gradle scripts and res XML only. **No formatter checks
  Kotlin sources**, by the decision recorded in `android/build.gradle.kts` on
  2026-10-22.
- `verifyCoverageRatchet` depends on `jacocoDebugReport`, which runs the whole
  module's unit tests. Running the whole suite once is also how plan Step 23
  shows the existing suite stays green; it is the module gate, not a per-unit
  command.

## Coverage expectations

- **Kotlin coverage ratchet** (`android/coverage.gradle.kts`): whole-module
  JaCoCo line coverage must not fall more than 0.5 points below
  `android/coverage-floor.txt`. **The floor file is not lowered by this unit**
  (project Forbidden), even though the ratchet's message offers that.
- The ratchet excludes `*ScreenKt*`, `ui/*Kt*` and `navigation/*Kt*`, so this
  unit's composables are not in the figure. ViewModels, mappers, the checker,
  DTOs and repositories are measured.
- Because the figure is whole-module, it cannot show a single untested class.
  The obligation is NFR5.4: each class in the plan's Steps 2–21 has its named
  test class above. The code summary lists them, and review checks the list.
  Nothing automated checks per-class coverage.
- Standard strategy, per component: five to eight tests for each mapper,
  ViewModel and repository, as listed per step in the plan. Every ViewModel
  covers loading, success, error and the explicit retry of a failed write
  (TC-8, D-9).

## Mocking and stubbing guidance

- **HTTP: `MockEngine` through the real client.** Build the client with
  `ApiClient.build("https://staging.example", engine, tokens)`, as the
  existing `HttpAccountRepositoryTest` does, so the
  JSON settings (`ignoreUnknownKeys`, `explicitNulls = false`), the workspace
  and platform headers and `SessionRenewal` are the real ones. In the handler,
  assert `request.method`, `request.url.encodedPath`,
  `request.url.encodedQuery` (empty for the no-query routes of NFR3.1) and the
  body read as text and parsed with `Json`. Respond with JSON strings copied
  from `openapi.json` shapes.
- **Virtual time with `MockEngine`.** Construct the engine as
  `MockEngine(MockEngineConfig().apply { dispatcher = testDispatcher; addHandler { … } })`,
  so a handler's `delay(…)` or `awaitCancellation()` advances with `runTest`.
  If the Ktor version on this branch refuses that property, fall back to a
  suspending fake at the repository seam for the timing half, and keep one
  real-`MockEngine` test with a short real delay for the cancellation half.
  Record which was used in the code summary.
  This is how the 3 s bound, the stale-lookup case and `CallCancellationTest`
  are driven without wall-clock waits.
- **ViewModels.** `Dispatchers.setMain(StandardTestDispatcher())` in `@Before`
  and `resetMain` in `@After`, as `AuthViewModelTest` does. Drive the 500 ms
  debounce and the 30 s re-check with `advanceTimeBy` and `runCurrent`, and
  never with real sleeps. Collect `StateFlow` sequences with
  `backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { state.toList(seen) }`.
- **Repositories in ViewModel tests** are hand-written fakes of the feature
  interfaces (`AuthRepository`, `SignupRepository`, `AccountRepository`,
  `ProfileRepository`, `CentresRepository`), recording each call so a test can
  assert that the password was received once and that nothing was sent after
  a 429.
- **Compose.** Robolectric with `createComposeRule()`. For saved-state checks,
  use `StateRestorationTester(composeRule)`, `emulateSavedInstanceStateRestore()`,
  then assert the password field is empty and the username or login survives.
  Find nodes by the existing and new test tags, never by English text, because
  the tests run in either locale.
- **Source scans** (`NoLoggingTest`, `IdentifierToStringTest`,
  `NoSavedSecretsTest`, `UsernameDeclarationScanTest`) read files relative to
  the module directory (`src/main/kotlin`, `detekt.yml`), as
  `ForbiddenIdentifiersTest` does.

## Test data

- No device data and no real identifiers anywhere. Use:
  - phones in the `+88017…` test range;
  - emails under `example.com`, or `example.invalid` for sentinels;
  - usernames like `nadia_k`, `Rahim.Uddin`, `rahim_math`;
  - passwords like `correct horse`.
- **Sentinels for the masking tests:** `sentinel_user_7`,
  `sentinel@example.invalid`, `+8801999999999`, `sentinel-pass`. Assert none
  appears in any `toString()`.
- **Username boundary values** (client cap only; FR1 is the server's):
  - 64 characters accepted;
  - 65 rejected;
  - 64 plus surrounding spaces accepted;
  - 21 accepted.
- **Email corners** from the server pattern: `a@b.c.` and `a@.b.c` accepted;
  `a@b` and `@b.c` refused.
- **JSON fixtures** are inline strings in the tests, written from the committed
  `openapi.json` schemas named in functional-spec § Sources. They are not
  separate files and are not generated at test time.
- Nothing persists between tests: there are no shared preferences, tokens use
  `TokenStore.InMemory()`, and each test builds its own client and fakes.
