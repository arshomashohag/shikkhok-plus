# Tech Stack Decisions — U3 android-identity

U3 changes the existing Android app. The stack is fixed and this unit
**adds no library**. This file records what it uses, the few choices it does
make, the toolchain controls that verify it (as built on this branch), and the
client-owned parts of NFR5 (coverage), NFR6 (compatibility) and NFR9
(committed contract).

## 1. What this unit builds on (read on this branch)

From `gradle/libs.versions.toml`, `android/build.gradle.kts` and
`aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md`:

| Concern | In use | Used by U3 for |
|---|---|---|
| Language and UI | Kotlin, Jetpack Compose (BOM in the catalogue), Material 3 | every screen in functional-spec W1–W8 |
| State | AndroidX ViewModel, `StateFlow`, `kotlinx-coroutines` | ViewModels, the availability checker's debounce, bounded wait and in-flight rule (performance NFR8.1–8.3) |
| HTTP | Ktor client with the OkHttp engine, `ContentNegotiation` + `kotlinx-serialization` JSON (`core/network/ApiClient.kt`) | every new call, through the existing `call { }` helper |
| JSON settings | `ignoreUnknownKeys = true`, `explicitNulls = false` (`ApiClient.kt:50-51`) | tolerating new fields (NFR6.1); the student-edit "clear an email" body needs an explicit `null`, which these settings omit, so that body uses a per-field encoding (frontend-components § 4.1) |
| Navigation | navigation-compose | three new destinations (frontend-components § 5) |
| Autofill | `androidx.compose.ui.autofill` (`AutofillType`) through `core/ui/AutofillHint.kt` | `Username` and `NewUsername` types added to the existing three hints |
| Tests | JUnit via `kotlin-test-junit`, `kotlinx-coroutines-test`, `ktor-client-mock`, Robolectric, `compose-ui-test-junit4` | every test in frontend-components § 8 |

## 2. Decisions

