# Performance Requirements — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **No millisecond target, deliberately — and the reason is not laziness.**
> Nothing in this project has measured a request yet. A number invented now
> would be a guess carrying a requirement's authority, and the first person
> to miss it would weaken it rather than investigate. That is how a target
> becomes decoration.
>
> What replaces it is a **structural** requirement that is mechanically
> checkable, which is the same reasoning as the money module's branch
> coverage: pick the obligation a machine can verify over the one that
> sounds stricter.

## Sources

- [stage] `nfr-requirements-questions.md` — Q1
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR1.1, BR1.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.9
- [team] `## Code Style` → authorization
- [project] `## Mandated`

---

## A. The one performance decision that matters

**Lens resolution hits the database on every request, by design** [TC-11,
BR1.1]. That makes it the hottest query in the system on a single 2 GB
instance, and `project.md` forbids caching it in the most absolute terms.

So the pressure to cache will arrive, and it will arrive with plausible
numbers attached. The requirements below exist to make the *honest*
optimisation available so the dishonest one is not needed.

| ID | Requirement | Why it is this and not a latency number |
|---|---|---|
| **NFR6.1** | Lens resolution is **one query**, not three | Three round trips is what makes the caching argument persuasive |
| **NFR6.2** | Indexed on `Owner.account_id` and `Enrollment.account_id` | An unindexed scan on the hottest query is the actual performance bug |
| **NFR6.3** | A test asserts the **query count per request** | A count is stable across machines; a duration is not, and a flaky performance assertion gets deleted |
| **NFR6.7** | Request-scoped memoization satisfies repeat lookups **within** one request [BR1.4] | The legitimate optimisation, bounded so it cannot become a cache |

---

## B. What is deliberately not specified

| Not specified | Why |
|---|---|
| A p95 or p99 latency target | Nothing has been measured. An invented number would be weakened on first contact rather than investigated |
| A throughput target | 100 teachers and a few thousand students [NFR6] is not a throughput problem |
| A connection-pool size | Tuning belongs with a measurement, and there is none yet |

> **These become real at B4**, where the Macrobenchmark harness arrives and
> there is something to measure against. Stating a number here and a
> measurement there would guarantee they disagree.

---

## Assumptions & Open Questions

**None.** [assumption] The absence of a latency target is a decision, not
an omission, and it is recorded as one so a later reader does not supply a
number to fill the gap.
