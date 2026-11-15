# Code Summary — web-identity (U4)

Built against the approved plan (`code-generation-plan.md`, Steps 1–26; Step 27
is this file, `source-manifest.json` and `traceability.json`). Web only: no
backend, Android, `openapi.json`, CI workflow, `package.json` or
`package-lock.json` change. `source-manifest.json` lists all 79 paths.

## Baselines (Step 1, before any change)

- `npm run check:generated` was **red**: `strings.en.json`, `strings.bn.json`, `message-keys.json` and `schema.d.ts` were stale against the Android bundles and `openapi.json`.
- The whole vitest suite: 61 files, **15 failed and 856 passed**. All 15 failures were in the i18n "server message keys" test: the `account.contact.*`, `account.username.*`, `auth.lookup.too_many` and `student.email.taken` keys were unmapped.
- `typecheck` and `lint` were clean.
- After the Step 2 regeneration, `check:generated` and the i18n test went green. `typecheck` went red at `SignUp.tsx` and `Members.tsx`, as correction 2 predicted. Steps 4–5 cleared it, and nothing was suppressed.

## Files

Main code, all under `web/src/` unless shown:

- **Session and shell**: `session/session.tsx`, which adds the `username-required` state, `sessionFromMe` and `reread()`. `App.tsx` places the gate before the lens picker and every route, and gives the failed card a Sign out. New `shell/RouteErrorBoundary.tsx`.
- **API**: `api/client.ts`, where `send()` treats any aborted signal as cancelled. `api/endpoints.ts`. The regenerated `api/schema.d.ts` and `i18n/generated/*`.
- **Auth**:
  - One-field sign-in, with no identifier in route state.
  - Sign-up with a username and an email already-added lookup.
  - The code-step seam and the new `ReplaceUsernameStep.tsx`.
  - `identifier.ts` measures length in code points.
  - New `username/{availability.ts, useUsernameAvailability.ts, UsernameField.tsx, AvailabilityHint.tsx}`.
- **Account**:
  - New `username/{ChooseUsernameGate, UsernameScreen}.tsx` and `contacts/{mappers.ts, ContactsScreen, ReplaceContact, RemoveContactSheet}.tsx`.
  - Changed: `security/{AccountEntries, AddContact, Password, index}.tsx` and `paths.ts`.
- **Teacher**:
  - `centre/Members.tsx`: `contactLine` and invite by email; this fixes the `formatPhone(null)` crash.
  - `people/*`: student emails, the new `EditStudentSheet.tsx`, and an emptied phone now sends `null`.
  - `students/*`: the roster shows the guardian's email and a "Record by email instead" link.
- **Strings**: web-only strings in English and Bangla. Ten are reworded and `web_auth_password_wrong` is removed.
- **Lint and docs**:
  - `web/eslint.config.js` adds `no-console: error` on `src`, with two annotated exemptions: `core/useResource.ts` and `family/pay/PayScreen.tsx`.
  - `docs/delivery/bangla-layout-check.md` gains the U4 rows.

## Tests

Final gates, re-run by the orchestrator after the build:

- `cd web && npm run check` (exit 0):
  - `check:generated` is current.
  - Prettier is clean.
  - ESLint passes with `--max-warnings 0`.
  - `tsc` is clean.
  - **75 test files, 1147 tests passed**.
  - The main build has 252 modules and the admin build 109.
  - `check:bundles` passes: the main and admin bundles are separate.
- `make web` (exit 0): `npm ci`, then the same results.
- This unit's named test files: 27 files, 588 tests passed. The command is in `unit-test-instructions.md`.

**Test-first evidence:**

| Step | Tests | Result before implementation |
|---|---|---|
| 5 | Members null phone | `5 failed, 5 passed (10)`; the render case failed with `TypeError: Cannot read properties of null (reading 'replace')`, which is defect 2 reproduced |
| 6 | Renewal survives an aborted caller | **green, 15 passed**, as expected. No defect: the rotated pair is stored, the next call uses the new token, and the refresh runs once |
| 7 | `sessionFromMe` and the `username-required` state | `4 failed, 5 passed (9)` |
| 8 | Gate routing | `14 failed (14)`: "Unable to find … choose-username-gate". After Step 9, Steps 7 and 8 pass together (23 tests) |

**Named test files (NFR5.1).** `namedTests.test.ts` fails if a listed file is missing. It does not catch a weakened test inside a file that still exists. The list:

