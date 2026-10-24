# Unit Test Instructions — D3 `collecting-fees`

**Stage**: code-generation (3.5)
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices
**Test strategy**: Standard — 5–8 tests per component, unit plus integration
at key boundaries

---

## The exact commands for this unit

Runnable **before** the first test-first cycle, scoped to D3's paths only:

```bash
python -m pytest tests/fees tests/notifications -v
```

Kotlin, scoped to D3's tests:

```bash
./gradlew :android:testDebugUnitTest --tests '*Fee*' --tests '*Payment*'
```

**Not** `make check` and not a bare `pytest`. Build and Test runs every
unit's commands, so an unscoped command reruns the whole suite once per unit.

### Before the first RED step

```bash
python -m pytest tests/fees --collect-only -q
docker info >/dev/null 2>&1 && echo "docker reachable" || echo "INTEGRATION SUITE WILL SKIP"
```

**The second line is not optional for this unit.** D3's tests are almost
entirely integration tests against a real PostgreSQL container — the unique
constraint, `ON CONFLICT DO NOTHING`, `NUMERIC(12,2)` and the row-level
behaviour are the things under test, and SQLite emulates none of them. Without
Docker the whole suite skips and still exits zero, so a green run would mean
the money paths were never checked.

---

## Framework and configuration

Already configured; D3 adds one test dependency only if the across-days test
needs a clock library — prefer injecting a `now` parameter over patching.

| Concern | Choice | Notes |
|---|---|---|
| Runner | pytest 8.4 | |
| Database | **Real PostgreSQL 16** via testcontainers | The constraint and the conflict behaviour are the behaviours under test |
| Database role | `shikkhok_app`, restricted non-superuser | A superuser bypasses RLS, so the privacy probes would certify nothing |
| Concurrency | `threading.Barrier`, real threads | Imports at the **top of the file** |
| Kotlin | JUnit + Turbine; Robolectric for rendering | |
| Coverage | pytest-cov; JaCoCo ratchet at **48.52** | |

---

## Coverage targets

| Target | Value |
|---|---|
| Backend line | **80%**, no decrease from 91.68% |
| Authorization layer | **Branch**, not line |
| Money module | **100% branch — D3 adds no code there** |
| Kotlin | No percentage floor; **no decrease from 48.52** |

**Never lower a threshold to make a step pass.**

**If the money module's branch coverage drops, the cause is not a missing
test.** D3 writes nothing in `app/money/`. A drop means something imported it
in a way that executed a new path, which is a boundary violation to
investigate rather than a number to restore.

---

## Test inventory

### Test-first (31 tests; each must fail before its implementation step)

| File | Tests | Covers |
|---|---|---|
| `tests/fees/test_periods.py` | 6 | `YYYY-MM`; the clamp; the anchor is not rewritten; leap year; NULL anchor [BR2.1–BR2.3] |
| `tests/fees/test_resolution.py` | 3 | Enrollment fee, batch default, **zero is real**, both-NULL refuses [BR2.4] |
| `tests/fees/test_generation.py` | 5 | One charge at the resolved fee; no money on the cycle; conflict is success [BR1.1–BR1.3] |
| `tests/fees/test_generation_races.py` | 2 | **Barrier-released threads**; outcome asserted [BR1.3] |
| `tests/fees/test_generation_across_days.py` | 2 | Self-healing; a later re-run appends nothing [BR1.4] |
| `tests/fees/test_decline_semantics.py` | 5 | Student stops and reverses; **guardian does neither**; pending generates; un-decline resumes [BR1.6–BR1.9] |
| `tests/fees/test_carry.py` | 3 | The pair in one transaction; 1000 into 1000 reads **2000**; a carry cannot exceed the origin [BR3.1, BR3.2] |
| `tests/fees/test_credit.py` | 3 | Over-approval becomes credit; `min(available, owed)`; applied with the charge; 1000 charge with 200 credit leaves **800** [BR4.1–BR4.5] |
| `tests/fees/test_claims.py` | 2 | Oldest unpaid cycle or refused; zero and negative refused [BR5.1, BR5.2] |
| `tests/fees/test_verification.py` | 4 | Shortfall **400 not 900**; explicit carry-or-waive; atomic commit; rejection and correction [BR5.3–BR5.7] |
| `tests/fees/test_fee_privacy.py` | 6 | Adversarial probes; the collection number bounded **downward** [NFR14.32, NFR14.36–.39, BR6.4] |

