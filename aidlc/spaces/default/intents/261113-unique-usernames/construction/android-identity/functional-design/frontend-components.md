# Frontend Components — U3 android-identity

The component design for the workflows and state machines in
`functional-spec.md` (W1–W10, § 3). Paths are under
`android/src/main/kotlin/com/shikkhokplus/app/`. This is a design, not code:
the shapes below are interface-level, and code generation writes the bodies.

Conventions kept from the built app (team.md, Android): feature packages with
a layer split; a ViewModel owns the coroutine and state holder only; a pure
`*StateMapper` object makes every decision and is the unit under test; a
composable renders a UiState with no conditional on a domain value; each
feature declares its repository interface and `core/network` implements it
with the three-way `AuthResult` (`Ok`, `Refused`, `TransportFailure`);
secrets live in `remember` or ViewModel memory, never in saved state.

## 1. Composable hierarchy

```text
MainActivity.AppRoot
├── FullScreenLoader                      (Restoring / Resolving, existing)
├── ChooseUsernameGate                    NEW (W4) — before LensPickerScreen
│   ├── UsernameField + AvailabilityHint  NEW shared (core/ui)
│   ├── PrimaryButton "Continue"
│   └── TextAction "Sign out"
├── LensPickerScreen                      existing
└── ShikkhokNavHost
    ├── AuthScreen                        changed
    │   ├── SignInStep                    changed: LoginField replaces toggle + IdentifierField (W3)
    │   ├── CodeRequestStep               unchanged (toggle kept, FR10.1)
    │   ├── CodeStep                      unchanged
    │   └── ReplaceUsernameStep           NEW (W2)
    ├── SignupScreen                      changed: UsernameField + AvailabilityHint above passwords (W1); email lookup (W9)
    ├── ProfileScreen (More)
    │   └── SignInRows                    changed: Username row, Phone and email row (W5, W6)
    ├── accountRoutes
    │   ├── PasswordChangeScreen          unchanged
    │   ├── AddContactScreen              unchanged (reached from Contacts)
    │   ├── UsernameScreen                NEW (W5)
    │   ├── ContactsScreen                NEW (W6)
    │   │   └── RemoveContactSheet        NEW (W6)
    │   └── ReplaceContactScreen          NEW (W6) — entry step + code step
    ├── AddStudentForm                    changed: two email fields (W7)
    ├── StudentDetailScreen               changed: contact lines; EditStudentDialog email fields (W7)
    ├── StudentsScreen                    changed: row subtitle from mapper (W7)
    ├── Roster rows                       changed: guardian email (W7)
    └── MembersScreen                     changed: email invite field; MemberCard contactLine (W8)
```

Shared new pieces in `core/ui`:

- `UsernameField(value, onValueChange, label, help, error, enabled, fieldModifier)`
  — single-line text field, text keyboard, no autocorrect or capitalisation,
  autofill hint `Username` on sign-up only (`NewUsername` is not a Compose
  autofill type; `Username` is what a password manager saves against).
- `AvailabilityHint(state: AvailabilityState)` — renders one line per state of
  functional-spec 3.1 with a text label (never colour alone), as a polite
  live region for TalkBack.
- `LoginField(value, onValueChange, error, enabled, fieldModifier)` — the
  sign-in field: text keyboard, autofill hint `Username`, label "Username,
  phone or email". Test tag stays `TAG_IDENTIFIER_FIELD` so the device-run
  scripts keep working.

## 2. UiState data classes

### 2.1 Availability (shared)

```kotlin
sealed interface AvailabilityState {
    data object Idle : AvailabilityState
    data object Checking : AvailabilityState
    data object Available : AvailabilityState
    data class Refused(val messageKey: String) : AvailabilityState  // unavailable / invalid(key) / reserved
    data object CouldNotCheck : AvailabilityState
}
```

`Waiting` from the state machine is not a separate UiState: it renders as
`Idle` (the help line), so the hint does not flicker while typing.

