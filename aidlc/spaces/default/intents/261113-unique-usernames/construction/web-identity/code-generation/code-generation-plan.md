# Code Generation Plan — web-identity (U4)

## Summary

- Builds: the web client for usernames and contacts: one-field sign-in, the sign-up username with live availability, the shared verify Replace step, the choose-username gate, Username and Phone and email in Settings, student emails with a new Edit sheet, centre invite by email. It also adds the regenerated API types and strings, the null-phone members fix, the route error boundary, `send()` abort handling, the reworded web-only strings, the `no-console` rule and the leak, lint-config and named-test guards.
- Touches: web/src/ (api/client.ts, api/endpoints.ts, api/schema.d.ts, i18n/generated/*, i18n/web/*.json, session/session.tsx, App.tsx, shell/, features/auth, features/account/{security,username,contacts}, features/teacher/{people,students,centre}, test/), web/eslint.config.js, docs/delivery/bangla-layout-check.md.
- Tests: roughly 170 Vitest and Testing Library tests (an estimate, not asserted) in about 25 new or extended test files. Written first and run red: the null-phone members render, the session's username-required state, gate-before-routes and lift-only-on-a-fresh-read routing, and the renewal-on-abort pin. Everything else is test-after.

## Inputs

Authoritative design, by path (the plan does not restate it):

- Functional design: `construction/web-identity/functional-design/` — `functional-spec.md` (§ 1 grounding and built defects 1–6, W1–W10, § 3 state machines, § 4 error handling per key, § 5 strings and the swept web-only list, § 7 corner sweep with verifiers, § 8 Bangla rows, § 9 differences from U3, § 10 structural concerns) and `frontend-components.md` (§ 1 hierarchy, § 2 state types, § 2.2a the code-step seam, § 3 events, § 4 API functions, § 5 routing, § 6 validation, § 7 strings, § 8 tests), both as revised after review 1 (R-01 to R-07).
- NFR requirements: `construction/web-identity/nfr-requirements/` — `security-requirements.md` (NFR1.1–1.4, NFR3.1–3.17, NFR8.7, NFR8.8, NFR4.1), `performance-requirements.md` (NFR8.1–8.6, NFR2.1–2.3), `tech-stack-decisions.md` (TSD-1–5, NFR5.1, NFR5.2, NFR6.1–6.3, NFR9.1), all with the review-01 folds (R-01 directive pin scan, R-02 the checker's own 3 s timer, R-03 the stubbed `indexedDB`, R-04 `namedTests.test.ts`).
- Contracts: `openapi.json` on this branch is authoritative (C1 as amended by U1, C2 as built by U2).
- U1, U2 and U3 are built on this branch. Nothing here changes backend or Android code.

**Corrections found while planning, applied by this plan.** These were read from the code, not run, because shell commands are refused before Plan Approval.

1. **Existing web tests encode the old sign-in.** `features/auth/SignIn.test.tsx` has two tests: "refuses a malformed number without calling the server" and "refuses a malformed email address without calling the server". It also asserts that the client normalises a Bangla-digit phone and lowercases an email. W3 removes every client shape check and sends the login trimmed, as typed. Step 15 rewrites those tests from W3's acceptance steps; they are not deleted silently. The same applies to `SignUp.test.tsx` cases that post `POST /v1/accounts` without `username` (Step 4), to `Members.test.ts` `inviteBody` cases, whose signature gains `email` (Step 21), and to any `security.test.tsx` case asserting the two Add rows in Settings (Step 19).
2. **Regenerating `schema.d.ts` breaks the typecheck before it fixes it.** Step 2 makes `npm run typecheck` red. At least `SignUp.tsx` is affected, because `username` is required, and `Members.tsx` too, because `formatPhone(m.phone)` receives a `string | null`. Steps 4 and 5 are what turn those compile errors green. The plan keeps that order on purpose: the compile error is the mechanism the functional design relies on (§ 1 defects 2 and 3).
3. **The route boundary resets on a pathname change, not through a `key`.** frontend-components § 5 says the boundary is rendered with `key={location.pathname}`. A key remounts everything under it on every navigation. That includes `AppShell` and its open sheets and fetched data, plus the gate and sign-in screens, which `App` also wraps. So Step 11 implements the same guarantee another way. The boundary receives `pathname` as a prop and, in `componentDidUpdate`, clears its error when the pathname changes. Recovery on navigation is kept, and remounts on navigation are avoided. *Deviation from the design, recorded for the code summary.*
4. **NFR4.1 classes every web test as test-after. This plan writes four groups first.** NFR4.1 reads the predicate as holding for no web code, because every authorization decision is the server's. U3's approved and built plan read the same predicate the other way for the client's routing: a wrong answer there grants or withholds a screen. The coordinator's brief for this unit asks for that reading. So Steps 5–9 write these tests first and run them red:
   - the session's `username-required` state;
   - gate-before-routes;
   - lift-only-on-a-fresh-read;
   - the members null-phone render;
   - the renewal-on-abort pin.
   Every other test stays test-after, written from its acceptance step, as NFR4.1 says. *Deviation from NFR4.1, recorded for the code summary.*
5. **The 3 s bound follows performance NFR8.3, not frontend-components § 2.2.** NFR8.3 explicitly amends § 2.2. The checker's own timer publishes could-not-check and retires the request at 3 s, even while `request()` is still awaiting a held-open `renew()`.

## Testing Contract

```json
{
  "version": 1,
  "methodology": "custom",
  "source": "team",
  "ordering": "Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
  "scope": "refactor",
  "test_strategy": "standard",
  "project_type": "brownfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt\nwithout its tests is not done.\n\n- **Methodology**: custom\n- **Methodology evidence**: The cadence genuinely differs by surface, and\n  recording a single uniform value would misdescribe what we actually do. Three\n  facts drive the split. (1) The money paths — fee-cycle arithmetic,\n  carry-forward, partial approval, waiver — have **mandatory** tests by stated\n  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than\n  I/O-shaped, and have expected values knowable before any implementation\n  exists. That is the exact precondition under which test-first pays: the test is\n  a specification we can write correctly without having written the code, and the\n  fee model is *already known to be in revision* [D-18], so a suite that pins the\n  arithmetic is what makes the next revision safe rather than frightening. (2) The\n  Compose UI surface is the opposite case. There is **no declared Kotlin or\n  Android experience** [OC-3], so a Compose test written before the\n  implementation is as likely to encode a misunderstanding of the framework as to\n  catch a defect, and when it passes it certifies that misunderstanding — worse\n  than no test. (3) The privacy boundary is structural rather than arithmetic\n  [D-7, TC-13] — enforced by table design, row-level security and distinct\n  response schemas — so its tests are adversarial probes against a built\n  boundary, which is inherently test-after. A uniform `tdd` would be a commitment\n  we would break on the Compose Bolts; a uniform `test-after` would weaken the\n  one surface where the requirement is explicit and the preconditions for\n  test-first are actually met. `custom` is the accurate value. *Re-confirmed\n  2026-10-22 against the built state: the money module shipped at 100% branch\n  coverage with the property-based ledger test, and the privacy suite shipped as\n  adversarial probes behind a superuser meta-check. The split described here is\n  the split that was actually practised.*\n- **Ordering**: Write the failing test first whenever **both** of these hold —\n  the correct output is knowable from the requirement without having written the\n  code, **and** a wrong answer would be a money error or an authorization error —\n  and for everything else implement the layer, then write and run that layer's\n  tests before the Bolt is complete.\n\nThat ordering is a **predicate, not a list**, and the distinction is the point:\nan enumeration plus \"everything else\" fails open, because every case nobody\nanticipated defaults to test-after. The following are *examples* of the\npredicate holding, not its boundary:\n\n- every change to the money module;\n- every fee-cycle and payment-verification state transition — generation,\n  carry-forward, partial and reduced approval, waiver, rejection;\n- the `(enrollment_id, period)` idempotency constraint;\n- every lens-resolution and row-level-security rule, wherever that code lives;\n- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,\n  leave existing dues standing, and leave the student active in other batches,\n  all three of which are money-adjacent and fail quietly;\n- the cross-batch dues query [PU-7.2], which is driven by outstanding balance\n  and not by active status, so students who left owing money still appear;\n- *(added 2026-10-22)* **acceptance state transitions in D1** — a seat moving\n  from pending to accepted or declined grants or withholds a guardian lens, so\n  a wrong answer is an authorization error and the predicate holds. This is the\n  gap the re-cut exists to close and it is test-first.\n\n**A change meeting the predicate does not escape it by being implemented in\nKotlin**, or in a route handler rather than in the money module. Where the code\nlives is not part of the test.\n\n**Test-after is a cadence, not permission to write the test against the\nimplementation.** A test-after test is written from the acceptance criterion. If\nwriting it requires reading the implementation to know what to assert, the\nacceptance criterion is the defect.\n\nSupporting bullets, which do not replace the two fields above:\n\n- **Backend coverage floor**: 80% line coverage, enforced in CI, with no\n  decrease permitted. This comes from the active `classic` scope at Comprehensive\n  test strategy and may not be weakened to make a step pass. **The authorization\n  layer is measured as branch coverage rather than line coverage** — lens\n  resolution is pure branching over teacher, student and guardian and owned-batch\n  membership, so line coverage on it is close to meaningless. *Measured\n  2026-10-22: 91% overall against the 80% floor, 615 tests passing. Met with\n  headroom.*\n- **The money module carries 100% branch coverage**, because the defects that\n  matter there live in the branches: the short-month clamp, the\n  carry-forward-versus-waive fork, the partial-approval path, the\n  zero-and-negative edges. An 80% line floor can be met while leaving the waiver\n  branch entirely unexecuted, which satisfies the number and misses the\n  requirement. Two things make that target honest rather than decorative: the\n  money module contains **no I/O, no session and no HTTP**, so 100% stays\n  reachable; and branch coverage is supplemented by obligations not reducible to\n  a percentage — a named test per fee-cycle and payment state transition, and a\n  documented boundary case per money input (period boundaries, rounding at the\n  half, zero, negative, an approved amount exceeding the claimed amount). We also\n  add one property-based test (Hypothesis) on the ledger invariant. *Measured\n  2026-10-22: 100.00%, `fail_under = 100` configured. Met. The invariant in\n  force is the corrected one recorded under Corrections, not the superseded\n  `charged - received - forgiven == outstanding`.*\n- **Android carries named obligations and no percentage floor.** Gating a surface\n  the reviewer cannot yet evaluate produces tests written to raise a number; that\n  is a reason to drop the *percentage*, not a reason to drop the *obligation*,\n  and this is the thinnest-reviewed part of the product. So:\n  - every ViewModel ships tests for its state machine — loading, success, error,\n    and the explicit retry path for a failed write [TC-8, D-9];\n  - every money-carrying model class ships a serialization test proving decode\n    from a JSON string and **loud failure** on a JSON number, because a lenient\n    decoder that quietly accepts a number and converts is the actual failure mode\n    and it passes a happy-path-only both-sides test;\n  - Kotlin line coverage is reported from the first Android Bolt, with **no\n    decrease permitted** once three Android Bolts have merged. A no-regression\n    ratchet gives the trend teeth without anyone inventing a target they cannot\n    justify.\n\n  **The first two obligations were met and the third was not.** *(Reconciled\n  2026-10-22.)* 137 `@Test` functions across 14 files, targeting the mapping\n  functions rather than untargeted ViewModels, which is what the practice asked\n  for; `MoneySerializerTest` and `NoFloatingPointTest` cover the money boundary\n  including loud failure on a JSON number. But there is **no Kotlin coverage\n  report of any kind** — no JaCoCo, no Kover — and three Android Bolts have\n  merged, so the ratchet that should now be in force has no number to ratchet.\n  The obligation stands and the mechanism is assigned to **before D1**: a Kover\n  report from the next Android Bolt, with the no-decrease rule arming on the\n  first merged figure. Starting the ratchet now costs one plugin line and\n  establishes the baseline before five more units of Kotlin land; starting it\n  after D6 would baseline against the finished app and ratchet nothing.\n- **Test types by layer**: pytest for backend unit and integration tests, with\n  integration tests running against a **real PostgreSQL 16** container via\n  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,\n  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and\n  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin\n  ViewModel and repository tests, targeting the response-to-UiState mapping\n  function rather than an untargeted \"the ViewModel\". Compose UI tests for the\n  OTP entry path and the mid-class attendance path.\n- **The integration suite must assert that it ran.** *(Added 2026-10-22.)*\n  `tests/conftest.py` skips the whole integration suite at module level when no\n  Docker daemon is reachable, so on a machine without Docker `make check` passes\n  having run none of the row-level-security probes, none of the migration tests\n  and none of the roster tests, signalling only a pytest skip line. The skip\n  itself is reasonable. What is missing is the precondition assertion this\n  project applies to Gitleaks and not to its own database suite: **CI asserts\n  Docker was present and the integration suite actually ran.** A runner image\n  change that dropped Docker would otherwise silently narrow the suite to its\n  unit half, and the privacy boundary is the thing that would stop being tested.\n  Costs one step; assigned to **before D1**.\n- **Database tests connect as a restricted non-superuser role.** PostgreSQL\n  documents that superusers and table owners bypass row-level security entirely\n  [pg-rls], and the default test-container connection is `postgres`, a superuser.\n  A privacy-boundary suite run as superuser passes identically whether the policy\n  is correct, broken, or entirely absent — so the strongest test obligation we\n  have would certify nothing. Integration tests therefore connect as the same\n  restricted role the application uses, and a **meta-test asserts that\n  `current_user` is not a superuser and that row-level security is in force**\n  (`row_security` on, policy present) before the privacy suite runs. *Verified\n  2026-10-22: built, as `shikkhok_app`, enforced by a collection reorder and an\n  autouse re-check. This is the practice working exactly as written.*\n- **Privacy boundary tests are adversarial, and the API-level half is a\n  schema-wide invariant.** No teacher-lens response schema may contain any field\n  in the owner-private profile set, enforced by iterating the generated OpenAPI\n  schema rather than by remembering to write a test per endpoint — per-endpoint\n  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking\n  about it. The probe suite explicitly covers the IDOR shape: teacher A\n  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a\n  student requesting a fee cycle not their own.\n- **Schemathesis validates conformance, not correctness, and never counts as\n  privacy coverage.** We keep Schemathesis for what it is good at — unexpected\n  500s, type and required-field drift, auth present on every route — and we add\n  the check it cannot provide: **an OpenAPI schema-diff gate**, where the\n  committed schema must match the generated one and CI fails if they diverge.\n  *Built 2026-10-22: the schema-diff gate exists and works. Schemathesis itself\n  does not. That is the right half to have built first — the practice says so —\n  and the conformance half remains outstanding at Low severity, unassigned. We\n  are not assigning it to a unit: it is a genuine nice-to-have, and naming a\n  unit for it would be the same empty promise this run is correcting.*\n- **Money representation is itself a test target.** Every money value crosses the\n  API as a JSON **string** [TC-7, D-20], asserted on both sides.\n- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle\n  guarantee is a database constraint precisely because application-level guards\n  fail under concurrency [D-21, TC-12]. The test runs overlapping generations\n  and asserts the **outcome**: after N overlapping generations exactly one row\n  exists per `(enrollment_id, period)` and the ledger total is unchanged. It also\n  covers the case concurrency alone misses — the daily self-healing re-run\n  [PU-5.5] must be idempotent across *days*. **This lands in D3 and has not been\n  exercised yet**, because fee cycles are not built.\n- **Token lifecycle is tested as a state machine.** Refresh-token rotation with\n  reuse detection has a security-critical failure mode: present a rotated-out\n  token and the whole token family must be invalidated.\n- **Both account-deletion paths are tested** [TC-19]: the in-app path and the\n  externally accessible route. Each must assert that deletion removes what the\n  Data Safety form claims it removes and retains only what the privacy policy\n  discloses [RC-4, RC-5], per each table's written disposition. Deletion features\n  are the ones most reliably shipped broken, because nobody tests the absence of\n  data. **This is D6** and neither path exists yet; `PUBLIC_ROUTES` already\n  allowlists both, so D6 lands handlers against entries that exist rather than\n  adding new ones.\n- **PU-3.6's mid-class speed requirement is not discharged by a correctness\n  test.** Either the attendance obligation is a **Macrobenchmark on a low-end\n  device profile** (which also serves TC-17), or PU-3.6 has no automated\n  verification in V1 and carries an explicit manual check in the pilot. Both are\n  acceptable; silently using a correctness test to discharge a performance\n  requirement is not. **The harness does not exist and is assigned to D5** by\n  the delivery plan, while the attendance screen it measures lands in D4. That\n  ordering is backwards and the delivery plan records it as an open question;\n  this practice does not resolve it, it only insists the obligation is not\n  discharged by a Compose correctness test in D4.\n- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:\n  Compose screenshot tests at the longest Bangla string, or an explicit\n  per-screen manual check. \"Must not break the layout\" currently has no verifier,\n  and an unverifiable obligation is a wish. *(Reconciled 2026-10-22.)* **The\n  hard half is done and the verifier is absent.** Both bundles are complete at\n  53 strings each and no user-facing string is hard-coded. But there is no\n  Paparazzi, no Roborazzi, no screenshot infrastructure of any kind, and no\n  written per-screen manual check either — so of the two verifiers the practice\n  offered, neither exists, across three shipped screens. The practice's own\n  sentence applies to itself: this obligation is currently a wish. Both options\n  remain acceptable and the choice is the human's at this gate; what is not\n  acceptable is a fourth, fifth and sixth unit of screens shipping with neither.\n- **One command, local and in CI.** `make check` or equivalent, the same\n  entrypoint in both places. For a solo build this is the single most important\n  property of the gate: a gate reproducible only by pushing is a gate that gets\n  bypassed. The blocking suite needs no secret to run locally. *Verified\n  2026-10-22: `make check` is the CI entrypoint. Working as intended.*\n- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if\n  minutes become a real constraint. The Android job is split from the backend job\n  so a Kotlin build does not gate a backend PR, dependencies are cached, and the\n  backend path stays under about ten minutes. *Verified 2026-10-22: split, with\n  ten- and fifteen-minute timeouts, concurrency groups and `cancel-in-progress`\n  on checks but not on deploys. Built well.*\n- **A green `main`, not just a green PR.** With squash-merge and one reviewer, a\n  PR green against an older `main` can merge and break it. The post-merge run was\n  removed on 2026-10-19 at the user's instruction (\"don't run actions on merge\"),\n  and the obligation moves to GitHub's **\"Require branches to be up to date\n  before merging\"** under branch protection. **That setting is repository\n  configuration and cannot be verified from the repository.** If it is off, this\n  obligation has no verifier. We flag it as the one practice whose status this\n  run genuinely cannot establish; confirming it is a thirty-second check in the\n  repository settings and worth doing before D1.\n- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.\n  Tests that always pass regardless of implementation are defects in their own\n  right and are rejected in review.\n\n---"
    }
  ],
  "obligations": {
    "strategy": "standard",
    "strategy_volume": [
      "Five to eight tests per component.",
      "Unit tests plus integration tests for key boundaries.",
      "Add E2E, performance, or security tests when requirements demand them."
    ],
    "scope_floor": [
      "Keep the existing test suite green.",
      "This scope adds no extra new-test floor beyond the selected test strategy."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "custom",
    "runner_step": "Verify the existing test runner/configuration and record the exact unit-scoped command.",
    "runner_ready_before_first_test": true,
    "testable_layers": [
      "Data model / database behavior",
      "Repository / data access",
      "Business logic",
      "API / endpoint",
      "Frontend behavior"
    ],
    "steps": [
      "Project structure and production configuration skeleton.",
      "Verify the existing test runner/configuration and record the exact unit-scoped command.",
      "Custom ordering - Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
      "Implementation and tests - preserve that exact ordering; do not convert it to layer-local TDD.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:4ff9b391e45f162f1b245cc5ed556fb56891a688dd48068b3f9ac7245b8558c3",
  "contract_sha256": "sha256:fafb7d5d3d6e0974896ba3eb5b3770ea2c6ec67e7266749c288cd74d308e09f2"
}
```

How the contract applies here: **the predicate holds where a wrong answer
grants or withholds a screen, or ends a session.** That covers:

- the session state that decides whether the gate or the app is rendered
  (`sessionFromMe`, `username-required`, the interim publication during a
  re-read);
- `App`'s routing on it: gate before any route, typed URL and history
  included, lift only on a fresh read saying `false`, a read landing in
  Saving ignored, the failed card with Sign out;
- the members null-phone render, which today unmounts the whole app for
  every manager of a centre with an email-only invitation, so no manager
  can reach the screen where access is revoked;
- token renewal surviving an aborted caller. A lost rotated pair makes the
  next renewal present a rotated-out token, and the server then revokes the
  whole family: every device is signed out.

The output of each is knowable from the design (functional-spec W4, § 3.3,
§ 3.4; § 1 defects 2 and 5; security NFR3.14, NFR3.15, NFR8.7). So their tests
are written and run before the code that satisfies them (Part B). The renewal
test is a pin on code the design read as already correct. It is written before
Step 10 touches `client.ts`. It is expected green, and if it is red that is a
found defect: the build stops there and records it. Every authorization
decision behind these tests is the server's. What the client can get wrong is
which screen it shows and whether it keeps its tokens, and that is what these
tests pin. Everything else is test-after: implemented, then tested from its
acceptance step before the Bolt is complete.

## Steps

### Part A — structure, runner and the generated sets

- [x] **Step 1: Runner and baseline.**
  - `web/node_modules` is absent, so first run `cd web && npm ci --no-audit --no-fund`. That is the same locked install `make web` performs; it changes no lockfile.
  - Then run `cd web && npx vitest run src/session/session.test.ts src/api/client.test.ts` and confirm it runs green.
  - Record the baselines this plan expects red, by reading the code:
    - `cd web && npm run check:generated` (stale `schema.d.ts` and strings);
    - `cd web && npx vitest run src/i18n/i18n.test.ts` (15 server keys unmapped).
  - Also record the result of `cd web && npm run typecheck` and `npm run lint`.
  - Record what each prints in the code summary.
  - All unit-scoped commands are in `unit-test-instructions.md`.

  *(NFR5.2 baseline)*
- [x] **Step 2: Regenerate the API types and the strings.**
  - Run `cd web && npm run gen:api` and `npm run gen:strings`.
  - Commit the regenerated `src/api/schema.d.ts` and `src/i18n/generated/{strings.en,strings.bn,message-keys}.json` as their own commit, `chore(web): regenerate API types and strings`, so the generated diff is reviewable apart from hand-written code.
  - `npm run check:generated` goes green.
  - `npx vitest run src/i18n/i18n.test.ts` goes green: every committed server key now resolves, in both languages.
  - `npm run typecheck` is expected red here (correction 2), and its errors are recorded. Nothing is suppressed to quiet them.

  *(functional-spec § 1 defect 1, § 5; FR11.2 strings half; NFR9.1, NFR5.2)*
- [x] **Step 3: Web-only strings: reworded, removed and new.** These are in `src/i18n/web/{auth,core,account,students}.{en,bn}.json`, English and Bangla together.
  - **Reworded:** the swept rewordings exactly as functional-spec § 5 lists them, in both languages: `web_auth_signin_body`, `web_auth_point_login`, `web_password_set_body`, `web_auth_signup_phone_help`, `web_auth_signup_email_help`, `web_contact_add_phone_why`, `web_contact_add_email_why`, `web_students_col_phone`, `web_students_no_phone` and `web_roster_col_contact`.
  - **Removed:** `web_auth_password_wrong`, from both languages.
  - **New:** frontend-components § 7's new keys: `web_auth_replace_username_body_plain`, `web_students_add_by_email`, `web_student_edit_title`, `web_student_edit_save`, `web_student_edit_saved`.
  - Tests: `src/i18n/i18n.test.ts` stays green, including bundle parity and the `web_` prefix check. Extend it with:
    - one assertion that `web_auth_password_wrong` is absent from both bundles;
    - one assertion per reworded key that its English text equals § 5's.

  *(FR11.2; functional-spec § 5, W10)*
- [x] **Step 4: Sign-up sends the required username.**
  - `features/auth/SignUp.tsx` gains the Username field above the passwords, using `signup_username_label` and `signup_username_help`, with the trimmed value sent as `username`.
  - A blank value shows `signup_username_required` under the field.
  - `account.username.*` (400) and `account.username.unavailable` (409) from `POST /v1/accounts` land under Username, and every other field keeps its value.
  - The autofill tokens move: the username input carries `autocomplete="username"`, and the phone or email field drops `name="username"` and takes `tel` or `email` (`identifierInputProps` gains the `contact` purpose there).
  - The live hint is wired in Step 14. Here the field is plain, so the typecheck error from Step 2 for `SignupRequest` goes green.
  - Tests (test-after), in `features/auth/SignUp.test.tsx`:
    - the body carries `username`, trimmed;
    - a blank username blocks submit with the key;
    - each username refusal lands under the field with the other fields kept;
    - the autocomplete attributes.
    - Existing cases that posted without `username` are updated to send one (correction 1).

  *(functional-spec § 1 defect 3, W1 steps 1, 6–8; FR2.1, FR11.1)*

### Part B — test-first: what decides which screen is shown and whether the session survives (written and run first)

- [x] **Step 5: Members list with an email-only invitation, regression first.**
  - **Red:** in `features/teacher/centre/Members.test.ts`, add a pure `contactLine` case: phone formatted when non-null, `invited_email` when the phone is null, `null` when both are null.
  - **Red:** in `centre.screens.test.tsx`, render the members screen with a list containing `{"phone": null, "invited_email": "rina@example.com", …}` and assert it renders the email and does not throw.
  - Run both red. The render case fails with the `null.replace` TypeError traced in functional-spec § 1 defect 2.
  - **Green:** `Members.tsx` exports `contactLine(m)`. Each card renders the line it returns, and `formatPhone` is never called with `null`. The Step 2 typecheck error for `Members.tsx` goes green.

  *(functional-spec § 1 defect 2, W8 step 5; NFR6.2; FR6.4, FR11.1)*
- [x] **Step 6: Renewal survives an aborted caller, pinned first.** In `src/api/client.test.ts`, written before Step 10 touches `client.ts`:
  - signed in with a stale access token, `/v1/auth/refresh` is held open by the fetch mock;
  - a lookup's `AbortController` is aborted while `request()` awaits renewal;
  - the refresh is then released.
  - Assertions:
    - the rotated pair is in `sp.session`;
    - a second `request()` sends the new access token;
    - the refresh route was called exactly once.

  Run it. **Expected green**, because the design read the structure as correct (functional-spec § 1 defect 5). If it is red, that is a found defect: stop and record it before any further step. It must stay green through every later step. *(NFR8.7; functional-spec § 1 defect 5)*
- [x] **Step 7: The session's username-required state, tests first.**
  - In `src/session/session.test.ts`, add `sessionFromMe`:
    - `username_required: true` gives `{ state: 'username-required', me }`;
    - `false` gives the `ready` value `resolveLens` and `reconcileWorkspace` produce today;
    - an absent flag gives `ready`.
  - Add minimal signatures only, so the tests compile and fail on their assertions: the `username-required` arm of `Session`, an exported `sessionFromMe` stub, and a `reread()` stub on the context value. Run red.

  *(FR5.1, FR5.2, FR5.3; NFR3.14, NFR6.3, NFR8.5)*
- [x] **Step 8: Gate before routes, and lift only on a fresh read, tests first.**
  - New `src/session/usernameGate.routing.test.tsx`. It renders `App` signed in under `BrowserRouter`, as `src/main.tsx` does, with a fetch mock that answers `GET /v1/me` per test.
  - Cases, named for what they assert:
    1. `the first render after resolving is the gate when the read says true`: the lens picker, the shell and every route's content never render. The mock records exactly one `/v1/me` before the gate shows.
    2. `a typed URL renders the gate`: the starting location is `/settings`.
    3. `history back and forward render the gate`: `window.history.pushState`, then `history.back()` and `history.forward()`.
    4. `a 200 from PUT /v1/me/username lifts the gate only when the next read says false`.
    5. `a 200 followed by a read still saying true returns to editing with a re-read retry`.
    6. `password_required re-reads with no password asked, and lifts on false`.
    7. `a visibility read landing during Saving is ignored`, in both cases: it says true, and the `PUT` answer then leads to Rereading; it says false, and `ready` renders while the late `PUT` answer renders and throws nothing.
    8. `visibilitychange sends one read in Editing and none in Saving or Rereading`.
    9. `a re-read while the gate shows never renders the resolving loader`.
    10. `a failed re-read shows the error card, not the app, and its Sign out clears the tokens`, also for a non-retryable failure where the card shows no Retry.
    11. `Sign out from the gate clears sp.session and calls POST /v1/auth/logout`.
  - A placeholder `features/account/username/ChooseUsernameGate.tsx` lets the test compile. It carries only its `data-testid`, a username input and Continue and Sign out buttons.
  - Run red.

  *(FR5.2, FR5.3, FR5.4; NFR3.14, NFR3.15, NFR3.16, NFR8.5, NFR8.6; functional-spec W4, § 3.3, § 3.4)*
- [x] **Step 9: Session state, `App` branch and the gate, green.**
  - `session/session.tsx`:
    - `sessionFromMe`;
    - the `username-required` state;
    - `reread(): Promise<void>`, which starts the same read as `refresh()` and settles when it settles;
    - the interim publication keeping both `ready` and `username-required`.
  - `App.tsx`:
    - the `username-required` branch after `failed` and before `choosing`;
    - the failed branch gains a Sign out text button (`more_log_out`) calling `signOut()`.
  - `features/account/username/ChooseUsernameGate.tsx`, replacing the placeholder:
    - the `GateState` of frontend-components § 2.4: Saving, then Rereading through `reread()`;
    - a changed `me` is acted on only in Rereading;
    - the `visibilitychange` listener is attached only in Editing;
    - focus on the field when it mounts;
    - the field is plain until Step 14 wires the authenticated hint.
  - Steps 7–8 go green.
  - Test-after, new `features/account/username/ChooseUsernameGate.test.tsx`, covering W4 step 6's outcomes:
    - format key and `unavailable` under the field;
    - 429 in the banner with Continue available;
    - 503 and transport with Retry resending the same choice;
    - double submit ignored;
    - focus on mount;
    - Sign out is a `button`.

  *(functional-spec W4 steps 1–11; frontend-components § 2.3, § 2.4, § 5)*

### Part C — implementation, then each layer's tests (test-after)

- [x] **Step 10: `send()` treats any aborted signal as cancelled.**
  - `api/client.ts` `send()`: in its `catch`, rethrow when `options.signal?.aborted` is true, before mapping to `networkError()`.
  - `renew()` is unchanged and gains no signal.
  - Tests, in `src/api/client.test.ts`:
    - a signal aborted with a string reason rejects with that reason;
    - `AbortSignal.abort(new DOMException('', 'TimeoutError'))` rejects with the reason, not an `ApiError` of `error.network.unreachable`;
    - a plain `fetch` rejection with no abort still maps to `error.network.unreachable`.
  - Step 6 stays green.

  *(NFR8.8; functional-spec § 9 item 6)*
- [x] **Step 11: Route error boundary.**
  - New `src/shell/RouteErrorBoundary.tsx`, a class component. `App` wraps everything it returns in it and passes `pathname={useLocation().pathname}`.
  - On a render error it shows `ErrorCard` with `new ApiError(500, 'UNEXPECTED', UNEXPECTED_KEY, true)`, so `error_unexpected` and `auth_retry` appear.
  - Retry clears the error. `componentDidUpdate` clears it when `pathname` changes, and there is no `key` (correction 3).
  - It logs nothing.
  - Tests, new `src/shell/RouteErrorBoundary.test.tsx`:
    - a child that throws during render shows the card, not a blank root;
    - navigating to another path renders that route;
    - Retry renders the children again;
    - a navigation that changes only the search string does not remount a healthy subtree (a mount counter).

  *(functional-spec § 10 item 2; frontend-components § 5)*
- [x] **Step 12: The email check counts code points.**
  - `features/auth/identifier.ts` `readIdentifier` compares `[...email].length` with 254. The pattern is unchanged.
  - Tests, new `features/auth/identifier.test.ts`:
    - `a@b.c.` and `a@.b.c` accepted;
    - `a@b`, `@b.c` and an address containing whitespace refused;
    - 254 code points of astral characters accepted;
    - 255 code points refused;
    - trimming and lowercasing unchanged.
  - Existing add-contact tests stay green.

  *(functional-spec § 1 defect 4; NFR3.12; FR11.3)*
- [x] **Step 13: API functions.** In `api/endpoints.ts` and the feature `api.ts` files, exactly frontend-components § 4:
  - `signInWithPassword(login, password)`;
  - `verifyCode(identifier, code, username?)`;
  - `checkUsername` and `checkMyUsername` (POST, body, signal);
  - `setMyUsername(username, password | null)`, with the password omitted for the first choice;
  - `requestContactCode(identifier, password?)`;
  - `removeContact(kind, password)`;
  - `lookupAlreadyAdded({phone} | {email})`;
  - `createStudent` and `updateStudent` bodies carry the emails;
  - `inviteMember` takes `phone` and/or `email`.

  Tests, in `src/api/client.test.ts` (fetch mock): each function's method, path and JSON body. There is **no query string** on:
  - both lookups;
  - `PUT /v1/me/username`;
  - `POST /v1/auth/password`;
  - `POST /v1/me/contact`;
  - `POST /v1/me/contact/remove`.

  Further cases:
  - the `/v1/auth/password` body has `login` and `password` and no `phone` or `email` key;
  - `verifyCode` carries `username` only when one is passed;
  - refusal envelopes come back as `ApiError` with their key.

  *(FR3.1, FR4.1, FR5.4, FR6.1, FR6.4, FR6.7, FR7.1, FR8.2; NFR1.2, NFR3.1, NFR9.1)*
- [x] **Step 14: The availability checker and the username field.**
  - New `features/auth/username/availability.ts`: the `Availability` type and `mapAvailability`. An unknown status maps to could-not-check.
  - New `features/auth/username/useUsernameAvailability.ts`, with:
    - the 500 ms debounce;
    - one `AbortController` per request, a newer request aborting the older, with the `superseded` flag set before `abort()`;
    - the per-text answer `Map`;
    - stop after a 429;
    - **the checker's own 3 s timer**, which at 3 s sets `timedOut`, publishes could-not-check, retires the request and aborts it, without waiting for it to settle;
    - the settle step's first check: "this request is still the current one, else drop".
  - New `UsernameField.tsx`: the trimmed value capped at 64 code points in the change handler, not while `isComposing`, and no HTML `maxlength`.
  - New `AvailabilityHint.tsx`: a `role="status"` element present from Idle.
  - The checker is wired into sign-up (public lookup) and the gate (authenticated lookup).
  - Tests:
    - new `features/auth/username/availability.test.ts`: one state per status, no held-or-taken distinction, unknown status;
    - new `features/auth/username/useUsernameAvailability.test.ts` under `vi.useFakeTimers()`:
      - none at 499 ms and one at 500 ms;
      - an edit restarts the wait;
      - nothing for empty or whitespace text;
      - an edit while held open aborts it (the mock sees `signal.aborted`) and the late answer never renders;
      - a remembered text makes no call;
      - **a fetch mock that ignores its signal and never settles gives could-not-check at 3,000 ms and not at 2,999 ms**;
      - **signed in with a stale token and `/v1/auth/refresh` held open for 5 s, could-not-check at 3,000 ms while the refresh is pending; once the refresh answers, the lookup's late result changes nothing on screen and the rotated pair is stored**;
      - a retired request answering 200 after 3 s leaves could-not-check, and the next edit checks again;
      - after a transport failure there is no call until an edit;
      - after a 429 there is no call at all, even after edits and 500 ms of quiet;
    - new `features/auth/username/UsernameField.test.tsx`:
      - 65 trimmed code points refused, 64 accepted, 64 with surrounding spaces accepted, 21 accepted;
      - an `isComposing` input is not cut;
      - the hint's `status` role is present in Idle, and its text becomes `username_available` after an `available` answer.
  - Sign-up submission is never gated on the hint; this is asserted in `SignUp.test.tsx`.

  *(FR3.1, FR3.2, FR11.3; NFR1.3, NFR2.1, NFR2.3, NFR3.11, NFR6.3, NFR8.1, NFR8.2, NFR8.3; TSD-1, TSD-5)*
- [x] **Step 15: One-field sign-in, with no route state.**
  - `features/auth/SignIn.tsx`:
    - one `auth_login_label` field with `type="text"`, `autocomplete="username"`, `autocapitalize="none"` and `spellcheck="false"`;
    - no `KindToggle`;
    - non-blank is the only check;
    - it sends `signInWithPassword(login.trim(), password)`;
    - `email.invalid` shows under the field, and everything else goes in the banner;
    - the three links to `/signin/code` carry no `state`.
  - `features/auth/PasswordCode.tsx` drops `CodeFlowEntry` and its `useLocation().state` read. Its toggle stays (FR10.1).
  - Tests, in `SignIn.test.tsx`, rewritten from W3 (correction 1):
    - a username, a phone and an email are each sent as typed and trimmed, in `login`;
    - `auth.password.wrong` and `too_many_attempts` render as before, with the code-flow link;
    - `email.invalid` shows under the field;
    - no `state` is passed to `/signin/code`;
    - the MFA cases stay green.
  - In `PasswordCode.test.tsx`: it starts empty with the toggle.

  *(FR4.1, FR4.2, FR10.1, FR11.1; NFR1.1, NFR1.2; functional-spec § 1 defect 6)*
- [x] **Step 16: Sign-up email lookup and the password-manager username.**
  - `SignUp.tsx`: when the email field is left holding an address the shared check accepts, it calls `lookupAlreadyAdded({ email })`. This happens once per value, remembered, with a late answer for a changed value dropped and the role locked on a seat. A refusal or a failure shows nothing and never blocks.
  - The header comment's sentence "An email address is never looked up" is corrected.
  - `ChoosePassword.tsx`'s `HiddenUsername` carries the chosen username after a sign-up, and the phone or email in the code flow (`setupFrom` takes an optional username).
  - `security/Password.tsx`'s `HiddenUsername` carries `me.username ?? me.phone ?? me.email`.
  - Tests, in `SignUp.test.tsx`:
    - the email lookup runs once per value, locks the role on a seat, and a failure shows nothing;
    - `HiddenUsername` holds the chosen username on the password step.
  - In `security/password.test.tsx`: `HiddenUsername` holds `me.username`.

  *(FR6.7, FR11.1; functional-spec W9, § 7 password managers)*
- [x] **Step 17: The code-step seam and the Replace step.**
  - `features/auth/parts.tsx` `CodeEntry` gains `initialError` and `resendAvailableAt` (frontend-components § 2.2a). The default equals today's behaviour.
  - New `features/auth/ReplaceUsernameStep.tsx`: Username field with the public hint, Continue, Back, focus on mount.
  - `SignUp.tsx` and `PasswordCode.tsx` each own the `code | replace` switch, a `heldCode` ref and `sentAt`.
  - On a 409 `account.username.unavailable`, `verify` stores the code, switches to `replace` and resolves.
  - Replace's `submit` calls `verifyCode(identifier, heldCode, username)`.
  - On `auth.otp.expired`, `no_tries_left` or `not_valid`, the owner:
    - clears the held code;
    - remounts `CodeEntry` with that key's message as `initialError`;
    - sets `resendAvailableAt = sentAt + RESEND_AFTER_S * 1000`.
  - A successful Resend sets a new `sentAt`. Back forgets the code and, in sign-up, the held password.
  - Tests:
    - in `SignUp.test.tsx`:
      - a 409 opens Replace, and `CodeEntry` never shows it;
      - the retry sends the same code with the replacement;
      - username refusal and 429 stay on Replace, and transport offers Retry;
      - **an expired code on the retry, with the original send 90 s earlier under fake timers, shows the `auth.otp.expired` message with the field empty and Resend enabled; with the send 20 s earlier, Resend counts down from 40**;
      - after an OTP refusal the next verify sends only newly typed digits;
      - after Back and a fresh 409, the retry sends the new digits;
      - the body names the W1 username and no response field;
    - in `PasswordCode.test.tsx`: the same Replace path with `web_auth_replace_username_body_plain`;
    - a `parts.test.tsx` case for `CodeEntry`: `initialError` on mount, and `resendAvailableAt` in the past enabling Resend at once.

  *(FR2.2, FR11.1; NFR1.4, NFR3.6; functional-spec W2, § 3.2; frontend-components § 2.2a)*
- [x] **Step 18: Username in Settings.**
  - New `features/account/username/UsernameScreen.tsx` at `securityPaths.username()`, with the `UsernameState` of § 2.5:
    - the authenticated hint;
    - the current password with `autocomplete="current-password"`;
    - `username_rule_note`;
    - `next_change_at` and `details.next_change_at` rendered by `formatDateTime`, not through `MESSAGE_ARGS`.
  - The password is cleared on every answer, and `refresh()` runs after a 200.
  - Registered in `securityRoutes`.
  - The Username row is added to `AccountEntries.tsx`, with the subtitle `me.username` or `more_username_choose`, greyed offline.
  - Tests, new `features/account/username/username.test.tsx`:
    - every outcome of W5 step 5;
    - the date from `next_change_at`, from `details.next_change_at`, and a missing detail giving the plain string;
    - Change always present;
    - the password cleared after `current_wrong`;
    - double submit ignored;
    - Retry resends the same request.
  - In `security.test.tsx`: the Username row.

  *(FR7.1, FR7.2, FR7.5, FR11.1, FR11.3; NFR3.13; functional-spec W5)*
- [x] **Step 19: Contacts: view, add, replace, remove.**
  - New `features/account/contacts/`:
    - `mappers.ts` `contactCards(me)`;
    - `ContactsScreen.tsx` at `securityPaths.contacts()`;
    - `ReplaceContact.tsx` at `securityPaths.replaceContact(kind)`, which drops the password after the code request;
    - `RemoveContactSheet.tsx`, keyed per opening, with focus on the password, `dirty` while typed, and `last_one` shown in the sheet with Add another.
  - `AccountEntries.tsx` replaces the two Add rows with Phone and email.
  - `AddContact.tsx` navigates back to Contacts.
  - Every write calls `refresh()`.
  - Tests:
    - new `features/account/contacts/contacts.test.tsx`:
      - both present, phone only and email only;
      - one present contact still yields Remove;
      - `has_password: false` shows the note with the actions enabled;
      - Replace's request refusals are routed per W6 step 4.3, its 200 drops the password, and its verify refusals stay;
      - Remove's 200, `last_one`, `current_wrong` and `password_required`, and transport Retry resending `{kind, password}`;
      - reopening the sheet starts fresh;
      - focus on the sheet's password;
    - `security.test.tsx`: the Phone and email row replaces the Add rows (correction 1).

  *(FR8.1, FR8.2, FR8.3, FR8.4, FR11.1, FR11.3; NFR3.13; functional-spec W6)*
- [x] **Step 20: Student emails, the Edit sheet and the quick-add link.**
  - `features/teacher/people/NewStudent.tsx` gains two email fields with `autocomplete="off"`. They are checked by the shared email check and sent trimmed, and omitted when blank.
  - New `people/EditStudentSheet.tsx` on `StudentDetail.tsx`:
    - name, both phones and both emails;
    - `studentEdit(original, typed)` in `people/mappers.ts`, which returns `null` when unchanged and an explicit `null` for any emptied contact;
    - refusals per W7 step 6;
    - focus on the first field.
  - `people/mappers.ts` gains the emails and `studentContactLine`/`guardianContactLine`. `StudentsList.tsx` and `StudentDetail.tsx` render those lines.
  - `students/mappers.ts` `mapSeats` reads both emails. The declined label uses phone, then email, then `roster_declined_no_number`.
  - `students/AddStudent.tsx` gains the `web_students_add_by_email` link to `paths.studentNew(batchId)`. Its request and required fields are unchanged.
  - Tests:
    - `people.test.tsx`:
      - `studentEdit`: unchanged gives `null`, an emptied email or emptied phone gives `null` in the body, a changed value is sent;
      - a 409 `student.number_accepted` on clearing a phone renders in the sheet banner;
      - `student.email.taken` under the field;
      - the line functions, phone then email;
      - `autocomplete="off"` on all four email inputs;
      - focus on the Edit sheet;
      - fixtures carrying an extra unknown field decode;
    - `students.test.tsx` and `students/mappers.test.ts`:
      - `mapSeats` with a guardian email;
      - the declined label;
      - the quick-add link's target.

  *(FR6.1, FR6.2, FR6.3, FR11.1; NFR3.8, NFR6.1; functional-spec W7, Q4, Q6)*
- [x] **Step 21: Centre invite by email.**
  - `features/teacher/centre/Members.tsx`:
    - an email field with `autocomplete="off"`, plus `centre_invite_by_help`;
    - `inviteBody(name, phone, email, role)`, which returns `null` unless the name is non-blank, at least one contact is non-blank, and each non-blank value is well-formed;
    - blanks omitted.
  - Tests:
    - `Members.test.ts`: phone only, email only, neither (`null`) and a malformed email (`null`). The existing cases are updated for the new signature (correction 1).
    - `centre.screens.test.tsx`:
      - an email-only invite posts `email` and no `phone`;
      - `centre.member.already_invited` in the banner;
      - `autocomplete="off"`.

  *(FR6.4, FR11.1; NFR3.8; functional-spec W8)*

### Part D — environment/build configuration and the mechanical guards

- [x] **Step 22: `no-console`, and the lint-configuration pin.**
  - `web/eslint.config.js`:
    - `'no-console': 'error'` with no allowed method, on `src/**/*.{ts,tsx}`, test files excluded;
    - `linterOptions: { reportUnusedDisableDirectives: 'error' }`.
  - `src/core/useResource.ts:104` and `src/features/family/pay/PayScreen.tsx:79` each get `// eslint-disable-next-line no-console -- <reason>`.
  - No rule is weakened, and `--max-warnings 0` is unchanged.
  - New `src/test/lintConfig.test.ts`, with `// @vitest-environment node`:
    - ESLint's `calculateConfigForFile` gives `no-console` at `error` for a `src` file, and does not apply it to a test file;
    - a scan of every non-test `.ts`/`.tsx` under `src`, excluding `src/api/schema.d.ts` and `src/i18n/generated`, for every inline directive matching security NFR3.5's regular expression. The result is compared as a multiset of (file, trimmed directive text) with counts, against the exact committed list: the two existing `react-hooks/exhaustive-deps` directives (`ui/components.tsx`, `core/useResource.ts`) and the two `no-console` exemptions.
  - `cd web && npm run lint` green.

  *(NFR3.5; TSD-2; functional-spec § 7, § 10 item 6)*
- [x] **Step 23: No identifier leaks.** New `src/test/noIdentifierLeaks.test.tsx`.
  - **Setup.** It mounts the flows under `BrowserRouter` (TSD-4), with `vi.stubGlobal('indexedDB', { open: vi.fn() })` and `vi.unstubAllGlobals()` after.
  - **Flows driven:** sign-in, sign-up through a 409 and Replace, the gate and rename. Each uses one distinctive sentinel per value: username, login, phone, email, password and code.
  - **After every step it snapshots:**
    - every `localStorage` and `sessionStorage` value;
    - `JSON.stringify(window.history.state)`;
    - `document.title`;
    - `window.location.href`;
    - every argument to a spied `console.log`, `info`, `warn`, `error` and `debug`.
  - **It fails if** any sentinel appears in any of them, or if `indexedDB.open` was called.
  - **Non-vacuity:**
    - it first asserts that its sentinels reached the request bodies;
    - after the first navigation, `window.history.state` holds the router's entry (a numeric `idx`).

  *(NFR3.2, NFR3.3, NFR3.4, NFR3.6; functional-spec § 7 Sensitive data)*
- [x] **Step 24: The send-path scan and the named-test list.**
  - New `src/test/usernameKeyScan.test.ts`. No file under `src/` other than `api/endpoints.ts` and the username, sign-in and sign-up modules sends a `username` or `login` key. It is paired with a "present" assertion on `api/endpoints.ts`, so an empty scan fails.
  - New `src/test/namedTests.test.ts`. It holds the list of every named test file this unit adds or extends (the files in `unit-test-instructions.md`) and fails if any listed file is missing. Vitest already fails a listed file that holds no test.

  *(NFR3.7, NFR5.1)*
- [x] **Step 25: Bangla layout rows and the device timing rows.**
  - `docs/delivery/bangla-layout-check.md` gains one row per screen in functional-spec § 8: unit `U4 (web)`, Artboard `web`, status *not yet checked*.
  - Run each check in a browser in বাংলা at a 360 CSS px viewport and again at the wide layout, at each screen's longest Bangla string. Derive that string from the generated `strings.bn.json` and `i18n/web/*.bn.json` once Steps 2–3 land. Record the string and a `PASS`, `FAIL (…)` or `FIXED (…)` status.
  - Beside U3's timing table, add performance NFR8.4's timed check rows for sign-up, the gate and rename (browser, device, network, observed times), also *not yet checked*.
  - **Both are manual verifiers and nothing automated discharges them.** No screenshot test or browser performance harness exists or is added, and the Vitest tests above are correctness tests that measure neither layout nor latency.

  *(FR11.2; NFR8.4)*
- [x] **Step 26: Full web checks.**
  - Run `cd web && npm run check`: `check:generated`, `format:check`, `lint` with `--max-warnings 0`, `typecheck`, `test` (the whole web suite, so the existing suite stays green: scope floor), `build`, `build:admin`, `check:bundles`.
  - Then run `make web` from the repository root, which repeats `npm ci` and `npm run check`.
  - All green is required for completion (NFR5.2). No ESLint rule, TypeScript option, `check-bundles` assertion or `--max-warnings 0` is relaxed to get there (project Forbidden).
  - Run `npm run format` only on files this unit wrote, before `format:check`.
  - Confirm no dependency was added: `package.json` and `package-lock.json` are unchanged.
  - Record both commands' results in the code summary separately, because the intent's verification command does not run `make web` (tech-stack § 3).

  *(NFR5.2, NFR3.10, NFR9.1; TSD-1; scope floor)*

### Part E — documentation and traceability

- [x] **Step 27: Documentation and traceability** (the orchestrator's).
  - TSDoc on every new module and exported function, keeping the `[FR…]` / `[NFR…]` tag convention the web code uses.
  - `code-summary.md`, `source-manifest.json` and `traceability.json` in this directory.
  - The code summary records:
    - the baselines from Step 1;
    - corrections 1–5 above (the route boundary without a key, and the NFR4.1 ordering deviation, among them);
    - Step 6's result;
    - the named test files and their tests (NFR5.1);
    - the `make web` result;
    - the carried-forward follow-ups: functional-spec § 10 items 3 and 4 for U2 and U1, and the tab-closed-mid-rotation limit.

## Traceability (plan step → design ids)

| Step | Implements |
|---|---|
| 1 | NFR5.2 (baseline) |
| 2 | FR11.2; NFR5.2, NFR9.1; functional-spec § 1 defect 1, § 5 |
| 3 | FR11.2; functional-spec § 5, W10 |
| 4 | FR2.1, FR11.1; functional-spec § 1 defect 3, W1 |
| 5 | FR6.4, FR11.1; NFR6.2; functional-spec § 1 defect 2, W8 step 5 |
| 6 | NFR8.7; functional-spec § 1 defect 5 |
| 7, 8, 9 | FR5.1, FR5.2, FR5.3, FR5.4; NFR3.14, NFR3.15, NFR3.16, NFR6.3, NFR8.5, NFR8.6; functional-spec W4, § 3.3, § 3.4 |
| 10 | NFR8.8; functional-spec § 9 item 6 |
| 11 | functional-spec § 10 item 2 |
| 12 | FR11.3; NFR3.12; functional-spec § 1 defect 4 |
| 13 | FR3.1, FR4.1, FR5.4, FR6.1, FR6.4, FR6.7, FR7.1, FR8.2; NFR1.2, NFR3.1, NFR9.1 |
| 14 | FR3.1, FR3.2, FR11.3; NFR1.3, NFR2.1, NFR2.3, NFR3.11, NFR6.3, NFR8.1, NFR8.2, NFR8.3; TSD-1, TSD-5 |
| 15 | FR4.1, FR4.2, FR10.1, FR11.1; NFR1.1, NFR1.2; functional-spec § 1 defect 6 |
| 16 | FR6.7, FR11.1; functional-spec W9, § 7 |
| 17 | FR2.2, FR11.1; NFR1.4, NFR3.6; functional-spec W2, § 3.2 |
| 18 | FR7.1, FR7.2, FR7.5, FR11.1, FR11.3; NFR3.13 |
| 19 | FR8.1, FR8.2, FR8.3, FR8.4, FR11.1, FR11.3; NFR3.13 |
| 20 | FR6.1, FR6.2, FR6.3, FR11.1; NFR3.8, NFR6.1 |
| 21 | FR6.4, FR11.1; NFR3.8 |
| 22 | NFR3.5; TSD-2 |
| 23 | NFR3.2, NFR3.3, NFR3.4, NFR3.6 |
| 24 | NFR3.7, NFR5.1 |
| 25 | FR11.2; NFR8.4 (both manual) |
| 26 | NFR5.2, NFR3.10, NFR9.1; TSD-1; scope floor |
| 27 | traceability |
