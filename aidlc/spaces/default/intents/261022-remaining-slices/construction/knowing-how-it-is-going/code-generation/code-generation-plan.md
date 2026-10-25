# Code Generation Plan — D5 `knowing-how-it-is-going`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices
**Plan approval**: required before any code is written

> **D5 is the smallest backend unit of the six and the one whose defects are
> hardest to see.** No table, no migration, no money arithmetic, no
> concurrency, no job. **Every figure it produces is derived — and a derived
> figure that is wrong still balances.** Nothing in `make check` can tell a
> correct earnings total from one that double-counts a credit.
>
> **Three things carry the whole unit**, and each has a named test that
> cannot pass against its defect:
>
> 1. **`receipt + credit_grant`, never `credit_apply`** — the test asserts
>    the TOTAL (2000, not 2500), because month 1 reads 1500 under both the
>    correct fold and the defect.
> 2. **No predicate on `inactive_from`** — the test needs a seat that is
>    **both inactive and owing**, because one using only active owing seats
>    passes against the wrong predicate.
> 3. **Grouped by `period`, never `created_at`** — the fixture is a
>    late-recorded payment, which is the normal case rather than an edge.

## Sources

- [upstream] `functional-design/entities.md`, `rules.md` (22 rules,
  BR1.1–BR4.5), `functional-spec.md`
- [upstream] `nfr-design/` — all six documents; `logical-components.md` § 1
  is the module split this plan builds
- [upstream] `nfr-requirements/` — 61 ids defined, traced in
  `traceability.json`
- [upstream] `infrastructure-design/cicd-pipeline.md` §§ 2, 3 — the two CI
  gates and their four preconditions
- [human] 2026-10-25 — OQ-2 stays open; `collection_rate` does not ship
- [code] read 2026-10-25: `app/fees/views.py:295-357`, `app/fees/balances.py`,
  `app/money/_ledger.py`, `app/money/_kinds.py`, `app/db/models.py:925-940`,
  `app/api/deps.py`, `app/authz/lenses.py`, `app/contract/routes.py`,
  `tests/fees/test_query_count.py:129-160`,
  `.github/workflows/release-android.yml`, `.github/workflows/deploy.yml`,
  `infra/versions.tf`, `infra/outputs.tf`

---

## 1. What this unit ships

| Surface | Count | Notes |
|---|---|---|
| New tables | **0** | Every figure derives from built rows [BR4.2] |
| Migrations | **0** | `dispositions.py` stays at 25 |
| Backend packages | 1 | `app/analytics/` — four modules |
| Routes | **2** | `GET /v1/me/dues`, `GET /v1/me/overview` |
| Android features | 2 | `feature/dues/`, `feature/overview/` |
| Screens | 2 | with a row each in the Bangla check table |
| CI gates | 2 | the size gate and the ZAP job, **release-time only** |
| New dependencies | 1 | `bundletool`, CI-only, pinned |

**`PUBLIC_ROUTES` is not touched** — eight entries, count asserted twice.

---

## 2. Build order

| # | Step | Ordering |
|---|---|---|
| 1 | `app/analytics/seats.py` — the owned-seat join | **test-first** |
| 2 | `app/analytics/earnings.py` — the kind-selecting fold | **test-first** |
| 3 | `app/analytics/dues.py` — row assembly, the `per_cycle` minimum | **test-first** |
| 4 | `app/analytics/upcoming.py` — the next exam | **test-first** |
| 5 | Schemas and the two routes | test-after |
| 6 | The privacy probe suite | **test-first** |
| 7 | Android: DTOs, mappers, two screens | test-after |
| 8 | The Bangla rows (2) | file check |
| 9 | The size gate | test-after (demonstrated once) |
| 10 | The ZAP job | test-after (demonstrated once) |

**Steps 1–4 and 6 are test-first and the predicate's second clause is what
puts them there.** A wrong seat set is an **authorization** error — it
returns another teacher's data. A wrong fold is a **money** error. Both
outputs are knowable from the requirement before any code exists: `rules.md`
computes the 2000/2500 case and `security-design.md` § 2 tabulates every
probe's expected value.