### 2.2 Auth (changed)

- `AuthUiState.ReplaceUsername(previous: String, checking: Boolean = false,
  messageKey: String? = null, retryable: Boolean = false)` — NEW. `previous`
  is the name the draft carried, for the body copy; it is the person's own
  typed value, not server data.
- `AuthUiState.Failed` unchanged; `IDENTIFIER_MESSAGE_KEYS` routing kept, with
  `email.invalid` now routed under the login field.

### 2.3 Sign-up (changed)

- `SignupForm` gains `username: String` (trimmed at submit; included in
  `toString`, since it is not a secret; the passwords stay masked).
- `SignupStateMapper.USERNAME_REQUIRED_KEY = "signup.username.required"`
  (client: blank only) added to `validate(form)`.
- `USERNAME_MESSAGE_KEYS: Set<String>` = the six format keys +
  `account.username.unavailable` + `signup.username.required`; a `Failed` or
  `Invalid` key in this set is rendered under the Username field.

### 2.4 Choose-username gate (new, `feature/account`)

```kotlin
sealed interface ChooseUsernameUiState {
    data class Editing(val saving: Boolean = false, val messageKey: String? = null,
                       val retryable: Boolean = false) : ChooseUsernameUiState
    data object Rereading : ChooseUsernameUiState
    data object Done : ChooseUsernameUiState
}
```

### 2.5 Username screen (new)

```kotlin
sealed interface UsernameUiState {
    data class Viewing(val username: String?, val nextChangeAt: String? = null) : UsernameUiState
    data class Editing(val current: String?, val saving: Boolean = false,
                       val usernameKey: String? = null, val passwordKey: String? = null,
                       val bannerKey: String? = null, val bannerDate: String? = null,
                       val offerSetPassword: Boolean = false, val retryable: Boolean = false) : UsernameUiState
    data class Changed(val username: String, val nextChangeAt: String?) : UsernameUiState
}
```

Which key goes to `usernameKey`, `passwordKey` or `bannerKey`, and whether
`offerSetPassword` is set, is decided in `UsernameStateMapper` from the
envelope's `message_key`; `bannerDate` is `details["next_change_at"]` as sent.

### 2.6 Contacts (new)

```kotlin
data class ContactCard(val kind: IdentifierKind, val value: String?)  // null = absent

sealed interface ContactsUiState {
    data object Loading : ContactsUiState
    data class Loaded(val phone: ContactCard, val email: ContactCard,
                      val passwordNote: Boolean, val removedKind: IdentifierKind? = null) : ContactsUiState
    data class Failed(val messageKey: String, val retryable: Boolean) : ContactsUiState
}

sealed interface ReplaceContactUiState {          // kind fixed for the screen
    val kind: IdentifierKind
    data class Entering(override val kind: IdentifierKind, val sending: Boolean = false,
                        val valueKey: String? = null, val passwordKey: String? = null,
                        val bannerKey: String? = null, val offerSetPassword: Boolean = false,
                        val retryable: Boolean = false) : ReplaceContactUiState
    data class AwaitingCode(override val kind: IdentifierKind, val checking: Boolean = false,
                            val messageKey: String? = null, val retryable: Boolean = false,
                            val attemptsLeft: String? = null) : ReplaceContactUiState
    data class Replaced(override val kind: IdentifierKind) : ReplaceContactUiState
}

sealed interface RemoveContactUiState {
    data class Confirming(val kind: IdentifierKind, val value: String, val removing: Boolean = false,
                          val passwordKey: String? = null, val bannerKey: String? = null,
                          val offerAddOther: Boolean = false, val offerSetPassword: Boolean = false,
                          val retryable: Boolean = false) : RemoveContactUiState
    data object Removed : RemoveContactUiState
}
```

`passwordNote` is `!MeDto.hasPassword` copied from the server; `offerAddOther`
is set by the mapper for `account.contact.last_one` only.

