# Security Requirements — U4 web-identity

The web client's share of NFR1 (anti-enumeration), NFR3 (privacy boundary),
NFR4 (test ordering), the client half of NFR8 that touches the session
(cancellation and token renewal), and the project's Forbidden and Mandated
rules, for the screens in `functional-spec.md` W1–W10. Server-side
enforcement (the privacy gate, uniform refusal, ceilings, the hold digest) is
U1's and U2's; this file covers only what the web client must do or must
never do. Every row names its verifier. Where a verifier is review or a
manual check, the row says so; such a row is not a mechanical control.

Every automated verifier below runs in `npm run check` (`check:generated`,
`format:check`, `lint`, `typecheck`, `test`, `build`, `build:admin`,
`check:bundles`), which `make web` runs after `npm ci` in CI job `web`
(`.github/workflows/check.yml`) on every pull request and every push to
`main` (tech-stack § 3).

Threat model in one paragraph. This is the browser client of a
children's-data product. In this unit's flows it holds the password
(sign-in, sign-up, rename, replace, remove), the six-digit code held for the
Replace step, the username (owner-private, FR9, low-entropy), the person's
own phone and email, and teacher-recorded emails of others (student form,
Edit sheet, centre invite). The realistic leaks in a browser are
`localStorage` and `sessionStorage`, route state (React Router writes it to
`history.state`, which the browser keeps for the tab's session history
across reloads), `document.title` (tab strip, history, window switchers),
the URL (address bar, history, server and CDN logs), the console (visible to
anyone at the machine, and copied into support screenshots), the browser's
form-autofill history, IndexedDB and Cache Storage, and third-party script.
The realistic logic risks are a client that reveals more than the server
decided, a gate that fails open, and an aborted request mistaken for an
offline one or one that discards a rotated token pair.

## Requirements

### Anti-enumeration (NFR1)

| ID | Requirement | Verifier |
|---|---|---|
| NFR1.1 | Sign-in renders the server's refusal and nothing more. Unknown username, account without a password and wrong password all arrive as `auth.password.wrong` and are shown identically, with the link to the code flow (FR4.3). The client has no branch that could tell them apart. | `SignIn.test.tsx`: `auth.password.wrong` renders exactly as before the change, for a username, a phone and an email typed as the login. |
| NFR1.2 | The client never classifies the login value (FR4.1). It sends one `login` field, trimmed, and no `phone` or `email` key, so the request shape says nothing about which kind the person meant. | `SignIn.test.tsx` and `api/client.test.ts`: the `POST /v1/auth/password` body has `login` and `password` and no `phone` or `email` key, for all three kinds of input. |
| NFR1.3 | The availability hint shows only the server's four answers. `unavailable` is shown without saying whether the name is taken or held (ADR-007). Nothing about who holds a name is requested or displayed. An unknown `status` value renders as could-not-check. | `mapAvailability` tests: one state per status, no state that distinguishes held from taken, and an unknown status maps to could-not-check. |
| NFR1.4 | The Replace step names only the person's own typed username (sign-up), or no name (code flow). It carries nothing from the 409 beyond its key. | `SignUp.test.tsx` and `PasswordCode.test.tsx`: the Replace body shows the W1 name from the form in sign-up, and the plain body in the code flow; neither renders any response field. |

