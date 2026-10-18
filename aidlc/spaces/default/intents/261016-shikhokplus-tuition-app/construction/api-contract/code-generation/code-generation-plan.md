# Code Generation Plan — `api-contract` (U2)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Depth**: Comprehensive

> **What this Bolt builds.** Not a feature — a contract and four CI gates that
> every later Unit is checked against. The gates must exist *before* the first
> route does, which is why U2 precedes U3.
>
> **The central risk, carried from NFR Requirements.** Every schema assertion
> here iterates a collection that is **empty in B2**: no routes, no money
> endpoints, no response schemas. Each returns green having examined nothing,
> and a passing test and a vacuous test are the same colour. Steps 9–12 are the
> four violation fixtures that close it, and they are not optional polish.

---

## Testing Contract

```json
{
  "version": 1,
  "methodology": "custom",
  "source": "team",
  "ordering": "Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
  "scope": "classic",
  "test_strategy": "comprehensive",
  "project_type": "greenfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt\nwithout its tests is not done.\n\n- **Methodology**: custom\n- **Methodology evidence**: The cadence genuinely differs by surface, and\n  recording a single uniform value would misdescribe what we actually do. Three\n  facts drive the split. (1) The money paths — fee-cycle arithmetic,\n  carry-forward, partial approval, waiver — have **mandatory** tests by stated\n  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than\n  I/O-shaped, and have expected values knowable before any implementation\n  exists. That is the exact precondition under which test-first pays: the test is\n  a specification we can write correctly without having written the code, and the\n  fee model is *already known to be in revision* [D-18], so a suite that pins the\n  arithmetic is what makes the next revision safe rather than frightening. (2) The\n  Compose UI surface is the opposite case. There is **no declared Kotlin or\n  Android experience** [OC-3], so a Compose test written before the\n  implementation is as likely to encode a misunderstanding of the framework as to\n  catch a defect, and when it passes it certifies that misunderstanding — worse\n  than no test. (3) The privacy boundary is structural rather than arithmetic\n  [D-7, TC-13] — enforced by table design, row-level security and distinct\n  response schemas — so its tests are adversarial probes against a built\n  boundary, which is inherently test-after. A uniform `tdd` would be a commitment\n  we would break on the Compose Bolts; a uniform `test-after` would weaken the\n  one surface where the requirement is explicit and the preconditions for\n  test-first are actually met. `custom` is the accurate value.\n- **Ordering**: Write the failing test first whenever **both** of these hold —\n  the correct output is knowable from the requirement without having written the\n  code, **and** a wrong answer would be a money error or an authorization error —\n  and for everything else implement the layer, then write and run that layer's\n  tests before the Bolt is complete.\n\nThat ordering is a **predicate, not a list**, and the distinction is the point:\nan enumeration plus \"everything else\" fails open, because every case nobody\nanticipated defaults to test-after. The following are *examples* of the\npredicate holding, not its boundary:\n\n- every change to the money module;\n- every fee-cycle and payment-verification state transition — generation,\n  carry-forward, partial and reduced approval, waiver, rejection;\n- the `(enrollment_id, period)` idempotency constraint;\n- every lens-resolution and row-level-security rule, wherever that code lives;\n- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,\n  leave existing dues standing, and leave the student active in other batches,\n  all three of which are money-adjacent and fail quietly;\n- the cross-batch dues query [PU-7.2], which is driven by outstanding balance\n  and not by active status, so students who left owing money still appear.\n\n**A change meeting the predicate does not escape it by being implemented in\nKotlin**, or in a route handler rather than in the money module. Where the code\nlives is not part of the test.\n\n**Test-after is a cadence, not permission to write the test against the\nimplementation.** A test-after test is written from the acceptance criterion. If\nwriting it requires reading the implementation to know what to assert, the\nacceptance criterion is the defect.\n\nSupporting bullets, which do not replace the two fields above:\n\n- **Backend coverage floor**: 80% line coverage, enforced in CI, with no\n  decrease permitted. This comes from the active `classic` scope at Comprehensive\n  test strategy and may not be weakened to make a step pass. **The authorization\n  layer is measured as branch coverage rather than line coverage** — lens\n  resolution is pure branching over teacher, student and guardian and owned-batch\n  membership, so line coverage on it is close to meaningless.\n- **The money module carries 100% branch coverage**, because the defects that\n  matter there live in the branches: the short-month clamp, the\n  carry-forward-versus-waive fork, the partial-approval path, the\n  zero-and-negative edges. An 80% line floor can be met while leaving the waiver\n  branch entirely unexecuted, which satisfies the number and misses the\n  requirement. Two things make that target honest rather than decorative: the\n  money module contains **no I/O, no session and no HTTP**, so 100% stays\n  reachable; and branch coverage is supplemented by obligations not reducible to\n  a percentage — a named test per fee-cycle and payment state transition, and a\n  documented boundary case per money input (period boundaries, rounding at the\n  half, zero, negative, an approved amount exceeding the claimed amount). We also\n  add one property-based test (Hypothesis) on the invariant that holds across all\n  of it: for any sequence of charges, approvals, carry-forwards and waivers,\n  `charged - received - forgiven == outstanding`, and `outstanding` never goes\n  negative. That invariant catches the class of defect no enumerated example\n  will.\n- **Android carries named obligations and no percentage floor.** Gating a surface\n  the reviewer cannot yet evaluate produces tests written to raise a number; that\n  is a reason to drop the *percentage*, not a reason to drop the *obligation*,\n  and this is the thinnest-reviewed part of the product. So:\n  - every ViewModel ships tests for its state machine — loading, success, error,\n    and the explicit retry path for a failed write [TC-8, D-9];\n  - every money-carrying model class ships a serialization test proving decode\n    from a JSON string and **loud failure** on a JSON number, because a lenient\n    decoder that quietly accepts a number and converts is the actual failure mode\n    and it passes a happy-path-only both-sides test;\n  - Kotlin line coverage is reported from the first Android Bolt, with **no\n    decrease permitted** once three Android Bolts have merged. A no-regression\n    ratchet gives the trend teeth without anyone inventing a target they cannot\n    justify.\n- **Test types by layer**: pytest for backend unit and integration tests, with\n  integration tests running against a **real PostgreSQL 16** container via\n  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,\n  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and\n  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin\n  ViewModel and repository tests, targeting the response-to-UiState mapping\n  function rather than an untargeted \"the ViewModel\". Compose UI tests for the\n  OTP entry path and the mid-class attendance path.\n- **Database tests connect as a restricted non-superuser role.** PostgreSQL\n  documents that superusers and table owners bypass row-level security entirely\n  [pg-rls], and the default test-container connection is `postgres`, a superuser.\n  A privacy-boundary suite run as superuser passes identically whether the policy\n  is correct, broken, or entirely absent — so the strongest test obligation we\n  have would certify nothing. Integration tests therefore connect as the same\n  restricted role the application uses, and a **meta-test asserts that\n  `current_user` is not a superuser and that row-level security is in force**\n  (`row_security` on, policy present) before the privacy suite runs.\n- **Privacy boundary tests are adversarial, and the API-level half is a\n  schema-wide invariant.** No teacher-lens response schema may contain any field\n  in the owner-private profile set, enforced by iterating the generated OpenAPI\n  schema rather than by remembering to write a test per endpoint — per-endpoint\n  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking\n  about it. The probe suite explicitly covers the IDOR shape: teacher A\n  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a\n  student requesting a fee cycle not their own. That is the vulnerability class a\n  scanner cannot find and the one most likely to exist, because finding it\n  requires knowing the intended policy.\n- **Schemathesis validates conformance, not correctness, and never counts as\n  privacy coverage.** A teacher-facing response schema that wrongly includes\n  profile fields is perfectly *conformant*. We keep Schemathesis for what it is\n  good at — unexpected 500s, type and required-field drift, auth present on every\n  route — and we add the check it cannot provide: **an OpenAPI schema-diff gate**,\n  where the committed schema must match the generated one and CI fails if they\n  diverge. A stale committed schema is worse than none, because the contract tests\n  then pass against fiction.\n- **Money representation is itself a test target.** Every money value crosses the\n  API as a JSON **string** [TC-7, D-20], asserted on both sides: the backend never\n  emits a JSON number for a money field, and the client rejects one.\n- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle\n  guarantee is a database constraint precisely because application-level guards\n  fail under concurrency [D-21, TC-12]; testing it by calling the job twice in\n  sequence would pass against the broken implementation the decision exists to\n  avoid. The test runs overlapping generations and asserts the **outcome** rather\n  than the absence of an exception: after N overlapping generations exactly one\n  row exists per `(enrollment_id, period)` and the ledger total is unchanged. It\n  also covers the case concurrency alone misses — the daily self-healing re-run\n  [PU-5.5] must be idempotent across *days*, so a cycle generated on the 1st is\n  not regenerated on the 2nd.\n- **Token lifecycle is tested as a state machine.** Refresh-token rotation with\n  reuse detection has a security-critical failure mode: present a rotated-out\n  token and the whole token family must be invalidated. Untested, this degrades\n  silently into non-rotating refresh tokens, because the happy path is identical.\n  We also test that refresh tokens are stored hashed, that access-token expiry is\n  actually enforced, and that a 15-minute-expired token is rejected.\n- **Both account-deletion paths are tested** [TC-19]: the in-app path and the\n  externally accessible route. Each must assert that deletion removes what the\n  Data Safety form claims it removes and retains only what the privacy policy\n  discloses [RC-4, RC-5], per each table's written disposition. Deletion features\n  are the ones most reliably shipped broken, because nobody tests the absence of\n  data.\n- **PU-3.6's mid-class speed requirement is not discharged by a correctness\n  test.** A Compose UI test asserts behaviour, not latency. Either the attendance\n  obligation is a **Macrobenchmark on a low-end device profile** (which also\n  serves TC-17), or PU-3.6 has no automated verification in V1 and carries an\n  explicit manual check in the pilot. Both are acceptable; silently using a\n  correctness test to discharge a performance requirement is not.\n- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:\n  Compose screenshot tests at the longest Bangla string, or an explicit\n  per-screen manual check. \"Must not break the layout\" currently has no verifier,\n  and an unverifiable obligation is a wish.\n- **One command, local and in CI.** `make check` or equivalent, the same\n  entrypoint in both places. For a solo build this is the single most important\n  property of the gate: a gate reproducible only by pushing is a gate that gets\n  bypassed. The blocking suite needs no secret to run locally, which means the\n  SMS gateway is stubbed in tests and the sandbox-credential question affects\n  staging only, never CI.\n- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if\n  minutes become a real constraint. Splitting by cost is cheaper than migrating by\n  platform, and the PR integration is where the only review happens. The Android\n  job is split from the backend job so a Kotlin build does not gate a backend PR,\n  dependencies are cached, the backend path stays under about ten minutes or it\n  will be skipped, and the per-month minute budget is stated and monitored\n  against [OC-4].\n- **A green `main`, not just a green PR.** With squash-merge and one reviewer, the\n  post-merge run on `main` is the only thing that catches a stale-base merge.\n- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.\n  Tests that always pass regardless of implementation are defects in their own\n  right and are rejected in review.\n\n---\n\n- The ledger invariant for the money module's property-based test is `total_charged - total_forgiven - (total_receipt + total_credit_grant) == total_outstanding - available_credit`, with `available_credit = credit_grant - credit_apply >= 0`, `total_outstanding >= 0`, and `sum(carry_forward) == sum(carried_out)`. This supersedes the earlier `charged - received - forgiven == outstanding`, which omitted carry-forward and predated credit, and an intermediate form that omitted credit_grant from cash in. Money received as credit is money received: cash in is receipts plus credit grants. (learned 2026-10-17) \n\n- Carry-forward is recorded two-sided — a `carried_out` entry relieves the originating period and a `carry_forward` entry charges the receiving one — so the two cancel at enrollment level. A one-sided carry counts the same debt in both periods: carrying 1000 into a second 1000 charge reads **3000 owed against a true 2000** — this figure was corrected on 2026-10-18, see the Corrections entry below; the earlier \"2500 against a true 1500\" reproduces under no implementation. A named test covers a multi-period carry, not only a single one, because a single carry can pass against a model that double-counts. (learned 2026-10-17, figure corrected 2026-10-18) \n\n- A money invariant is verified before it is recorded as satisfied, never asserted from reasoning alone: worked cases across every ledger operation, then randomized histories composing those operations in arbitrary order. This project's identity was wrong twice before randomized testing settled it, and it is the property-based test standing behind 100% branch coverage on the money module — an unverified invariant there certifies the arithmetic it was meant to check. (learned 2026-10-17)"
    }
  ],
  "obligations": {
    "strategy": "comprehensive",
    "strategy_volume": [
      "Ten to fifteen tests per component.",
      "Unit, integration, and E2E tests.",
      "Add performance and security tests when NFRs demand them."
    ],
    "scope_floor": [
      "Keep the existing test suite green.",
      "This scope adds no extra new-test floor beyond the selected test strategy."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "custom",
    "runner_step": "Bootstrap the minimal test runner/configuration and record the exact unit-scoped command.",
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
      "Bootstrap the minimal test runner/configuration and record the exact unit-scoped command.",
      "Custom ordering - Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
      "Implementation and tests - preserve that exact ordering; do not convert it to layer-local TDD.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:f4aa2bdf0c63e875ce270a77c925a8267750ddf3fbb4687e062eef8e67c89f26",
  "contract_sha256": "sha256:e6177bc5e7766f133e4f6761f673165dae49441e9b7d6dcc42479afb0c5acb47"
}
```

