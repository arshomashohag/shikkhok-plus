# Frontend Components — U4 web-identity

The component, state, API, routing and test design for the workflows in
`functional-spec.md` (W1–W10). Shapes are written at interface level; bodies
belong to code generation. Paths are under `web/src/`. React 19, React Router
7, Vite and Vitest with Testing Library, as built. Mirrors U3's
`frontend-components.md`; § 9 of the functional spec lists the deliberate
differences.

## 1. Component hierarchy

```text
main.tsx
└─ SessionProvider                     (changed: 'username-required' state, visibility re-read)
   └─ App                              (changed)
      ├─ RootErrorBoundary             (new, functional-spec § 10 item 2)
      ├─ signed-out routes
      │  ├─ SignIn                     (changed: LoginField, no KindToggle, no route state)
      │  ├─ SignUp                     (changed: UsernameField + hint, email already-added lookup)
      │  │  └─ code step → CodeEntry → ReplaceUsernameStep (new, shared)
      │  └─ PasswordCode               (changed: no entry state; CodeEntry → ReplaceUsernameStep)
      ├─ 'resolving' loader            (unchanged)
      ├─ 'failed' ErrorCard            (unchanged: fail-closed)
      ├─ ChooseUsernameGate            (new; returned before LensPicker and Routes)
      ├─ LensPicker                    (unchanged)
      └─ Routes → AppShell
         ├─ Settings → AccountEntries  (changed: Username row, Phone and email row)
         ├─ /settings/username         UsernameScreen      (new)
         ├─ /settings/contacts         ContactsScreen      (new) ─ RemoveContactSheet (new)
         ├─ /settings/contact/:kind    AddContact          (unchanged route; returns to Contacts)
         ├─ /settings/contact/:kind/replace  ReplaceContact (new)
         ├─ people: NewStudent (emails), StudentDetail ─ EditStudentSheet (new), StudentsList
         ├─ students: StudentsTab (guardian email), AddStudent (link to New student)
         └─ centre: Members (email invite, contactLine)

shared (features/auth/username/):
   UsernameField  ·  AvailabilityHint  ·  useUsernameAvailability (the checker)
```

## 2. State types

### 2.1 Availability (shared)

```text
type Availability =
  | { kind: 'idle' }
  | { kind: 'waiting' }
  | { kind: 'checking' }
  | { kind: 'answered'; status: 'available' | 'unavailable' | 'invalid' | 'reserved';
      messageKey: string | null }
  | { kind: 'could-not-check' }
  | { kind: 'stopped' }                // after a 429; renders as could-not-check
```

`mapAvailability(response) → Availability` is a pure function. No state tells
held from taken, because the server never says (U3 NFR1.3).

### 2.2 The checker: `useUsernameAvailability(lookup)`

- Input: `lookup(username, signal) → Promise<UsernameAvailabilityResponse>`.
  The public or authenticated endpoint is chosen by the screen.
- Output: `{ state: Availability, edited(text: string): void }`.
- Internals:
  - a 500 ms debounce timer;
  - one `AbortController` for the request in flight;
  - a per-text answer `Map` that lives as long as the component is mounted;
  - a `stopped` flag set on a 429;
  - a 3 s timer that aborts and marks `timedOut`.
- Superseding sets `superseded` before calling `abort()`.
- The settle step checks, in order:
  1. this request is still the current one, else drop;
  2. `timedOut` → could-not-check;
  3. `superseded` → drop;
  4. 200 for the current trimmed text → answered;
  5. 429 → stopped;
  6. otherwise → could-not-check.
- The error's type is never consulted to tell an abort from a failure
  (functional-spec Q1 and § 9 item 6).
- Unmounting aborts and clears both timers.

### 2.3 Session (changed, `session/session.tsx`)

