# Performance Design — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-requirements/performance-requirements.md` — NFR6.11–NFR6.14, NFR4.1–NFR4.2
- [upstream] `functional-design/functional-spec.md` — §2.6, §2.7
- [upstream] `construction/identity-and-access/nfr-design/performance-design.md`
- [team] `## Testing Posture`

---

## A. The query count is asserted as a property, not a number

**Constant in N, not minimal** [NFR6.11]. The test compares the count
at two roster sizes rather than against a literal:

```python
with count_queries() as small:  roster(batch_with(2))
with count_queries() as large:  roster(batch_with(25))
assert small == large        # constant: the property that matters
```

| Implementation | N=2 | N=25 | Verdict |
|---|---|---|---|
| N+1 | 3 | 26 | **caught** |
| One JOIN | 1 | 1 | accepted |
| `selectinload` | 2 | 2 | accepted |

> **An `== 1` assertion would reject `selectinload`**, which issues two
> queries and is often preferable to a wide JOIN. The first draft of
> this requirement did exactly that. Comparing two sizes catches the
> defect that scales and constrains nothing else.

Both fixture sizes are part of the design: **a one-row roster passes
against N+1**, so the smaller N must still be above one.

---

## B. Indexes, and which read each serves

| Index | Read | Why it is not optional |
|---|---|---|
| `enrollment(batch_id)` | The teacher's roster | The hottest teacher query |
| `enrollment(student_account_id)` | A student's batch list | U3 indexed `account_id`; the rename moves it |
| `enrollment(guardian_account_id)` | The guardian's child list | A **new** access path U3 had no column for |
| `batch(owner_id)` | The teacher's batch list | Every teacher read scopes on it |

> U3 created one index on this table because it had one query. Three
> reads now scope on three different columns, and the guardian one has
> no index at all today.

---

## C. The Room cache

| Decision | Why |
|---|---|
| Entities mirror the DTO, plus `fetched_at` [NFR4.2] | A derived field is a business rule on the client |
| `fetched_at` is **rendered**, not just stored [NFR4.1] | V1 accepts no write without connectivity, so a stale read is the only offline state and hiding it is a lie of omission |
| No eviction policy | Rosters are kilobytes; the device floor is 2 GB |

---

## D. What is deliberately not designed

| Not designed | Why |
|---|---|
| Pagination | Deferred, and **not** on the "rosters are small" reasoning an earlier draft used — nothing caps students per batch. The honest ground is that a constant query count makes a large roster survivable, and pagination is easier to add than to remove. Revisit if a pilot roster exceeds ~200 |
| A latency budget | No baseline exists; a query count is stable across machines and a duration is not |
| Caching lens-scoped data server-side | That is how cross-teacher leakage happens |

---

## Assumptions & Open Questions

**None, but one correction worth keeping.** [assumption] Both fixture
sizes must sit on the **same side of the batching chunk boundary**,
and an earlier draft of this note had the reasoning exactly inverted.

SQLAlchemy chunks `selectin` loads at 500 by default. Worked:

| Small | Large | Queries | Result |
|---|---|---|---|
| 2 | 25 | 2 vs 2 | constant — correct |
| 2 | 600 | 2 vs 3 | **a correct build fails** |
| 25 | 1200 | 2 vs 4 | **a correct build fails** |

N=25 works because it is far **below** 500, not above it. The draft
said "comfortably above any plausible chunk size", which is both false
and dangerous: acting on it would mean picking a larger N and failing
a correct implementation.

The constraint is therefore stated as a rule rather than a number —
**both fixtures under the chunk size** — so a later author raising N
knows what they must not cross.
