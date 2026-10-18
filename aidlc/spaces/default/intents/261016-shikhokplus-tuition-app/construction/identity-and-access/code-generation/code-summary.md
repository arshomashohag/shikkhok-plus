# Code Summary — `identity-and-access` (U3)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

> **The skeleton walks.** A real FastAPI endpoint, a real PostgreSQL 16
> row behind a real row-level-security policy, a real OTP through the
> gateway seam, a real token pair, and rotation with reuse detection —
> asserted end to end over HTTP.
>
> The device leg remains: one real SMS to the developer's own number at
> the checkpoint, which is the only place real money is spent before
> launch, because BulkSMSBD has no sandbox.

## Sources

- [stage] `code-generation-plan.md` — the 34 approved steps
- [stage] `unit-test-instructions.md`
- [upstream] `functional-design/rules.md` — BR1.1–BR6.3
- [upstream] `functional-design/entities.md`
- [upstream] `functional-design/functional-spec.md`
- [upstream] `nfr-design/security-design.md` — §B.1, §C.1
- [upstream] `infrastructure-design/infrastructure-specification.md`
- [upstream] `inception/contract-design/contract-summary.md` — §C.4
- [team] `## Testing Posture`, `## Code Style`, `## Walking Skeleton`
- [project] `## Forbidden` / `## Mandated`

---

## A. What runs

| Verified | Evidence |
|---|---|
| **472 Python tests** | `make check` green |
| **38 Android tests** | `./gradlew :android:testDebugUnitTest` |
| Backend line coverage | **91.60%** against an 80% floor |
| `app.authz` branch coverage | **100%** |
| `app.money` branch coverage | **100%**, unchanged from B1 |
| Types | mypy clean, 52 source files |
| Lint and format | ruff clean |

The end-to-end path, asserted in one test: issue → the rendered SMS body
→ verify → a working token pair → rotation → **a replayed token refused
with 401**.

---

## B. Every control was verified against the wrong implementation

**This is the part worth reading.** Each control below is easy to build
so it passes a confirmatory test and is silently wrong. Rather than
assert the tests are adversarial, I built each defect and recorded which
tests fired.

| Defect injected | What fired | What did NOT |
|---|---|---|
| **Cross-request lens cache** | BR1.2, BR1.3, the two-request query count, the module-cache scan — **4 tests** | Everything else passed |
| **Global-first ceiling order** | Both accounting tests — **2 tests** | Every threshold test passed |
| **Per-process counter dict** | The two-worker test | — |
| **Bare SHA-256 for the OTP** | The two key-dependent tests | **"stored ≠ transmitted" PASSED** |
| **Early return on unknown number** | The statement-equivalence test | Response-shape tests passed |
| **Hash both branches, write one** | The statement-equivalence test | A hash-symmetry test would have passed |
| **Invalidate only the presented token** | The family test — **1 of 5 transitions** | The other four passed |
| **Log `error_message`** | The credential-leak test | — |
| **Drop the RLS policy** | Every privacy probe | — |
| **Run the suite as superuser** | The meta-test | **Every probe would have PASSED** |
| **Audit write fails mid-transaction** | The new outcome test | **Both fail-open tests PASSED** |
| **Read-then-write counter** | The real concurrency test | **The old "concurrent" test PASSED** |
| **A domain comparison in the ViewModel** | The no-business-logic test | — |

Two rows deserve emphasis:

- **The bare-digest row.** "The stored value differs from the
  transmitted one" is satisfied by SHA-256, and by ROT13. Only the
  *not-reproducible-without-the-key* half distinguishes a keyed MAC from
  a digest, which is why NFR9.5 states both.
- **The superuser row.** With a *correct* policy and a superuser
  connection, a teacher reads the profile. The suite reports a pass it
  has not earned. That is the entire reason the meta-test runs first.

### B.1 The last three rows were found by the review, not by me

**The method caught the defects I pointed it at, and missed one I had
pointed it at wrongly.** That distinction is worth more than the table
above, so it is recorded rather than smoothed over.

**The audit row is the important one.** I injected the audit failure *at
the mock level* — monkeypatching `session.execute` — which never touches
a real connection and therefore never poisons a transaction. So my test
proved the exception was caught and nothing more. PostgreSQL aborts the
entire transaction on any failed statement, so the swallowed error left
the caller holding an aborted transaction whose `commit()` issues a
ROLLBACK and **returns normally**.

Measured through the real `otp.issue` path: a code was returned, the SMS
went out, and the OTP row was silently lost — a code that can never
verify, after consuming a ceiling slot that moves the user closer to
lockout. **The audit log did not fail to record the authentication; it
destroyed it.** Fixed with a savepoint, and the regression asserts the
caller's row survives rather than that no exception escaped.