### 2.7 Students, roster, members (changed)

- `StudentDetail` gains `studentEmail: String?`, `guardianEmail: String?`, and
  two mapped display lines `studentContactLine: String?`,
  `guardianContactLine: String?` (phone, else email, both when both — W7.7).
- `StudentListRow` subtitle becomes the mapped `studentContactLine`.
- The roster row's UI model gains `guardianContactLine` from `RosterRowDto`.
- `NewStudent` gains `studentEmail: String?`, `guardianEmail: String?`.
- `MembersUiState` gains `inviteEmail: String = ""`,
  `inviteEmailRejected: Boolean = false`; `canInvite` becomes
  `!inviting && inviteName.isNotBlank() && (invitePhone.isNotBlank() || inviteEmail.isNotBlank())`.
- `MembersBody.Loaded` holds `List<MemberLine>` (a mapped
  `MemberLine(memberId, displayName, contactLine, role, decision, revoked, isYou)`)
  instead of raw `MemberDto`, so the card renders a line and decides nothing.

### 2.8 Session (changed)

`SessionViewModel` gains `usernameRequired: StateFlow<Boolean>` (false until
a read says otherwise, reset on `resolve`, set on every successful read in
`resolve` and `refreshLenses`) and `usernameChosen()` (sets it false, like
`passwordSet`). The profile summary (`ProfileSummary`) gains
`username: String?` for More's row.

## 3. ViewModel events