```text
type Session =
  | { state: 'signed-out' } | { state: 'resolving' }
  | { state: 'failed'; error: ApiError }
  | { state: 'username-required'; me: Me }                   // new
  | { state: 'ready'; me: Me; options; lens; choosing; workspace }   // unchanged

sessionFromMe(me: Me, remembered: Lens | null, workspaces): Session   // new, pure, exported
```

- `sessionFromMe` returns `username-required` when
  `me.username_required === true`, else the `ready` value the provider
  builds today. It is the session's state machine for the gate, and it is
  tested like `resolveLens`.
- The resolve effect's interim publication changes. Today it keeps `ready`
  and otherwise publishes `resolving`. It must keep `ready` **and**
  `username-required`.
- New effect: while the state is `username-required`, a `visibilitychange`
  to `visible` calls `refresh()` (W4 step 8).
- `useReadySession()` keeps throwing outside `ready`. The gate is rendered
  outside every screen that calls it.

### 2.4 Choose-username gate (`features/account/username/ChooseUsernameGate.tsx`)

```text
type GateState =
  | { step: 'editing'; error: string | null; field: 'username' | null; retry: 'save' | 'reread' | null }
  | { step: 'saving' }
  | { step: 'rereading' }
```

- Props: `{ me: Me }`. Callbacks come from `useSession()`: `refresh` and
  `signOut`.
- Lift: the gate does not lift itself. It calls `refresh()` and waits. The
  provider replaces it with `ready` when the read says false. If the read
  says true again, the provider publishes a new `username-required` value
  whose `me` differs, and the gate returns to `editing` with
  `retry: 'reread'`.

### 2.5 Username screen (`features/account/username/UsernameScreen.tsx`)

```text
type UsernameState =
  | { step: 'viewing'; notice: string | null }
  | { step: 'editing'; error: string | null; field: 'username' | 'password' | null; retryable: boolean }
  | { step: 'saving' }
```

The notice is built with `formatDateTime(next_change_at, lang)`. The password
is a separate `useState` and is cleared on every answer.

### 2.6 Contacts (`features/account/contacts/*`)

```text
type ContactCard = { kind: 'phone' | 'email'; contact: string | null }  // shown value or absent
contactCards(me: Me): [ContactCard, ContactCard]   // pure: phone first; formatPhone applied here
```

Remove is offered for every present card; nothing reads a count (U3 NFR3.11).

- `ReplaceContact`:
  - states: `entering → sending → awaiting-code → checking → replaced`;
  - the password is dropped once the code request succeeds;
  - the code step is `CodeEntry`.
- `RemoveContactSheet`:
  - states: `confirming → removing → removed`;
  - it is keyed per opening, so reopening it never shows the last sheet's
    finished state (U3 deviation 10).

### 2.7 Students, roster, members

- `people/mappers.ts` `Student` gains `studentEmail` and `guardianEmail`, and
  two pure line functions: `studentContactLine(s)` and
  `guardianContactLine(s)` (functional-spec W7 step 7).
- New `studentEdit(original, typed) → StudentUpdateRequest | null`. It is
  pure. It returns `null` when nothing changed, and it emits explicit `null`
  only for an emptied email.
- `students/mappers.ts` `Seat` gains `guardianEmail`. The declined label
  uses the phone, then the email, then `roster_declined_no_number`.
- `centre/Members.tsx`:
  - `inviteBody(name, phone, email, role)` returns `null` unless the name is
    non-blank, at least one contact is non-blank, and each non-blank value
    is well-formed;
  - new `contactLine(m)` returns `formatPhone(m.phone)` when it is non-null,
    else `m.invited_email`, else `null`.

## 3. Events

