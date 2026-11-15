## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-11-15T13:05:29Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | web/src/test/noIdentifierLeaks.test.tsx > snapshot(), the `console` entry | The console check joins each logged argument with `String(a)`. A planted `console.log({ username })` becomes "[object Object]" and passes, so the header claim "every argument to a spied console method" holds only for strings and primitives. The `no-console` lint rule is the real net here. | Serialise each argument (JSON.stringify with a fallback to String for non-serialisable values) before the substring search, or narrow the header claim to say the lint rule carries objects. | New |
| R-02 | Minor | web/src/test/lintConfig.test.ts > 'is an error, with no allowed method, on shipped source' | The test resolves the config for only three files (App.tsx, SignUp.tsx, client.ts). A narrower override that turns `no-console` off for one directory, for example `src/features/account/username/**`, passes every test in the file. | Run `calculateConfigForFile` over every file `sourceFiles()` returns, the shipped non-test files, and assert `no-console` is an error with no options in each. | New |
| R-03 | Minor | web/src/shell/RouteErrorBoundary.tsx > header comment and Failed card; web/src/App.tsx > App | The boundary wraps the whole of AppRoutes, so on a render error it replaces the shell and the gate with a card that offers only Retry. Retry re-renders the same failing page, and there is no nav, Home link or Sign out. The header says "the rest of the app is reachable", and the test 'navigating to another path renders that route' passes through a button that exists only in the test harness. | Add a link home and a Sign out to the failed card, or mount the boundary inside the shell around the outlet. Reword the comment, and have the test use what the real card renders. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261113-unique-usernames/construction/web-identity/code-generation/traceability.json > FR11.2 and NFR8.4 | Both entries are status OK, but their stated targets are manual layout and timing rows that are all "not yet checked". The prose in code-summary.md is honest, but a machine reader sees 43 of 43 OK, and the engine's Deferred status exists for this case. | Mark FR11.2 and NFR8.4 as Deferred with the manual rows as the target, so the obligation shows as open. | New |
| R-05 | Minor | web/src/core/useResource.ts and web/src/features/family/pay/PayScreen.tsx > the two `no-console` exemptions | Both comments assert that the logged value is "never a typed value". Nothing checks that, because `console.error(e)` prints whatever non-ApiError was thrown. The pin test fixes the directive text, not its truth. | Reword to what is true, for example "the thrown error only; no field value is passed". Optionally log `e.name` and `e.message` instead of the raw value. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `npx vitest run` (full suite, run by me) | 75 files, 1147 tests passed | Matches the code-summary claim. |
| `npm run check:generated` | "generated files are current" | `schema.d.ts` and `i18n/generated/*` match their generators, so generated files are really generated. |
| `git diff` on package.json, package-lock.json, tsconfig*, scripts, .prettierrc, CI workflow | No changes | No new dependency and no gate weakened. The eslint config diff is additive only: `reportUnusedDisableDirectives: 'error'` and `no-console: 'error'` on `src` outside tests. |
| Wire check of endpoints.ts against openapi.json | Match | Sign-in sends `login`. Username lookups are POST with a body. `already-added` is GET with a query, as contracted. Invite and student edit carry email. Student edit sends null to clear. `MemberResponse.phone` is nullable and `contactLine` guards it. |
| Bangla layout doc: 41 `key (n)` lengths recomputed from the bundles | All 41 match | The lengths are computed, not estimated. All 20 U4 rows are "not yet checked", and the document says so. |
| source-manifest.json against `git diff --name-only` | 79 paths, same set | The manifest is accurate. |
| Admin bundle | No `src/admin` file changed | The admin bundle is untouched. `api/client.ts` and `useResource.ts` changed only in abort handling and a lint comment. |

### Summary

I tried to refute the authorization gate, the client-side-rule boundary, the wire shapes and the async checker, and could not. The gate renders before the lens picker and every route, and it lifts only on a `reread()` that says not required. The failed-read card carries Sign out. The 3 s bound retires a lookup while a renewal is held open, and the rotated pair is still stored. Routing and abort tests are strong and non-vacuous. What remains is Minor: two scan tests that could catch more, a boundary fallback with no way out, an over-green traceability status, and one unchecked comment claim.