The second row is the same shape: a test *named* for concurrency ran
sequentially. Against a read-then-write counter, all 8 racing requests
were admitted against a limit of 3.

**The lesson, stated plainly**: injecting a defect proves only as much
as the layer you inject it at. A mock-level injection tests the
`except` clause; only a database-level one tests the guarantee.

---

## C. Three things the build caught that the design had not

### C.1 NFR6.1's one-query rule caught a real defect in my first draft

Lens resolution fetched `owner_id` and `enrollment_id` as **follow-up
selects** — three round trips per request. The query-count assertion
failed, and the fix was scalar subqueries inside the single statement.

> This matters beyond the round trips: **three round trips per request
> is exactly what makes caching the lens look necessary**, and BR1.1 has
> to survive that argument on a 2 GB instance.

### C.2 The coverage floor was measuring none of this Bolt's code

B2 wrote an explicit `--cov` package list. B3 added five packages and
did not extend it, so the floor **passed at 95% while measuring none of
what B3 had written**. It did not fail — it silently covered less, which
is the quietest way a coverage gate erodes.

Fixed, and `tests/gates/test_coverage_scope.py` now asserts the list
against the packages on disk. I reproduced the exact omission and
confirmed it fails.

### C.3 A test that fired on the comment warning against the defect

The AD_ID check matched the manifest's own explanatory comment, which
names `AD_ID` in order to forbid it. **A test that fails on the warning
against a thing, while saying nothing about the thing, is worse than no
test** — the obvious fix is to delete the warning. It now parses
`<uses-permission>` elements, verified to fire on a real declaration.

---

## D. B1's inherited obligation, discharged

**NFR9.32** — the money column assertion B1 authored and could not run,
having no schema. B3 is the first Bolt with one.

It is **vacuously true here**, which is stated as its own test so the
pass is not mistaken for evidence. I verified it fires by creating the
columns a later Unit might add in hand-written SQL — the path that
bypasses the SQLAlchemy `TypeDecorator` entirely:

| Column | Result |
|---|---|
| `amount_due double precision` | **caught** by both assertions |
| `total_paid numeric` (unconstrained) | **caught** by the precision assertion |
| `amount_charged numeric(12,2)` | passes |

---

## E. What is deliberately low-coverage

| Module | Coverage | Why |
|---|---|---|
| `app/db/seed_skeleton.py` | **0%** | BR6.3 forbids application code from importing it; a test asserts no module does. Covering it would mean importing it. |
| `app/db/session.py` | 32% | The app runs on the test fixture's engine, so `build_engine` is exercised at deployment rather than here. |

Both are honest rather than convenient: the first is a rule, the second
is a real gap the skeleton checkpoint closes by running against the
deployed host.

---

## F. What this Bolt did not build

- **No batches or enrollments** — U4's. The tables are created empty and
  read; a test asserts this Unit writes neither.
- **No deletion** — U11's, so both paths are specified once against the
  full schema.
- **No money** — U1 owns the type; none crosses this surface.
- **No HTTP client on Android yet.** The Compose screen, the Activity
  and the ViewModel are here; the repository behind them is a
  placeholder returning a transport failure, because configuring a base
  URL per environment belongs with the deployment Bolt.

  It returns a **failure rather than a fabricated success** deliberately:
  the screen renders its offline state, so nothing in a device run can
  be mistaken for a working network path. A stub returning a fake token
  would make the run demonstrate nothing while looking like it worked.

  > An earlier version of this document said "No Compose screens yet"
  > and deferred them to the checkpoint. **The review was right that
  > this did not hold**: `team.md` requires the skeleton be demonstrated
  > on a device, and a backend-only skeleton cannot satisfy that. The
  > screen is now built; what remains deferred is narrower and named.

- **No SMS Retriever wiring.** The screen takes a typed code. Autofill
  is an optimization over a path that already works.

---

## Assumptions & Open Questions

**Two, both carried forward rather than opened here.**

[assumption] The global daily SMS ceiling's production value derives
from BulkSMSBD's per-SMS rate against the budget and is set at
deployment. The **mechanism** is built and tested at a configurable
threshold, and the test drives the counter directly rather than issuing
real sends.

[assumption] Whether BulkSMSBD enforces IP whitelisting on this account
is still a vendor question. The design works either way, and a static IP
costs nothing while attached.

**One item for the checkpoint, not an open question**: the gateway leg
is unverified against the real endpoint. Every gateway test runs against
a stub, which is what keeps `make check` secret-free. The single real
send happens at the checkpoint.
