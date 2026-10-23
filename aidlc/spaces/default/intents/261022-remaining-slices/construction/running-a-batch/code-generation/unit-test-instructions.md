# Unit Test Instructions — D2 `running-a-batch`

**Stage**: code-generation (3.5)
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices
**Test strategy**: Standard — 5–8 tests per component, unit plus integration
at key boundaries

---

## The exact command for this unit

Runnable **before** the first test-first cycle, scoped to D2's paths only:

```bash
python -m pytest tests/batches/test_accepted_count.py tests/batches/test_removal_refusals.py tests/batches/test_roster_states.py -v
```

Kotlin, scoped to D2's tests:

```bash
./gradlew :android:testDebugUnitTest --tests '*Roster*' --tests '*Batches*' --tests '*Guardian*' --tests '*CreateBatch*' --tests '*AddStudent*' --tests '*RemoveSeat*'
```

**Not** `make check` or a bare `pytest`. Build and Test runs every unit's
commands, so an unscoped command reruns the whole suite once per unit.

### Before the first RED step

```bash
python -m pytest tests/batches -q --collect-only
docker info >/dev/null 2>&1 && echo "docker reachable" || echo "INTEGRATION SUITE WILL SKIP"
```

**The second line matters here more than it did for D1.** D2's tests are
*all* roster and batch tests, which are integration tests against a real
PostgreSQL container. Without Docker the entire D2 suite skips and still exits
zero — so a green run would mean nothing was checked.

---

## Framework and configuration

Already configured; D2 adds no test dependency.

| Concern | Choice | Notes |
|---|---|---|
| Runner | pytest 8.4 | |
| Database | **Real PostgreSQL 16** via testcontainers | Row-level security and the decision enums are the behaviours under test |
| Database role | `shikkhok_app`, restricted non-superuser | A superuser bypasses RLS, so the privacy suite would certify nothing |
| Kotlin | JUnit + Turbine; Robolectric for rendering | |
| Coverage | pytest-cov; JaCoCo ratchet at **45.84** | See the ratchet note below |

---

## Coverage targets

| Target | Value |
|---|---|
| Backend line | **80%**, no decrease |
| Authorization layer | **Branch**, not line |
| Money module | 100% branch — **untouched by D2** |
| Kotlin | No percentage floor; **no decrease from 45.84** |

**Never lower a threshold to make a step pass.** And for Kotlin specifically:
if the ratchet drops, the first hypothesis is **not** "cover your new code".
D1 excluded composables from the denominator because JaCoCo cannot instrument
them under Robolectric; a drop means `**/ui/*Kt*` is catching something that
is not a composable. **Narrow the glob.**

---

## Test inventory

### Test-first (must fail before Phase B)

| File | Tests | Covers |
|---|---|---|
| `tests/batches/test_accepted_count.py` | 5 | Counts seats with at least one accepted link; denominator includes declined seats; zero-seat batch; all-declined batch [BR1.2, BR1.4] |
| `tests/batches/test_removal_refusals.py` | 4 | Claimed and erased return **different** codes and message keys; neither is retryable [BR3.2] |

### Test-after

| File | Tests | Covers |
|---|---|---|
| `tests/batches/test_roster_states.py` | 6 | A guardian-less seat reports `absent`; a split seat returns both states; `status` still returns its three values [BR2.1, BR2.2] |
| `RosterStateMapperTest` (extended) | ~8 | `isDeclined` for declined only; `displayLabel` number-vs-name; `isRemovable` read not derived [BR2.3, BR3.1] |
| `BatchesStateMapperTest` | ~4 | The count comes from the response; `Empty` vs `Loaded` [BR1.3] |
| `GuardianStateMapperTest` | ~4 | `OneChild` vs `SeveralChildren` as separate states |
| Screen tests (Robolectric) | ~10 | Declined marked per row and pending not; split seat rendered once; two refusals with two remedies; **Back after a child switch** |

~22 backend, ~26 Kotlin.

---

## The three obligations that need naming

**1. The count is tested from the criterion, not from the implementation.**
"At least one accepted link, over every seat the teacher created" is knowable
from AC1.3.5a before any SQL exists. Writing the test after the aggregate
would let the aggregate define what the count means.

**2. The two refusals are tested as a pair.** A test asserting "removal is
refused" passes for both and distinguishes neither. The assertion is that the
codes and message keys **differ**, because the remedies differ.

**3. Back after a child switch has no other verifier.** No server-side control
can observe it: both requests are legitimately authorized, the lens is correct
in both, and neither response is anomalous. The Robolectric test is the only
mechanism, so it is not optional and it is not a review note.

---

## Mocking and test data

| Boundary | Approach |
|---|---|
| Database | **Never mocked.** Real PostgreSQL via testcontainers |
| Seats | Built through `add_enrollment`, then decisions moved through D1's service functions |
| Erased seats | The erasure markers set directly — there is no service path that sets them in D2's scope |

**Test data goes through the application's own service functions**, so a seat
in a test carries the same invariants as one a teacher creates. The erasure
case is the exception and is marked as such rather than quietly special.

---

## What a test-after test may not do

Test-after is a cadence, not permission to write the test against the
implementation. **A test-after test is written from the acceptance
criterion.** If writing it requires reading the implementation to know what to
assert, the acceptance criterion is the defect.

Tests that always pass regardless of implementation are defects in their own
right and are rejected in review.
