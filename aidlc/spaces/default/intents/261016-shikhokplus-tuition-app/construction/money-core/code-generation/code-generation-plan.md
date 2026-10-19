# Code Generation Plan — `money-core` (U1)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> First code in the project. Four design stages stand behind it: 39 business
> rules, 34 NFR requirements, a verified ledger identity, and a CI pipeline
> that gates all of it. This plan says exactly what gets written, in what
> order, and what is deliberately **not** written.

## Sources

- [upstream] `construction/money-core/functional-design/` — `rules.md` (39
  rules), `functional-spec.md` (§2 operations, §3 worked scenarios, §5
  boundary cases, §5.6 refusals), `entities.md`
- [upstream] `construction/money-core/nfr-requirements/` — NFR9.1–NFR9.25
- [upstream] `construction/money-core/nfr-design/security-design.md` —
  mechanisms, NFR9.26–NFR9.32
- [upstream] `construction/money-core/infrastructure-design/cicd-pipeline.md`
  — the eleven gate steps
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [upstream] `inception/delivery-planning/bolt-plan.md` — B1 DoD
- [team] `## Code Style` (money as a type, line length 88, Sphinx docstrings,
  Ruff rule sets, mypy strict islands), `## Testing Posture` (test-first
  predicate, 100% branch, the property test)
- [project] `## Forbidden` / `## Mandated`
- [human] Three decisions taken at this stage's entry — see **Decisions taken
  into this plan** below

---

## Decisions taken into this plan

Three questions were open when this stage began. All three are now answered,
and each changes what gets built.

| Decision | Effect on this plan |
|---|---|
| **Build everything except the formatting operation** | `format(locale)` and its per-locale rendering table are **out of scope**. The B1 DoD is amended to match (see §D). Everything else in the DoD is in scope |
| **Persist the carry-forward correction** to `team.md` | A post-approval step, not a code step. Recorded in §E so it is not lost |
| **Amend B2's and B3's definitions of done** to own the two schema assertions | A post-approval edit to `bolt-plan.md`, also §E. Closes the NFR9.32 gap that has been carried since NFR Design |

---

## A. What gets built

### A.1 Python package layout

```
app/money/
  __init__.py          # public surface only: Money, LedgerEntryKind,
                       # DerivedQuantities, the two errors
  _money.py            # the Money value type
  _kinds.py            # the seven-kind closed enumeration
  _ledger.py           # entry shape, the fold, derived quantities
  _rounding.py         # ROUND_HALF_UP as the single declared constant
  _errors.py           # MoneyValidationError
  pydantic.py          # the API chokepoint — one annotated type
  sqlalchemy.py        # the storage chokepoint — one TypeDecorator
```

**Why the split.** `_money.py` must not import `_ledger.py`: the value type is
usable without the ledger vocabulary, and keeping that direction one-way is
what lets the ledger grow without touching the type. `pydantic.py` and
`sqlalchemy.py` are separate modules because they are the only files importing
a framework, which keeps the core importable with neither installed.

**`__init__.py` exports the public surface only.** Every underscore-prefixed
module is private. This matters for the import gates: a consumer importing
`app.money._ledger` directly is doing something the design did not intend, and
the public surface is what makes that visible.

### A.2 The `Money` type — `_money.py`

| Member | Rule | Note |
|---|---|---|
| `__init__` / construction | BR1.1, BR1.2, BR1.3, BR1.7 | Refuses a float by **type**, not value — `1000.0` is refused identically to `0.1`. Quantizes to 2dp. Refuses beyond ten integer digits |
| frozen dataclass, `__eq__`, `__hash__` | BR1.5 | Immutable; equality and hashing consistent because quantization happens at construction |
| `__add__`, `__sub__` | BR2.1 | `Money`-only. `Money + 5` is a type error, not a surprise |
| `apply_rate(rate)` | BR2.2, BR2.10, BR3.1 | The named multiplication. Refuses a float rate and a negative rate; permits zero and above one |
| `allocate(n)` | BR2.3, BR2.8, BR2.9 | Exact-sum split. Refuses `n < 1`. **Magnitude-then-sign** for negatives |
| `sum(iterable)` | BR2.5 | Zero identity for an empty iterable |
| `ZERO` | BR2.4 | Module constant so no caller writes a bare `0` |
| `is_zero()`, `is_positive()` | BR2.6 | Sign knowledge in one place |
| comparison operators | BR2.6 | Type-safe: comparing to `int` is a type error |
| **no** `__float__`, `__int__`, `__mul__`, `__truediv__` | BR1.6, BR2.2 | Absence is the mechanism |