**Steps 5 and 7 are test-after.** Route plumbing over an already-tested
layer, and Compose UI where — per `team.md` — a test written first is as
likely to encode a framework misunderstanding as to catch a defect.

---

## 3. `app/analytics/`, and which modules may touch a session

**This table is the unit's one structural control** [logical-components § 1]:

| Module | Session | Holds |
|---|---|---|
| `seats.py` | **yes** | The one owned-seat join; the one ledger select |
| `upcoming.py` | **yes** | One exam select, `LIMIT 1` |
| `earnings.py` | **no** | Pure fold: entries in, period totals out |
| `dues.py` | **no** | Pure assembly: seats + entries in, rows out |

**`dues.py` taking no session is load-bearing, not stylistic.** It is where
the per-seat loop lives, so it is the one place a query could be added per
row [NFR20.32] — **a module that cannot reach a session cannot make that
mistake.** The N+1 obligation becomes a property of the module graph rather
than a rule someone must remember.

### The query shapes

```sql
-- seats.py, statement 1: ONE join, no resource id        [security § 1]
SELECT e.id, e.batch_id, e.display_name, b.name
  FROM enrollment e JOIN batch b ON b.id = e.batch_id
 WHERE b.owner_id = :owner_id
   AND e.student_decision <> 'declined'          -- BR1.7
-- NO predicate on inactive_from                 -- BR1.2
-- NO predicate on joined_on                     -- entities.md § 4

-- seats.py, statement 2: ONE select, folded in memory
SELECT enrollment_id, kind, period, amount
  FROM ledger_entry WHERE enrollment_id IN (:seat_ids)

-- upcoming.py: ONE select
SELECT ... FROM exam x JOIN batch b ... JOIN batch_subject s ...
 WHERE b.owner_id = :owner_id AND x.date >= :today
 ORDER BY x.date, x.created_at, x.id LIMIT 1     -- BR3.3
```

**Two statements for dues, three for the overview, whatever the teacher's
size.** The earnings total and the trend fold the **same** ledger read twice
— two figures from one read, so they cannot disagree.

**The oldest unpaid period comes from the same in-memory `per_cycle` map**,
not from the built `oldest_unpaid_period`, which takes one enrollment and
would be one query per row. A test pins the two to the same value
[NFR20.33].

---

## 4. The two routes

| Route | Lens | Returns |
|---|---|---|
| `GET /v1/me/dues` | Teacher | `DuesRow[]`, possibly empty [BR1.5] |
| `GET /v1/me/overview` | Teacher | earnings, trend?, next exam? |

**Neither declares a path or query parameter.** A schema test asserts both
operations have an **empty parameter list** — a plain predicate, not a
judgement about whether a name denotes a resource.

**The `/me/` prefix does not imply this**: `GET /v1/me/fees` carries a
`StudentLens` *and* an `enrollment_id` query parameter. So the assertion is
load-bearing — a later `/v1/me/dues?batch_id=` would be perfectly
conventional and would reintroduce the IDOR class.

**Three response shapes, none collapsible** [NFR19.52]: an empty collection,
a zero **value**, and an **absent** block. Absent and zero are different wire
shapes.

---

## 5. Android

`feature/dues/` and `feature/overview/`, matching `feature/roster/`'s
convention. `core/network/AnalyticsDto.kt`. **No new dependency** — no
charting library, so the trend renders with existing Compose primitives or
as a list.

**The mapper decides every rendering question**, including the three
absences. **No composable compares a domain value**: `if (outstanding > 0)`
on the client would be the dues membership rule, reimplemented where nothing
tests it.

Both screens get a row in `docs/delivery/bangla-layout-check.md`. **The
earnings figure is the string to check hardest** — a money amount in Bangla
numerals under a long Bangla label, on the screen a teacher opens most.

---

## 6. The two CI gates