---

### How the custom ordering applies to this Unit

The predicate is: **test-first when the correct output is knowable from the
requirement AND a wrong answer would be a money or authorization error.**

| Component | Predicate holds? | Order |
|---|---|---|
| `app/authz/annotations.py` — the lens resolver | **YES** — authorization. A wrong answer silently authorizes nothing | **Test-first** |
| `tests/contract/test_route_lenses.py` gate | **YES** — authorization | **Test-first** |
| `tests/contract/test_privacy_schema.py` gate | **YES** — authorization/privacy | **Test-first** |
| `app/errors/*` — taxonomy and handler | No — not money or authz; shape knowable but failure is a 500, not a leak | Test-after |
| `app/contract/serialize.py` — canonicalization | No | Test-after |
| `tests/contract/test_money_schema.py` gate | No — money-*adjacent*, but it asserts a schema shape, not arithmetic | Test-after |
| `app/schemas/*` — the Money component + envelope | No | Test-after |

The three test-first items are exactly those where **a wrong answer is an
authorization error that passes silently**. Nothing escapes the predicate by
living in a test file rather than a module: the route-lens gate *is* the
authorization control for every Unit after this one.

---

## Steps

### Part 1 — Runner readiness and skeleton

- [ ] **Step 1 — Package skeleton.** Create `app/errors/`, `app/schemas/`,
      `app/authz/`, `app/contract/`, each with `__init__.py` and a module
      docstring. Create `tests/contract/` and `tests/contract/fixtures/`.
      *No logic.* [NFR-design §A]

