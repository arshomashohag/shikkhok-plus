# Code Generation Plan — android-identity (U3)

## Summary

- Builds: the Android client for usernames and contacts: one-field sign-in, the sign-up username with live availability, the verify replacement, the choose-username gate, Username and Contacts in More, student and centre emails, plus the null-phone members fix, the cancellation rethrow, the 15 message keys with Bangla and English strings, and the source-scan guards.
- Touches: android/src/main/kotlin/com/shikkhokplus/app/ (core/network, core/session, core/ui, core/model/Identifier.kt, feature/auth, feature/account, feature/profile, feature/students, feature/roster, feature/centres, navigation, MainActivity.kt), res/values and res/values-bn strings, android/detekt.yml, docs/delivery/bangla-layout-check.md.
- Tests: roughly 150 JUnit, kotlinx-coroutines-test, MockEngine and Robolectric tests (an estimate, not asserted) in about 40 new or extended test files; the session flag, gate routing and recheck tests, and the null-phone decode regression, written first; everything else test-after.

## Inputs

Authoritative design, by path (the plan does not restate it):

- Functional design: `construction/android-identity/functional-design/` — `functional-spec.md` (§ 1 grounding and the two built defects, W1–W10, § 3 state machines, § 4 error handling per key, § 5 strings, § 8 Bangla layout rows, § 9 findings) and `frontend-components.md` (§ 1 hierarchy, § 2 UiState classes, § 3 ViewModel events, § 4 DTOs and repositories, § 5 navigation, § 6 validation, § 7 string names, § 8 tests), both as revised after review.
- NFR requirements: `construction/android-identity/nfr-requirements/` — `performance-requirements.md` (NFR8.1–8.6, NFR2.1–2.3), `security-requirements.md` (NFR1.1–1.4, NFR3.1–3.14, NFR4.1), `tech-stack-decisions.md` (TSD-1–5, NFR5.1, NFR5.4, NFR6.1–6.3, NFR9.1), as revised after review.
- Contracts: `openapi.json` on this branch is authoritative (C1 as amended by U1, C2 as built by U2).
- U1 and U2 are built on this branch; nothing here changes backend code.

**Corrections found while planning, applied by this plan** (read from the code, not run, because shell commands are refused before Plan Approval):