### Privacy and secrets in the browser (NFR3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.1 | **No username, login, phone, email, password or code in a request URL.** Both availability lookups, `PUT /v1/me/username`, `POST /v1/auth/password`, `POST /v1/me/contact` and `POST /v1/me/contact/remove` carry their values in a JSON body. **The one exception** is U2's already-added lookup, `GET /v1/accounts/already-added?phone=` and, new in this unit, `?email=` (W9), which C2 defines with a query parameter for the person's own typed contact. That route and its server-side logging are U2's (U1 reverse item `NFR3/already-added-query-string-in-nginx-log`); this unit calls it as defined and makes no URL claim for it. | `api/client.test.ts`: each listed request's URL has **no query string** and its body carries the value. |
| NFR3.2 | **No identifier in the page URL.** No screen this unit adds or changes puts a username, login, phone, email or code in a route path or query. The app's own routes already carry none; the CDN sends `Referrer-Policy: no-referrer` (`infra/modules/cdn/web.tf:150-151`), unchanged, so a page URL is never sent as a `Referer` either. | `noIdentifierLeaks.test.tsx` asserts `window.location.href` contains no sentinel after every step (Q3). The Referrer-Policy is built infrastructure; this unit does not touch it. |
| NFR3.3 | **Nothing typed is persisted, titled or put in route state.** No username, login, phone, email, password or code is written to `localStorage`, `sessionStorage`, route state (`history.state`) or `document.title`. Sign-in no longer hands the typed identifier to the code flow in route state (functional-spec defect 6, W3 step 6). The values the web stores today (`sp.session` tokens, the remembered lens, the workspace id, preferences, the two-step prompt and sidebar flags) are server-issued or app-chosen and carry none of the sentinels. | `noIdentifierLeaks.test.tsx` (frontend-components § 8), with the router decision of Q3. It drives sign-in, sign-up through a 409 and Replace, the gate and rename, with a distinctive sentinel per value. After every step it snapshots every `localStorage` and `sessionStorage` value, `JSON.stringify(window.history.state)`, `document.title`, `window.location.href`, and every argument to a spied `console.log`, `info`, `warn`, `error` and `debug`, and fails if any sentinel appears. **Non-vacuity, two controls:** (1) it first asserts that its sentinels reached the request bodies; (2) it mounts the flows under `BrowserRouter`, as `src/main.tsx` does, and asserts after the first navigation that `window.history.state` holds the router's entry (a numeric `idx`). Under the shared helpers' `MemoryRouter` the `history.state` snapshot would be empty whatever the code did. |
| NFR3.4 | **No IndexedDB and no cached API response.** The web client opens no IndexedDB database. The service worker caches the app shell only (`runtimeCaching: []`, `vite.config.ts`), so no response carrying a username or contact is stored in Cache Storage. Both unchanged. | `noIdentifierLeaks.test.tsx` installs a stub `indexedDB` global whose `open` is a spy (`vi.stubGlobal('indexedDB', { open: vi.fn() })`, removed by `vi.unstubAllGlobals()` after the test) and asserts `open` was never called. jsdom implements no IndexedDB, so without the stub there is nothing to spy on and a call would throw a `ReferenceError` rather than fail the assertion (review R-03). The `runtimeCaching` setting is checked by review: no test reads the generated service worker. |
| NFR3.5 | **No console output from shipped code** (the control functional-spec § 10 item 6 assigns to U4; Q1). ESLint `'no-console': 'error'` with no allowed method applies to `src/**/*.{ts,tsx}`, test files excluded. The two existing calls (`src/core/useResource.ts:104`, `src/features/family/pay/PayScreen.tsx:79`, each a `console.error` of a non-`ApiError` exception) keep their call behind `// eslint-disable-next-line no-console -- <reason>`. `linterOptions.reportUnusedDisableDirectives: 'error'` makes a directive that suppresses nothing a lint failure. **Installed in U4's code generation; U4 is not complete without it** (project Mandated: a control names the unit that installs it). Out of scope, with the reason: `vite*.config.ts` and `scripts/*.mjs` run in Node at build time, see no user data and print to the developer's terminal. **Inline directives are pinned, not banned** (review R-01). `linterOptions.noInlineConfig: true` was considered and rejected: it disables every `eslint-disable` comment, and `src` already relies on two `react-hooks/exhaustive-deps` directives (`ui/components.tsx:55`, `core/useResource.ts:116`) plus the two `no-console` exemptions this unit adds, so it would force each into file-level config overrides that are harder to review than the comments. **Stated limits:** the rule matches `console.<method>` on the global name. It does not catch an alias (`const c = console`), `globalThis.console`, or React's own default logging of a caught render error (React logs the error and component stack, not props or state). Those remain review's and, for the flows driven, the leak test's console spy. | Three verifiers. **(1)** `npm run lint` (`eslint . --max-warnings 0`) in `make web`. **(2)** `src/test/lintConfig.test.ts`, Node environment: it resolves the ESLint configuration for a `src` file through ESLint's own `calculateConfigForFile` and asserts `no-console` is at `error`, and that the same call for a test file does not apply it. **(3)** The same test scans every non-test `.ts`/`.tsx` file under `src` (excluding `src/api/schema.d.ts` and `src/i18n/generated`, which lint ignores) for **every** ESLint inline directive or config comment, matched by `/(\/\/|\/\*)\s*(eslint(-disable(-next-line\|-line)?\|-enable)?\|globals?\|exported)(\s\|\*\/\|$)/`: a bare `eslint-disable-next-line` with no rule name, a block `/* eslint-disable */`, `eslint-disable-line`, an inline `/* eslint no-console: off */` config and `/* global */` all match. It compares the result, as a multiset of (file, trimmed directive text) with a count per pair, against an exact committed list: today's two `react-hooks/exhaustive-deps` directives and the two `no-console` exemptions. A new directive of any kind, a second identical directive in a file that already has one, or a removed one fails the test until the list changes in the same diff, where review sees it. Line numbers are not pinned, so moving a directive with its code does not fail the test; pinning the directive text and count is what closes the bypass. **Limit:** the match is textual; a directive assembled so the regular expression misses it (for example split across lines inside a block comment) is review's. |
| NFR3.6 | **Passwords and the held code are never persisted.** Password fields live in component state and are cleared on the paths the functional design names (FR1.6); none is written anywhere NFR3.3 lists. The six digits held for Replace live in a `useRef` owned by `SignUp` or `PasswordCode` (W2 step 2), never in state passed to a child, route state or storage. They are cleared on Back and on an OTP refusal, and go with the component on unmount. Both flows run signed out. | **(1)** `SignUp.test.tsx` and `PasswordCode.test.tsx`: after Back and a fresh code entry, a second 409 and Replace retry sends the newly typed digits, never the old ones; after an OTP refusal on the retry, the next verify sends only what is typed into the remounted `CodeEntry`. **(2)** `noIdentifierLeaks.test.tsx` carries password and code sentinels through the same flows. |
| NFR3.7 | **The username is shown only to its owner.** It arrives only in `MeResponse` and `UsernameChangeResponse`, both owner-only (ADR-010), and is rendered only on Settings → Account's Username row, the Username screen and the gate's field. No other response type in the generated `schema.d.ts` declares a `username` field, so no other screen can read one without a type error. No share, notification or title carries it. | Server-side: U1's privacy gate (FR9.2) keeps `openapi.json` honest, and `check:generated` keeps `schema.d.ts` equal to it, so `tsc` refuses a read of `username` from any other response. Client-side send path: the source-scan test of frontend-components § 8 asserts that no file under `src/` other than `api/endpoints.ts` and the username, sign-in and sign-up modules sends a `username` or `login` key, paired with a "present" assertion on `api/endpoints.ts` so an empty scan fails. The scan is textual and can be defeated by deliberate string building; NFR3.1's URL assertions are its behavioural half. |
| NFR3.8 | **Teacher-recorded emails are someone else's data.** The student email and guardian email fields on New student and the Edit sheet, and the centre invite email, carry `autocomplete="off"`, so the browser neither offers the teacher's own addresses nor files the typed address in form history. They are shown only on the teacher's and manager's own screens, as recorded phones are today (TC-13, FR6.3). | A test per form asserting the attribute (`people.test.tsx`, `centre.screens.test.tsx`). Whether a particular browser honours `autocomplete="off"` for form history is not verified; it is the platform's documented control and none stronger exists for a web form. |
| NFR3.9 | **No third party can receive what the page holds, and this unit changes nothing that keeps it so.** The generated Content-Security-Policy (`vite.config.ts`, `contentSecurityPolicy`) allows `connect-src` only to `'self'` and the build-time API origin, `script-src 'self'`, `object-src 'none'`, `form-action 'self'`. The build refuses a non-HTTPS `VITE_API_BASE_URL`. The CDN adds HSTS, `frame-ancestors 'none'` and `no-referrer` (`infra/modules/cdn/web.tf:132-156`). Every new call goes to the same API origin through `request()`, so `connect-src` is not widened. **U4 edits neither `vite.config.ts`'s policy nor `infra/`.** | The policy and the HTTPS check are built and run in every `npm run build`. That U4 does not change them is checked by review of the diff: no test asserts the policy text. |
| NFR3.10 | **No new dependency, so no new identifier surface.** Debounce, abort, timers and `visibilitychange` are platform APIs; tests use the installed Vitest, jsdom and Testing Library. If code generation finds a dependency unavoidable, it is checked against the forbidden-identifier set first (project Mandated) and gets an admission note in the PR, `package-lock.json` is regenerated in the same commit, and `npm audit` annotates it. The web client has no device-identifier API to misuse (no `TelephonyManager`, no advertising id), and adds no analytics, ads or crash-reporting script (project Forbidden). | `npm ci` in `make web` fails when `package.json` and `package-lock.json` disagree, so a dependency cannot arrive without a lockfile change in the diff. `npm audit` in CI job `web` annotates on every push; `npm audit --omit=dev --audit-level=high` blocks the web release (`.github/workflows/deploy.yml`, step "Release gate - web dependency CVEs"). The admission note and the forbidden-set check are review's. |

