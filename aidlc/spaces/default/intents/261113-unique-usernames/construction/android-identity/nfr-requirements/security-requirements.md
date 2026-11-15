# Security Requirements — U3 android-identity

The Android client's share of NFR1 (anti-enumeration), NFR3 (privacy
boundary), NFR4 (test ordering) and the project's Forbidden and Mandated rules,
for the screens in `functional-spec.md` W1–W10. Server-side enforcement (the
privacy gate, uniform refusal, ceilings, the hold digest) is U1's and U2's;
this file covers only what the client must do or must never do. Every row
names its verifier. Where a verifier is review or a manual check, the row says
so; such a row is not a mechanical control.

Threat model in one paragraph. This is a children's-data app on a Play
Families track. The client holds four secrets or identifiers in this unit's
flows:
- the password (sign-up, rename, replace, remove);
- the six-digit code held for the verify replacement;
- the username, which is owner-private (FR9) and low-entropy;
- the person's own phone and email, plus the teacher-recorded emails of
  others (student form, centre invite).

The realistic leaks on a phone are logs, `toString` in crash or test output,
URLs (proxy and server access logs), saved instance state and backups, and
third-party SDKs that read device identifiers. The realistic logic risks are
a client that reveals more than the server decided (an oracle) and a gate
that fails open.

## Requirements

### Anti-enumeration (NFR1)

| ID | Requirement | Verifier |
|---|---|---|
| NFR1.1 | Sign-in renders the server's refusal and nothing more. Unknown username, account without a password and wrong password all arrive as `auth.password.wrong` and are shown identically, through the existing mapper. The client has no branch that could tell them apart (FR4.3). | Existing `AuthStateMapperTest` cases kept. New mapper test: the one-field sign-in maps `auth.password.wrong` exactly as the phone form did. |
| NFR1.2 | The client never classifies the login value (FR4.1). It sends one `login` field as typed (trimmed), so the request shape reveals nothing about which kind the person meant, and the client holds no parsing that could diverge from the server's. | `MockEngine` test: `POST /v1/auth/password` body has `login` and no `phone`/`email` keys (frontend-components § 8). |
| NFR1.3 | The availability hint shows only the server's four answers. `unavailable` is shown without saying whether the name is taken or held (ADR-007), and nothing about who holds it is requested or displayed. | `AvailabilityMapper` tests: one state per status; there is no state that distinguishes held from taken. |
| NFR1.4 | The verify replacement says the person's own name was taken, which they already know they typed. It names no account and carries no server data beyond the key. | Mapper test on `ReplaceUsername(previous)`: `previous` is the person's own typed value, carried from the form, never from the response. |

