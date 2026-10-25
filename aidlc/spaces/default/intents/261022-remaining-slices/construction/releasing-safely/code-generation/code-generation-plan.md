# Code Generation Plan — D6 `releasing-safely`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **D6 is the terminal, release-blocking unit, and most of its work is making
> absences assertable.** A row that must be gone, a policy claim with no
> generator, a retention class nothing enforces, three cascades that destroy
> retained records.
>
> **Six things are built here**, and the order matters because three of them
> are preconditions for the others:
>
> | # | What | Why it is in this position |
> |---|---|---|
> | 1 | **Migration `0007`** | Everything else deletes; this is what makes deletion safe |
> | 2 | **The constraint assertion** | Proves `0007` did what it claims, transitively |
> | 3 | **Purpose-scoped OTP** | The public route cannot exist safely without it |
> | 4 | **The deletion ceiling cascade** | Same: a public SMS route needs its own budget |
> | 5 | **Both deletion paths** | The unit's actual feature, on 1–4 |
> | 6 | **The policy generator and the purge** | Independent of 1–5; the compliance half |
>
> **`0007` is first because it is the only irreversible step**, and because
> items 5 and 6 both destroy data against the schema it fixes.

## Steps

- [x] **Step 1** — Migration `0007`: three `ondelete` values, two columns
      made nullable, constraints dropped by their real names, the
      `Account.deleted_at` docstring corrected, all four pinned revision
      literals moved, `test_no_d5_migration.py` renamed or re-commented [§ 1]
- [x] **Step 2** — `tests/db/test_cascade_contradictions.py`: the recursive
      `pg_constraint` walk, with its anti-vacuity reach assertions and both
      states exercised [§ 2]
- [x] **Step 3** — Purpose-scoped OTP: a required `purpose` on `issue()`, the
      predicate in `verify()`'s `WHERE`, and the shadowing test [§ 3]
- [x] **Step 4** — The deletion ceiling cascade: `check_and_consume_deletion()`
      over the existing `_consume()`, four `del_*` scopes, the alert on the
      global scope [§ 4]
- [x] **Step 5** — Both deletion paths, the teacher refusal as a precondition,
      absence enumerated from the manifest for both roles, the
      `PUBLIC_ROUTES` comment corrected [§ 5]
- [x] **Step 6** — The policy generator and the retention purge [§ 6]
- [x] **Step 7** — `make check` green: the floors met, the integration suite
      shown to have actually run [§ 7]

## Sources

- [upstream] `functional-design/functional-spec.md`, `rules.md`, `entities.md`
- [upstream] `nfr-design/security-design.md` — §§ 1–7, DESIGN-1…DESIGN-8
- [upstream] `nfr-requirements/security-requirements.md` — NFR14.78–NFR14.102
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR21.2–NFR21.6
- [prior] D5's `code-generation-plan.md` — the plan shape and Testing Contract
- [human] 2026-10-25 — hard delete; `0007`'s three columns; teacher refusal;
  the deletion-specific global sub-ceiling
- [code] read 2026-10-25: `app/auth/otp.py`, `app/auth/ceilings.py`,
  `app/api/auth.py`, `app/db/models.py`, `app/governance/dispositions.py`,
  `app/contract/routes.py`, `tests/db/test_governance.py`,
  `tests/db/test_no_d5_migration.py`, `migrations/versions/0001`, `0002`

---

## 1. Migration `0007`

**Three `ondelete` values change**, and two of the three columns are
`NOT NULL` so each needs `nullable=True` as well — a bare `ondelete` flip
fails at migration time.

| Table | Column | Today | After | `NOT NULL` today |
|---|---|---|---|---|
| `enrollment` | `student_account_id` | CASCADE | **SET NULL** | no |
| `payment_claim` | `submitted_by_account_id` | CASCADE | **SET NULL** | **yes** |
| `queued_submission` | `submitted_by_account_id` | CASCADE | **SET NULL** | **yes** |

**The constraints are dropped by their REAL names**, which are not the names
the model implies [DESIGN-4], verified in the migration sources:

| Constraint | Model implies | Actually named |
|---|---|---|
| enrollment → account (student) | `fk_enrollment_student_account_id_account` | **`fk_enrollment_account_id_account`** (`0001:201`) |
| enrollment → account (guardian) | — | `fk_enrollment_guardian_account` (`0002:363`) |
| `payment_claim` → account | convention | convention — created by `0005` |
| `queued_submission` → account | convention | convention — created by `0006` |