### Client checks are format-only and never stricter than the server (FR11.3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.11 | Username fields check only non-blank, and cap input so the **trimmed** value is at most 64 code points (the schema's `maxLength`), applied in the change handler and not while an IME composition is in progress. None of FR1's rules is applied on the client. The login field checks only non-blank. | Field tests: 65 trimmed code points refused, 64 accepted, 64 with surrounding spaces accepted, 21 accepted; an input event with `isComposing` is not cut. `SignIn.test.tsx`: a login of any shape is sent. |
| NFR3.12 | Every email field uses the one shared check, the server's pattern with length counted in **code points**, not UTF-16 units (functional-spec defect 4). | `identifier.test.ts`: `a@b.c.` and `a@.b.c` accepted; `a@b` and `@b.c` refused; 254 code points of astral characters accepted, 255 refused. **Limit:** the test pins the known corners; nothing compares the client function with the server regex mechanically, so a server change is caught only by its own review. |
| NFR3.13 | The client never decides whether a contact may be removed, whether a rename is allowed now, or whether a username is required. Remove is offered for every present contact, Change is always offered, and the gate follows the server's flag. A `has_password: false` note leaves the actions enabled; the server's refusal decides. | `contacts.test.tsx`: one present contact still yields Remove; `has_password: false` shows the note with actions enabled. `username.test.tsx`: Change is present without `next_change_at`. |

