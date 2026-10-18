# Scalability Requirements — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **The scale ceiling is not the constraint; the worker count is.** 100
> teachers and a few thousand students [NFR6] is small. What matters at this
> size is one correctness property that *looks* like a scaling concern and
> is not.

## Sources

- [stage] `nfr-requirements-questions.md` — Q6
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR2.1
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6, NFR7
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.8
- [team] `## Walking Skeleton`
- [project] `## Mandated`

---

## A. The requirement that is really about correctness

| ID | Requirement |
|---|---|
| **NFR10.1** | Rate-limit counters are **datastore-backed, never per-process** |
| **NFR10.2** | The counter upsert is **atomic**, under a unique constraint on `(scope_kind, scope_value, window_start)` |

> **NFR10.1 is a correctness requirement wearing a scaling costume.** A
> single Lightsail host runs several Uvicorn workers, so a per-process
> dictionary silently stops enforcing the moment there is more than one —
> and it passes every naive test on the way there. It presents as *"the
> limit works in testing"*, which is the worst way for a budget control to
> fail.
>
> **NFR10.2 is what stops the limit leaking at its own boundary.** Without
> an atomic upsert, two workers racing on the same window both read a stale
> count and both pass a check at the limit.

## B. What does not need to scale

| Not required | Why |
|---|---|
| Horizontal scaling | One instance at Phase 1; an ALB would consume a third of the budget before any compute [D-29] |
| Sharding | A few thousand students is one table |
| Read replicas | Replication lag against a computed lens would be an authorization bug, not a performance win |
| A cache tier | `project.md` forbids caching the lens, and nothing else here is hot |

> **The read-replica row is the one worth stating.** It is the obvious
> scaling move and it is specifically wrong here: serving lens resolution
> from a replica means authorizing against stale ownership, which is
> exactly what BR1.2 and BR1.3 forbid.

---

## Assumptions & Open Questions

**None.** [assumption] Phase 2's capacity planning belongs to Infrastructure
Design, not here.