### A.3 The ledger — `_kinds.py`, `_ledger.py`

- **`LedgerEntryKind`**: the seven kinds as a closed enumeration. [BR4.2]
- **`LedgerEntry`**: a value shape — kind, amount, enrollment, period. **No
  table, no id, no persistence.** [BR4.1 refuses a negative amount]
- **The fold → `DerivedQuantities`**: eight quantities, single linear pass.
  - **Total mapping with no default** [NFR9.19]. No `else`, no
    `.get(kind, ZERO)`.
  - **Exhaustiveness proven statically** [NFR9.27, NFR9.28] via an
    `assert_never` in the unreachable position, so mypy proves totality and
    **no coverable branch is emitted**.
  - `available_credit` and `total_outstanding` **derived, never stored**
    [BR4.4, BR4.5]; credit application is `min(available, owed)`, so
    over-application is unrepresentable rather than refused.
  - `carry_forward` / `carried_out` produced **as a pair** by one operation
    [BR4.6], so a one-sided carry cannot be written.

### A.4 Errors — `_errors.py`

**One class: `MoneyValidationError`.** [BR1.8] Every refusal path raises it.
No conflict class, no transient class, no envelope, no HTTP mapping — three of
the five taxonomy classes are structurally unreachable in a module with no
state and no I/O, and U2 owns the envelope.

### A.5 Chokepoints — `pydantic.py`, `sqlalchemy.py`

- **API**: one annotated type reused by every schema. Serializes to the
  canonical string; **refuses a negative** [BR5.7]; rejects a JSON number on
  input [BR5.2].
- **Storage**: one `TypeDecorator` → `NUMERIC(12,2)` [BR5.3].

### A.6 Kotlin — `core/model/`

Inside the single `:app` module, per the settled one-module decision.

- `Money.kt` — `@JvmInline value class Money(val amount: BigDecimal)`
- `MoneySerializer.kt` — reads **only** a JSON string; **fails loudly** on a
  JSON number [NFR9.9, B1 DoD]

### A.7 Gates and configuration

Everything `cicd-pipeline.md` §B lists: both import gates with their violation
fixtures and configuration assertions, the coverage configuration scoped by
behaviour, the named-test manifest, the coverage-scope check, `make check`,
and the CI workflow with its backend and android-unit jobs.

---

## B. Build order

Test-first where the predicate holds: *the correct output is knowable from the
requirement without having written the code, **and** a wrong answer would be a
money error or an authorization error.* That predicate holds for **everything
in A.2 through A.5**.

| # | Step | Cadence |
|---|---|---|
| 1 | Project skeleton, `pyproject.toml`, Ruff + mypy config, `make check`, lockfiles | — |
| 2 | Both import gates, their fixtures, their configuration assertions | Test-first: the fixtures *are* the tests |
| 3 | `_rounding.py`, `_errors.py` | — |
| 4 | `Money` construction and representation | **Test-first** |
| 5 | `Money` arithmetic — add, subtract, sum, apply_rate, allocate | **Test-first**, including every §5 boundary case |
| 6 | Kinds, entry shape, the fold, derived quantities | **Test-first**, from §3's eight worked scenarios |
| 7 | The property test on the ledger identity | **Test-first** — it is the specification |
| 8 | Both chokepoints | **Test-first**, both directions |
| 9 | Kotlin value class and serializer | **Test-first** on the loud-failure case |
| 10 | Named-test manifest, coverage-scope check, CI workflow | — |

**Step 7 before step 8 deliberately**: the identity must hold over the fold
before anything serializes it.

---