### Privacy and secrets on the device (NFR3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.1 | **No username, login, phone, email, password or code in a URL.** Both availability lookups, the username change, sign-in and contact replace and remove send their values in a JSON body (NFR3.5 as amended for C1). The one exception is the already-added lookup's `?email=` / `?phone=` query, which C2 defines as a query parameter for the person's own typed contact. That route is U2's (U1 reverse item `NFR3/already-added-query-string-in-nginx-log`), and this unit makes no claim for it. | `MockEngine` tests assert the request URL carries **no query string** on the two username lookups, `PUT /v1/me/username`, `POST /v1/auth/password`, `POST /v1/me/contact` and `POST /v1/me/contact/remove`. |
| NFR3.2 | **No secret or identifier in `toString`, for every class this unit adds or changes that holds one** (review R-03). A Kotlin data class prints every property, so any such class reaching a crash report, an assertion message or a log would print the value. Each class below overrides `toString` to print its non-identifying fields and `***` for: username, login, phone, email, password, code, and a contact `value` or `contactLine`. **Requests and forms:** `SignupForm`, `SignupRequestDto`, `VerifyRequest`, `UsernameAvailabilityRequest`, `UsernameChangeRequest`, `PasswordSignInRequest`, `ContactChangeRequest`, `ContactRemoveRequest`, `MemberInviteDto`, `StudentCreateBody`, `StudentUpdateBody`, `NewStudent`. **Responses changed here:** `MeDto`, `UsernameChangeDto`, `MemberDto`, `TeacherStudentDto`, `RosterRowDto`. **UI states and view models of rows:** `AuthUiState.ReplaceUsername` (`previous`), `UsernameUiState.Viewing`, `Editing`, `Changed`, `ContactCard`, `ContactsUiState.Loaded`, `RemoveContactUiState.Confirming`, `ReplaceContactUiState` (all three), `MembersUiState` (`invitePhone`, `inviteEmail`), `MemberLine`, `StudentDetail`, `StudentListRow`, `ProfileSummary`. `AvailabilityState`, `ChooseUsernameUiState` and `SessionUiState` hold no such value and need no override. The six-digit code is held only in a private ViewModel field, never in a state class. **Out of scope, recorded:** classes this unit does not touch that already print teacher-recorded phones, such as `StaffDto` and `ProfileUiState.Viewing`. They predate it and are listed for a later unit, not silently claimed. | Two verifiers. **(1)** A `toString` test per listed class asserting the printed text contains none of its identifying values (in the pattern of `PasswordFlowMapperTest`). **(2)** A source-scan test, `IdentifierToStringTest`, in the no-type-resolution style of `NoFloatingPointTest`. Over the files this unit adds or changes, listed in the test, it fails if a `data class` declares a property whose name matches `(?i)username|login|phone|email|password|code|previous|contactLine|value` without an `override fun toString` in the same class body. A new class with such a property cannot slip past without review noticing a red test. |
| NFR3.3 | **No log lines.** The Android source has no `android.util.Log` call and no Ktor logging plugin today (searched in `android/src/main`). This unit adds `android.util.Log` and `io.ktor.client.plugins.logging.*` to `detekt.yml`'s active `ForbiddenImport` list (Q5), so either is refused on the commit that adds it. **Stated limit:** `println` and a fully qualified `android.util.Log.d(…)` written without an import are not caught. This project's detekt run has no type resolution, so `ForbiddenMethodCall` cannot fire, as `detekt.yml` already records for `Double`. Those two remain review's. | Three committed verifiers, all in CI's `android-unit` job (review R-05). **(1)** detekt `ForbiddenImport` (`./gradlew :android:detekt`). **(2)** `NoLoggingTest`, a source scan of `src/main/kotlin` in the `NoFloatingPointTest` / `ForbiddenIdentifiersTest` style, without type resolution. It fails on any match of the regular expression `\bprintln\(|\bprint\(|android\.util\.Log|\bLog\.(v|d|i|w|e|wtf)\(|printStackTrace\(|io\.ktor\.client\.plugins\.logging`. The `\b` boundaries keep identifiers such as `fingerprint(` from matching. The expression matches nothing in `android/src/main/kotlin` today (searched), so the test lands green. That closes the `println` and fully-qualified-`Log` gap mechanically, so neither is left to review. **(3)** The same test asserts that `detekt.yml`'s `ForbiddenImport` list contains the two new entries, as `ForbiddenIdentifiersTest` does for the identifier set, so an emptied list fails a test. The scan is textual and can be defeated by deliberate obfuscation, such as a reflective call; that limit is stated and left to review. |
| NFR3.4 | **Passwords and the held code are never persisted.** Password fields live in `remember`, never `rememberSaveable` or a `SavedStateHandle`. A ViewModel holds a password only for one request: the replace flow drops it once the code is sent, and rename and remove drop it on the answer. The verify replacement holds the six digits in ViewModel memory only, and forgets them on Change, Back, sign-out and `onCleared`. The app's existing `allowBackup="false"` with `dataExtractionRules` (manifest) keeps app data out of backups and device transfer. | **(1)** Compose `StateRestorationTester` tests on every password field this unit adds or changes (review R-06): the sign-in form (one login field), the sign-up form (password and confirm), the rename form, the replace entry step and the remove sheet. After a simulated recreation each password field is empty, and the login, username or new contact value survives. The gate and the verify replacement step have **no** password field. Their tests assert that the typed username survives and that, after recreation, the replacement step still submits with the code held in the ViewModel. `StateRestorationTester` recreates composition state only; ViewModel memory survives it, which is the intended behaviour. **(2)** `NoSavedSecretsTest`, a source scan of `src/main/kotlin`. It fails on any `SavedStateHandle` in `feature/auth`, `feature/account` or `core/session`; there is none today. It also fails on any `rememberSaveable` declaration whose variable name matches `(?i)password|confirm|current|code|otp|secret`; none today. **(3)** ViewModel tests: the repository fake receives the password once; after `changeNumber`, `submitReplacement` sends nothing (frontend-components § 8). The manifest settings are unchanged and already checked by review. |
| NFR3.5 | **The username is shown only to its owner.** It arrives only in `MeResponse` and `UsernameChangeResponse`, both owner-only (ADR-010), and is rendered only on More's Username row and the Username screen. No other DTO declares a `username` field, so no other screen can show one. No notification, share sheet or deep link carries it. | Server-side: U1's privacy gate (FR9.2). Client-side (review R-08): **(1)** a source-scan test over `core/network`. It matches `@SerialName("username")`, `@SerialName("login")`, and a property named `username` or `login` with or without `@SerialName`, because an unannotated property serializes under its own name. It fails when any match is in a class outside an explicit allowlist: `MeDto`, `UsernameChangeDto`, `SignupRequestDto`, `VerifyRequest`, `UsernameAvailabilityRequest`, `UsernameChangeRequest`, `PasswordSignInRequest`. **(2)** The `MockEngine` URL assertions of NFR3.1, which catch a value placed in a path or query by any means, including string building, which a declaration scan cannot see. |
| NFR3.6 | **Teacher-recorded emails are someone else's data.** The student and invite email fields set no autofill hint, so the device's own accounts are not offered. They are shown only on the teacher's and the manager's own screens, as the recorded phones are today (TC-13, FR6.3). | Review of the two forms; Robolectric screen test asserting the fields carry no autofill node. |
| NFR3.7 | **Forbidden identifiers, unchanged and still enforced at commit and at release.** No `TelephonyManager` or other forbidden identifier is used to fill the login, phone or email fields; the number is always typed (TC-4, D-35). The login field's autofill hint is `Username` and reads nothing from the SIM. The existing controls stay unchanged: detekt `ForbiddenImport` (`TelephonyManager`, `WifiInfo`, `WifiManager`, advertising-identifier packages, `Settings.Secure`) on every commit; Lint `HardwareIds` fatal (`android/lint.xml`) on every commit; the merged-manifest allowlist and minified DEX scan on the release build (`android/release-gates.gradle.kts`). | Those existing gates in CI (`.github/workflows/check.yml`, job `android-unit`: detekt and `lintDebug` steps) and the release workflow. This unit adds no exemption to any of them. |
| NFR3.8 | **No new third-party dependency.** Debounce and timeouts use `kotlinx-coroutines`, tests use `kotlinx-coroutines-test` and `ktor-client-mock`, all already declared. If code generation finds a dependency unavoidable, it is checked against the forbidden-identifier set first and gets an admission note in `android/sdk-admissions/` (project Mandated). Its lockfile and checksum entries are regenerated, and CI's lockfile and verification checks fail without them. | `android/gradle.lockfile` under `dependencyLocking { lockAllConfigurations() }` and `gradle/verification-metadata.xml` with `verify-metadata` true. A new artifact missing from either fails dependency resolution in every Gradle step of CI. The admission note itself is checked by review. |

