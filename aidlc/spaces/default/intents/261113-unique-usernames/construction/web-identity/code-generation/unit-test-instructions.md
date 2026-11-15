# Unit Test Instructions — web-identity (U4)

## Framework and setup

- **Runner.** Vitest 4.1.12 with jsdom 27.4.0, configured in the `test` block
  of `web/vite.config.ts`: `environment: 'jsdom'`, `globals: true`,
  `restoreMocks: true`, setup `src/test/setup.ts`. Testing Library is
  installed: `@testing-library/react` 16.3.3, `user-event` 14.6.8 and
  `jest-dom` 6.10.0. **Nothing is added** (tech-stack TSD-1).
- **Install first.** `web/node_modules` is absent in this sandbox. Run the
  locked install once, the same one `make web` performs:

  ```bash
  cd /workspace/shikkhok-plus/web && npm ci --no-audit --no-fund
  ```

  `npm ci` refuses to run when `package.json` and `package-lock.json`
  disagree, so a dependency cannot arrive unseen (security NFR3.10).
- **Node environment for the lint test.** `src/test/lintConfig.test.ts` starts
  with the docblock `// @vitest-environment node`, because it loads ESLint's
  Node API (`calculateConfigForFile`). Every other test runs in jsdom.
- **Real router where it matters.** The shared helpers (`src/test/render.tsx`,
  `src/test/signedIn.tsx`) use `MemoryRouter`. Two tests mount under
  `BrowserRouter`, as `src/main.tsx` does, because they assert on
  `window.history` and `window.location`:
  - `src/session/usernameGate.routing.test.tsx`;
  - `src/test/noIdentifierLeaks.test.tsx` (tech-stack TSD-4).

## Commands (this unit only)

Run from `/workspace/shikkhok-plus/web`. Every command names this unit's test
files exactly. None is a bare `npm test`.

**Runner check and baseline (plan Step 1).** Run before the first test-first
step:

```bash
cd /workspace/shikkhok-plus/web
npx vitest run src/session/session.test.ts src/api/client.test.ts
npm run check:generated
npx vitest run src/i18n/i18n.test.ts
npm run typecheck
npm run lint
```

By reading the code, two of these are expected red before plan Step 2:
- `check:generated`, because `schema.d.ts` and the generated strings are
  stale;
- the i18n test, because 15 committed server keys are unmapped.

Record what each command actually prints in the code summary.

**Test-first steps (plan Steps 5–8).** Run each file alone, and record its
output before the matching implementation step:

```bash
cd /workspace/shikkhok-plus/web
npx vitest run src/features/teacher/centre/Members.test.ts src/features/teacher/centre/centre.screens.test.tsx
npx vitest run src/api/client.test.ts
npx vitest run src/session/session.test.ts
npx vitest run src/session/usernameGate.routing.test.tsx
```

- **The members render (Step 5)** and **the session and routing tests (Steps
  7–8)** are expected red until Steps 5 and 9.
- **The renewal-on-abort test (Step 6)** is written before `client.ts` is
  touched. It is expected green, because the design reads the code as already
  correct. If it is red, that is a found defect, and the build stops there.

**This unit's whole test set:**

```bash
cd /workspace/shikkhok-plus/web
npx vitest run \
  src/api/client.test.ts \
  src/session/session.test.ts \
  src/session/usernameGate.routing.test.tsx \
  src/shell/RouteErrorBoundary.test.tsx \
  src/i18n/i18n.test.ts \
  src/features/auth/identifier.test.ts \
  src/features/auth/parts.test.tsx \
  src/features/auth/SignIn.test.tsx \
  src/features/auth/SignUp.test.tsx \
  src/features/auth/PasswordCode.test.tsx \
  src/features/auth/username/availability.test.ts \
  src/features/auth/username/useUsernameAvailability.test.ts \
  src/features/auth/username/UsernameField.test.tsx \
  src/features/account/username/ChooseUsernameGate.test.tsx \
  src/features/account/username/username.test.tsx \
  src/features/account/contacts/contacts.test.tsx \
  src/features/account/security/security.test.tsx \
  src/features/account/security/password.test.tsx \
  src/features/teacher/people/people.test.tsx \
  src/features/teacher/students/students.test.tsx \
  src/features/teacher/students/mappers.test.ts \
  src/features/teacher/centre/Members.test.ts \
  src/features/teacher/centre/centre.screens.test.tsx \
  src/test/lintConfig.test.ts \
  src/test/noIdentifierLeaks.test.tsx \
  src/test/usernameKeyScan.test.ts \
  src/test/namedTests.test.ts
```

`src/test/namedTests.test.ts` holds this same file list and fails when any
listed file is missing (tech-stack NFR5.1). Change both together.

**Static and build gates this unit touches (plan Steps 2, 22 and 26).**

```bash
cd /workspace/shikkhok-plus/web
npm run check:generated
npm run format:check
npm run lint
npm run typecheck
```

The module gate is `cd web && npm run check`, then `make web` from the
repository root. Both run the whole web suite once, and that is how plan Step
26 shows the existing suite stays green. They are the module gate, not a
per-unit command.

## Coverage expectations

- **No web coverage figure exists, and none is claimed** (tech-stack TSD-3,
  NFR5.1). Vitest runs without a coverage provider, and this unit adds none.