- [ ] **Step 2 — Test runner readiness.** The runner already exists from B1
      (`pytest`, configured in `pyproject.toml`), so this step **verifies**
      rather than bootstraps: confirm `python3 -m pytest tests/contract -q`
      runs and reports zero collected tests without error. Record the exact
      command in `unit-test-instructions.md`.
      *A Red step is invalid if no runnable command exists — this is that
      check.* [Testing Contract `runner_ready_before_first_test`]

- [ ] **Step 3 — mypy strict island for `app.schemas`.** Add the
      `[[tool.mypy.overrides]]` block for `app.schemas.*` with `strict = true`
      and `disallow_any_explicit = true`. Verify `mypy app` still passes.
      [NFR14.11, tech-stack A.4]

      > B1 configured only `app.money.*`, correctly — an override naming a
      > non-existent module is dead configuration. U2 is the Unit that first
      > populates `app.schemas`, so the override lands here. `app.authz.*`
      > stays unconfigured until U3 creates it.

### Part 2 — Authorization primitives (TEST-FIRST — the predicate holds)

- [ ] **Step 4 — RED: the lens resolver's tests.** Write
      `tests/authz/test_annotations.py` **before** the implementation, from
      NFR14.7's stated requirement. Must cover, each as its own test:
      a plain `TeacherLens` return annotation resolves; a **string**
      annotation under `from __future__ import annotations` resolves; a
      `TeacherLens | GuardianLens` union resolves (every member qualifies);
      a `TeacherLens | None` union does **not** (not every member qualifies);
      `Annotated[TeacherLens, ...]` unwraps; a non-lens type returns `None`;
      an **unresolvable** annotation **raises** `AnnotationResolutionError`
      and is never swallowed.
      *Run and confirm they fail.* [NFR14.7, US10.1]