| ViewModel | Events (public functions) | Notes |
|---|---|---|
| `UsernameAvailabilityChecker` (NEW, plain class owned by a ViewModel, `core/ui` or `feature/account`) | `edited(text)`, `state: StateFlow<AvailabilityState>` | Takes the lookup function and the ViewModel's scope. Debounce 500 ms with a cancellable job, one in flight, latest-wins by comparing the answered text with the current one, an in-memory `Map<String, AvailabilityState>` cache. Mapping of the answer is `AvailabilityMapper.afterLookup(result)` — pure, tested. |
| `SignupViewModel` | existing + `usernameEdited(text)`, `emailLeft(email)` | Owns a checker on the public lookup; `submit(form)` now carries `form.username`; `emailLeft` mirrors `lookup(phone)` (once per value, Q4). |
| `AuthViewModel` | existing + `adoptPendingCode(identifier, password, username)`, `replacementEdited(text)`, `submitReplacement(username)` | Holds the verified code in memory between `CheckingCode` and the replacement retry; `submitCode` maps a 409 `account.username.unavailable` through `AuthStateMapper.afterVerifyRefused` to `ReplaceUsername`; `changeNumber`/`backToSignIn`/`onCleared` forget the held code with the other secrets. `signIn(login: String, password)` replaces `signIn(Identifier, password)`. |
| `ChooseUsernameViewModel` (NEW) | `edited(text)`, `submit(username)`, `retry()` | Authenticated checker; `submit` ignored while saving; on `password_required` calls the injected `reread` (the session's `refreshLenses`-style read that updates `usernameRequired`); on 200 calls `onChosen` (`SessionViewModel.usernameChosen`). |
| `UsernameViewModel` (NEW) | `startChange()`, `cancel()`, `edited(text)`, `save(username, password)` | Authenticated checker; password passes through, never stored; on 200 calls `onChanged` to re-read the profile. |
| `ContactsViewModel` (NEW) | `load()`, `retry()` | Reads `GET /v1/me` through the existing `ProfileRepository.profile()`; maps with `ContactsStateMapper.afterLoad`. |
| `ReplaceContactViewModel` (NEW) | `requestCode(value, password)`, `resendCode()`, `submitCode(code)`, `changeValue()` | Holds the pending identifier, drops the password after a 200 request; resend sends the same request again, which needs the password, so the password is held only until the first successful request and **Resend** after that re-asks for it via `changeValue()` (no password kept for a resend). |
| `RemoveContactViewModel` (NEW) | `remove(password)` | Ignored while removing; on 200 calls `onRemoved` (re-read Contacts, quiet lens re-read). |
| `StudentsViewModel` / `StudentDetailViewModel` | `create(…, studentEmail, guardianEmail)`, `edit(name, studentPhone, guardianPhone, studentEmail: EmailEdit, guardianEmail: EmailEdit)` | `EmailEdit` = `Unchanged` / `Set(value)` / `Clear` so "emptied" sends `null` (W7.5) while phones keep today's rule. |
| `CentreMembersViewModel` | existing + `inviteEmail(text)` | `invite()` sends the email when non-blank; shape-checks it first. |

Resend on the replace flow, precisely: the existing add flow resends with
`requestContact(identifier)`; a replacement request must carry the password
(C2), and keeping the password for a possible resend would hold a secret past
its use. So the replace code step's "Send a new code" returns to the entry
step with the new value kept and the password field empty. Recorded here
because it differs from Add.

## 4. Repository and DTO changes

### 4.1 DTOs (`core/network`)

| DTO | Change |
|---|---|
| `PasswordSignInRequest` | add `@SerialName("login") val login: String? = null`; `toString` masks the password as today and prints no login either (it may be a phone or email) |
| `VerifyRequest` | add `@SerialName("username") val username: String? = null` (sent only on a replacement; omitted when null by the client's JSON settings) |
| `SignupRequestDto` | add `val username: String` (required by `SignupRequest`) |
| `MeDto` | add `val username: String? = null`, `@SerialName("username_required") val usernameRequired: Boolean = false` (absent reads as not required) |
| NEW `UsernameAvailabilityRequest(username: String)` | body of both lookups |
| NEW `UsernameAvailabilityDto(status: String, @SerialName("message_key") messageKey: String? = null)` | `status` kept a string; an unknown status maps to `CouldNotCheck` |
| NEW `UsernameChangeRequest(username: String, password: String? = null)` | `toString` masks the password |
| NEW `UsernameChangeDto(username: String, @SerialName("next_change_at") nextChangeAt: String? = null)` | |
| `IssueRequest` | unchanged for Add; NEW `ContactChangeRequest(phone: String? = null, email: String? = null, password: String? = null)` for Replace, masked `toString` |
| NEW `ContactRemoveRequest(kind: String, password: String)` | `kind` is `phone` or `email`; masked `toString` |
| `TeacherStudentDto` | add `@SerialName("student_email") studentEmail: String? = null`, `@SerialName("guardian_email") guardianEmail: String? = null` |
| `StudentCreateBody` | add `student_email`, `guardian_email`, both `String? = null` (omitted when null) |
| `StudentUpdateBody` | add both, encoded so an explicit clear sends JSON `null` and "unchanged" omits the key (an `@EncodeDefault`-style wrapper or a custom serializer; the existing body relies on null-omission, which cannot express "clear") |
| `RosterRowDto` | add `student_email`, `guardian_email`, both `String? = null` |
| `MemberDto` | `phone: String? = null` (**was non-null, no default**), add `@SerialName("invited_email") invitedEmail: String? = null` |
| `MemberInviteDto` | `phone: String? = null`, add `email: String? = null` |
| `AlreadyAddedDto` | unchanged |

### 4.2 Repository interfaces (feature-declared)

- `AuthRepository.signIn(login: String, password: String)` (replaces the
  `Identifier` overload; the code flow keeps `issue(identifier)`).
- `AuthRepository.verify(identifier: Identifier, code: String, username: String? = null)`.
- `SignupRepository.lookup(phone: String)` kept; NEW
  `lookupEmail(email: String)`; NEW `checkUsername(username: String):
  AuthResult<UsernameAvailabilityDto>` (public lookup);
  `signup(…, username: String)`.
- `AccountRepository` NEW: `checkUsername(username)` (authenticated lookup),
  `changeUsername(username: String, password: String?): AuthResult<UsernameChangeDto>`,
  `replaceContact(identifier: Identifier, password: String): AuthResult<IssueResponse>`,
  `removeContact(kind: IdentifierKind, password: String): AuthResult<MeDto>`.
  `verifyContact` serves both add and replace (same route, C2).
- `CentresRepository.invite(displayName: String, phone: String?, email: String?, role: String)`.
- Students repository `create`/`rename` gain the email parameters (§ 3).

### 4.3 HTTP implementations

- `HttpAuthRepository.signIn` posts `PasswordSignInRequest(login = …)`;
  `verify` adds `username`.
- `HttpSignupRepository`: `checkUsername` → `POST /v1/accounts/username-availability`;
  `lookupEmail` → `GET /v1/accounts/already-added?email=` (a query parameter,
  as the contract defines; the email is the person's own, typed by them);
  `signup` adds `username`.
- `HttpAccountRepository`: `checkUsername` → `POST /v1/me/username-availability`;
  `changeUsername` → `PUT /v1/me/username`; `replaceContact` →
  `POST /v1/me/contact` with password; `removeContact` →
  `POST /v1/me/contact/remove`. A username change ends no session and returns
  no tokens, so nothing is written to the token store.
- `HttpCentresRepository.invite` sends the new body.
- Every new call uses the existing `call { … }` helper, so the three-way
  result and the envelope decoding are unchanged.

## 5. Navigation changes

- `MainActivity.AppRoot`: after the `Resolving` branch and before the
  `Choosing` branch, `if (signedIn && usernameRequired) { ChooseUsernameGate(…); return }`.
  The gate's ViewModel is created with the authenticated client and the
  session callbacks; "Sign out" calls the same `endSession` lambda More uses.
- `Destination`: NEW `Username` (`me/username`), `Contacts` (`me/contacts`),
  `ReplaceContact` (`me/contacts/replace?kind={phone|email}`). The existing
  `AddContact` stays and is navigated to from Contacts.
- `accountRoutes`: registers the three new destinations; Replace and Remove
  completion call `session.onLensesChanged()` (quiet) and pop back to
  Contacts, which re-reads.
- `accountRowsFor` → returns `onUsername`, `username`, `onContacts`,
  `contactsLine` instead of `onAddPhone`/`onAddEmail`; More's `SignInRows`
  renders a Username row and a Phone and email row. `AccountRowsTest` is
  updated to the new rows (a test asserting the old rows is a test of the old
  design, rewritten from the new acceptance criterion, not deleted silently).
- The Auth destination's `AuthActions.onSignIn` type becomes
  `(String, String) -> Unit`; the Signup destination passes
  `model::usernameEdited`, `model::emailLeft`, and hands the username to
  `authModel.adoptPendingCode` with the identifier and password.

## 6. Form validation rules (client, format only)

| Field | Client check | Never checked on the client |
|---|---|---|
| Sign-up username, replacement, gate, rename | non-blank | length, characters, first letter, dots, reserved, availability (server, FR1, FR11.3) |
| Sign-in login | non-blank | which kind it is; any shape (server classifies, FR4.1) |
| Email (sign-up, add, replace, student, guardian, invite) | `emailIsWellFormed`, aligned to the server's `[^@\s]+@[^@\s]+\.[^@\s]+` (Q5) | whether it is taken or recorded |
| Phone (add, replace, invite, student) | existing `identifierIsWellFormed` / `PhoneNumberField` behaviour | unchanged |
| Current password (rename, replace, remove) | non-empty | correctness, ceilings |
| Invite | name non-blank and phone or email non-blank | the at-least-one rule's enforcement (server 422) |

## 7. String resources

Added to `values/strings.xml` and `values-bn/strings.xml` together. Names
follow the existing snake_case-by-feature pattern.

- **Message keys (15)**: `account_username_too_short`,
  `account_username_too_long`, `account_username_invalid_character`,
  `account_username_must_start_with_letter`, `account_username_bad_dot`,
  `account_username_reserved`, `account_username_unavailable`,
  `account_username_change_too_soon` (plain) and
  `account_username_change_too_soon_on` (with `%1$s` date),
  `account_username_password_required`, `account_contact_password_required`,
  `account_contact_last_one`, `account_contact_change_limit`,
  `account_contact_admin_locked`, `auth_lookup_too_many`,
  `student_email_taken`; each mapped in `MessageKeys`.
- **Client-only key**: `signup.username.required` → `signup_username_required`.
- **Sign-in**: `auth_login_label`.
- **Availability**: `username_checking`, `username_available`,
  `username_could_not_check`.
- **Sign-up**: `signup_username_label`, `signup_username_help`.
- **Replacement**: `auth_replace_username_title`,
  `auth_replace_username_body` (`%1$s` previous name),
  `auth_replace_username_continue`.
- **Gate**: `choose_username_title`, `choose_username_body`,
  `choose_username_continue`, `choose_username_sign_out`.
- **More**: `more_username`, `more_username_choose`, `more_contacts`,
  `more_contacts_sub_none`.
- **Username screen**: `username_title`, `username_current_label`,
  `username_change`, `username_new_label`, `username_rule_note`,
  `username_changed_on` (`%1$s`), `username_changed`, `username_save`.
- **Contacts**: `contacts_title`, `contacts_phone`, `contacts_email`,
  `contacts_no_phone`, `contacts_no_email`, `contacts_replace`,
  `contacts_remove`, `contacts_password_note`, `contacts_set_password`,
  `contacts_replace_phone_title`, `contacts_replace_email_title`,
  `contacts_new_phone_label`, `contacts_new_email_label`,
  `contacts_code_sent_new_phone`, `contacts_code_sent_new_email`,
  `contacts_replaced_phone`, `contacts_replaced_email`,
  `contacts_remove_title`, `contacts_remove_body` (`%1$s` value),
  `contacts_remove_confirm`, `contacts_removed`, `contacts_add_other`.
- **Students**: `student_add_student_email`, `student_add_guardian_email`,
  `student_detail_guardian_email` (if the guardian line needs its own
  pattern).
- **Centre**: `centre_invite_email_label`, `centre_invite_by_help`.
- **Reworded, same names**: `student_number_accepted`,
  `student_number_erased`, `centre_member_already_invited`.

The count of new strings is whatever the list above comes to when written;
the bundles are asserted equal by the existing build check, and no comment or
doc states the count (project: NEVER let a comment state a count nothing
checks).

## 8. Test obligations per ViewModel and mapper

Methodology (team.md Testing Posture): the ordering predicate decides
test-first. It holds for nothing here that is a money error, and for one
authorization-adjacent case: **the gate must not be passable without a
choice** — but that decision is the server's flag and the gate's rendering;
the client test pins that `AppRoot` routes on the flag (below), written
test-after from FR5.2's acceptance criterion. Everything else is test-after,
written from the acceptance criteria, against the mapping functions (JUnit;
Turbine where a flow is observed). Every ViewModel covers loading, success,
error and the explicit retry path of a failed write (TC-8, D-9).

| Unit under test | Obligations (each a named test) |
|---|---|
| `AvailabilityMapper` | each of `available`, `unavailable`, `invalid` with each format key, `reserved` → its state; `invalid` without a key → `CouldNotCheck`; unknown status → `CouldNotCheck`; 429 → `CouldNotCheck`; transport → `CouldNotCheck` |
| `UsernameAvailabilityChecker` (virtual time) | no call before 500 ms of quiet; one call after; edits inside the window restart it; an answer for stale text is dropped (older response arrives last); a remembered text makes no second call; empty text makes no call; no state disables submission (asserted on the form's enabled flag) |
| `SignupStateMapper` / `SignupViewModel` | blank username → `signup.username.required`; each `account.username.*` refusal and the 409 route under the Username field and keep the form; success hands over identifier, password and username; transport → retry resends the same form including the username; `emailLeft` once per value; email lookup locks the role |
| `AuthStateMapper` / `AuthViewModel` | sign-in sends `login` only (repository fake asserts the call); `email.invalid` routes under the field; 409 `account.username.unavailable` at verify → `ReplaceUsername` and the code is retained; replacement 200 → same continuation as a first-time verify (password sent from memory); replacement refusal and 429 stay on `ReplaceUsername`; `auth.otp.expired` from a replacement → `CodeRejected`; transport → Retry resends code + username; `changeNumber` forgets the held code (a later `submitReplacement` sends nothing) |
| `ChooseUsernameViewModel` | 200 → `Done` and `onChosen` called; format and unavailable refusals → `Editing` with the key; `password_required` → `Rereading` then `Done` when the read says false; failed re-read → `Editing` retryable; 503 and transport → retry resends the same username; double submit ignored |
| `AppRoot` routing (Robolectric, the existing `navigation` test style) | signed in + `usernameRequired` → gate shown, home/More/lens picker not composed; gate has no back arrow; after `usernameChosen` → lens picker or home; Sign out → sign-in |
| `UsernameStateMapper` / `UsernameViewModel` | 200 with and without `next_change_at`; `change_too_soon` with date → banner with the date, without → plain; `password_required` → `offerSetPassword`; `current_wrong` → password field; `unavailable` → username field; 503/transport → retry resends; the password is not retained after success (repository fake receives it once) |
| `ContactsStateMapper` / `ContactsViewModel` | both present; phone only; email only; `has_password` false → note; load failure → retry re-reads |
| `ReplaceContactViewModel` | request with password; each request refusal routed (`password_required`, `current_wrong`, `already_set`, `admin_locked`, `change_limit`); 200 → code step and password dropped; verify `taken`/`change_limit` stay on the code step; wrong code shows tries left; 200 → `Replaced`; Resend returns to entry with the value kept and password empty; transport retry |
| `RemoveContactViewModel` | 200 → `Removed`; `last_one` → `offerAddOther`; `current_wrong` → password field; `password_required` → `offerSetPassword`; transport retry resends the same `{kind, password}` |
| Students mappers / ViewModels | create sends both emails, omits blanks; `student.email.taken` under Student email; edit: unchanged omits, changed sends, emptied sends JSON `null` (serializer test asserting the encoded body); contact line: phone, email-only, both, neither |
| Roster mapper | guardian email shown when no guardian phone |
| Centres | `MemberDto` decodes `"phone": null` with an `invited_email` (the regression for § 1 defect 1, a decode test on a JSON string); `contactLine` phone vs email; `canInvite` with phone only, email only, neither; invite body omits blanks |
| `emailIsWellFormed` | `a@b.c.` and `a@.b.c` accepted (server pattern), `a@b` and `@b.c` refused, whitespace refused — the two corners from Q5 pinned |
| `MessageKeyCoverageTest` | unchanged; passes once the 15 keys map |
| DTO serialization | `PasswordSignInRequest`, `ContactRemoveRequest`, `UsernameChangeRequest`, `ContactChangeRequest` `toString` print no password; `VerifyRequest` omits `username` when null; `MeDto` without `username_required` reads `false` |

Compose UI tests are added only for the gate (it is a new root screen) and
follow the existing Robolectric screen tests; the Bangla layout obligation is
**not** discharged by any of these (functional-spec § 8). The Kotlin coverage
ratchet (`coverage.gradle.kts`) must not decrease.

## 9. Dependencies

None new. Debounce uses `kotlinx.coroutines` (`delay` and a cancellable job),
already on the classpath; tests use `kotlinx-coroutines-test` virtual time,
already used by the attendance tests. No SDK admission note is due.