## C. Tests

Full detail in `unit-test-instructions.md`. The shape:

- **Every rule in `rules.md` that has runtime behaviour** gets at least one
  named test.
- **Every worked scenario in §3** becomes a test with its computed expected
  values — eight scenarios, each checked against the identity.
- **Every boundary case in §5** gets a test: period attribution, rounding at
  the half (all five sampled values), zero, negative, approved-exceeds-claimed.
- **The property test**: randomized histories, generators derived from the
  kind enumeration [NFR9.20], with a **hand-written expected effect per kind**
  [NFR9.25] so the test can disagree with a mis-sided kind.
- **The two import-gate fixtures**, asserted to fail.
- **100% branch coverage** on `app/money/**`, no exclusion pragmas.

---

## D. Out of scope, and the DoD amendment

**`format(locale)` is not built.** Per the decision recorded above: the
rendering is unspecified (OQ-B1-1 — digit set, grouping interval, separators,
currency symbol), and a guessed rendering shipped to installed phones cannot
be withdrawn while a missing one is additive under the `/v1/` policy.

**This requires amending B1's Definition of Done**, which currently lists
`format(locale)` among its unconditional deliverables. Without the amendment
B1 would ship failing its own checklist. The amendment:

- remove `format(locale)` from B1's DoD deliverable list;
- add a line recording that it is deferred pending OQ-B1-1, and naming B6 as
  the point where it becomes blocking, since B6 is the first Bolt whose
  response assembly needs a display string.

Also **not built**: the locale-completeness check (step 8 of the pipeline),
which has nothing to check until a rendering specification exists. It is
deferred with the operation, as a single unit of work rather than a check
without a subject.

Everything else in B1's DoD is in scope.

---

## E. Post-approval steps that are not code

Three, recorded here so they are not lost between the plan and the work:

1. **Persist the carry-forward learning** to `team.md` through the learnings
   gate. The affirmed rule currently reads *"carrying 1000 into a second 1000
   charge reads 2500 owed against a true 1500"* — figures that reproduce under
   no implementation. Correct: **2000 true, 3000 one-sided**. Already fixed in
   `decisions.md` and `bolt-plan.md`; `team.md` changes only at this gate.
