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
      ├─ RouteErrorBoundary            (new, resets on pathname change; functional-spec § 10 item 2)
      ├─ signed-out routes
      │  ├─ SignIn                     (changed: LoginField, no KindToggle, no route state)
      │  ├─ SignUp                     (changed: UsernameField + hint, email already-added lookup;
      │  │  │                           owns step 'code' | 'replace', heldCode ref, sentAt)
      │  │  ├─ CodeEntry               (changed: initialError, resendAvailableAt)   ┐ siblings: the owner
      │  │  └─ ReplaceUsernameStep     (new, shared)                                ┘ renders one or the other
      │  └─ PasswordCode               (changed: no entry state; same owner pattern, same two siblings)
      ├─ 'resolving' loader            (unchanged)
      ├─ 'failed' ErrorCard            (unchanged card, fail-closed) + Sign out button (new)
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

### 2.2a The code step seam (changed `CodeEntry`, new `ReplaceUsernameStep`; review R-02)

```text
CodeEntry props (changed):
  verify: (code) => Promise<void>        unchanged; resolving keeps it busy (the owner moves on)
  resend: () => Promise<void>            unchanged; the owner records a new sentAt on success
  initialError?: string | null           new: shown on mount
  resendAvailableAt?: number             new: epoch ms; countdown = max(0, ceil((at - now) / 1000));
                                         default now + RESEND_AFTER_S * 1000, today's behaviour
ReplaceUsernameStep props:
  name: string | null                    the W1 name, or null in the code flow (plain body)
  submit: (username) => Promise<void>    owner calls verifyCode(identifier, heldCode, username)
  onBack: () => void
```

- **The owner** is `SignUp` or `PasswordCode`. It holds the step
  (`code | replace`), `heldCode` (a `useRef<string | null>`) and `sentAt`.
- On a 409 `account.username.unavailable`, the owner's `verify` sets
  `heldCode`, switches the step to `replace` and resolves.
- On an OTP refusal from `submit`, the owner clears `heldCode`, switches to
  `code` with a new `round` key (a remount), and passes:
  - `initialError = message(key)`;
  - `resendAvailableAt = sentAt + RESEND_AFTER_S * 1000`.
- Every other refusal is thrown back to `ReplaceUsernameStep`, which renders
  it under its field or in its banner.

**Remedy adjusted.** The review proposed starting with Resend available
whenever the refusal is an expiry. The adjustment keeps the original send's
pacing instead. After a Replace round the minute has almost always passed,
so Resend is available at once in the case the finding describes. The
adjustment also never offers an earlier resend than the existing step would.

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
- New `reread(): Promise<void>`. It starts the same read as `refresh()` and
  settles when that read settles, whatever it published. A read the
  provider supersedes with a newer one does not strand its caller:
  `reread()` resolves with the newest read's settlement, so every pending
  `reread()` settles when the latest read does (review 2, minor). A test
  starts a `reread()`, starts a `refresh()` before it answers, and asserts
  the first `reread()` settles. `refresh()` is kept
  for its existing callers. The gate uses `reread()`, so it never infers a
  read's completion from a changed `me` object (review R-05).
- The visibility re-read (W4 step 8) lives in the gate, not the provider,
  and is attached only while the gate is in Editing.
- New `signOut` use: `App`'s `failed` branch renders a Sign out button
  (`more_log_out`) under `ErrorCard` (W4 step 10).
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
- The step is `saving`, then `rereading`, then the gate awaits `reread()`:
  - if the provider published `ready`, the gate is already unmounted and
    nothing remains to do;
  - if the gate is still mounted, the read said true, and the gate returns
    to `editing` with `retry: 'reread'`;
  - if the read failed, the provider published `failed` and the gate is
    unmounted.
- **A changed `me` prop is ignored in every step but `rereading`.** In
  particular, a visibility read started in Editing that lands while
  `saving` changes nothing. The gate waits for the `PUT`'s answer (W4 step
  9).

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
  pure. It returns `null` when nothing changed, and it emits an explicit
  `null` for any emptied contact, phone or email. That clears it, as
  `StudentUpdateRequest` documents (review R-04).
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
- `RouteErrorBoundary` is a class component (React has no hook form). It
  wraps everything `App` returns. It is **not** keyed on the path, since a
  key would remount the whole shell on every navigation (review 2, minor).
  Instead it records the pathname at the time of the error and clears its
  error state when `location.pathname` differs (`componentDidUpdate` on a
  `pathname` prop), so navigating away recovers without remounting
  anything that did not fail. A test renders a throwing route, navigates
  to another, and asserts the other renders and the shell was not
  remounted. On a
  render error it shows `ErrorCard` with
  `new ApiError(500, 'UNEXPECTED', UNEXPECTED_KEY, true)`, which renders
  `error_unexpected` and `auth_retry`. Retry clears the boundary's error
  state and renders the children again. It does not log the error; it only
  renders. No new string is needed (review R-06).