### Client checks are format-only and never stricter than the server (FR11.3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.9 | Username fields check only non-blank, and cap input so the **trimmed** value is at most 64 characters (the schema's `maxLength`). They apply none of FR1's rules (length 3–20, characters, first letter, dots, reserved). The login field checks only non-blank. | `UsernameField` cap tests (65 rejected, 64 accepted, 64 with surrounding spaces accepted, 21 accepted). Sign-in test: a login of any shape is sent. |
| NFR3.10 | Every email field uses the one shared `emailIsWellFormed`, aligned to the server's pattern `[^@\s]+@[^@\s]+\.[^@\s]+` (`app/accounts/identifier.py:50`). The two corners that diverge today, `a@b.c.` and `a@.b.c`, are accepted. | `emailIsWellFormed` tests pinning both corners, plus `a@b` and `@b.c` refused. **Limit:** the test pins the two known corners and does not compare the client function with the server regex mechanically. A future server change would be caught only by its own review. |
| NFR3.11 | The client never decides whether a contact may be removed, whether a rename is allowed now, or whether a username is required. Remove is offered for every present contact, Change is always offered, and the gate follows the server's flag (FR11.3). | Contacts mapper test: one present contact still yields a Remove action. Username screen test: Change is present without `next_change_at`. |

### The gate's security bounds (FR5.2, FR5.3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.12 | When the account read says `username_required: true`, nothing but the gate is composed until a choice succeeds or the person signs out. The flag and the lens state arrive in one `SessionUiState` write (`UsernameRequired(then)`), so no frame of the graph precedes the gate. | `SessionStateMapper` and `SessionViewModel` tests; the first-frame routing test (frontend-components § 8). |
| NFR3.13 | **Unknown flag, bounded.** When the account read fails, the app keeps its built behaviour: the lens-free graph. While the state is `Failed` it re-reads the account on each return to the foreground and every 30 s, and shows the gate as soon as a read says true. The window in which a username-less account uses the lens-free graph is therefore the server's unreachability plus at most 30 seconds. This is an ordering exposure, not an authorization one: the server refuses nothing for a missing username (FR5.3), so the window grants nothing the account does not already have. | `recheck` unit tests; the Robolectric re-check routing test under a virtual clock (performance NFR8.6). |
| NFR3.14 | "Sign out" on the gate runs the app's one `endSession`: queue, offline copies, workspaces and tokens are cleared, and the token family is revoked on the server, best effort. Nothing of the session survives on the gate's exit. | Routing test: gate Sign out → sign-in screen, with the token store fake cleared. |

