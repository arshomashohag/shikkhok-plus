# Performance Design — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **One design decision carries this whole document**: lens resolution runs
> on every request and must not be cached. Everything below exists to make
> the *honest* optimisation good enough that the forbidden one is never
> needed.

## Sources

- [stage] `nfr-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-requirements/performance-requirements.md` — NFR6.1–NFR6.3, NFR6.7
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md`
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR1.1, BR1.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.9
- [team] `## Code Style` → authorization
- [project] `## Mandated`

---

## A. One query, not three

```sql
SELECT
  EXISTS (SELECT 1 FROM owner      WHERE account_id = :acct) AS is_teacher,
  EXISTS (SELECT 1 FROM enrollment WHERE account_id = :acct
                                     AND role = 'student')   AS is_student,
  EXISTS (SELECT 1 FROM enrollment WHERE account_id = :acct
                                     AND role = 'guardian')  AS is_guardian;
```

One round trip, three booleans [NFR6.1]. Indexes on `owner.account_id` and
`enrollment.account_id` [NFR6.2].

> **Three separate queries is what makes the caching argument
> persuasive.** Someone will measure three round trips on every request,
> conclude the lens must be cached, and be half right — the measurement is
> real and the remedy is forbidden. Making it one query removes the
> premise.

## B. Memoization, bounded by where it lives

```python
async def current_lens(request: Request) -> Lens:
    """Resolve once per request, from the request object."""
    if (memo := getattr(request.state, "lens", None)) is not None:
        return memo
    lens = await resolve_from_db(request.state.account_id)
    request.state.lens = lens          # dies with the request
    return lens
```

**The location is the control** [BR1.4]. On `request.state` it is
garbage-collected with the request; in a module dict, an `lru_cache` or a
Redis key it is not — and at the call site the three look identical.

## C. Verification

| ID | Verified by | Fails when |
|---|---|---|
| NFR6.1 | **Query-count assertion** per request | More than one lens query |
| NFR6.2 | `EXPLAIN` asserts index use | A sequential scan on the hottest query |
| NFR6.3 | Query count, not duration | — |
| NFR6.7 | Two lookups in one request hit the DB once; **two requests hit it twice** | A cache that survives the request |

> **A count, not a duration.** A count is stable across machines and CI
> runners; a duration is not, and a flaky performance assertion gets
> deleted the third time it fails spuriously — taking the real check with
> it.

---

## D. Not designed here

Connection-pool sizing, p95 targets and throughput budgets all need a
measurement that does not yet exist. They arrive at B4 with the
Macrobenchmark harness. Inventing them now would guarantee they disagree
with the first real number.

---

## Assumptions & Open Questions

**None.** [assumption] The absence of a latency target is a recorded
decision, not an omission.