- `App`'s `failed` branch: `ErrorCard` as today, then a text button
  `more_log_out` calling `signOut()`.
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
- **Reworded and removed web-only strings**: the swept list in
  functional-spec § 5, with English and Bangla. That section is the one copy,
  so this file does not repeat it.

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
- **A visibility read landing during Saving** (review R-05). The read is
  started in Editing and held open by the mock. Continue is pressed, then
  the read is released.
  - If it says true, the gate stays in Saving, and the `PUT`'s 200 then
    leads to Rereading.
  - If it says false, the app renders `ready`, and the `PUT`'s late answer
    renders nothing and throws nothing.
- The visibility listener is not attached in Saving or Rereading: a
  `visibilitychange` there sends no read.
- `password_required` re-reads with no password asked.
- A failed re-read shows the session's error card, not the app, and that
  card's Sign out (`more_log_out`) clears the tokens. This holds for a
  non-retryable failure too, where the card has no Retry.
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
- A 409 on verify opens Replace, and `CodeEntry` never shows the 409. The
  retry sends the same code with the replacement.
- **An expired code on the Replace retry** (review R-02). Fake timers; the
  original send is 90 s earlier. The test asserts:
  - the code step shows the `auth.otp.expired` message;
  - the code field is empty;
  - Resend is enabled at once.
  - The same case with the send 20 s earlier shows Resend counting down
    from 40.
- After an OTP refusal, the next verify sends only the newly typed digits.
- Back forgets the code: a later Replace retry after a fresh 409 sends the
  new digits.
- The same Replace path is tested from the code flow, with the plain body.
- Focus is on the Replace step's Username field when it opens.
- The email already-added lookup runs once per value, and locks the role on
  a seat.
- Autofill: the real username field carries `autocomplete="username"`, and
  the phone or email field no longer does.

**No identifier leaks** (`noIdentifierLeaks.test.tsx`, review R-03):

- Flows driven: sign-in, sign-up through a 409 and Replace, the gate, and
  rename, each with distinctive sentinel values for the username, login,
  phone, email, password and code.
- After every step, the test collects:
  - every `localStorage` and `sessionStorage` value;
  - `JSON.stringify(history.state)`;
  - `document.title`;
  - every argument to `console.log`, `info`, `warn`, `error` and `debug`
    (spied).
- It fails if any sentinel appears in any of them.
- It fails if `indexedDB.open` is called.
- It first asserts that its own sentinels did reach the request bodies. A
  run that never typed them cannot pass vacuously.

**Username, contacts** (`username.test.tsx`, `contacts.test.tsx`):

- rename: each outcome in W5 step 5 renders as specified;
- focus: on the gate's field when the gate mounts, and on the password when
  the Remove sheet opens;
- `AvailabilityHint`: an element with role `status` exists in Idle, and its
  text becomes `username_available` after an `available` answer;
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
  - an emptied phone gives `null` in the body (review R-04);
  - a 409 `student.number_accepted` on clearing a phone renders in the sheet
    banner.
- `autocomplete="off"` is on the New student email fields, the Edit sheet
  email fields and the centre invite email field.
- Focus is on the Edit sheet's first field when it opens.
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

**Route boundary**:
- A child that throws during render shows `error_unexpected` with Retry, not
  a blank root.
- Navigating to another route renders that route normally.
- Retry renders the children again.

**Lint (mechanical, U4)**: `no-console` in `eslint.config.js`, configured at
U4's NFR Requirements stage and installed in U4's code generation
(functional-spec § 10 item 6). `npm run lint` in `make web` is its verifier.

**Manual, not automated**:
- The Bangla layout rows (functional-spec § 8).
- Whether a real screen reader announces the hint (functional-spec § 7).
  This one is not verified and not claimed.
Nothing above discharges either.

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