- **The obligation is named tests.** Every new or changed hook, mapper,
  session function, screen and API function has its named test file, listed
  above. Two things check that list:
  - `namedTests.test.ts` fails if a listed file is missing;
  - Vitest fails a file that holds no test.
  **Not caught, stated plainly:** a weakened case inside a file that still
  holds other cases, and a new module that ships with no file at all. Both
  are review's, against frontend-components § 8.
- **Standard strategy, per component:** five to eight tests for each mapper,
  hook, session function and screen, as listed per step in the plan.
  - Every screen that writes covers success, each refusal routing named in
    functional-spec § 4, double submit ignored, and the explicit Retry of a
    failed write (TC-8, D-9).
  - The checker and the gate cover their full state machines (functional-spec
    § 3.1, § 3.4).
- **Scope floor (refactor):** the existing web suite stays green. A changed
  acceptance criterion rewrites the old test. It never deletes it silently
  (plan correction 1).

## Mocking and stubbing guidance

- **HTTP.** Stub `fetch` with `vi.stubGlobal('fetch', …)`, as
  `src/test/signedIn.tsx` does. Requests go through the real `request()`,
  `send()` and `renew()`, so the headers, token renewal and error envelope
  are the real ones. In the handler, assert:
  - the method;
  - the path;
  - `new URL(url).search` (empty for the no-query routes of security NFR3.1);
  - the JSON body.

  Respond with JSON strings shaped from `openapi.json`.
- **Holding a request open.** Return a promise resolved by the test, to model
  an in-flight request or a held-open `/v1/auth/refresh`.
  - For the 3 s bound, the lookup mock must **ignore its signal and never
    settle**. A mock that rejects on abort would let a settle-driven
    implementation pass (performance NFR8.3).
  - For supersession, assert `signal.aborted` on the earlier call.
- **Signed in with a stale token.** Save tokens with an `expires_in` that
  makes `isFresh` false (within the 30 s early-renewal window), so `request()`
  renews first. Assert that `/v1/auth/refresh` is called once and that
  `sp.session` holds the rotated pair afterwards.
- **Time.** Use `vi.useFakeTimers()` with `vi.advanceTimersByTime(…)` for:
  - the 500 ms debounce;
  - the 3 s bound;
  - the resend countdown (`resendAvailableAt`).

  This is the same as `src/core/useResource.test.tsx` does today
  (tech-stack TSD-5). Assert the exact edges: none at 499 ms and one at
  500 ms; could-not-check at 3,000 ms and not at 2,999 ms. Use
  `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` with fake
  timers.
- **Aborts.** Build the reasons explicitly; do not depend on real time:
  - `controller.abort('superseded')`;
  - `AbortSignal.abort(new DOMException('', 'TimeoutError'))`.
- **Visibility.** Set `document.visibilityState` with
  `Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })`,
  then dispatch `visibilitychange` on `document`.
- **History.** Under `BrowserRouter`, move with
  `window.history.pushState({}, '', '/settings')` before rendering. Then call
  `history.back()` and `history.forward()` and await `popstate`.
- **IndexedDB.** jsdom implements none. Use
  `vi.stubGlobal('indexedDB', { open: vi.fn() })`, assert `open` was never
  called, and `vi.unstubAllGlobals()` afterwards (security NFR3.4).
- **Console.** Use `vi.spyOn(console, m)` for `log`, `info`, `warn`, `error`
  and `debug`, and collect every argument. `restoreMocks: true` restores them
  after each test.
- **Queries.** Find elements by role and `data-testid`, never by English
  text, because tests run in either language. Where a test asserts copy, use
  `translate('en', key)` from `src/i18n/i18n.tsx`.
- **Source scans** (`lintConfig.test.ts`, `usernameKeyScan.test.ts`,
  `namedTests.test.ts`) read files relative to `process.cwd()`, which is
  `web/` under `npx vitest run`. Each pairs every "absent" check with a
  "present" one, so a scan of an empty or wrong directory fails.

## Test data

- No real identifiers anywhere. Use:
  - phones in the `+88017…` test range;
  - emails under `example.com`, or `example.invalid` for sentinels;
  - usernames like `nadia_k`, `Rahim.Uddin`, `rahim_math`;
  - passwords like `correct horse`.
- **Sentinels for the leak test**, one per value, each distinctive enough
  never to occur by accident:
  - username `sentinel_user_7`;
  - login `sentinel_login_9`;
  - phone `+8801999999999`;
  - email `sentinel@example.invalid`;
  - password `sentinel-pass`;
  - code `918273`.
- **Username boundary values.** These are the client cap only; FR1's rules
  are the server's.
  - 64 trimmed code points accepted;
  - 65 refused;
  - 64 plus surrounding spaces accepted;
  - 21 accepted.
- **Email corners.** From the server's pattern, `a@b.c.` and `a@.b.c` are
  accepted, and `a@b` and `@b.c` refused. Counted in code points, 254 astral
  code points with `@b.cd` included are accepted and 255 refused.
- **JSON fixtures** are inline objects in the tests, written from the
  committed `openapi.json` schemas named in functional-spec § Sources. Some
  carry one extra unknown field, to show it is tolerated (NFR6.1). They are
  not separate files and are not generated at test time.
- **Nothing persists between tests.**
  - Each test clears the `localStorage` keys it set; it never calls
    `localStorage.clear()` in source code (lint bans it there).
  - Each test builds its own fetch stub.
  - `vi.useRealTimers()` runs after any fake-timer test.