`0002:132` renamed the **column** with `alter_column`, which does not rename
its constraint. **A comment in `0007` records why the name looks wrong**, so
the next reader does not "correct" it.

**`Account.deleted_at`'s docstring is corrected in this change** — it reads
*"Reserved for U11's deletion paths"* and the column becomes unused under a
hard delete [NFR21.2]. The column stays; dropping it is irreversible.

### The four pinned revision literals move with it

Verified by grep, and the fourth is not a migration test:

| Location | What it pins |
|---|---|
| `tests/db/test_no_d5_migration.py:29` | `EXPECTED_HEAD`, plus the revision **count** at `:26` |
| `tests/db/test_migration_from_head.py:142` | `assert revision == "0006"` |
| `tests/db/test_migration_runs.py:121` | `assert revision == "0006"` |
| **`tests/auth/test_endpoints.py:194`** | **`body["migration_revision"]`** — `/health`'s value, which the Deployment practice makes part of the post-deploy **smoke** set |

**`tests/db/test_migration_rollback_is_total.py:117` asserts `"0001"` and is
deliberately NOT changed** — the failed-migration path, which `0007` does not
move.

**`test_no_d5_migration.py` is renamed or re-commented**, not merely
re-pinned: its name and docstring say *"D5 ships no migration"*, and after
D6 it is asserting something else. Editing the constant while leaving the
name is how a file comes to describe a check it no longer performs.

---

## 2. The constraint assertion

**`tests/db/test_cascade_contradictions.py`**, run as the restricted role
through the existing `restricted_session` fixture — no new fixture, no new
privilege.

A **recursive** query over `pg_constraint` finds every table reachable from
`account` by `ON DELETE CASCADE`, and fails when any reachable table's
`DISPOSITIONS` entry is `RETAIN_WITH_BASIS`. The query **carries the path**,
so the failure names the chain rather than sending the reader to `models.py`.

**It reads `pg_constraint`, never `information_schema`** [DESIGN-8].
Measured against a real PostgreSQL 16: an ungranted table is invisible in
`information_schema` but **visible in `pg_constraint`**, because the system
catalog is not permission-filtered by table grant. The governance suite
records the near-miss this avoids — the money gate silently skipped
`batch.default_fee` until a grant was added. **A comment states this**, since
"simplifying" to `information_schema.referential_constraints` would
reintroduce the narrowing and the test would keep passing.

**Before `0007` this test fails on three rows; after it, zero.** Both states
are exercised — the pre-state via the migration-staging helpers in
`tests/db/migration_support.py`, so the test is shown to be capable of
failing rather than merely passing.

---

## 3. Purpose-scoped OTP codes

`issue()` gains a **required** `purpose` parameter — no default, because
`OTP_PURPOSE`'s own docstring records that a default *"would let a second
consumer arrive without anyone choosing its ceiling"*.

`verify()` gains the same parameter and **puts it in the `WHERE`, beside
`phone`** — not in a check after the row is fetched [DESIGN-1]:

```sql
WHERE phone = :phone AND purpose = :purpose
ORDER BY issued_at DESC LIMIT 1 FOR UPDATE
```

**The fetch-then-check form is a real bug, not a style preference**: a
sign-in code issued *after* a deletion code would shadow it, and the user
would be refused by the deliberately contentless `_refused()`.

`otp_request.purpose` is `String(32)`; `"deletion"` is eight characters, so
**no migration**. Every existing call site passes `OTP_PURPOSE` explicitly.

---

## 4. The deletion ceiling cascade

`check_and_consume_deletion()`, a **third cascade over the same
`_consume()`** — one implementation, because the built docstring says a
second copy is how two cascades stop agreeing.

| Member | Value | Length | Scope | Limit |
|---|---|---|---|---|
| `DEL_NUMBER_HOURLY` | `del_number_hour` | 15 | number | 3 |
| `DEL_NUMBER_DAILY` | `del_number_day` | 14 | number | 5 |
| `DEL_IP_HOURLY` | `del_ip_hour` | 11 | /24 prefix | 10 |
| `DEL_GLOBAL_DAILY` | `del_global_day` | 14 | global | **50** |

**`scope_kind` is `String(16)`**, and the obvious prefixes do not fit —
`deletion_number_day` is 19, `delete_number_day` is 17. The built comment
records PostgreSQL refusing exactly this once already. **The `del_` prefix is
deliberate and a comment says why.**