- [ ] **Step 5 — GREEN: `app/authz/lenses.py` and `annotations.py`.**
      The `Lens` base plus `TeacherLens`, `StudentLens`, `GuardianLens` (types
      only — U3 resolves them), and `resolve_lens_type()` using
      `typing.get_type_hints`. Run Step 4's tests to green.
      [NFR14.7, entities.md `Lens`]

      > One function, two callers — Steps 7 and 13 both use it. A second
      > implementation would almost certainly be the naive `issubclass` the
      > requirement exists to forbid.

- [ ] **Step 6 — REFACTOR while green.** Docstrings per the Sphinx standard,
      `:raises:` on the resolver, mypy clean.

- [ ] **Step 7 — RED: the route-lens gate's tests.** Write
      `tests/contract/test_route_lenses.py` before the gate exists, including
      the `PUBLIC_ROUTES` (exactly 5) and `LENS_EXEMPT_AUTHENTICATED`
      (exactly 1) frozensets with their **length assertions**, and a test that
      a throwaway app with an unlensed route is caught.
      *Run and confirm failure.* [NFR14.5, NFR14.6, AC10.1.7]

- [ ] **Step 8 — GREEN: `app/contract/routes.py`.** Implement
      `unlensed_routes(app: FastAPI) -> list[RouteViolation]`, walking
      `route.dependant` **recursively**. **Parameterized on the app**, so the
      fixture and the real gate call one function rather than two that drift.
      [NFR14.5, review fix]