| Screen | Events |
|---|---|
| Sign-in | `typed(login)`, `typedPassword`, `submit` |
| Sign-up | existing, plus `typedUsername` (feeds `edited`), `identifierLeft` (now also for email) |
| Replace step | `typedUsername`, `continue`, `back`, `retry` |
| Gate | `typedUsername`, `continue`, `signOut`, `retry` (save or re-read) |
| Username screen | `change`, `cancel`, `typedUsername`, `typedPassword`, `save`, `retry` |
| Contacts | `add(kind)`, `replace(kind)`, `remove(kind)` |
| Replace contact | `typedValue`, `typedPassword`, `sendCode`, code events, `change` |
| Remove sheet | `typedPassword`, `confirm`, `cancel`, `retry` |
| Edit student | `typed(field)`, `save`, `cancel`, `retry` |
| Members invite | `typed(name, phone, email, role)`, `invite` |

## 4. API functions (`api/endpoints.ts` and feature `api.ts`)

All are typed from the regenerated `schema.d.ts`. Every value below goes in a
JSON body, except U2's already-added query.

| Function | Request | Note |
|---|---|---|
| `signInWithPassword(login, password)` | `POST /v1/auth/password` `{login, password}` | replaces the identifier form; no `phone`/`email` key |
| `signUp(body)` | `POST /v1/accounts` | `SignupRequest` now requires `username` |
| `verifyCode(identifier, code, username?)` | `POST /v1/auth/verify` | `username` only on the Replace retry |
| `checkUsername(username, signal)` | `POST /v1/accounts/username-availability` | anonymous |
| `checkMyUsername(username, signal)` | `POST /v1/me/username-availability` | authenticated |
| `setMyUsername(username, password \| null)` | `PUT /v1/me/username` | `password` omitted for the first choice |
| `requestContactCode(identifier, password?)` | `POST /v1/me/contact` | with `password` it is a replacement (C2) |
| `removeContact(kind, password)` | `POST /v1/me/contact/remove` | returns `Me` |
| `lookupAlreadyAdded(identifier)` | `GET /v1/accounts/already-added?phone=` or `?email=` | U2's query shape, unchanged |
| `createStudent` / `updateStudent` | existing | bodies gain `student_email`, `guardian_email` |
| `inviteMember` | existing | body: `phone` and/or `email` |

`client.ts` `send()` changes one line: in its `catch`, it rethrows when
`options.signal?.aborted` is true, before mapping to `networkError()`
(functional-spec § 9 item 6). `renew()` is unchanged.

## 5. Routing and `App` changes

- `App`: after the `failed` branch, `if (session.state === 'username-required')
  return <ChooseUsernameGate me={session.me} />`, before `session.choosing`.
- `RootErrorBoundary`, a class component (React has no hook form), wraps the
  routed content. It renders `ErrorCard` with `error_unexpected` and a
  reload action. It logs nothing that came from data: it does not log the
  error, it only renders. It is one component, added because of
  functional-spec § 10 item 2.
- `securityPaths` gains `username()` → `/settings/username`, `contacts()` →
  `/settings/contacts` and `replaceContact(kind)` →
  `/settings/contact/${kind}/replace`. `securityRoutes` registers the three
  lazily, as the existing screens are. `AddContact` navigates back to
  `contacts()`.
- `SignIn` and `PasswordCode`: the `CodeFlowEntry` type, the `state` prop on
  the three links, and the `useLocation().state` read are removed.

## 6. Form validation rules (client, format only)

| Field | Client rule | Never applied on the client |
|---|---|---|
| Username (sign-up, Replace, gate, rename) | non-blank to submit; trimmed value capped at 64 code points, not while composing | FR1 length 3–20, characters, first letter, dots, reserved, taken, held |
| Login (sign-in) | non-blank; trimmed before sending | any shape or classification |
| Any email (sign-up, sign-in none, add or replace, student forms, invite) | `readIdentifier('email', …)`: trim, lowercase, server pattern, at most 254 **code points** | deliverability, uniqueness |
| Any phone | `normalisePhone`, unchanged | — |
| Invite contacts | at least one of phone or email non-blank | whether the person may be invited |
| Passwords (rename, replace, remove) | non-blank | correctness, which is the server's |

