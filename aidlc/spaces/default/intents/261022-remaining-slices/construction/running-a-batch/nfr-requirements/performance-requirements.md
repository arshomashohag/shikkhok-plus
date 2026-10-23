# Performance Requirements — D2 `running-a-batch`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> D2's performance question is one shape repeated: **a list plus a count**.
> The batch list is the first screen a teacher sees after signing in, and the
> count it now carries is the easiest thing in this unit to implement as an
> extra query per row.

## Sources

- [upstream] `construction/running-a-batch/functional-design/functional-spec.md` § 1
- [upstream] `construction/running-a-batch/functional-design/rules.md` — BR1.2,
  BR1.3, BR1.4
- [prior] NFR2, NFR6, NFR20 of `261016-shikhokplus-tuition-app`
- [code] `app/batches/service.py`, `app/api/batches.py`, read 2026-10-23

---

## The count

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.7 | `accepted_count` costs **no additional statement per batch** | A constant number of statements however many batches a teacher owns | [BR1.2] |
| NFR20.8 | The count is derived the way `enrollment_count` already is: one grouped aggregate over every batch id at once | `sa.func.count` grouped by `batch_id`, filtered by `batch_id.in_(batch_ids)` | [code: `service.py:470-476`] |
| NFR20.9 | The count is computed server-side and never by the client | A client count is wrong the moment the roster is paginated, and it is the client deciding what counts as accepted | [BR1.3] [TC-9] |

**NFR20.7 is the N+1 requirement, stated plainly because the wrong
implementation is the natural one.** Listing batches and then asking "how many
accepted?" per batch reads correctly and turns a bounded set of statements
into one-per-batch — on the screen a teacher sees first, on a 2 GB host.

`enrollment_count` already demonstrates the right shape, and the shape is
worth stating precisely rather than loosely: `list_batches` runs **three
bounded statements** — the batches, one grouped count over
`batch_id.in_(batch_ids)`, and one grouped subject fetch over the same ids.
Not one statement, and not one per batch. `accepted_count` is the same
grouped aggregate with a decision predicate, which keeps the number of
statements constant.

*(A draft of this requirement said "the same statement". Reading
`service.py:459-480` corrected it: the count is a second query over all ids at
once. The bound is what the requirement protects, and claiming a tighter
property than the code has would have made the requirement fail against
correct work.)*

**NFR20.9 is a performance requirement as much as a layer-boundary one.**
The client-side count is not merely wrong in principle; it is wrong in fact as
soon as the roster does not fit one response, and designing it out now is what
makes pagination a later additive change rather than a breaking one.

---

## The roster

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.10 | The two new roster fields add **no statement and no join** | They are columns of rows the seat select already reads; the ownership check stays its own statement, as today | [BR2.1] |
| NFR20.11 | No pagination in V1, and the design stays pagination-ready | A batch is one teacher's class; NFR6 caps the product at a few thousand students across 100 teachers | [NFR6] |

**NFR20.11 records a bound, not an omission.** A realistic roster is in the
tens. What makes the absence safe is NFR20.9: because the count is the
server's, adding pagination later changes nothing a client computed.

---

## Client

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR2.3 | D2's six screens run within the device floor: `minSdk` 24, 2 GB RAM | No new dependency; one new feature package | [NFR2] |
| NFR2.4 | D2 adds no measurable increase to the release download size beyond its own code and strings | Measured at the release gate, which is **D5/D6's** | [NFR2] |
| NFR3.3 | The count renders correctly under the Bangla locale | "9 of 12 accepted" is a formatted string with two numbers; digit rendering under `values-bn` is a per-screen check obligation | [NFR3] [FR0.2] |

**NFR3.3 is worth its own line.** `Money.format(locale)` exists because the
server decides digit rendering for money; a plain count has no such helper, so
the count is the one D2 string whose Bangla form could differ in a way nobody
built for. It is named in the per-screen check rather than assumed.

**No mid-class latency requirement here.** PU-3.6 is D4's attendance path and
carries a named manual verifier; it is not restated or borrowed.

---

## Assumptions & Open Questions

- **Assumed**: the two new roster enums need no index. They are read as
  additional columns of rows already located by `batch_id`, not filtered on.
- **Assumed**: the four new screens introduce no list long enough to need
  lazy loading beyond what `LazyColumn` already gives.
- **Open, and D5's**: the cross-batch dues list is the same list-plus-count
  shape at a larger scale, and is where pagination would first genuinely
  matter.