### Part 3 — The four violation fixtures (the vacuity defence)

- [ ] **Step 9 — Route fixture.** `tests/contract/fixtures/unlensed_app.py`
      builds its **own** `FastAPI()` with one unlensed route. Asserted to be
      caught, **naming that route's path**.
      *Builds its own app rather than mutating the real one: that mutation
      leaks into any test running in between, and presents as an unrelated
      test failing mysteriously.* [NFR14.1, NFR14.2]

- [ ] **Step 10 — Money fixture.** An otherwise-valid OpenAPI document with
      one property declaring an inline `{"type": "string"}` where a `$ref`
      belongs. Asserted to fail **naming that property path**. [NFR9.1]

- [ ] **Step 11 — Display-pairing fixture.** An otherwise-valid document with
      `amount_display` and no sibling `amount`. Asserted to fail **naming the
      orphan field**. [NFR9.2]

- [ ] **Step 12 — Privacy fixture.** An otherwise-valid document with one
      teacher-lens response declaring `date_of_birth` and a second declaring
      `student_account_id`. Asserted to produce **two distinct errors, one per
      field set**.
      *Two, deliberately: a fixture tripping only the profile set leaves
      ADR-001's account-id set unexercised while the gate reports green.*
      [NFR14.8, ADR-001]

      > Every fixture is **otherwise valid** and violates exactly one rule.
      > That is what makes "assert which violation" achievable — a merely
      > malformed fixture fails every gate for the wrong reason and certifies
      > nothing while looking like a working test.

### Part 4 — The schema gates (TEST-FIRST for privacy; test-after for money)

- [ ] **Step 13 — RED then GREEN: the privacy gate.**
      `tests/contract/test_privacy_schema.py` first (authorization predicate),
      then `app/contract/privacy.py`:
      `forbidden_fields(document, app) -> list[FieldViolation]`. Reads the
      lens **from the route** via Step 5's resolver, never from the schema
      name; recurses through `$ref`/`items`/`allOf`/`anyOf` with a **cycle
      guard**. Both forbidden field sets on one iteration.
      *An unguarded walk **hangs** CI rather than failing it, and a hang is
      worse because nobody reads it as a result.* [NFR14.8]

- [ ] **Step 14 — The money gate.** `app/contract/money_schema.py` +
      `tests/contract/test_money_schema.py`. Assert no property declares an
      inline money-shaped type instead of `$ref`-ing the shared `Money`
      component; assert no `<x>_display` without its sibling. Both take the
      **document as an argument**. [NFR9.1, NFR9.2]

### Part 5 — Serialization and the schema-diff gate

- [ ] **Step 15 — `app/contract/serialize.py`.** `canonical(document) -> str`
      with `sort_keys=True`, fixed separators, **and `_sort_lists`** sorting
      order-insensitive lists (`required`, enum members, tag lists).
      [NFR16.3]

      > **`sort_keys` alone is not sufficient and this was measured.** It
      > orders object *keys*, not list *values*: a `required` list built from
      > a `set` keeps hash ordering straight through a fully canonical dump.
      > `_sort_lists` is the half that actually closes it.

- [ ] **Step 16 — `app/contract/emit.py`.** A `python -m` entry point printing
      the canonical document to stdout — the subprocess target for Step 17.

