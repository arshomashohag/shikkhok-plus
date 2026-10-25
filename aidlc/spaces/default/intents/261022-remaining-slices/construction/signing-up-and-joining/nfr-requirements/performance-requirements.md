# Performance Requirements — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> D1's performance question is narrow and specific: it adds a predicate to
> **the hottest query in the system**, and a fourth lens type that must not
> join it there. Everything else in this unit is a once-per-account write.

## Sources

- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md` § 6
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20, NFR21,
  NFR22
- [prior] NFR2, NFR6 of `261016-shikhokplus-tuition-app`
- [prior] `inception/domain-design/decisions.md` — ADR-011
- [code] `app/authz/resolve.py`, read 2026-10-23

---

## Requirements

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.1 | Lens resolution remains **one statement** per request | The three role lenses resolve in a single statement carrying three booleans and two scoping ids; D1's predicates add no join and no round trip | [NFR20] [NFR6.1] [ADR-011] |
| NFR20.2 | Lens-resolution cost tracks the data belonging to the **requesting account**, never the total data in the system | The property NFR20 fixes; D1's predicates are on columns of rows the query already reads, so the access path is unchanged | [NFR20] |
| NFR20.3 | The invitation grant is resolved by its **own statement, on the invitation route only**, and never joins the per-request path | A second statement is acceptable precisely because it is not per-request | [ADR-011] [NFR22] |
| NFR21.1 | No cached summary table, no denormalised acceptance counts, and no cross-request lens cache | Request-scoped memoization on the request object is permitted; a module dict or `lru_cache` is not | [NFR21] [BR1.1] |
| NFR22.1 | `GET /v1/me` returns counts only; no per-lens rows are fetched at login | A lens's rows arrive when that lens is chosen | [NFR22] |

**NFR20.1 and NFR20.3 are one decision seen from two sides.** `_LENS_QUERY`
returns three scalars for one account, including exactly one guardian
enrollment id via `LIMIT 1`. An invitation grant is a **set** — a person may
hold several pending seats — so a fourth scalar would have returned only the
first, presenting to the user as "my other invitation never appeared". That is
why the invitation lens pays for its own query rather than widening the hot
one, and why widening it later would be a correctness regression before it was
a performance one.

**Why NFR20.2 is a property and not a number.** NFR20's measurement was taken
at 50,000 accounts and 200,000 enrollments — 500× the NFR6 target — at 0.20 ms
with index-only scans. Restating a millisecond figure here would invite
re-measurement of a thing D1 does not change. What D1 must not break is the
*shape*: a predicate on an already-read column keeps the index-only access
path; a predicate that forces a join or a second round trip does not.

---

## Signup path

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.4 | Signup is a once-per-account write and carries no latency budget beyond ordinary request handling | Account, profile and optional owner row in one transaction | [BR3.3] |
| NFR20.5 | The already-added lookup is a single indexed read on a unique column | `Account.phone` and the enrollment link columns are indexed; the lookup adds no scan | [BR2.3] [BR4.4] |
| NFR20.6 | Signup does **not** block on the SMS gateway | The account is created first and the OTP path is triggered after; a slow gateway delays the code, not the account | [BR4.3] |

**NFR20.6 is the ordering requirement stated as performance.** BR4.3 fixes the
order for a correctness reason — a code must not be sent for an account that
does not exist. It has a performance consequence worth naming separately:
signup's response time is not coupled to a third party's.

---

## Client

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR2.1 | D1's screens run within the device floor: `minSdk` 24, 2 GB RAM | No new dependency that raises the floor | [NFR2] |
| NFR2.2 | D1 adds no measurable increase to the release download size beyond its own code and strings | The 15 MB assertion is measured at the release gate | [NFR2] **D5/D6 own the measurement** |

**There is deliberately no mid-class latency requirement here.** PU-3.6 is
D4's attendance path, and the affirmed posture requires it be discharged by a
named verifier rather than by a correctness test. It is not D1's and is not
restated here.

---

## Assumptions & Open Questions

- **Assumed**: the decision columns need no index of their own. They are read
  as additional predicates on rows already located by an indexed link column,
  so they narrow a result rather than find one. If a later query filters
  *primarily* by decision — a "all pending seats" admin view — that is a new
  access path and a new index question.
- **Assumed**: request-scoped memoization continues to live on the request
  object. NFR21.1 restates the built rule because D1 adds a second resolver
  and a second resolver is where a convenient module-level cache appears.