## 7. Strings

- **Regenerated** (`npm run gen:strings`): every string U3 added, including
  `auth_login_label`, `signup_username_*`, `username_*`, `choose_username_*`,
  `auth_replace_username_*`, `contacts_*`, `more_username*`, `more_contacts*`,
  `student_add_*_email`, `student_email_taken`, `centre_invite_email_label`,
  `centre_invite_by_help`, and every `account_username_*`,
  `account_contact_*` and `auth_lookup_too_many` message string.
- **New web-only strings** (`web_` prefix; English and Bangla together):
  - `web_auth_replace_username_body_plain`: the Replace body without the
    `{1}` name, for the code flow (functional-spec W2 step 3);
  - `web_students_add_by_email` (`students.*.json`);
  - `web_student_edit_title`, `web_student_edit_save`,
    `web_student_edit_saved` (`students.*.json`);
  - `web_root_error_reload`, for the boundary (`core.*.json`).
- **Reworded web-only strings**: `web_auth_signin_body`,
  `web_auth_signup_phone_help`, `web_students_no_phone`,
  `web_students_col_phone` (functional-spec § 5).

## 8. Test obligations

Vitest with Testing Library, in each feature's existing test file, or a new
one beside it. The tests are test-after, written from the functional-spec
acceptance steps. No client code here decides money or authorization; every
decision tested is the server's, rendered (team Testing Posture predicate,
as in U3 NFR4.1). Each obligation below is a named test. No web coverage
figure exists, and none is claimed (functional-spec § 10 item 5).

**Availability checker** (`useUsernameAvailability.test.ts`, fake timers):

- no request before 500 ms of quiet; one after it; the timer restarts on
  each edit; nothing for empty text;
- an edit while a request is in flight aborts it, and the aborted answer
  never renders;
- a stale answer is dropped;
- a remembered text sends nothing;
- a request with no answer after 3 s becomes could-not-check, and not
  before;
- after a 429 no further request is sent, even after edits;
- a transport failure gives could-not-check, and the next edit checks
  again.

**Fetch layer** (`api/client.test.ts`):

- a caller aborted while `request()` awaits renewal still leaves the
  rotated pair in storage (defect 5);
- `send()` rethrows an abort with a reason, and an abort from
  `AbortSignal.timeout()`, rather than returning `error.network.unreachable`;
- each new write's method, path and body is asserted, with **no query
  string** on both lookups, `PUT /v1/me/username`, `POST /v1/auth/password`,
  `POST /v1/me/contact` and `POST /v1/me/contact/remove`.

**Session and gate** (`session/session.test.ts`, `ChooseUsernameGate.test.tsx`):

- `sessionFromMe`:
  - `true` gives `username-required`;
  - `false` gives `ready`;
  - an absent flag gives `ready`.
- First render after resolving with `true` is the gate. The lens picker, the
  shell and every route's content never render. This is asserted on a typed
  URL such as `/settings`, and again after `history.back()`.
- On a 200 the gate re-reads, and lifts only when the read says false. A
  read that still says true returns it to editing with a re-read Retry.
- `password_required` re-reads with no password asked.
- A failed re-read shows the session's error card, not the app.
- `visibilitychange` to visible re-reads while the gate shows, and does
  nothing otherwise.
- Sign out clears tokens and calls the logout route.
- A refresh while the gate shows never renders the resolving loader.

**Sign-in and sign-up** (`SignIn.test.tsx`, `SignUp.test.tsx`, `PasswordCode.test.tsx`):

- Sign-in sends `login` for a username, a phone and an email typed as-is.
- `auth.password.wrong` renders exactly as before.
- No route state is passed to `/signin/code`.
- Sign-up sends `username`.
- Each `account.username.*` refusal lands under Username, with other fields
  kept.