2. **Amend B1's DoD** per §D.
3. **Amend B2's and B3's DoD** to own the two schema assertions — the OpenAPI
   money-pattern assertion to B2, the column type-and-precision assertion to
   B3. This closes NFR9.32, carried as a GAP since NFR Design, and stops both
   Bolts passing their stated checklists while the checks never exist.

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
      "text": "Tests are a first-class deliverable in every Bolt, not a follow-up Bolt. A Bolt\nwithout its tests is not done.\n\n- **Methodology**: custom\n- **Methodology evidence**: The cadence genuinely differs by surface, and\n  recording a single uniform value would misdescribe what we actually do. Three\n  facts drive the split. (1) The money paths — fee-cycle arithmetic,\n  carry-forward, partial approval, waiver — have **mandatory** tests by stated\n  requirement [TC-20, D-23, PU-5.7], are arithmetic over a ledger rather than\n  I/O-shaped, and have expected values knowable before any implementation\n  exists. That is the exact precondition under which test-first pays: the test is\n  a specification we can write correctly without having written the code, and the\n  fee model is *already known to be in revision* [D-18], so a suite that pins the\n  arithmetic is what makes the next revision safe rather than frightening. (2) The\n  Compose UI surface is the opposite case. There is **no declared Kotlin or\n  Android experience** [OC-3], so a Compose test written before the\n  implementation is as likely to encode a misunderstanding of the framework as to\n  catch a defect, and when it passes it certifies that misunderstanding — worse\n  than no test. (3) The privacy boundary is structural rather than arithmetic\n  [D-7, TC-13] — enforced by table design, row-level security and distinct\n  response schemas — so its tests are adversarial probes against a built\n  boundary, which is inherently test-after. A uniform `tdd` would be a commitment\n  we would break on the Compose Bolts; a uniform `test-after` would weaken the\n  one surface where the requirement is explicit and the preconditions for\n  test-first are actually met. `custom` is the accurate value.\n- **Ordering**: Write the failing test first whenever **both** of these hold —\n  the correct output is knowable from the requirement without having written the\n  code, **and** a wrong answer would be a money error or an authorization error —\n  and for everything else implement the layer, then write and run that layer's\n  tests before the Bolt is complete.\n\nThat ordering is a **predicate, not a list**, and the distinction is the point:\nan enumeration plus \"everything else\" fails open, because every case nobody\nanticipated defaults to test-after. The following are *examples* of the\npredicate holding, not its boundary:\n\n- every change to the money module;\n- every fee-cycle and payment-verification state transition — generation,\n  carry-forward, partial and reduced approval, waiver, rejection;\n- the `(enrollment_id, period)` idempotency constraint;\n- every lens-resolution and row-level-security rule, wherever that code lives;\n- `inactive_from` date semantics [PU-2.9] — it must stop future fee cycles,\n  leave existing dues standing, and leave the student active in other batches,\n  all three of which are money-adjacent and fail quietly;\n- the cross-batch dues query [PU-7.2], which is driven by outstanding balance\n  and not by active status, so students who left owing money still appear.\n\n**A change meeting the predicate does not escape it by being implemented in\nKotlin**, or in a route handler rather than in the money module. Where the code\nlives is not part of the test.\n\n**Test-after is a cadence, not permission to write the test against the\nimplementation.** A test-after test is written from the acceptance criterion. If\nwriting it requires reading the implementation to know what to assert, the\nacceptance criterion is the defect.\n\nSupporting bullets, which do not replace the two fields above:\n\n- **Backend coverage floor**: 80% line coverage, enforced in CI, with no\n  decrease permitted. This comes from the active `classic` scope at Comprehensive\n  test strategy and may not be weakened to make a step pass. **The authorization\n  layer is measured as branch coverage rather than line coverage** — lens\n  resolution is pure branching over teacher, student and guardian and owned-batch\n  membership, so line coverage on it is close to meaningless.\n- **The money module carries 100% branch coverage**, because the defects that\n  matter there live in the branches: the short-month clamp, the\n  carry-forward-versus-waive fork, the partial-approval path, the\n  zero-and-negative edges. An 80% line floor can be met while leaving the waiver\n  branch entirely unexecuted, which satisfies the number and misses the\n  requirement. Two things make that target honest rather than decorative: the\n  money module contains **no I/O, no session and no HTTP**, so 100% stays\n  reachable; and branch coverage is supplemented by obligations not reducible to\n  a percentage — a named test per fee-cycle and payment state transition, and a\n  documented boundary case per money input (period boundaries, rounding at the\n  half, zero, negative, an approved amount exceeding the claimed amount). We also\n  add one property-based test (Hypothesis) on the invariant that holds across all\n  of it: for any sequence of charges, approvals, carry-forwards and waivers,\n  `charged - received - forgiven == outstanding`, and `outstanding` never goes\n  negative. That invariant catches the class of defect no enumerated example\n  will.\n- **Android carries named obligations and no percentage floor.** Gating a surface\n  the reviewer cannot yet evaluate produces tests written to raise a number; that\n  is a reason to drop the *percentage*, not a reason to drop the *obligation*,\n  and this is the thinnest-reviewed part of the product. So:\n  - every ViewModel ships tests for its state machine — loading, success, error,\n    and the explicit retry path for a failed write [TC-8, D-9];\n  - every money-carrying model class ships a serialization test proving decode\n    from a JSON string and **loud failure** on a JSON number, because a lenient\n    decoder that quietly accepts a number and converts is the actual failure mode\n    and it passes a happy-path-only both-sides test;\n  - Kotlin line coverage is reported from the first Android Bolt, with **no\n    decrease permitted** once three Android Bolts have merged. A no-regression\n    ratchet gives the trend teeth without anyone inventing a target they cannot\n    justify.\n- **Test types by layer**: pytest for backend unit and integration tests, with\n  integration tests running against a **real PostgreSQL 16** container via\n  testcontainers rather than SQLite — row-level security, `NUMERIC(12,2)`,\n  `ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test and\n  SQLite emulates none of them faithfully. JUnit plus Turbine for Kotlin\n  ViewModel and repository tests, targeting the response-to-UiState mapping\n  function rather than an untargeted \"the ViewModel\". Compose UI tests for the\n  OTP entry path and the mid-class attendance path.\n- **Database tests connect as a restricted non-superuser role.** PostgreSQL\n  documents that superusers and table owners bypass row-level security entirely\n  [pg-rls], and the default test-container connection is `postgres`, a superuser.\n  A privacy-boundary suite run as superuser passes identically whether the policy\n  is correct, broken, or entirely absent — so the strongest test obligation we\n  have would certify nothing. Integration tests therefore connect as the same\n  restricted role the application uses, and a **meta-test asserts that\n  `current_user` is not a superuser and that row-level security is in force**\n  (`row_security` on, policy present) before the privacy suite runs.\n- **Privacy boundary tests are adversarial, and the API-level half is a\n  schema-wide invariant.** No teacher-lens response schema may contain any field\n  in the owner-private profile set, enforced by iterating the generated OpenAPI\n  schema rather than by remembering to write a test per endpoint — per-endpoint\n  tests fail to cover the endpoint added in PU-7 after everyone stopped thinking\n  about it. The probe suite explicitly covers the IDOR shape: teacher A\n  requesting teacher B's batch, a guardian requesting a non-child's enrollment, a\n  student requesting a fee cycle not their own. That is the vulnerability class a\n  scanner cannot find and the one most likely to exist, because finding it\n  requires knowing the intended policy.\n- **Schemathesis validates conformance, not correctness, and never counts as\n  privacy coverage.** A teacher-facing response schema that wrongly includes\n  profile fields is perfectly *conformant*. We keep Schemathesis for what it is\n  good at — unexpected 500s, type and required-field drift, auth present on every\n  route — and we add the check it cannot provide: **an OpenAPI schema-diff gate**,\n  where the committed schema must match the generated one and CI fails if they\n  diverge. A stale committed schema is worse than none, because the contract tests\n  then pass against fiction.\n- **Money representation is itself a test target.** Every money value crosses the\n  API as a JSON **string** [TC-7, D-20], asserted on both sides: the backend never\n  emits a JSON number for a money field, and the client rejects one.\n- **Idempotency gets a concurrency test, not a sequential one.** The fee-cycle\n  guarantee is a database constraint precisely because application-level guards\n  fail under concurrency [D-21, TC-12]; testing it by calling the job twice in\n  sequence would pass against the broken implementation the decision exists to\n  avoid. The test runs overlapping generations and asserts the **outcome** rather\n  than the absence of an exception: after N overlapping generations exactly one\n  row exists per `(enrollment_id, period)` and the ledger total is unchanged. It\n  also covers the case concurrency alone misses — the daily self-healing re-run\n  [PU-5.5] must be idempotent across *days*, so a cycle generated on the 1st is\n  not regenerated on the 2nd.\n- **Token lifecycle is tested as a state machine.** Refresh-token rotation with\n  reuse detection has a security-critical failure mode: present a rotated-out\n  token and the whole token family must be invalidated. Untested, this degrades\n  silently into non-rotating refresh tokens, because the happy path is identical.\n  We also test that refresh tokens are stored hashed, that access-token expiry is\n  actually enforced, and that a 15-minute-expired token is rejected.\n- **Both account-deletion paths are tested** [TC-19]: the in-app path and the\n  externally accessible route. Each must assert that deletion removes what the\n  Data Safety form claims it removes and retains only what the privacy policy\n  discloses [RC-4, RC-5], per each table's written disposition. Deletion features\n  are the ones most reliably shipped broken, because nobody tests the absence of\n  data.\n- **PU-3.6's mid-class speed requirement is not discharged by a correctness\n  test.** A Compose UI test asserts behaviour, not latency. Either the attendance\n  obligation is a **Macrobenchmark on a low-end device profile** (which also\n  serves TC-17), or PU-3.6 has no automated verification in V1 and carries an\n  explicit manual check in the pilot. Both are acceptable; silently using a\n  correctness test to discharge a performance requirement is not.\n- **The Bangla layout obligation needs a concrete verifier** [TC-15, D-43]:\n  Compose screenshot tests at the longest Bangla string, or an explicit\n  per-screen manual check. \"Must not break the layout\" currently has no verifier,\n  and an unverifiable obligation is a wish.\n- **One command, local and in CI.** `make check` or equivalent, the same\n  entrypoint in both places. For a solo build this is the single most important\n  property of the gate: a gate reproducible only by pushing is a gate that gets\n  bypassed. The blocking suite needs no secret to run locally, which means the\n  SMS gateway is stubbed in tests and the sandbox-credential question affects\n  staging only, never CI.\n- **CI runs on GitHub Actions**, with the Android job moving to CodeBuild only if\n  minutes become a real constraint. Splitting by cost is cheaper than migrating by\n  platform, and the PR integration is where the only review happens. The Android\n  job is split from the backend job so a Kotlin build does not gate a backend PR,\n  dependencies are cached, the backend path stays under about ten minutes or it\n  will be skipped, and the per-month minute budget is stated and monitored\n  against [OC-4].\n- **A green `main`, not just a green PR.** With squash-merge and one reviewer, the\n  post-merge run on `main` is the only thing that catches a stale-base merge.\n- A red suite blocks the merge. Coverage below floor blocks. Schema drift blocks.\n  Tests that always pass regardless of implementation are defects in their own\n  right and are rejected in review.\n\n---\n\n- The ledger invariant for the money module's property-based test is `total_charged - total_forgiven - (total_receipt + total_credit_grant) == total_outstanding - available_credit`, with `available_credit = credit_grant - credit_apply >= 0`, `total_outstanding >= 0`, and `sum(carry_forward) == sum(carried_out)`. This supersedes the earlier `charged - received - forgiven == outstanding`, which omitted carry-forward and predated credit, and an intermediate form that omitted credit_grant from cash in. Money received as credit is money received: cash in is receipts plus credit grants. (learned 2026-10-17) \n\n- Carry-forward is recorded two-sided — a `carried_out` entry relieves the originating period and a `carry_forward` entry charges the receiving one — so the two cancel at enrollment level. A one-sided carry counts the same debt in both periods: carrying 1000 into a second 1000 charge reads 2500 owed against a true 1500. A named test covers a multi-period carry, not only a single one, because a single carry can pass against a model that double-counts. (learned 2026-10-17) \n\n- A money invariant is verified before it is recorded as satisfied, never asserted from reasoning alone: worked cases across every ledger operation, then randomized histories composing those operations in arbitrary order. This project's identity was wrong twice before randomized testing settled it, and it is the property-based test standing behind 100% branch coverage on the money module — an unverified invariant there certifies the arithmetic it was meant to check. (learned 2026-10-17)"
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
  "input_sha256": "sha256:8d4232907d7742aa2e6bf6bea8dbe93970ec38906047457e9f9ca7b0949b543d",
  "contract_sha256": "sha256:ecb48a84ca7056521bc54449eace28b7404032f81d0d00278b554f1d42057808"
}
```

> **Note on the rendered contract.** Its `applicable_notes` (omitted above for
> length; regenerable with `aidlc engine testing-posture render`) still carry
> the stale carry-forward figure — *"reads 2500 owed against a true 1500"* —
> because they are generated from `team.md`, where the correction is still
> pending. That correction is §E step 1 of this plan. The figures this Unit
> actually builds and tests against are **2000 true, 3000 one-sided**, per
> `functional-spec.md` §3 S4/S5 and the tests in
> `unit-test-instructions.md` A.3.

---

## F. What this plan does not decide

- **The Bangla rendering** (OQ-B1-1) — deferred by decision, not by oversight.
- **The collection-rate arithmetic** — open upstream, lands in B10; this
  Unit's property test extends to cover it when it settles.
- **Anything in B2–B11.** This plan builds U1 and the project skeleton the
  pipeline needs, and nothing else.
