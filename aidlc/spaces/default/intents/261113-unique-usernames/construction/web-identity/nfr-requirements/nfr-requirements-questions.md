# NFR Requirements Questions — U4 web-identity

Unit `web-identity` (U4, kind `ui`). Four questions the functional design,
the requirements and the built web toolchain leave open. Everything else is
settled by NFR1–NFR9, the U1 sizing (Family A ceilings assume a client
debounce of at least 500 ms), U3's reviewed NFR set, and the functional
design's own decisions (500 ms debounce, 3 s bound, stop after 429, the
`send()` abort rule, the gate that lifts only on a read).

The person instructed: "don't wait for my approval. Go with your
recommendations." Every answer below is the recommended option, A.

## Q1. How the `no-console` rule is configured

The functional design assigns an ESLint `no-console` rule to U4 (functional-spec
§ 10 item 6): decided here, installed in U4's code generation, and U4 is not
complete without it. As built, `web/eslint.config.js` has no `no-console`
rule. `console.` appears in shipped source at `src/core/useResource.ts:104`
and `src/features/family/pay/PayScreen.tsx:79` (both `console.error` of a
non-`ApiError`), in the Node config file `vite.admin.config.ts:98`
(`console.warn` for the dev server) and in the four `scripts/*.mjs` build
scripts. No test file calls `console.` today.

A. `'no-console': 'error'` with no allowed methods, in a block scoped to
   `src/**/*.{ts,tsx}`, test files (`**/*.test.{ts,tsx}`, `src/test/**`)
   excluded. The two `src` sites keep their call behind an
   `// eslint-disable-next-line no-console -- <reason>` line.
   `linterOptions.reportUnusedDisableDirectives: 'error'` is set, so a
   directive that no longer suppresses anything fails lint. Node-side files
   (`vite*.config.ts`, `scripts/*.mjs`) are out of scope: they run at build
   time, see no user data and print to the developer's terminal. A committed
   test (`src/test/lintConfig.test.ts`, Node environment) resolves the ESLint
   configuration for a `src` file and asserts the rule is at `error`, and
   asserts the exact list of files that carry a `no-console` disable line,
   so neither the rule nor a new exemption can disappear or appear unseen.
B. `'no-console': ['error', { allow: ['error'] }]`, keeping the two sites
   unannotated.
C. `'no-console': 'error'` over every linted file, annotating the Node
   config file too.
D. `'no-console': 'warn'` (fails anyway under `--max-warnings 0`).
E. Remove the two `console.error` calls instead of annotating them.
X. Other (please specify)

[Answer]: A

## Q2. Whether U4 adds web coverage measurement

No web coverage figure exists. `vitest run` runs with no coverage option,
`vite.config.ts`'s `test` block configures none, and no coverage provider is
installed: `@vitest/coverage-v8` and `@vitest/coverage-istanbul` appear in
`web/package-lock.json` only as optional peer entries of `vitest`. NFR5 names
backend and Android coverage only. No team practice assigns a web figure or
ratchet.

A. Add no measurement in U4. The obligation on the web is the named test
   list (frontend-components § 8), as U3's named-tests obligation is for Android, recorded in the
   code summary test by test. The artifacts say plainly that no web
   coverage figure exists and that nothing automated checks that each new
   module has tests. Adding a coverage provider would be a new dev
   dependency (an admission note and a lockfile change) for a number no
   practice asks for, and a report without a gate is decoration while a gate
   would be a quality target nobody affirmed.
B. Add `@vitest/coverage-v8` as a report only, with no threshold.
C. Add a report and a no-decrease ratchet with its floor in a committed file.
D. Add a percentage floor (for example the org default of 80%).
X. Other (please specify)

[Answer]: A

## Q3. How the identifier-leak test observes `history.state`

The functional design's verifier for "no identifier in route state" is
`noIdentifierLeaks.test.tsx`, which snapshots `JSON.stringify(window.history.state)`.
The test helpers render under `MemoryRouter` (`src/test/render.tsx`,
`src/test/signedIn.tsx`). `MemoryRouter` keeps route state in memory and
never writes `window.history`, so under those helpers that snapshot is
always empty and the assertion would pass whatever the code does. The
production app uses `BrowserRouter` (`src/main.tsx:21`).

A. The leak test mounts its flows under `BrowserRouter`, the production
   router, so a `navigate(…, { state })` or `<Link state>` lands in
   `window.history.state` as it does in a browser. It carries a positive
   control: after its first navigation it asserts that `window.history.state`
   holds the router's own entry (a numeric `idx`), which proves the snapshot
   is reading the place route state goes. It also asserts that
   `window.location.href` contains no sentinel. The existing helpers are left
   as they are for every other test.
B. Keep `MemoryRouter` and assert on `useLocation().state` through a probe
   component.
C. Keep the snapshot of `window.history.state` under `MemoryRouter`.
D. Drop the `history.state` half and rely on review.
X. Other (please specify)

[Answer]: A

## Q4. How the perceived hint latency is verified

No browser performance harness exists in `web/` (no Playwright, no
Lighthouse, no benchmark script). The project has recorded that a latency
obligation with no automated verifier is a manual pilot check, stated with
the sentence that nothing automated discharges it (project.md Corrections,
2026-10-23).

A. Two verifiers, as U3's NFR8.4. (1) The client's own timing logic
   (debounce, single in-flight request, abort of the older request, the 3 s
   bound, latest wins, stop after 429) is unit-tested under Vitest fake
   timers. (2) The perceived budget (an answer or "could not check" within
   1 s of the pause, at the server's p95) is a timed manual check in a
   browser on the pilot's low-end Android phone on a mobile network,
   recorded per screen in `docs/delivery/bangla-layout-check.md` beside the
   Bangla rows. Nothing automated discharges (2), and the artifact says so.
B. Add a Playwright harness in this unit.
C. Rely on the backend's 300 ms p95 alone.
D. Manual check only, with no fake-timer tests.
X. Other (please specify)

[Answer]: A

## Assumptions & Open Questions

- [assumption] The person's instruction applies to every question here, so
  each answer is the recommended option A.
- Open questions: None.

## Sources

- Functional design: `construction/web-identity/functional-design/functional-spec.md`
  § 7 (Sensitive data), § 10 items 5 and 6; `frontend-components.md` § 8, § 9.
- Requirements: `inception/requirements-analysis/requirements.md` NFR5, NFR8.
- U3 reference: `construction/android-identity/nfr-requirements/nfr-requirements-questions.md`
  Q4 and Q5; `performance-requirements.md` NFR8.4.
- Code read: `web/eslint.config.js`, `web/package.json`,
  `web/package-lock.json`, `web/vite.config.ts`, `web/vite.admin.config.ts:98`,
  `web/src/core/useResource.ts:104`, `web/src/features/family/pay/PayScreen.tsx:79`,
  `web/src/main.tsx`, `web/src/test/{render,signedIn}.tsx`, `web/scripts/*.mjs`.
- Project rule: `project.md` Corrections 2026-10-23.
