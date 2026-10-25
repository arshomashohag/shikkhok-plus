# Scalability Requirements — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 has no concurrency to protect.** It writes nothing — no row, no
> counter, no heartbeat — so there is no race, no version, no replay key and
> no idempotency constraint in this unit. Every scalability requirement D1
> through D4 carried about concurrent writes is **inapplicable here, and that
> is stated rather than left as silence**, because four consecutive units
> carrying them makes their absence look like an oversight.
>
> What D5 scales against instead is **breadth**: it is the first unit to read
> across every batch a teacher owns, so the quantity that grows is the seat
> set, not the request rate.

> **`NFRx.y` IDs are GLOBAL.** D5's new IDs start above each base's
> high-water mark after D4. A bare `NFR6.44` or `NFR6.51` below is a
> **citation**, never an ID defined here.

## Sources

- [upstream] `.../functional-design/rules.md` — BR1.6, BR4.2, BR4.3
- [upstream] `.../functional-design/entities.md` § 4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6
- [prior] D4's `nfr-requirements/scalability-requirements.md` — NFR6.44,
  NFR6.50, NFR6.51, the concurrency set this unit does not inherit
- [code] read 2026-10-25: `app/fees/views.py:331-357`

---

## 1. What grows, and what does not

**NFR6.59** — The quantity that grows in this unit is the **seat set**:
every enrollment across every batch one teacher owns. At the ceiling that is
a nominal 100 seats and roughly 3,000 ledger rows per dues read
[performance § 1]. **Verifier: the statement-count assertions of NFR20.31,
which hold the cost flat as that set grows.**

**NFR6.60** — The **request rate** does not grow with scale here. Two reads
per teacher per session, against a ceiling of 100 teachers [NFR6]. No
requirement about throughput, connection pooling or rate limiting is set,
because the arithmetic gives no reason to set one. **Verifier: none, and
none is claimed** — this requirement records that the question was asked.

**NFR6.61** — D5 performs **no write of any kind**, so it introduces no
concurrency guarantee, no optimistic version, no replay key and no
idempotency constraint. **Verifier: a test asserting the unit's reads leave
every table byte-identical** — which is stronger than reviewing for the
absence of writes, because it fails on a write added later by someone who did
not read this document.

---

## 2. The concurrency requirements D5 does not inherit

Named individually rather than dismissed in one sentence, because each was a
real obligation one unit ago and a reader arriving from D4 will look for them:

| D4 requirement | Why inapplicable here |
|---|---|
| `attendance_version` conditional update [NFR6.44] | D5 updates nothing |
| Replay under concurrency [NFR6.50] | D5 writes nothing to replay |
| Generation idempotency [NFR6.51] | D5 runs no job |
| The barrier-released race tests [D4 § 3] | There is no contended write to race |

**NFR6.62** — **A read is not automatically safe under concurrency, and the
one property that matters here is stated rather than assumed**: the dues and
overview reads each run in a single transaction, so a figure is computed from
one consistent snapshot. Without that, a receipt committed mid-read could be
counted in the balance and missed in the oldest-unpaid-period — **two figures
on one row disagreeing about the same money**. **Verifier: a test issuing a
concurrent write during the read and asserting the response is internally
consistent** — the balance and the period agree, whichever snapshot won.

That last requirement is the exception to this section, and it is why the
section is a table rather than a sentence: D5 has no *write* concurrency and
it does have *read* consistency, and collapsing the two would have lost it.

---

## 3. Growth beyond V1

**NFR6.63** — The in-memory fold is sized for the stated ceiling and **no
further**. At 100 teachers and a few thousand students [NFR6] the largest
single fold is roughly 3,000 rows, which is small. **This requirement records
the bound rather than defending it**: a tenant with 50 batches would fold
~30,000 rows per read, which is still tractable but is outside what any
upstream artifact sizes. **Verifier: none. The trigger for revisiting is a
teacher exceeding the nominal batch count by an order of magnitude, and
nothing watches for it** — stated plainly, because a bound with an unwatched
trigger is this project's recorded failure shape.

---

## Assumptions & Open Questions

- **The ~3,000-row figure is computed in `performance-requirements.md` § 1**
  from D4's nominal five-batch assumption and D4's 8–20 seat range. It sizes
  the fold and nothing depends on its precision.
- **NFR6.63's trigger is unwatched and said so.** The alternative — a
  per-teacher seat-count alert — would be a mechanism for a bound no upstream
  artifact sets, which is the shape of inventing a requirement.
- **No figure here was measured.** D5's code does not exist yet.