- [ ] **Step 17 — The diff and determinism gate.**
      `tests/contract/test_schema_diff.py`: committed equals generated; and a
      **subprocess** regeneration comparison.
      *A subprocess gets a fresh hash seed, which is the only arrangement that
      can observe a set-derived ordering — verified: it fails where a same-run
      comparison passes.* `PYTHONHASHSEED` stays unpinned. [NFR16.1–16.3]

### Part 6 — The error taxonomy (test-after)

- [ ] **Step 18 — `app/errors/`.** Five exception classes; `AuthorizationError`
      carries `status: Literal[401, 403]`. The `codes.py` registry with **no
      pair distinguishing unreachable from absent**. One FastAPI handler with a
      five-arm `match` ending in `assert_never`.
      [NFR17.2, NFR17.3, NFR14.3, BR1.1–BR1.6]

- [ ] **Step 19 — `app/schemas/errors.py`.** The envelope as a Pydantic model:
      `code`, `retryable`, `message_key`, optional `error_class` and typed
      `details`. **`additionalProperties: false`**, no `message` field ever.
      [NFR3.1, BR1.3]

- [ ] **Step 20 — `tests/contract/test_error_contract.py`.** Class-to-status
      mapping; `retryable` derived at the handler; no `message` field emitted;
      **the status/code pairing** (a 403 never carries `ACCESS_TOKEN_EXPIRED`);
      the handler performs no I/O. [NFR3.1, NFR13.1, NFR14.3, NFR17.3]

- [ ] **Step 21 — `tests/gates/test_import_gates.py` extension.** Assert
      `app.errors` imports nothing from `app.db`, `app.repositories`,
      `app.api`, or any HTTP client — **extending B1's existing passing gate
      file** rather than creating a parallel one. [NFR17.2]

### Part 7 — Committed artifacts and wiring

- [ ] **Step 22 — `app/main.py` minimal app + `openapi.json`.** A FastAPI app
      with the exception handler registered and the `Money` schema component,
      but **no routes**. Generate and commit `openapi.json` via
      `make openapi`. [NFR16.1]

- [ ] **Step 23 — `Makefile` targets.** `make openapi` (regenerate — **the
      only sanctioned way to update the committed file**) and `make check`
      extended to run `tests/contract`. [NFR16.2, NFR16.4]

- [ ] **Step 24 — Documentation.** A `README` note beside `openapi.json`
      stating it is generated output and naming `make openapi`.
      *The counterweight to the gate's one real misuse: hand-editing the
      committed file to make a red diff green, which looks exactly like
      fixing the problem.* [NFR16.4]

### Part 8 — Verification

- [ ] **Step 25 — Full suite green.** `make check`: all tests, Ruff, mypy.
      Coverage on `app/money` unchanged at 100% branch; `app/errors` and
      `app/contract` at or above the 80% line floor.
      **No threshold is relaxed to make this pass.**

- [ ] **Step 26 — `source-manifest.json`** listing every application-source
      path this Unit created or modified.

---

## Story-to-step traceability

| Story / AC | Steps |
|---|---|
| US9.2 — the error taxonomy a client can act on | 18, 19, 20 |
| AC9.2.3 — five classes, `retryable` derived | 18, 20 |
| US10.1 — the privacy boundary is structural | 4–14 |
| AC10.1.1–AC10.1.4 — non-disclosing refusals | 18, 20 |
| AC10.1.5 — no profile field in a teacher-lens schema | 12, 13 |
| AC10.1.7 — every route resolves a lens | 7, 8, 9 |
| NFR16 — `/v1/` additive, contract diff-visible | 15, 16, 17, 22, 23 |
| NFR9 — money crosses as a patterned string | 10, 11, 14 |

---

## What this Unit deliberately does not build

- **No routes.** U2 defines the shapes and the gates; the Units that own the
  features add the endpoints.
- **No lens *resolution*.** U2 defines the `Lens` types so the harness has
  something to match on; **U3** resolves them against owned batches and
  enrollments.
- **No `Money` type.** U1 owns it. U2 asserts its *schema* representation.
- **NFR14.4** — the structural-equivalence clause requiring both lookup
  branches to execute the same queries. **U3's**, per BR4.4: U2 owns no lookup
  code, and building a mechanism it cannot run would be the over-reach the
  fixture obligation exists to prevent.
