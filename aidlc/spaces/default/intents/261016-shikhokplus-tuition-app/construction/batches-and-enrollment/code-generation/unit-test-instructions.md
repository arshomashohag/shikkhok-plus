# Unit Test Instructions — `batches-and-enrollment` (U4)

**Stage**: code-generation (3.5)
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **Every obligation below names what the test must be able to FAIL
> against.** This Unit's reviews found the same defect three times —
> the assertion was real and the setup made it vacuous — so an
> obligation that does not say which wrong implementation it rejects
> is not written down here.

## Sources

- [upstream] `code-generation/code-generation-plan.md`
- [upstream] `functional-design/rules.md` — BR1.1–BR7.1
- [upstream] `nfr-design/security-design.md` — §A, §A.1, §B.1
- [upstream] `nfr-design/scalability-design.md` — §A
- [team] `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. The command

```
make check
```

Unchanged from B3 and still the only entrypoint, locally and in CI. No
new secret. The backend suite runs against a **real PostgreSQL 16**
testcontainer as the restricted `shikkhok_app` role; the Android suite
runs on the JVM under Robolectric.

---

## B. The fixtures, and why each is shaped as it is

| Fixture | Shape | The wrong implementation it rejects |
|---|---|---|
| `two_teachers` | Two owners, one shared student account | A roster query scoped on a caller-supplied id rather than the lens |
| `roster_n` | Parameterized, **N=2 and N=25** | N+1, which a one-row roster cannot see |
| `erased_seat` | Dormant **and** `student_relink_blocked_at` set | A removal check reading the null column alone |
| `pre_migration` | `0001` head with a **claimed** enrollment | A rename implemented as drop-and-recreate |
| `guardian_shapes` | Batches with 0, 1 and 2 students | A fold that places rows it cannot place |

> **`roster_n` is the one most easily built wrong.** Both values must
> sit **below** SQLAlchemy's 500-row `selectinload` chunk boundary, or
> a correct implementation issues a second query at the larger N and
> the test fails against working code. 2 and 25 are both under it.

---

## C. Obligations by surface

### C.1 The migration — 8 tests

1. The fold guard **raises** on a batch with zero students.
2. It raises on a batch with two students.
3. It folds a batch with exactly one.
4. It ignores a batch with no guardian row.
5. From-`0001`-with-rows: the claimed enrollment **still points at its
   account** after upgrade. *Not a row count — an empty table makes a
   rename and a drop-and-recreate indistinguishable.*
6. `downgrade()` raises, naming the dump.
7. The partial unique index admits two dormant seats in one batch and
   refuses the same account twice.
8. The four indexes exist by name in `pg_indexes`.

### C.2 Authorization — 7 tests

1. Teacher A's roster **excludes** teacher B's enrollment of the same
   student account.
2. Teacher B's roster excludes teacher A's.
3. Another owner's batch returns **404**, not 403.
4. A guardian reaches enrollments through `guardian_account_id`.
5. A guardian recorded by teacher A does **not** see teacher B's batch
   for the same child. *The child-keyed implementation passes test 4
   and fails this one; that is the whole point of the pair.*
6. The children list returns distinct **children**, not enrollments.
7. No U4 module imports or references `Profile`.

### C.3 The money gates — 6 tests

1. The database gate reports `batch.fee_due_day` **before** the
   allowlist exists. *Recorded as the observation step 7 asks for.*
2. The schema gate reports `fee_due_day numeric-money` before it.
3. Both are silent after their allowlists are added.
4. **An unlisted money-named integer column is still reported** by the
   database gate.
5. **An unlisted money-named integer field is still reported** by the
   schema gate. *Tests 4 and 5 are what distinguish an allowlist from
   a disabled gate.*
6. Both gates read the **same** token constant.

### C.4 `inactive_from` — 4 tests

1. A period beginning strictly after the date is **not** charged.
2. The period **containing** the date is charged in full.
3. Another enrollment of the same student is untouched.
4. The comparison is against the **period start**, never the due date.
   *Worked case: `fee_due_day` 31, `inactive_from` 2026-02-15 — a
   due-date comparison gets this one wrong and passes the other three.*

### C.5 Removal — 3 tests

1. A dormant, never-erased seat is removed.
2. A **claimed** seat is refused.
3. An **erased** seat is refused and its marker survives. *A null-only
   check passes 1 and 2 and destroys the marker here.*

### C.6 Endpoints — the query-count property

The roster endpoint issues the **same number of queries at N=2 and
N=25**. Assert equality between the two counts, not a literal. A
literal pins an implementation detail and gets raised whenever it
fails, which is how this check gets retired.

### C.7 Android — named obligations, no percentage floor

- Every ViewModel: loading, success, error, and the explicit retry path
  for a failed write [TC-8, D-9].
- No Room entity carries a derived field; only `fetched_at`.
- `fetched_at` is **rendered**, not merely stored.
- Both language bundles present on every new screen [TC-15, D-43].
- Kotlin line coverage reported, **no decrease** permitted.

---

## D. Coverage

| Surface | Floor | Note |
|---|---|---|
| Backend | **80% line**, no decrease | `classic` at Comprehensive |
| `app.authz` | **100% branch** | Pure branching; line coverage is near-meaningless here |
| Android | Named obligations, ratchet | No percentage [OC-3] |

**No floor is weakened to make a step pass** [project.md NEVER]. A
column added to the coverage scope that the Makefile's `--cov` list
does not name is caught by `tests/gates/test_coverage_scope.py`.

---

## E. What is NOT tested here, and where it goes

| Not tested | Owner |
|---|---|
| Fee arithmetic, carry-forward, waiver | U7 |
| Attendance, marks | U5, U6 |
| Either deletion path | U11 |
| Mid-class latency | U5's Macrobenchmark harness |

> U4 ships the columns U11's erasure writes and the anchor U7 charges
> against. Testing either here would test a stub.

---

## Assumptions & Open Questions

**None.** [assumption] The B3 device leg was never run, so production
may hold no seed rows; the fold guard makes the migration correct
either way rather than depending on which happened.
