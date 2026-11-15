# Tech Stack Decisions — U4 web-identity

U4 changes the existing web client. The stack is fixed and this unit **adds
no library**, runtime or dev. This file records what it uses, the few choices
it makes, the toolchain controls that verify it as built on this branch, and
the client-owned parts of NFR5 (coverage), NFR6 (compatibility) and NFR9
(committed contract).

## 1. What this unit builds on (read on this branch)

From `web/package.json` (exact pins) and `web/package-lock.json`:

| Concern | In use | Used by U4 for |
|---|---|---|
| Language and UI | TypeScript 5.9.3 (`strict`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`; `tsconfig.app.json`), React 19.3.1 | every screen in functional-spec W1–W10 |
| Routing | `react-router` 7.18.5, `BrowserRouter` in `src/main.tsx` | the new Settings destinations; the gate is a session state, not a route (W4) |
| HTTP | platform `fetch` through `request()` / `send()` (`src/api/client.ts`), renewal in `src/api/tokens.ts` | every new call; the `send()` abort rule (security NFR8.8) |
| API types | `openapi-typescript` 7.13.0 generating `src/api/schema.d.ts` from `../openapi.json` | the regenerated types that turn the C1/C2 changes into `tsc` errors (functional-spec § 1) |
| Strings | `scripts/sync-strings.mjs` generating `src/i18n/generated/*` from the Android bundles | U3's strings and message-key map, regenerated (functional-spec § 5) |
| Build and PWA | Vite 7.3.7, `vite-plugin-pwa` 1.3.0, a generated CSP (`vite.config.ts`) | unchanged (security NFR3.9) |
| Tests | Vitest 4.1.12 (jsdom 27.4.0, `globals`, `restoreMocks: true`, setup `src/test/setup.ts`), Testing Library (`react` 16.3.3, `user-event` 14.6.8, `jest-dom` 6.10.0), `vi.stubGlobal('fetch')` as `src/test/signedIn.tsx` does | every test in frontend-components § 8 |
| Lint and format | ESLint 9.39.5 with `typescript-eslint` 8.72.1 `strict`, `react-hooks` 5.2.0; Prettier 3.9.10 | the new `no-console` rule (TSD-2); formatting of every new `.ts`/`.tsx` file |

## 2. Decisions

| ID | Decision | Rationale | Alternatives rejected |
|---|---|---|---|
| TSD-1 | **No new runtime or dev dependency.** Debounce and the 3 s bound are `setTimeout`; supersession is `AbortController`; the tab re-read is `visibilitychange`. | Each package added means an admission note, a lockfile change, `npm audit` surface and forbidden-identifier checking (project Mandated) for behaviour the platform already gives. | A debounce helper library (one more package for five lines); `AbortSignal.timeout()` for the bound (works, but the checker must know it timed out from its own flag, functional-design Q1, and fake timers drive the checker's own timer directly). |
| TSD-2 | **`no-console` as specified in security NFR3.5** (Q1): `'no-console': 'error'`, no allowed methods, on `src/**/*.{ts,tsx}` with tests excluded; two annotated exemptions; `reportUnusedDisableDirectives: 'error'`; `src/test/lintConfig.test.ts` pins the rule and every inline ESLint directive under `src` (security NFR3.5, review R-01). Installed in U4's code generation. | The rule is the mechanical form of "no identifier in a log line" for the web, which the functional design assigned to this unit. Scoping to `src` keeps build-time Node files, which see no user data, out of it. The config test exists because a lint rule deleted from `eslint.config.js` would otherwise disappear silently with a green lint. | `allow: ['error']` (leaves the most likely leaking call open); linting Node config files (annotations with no privacy value); `warn` (equivalent under `--max-warnings 0`, but reads as advisory). |
| TSD-3 | **No web coverage measurement** (Q2). | No practice names a web figure; a report without a gate is decoration, and a gate would be a quality target nobody affirmed. The named test list is the obligation (NFR5.1). | `@vitest/coverage-v8` as a report (a dev dependency for a number nobody acts on); a ratchet or floor (an unaffirmed target; a ratchet whose floor file can be lowered in the same commit, as Android's prints, gives no protection a reviewer does not already give). |
| TSD-4 | **The leak test renders under `BrowserRouter`** (Q3), with a positive control on `window.history.state`. | The shared helpers use `MemoryRouter`, which never writes `window.history`, so the functional design's snapshot would pass vacuously under them. | Asserting `useLocation().state` through a probe (tests the router, not the browser place route state is kept). |
| TSD-5 | **Fake timers for every timing obligation.** `vi.useFakeTimers()` with `vi.advanceTimersByTime`, as `src/core/useResource.test.tsx` already does. | Virtual time makes "at 500 ms and not at 499 ms" and "at 3,000 ms and not at 2,999 ms" exact and fast. | Real timers with waits (slow and flaky); a timing library (TSD-1). |

## 3. Toolchain controls on this branch (as built, read from the files)

`npm run check` = `check:generated` → `format:check` → `lint` → `typecheck`
→ `test` → `build` → `build:admin` → `check:bundles` (`web/package.json`).
`make web` = `cd web && npm ci --no-audit --no-fund && npm run check`
(`Makefile`); `make check` includes `web`.

| Control | Built? | Where | U4 relies on it for |
|---|---|---|---|
| Generated-file drift (API types, strings, fonts) | yes | `scripts/check-generated.mjs` | NFR9.1. **Red on this branch today** (functional-spec § 1 defect 1) until U4 regenerates both sets as its first change. |
| Prettier | yes, over every file Prettier handles | `format:check` (`prettier --check .`) | formatting of every new file; unlike Android's Kotlin, web source is format-checked |
| ESLint, `--max-warnings 0` | yes; **no `no-console` rule today** | `eslint.config.js` (money-boundary bans on `parseFloat`, `Number.parseFloat`, `localStorage.clear`) | TSD-2 adds `no-console` |
| TypeScript, `tsc -b --noEmit` over app, node and test configs | yes | `tsconfig*.json` | the regenerated types (NFR9.1); test files are typechecked too (`tsconfig.test.json`) |
| Vitest | yes; jsdom, **no coverage option, no coverage provider installed** | `vite.config.ts` `test` block | every named test |
| Production builds and bundle separation | yes | `build`, `build:admin`, `scripts/check-bundles.mjs` | security NFR3.17 |
| Locked install | yes: `package-lock.json` (lockfileVersion 3, every package entry with `resolved` and `integrity`), installed with `npm ci` in `make web`, CI and the deploy job; every direct dependency pinned exactly in `package.json` | `Makefile` `web`, `.github/workflows/check.yml` job `web`, `deploy.yml` job `web` | security NFR3.10 |
| npm CVE scan | yes, `npm audit` (no osv-scanner on npm): annotating on every push in CI job `web` (`--omit=dev --audit-level=low`, and `--audit-level=high` for the toolchain), **blocking at the web release** (`npm audit --omit=dev --audit-level=high`, `deploy.yml` step "Release gate - web dependency CVEs") | `.github/workflows/check.yml`, `deploy.yml` | NFR3.10; unchanged |
| Dependabot or another update bot | **no** (`.github/` holds `workflows/` only) | — | not relied on |
| Web coverage | **no** | — | not relied on (TSD-3) |
| Screenshot tests | **no** | — | not relied on; Bangla layout stays manual (FR11.2) |
| Browser performance harness | **no** | — | not relied on; performance NFR8.4 is a manual check |

**What triggers the web job.** `.github/workflows/check.yml` runs on every
`pull_request`, on `push` to `main` and on `workflow_dispatch`, with **no
`paths` filter**: job `web` runs, in parallel with `backend`, `android-unit`
and `site`, for every pull request whatever it changes. The jobs are split per
surface (so a web change never waits on a Kotlin build), not filtered by
path. `deploy.yml` refuses a commit whose `web` job did not pass (its
`REQUIRED` list). This corrects functional-spec § 10 item 1, which attributes
the red web gate to path-split CI. What the record shows instead: the
branch carrying U1–U4 has not been run through CI as a pull request in this
record, U1's and U2's code summaries ran `make … lint typecheck test`
(backend only, and U2's says the web part was not run), U3's ran Gradle
tasks only, and the intent's recorded Construction Verification Command is
`make PY=.venv/bin/python lint typecheck test`, which does not include
`make web`.

## 4. Client-owned NFR requirements

| ID | Requirement | Verifier |
|---|---|---|
| NFR5.1 | **No web coverage figure exists, and none is claimed** (Q2). NFR5 names backend and Android coverage only. The web obligation is that **every new or changed hook, mapper, session function, screen and API function ships its named tests**, listed in frontend-components § 8: the availability checker, `mapAvailability`, `sessionFromMe` and `reread()`, the gate, sign-in, sign-up and the Replace step from both owners, username and contacts screens, students and members, the email check, the fetch-layer tests, the leak test, the `username`/`login` source scan, the route boundary and `lintConfig.test.ts`. | Two verifiers, with what each does not catch (review R-04). **(1)** The unit's code summary lists each named test file and the tests in it. **(2)** `src/test/namedTests.test.ts` holds that file list and fails if any listed file is missing. A listed file that remains but holds no test fails the run too: Vitest reports a test file with no test as a failure. **Not caught, stated plainly:** deleting or weakening one test case inside a file that still holds others, and a module that ships with no test file at all. Both stay review's, against frontend-components § 8. The list itself can be shortened in the same diff, where review sees it. No coverage measurement exists to catch either case, and this unit adds none. |
| NFR5.2 | **The web gate is green at U4's completion.** U4 is not complete while `make web` fails: `check:generated` must pass after regeneration, and the i18n `server message keys` test must resolve every committed key. | `make web` run and its result recorded in U4's code summary. Because the intent's Construction Verification Command does not run `make web` (§ 3), the code summary records it separately. |
| NFR6.1 | **Unknown response fields are tolerated.** Responses are `JSON.parse`d and typed, never validated against a closed shape, so a new server field is ignored. | Decode-path tests in the screen and mapper tests use fixtures carrying an extra field (frontend-components § 8, students and members). |
| NFR6.2 | **Fields that became nullable are read as nullable.** `MemberResponse.phone` is `string \| null` (C2). | The regenerated `schema.d.ts` makes a non-null use a `tsc` error; `Members.test.ts`: a members list containing `phone: null` renders without throwing (defect 2). |
| NFR6.3 | **Unknown enum-like values degrade, not crash.** An availability `status` outside the four known values renders as could-not-check; an absent `username_required` reads `false`. | `mapAvailability` tests; `sessionFromMe` with the flag absent gives `ready`. |
| NFR9.1 | **The client is compiled against the committed contract.** `schema.d.ts` must equal what `openapi-typescript` generates from `../openapi.json`, and every request and response the unit uses is typed from it, so a renamed, removed or newly required field in `openapi.json` is a `tsc` error. **Limit, stated plainly:** the check is compile-time. Nothing validates a live response against the schema at run time, and a field is only as nullable as `openapi.json` declares it; the server's schema-diff gate keeps `openapi.json` true to the server. | `check:generated` and `typecheck` in `npm run check`. |

## Assumptions & Open Questions

- [assumption] The record contains no pull-request CI run for this branch;
  the statement in § 3 is about what the record shows, not about GitHub's
  history, which this stage did not query.
- [assumption] `npm ci` and the registry are reachable from CI as they are
  today; no new host is needed, because no dependency is added.
- Open questions: None.

## Sources

- `web/package.json`, `web/package-lock.json`, `web/eslint.config.js`,
  `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.test.json`,
  `web/vite.config.ts`, `web/src/test/setup.ts`, `web/src/test/signedIn.tsx`,
  `web/src/core/useResource.test.tsx`, `web/scripts/check-generated.mjs`,
  `web/scripts/check-bundles.mjs`, `Makefile` (`web`, `check`),
  `.github/workflows/check.yml` (triggers, job `web`),
  `.github/workflows/deploy.yml` (job `web`, `REQUIRED`), read on this branch.
- Record: `aidlc-state.md` (Construction Verification Command);
  `construction/usernames-backend/code-generation/code-summary.md`,
  `construction/contacts-and-invites-backend/code-generation/code-summary.md`,
  `construction/android-identity/code-generation/code-summary.md` (commands run).
- Requirements NFR5, NFR6, NFR9; contract C2 (`MemberResponse.phone`
  nullable); U1 reverse item `NFR6/clients-tolerate-unknown-fields`.
- Functional design: `functional-spec.md` § 1 defects 1–2, § 10 items 1, 5
  and 6; `frontend-components.md` § 8, § 9.
- U3 reference: `construction/android-identity/nfr-requirements/tech-stack-decisions.md`
  (its coverage-ratchet limits and its named-tests obligation).
- Answers: `nfr-requirements-questions.md` Q1, Q2, Q3 [Q1] [Q2] [Q3].
