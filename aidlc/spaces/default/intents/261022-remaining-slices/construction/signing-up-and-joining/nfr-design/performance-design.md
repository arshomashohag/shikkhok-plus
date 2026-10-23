# Performance Design — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> The performance design for this unit is mostly a set of **refusals**: no
> cache, no second round trip on the hot path, no index for a predicate that
> narrows rather than finds. The one positive design decision is where the
> invitation query lives, and that is settled by correctness before it is
> settled by speed.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-requirements/performance-requirements.md`
  — NFR20.x, NFR21.1, NFR22.1, NFR2.x
- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md` § 6
- [prior] `inception/domain-design/decisions.md` — ADR-011
- [code] `app/authz/resolve.py`, read 2026-10-23

---

## 1. The hot path

Lens resolution runs on **every authenticated request** on a 2 GB host, which
makes it the most load-bearing query in the product and the one under the most
pressure to be cached.

### The query shape is the design

```
ONE statement, three scalars, for one account:
  owner_id                 scalar subquery, LIMIT 1
  is_student               EXISTS
  guardian_enrollment_id   scalar subquery, ORDER BY created_at, id LIMIT 1
```

D1 adds `decision = 'accepted'` to the student and guardian branches
[NFR20.1]. The design property is that **both predicates are on columns of
rows the query already locates**, so:

- no join is added;
- no second round trip is added;
- the index-only access path is preserved — the predicate narrows a result
  rather than finding one.

That is why NFR20.2 is stated as a property rather than a millisecond number:
the measurement (0.20 ms at 500× the target scale) was taken against this
access path, and what D1 must not do is change the path.

### Three round trips is the thing being avoided

The built module records why it is one statement [NFR6.1 of the prior record]:
three round trips per request is what makes the caching argument persuasive.
The design inherits that reasoning rather than re-deriving it, and it is the
reason the invitation grant does **not** join this query.

### `GET /v1/me` stays counts-only

The lens picker is rendered from **counts, not rows** [NFR22.1]. `/v1/me`
returns how many student seats and guardian children an account has, and a
lens's actual rows arrive only when that lens is chosen.

D1 changes what those counts *mean* — they now count `accepted` links only
[NFR20.1] — and deliberately does not change their **shape**. The temptation
it creates is specific: now that acceptance exists, a picker could usefully
show the batch names behind each count, which would turn one summary statement
into a per-lens fetch on the login path. That is the eager-load NFR22.1
forbids, and the reason is the same one behind the single-statement rule — the
login path is the one every user traverses and the one with nothing cached
behind it.

---

## 2. Where the invitation query lives, and why

| Option | Verdict | Reason |
|---|---|---|
| A fourth scalar on `_LENS_QUERY` | **Rejected** | A scalar returns one value; an invitation grant is a **set**. A person holding three pending seats would see one, presenting as "my other invitation never appeared" |
| Its own statement on the invitation route | **Chosen** | Not per-request, so a second statement costs nothing on the hot path [NFR20.3] |

**This is a correctness decision with a performance consequence, not the
reverse** [ADR-011]. Widening the hot query later would be a correctness
regression before it was a performance one, which is worth recording because
the widening would *look* like an optimisation — one query instead of two.

---

## 3. Caching architecture

**There is none, and that is the design** [NFR21.1].

| Tempting cache | Forbidden | Why |
|---|---|---|
| Cached lens summary table | Yes | Reintroduces the staleness the per-request rule exists to prevent |
| Denormalised acceptance counts | Yes | Same, and a count that disagrees with the grant is worse than a slow count |
| Cross-request lens cache | Yes | A module dict or `lru_cache` outlives the request; at the call site it looks identical to the permitted memo |
| Request-scoped memo on the request object | **Permitted, and already built** | Its lifetime is the request object's — it is garbage-collected with the request |

The distinction is **where the value lives**, not how it is spelled. A test
asserts the absence of a module-level dict and an `lru_cache` in the resolver
rather than trusting a reading of the code.

D1 adds a second resolver (the invitation grant), and a second resolver is
exactly where a convenient module-level cache appears. The rule is restated
here for that reason.

---

## 4. The signup path

Once-per-account writes, with no latency budget beyond ordinary request
handling [NFR20.4]:

| Step | Cost | Design note |
|---|---|---|
| Ceiling check | Upsert-and-compare per scope, narrowest first | A refusal stops the cascade immediately |
| Duplicate check | Unique index on `Account.phone` | The constraint reports it; no separate lookup [NFR20.5] |
| Create account + profile + owner | One transaction, three inserts | [BR3.3] |
| Trigger OTP | **After** the transaction | [NFR20.6] |

**Signup does not block on the gateway** [NFR20.6]. The account is created
first and the OTP path is triggered after, so a slow third party delays the
code rather than the account. BR4.3 fixes that order for a correctness reason;
the performance consequence is that signup's response time is not coupled to
BulkSMSBD's.

### The already-added lookup

A single indexed read. It is called on **every signup form render**, which
makes it the only part of this unit with any volume at all — and it is bounded
by the same ceilings as signup itself, so its worst case is a bounded number
of indexed reads.

---

## 5. Indexing

**No new index** [NFR20.2 assumption, restated as a design decision].

The decision columns are read as **additional predicates on rows already
located by an indexed link column**. An index on `student_decision` alone
would have three distinct values across the whole table — the worst possible
selectivity — and would not be chosen by the planner for these queries.

**The condition that would change this**: a query filtering *primarily* by
decision, such as an administrative "all pending seats" view. That is a new
access path and a new index question, and no requirement in V1 asks for it.

---

## 6. Client

| Target | Design |
|---|---|
| Device floor `minSdk` 24, 2 GB RAM [NFR2.1] | No new dependency; D1's screens use the existing Compose stack |
| Download size [NFR2.2] | D1 adds code and strings only; the 15 MB assertion is measured at the release gate, which is **D5/D6's** |

**No mid-class latency design here.** PU-3.6 belongs to D4's attendance path
and carries a named manual verifier; it is not restated or borrowed.

---

## Assumptions & Open Questions

- **Assumed**: the existing indexes on `enrollment.student_account_id` and
  `enrollment.guardian_account_id` are what locate the rows both granting
  queries read. The decision predicates ride on those lookups.
- **Assumed**: no connection-pool change. D1 adds no concurrent workload
  class — signup is a low-volume write and the lookup is a bounded read.
- **Open, and not D1's**: whether the invitation route needs pagination. A
  person holding more pending seats than one screen shows is possible and
  unlikely at this scale; no requirement asks for it and inventing a page size
  now would guess at a problem nobody has.
