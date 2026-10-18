# Performance Requirements — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `functional-design/functional-spec.md` — §2.6, §2.7
- [upstream] `functional-design/rules.md` — BR5.3, BR7.1
- [upstream] `inception/requirements-analysis/requirements.md` — NFR2, NFR4, NFR6
- [upstream] `construction/identity-and-access/nfr-requirements/performance-requirements.md`
  — NFR6.1–NFR6.3, which this Unit's reads now exercise
- [team] `## Testing Posture`
- [project] `## Mandated`

---

## A. The roster read is the first list endpoint, and it sets a pattern

U3 had no list. Every read it served returned one row or none, so the
N+1 question never arose. **U4 returns rosters, batch lists and child
lists**, and every later Unit copies whatever shape lands here.

| ID | Requirement | Why it is this and not a latency number |
|---|---|---|
| **NFR6.11** | A roster read is **one query**, not one per enrollment | The N+1 shape is invisible at ten students and quadratic at a hundred |
| **NFR6.12** | A test asserts the **query count** for a roster of N, with N > 1 | A roster of one passes against an N+1 implementation, so the fixture size is part of the requirement |
| **NFR6.13** | The guardian child list is one query, including the teacher name each child shows [AC2.7.3] | The attribution requirement is exactly what tempts a per-child lookup |
| **NFR6.14** | Indexes on `Enrollment.batch_id`, `Enrollment.student_account_id` and `Enrollment.guardian_account_id` | Three different reads scope on three different columns; U3 indexed only the one it used |

> **NFR6.12's fixture size is the load-bearing part.** A query-count
> test written against a one-row roster passes against an N+1
> implementation and reports a green build. The same mistake as a
> privacy suite run as superuser: the assertion is real, the setup
> makes it vacuous.

---

## B. The Room cache is a read cache, and staleness is visible

| ID | Requirement | Why |
|---|---|---|
| **NFR4.1** | A cached roster renders with its `fetched_at`, not silently | V1 accepts no write without connectivity [TC-8], so a stale read is the only offline state and the user should be able to see it |
| **NFR4.2** | Room entities mirror the DTO one-to-one and derive nothing [BR7.1] | A derived field is a business rule on the client, and U4 sets the pattern every later Unit copies |

---

## C. What is deliberately not specified

| Not specified | Why |
|---|---|
| A latency target for any read | No baseline exists, so any number is invented. NFR6.12 asserts a query **count**, which is stable across machines |
| Pagination | 100 teachers with a few thousand students [NFR6] means the largest plausible roster is tens of rows. Pagination now is a contract an unpaginated client would have to be taught |
| A cache eviction policy | Room holds rosters, not media. The device floor is 2 GB [NFR2] and the data is kilobytes |
| Connection pool sizing | One container on one instance; U3 set `pool_pre_ping` and nothing here changes the shape |

---

## Assumptions & Open Questions

**None.** [assumption] The roster size that makes NFR6.12 meaningful is
a test-fixture decision rather than a product one — any N above one
distinguishes the two implementations, and the test picks a number
large enough to read clearly in a failure message.