**The size gate** — one step in `release-android.yml`, after "The bundle is
signed" and before Syft, signing its own APK set with a **throwaway
keystore** generated in the step. The upload keystore is shredded at line 187,
**before** the signature step at 194, so signing with it would fail every
release. Pinned, checksum-verified `bundletool` [NFR2.21]. Precondition:
`[ -f "$aab" ]`.

**The ZAP job** — `zap-api-scan.py`, **not** `zap-baseline.py`, which has no
`-f` option and performs no schema import. Reads `terraform output -raw
api_url` after an explicit `init` keyed by the job's own environment input.
Assumes `AWS_DEPLOY_ROLE_ARN`, not the infrastructure role that can destroy.

**Four preconditions across the two gates**, because each would otherwise
exit zero having checked nothing:

| Gate | Vacuous pass | Guard |
|---|---|---|
| Size | A missing AAB | `[ -f "$aab" ]` |
| ZAP | No `init` — `output` reads no state | `[ -n "$url" ]` after init |
| ZAP | An unreachable host | A `/health` probe |
| ZAP | **A schema that never imported** | A path count from the JSON report |

**The fourth hides behind the third passing**, which is why it is specified
rather than left to ZAP's exit code.

---

## 7. Definition of done

- `make check` green, with the statement-count property asserted by **growing
  batches per teacher**, not seats per batch — D5's new axis.
- BR2.1's case asserted at **2000, not 2500**, on the total.
- Bolt 5's hypothesis asserted in **both** halves [BR1.2, BR1.3].
- The generated schema carries **no** `collection_rate` and **no** parameter
  on either new operation; `PUBLIC_ROUTES` still 8; `dispositions.py` still
  25; `migrations/versions/` unchanged.
- Two rows in the Bangla check table.
- Both CI gates demonstrated failing once.

---

## 8. What D5 does not build

No table, migration or index. No money arithmetic — `derive()` and `Money`
are built. No `collection_rate` [BR4.1, OQ-2]. No cache or rollup. No job,
heartbeat or cron. No alert. No charting library. No RLS policy. No new error
class. No latency assertion anywhere.

---

## Testing Contract

```json
{
  "version": 1,
  "methodology": "custom",
  "source": "team",
  "ordering": "Write the failing test first whenever **both** of these hold — the correct output is knowable from the requirement without having written the code, **and** a wrong answer would be a money error or an authorization error — and for everything else implement the layer, then write and run that layer's tests before the Bolt is complete.",
  "scope": "classic",
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
  "input_sha256": "sha256:ead71391fd1b965e6ba93466891a92ee7c79f56c4c5890f84e9ca14257ae5bc9",
  "contract_sha256": "sha256:3e5ed58e58959c39e4f534bf45533286315a0ec4e7adda70a17544b1e976e78a"
}
```

The same block appears in `unit-test-instructions.md`, where § 2 applies its
`ordering` predicate item by item.

---

## Assumptions & Open Questions

- **`app/analytics/` is this plan's package name**; no upstream artifact
  names it.
- **`/v1/me/dues` and `/v1/me/overview` are proposed paths.**
- **OQ-2 stays open and `collection_rate` does not ship** [BR4.1]. What is
  open is narrow: FR8.3's definition is annotated open to correction and
  AC8.3.4's credit rule postdates it. **For the human.**
- **BR2.1 and AC8.3.4 take opposite sides on when a credit counts.** Earnings
  count it on arrival; AC8.3.4 counts it in the period it settles. Both are
  right for their own figure — **so closing OQ-2 is also deciding whether two
  figures on one screen may use different month conventions. For the human.**
- **Where the ZAP job lives is open** — a fourth job in `deploy.yml` or its
  own `security-scan.yml`. Both satisfy every requirement. **For the human.**
- **Whether `AWS_DEPLOY_ROLE_ARN` can read Terraform state is unverified.**
  If it cannot, widen that role by one permission rather than reaching for
  the infrastructure role that can destroy.
- **Whether ZAP's report exposes a parseable path count is unverified.** If
  it does not, the precondition needs a different mechanism — **not
  dropping**; it guards the vacuous pass that hides behind a passing probe.