### Test ordering (NFR4)

| ID | Requirement | Verifier |
|---|---|---|
| NFR4.1 | Team ordering predicate applied to this unit. No client change computes money, and every authorization decision (lens, username required, removal allowed) is the server's. So the predicate "a wrong answer would be a money or authorization error" holds for no client code here. The tests are test-after, written from the functional-design acceptance criteria. The one authorization-adjacent client behaviour, routing on the server's flag (NFR3.12–3.13), is tested from FR5.2's acceptance criterion. | The test list in frontend-components § 8; review checks each test was written from its criterion (team: test-after is not permission to test the implementation). |

## Not adopted, with reason

- **`FLAG_SECURE` on the rename, replace and remove screens.** The app sets it
  only on the two-step setup screen (`TwoStepScreen.kt`), which shows a
  recovery secret. Password fields elsewhere (sign-in, change password) do
  not set it, and these screens show no secret beyond a masked password
  field. They are kept consistent with the existing password screens.
- **Pinning or a custom TLS policy for the new calls.** The new calls use the
  same client and engine as every other request, and the HTTPS-only check in
  `ApiClient.build` is unchanged.

## Assumptions & Open Questions

- [assumption] The username is treated as personal data for logging and
  display (owner-private, FR9), but not as a credential. It is masked in
  `toString` and kept out of URLs, but it is not cleared from saved state,
  because a person's own half-typed name surviving rotation is the
  conventional behaviour and leaks nothing beyond the owner's device.
- Open questions: None.

## Sources

- Requirements: `inception/requirements-analysis/requirements.md` NFR1, NFR3,
  NFR4, FR4.1, FR4.3, FR5.2, FR5.3, FR9, FR11.3.
- Contract: `inception/contract-design/contract-summary.md` C1 (both lookups
  `POST` with a body), C2 (the already-added query).
- Functional design: `construction/android-identity/functional-design/functional-spec.md`
  W1–W8, § 7, § 9; `frontend-components.md` § 2, § 4, § 6, § 8.
- U1 reverse items: `construction/usernames-backend/nfr-requirements/traceability.json`.
- Code read: `android/detekt.yml` (active `ForbiddenImport` list; the
  no-type-resolution note), `android/lint.xml` (`HardwareIds` fatal),
  `android/src/main/AndroidManifest.xml` (`allowBackup="false"`,
  `dataExtractionRules`), `android/build.gradle.kts`
  (`dependencyLocking { lockAllConfigurations() }`),
  `gradle/verification-metadata.xml`, `core/network/ApiClient.kt`,
  `feature/mfa/ui/TwoStepScreen.kt` (`FLAG_SECURE`),
  `app/accounts/identifier.py:50`.
- Project rules: `project.md` Forbidden (device identifiers, `TelephonyManager`,
  no client business rule, obligations name their verifiers) and Mandated
  (dependency check against the forbidden set; forbidden set enforced at
  commit time).
- Answers: `nfr-requirements-questions.md` Q5 [Q5].