**`DEL_GLOBAL_DAILY` is the load-bearing control** [DESIGN-6], which is the
opposite of how a reader would rank the four: `ip_prefix_of` reduces IPv4 to
a /24 so spanning prefixes never meets the per-IP limit, and an IPv6 address
contains no `.` so it becomes its own whole-address scope. **`ip_prefix_of`
is not changed** — it is a shared primitive with three built dependents, and
the last unit before release is the wrong place.

`fire_ceiling_alert` fires on `DEL_GLOBAL_DAILY`: it is the one scope whose
breach has no innocent explanation.

**The new counters need no retention entry** — `rate_limit_counter` already
carries `HOURS_48`, longer than every ceiling window it serves [DESIGN-7].

---

## 5. Both deletion paths

```
In-app:    DELETE /v1/me            (authenticated)
External:  GET    /account-deletion (the page, no session)
           POST   /account-deletion (after OTP ownership proof)
```

**Both `/account-deletion` entries are already in `PUBLIC_ROUTES`**, declared
in D1 as *"pre-declared D6 scope"*. **D6 lands handlers against entries that
exist**, so the asserted count of eight does not change — and
**Correction, 2026-10-25, found during the build**: this plan said
`app/contract/routes.py:33-49` reads "Exactly five" against a frozenset of
six. **It does not.** It reads "Exactly eight", the count is asserted twice,
and the comment itself records that it read "five" until 2026-10-22. `git
log -S` dates that fix to commit `eec0f92`, **before D6 began**.

**The stale claim came from `team.md`'s 2026-10-22 drift note**, which
described the defect and was never updated when the same day's commit fixed
it — and I carried it into this plan and the test instructions without
opening the file. **The project's own rule applied to the document that
states it**: where a comment states a number, the number is a claim, and a
*practices file* stating a number is a claim too.

The genuinely stale sentence in that comment was a different one —
*"Two of these have no handler yet"* — which D6 falsifies. That is corrected,
along with two further unasserted count claims found nearby:
`app/api/auth.py:3` ("three of the five `PUBLIC_ROUTES`") and
`app/api/health.py:7` ("one of the five"). For `health.py` the number was
**removed** rather than restated, because the count belongs in the one place
that asserts it.

**One deletion function, two callers** [BR3.1]. The test compares the
**surviving row sets** of the two paths rather than asserting each against a
hand-written expectation, because the route that drifts is the external one.

### The refusal is a precondition

A teacher owning any batch **cannot delete** [BR1.6]. Checked **before
anything is destroyed, in the same transaction** — a deletion that removes
half an account and then refuses is worse than either outcome.

**This refusal is not contentless**, unlike every other refusal on this
route: the caller has already proven ownership of the number, so enumeration
resistance does not apply, and a contentless refusal would leave a teacher
concluding the feature is broken. It carries a `message_key`.

**It is load-bearing, not belt-and-braces**: 11 `RETAIN_WITH_BASIS` tables are
reachable from `account` by cascade, **7 only through `owner → batch`**, which
`0007` does not touch.

### Deletion asserts absence, enumerated from the manifest

The test derives its table list from `DISPOSITIONS` [BR1.3], so **a table
added later with no deletion handling fails without the test being edited**.
`HARD_DELETE` rows must be gone; `RETAIN_WITH_BASIS` rows must survive;
`ANONYMIZE_IN_PLACE` rows must be present with the named fields cleared.

**Asserted for BOTH roles.** A test using only a guardian passes against the
defect `0007` fixes.

---

## 6. The policy generator and the purge

### The generator

`scripts/generate_privacy_policy.py`, beside the existing `release_notes.py`.
It writes **between markers** in the committed `docs/legal/PRIVACY.md`; the
**marker region is the unit of comparison**, so human prose around it stays
editable. `make check` regenerates and compares [BR2.3] — the same shape as
the built OpenAPI schema-diff gate.

**Deterministic**: same manifest, same bytes. No timestamp, no unordered
dict.

**The `account` entry's disposition AND its basis both change** [NFR14.101].
The basis currently argues for anonymization — the disposition the human
overruled — and the generator reads that field. Correcting one without the
other publishes a mechanically consistent, substantively wrong policy.

**The hand-written factual table is removed**, since it is the rival source
the generated region replaces [NFR14.90].

### The purge

`app/governance/commands.py`, following `main_generate()`'s built shape: **no
required arguments**, so it is also the by-hand recovery procedure. Seven
tables carry finite windows, derived from the manifest rather than
hard-coded:

