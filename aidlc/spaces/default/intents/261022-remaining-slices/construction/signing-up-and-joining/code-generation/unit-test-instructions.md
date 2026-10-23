# Unit Test Instructions — D1 `signing-up-and-joining`

**Stage**: code-generation (3.5)
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices
**Test strategy**: Standard — 5–8 tests per component, unit plus integration
at key boundaries

---

## The exact command for this unit

Runnable **before** the first test-first cycle, and scoped to D1's paths only:

```bash
python -m pytest tests/authz/test_acceptance_predicate.py tests/authz/test_decision_transitions.py tests/authz/test_invitation_lens.py tests/batches/test_removability_after_signup.py tests/db/test_migration_0004.py tests/accounts/ tests/privacy/test_address_boundary.py -v
```

Kotlin, scoped to D1's new tests:

```bash
./gradlew :android:testDebugUnitTest --tests '*Invitation*' --tests '*Signup*' --tests '*Acceptance*'
```

**Not** `make check` or a bare `pytest`. Build and Test runs every unit's
commands, so an unscoped command would rerun the whole suite once per unit.

### Before the first RED step

Verify the runner and the container prerequisite:

```bash
python -m pytest tests/authz -q --collect-only
docker info >/dev/null 2>&1 && echo "docker reachable" || echo "INTEGRATION SUITE WILL SKIP"
```

**The second line matters more than it looks.** `tests/conftest.py` skips the
whole integration suite at module level when no Docker daemon is reachable —
so without it, the row-level-security probes, the migration tests and the
roster tests do not run, and the command still exits zero. D1's privacy and
migration obligations are in that half.

---

## Framework and configuration

Already configured; D1 adds no test dependency.

| Concern | Choice | Notes |
|---|---|---|
| Runner | pytest 8.4 | `pyproject.toml` |
| Database | **Real PostgreSQL 16** via testcontainers | Not SQLite — RLS, `NUMERIC(12,2)` and partial indexes are the behaviours under test |
| Database role | `shikkhok_app`, a **restricted non-superuser** | A superuser bypasses RLS entirely, so the privacy suite would certify nothing |
| Coverage | `pytest-cov` | Existing floors apply |
| Kotlin | JUnit + Turbine; JaCoCo ratchet | `android/coverage.gradle.kts`, floor 30.95, no decrease |

**The RLS meta-test is a precondition, not a test.** `tests/privacy/conftest.py`
asserts `current_user` is not a superuser and `row_security` is on before the
privacy suite runs. D1's new privacy probes inherit it automatically by living
under `tests/privacy/`.

---

## Coverage targets

| Target | Value | Source |
|---|---|---|
| Backend line coverage | **80%**, no decrease | Scope floor, enforced in CI |
| Authorization layer | **Branch** coverage, not line | Lens resolution is pure branching; line coverage on it is near-meaningless |
| Money module | 100% branch | Untouched by D1 |
| Kotlin | No percentage floor; **no decrease** from 30.95 | Named obligations instead |

**Never lower a threshold to make a step pass.** If a target cannot be met,
surface the gap.

---

## Test inventory

### Test-first (Phase A — must fail before implementation)

| File | Tests | Covers |
|---|---|---|
| `tests/authz/test_acceptance_predicate.py` | 4 | An account on only `pending`/`declined` links resolves no student or guardian lens and both summary counts are zero [BR1.1, BR1.2] |
| `tests/authz/test_decision_transitions.py` | 5 | Per-link transitions; no reset to `pending`; one action moves both columns only when both links name the same account [BR5.2–BR5.4, BR6.1] |
| `tests/authz/test_invitation_lens.py` | 3 | `pending`/`declined` grants a one-enrollment invitation lens; `accepted` does not; exactly three fields [BR1.3, BR1.4] |
| `tests/batches/test_removability_after_signup.py` | 3 | A seat stays removable after the named person signs up and before they accept; dormancy reads the decision [BR7.1, BR7.2] |

### Test-after

| File | Tests | Covers |
|---|---|---|
| `tests/db/test_migration_0004.py` | 4 | Conditional backfill both ways; `NOT NULL`; no server default |
| `tests/accounts/test_signup.py` | 7 | `Owner` only for Teacher; one transaction; duplicate number; account before code |
| `tests/accounts/test_lookup.py` | 5 | Names neither teacher nor batch; pre-fill and role lock; signing up leaves the seat `pending` [BR5.1] |
| `tests/accounts/test_ceilings.py` | 5 | Separate counters; narrowest-first; a refusal consumes nothing; OTP response stays byte-identical [BR2.1, BR2.2] |
| `tests/accounts/test_decisions_api.py` | 6 | Accept, decline, un-decline; a declined seat leaves the enrollments and stays in the invitations |
| `tests/privacy/test_address_boundary.py` | 4 | No teacher-lens schema carries `address`; IDOR probes [BR3.2] |

~46 backend tests. Kotlin: ~14 across mapping functions and money serialization.

---

## The named-test manifest

`tests/named_tests.toml` exists because 100% branch coverage says the branches
executed — **it cannot say the right tests exist.** A missing named test whose
branches another test already covers is invisible to the number.

D1 adds 7 entries, each with its acceptance criterion and rule id, for the
four test-first files and the two merged-reader predicates.
`test_named_test_manifest.py` asserts every entry resolves to a test that
exists and runs.

---

## Mocking and test data

| Boundary | Approach |
|---|---|
| Database | **Never mocked.** Real PostgreSQL via testcontainers |
| SMS gateway | `NullGateway` in tests; sandbox credentials in staging |
| Clock | Injected where a window boundary matters (ceilings) |
| OTP | Never asserted on a real code; the byte-identical test compares responses |

**Test data is built through the application's own service functions**, not by
raw inserts, so a seat created in a test has the same invariants as one a
teacher creates. The one exception is migration testing, which necessarily
writes rows in the pre-migration shape.

---

## What a test-after test may not do

Test-after is a cadence, not permission to write the test against the
implementation. **A test-after test is written from the acceptance
criterion.** If writing it requires reading the implementation to know what to
assert, the acceptance criterion is the defect — fix the criterion, not the
test.

Tests that always pass regardless of implementation are defects in their own
right and are rejected in review.