1. **`WriteContractTest` is red against the built backend.** Its `POST /v1/accounts` entries send no `username`, which `SignupRequest` now requires. Its existing entries for `/v1/auth/password`, `/v1/me/contact` and `/v1/centre/members` are still valid. Step 10 adds `username` and registers every new write.
2. **`MessageKeyCoverageTest` is red for the 15 keys** listed in functional-spec § 1. Step 7 turns it green.
3. **NFR9.1 understated the existing checks.** `ContractConformanceTest` (every GET decodes an example built from `openapi.json`) and `WriteContractTest` (every write's method, path and body validated against `openapi.json`) already compare client and contract for the shapes they cover. Their example builder emits only the non-null arm of a nullable field, so a nullable server field the client declares non-null passes them. That is exactly how `MemberDto.phone` slipped through, and it is why Step 3 adds an explicit null decode test. This plan registers every new read and write in those two gates, and Step 24 records the NFR9.1 correction.
4. **Turbine is not on the classpath** (TSD-2). Sequence assertions collect the `StateFlow` into a list with `kotlinx-coroutines-test`.
5. **Broad property names in two state classes.** `ContactCard.value` and `RemoveContactUiState.Confirming.value` (frontend-components § 2.6) are renamed `contact`. This lets `IdentifierToStringTest` match exact identifying names instead of `value` or `code` (NFR review iteration 2, note b).
6. **The cancellation rethrow also covers the `catch (_: Exception)` sites in files this unit touches**, not only the shared helpers. That means `HttpRosterRepository` (`roster`, `addEnrollment`, `removeEnrollment`, `createBatch`, `batches`, which `RosterRowDto` reaches through `roster`) and `HttpAuthRepository.logout` (NFR review iteration 2, note a). `HttpAttendanceRepository`, `SessionRenewal` and `TokenStore` keep their own catches; this unit does not touch them, and Step 24 records them as follow-ups.

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
grants or withholds a screen or a lens.** That covers:
- the session state that decides whether the choose-username gate or the
  graph is shown (`UsernameRequired` wrap, unwrap, `usernameChosen`,
  `refreshLenses`, `recheck`);
- `AppRoot`'s routing on it, first frame included;
- the null-phone members decode, which today withholds the members screen,
  the place a manager revokes access, from every manager of a centre with an
  email-only invitation.

The output of each is knowable from the design (functional-spec W4, § 3.4;
§ 1 defect 1), so their tests are written and run red first (Part B). Every
authorization decision behind them is the server's; what the client can get
wrong is which screen it shows, and that is what these tests pin. Everything
else is test-after: implemented, then tested from its acceptance criterion
before the Bolt is complete. This includes every Compose screen (team: no
Compose test before implementation).

## Steps

### Part A — structure and runner

- [ ] **Step 1: Runner and baseline.** With `ANDROID_HOME=/opt/android-sdk`, run `./gradlew :android:testDebugUnitTest --tests 'com.shikkhokplus.app.core.session.SessionViewModelTest' --no-daemon` and confirm it compiles and runs. Then record the baseline of the two gates this plan expects red by reading:
  - `--tests 'com.shikkhokplus.app.feature.auth.MessageKeyCoverageTest'`;
  - `--tests 'com.shikkhokplus.app.core.network.WriteContractTest'`.

  Record the current figure printed by `./gradlew :android:verifyCoverageRatchet --no-daemon`. All unit-scoped commands are in `unit-test-instructions.md`. *(NFR5.1)*
- [ ] **Step 2: Cancellation is not a transport failure.**
  - `core/network/HttpAuthRepository.kt`: `call { }`, `callDiscardingBody { }` and `logout` rethrow `CancellationException` before their `catch (_: Exception)` arm.
  - `core/network/HttpRosterRepository.kt`: the five methods with their own `catch (_: Exception)` (`roster`, `addEnrollment`, `removeEnrollment`, `createBatch`, `batches`) do the same.
  - Land this as its own small commit, `fix(network): rethrow cancellation from request helpers`, so the change to every caller is reviewable alone.
  - Test-after, new `core/network/CallCancellationTest.kt` (`MockEngine` with a handler that suspends, under the test dispatcher):
    - cancelling the caller of `call`, `callDiscardingBody`, `HttpRosterRepository.roster` and `logout` propagates `CancellationException` and returns no `TransportFailure`;
    - a real transport exception still returns `TransportFailure`.

  The existing `HttpRepositoryTest`, `SessionRenewalTest` and `HttpAttendanceRepositoryTest` stay green. *(NFR8.3, TSD-5)*

### Part B — test-first: what decides which screen is shown (written and run red first)

- [ ] **Step 3: Members list with an email-only invitation, regression first.**
  - **Red:** new `core/network/CentreDtoTest.kt`. Decode `[{"member_id":"m1","display_name":"Rina","phone":null,"invited_email":"rina@example.com","invited_at":"2026-11-14T10:00:00Z","role":"teacher","decision":"pending","revoked":false,"is_you":false}]` from a JSON string with `ApiClient.json` into `List<MemberDto>`, and assert it decodes with `phone == null` and the email kept. A second case decodes `"phone": "+8801712345678"` unchanged. Run red.
  - **Green:** in `core/network/CentreDto.kt`, `MemberDto.phone: String? = null` and `invitedEmail: String? = null`; `MemberInviteDto.phone: String? = null` and `email: String? = null`.

  The existing centre tests stay green; those needing `phone` non-null are adjusted to the nullable field, not deleted. *(functional-spec § 1 defect 1, W8.5; NFR6.2; FR6.4, FR11.1)*
- [ ] **Step 4: Session flag transitions, tests first.**
  - Extend `core/session/SessionStateMapperTest.kt`:
    - `afterLoad` with `username_required: true` gives `UsernameRequired(then = Ready)` for one lens, `UsernameRequired(then = Choosing)` for several, and `UsernameRequired(then = NoLens)` for none;
    - with `false`, the state is unchanged from today.
  - Extend `core/session/SessionViewModelTest.kt` with the eleven named tests of frontend-components § 8 (resolve, reset, failed read stays unknown, `usernameChosen` both ways, `refreshLenses` wrap and unwrap, three `recheck` cases, `recheck never publishes Resolving`). Sequences are collected into a list with `kotlinx-coroutines-test` (TSD-2).
  - Add a `MeDto` decode case to a new `core/network/ProfileDtoTest.kt`: `username`, and `username_required` both present and absent.
  - Minimal signatures only, so the tests compile and fail on assertions: `SessionUiState.UsernameRequired`, `MeDto.username` and `usernameRequired` defaulting to false, and `usernameChosen()`/`recheck()` stubs. Run red. *(FR5.1, FR5.2, FR5.3; NFR3.12, NFR3.13, NFR8.5, NFR8.6)*
- [ ] **Step 5: Gate routing, tests first.** New `navigation/UsernameGateRoutingTest.kt` (Robolectric, `MockEngine` answering `GET /v1/me`):
  - `first composed frame after Resolving is the gate when the read says true`: lens-picker and home tags never present in any frame;
  - the gate has no back arrow;
  - after `usernameChosen` the lens picker or home shows;
  - Sign out from the gate reaches sign-in with the token store fake cleared;
  - `failed read then foreground re-check showing true replaces the lens-free graph with the gate`, under a virtual clock over the 30 s re-check.

  A placeholder `ChooseUsernameGate` composable carrying only its test tag lets the test compile. Run red. *(FR5.2; NFR3.12–3.14, NFR8.5, NFR8.6)*
- [ ] **Step 6: Session state, `AppRoot` branch and re-check, green.**
  - `core/session/SessionUiState.kt`, `SessionStateMapper.kt`, `SessionViewModel.kt`: `UsernameRequired(then)`, `usernameChosen()`, `refreshLenses` wrap and unwrap, quiet `recheck()`.
  - `MainActivity.kt`: the `is SessionUiState.UsernameRequired` branch after `Resolving` and before `Choosing` in the single `when`; the `endSession` declaration moved above the `when` with no behaviour change; the `Failed` re-check effect inside `repeatOnLifecycle(STARTED)`, once on start and every 30 s.

  Steps 4–5 go green. *(functional-spec W4.1, W4.2, W4.8; frontend-components § 2.8, § 5)*

### Part C — implementation, then each layer's tests (test-after)

- [ ] **Step 7: Message keys and strings.**
  - `feature/auth/MessageKeys.kt` maps the 15 published keys (functional-spec § 1 defect 2) plus the client-only `signup.username.required`.
  - `res/values/strings.xml` and `res/values-bn/strings.xml` gain every string in frontend-components § 7, in English and Bangla together. `student_number_accepted`, `student_number_erased` and `centre_member_already_invited` are reworded from "number" to "contact" in both languages.
  - Tests: `feature/auth/MessageKeyCoverageTest.kt` goes green unchanged; extend `core/designsystem/StringPlaceholderTest.kt` for the new `%1$s` strings; Lint `MissingTranslation` (fatal) passes. *(FR1.6, FR11.2 strings half, W10)*
- [ ] **Step 8: Email shape aligned to the server.** `core/model/Identifier.kt` `emailIsWellFormed` follows `[^@\s]+@[^@\s]+\.[^@\s]+` with the 254 cap. New `core/model/EmailShapeTest.kt`: `a@b.c.` and `a@.b.c` accepted, `a@b`, `@b.c` and whitespace refused, 255 characters refused. Existing sign-up and add-contact tests stay green. *(Q5; NFR3.10; FR11.3)*
- [ ] **Step 9: DTOs and their `toString`.**
  - `core/network/AuthDto.kt`: `PasswordSignInRequest.login`, `VerifyRequest.username`.
  - `AccountsDto.kt`: `SignupRequestDto.username`.
  - New `UsernameDto.kt`: `UsernameAvailabilityRequest`, `UsernameAvailabilityDto`, `UsernameChangeRequest`, `UsernameChangeDto`, `ContactChangeRequest`, `ContactRemoveRequest`.
  - `TeacherStudentDto.kt`: `studentEmail` and `guardianEmail` on the DTO and both bodies, with a per-field encoding so an explicit clear sends JSON `null` under `explicitNulls = false`.
  - `RosterDto.kt`: `RosterRowDto` emails.
  - Every class in security NFR3.2's request and response lists masks identifying values in `toString`.
  - Tests:
    - new `core/network/UsernameDtoTest.kt`: decode each availability status including an unknown one, `next_change_at` null and set, and `toString` masks;
    - extend `TeacherStudentDtoTest.kt`: emails present, null and absent; the update body's unchanged, set and clear encodings asserted on the encoded JSON string;
    - new `core/network/RosterDtoTest.kt`: emails;
    - extend `ProfileDtoTest.kt` and `CentreDtoTest.kt` with `toString` masks;
    - extend `feature/auth/PasswordFlowMapperTest.kt` `toString` cases for `login`.

  *(NFR3.2, NFR6.1–6.3, NFR9.1; FR11.1)*
- [ ] **Step 10: Repositories.**
  - `AuthRepository.signIn(login, password)` and `verify(identifier, code, username)` in `HttpAuthRepository`.
  - `SignupRepository.checkUsername`, `lookupEmail` and `signup(…, username)` in `HttpSignupRepository`.
  - `AccountRepository.checkUsername`, `changeUsername`, `replaceContact` and `removeContact` in `HttpAccountRepository`.
  - `CentresRepository.invite(displayName, phone?, email?, role)` in `HttpCentresRepository`.
  - Teacher-students `create`/`rename` with emails in `HttpTeacherStudentsRepository`.
  - Tests (`MockEngine` through `ApiClient.build(engine = …)`):
    - extend `HttpSignupRepositoryTest.kt` and `HttpAccountRepositoryTest.kt`;
    - new `HttpAuthLoginTest.kt` (body has `login` and no `phone`/`email`; `verify` carries `username` only on a replacement);
    - new `HttpCentresRepositoryTest.kt`;
    - extend `HttpTeacherStudentsRepositoryTest.kt`.
    - Each test asserts method, path and JSON body. **No query string** is asserted on the two username lookups, `PUT /v1/me/username`, `POST /v1/auth/password`, `POST /v1/me/contact` and `/remove`.
    - Refusal envelopes come back `Refused` with their key.
  - `WriteContractTest.kt`:
    - every `POST /v1/accounts` entry sends `username`;
    - entries added for `POST /v1/auth/verify` with `username`, `POST /v1/auth/password` with `login`, both availability posts, `PUT /v1/me/username`, `POST /v1/me/contact` with `password`, `POST /v1/me/contact/remove`, `POST /v1/centre/members` with `email` only, and `POST /v1/students` and `PATCH /v1/students/{student_id}` with emails;
    - green.
  - `ContractConformanceTest.kt` stays green; no new GET path is added; `/v1/me` and `/v1/centre/members` are already listed.

  *(FR3.1, FR4.1, FR5.4, FR6.1, FR6.4, FR6.7, FR7.1, FR8.2; NFR1.2, NFR3.1, NFR9.1)*
- [ ] **Step 11: Shared username pieces.**
  - `core/ui/AutofillHint.kt`: `USERNAME` and `NEW_USERNAME`, and the pure `autofillTypeOf(hint)`.
  - New `core/ui/UsernameField.kt` (trimmed-64 cap), `LoginField.kt` and `AvailabilityHint.kt`.
  - New `core/ui/UsernameAvailability.kt` with:
    - `AvailabilityState` and `AvailabilityMapper`;
    - `UsernameAvailabilityChecker`: 500 ms debounce, one in flight, latest-wins with the apply-time text check, per-text cache, `withTimeoutOrNull(3_000)` outside the repository call, and stop after 429.
  - Tests:
    - new `core/ui/AvailabilityMapperTest.kt`;
    - new `core/ui/UsernameAvailabilityCheckerTest.kt`: virtual time; fake lookup cases for debounce, restart, empty, cache, no retry after transport, no call after 429; `MockEngine` through the real repository for the never-answering handler giving `CouldNotCheck` at 3 s, and the slow "ab" then "abc" case where the stale answer is never applied;
    - new `core/ui/AutofillHintTest.kt`;
    - new `core/ui/UsernameFieldTest.kt` (Robolectric): 65 rejected, 64 accepted, 64 with surrounding spaces accepted, 21 accepted.

  *(FR3.1, FR3.2, FR11.3; NFR8.1–8.3, NFR2.1, NFR3.9; TSD-4)*
- [ ] **Step 12: One-field sign-in.**
  - `feature/auth/AuthViewModel.kt` `signIn(login, password)`.
  - `ui/AuthActions.kt`.
  - `ui/AuthScreen.kt` `SignInStep` uses `LoginField` (tag `TAG_IDENTIFIER_FIELD` kept); no toggle, no shape check; `email.invalid` is shown under the field. The code flow keeps its toggle.
  - `ShikkhokNavHost.kt` wiring.
  - Tests:
    - extend `AuthStateMapperTest.kt` and `AuthViewModelTest.kt` (login sent as typed and trimmed; refusals unchanged; retry);
    - extend `AuthScreenTest.kt`: no toggle on sign-in, toggle still on the code flow, and a `StateRestorationTester` case where the password is empty after recreation and the login survives.

  *(FR4.1, FR4.2, FR10.1, FR11.1; NFR1.1, NFR1.2, NFR3.4)*
- [ ] **Step 13: Sign-up username and the email lookup.**
  - `SignupForm.username` with masked `toString`.
  - `SignupStateMapper` username keys.
  - `SignupViewModel` `usernameEdited`, `emailLeft` and submit with username.
  - `HttpSignupRepository` already done.
  - `ui/SignupScreen.kt`: username above the passwords with the hint; `NEW_USERNAME` autofill.
  - Navigation hands the username to `adoptPendingCode`.
  - Tests:
    - extend `SignupStateMapperTest.kt` and `SignupViewModelTest.kt` (blank username key; each username refusal under the field; transport retry resends the username; email lookup once per value and locks the role; `toString` masks);
    - extend `SignupScreenTest.kt`: the username field renders; `StateRestorationTester` empties password and confirm and keeps the username.

  *(FR2.1, FR3.1, FR6.7, FR11.1; NFR3.2, NFR3.4)*
- [ ] **Step 14: Verify replacement.**
  - `AuthUiState.ReplaceUsername(previous, checking, messageKey, retryable)` with masked `toString`.
  - `AuthStateMapper.afterVerifyRefused`.
  - `AuthViewModel` holds the verified code in a private field, with `replacementEdited`/`submitReplacement`; forgotten on Change, Back, sign-out and `onCleared`.
  - New `ui/ReplaceUsernameStep.kt`.
  - Tests:
    - extend `AuthViewModelTest.kt` and `AuthStateMapperTest.kt` (409 gives the replacement with the code retained; 200 continues as a first verify; username refusal and 429 stay; expired code goes to `CodeRejected`; transport retry; `changeNumber` forgets the code);
    - new `feature/auth/ReplaceUsernameStepTest.kt` (Robolectric, including a `StateRestorationTester` case where the username survives and the step still submits).

  *(FR2.2, FR11.1; NFR1.4, NFR3.4)*
- [ ] **Step 15: Choose-username gate.**
  - New `feature/account/ChooseUsername.kt` (UiState and `ChooseUsernameViewModel` on the authenticated checker; `recheck` on `password_required`).
  - New `ui/ChooseUsernameGate.kt`, replacing Step 5's placeholder; `USERNAME` autofill; Sign out.
  - Tests:
    - new `feature/account/ChooseUsernameViewModelTest.kt` (200 gives `Done` and `onChosen`; refusals; `password_required` gives `Rereading` then `Done`; failed re-read is retryable; 503/transport retry; double submit ignored);
    - new `feature/account/ChooseUsernameGateTest.kt` (renders, no back arrow, username survives restoration).

  `UsernameGateRoutingTest` stays green. *(FR5.2, FR5.4, FR11.1)*
- [ ] **Step 16: Username in Settings.**
  - New `feature/account/Username.kt` (`UsernameUiState`, `UsernameStateMapper`, `UsernameViewModel`).
  - New `ui/UsernameScreen.kt` (`next_change_at` via `core/format/Dates.kt` `dateTimeLabel`).
  - `Destination.Username` and its route.
  - Tests:
    - new `feature/account/UsernameStateMapperTest.kt` and `UsernameViewModelTest.kt` (200 with and without date; `change_too_soon` with and without date; `password_required` offers set-password; `current_wrong` goes to the password field; `unavailable` goes to the username field; 503/transport retry; password not retained; `toString` masks);
    - new `feature/account/UsernameScreenTest.kt` (Change always present; restoration empties the password).

  *(FR7.1, FR7.2, FR7.5, FR11.1, FR11.3)*
- [ ] **Step 17: Contacts.**
  - New `feature/account/Contacts.kt` (`ContactCard(kind, contact)`, `ContactsUiState`, `ContactsStateMapper`, `ContactsViewModel`).
  - New `ReplaceContact.kt` and `RemoveContact.kt`.
  - New `ui/ContactsScreen.kt`, `ui/ReplaceContactScreen.kt` and `ui/RemoveContactSheet.kt`.
  - `Destination.Contacts`, `Destination.ReplaceContact` and their routes. Completion re-reads Contacts and calls `session.onLensesChanged()`.
  - Tests:
    - new `feature/account/ContactsViewModelTest.kt` (both present; phone only; email only; password note; load failure retry; Remove present for a single contact);
    - new `ReplaceContactViewModelTest.kt` (request refusals routed; 200 gives the code step and drops the password; verify refusals stay; tries left; replaced; Resend returns to entry with the password empty; transport retry);
    - new `RemoveContactViewModelTest.kt` (200; `last_one` offers add-other; `current_wrong`; `password_required`; transport retry resends `{kind, password}`);
    - new `ContactsScreensTest.kt` (restoration empties the password on replace and remove; `toString` masks).

  *(FR8.1, FR8.2, FR8.4, FR11.1, FR11.3; NFR3.4, NFR3.11)*
- [ ] **Step 18: More rows and navigation.**
  - `navigation/AccountRoutes.kt` `accountRowsFor`/`AccountRows` give the Username row and the Phone and email row in place of the add rows.
  - `feature/profile/ui/ProfileScreen.kt` `MoreActions`/`SignInRows`.
  - `ProfileSummary.username`.
  - `navigation/Destination.kt`.
  - Tests:
    - update `navigation/AccountRowsTest.kt`, rewritten from the new acceptance criterion and not deleted;
    - extend `DestinationTest.kt`, `MoreActionsTest.kt` and `feature/profile/ProfileScreenTest.kt`.

  *(FR5.2, FR7.1, FR8.1, FR11.1)*
- [ ] **Step 19: Student and roster emails.**
  - `feature/students/ui/AddStudentForm.kt` (`NewStudent` emails, masked `toString`).
  - `StudentDetailScreen.kt` `EditStudentDialog` (`EmailEdit` unchanged/set/clear).
  - `StudentsStateMapper.kt` contact lines.
  - `StudentsUiState.kt` (`StudentDetail`, `StudentListRow` masked).
  - The ViewModels.
  - The roster mapper's `guardianContactLine`.
  - Tests:
    - extend `StudentsViewModelTest.kt` and `StudentDetailViewModelTest.kt`;
    - new `feature/students/StudentsStateMapperTest.kt` (contact line for phone, email only, both and neither; `student.email.taken` under the field);
    - extend `feature/roster/RosterStateMapperTest.kt`.

  *(FR6.1, FR6.2, FR6.3, FR11.1)*
- [ ] **Step 20: Centre invite by email.**
  - `feature/centres/CentresViewModels.kt` (`inviteEmail`, `canInvite`, `MemberLine` mapping with `contactLine`, masked).
  - `ui/CentresScreens.kt` (email field, `MemberCard` renders `contactLine`).
  - Tests: extend `CentresViewModelsTest.kt` (invite with phone only, email only, or neither; body omits blanks; `already_invited`) and `CentresScreensTest.kt` (an email-only member renders).

  *(FR6.4, FR11.1)*

### Part D — environment/build configuration and the mechanical guards

- [ ] **Step 21: detekt and the source scans.**
  - `android/detekt.yml` `ForbiddenImport` gains `android.util.Log` and `io.ktor.client.plugins.logging.*` with reasons.
  - New source-scan tests in `src/test/kotlin/com/shikkhokplus/app/`, in the `NoFloatingPointTest`/`ForbiddenIdentifiersTest` style:
    - **`NoLoggingTest.kt`**: the NFR3.3 regex over `src/main/kotlin`, plus an assertion that `detekt.yml` holds both new entries.
    - **`IdentifierToStringTest.kt`**: over an explicit list of the files this unit adds or changes, every `data class` declaring a property named exactly one of `username`, `login`, `previous`, `phone`, `email`, `password`, `currentPassword`, `newPassword`, `confirm`, `invitePhone`, `inviteEmail`, `invitedEmail`, `studentPhone`, `guardianPhone`, `studentEmail`, `guardianEmail`, `contact`, `contactLine`, `studentContactLine` or `guardianContactLine` must declare `override fun toString`. Exact names, never `value` or `code` (NFR review iteration 2, note b). A behavioural half then builds one instance of each listed class with sentinel values (`sentinel_user_7`, `sentinel@example.invalid`, `+8801999999999`, `sentinel-pass`) and asserts its `toString()` contains none of them, so an override that exists but does not mask fails.
    - **`NoSavedSecretsTest.kt`**: no `SavedStateHandle` in `feature/auth`, `feature/account` or `core/session`; no `rememberSaveable` whose variable name matches `(?i)password|confirm|current|code|otp|secret`.
    - **`UsernameDeclarationScanTest.kt`**: `@SerialName("username")`, `@SerialName("login")`, and any property named `username` or `login` in `core/network` appear only in the allowlisted classes of NFR3.5.
  - Run `./gradlew :android:detekt --no-daemon` green.

  *(NFR3.2, NFR3.3, NFR3.4, NFR3.5)*
- [ ] **Step 22: Bangla layout table rows.** `docs/delivery/bangla-layout-check.md` gains one row per screen in functional-spec § 8, unit `U3`, status *not yet checked*. Run the check on a device in Bangla locale at each screen's longest Bangla string, derived from `values-bn/strings.xml` once Step 7 lands. Record the string and a `PASS`, `FAIL (…)` or `FIXED (…)` status. **This is a manual verifier and nothing automated discharges it:** no screenshot test exists or is added, and the Robolectric tests above are correctness tests that do not measure layout. Alongside it, record the timed low-end-device check of performance NFR8.4 per screen, which is also manual with nothing automated discharging it. *(FR11.2; NFR8.4)*
- [ ] **Step 23: Full Android checks.** Run:
  - `./gradlew :android:testDebugUnitTest --no-daemon` (the whole module, so the existing suite stays green: scope floor);
  - `:android:detekt`, `:android:lintDebug`, `:android:spotlessCheck` (Gradle scripts and res XML only; no Kotlin formatter exists, by the 2026-10-22 decision);
  - `:android:verifyCoverageRatchet`.

  The ratchet's whole-module figure stays within its tolerance of `android/coverage-floor.txt`, and **the floor file is not lowered** (project Forbidden). The composables are excluded from the figure, so NFR5.4's named-test list is checked against Steps 2–21 by name in the code summary. *(NFR5.1, NFR5.4)*

### Part E — documentation and traceability

- [ ] **Step 24: Documentation and traceability.**
  - KDoc on every new class and public function, keeping the `[FR…]` / `[NFR…]` tag convention.
  - `code-summary.md`, `source-manifest.json` and `traceability.json` in this directory.
  - The code summary records: the NFR9.1 correction (`ContractConformanceTest` and `WriteContractTest` exist; their example builder skips null arms); the Turbine substitution; the `ContactCard.contact` rename; the untouched `catch (_: Exception)` sites in `HttpAttendanceRepository`, `SessionRenewal` and `TokenStore` as follow-ups; and functional-spec § 9's `openapi.json` follow-ups for U1 and U2.

## Traceability (plan step → design ids)

| Step | Implements |
|---|---|
| 1 | NFR5.1 (baseline) |
| 2 | NFR8.3, TSD-5 |
| 3 | FR6.4, FR11.1; NFR6.2; functional-spec § 1 defect 1 |
| 4, 5, 6 | FR5.1, FR5.2, FR5.3; NFR3.12, NFR3.13, NFR3.14, NFR8.5, NFR8.6 |
| 7 | FR1.6, FR11.2; functional-spec § 1 defect 2, § 5, W10 |
| 8 | FR11.3; NFR3.10 |
| 9 | NFR3.2, NFR6.1, NFR6.2, NFR6.3, NFR9.1 |
| 10 | FR3.1, FR4.1, FR5.4, FR6.1, FR6.4, FR6.7, FR7.1, FR8.2; NFR1.2, NFR3.1, NFR9.1 |
| 11 | FR3.1, FR3.2, FR11.3; NFR2.1, NFR2.3, NFR3.9, NFR8.1, NFR8.2, NFR8.3; TSD-4 |
| 12 | FR4.1, FR4.2, FR10.1, FR11.1; NFR1.1, NFR1.2, NFR3.4 |
| 13 | FR2.1, FR3.1, FR6.7, FR11.1; NFR3.2, NFR3.4 |
| 14 | FR2.2, FR11.1; NFR1.4, NFR3.4 |
| 15 | FR5.2, FR5.4, FR11.1 |
| 16 | FR7.1, FR7.2, FR7.5, FR11.1, FR11.3 |
| 17 | FR8.1, FR8.2, FR8.4, FR11.1, FR11.3; NFR3.4, NFR3.11 |
| 18 | FR5.2, FR7.1, FR8.1, FR11.1 |
| 19 | FR6.1, FR6.2, FR6.3, FR11.1 |
| 20 | FR6.4, FR11.1 |
| 21 | NFR3.2, NFR3.3, NFR3.4, NFR3.5, NFR3.7 |
| 22 | FR11.2; NFR8.4 (both manual) |
| 23 | NFR5.1, NFR5.4; scope floor |
| 24 | traceability; NFR9.1 correction |