### The gate's security bounds (FR5.2, FR5.3)

| ID | Requirement | Verifier |
|---|---|---|
| NFR3.14 | When a successful read says `username_required: true`, nothing but the gate is rendered until a later read says `false` or the person signs out. The gate is not a route: a typed URL, browser Back and Forward and a deep link all render the gate. It lifts **only** on a read, never on the `PUT`'s 200 alone. A read landing while Saving is acted on only in Rereading (W4 step 9). | `session.test.ts` (`sessionFromMe`: `true`, `false`, absent) and `ChooseUsernameGate.test.tsx`: typed `/settings` and `history.back()` render the gate; a 200 followed by a read still saying `true` returns to Editing; the visibility-read-during-Saving cases (both answers). |
| NFR3.15 | **Fail closed, with a way out.** A failed read renders the blocking error card, so no app screen is reachable while the flag is unknown; the web needs no bounded window (U3 NFR3.13 has one; functional-spec § 9 item 2). The failed card gains Sign out (`more_log_out`), so a non-retryable failure does not strand the person. | `ChooseUsernameGate.test.tsx`: a failed re-read shows the error card, not the app; its Sign out clears the tokens, also for a non-retryable failure where the card has no Retry. This is an ordering exposure, not an authorization one: the server refuses nothing for a missing username (FR5.3, A5). |
| NFR3.16 | Sign out from the gate or the failed card runs the session's one `signOut()`: tokens cleared, the token family revoked best-effort, lens and workspace forgotten, two-step status reset. | `ChooseUsernameGate.test.tsx`: Sign out clears `sp.session` and calls `POST /v1/auth/logout`. |
| NFR3.17 | The admin app is outside the gate and this unit's screens. `web/src/admin` has its own session and client and never calls `/v1/me`. | `scripts/check-bundles.mjs` in `npm run check` fails if either build carries the other's code or strings, with paired present and absent checks. |

### Cancellation and the session (NFR8, client half)

