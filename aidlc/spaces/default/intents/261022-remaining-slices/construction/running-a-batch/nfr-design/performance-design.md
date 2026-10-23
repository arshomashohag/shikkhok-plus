# Performance Design — D2 `running-a-batch`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> One design decision: **where the accepted count is computed.** Everything
> else in this unit is a column of a row already read.

## Sources

- [upstream] `construction/running-a-batch/nfr-requirements/performance-requirements.md`
  — NFR20.7–NFR20.11, NFR2.3, NFR2.4, NFR3.3
- [upstream] `construction/running-a-batch/functional-design/rules.md` —
  BR1.2, BR1.3, BR1.4
- [code] `app/batches/service.py:448-495`, read 2026-10-23

---

## 1. The count

### What `list_batches` does today

Three bounded statements, merged in Python:

```
1. SELECT batch           WHERE owner_id = :owner        ORDER BY created_at DESC
2. SELECT batch_id, count(*) FROM enrollment
                          WHERE batch_id IN (:ids)       GROUP BY batch_id
3. SELECT batch_id, name  FROM batch_subject
                          WHERE batch_id IN (:ids)
```

**Not one statement, and not one per batch.** The number of round trips is
constant in the number of batches, which is the property NFR20.7 protects.

### Where `accepted_count` goes

| Option | Statements | Verdict |
|---|---|---|
| A follow-up count per batch | 1 + N | **Rejected** — the N+1 shape, on the first screen after sign-in |
| A fourth grouped statement over the same ids | 4 | Acceptable |
| **A conditional aggregate in statement 2** | **3** | **Chosen** |

Statement 2 already scans exactly the rows the numerator needs. A conditional
aggregate yields both numbers from one grouped pass:

```
SELECT batch_id,
       count(*)                      AS enrollment_count,
       count(*) FILTER (WHERE <accepted>) AS accepted_count
  FROM enrollment
 WHERE batch_id IN (:ids)
 GROUP BY batch_id
```

**The design fixes the property, not the SQL.** What must hold is that the
statement count stays constant and the numerator comes from the same scan as
the denominator. A fourth grouped statement would also satisfy NFR20.7 at one
more bounded query; it is the per-batch version that is forbidden.

**One caveat worth stating**: this codebase uses no `FILTER` aggregate today,
so it would be a first. PostgreSQL 16 supports it and SQLAlchemy exposes it as
`.filter()` on a function element — but a reader should know it is new here
rather than assume it is the house style.

**And "exposes it" is a library fact, not a verified one for this project's
pins.** SQLAlchemy is pinned at 2.1.5 and nothing here has exercised that
construct. **Code Generation's first step on this is a syntax check against
the pinned version**, before the aggregate is written into `list_batches` —
and if it does not hold, the fourth grouped statement above is the fallback
that needs no new construct at all. Naming the fallback is what keeps this
caveat from becoming a blocker.

### What `<accepted>` means

**At least one link accepted** [BR1.2]: a seat somebody joined, whatever the
other link did. The denominator is **every seat the teacher created**,
declined ones included [BR1.4] — so the predicate goes only on the numerator
and the `WHERE` clause stays as it is.

That asymmetry is the whole arithmetic, and getting it backwards — filtering
the `WHERE` instead of the aggregate — would shrink the denominator silently
as people decline.

---

## 2. The roster

**No change in shape** [NFR20.10]. The two new fields are columns of the
`Enrollment` rows the seat select already reads:

- no join added;
- no statement added;
- the ownership check stays its own statement, as today.

**No index.** The enums are read as additional columns of rows located by
`batch_id`, never filtered on. An index over three distinct values would have
the worst possible selectivity and would not be chosen by the planner.

**No pagination in V1** [NFR20.11], and the design is pagination-ready because
of NFR20.9 rather than by accident: since the count is the server's, adding
pagination later changes nothing a client computed. A client-side count would
have made pagination a breaking change.

---

## 3. Caching

**None**, and the reasoning is inherited rather than re-derived: no cached
summary table, no denormalised counts, no cross-request cache [D1 NFR21.1].

D2 is where the temptation presents differently, though. The batch list is
read on every sign-in and its count changes only when someone accepts — which
is exactly the argument for caching it, and exactly the staleness the rule
exists to prevent. A count that disagrees with the roster is worse than a
count computed every time, and at this scale the computation is a grouped
aggregate over tens of rows.

---

## 4. Client

| Requirement | Design |
|---|---|
| Device floor [NFR2.3] | No new dependency; one new feature package |
| Download size [NFR2.4] | Code and strings only; measured at the release gate, **D5/D6's** |
| Bangla digit rendering [NFR3.3] | The count is a formatted string with two numbers and **no locale helper exists for it** |

**NFR3.3 deserves its own line.** `Money.format(locale)` exists because the
server decides digit rendering for money. A plain count has no such helper, so
"9 of 12 accepted" renders through the ordinary string-resource path and its
Bangla form is a per-screen check obligation rather than something a mechanism
guarantees [FR0.2].

**No mid-class latency requirement.** PU-3.6 is D4's and carries a named
manual verifier; it is not borrowed here.

---

## Assumptions & Open Questions

- **Assumed**: the conditional aggregate is expressible in statement 2 without
  changing its `WHERE`. It is; the predicate belongs on the aggregate.
- **Assumed**: no new index is wanted. If a later unit adds an administrative
  "all pending seats" view, that is a new access path and a new question.
- **Open, and D5's**: pagination, where the cross-batch dues list is the same
  shape at a scale that might need it.