### Test-after

| File | Tests | Covers |
|---|---|---|
| `tests/fees/test_status_enum.py` | ~4 | The server-computed enum and the four claim statuses [BR6.1, BR6.3] |
| `tests/fees/test_schemas.py` | ~5 | Money as a JSON string on both sides [BR6.2] |
| `tests/notifications/test_fcm.py` | ~5 | Best-effort, post-commit, `UNREGISTERED` deletes, no device identifier [BR7.2] |
| `tests/notifications/test_boundary.py` | 1 | **No feature package defines an FCM client** [NFR19.24] |
| `tests/fees/test_commands.py` | ~4 | The command runs; the heartbeat stamps; **the zero-cycles case stamps too** [NFR25.9] |
| `FeeStateMapperTest` | ~10 | Exhaustive-or-fail status mapping; every decision a mapper field |
| Screen tests (Robolectric) | ~10 | No composable compares a domain value |

~75 backend, ~20 Kotlin.

---

## The five obligations that need naming

**1. The concurrency test asserts an outcome, not an absence of exceptions.**
After N overlapping generations: exactly one row per `(enrollment_id, period)`
and the ledger total unchanged. `tests/auth/test_ceilings.py` records why a
sequential version is worthless — it "passes against the broken implementation
the constraint exists to prevent." **Copy its shape, not its `import
threading` inside the function**; this project requires imports at the top.

**2. The across-days test is a different test, and it is the forgettable
one.** Racing threads cannot reach a re-run on a later day. It injects time
rather than racing, and the first test looks like it already covers
generation, which is exactly why this gets dropped.

**3. The decline asymmetry is tested from both roles.** A student decline
stops generation; a guardian decline does not. This has already produced one
defect in this project on the presentation side, so a test that only exercises
the student path would leave the known failure mode uncovered.

**4. The separating cases are the point, not the happy paths.**
- Shortfall: 1000 charged, 1500 claimed, 600 approved → **400**, not 900.
  Measuring against the claim would let a payer change what they owe by
  changing what they assert.
- Carry: 1000 into a second 1000 charge → **2000** owed, not 3000. A one-sided
  carry double-counts.
- Credit: a 1000 charge with 200 applied → **800**, not 1000.

Each separates a correct implementation from a plausible wrong one. A test
that only asserts the happy path distinguishes neither.

**5. The heartbeat's zero-cycles case is mandatory.** Generation is monthly,
so most days legitimately create nothing. A heartbeat written only when
`cycles_created > 0` leaves the row stale for weeks during correct operation,
fires the 48-hour alert constantly, and gets it muted — reaching the alert's
own failure mode by the opposite route.

---

## Mocking and test data

| Boundary | Approach |
|---|---|
| Database | **Never mocked.** Real PostgreSQL via testcontainers |
| Money arithmetic | **Never mocked.** `app/money/` is real in every test |
| Clock | **Injected**, not patched — the across-days test needs it as a parameter |
| FCM | A null adapter behind the protocol, as the SMS gateway already does |
| Seats and batches | Built through the existing service functions |

**Test data goes through the application's own service functions**, so a seat
in a fee test carries the same invariants as one a teacher creates.

---

## What a test-after test may not do

Test-after is a cadence, not permission to write the test against the
implementation. **A test-after test is written from the acceptance
criterion.** If writing it requires reading the implementation to know what to
assert, the acceptance criterion is the defect.

Tests that always pass regardless of implementation are defects in their own
right and are rejected in review.