| Window | Tables |
|---|---|
| 7 days | `otp_request`, `staging_sms_outbox`, `verify_attempt` |
| 48 hours | `rate_limit_counter` |
| 12 months | `auth_audit_log`, `reminder_event` |
| until expiry + 30 days | `refresh_token` |

**`LIFE_OF_ACCOUNT` is never purged** [BR4.2] — 18 of 25 tables, including
every attendance, mark and ledger row. **The dangerous implementation is the
natural one**: iterate all tables and apply a default window to those without
an explicit one, which deletes the product's entire history on first run.

**Idempotent and chunked** [BR4.1]. The honest failure of a retention job is
dying halfway and being re-run; an unchunked `DELETE` over a year of
`otp_request` rows locks the table on a single small instance.

**It registers a heartbeat under its own name**, so D4's freshness
enumeration covers it with **no change to that mechanism** — the property
option B was chosen for. `user_data.sh.tftpl`'s comment already anticipates
this.

---

## 7. Test plan, against the ordering predicate

The predicate: **test-first when both** the correct output is knowable from
the requirement without the code **and** a wrong answer would be a money or
authorization error.

| Work | Predicate holds? | Order |
|---|---|---|
| The constraint assertion (§ 2) | **yes** — a cascade destroying retained records is an authorization-adjacent data loss, and the expected set is knowable | **test-first** |
| `verify()` purpose filter (§ 3) | **yes** — a sign-in code confirming a deletion is an authorization error | **test-first** |
| The shadowing case (§ 3) | **yes** — same predicate, and it is the case a naive fix gets wrong | **test-first** |
| Deletion ceilings (§ 4) | **yes** — exhausting a victim's sign-in allowance from a public route is an authorization error | **test-first** |
| The teacher refusal (§ 5) | **yes** — destroying other people's retained records | **test-first** |
| Deletion absence assertions (§ 5) | **yes** — the expected row sets come from the manifest | **test-first** |
| Migration `0007` itself (§ 1) | no — a schema change, verified by § 2's test | test-after |
| The generator (§ 6) | no — output shape is not knowable before writing it | test-after |
| The purge (§ 6) | **partly** — `LIFE_OF_ACCOUNT` must never be purged, which is knowable and catastrophic | **test-first for BR4.2**, test-after for the rest |

**The three ceiling tests assert that something still WORKS**: exhaust the
deletion scope, then assert a **sign-in** code still issues. A test asserting
only that the deletion route refuses **passes against the shared-counter
defect**.

### Coverage

80% line floor, no decrease. **Money module untouched** — D6 adds no money
arithmetic, and its 100% branch floor must stay met. New authorization code
(the refusal) is measured as **branch** coverage.

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

## 8. What D6 does not do

No new table. No new column. No new `PUBLIC_ROUTES` entry. No new disposition
kind or retention class. No new error class. No third-party dependency. No
new strict mypy island. **No change to `ip_prefix_of`** [§ 4]. No change to
any earlier unit's behaviour except the three constraints `0007` alters.

**No Android work.** D6 is backend and compliance only; the in-app deletion
entry point is a screen, and whether it lands here or is deferred is the one
scope question below.

---

## Assumptions & Open Questions

- **`DELETE /v1/me` is a proposed path** for the in-app route; no upstream
  artifact names it. `PUBLIC_ROUTES` fixes the external pair exactly.
- **The in-app deletion SCREEN is not in this plan.** D6's upstream describes
  both *paths*; a Compose settings screen with a confirmation flow is
  Android work this plan does not cover, and no upstream artifact assigns it
  to D6 explicitly. **For the human**: if the in-app path must be reachable
  from the app in V1, that screen is additional scope here.
- **The purge's cron hour is not set here** — it belongs with the entry in
  infrastructure, clear of the fee job's 02:00 UTC and D5's 01:00.
- **`test_no_d5_migration.py`'s rename is proposed, not required.** The
  alternative is keeping the filename and rewriting its docstring. Either is
  acceptable; leaving both stale is not.
- **The Data Safety form and Play declarations are release deliverables that
  this plan does not produce as code.** They are written against the
  *generated* policy, which this plan does produce. **For the human.**
- **No figure in this plan was produced by running D6 code**, which does not
  exist. Every count was read from the manifest, the built source, or a grep
  on 2026-10-25, and §2's catalog-visibility claim was measured against a
  real PostgreSQL 16.