| ID | Requirement | Verifier |
|---|---|---|
| NFR8.7 | **Aborting a request never loses a rotated token pair** (functional-spec defect 5; the U3 code-generation review's Major finding, checked on the web). `renew()` (`api/tokens.ts`) takes no `AbortSignal`, runs once per tab in a shared promise under a cross-tab Web Lock, and calls `saveTokens` inside that promise whatever happens to its callers. A lookup aborted while `request()` awaits renewal therefore cannot cancel the save. This unit keeps that shape: `renew()` gains no signal, and no caller wraps it in a race that could drop its result. **Stated limit:** a tab closed between the server's rotation and `saveTokens` loses the pair; no client code can close that. | `api/client.test.ts`: a caller aborted while `request()` awaits a held-open `/v1/auth/refresh` still leaves the rotated pair in storage once the refresh answers, and a second caller then uses the new access token. |
| NFR8.8 | **An aborted request is cancelled, never "offline".** `send()` (`api/client.ts:60-62`) rethrows only `DOMException` `AbortError` today. A `fetch` aborted with a reason rejects with that reason (a string, for `abort('superseded')`), and `AbortSignal.timeout()` rejects with `TimeoutError`; both are mapped to `error.network.unreachable` today. U4 changes `send()` to rethrow whenever `options.signal?.aborted` is true, before mapping. The checker still decides "superseded", "timed out" and "failed" from its own flags, never from the error's type (Q1 of the functional design). | `api/client.test.ts`: with a signal aborted with a string reason, and with `AbortSignal.abort(new DOMException('', 'TimeoutError'))` (the reason `AbortSignal.timeout()` produces, without depending on real time), `request()` rejects with the reason and not with an `ApiError` of `error.network.unreachable`; a genuine `fetch` rejection with no abort still maps to `error.network.unreachable`. |

### Test ordering (NFR4)

| ID | Requirement | Verifier |
|---|---|---|
| NFR4.1 | Team ordering predicate applied to this unit. No web change computes money, and every authorization decision (lens, username required, removal allowed, rename window) is the server's. The predicate "a wrong answer would be a money or authorization error" therefore holds for no client code here, and the tests are test-after, written from the functional-design acceptance steps. The authorization-adjacent client behaviour, routing on the server's flag (NFR3.14–3.15), is tested from FR5.2's acceptance criterion. | The test list in frontend-components § 8; review checks each test was written from its criterion (team: test-after is not permission to test the implementation). |

## Not adopted, with reason

- **A web Content-Security-Policy or header change for this unit.** None of
  the new calls needs a new origin, and the screens add no inline script.
  Changing the policy would widen review scope for no gain (NFR3.9).
- **Clearing the typed username on navigation away from a form.** Full-page
  forms already lose typed input on navigation and keep nothing across a
  reload (functional-spec § 7); the username is treated as personal data for
  persistence, URLs, titles and logs, not as a credential.
- **Overriding React's default caught-error logging.** React logs a render
  error and its component stack, not props or state. A custom
  `onCaughtError` would add code to silence a log that carries no
  identifier from this unit's flows, which the leak test's console spy
  observes (NFR3.5 limit).

## Assumptions & Open Questions

- [assumption] The username is personal data, not a credential: it is kept
  out of storage, route state, titles, URLs and logs, but the browser's
  password manager may save it with the credential, which is the
  conventional behaviour and stays on the owner's device.
- [assumption] ESLint's `calculateConfigForFile` is available from the
  installed `eslint` 9.39.5 to a Node-environment Vitest test; it is part of
  ESLint's public Node API. The build is the verifier: a missing method
  fails the test.
- Open questions: None.

## Sources

- Requirements: `inception/requirements-analysis/requirements.md` NFR1, NFR3,
  NFR4, NFR8, FR3.2, FR4.1, FR4.3, FR5.2, FR5.3, FR6.3, FR9, FR11.3, A5.
- Contract: `inception/contract-design/contract-summary.md` C1 (both lookups
  `POST` with a body), C2 (the already-added query).
- Functional design: `construction/web-identity/functional-design/functional-spec.md`
  § 1 defects 4–6, W1–W4, W9, § 7 (Sensitive data), § 9 items 2 and 6,
  § 10 item 6; `frontend-components.md` § 2.2, § 2.2a, § 2.3, § 8.
- U3 reference: `construction/android-identity/nfr-requirements/security-requirements.md`
  and `reviews/review-01.md`, `review-02.md`;
  `code-generation/code-summary.md` (review round 1, renewal fix).
- U1 reverse items: `construction/usernames-backend/nfr-requirements/traceability.json`.
- Code read: `web/eslint.config.js`, `web/package.json`, `web/package-lock.json`,
  `web/vite.config.ts` (CSP, HTTPS check, `runtimeCaching`),
  `web/src/api/client.ts:51-63`, `web/src/api/tokens.ts` (`renew`,
  `saveTokens`, storage), `web/src/main.tsx` (`BrowserRouter`),
  `web/src/test/{render,signedIn}.tsx` (`MemoryRouter`),
  `web/src/core/useResource.ts:104`, `web/src/features/family/pay/PayScreen.tsx:79`,
  `web/scripts/check-bundles.mjs`, `infra/modules/cdn/web.tf:132-156`,
  `.github/workflows/check.yml` (job `web`), `.github/workflows/deploy.yml`
  (job `web`, release gate).
- Project rules: `project.md` Forbidden (no analytics or ads SDK, obligations
  name their verifiers, no unchecked counts) and Mandated (dependency check
  against the forbidden set; a control names the unit that installs it).
- Answers: `nfr-requirements-questions.md` Q1, Q3 [Q1] [Q3].
