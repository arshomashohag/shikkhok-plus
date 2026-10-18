# Scalability Design — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **The worker count is the constraint, not the user count.** 100 teachers
> is small. Several Uvicorn workers on one host is what makes two
> otherwise-reasonable designs wrong.

## Sources

- [stage] `nfr-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-requirements/scalability-requirements.md` — NFR10.1, NFR10.2
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.2
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR2.1, BR1.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.8
- [team] `## Walking Skeleton`
- [project] `## Mandated`

---

## A. No in-process state, anywhere on this path

Two things look like natural in-process state and are both wrong:

| Looks natural | Why it is wrong | Design |
|---|---|---|
| A dict of rate-limit counters | Per-worker, so the limit stops enforcing with >1 worker — **and passes every naive test on the way there** | Counter **rows** [NFR10.1] |
| An `lru_cache` on lens resolution | Survives the request, so it is the forbidden cross-request cache | Memo on `request.state` [BR1.4] |

> Both present as *"it works in testing"*, which is the worst failure shape
> for a budget control and for an authorization check respectively.

## B. The counter is one atomic statement

```sql
INSERT INTO rate_limit_counter (scope_kind, scope_value, window_start, count)
VALUES (:kind, :value, :window, 1)
ON CONFLICT (scope_kind, scope_value, window_start)
DO UPDATE SET count = rate_limit_counter.count + 1
RETURNING count;
```

**Compare after the increment**, so two workers racing on the same window
cannot both read a stale value and both pass at the limit [NFR10.2].

> A read-then-write would leak exactly one request per racing worker at
> every boundary — invisible at low volume and precisely wrong under the
> burst a cost attack produces.

## C. The scaling moves deliberately not taken

| Move | Why not |
|---|---|
| **Read replicas** | Replication lag against a computed lens is an **authorization bug**, not a performance win. Serving BR1.1 from a replica means authorizing on stale ownership — exactly what BR1.2 and BR1.3 forbid |
| **Redis for counters** | A second store can disagree with the database about whether a send happened; and it costs budget against a USD 50/month ceiling |
| **Horizontal scaling** | One instance at Phase 1; an ALB would consume a third of the budget before any compute |
| **Sharding** | A few thousand students is one table |

> **The read-replica row is the one worth stating**, because it is the
> obvious move and the failure mode is silent: a stale replica does not
> error, it authorizes.

---

## Assumptions & Open Questions

**None.** [assumption] Phase 2 capacity planning belongs to Infrastructure
Design.
