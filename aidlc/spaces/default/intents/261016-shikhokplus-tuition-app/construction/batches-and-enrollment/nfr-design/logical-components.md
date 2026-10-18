# Logical Components — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-requirements/` — all seven artifacts
- [upstream] `functional-design/rules.md` — BR1.1–BR7.1
- [upstream] `construction/identity-and-access/nfr-design/logical-components.md`
- [team] `## Code Style`, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Components

| Component | Responsibility | Fails how |
|---|---|---|
| `app/batches/service` | Batch create, edit, list | Refuses; nothing partial [NFR10.10] |
| `app/enrollment/service` | Add, edit, mark inactive | Refuses; one row or none |
| `app/enrollment/removal` | The deletion gate + `HISTORY_TABLES` | **Fails closed** — see A.1 |
| `app/enrollment/resolution` | Dormant-seat resolution | **Fails closed** — see A.2 |
| `app/guardian/children` | Child list, distinct by child | Refuses; empty is a valid answer |
| `app/money/sqltypes` | The `TypeDecorator` U4 builds | Fails at author time, not runtime |

### A.1 Removal fails closed

If `HISTORY_TABLES` cannot be consulted — a table unreachable, a query
error — removal is **refused**, not permitted.

> A deletion gate that fails open under database trouble deletes rows
> carrying the teacher's own attendance and marks. The cost of failing
> closed is that a teacher cannot tidy a mistyped number until the
> database recovers; the cost of failing open is destroyed records that
> no backup restores selectively.

**The gate must distinguish two states that both mean "no history
found", and that is the whole implementation:**

| State | How it presents | Correct answer |
|---|---|---|
| Tables reachable, genuinely empty | `SELECT` returns 0 rows | delete is safe |
| Tables unreachable | raises `SQLAlchemyError` | **refuse** |

They *are* distinguishable — an exception is not an empty result — so
the claim is achievable rather than aspirational. But the shape is
forced:

```python
try:
    has_history = any(_count(session, t) for t in HISTORY_TABLES)
except SQLAlchemyError as error:
    raise ConflictError(...) from error   # refuse; never "no history"
```

> **The failure mode is a swallowed exception** — `except: return
> False` — which collapses "unreachable" into "empty" and deletes a
> row carrying real history. That is the same shape as U3's audit-log
> bug, where catching an error and carrying on destroyed the caller's
> transaction. A test provokes a real error (revoking `SELECT`) and
> asserts the removal is refused, rather than asserting on a mock.

### A.2 Dormant resolution fails closed

If the relink markers cannot be read, the number does **not** attach to
any existing enrollment.

> This is the erasure guarantee [NFR14.19]. Failing open reattaches an
> erased student to their own erased history, which is the exact harm
> the markers exist to prevent — and it happens silently, with no error
> anyone sees.

---

## B. What U4 adds to U3's shape

| Change | Why |
|---|---|
| `Enrollment` gains five columns and loses `role` | The catalogue's shape [BR5.0]; `role` was U3's placeholder |
| `_LENS_QUERY`'s guardian subquery is rewritten | U3 resolved it from the guardian's own row, which cannot say *which child* |
| The Room cache arrives | First Unit with a list worth caching [BR7.1] |

> **The lens-query rewrite and the column rename are one migration**
> [NFR6.17]. Separating them leaves authentication reading a column
> that no longer exists.

---

## C. Component boundaries that are enforced, not conventional

| Boundary | Mechanism |
|---|---|
| No U4 module touches `Profile` | A test asserts no import and no SQL reference [NFR14.16] |
| Teacher queries scope on `owner_id` from the lens | The lens object **carries** the value, so a scoped query cannot compile without it |
| `app/money` imports nothing from U4 | B1's layered-import test, unchanged |

---

## Assumptions & Open Questions

**None.** [assumption] `app/money/sqltypes` lives inside the money
module rather than beside the models, so the import-boundary test B1
built continues to govern it — a money type outside `app/money` would
be the first crack in that boundary.