| ID | Decision | Rationale | Alternatives rejected |
|---|---|---|---|
| TSD-1 | **No new runtime or test dependency.** Debounce, the bounded wait and latest-wins use `kotlinx-coroutines` (`delay`, a cancellable `Job`, `withTimeout`). | Each library added means another admission note, more lockfile and checksum churn, and more forbidden-identifier surface (project Mandated), for behaviour the coroutines library already gives. | A Flow `debounce` operator chain (no dependency, but harder to make latest-wins and the cache explicit for an unfamiliar reviewer, OC-3); RxJava (new dependency). |
| TSD-2 | **No Turbine** (Q2). Emitted-sequence assertions collect the `StateFlow` into a list in `backgroundScope` under `UnconfinedTestDispatcher`, the existing `kotlinx-coroutines-test` idiom. | Turbine is not on this branch's classpath: no catalogue entry, no test imports it. The functional design's mention of Turbine (frontend-components § 8, written from `team.md`'s "JUnit plus Turbine") is read by code generation as "an emitted-sequence assertion". | Adding Turbine as a test dependency (an admission and lockfile change for a convenience). |
| TSD-3 | **`MockEngine` for every new repository call.** `ktor-client-mock` is already a test dependency and already used by the navigation tests. | It lets the tests assert method, path, body and the absence of a query string (security NFR3.1) against the real `ApiClient` configuration, renewal plugin included. | Fake repositories only (they cannot see the wire); a local HTTP server (heavier, no gain). |
| TSD-4 | **Autofill: `Username` on sign-in and the gate; `NewUsername` on sign-up, the replacement step and rename.** These are the platform's own types; nothing reads the SIM or the account list. | A password manager saves a credential against the username it was created with, and offers it at sign-in. | No autofill on the username (worse for the person); `EmailAddress` on the login field (wrong once usernames exist). |
| TSD-5 | **The client-side lookup bound is `withTimeoutOrNull` outside the repository call, and the shared `call { }` / `callDiscardingBody { }` helpers rethrow `CancellationException`** (Q1, review R-02). | Placed outside the call, the timeout scopes the 3 s bound to the two lookups and changes no other request. The helpers' `catch (_: Exception)` currently turns any cancellation into `TransportFailure`. That breaks structured concurrency for every caller and would let a timed-out or superseded lookup publish a result. Rethrowing cancellation is the conventional Kotlin rule, and it changes behaviour only for a cancelled caller (performance NFR8.3). | Ktor `HttpTimeout` installed globally (changes every request's failure behaviour, including the offline queue's); a timeout inside `call { }` (swallowed by the same arm). |

## 3. Toolchain controls on this branch (as built, read from the build files)

`team.md` (2026-10-22) records the whole Android quality toolchain as absent.
Most of it now exists on this branch. One part was installed and then
**deliberately scoped away from Kotlin sources**: ktlint, through Spotless
(row below). This unit relies only on what is here now. Read from `android/build.gradle.kts`,
`android/coverage.gradle.kts`, `gradle/libs.versions.toml`, `android/lint.xml`,
`android/detekt.yml` and `.github/workflows/check.yml` (job `android-unit`):

| Control | Built? | Where | U3 relies on it for |
|---|---|---|---|
| ktlint via Spotless (`spotlessCheck`) | yes, but **not over Kotlin sources** (review R-01) | `build.gradle.kts` `spotless { kotlinGradle { target("*.gradle.kts") … }; format("xml") { target("src/main/res/**/*.xml") … } }`, CI step "Kotlin format" | **Gradle scripts and resource XML only.** It does check this unit's `strings.xml` additions (trailing whitespace, final newline). **No formatter checks any `.kt` file this unit adds or changes.** ktlint was installed and scoped off `src/**/*.kt` on 2026-10-22 because it cannot parse the `[AC1.1.6]`-style KDoc traceability tags (the comment in `build.gradle.kts`, and `detekt.yml` line 8). What does check new Kotlin source: detekt (static analysis with the `ForbiddenImport`, `MagicNumber`, `MaxLineLength`, `LongMethod` and related rules), Android Lint, the compiler, and the source-scan tests named in security-requirements.md. Formatting itself is unchecked. This unit installs no Kotlin formatter: that decision is recorded and is not this unit's to reopen. |
| detekt (`ForbiddenImport` active) | yes | `detekt.yml`, CI step "Kotlin static analysis" | forbidden identifiers at commit time; the new `android.util.Log` / Ktor logging bans (security NFR3.3) |
| Android Lint with `lint.xml` (`HardwareIds` fatal, `MissingTranslation` fatal, `HardcodedText` error) | yes | CI step "Android Lint" | identifiers at commit time (NFR3.7); every new string present in both bundles (FR11.2's presence half) |
| Kotlin coverage report and ratchet | yes, **JaCoCo**, not Kover | `coverage.gradle.kts` (`jacocoDebugReport`, `verifyCoverageRatchet`), floor in `android/coverage-floor.txt`, CI step "Kotlin coverage ratchet" | NFR5.1 |
| Gradle dependency locking and checksum verification | yes | `dependencyLocking { lockAllConfigurations() }`, `android/gradle.lockfile`, `gradle/verification-metadata.xml` (`verify-metadata` true) | NFR3.8: no dependency arrives unnoticed |
| CVE annotation on the Gradle lockfiles | yes (annotates; blocks at release) | CI osv-scanner step | unchanged |
| Screenshot tests | **no** | — | not relied on; the Bangla layout check stays manual (FR11.2) |
| Macrobenchmark | **no** | — | not relied on; performance NFR8.4 is a manual pilot check |
| Turbine | **no** | — | not used (TSD-2) |

## 4. Client-owned NFR requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR5.1 | **Kotlin coverage does not decrease, stated as the ratchet actually measures it** (review R-04). `verifyCoverageRatchet` (`android/coverage.gradle.kts`) reads the JaCoCo line total for the **whole module** and fails only when it falls **more than 0.5 points** below `android/coverage-floor.txt` (`pct < floor - 0.5`). It **excludes** `**/*ScreenKt*`, `**/ui/*Kt*` and `**/navigation/*Kt*`, among other generated and test classes. So the composables of W1–W10 are not measured at all, and because the figure is whole-module, one wholly untested new ViewModel can pass. The ratchet's failure message invites lowering the floor in the same commit. **This unit does not lower the floor** (project Forbidden: never weaken a coverage floor or quality target to make a step pass); a lowered floor in its diff is a defect. | `./gradlew :android:verifyCoverageRatchet` in CI job `android-unit`, for the module figure only. |
| NFR5.4 | **Every new or changed ViewModel, mapper, checker and repository method ships its named tests**, because the ratchet cannot show per-class gaps (NFR5.1). The list is frontend-components § 8 as amended by this stage: SessionViewModel and SessionStateMapper, AvailabilityMapper and the checker, Signup, Auth, ChooseUsername, Username, Contacts, ReplaceContact and RemoveContact ViewModels and mappers, the students, roster and centres mappers, the HTTP repositories under `MockEngine`, the decode tests, and the scans in security-requirements.md. | Review against that list at code generation; the unit's code summary lists each test by name. **Nothing automated checks that each class has tests:** no per-class coverage gate exists, and this unit adds none. |
| NFR6.1 | **Unknown response fields are tolerated.** New server fields arrive and are dropped, with no decode failure. | Existing `ignoreUnknownKeys = true` (`ApiClient.kt:50`); decode tests from JSON strings that carry an extra field (frontend-components § 8). |
| NFR6.2 | **Response fields that became nullable decode as nullable.** `MemberResponse.phone` (C2) is the one field this client declared non-null; `MemberDto.phone` becomes `String? = null`. | The `MemberDto` decode test with `"phone": null` (functional-spec § 1 defect 1). |
| NFR6.3 | **Unknown enum-like values degrade, not crash.** An availability `status` outside the four known values decodes as a string and maps to "could not check". `username_required` absent reads `false`. | `UsernameAvailabilityDto` and `MeDto` decode tests (frontend-components § 8). |
| NFR9.1 | **The client's DTOs match the committed `openapi.json`.** Each new or changed DTO mirrors its schema's field names, nullability and required-ness, as read from `openapi.json` on this branch (functional-spec Sources). | Decode tests from JSON strings written from those schemas, and `MockEngine` body assertions. **Limit, stated plainly:** nothing automated compares the Kotlin DTOs with `openapi.json`. The server's schema-diff gate keeps `openapi.json` true to the server, not the client true to `openapi.json`. A server change after this unit is caught only by these tests going red, if they cover the field. |

## Assumptions & Open Questions

- [assumption] `AutofillType.NewUsername` and `AutofillType.Username` exist in
  the Compose UI version the catalogue's BOM resolves. Both have been in the
  `AutofillType` enum since the autofill API first shipped. The build is the
  verifier: an absent constant fails compilation.
- Open questions: None.

## Sources

- `gradle/libs.versions.toml`, `android/build.gradle.kts`,
  `android/coverage.gradle.kts`, `android/coverage-floor.txt`,
  `android/detekt.yml`, `android/lint.xml`, `gradle/verification-metadata.xml`,
  `.github/workflows/check.yml` (job `android-unit`), read on this branch.
- `aidlc/spaces/default/codekb/shikkhok-plus/technology-stack.md` (Android
  libraries; JaCoCo for coverage).
- `android/src/main/kotlin/com/shikkhokplus/app/core/network/ApiClient.kt`,
  `core/ui/AutofillHint.kt`.
- Requirements NFR5, NFR6, NFR9; contract C2 (`MemberResponse.phone`
  nullable); U1 reverse items `NFR5/android-coverage-ratchet` and
  `NFR6/clients-tolerate-unknown-fields`.
- Team practice: `team.md` Code Style (Android toolchain, as reconciled
  2026-10-22) and Testing Posture.
- Answers: `nfr-requirements-questions.md` Q1, Q2 [Q1] [Q2].