- Submission works while the hint says unavailable or could-not-check.
- A 409 on verify opens Replace. The retry sends the same code with the
  replacement. An OTP refusal on the retry returns to the code step.
- Back forgets the code.
- The same Replace path is tested from the code flow.
- The email already-added lookup runs once per value, and locks the role on
  a seat.
- Autofill: the real username field carries `autocomplete="username"`, and
  the phone or email field no longer does.

**Username, contacts** (`username.test.tsx`, `contacts.test.tsx`):

- rename: each outcome in W5 step 5 renders as specified;
- the date comes from `next_change_at` or `details.next_change_at`, and a
  missing detail shows the plain string;
- Change is always present;
- `contactCards`: one present contact still yields Remove;
- `has_password: false` shows the note, and the actions stay enabled;
- Replace drops the password after the code request;
- Remove `last_one` shows in the sheet with Add another;
- reopening the sheet starts fresh.

**Students and members** (`people.test.tsx`, `students.test.tsx`, `Members.test.ts`, `centre.screens.test.tsx`):

- `studentEdit`:
  - an unchanged form gives `null`;
  - an emptied email gives `null` in the body;
  - an emptied phone is omitted.
- The line functions prefer phone, then email.
- `mapSeats` reads `guardian_email`.
- `inviteBody`:
  - email only → sent;
  - neither → `null`;
  - a malformed email → `null`.
- `contactLine` with a null phone.
- **A members list containing a `phone: null` member renders**, without
  throwing (defect 2).

**Email check** (`identifier.test.ts`):

- `a@b.c.` and `a@.b.c` accepted;
- `a@b` and `@b.c` refused;
- an address of 254 code points made of astral characters accepted, and one
  of 255 refused (defect 4).

**Privacy and strings**:

- The existing `server message keys` test passes after regeneration. That is
  the web's `MessageKeyCoverageTest`.
- Bundle parity covers the new web strings.
- A source-scan test asserts that no file under `src/` other than
  `api/endpoints.ts` and the username, sign-in and sign-up modules sends a
  `username` or `login` key. It is written in the style of the existing
  `check-bundles.mjs` "absent and present" pairs, so an empty scan fails.

**Root boundary**: a child that throws during render shows the boundary's
card, not a blank root.

**Manual, not automated**: the Bangla layout rows (functional-spec § 8).
Nothing above discharges them.

## 9. Dependencies

None added. The debounce, `AbortController`, timers and `visibilitychange`
are platform APIs. The tests use the installed `vitest`, `jsdom` and Testing
Library. `package-lock.json` is unchanged, which `npm ci` in `make web`
enforces.

## Assumptions & Open Questions

- [assumption] The new modules sit in `features/auth/username/`,
  `features/account/username/` and `features/account/contacts/`, the web's
  feature-folder pattern. The exact file names are code generation's.
- [assumption] The source-scan test for `username` and `login` keys is
  textual, like the bundle checks, and can be defeated by deliberate string
  building. The no-query-string assertions in the fetch tests are its
  behavioural half.
- Open questions: None.

## Sources

- `functional-spec.md` W1–W10, §§ 3–10 (this unit).
- U3: `construction/android-identity/functional-design/frontend-components.md`
  §§ 1–9, `nfr-requirements/{security,performance}-requirements.md`,
  `code-generation/code-summary.md`.
- Contracts: `inception/contract-design/contract-summary.md` C1 and C2;
  `openapi.json`.
- Code read: as listed in `functional-spec.md` § Sources, in particular
  `web/src/session/session.tsx`, `web/src/App.tsx`, `web/src/api/client.ts`,
  `web/src/api/tokens.ts`, `web/src/features/auth/parts.tsx`,
  `web/src/features/account/security/*`,
  `web/src/features/teacher/{people,students,centre}/*`,
  `web/src/i18n/i18n.tsx`, `web/scripts/check-bundles.mjs`.
- Answers: `functional-design-questions.md` Q1–Q6.