- **API and session**: `api/client.test.ts`, `session/session.test.ts`, `session/usernameGate.routing.test.tsx`, `shell/RouteErrorBoundary.test.tsx`, `i18n/i18n.test.ts`.
- **Auth**: `identifier.test.ts`, `parts.test.tsx`, `SignIn.test.tsx`, `SignUp.test.tsx`, `PasswordCode.test.tsx`.
- **Availability**: `username/availability.test.ts`, `username/useUsernameAvailability.test.ts`, `username/UsernameField.test.tsx`.
- **Account**: `username/ChooseUsernameGate.test.tsx`, `username/username.test.tsx`, `contacts/contacts.test.tsx`, `security/security.test.tsx`, `security/password.test.tsx`.
- **Teacher**: `people/people.test.tsx`, `students/students.test.tsx`, `students/mappers.test.ts`, `centre/Members.test.ts`, `centre/centre.screens.test.tsx`.
- **Source scans**: `test/lintConfig.test.ts`, `test/noIdentifierLeaks.test.tsx`, `test/usernameKeyScan.test.ts`, `test/namedTests.test.ts`.

**Existing tests rewritten from their new acceptance criteria (correction 1).** No test was deleted, skipped or marked `.only`.

- **`SignIn.test.tsx`**: the client-side shape checks and the phone and email normalisation became one table. A username, a phone and an email are each sent as typed under `login`. The server's `email.invalid` shows under the field.
- **`SignUp.test.tsx`**:
  - The form fills a username, and the autocomplete assertion moved to the username field.
  - "never looks up an email" became "looks up an email once per value".
  - The notice is now targeted by `data-testid`, because the username hint is a second live region.
- **`password.test.tsx`**: the two Add rows became one Phone and email row, and Add now lands on Contacts. The plan named `security.test.tsx`; these tests actually live in `password.test.tsx`.
- **`Members.test.ts`**: the `inviteBody` cases cover email.
- **`wide.test.tsx`**: "No phone" is now "No contact".
- **Fixtures**: updated for the regenerated types only.

## Corrections and decisions recorded in the plan

1. **Contradicting existing tests were rewritten, not deleted** (listed above).
2. **The typecheck was red on purpose** between Steps 2 and 5.
3. **`RouteErrorBoundary` takes `pathname` as a prop and clears itself in `componentDidUpdate`, with no `key`.** A test checks that navigation does not remount the page (review 2 of the functional design).
4. **Part B was written test-first** (session gate, routing, members null, renewal), although NFR4.1 classes all web tests as test-after. This follows the team's ordering rule: routing grants or withholds a screen, so a wrong answer is an authorization error.
5. **The checker's own 3 s timer retires a lookup even while a token renewal is held open** (performance NFR8.3, which amends frontend-components § 2.2).

Builder decisions:

- **Blank login**: Sign in stays disabled while the login field is blank. Android does the same, and no new string was invented.
- **Replace contact, Resend**: the password is dropped after the code request, so Resend and Change go back to the entry step with the new value kept, as on Android.
- **Code-step pacing**: a code step shown again after Replace counts its resend wait from the original send plus 60 s. The two setup-lapse paths keep today's fresh 60 s.
- **Spent-code keys**: only `auth.otp.expired`, `no_tries_left` and `not_valid` return to the code step. `auth.otp.wrong` shows in the Replace step's banner.
- **Roster**: `seatLine` names an email-only guardian by their email, instead of saying "no guardian".
- **Username key scan**: the allowlist is `api/endpoints.ts`, `features/auth/**` and `features/account/username/**`.
- **Lint directive scan**: it also covers the non-test helpers in `src/test/`, which is stricter than the plan.
- **Routing test without `StrictMode`**: StrictMode reads `/v1/me` twice, and the test counts reads exactly.
- **Step 2 was not a separate commit**: the builder was not allowed to commit. The generated diff is limited to `schema.d.ts` and `i18n/generated/*`.

## Not discharged (manual, stated plainly)

- **Bangla layout (FR11.2)**: 20 U4 web rows in `docs/delivery/bangla-layout-check.md`, all *not yet checked*. Nothing automated checks Bangla layout.
- **NFR8.4 hint latency on a low-end device**: 3 timing rows, *not yet checked*. Nothing automated discharges them.
- **Screen readers**: whether a real screen reader announces the hint is not verified and not claimed.

## Follow-ups carried forward

- **Batch quick-add cannot record an email** (functional-spec § 10 item 3): `EnrollmentCreateRequest` has no email fields. That is U2's to add, or to declare intended.
- **Under-declared statuses in `openapi.json`** (§ 10 item 4): four operations, carried from U3, for U1 and U2.
- **Tab closed mid-rotation**: if a tab closes while a refresh is in flight, the new token pair can be lost. No client code can prevent that.
