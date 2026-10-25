# Scalability Design — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 writes nothing, so it has no write concurrency to design.** The
> barrier-released race tests that were the centrepiece of D3 and D4 have no
> analogue here, and § 2 names each of those obligations individually rather
> than letting silence imply they were forgotten.
>
> **One concurrency property does apply, and it would have been lost in that
> sweep**: a read computing several figures from the same rows must compute
> them from **one snapshot**, or the balance on a dues row and its oldest
> unpaid period can disagree about the same money [NFR6.62].

## Sources

- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.59–NFR6.63
- [upstream] `functional-design/rules.md` — BR1.6, BR4.2, BR4.3
- [upstream] this stage's `performance-design.md` §§ 1, 3
- [prior] D4's `nfr-requirements/scalability-requirements.md` — the
  concurrency set this unit does not inherit
- [code] read 2026-10-25: `app/api/deps.py` (the request-scoped session),
  `app/fees/views.py`

---

## 1. What a read must not do between its statements

The dues read is two statements and a fold [performance § 1]. **Between
statement 1 and statement 2 a receipt can commit**, and what happens then is
a design decision rather than an accident:

| Design | What a mid-read commit does |
|---|---|
| Two autocommitted selects | Seats from before the write, ledger rows from after — a seat's balance reflects a payment its oldest-unpaid-period does not |
| **One transaction, one snapshot** | Both statements see the same instant; the figures agree with each other, whichever instant won |

**Design statement: each read runs within the single request-scoped
session's transaction** [NFR6.62], which is what the built
`app/api/deps.py` dependency already provides. **The design contribution is
not the mechanism — it is naming the property**, because it is the kind of
thing lost later for a good-sounding reason: splitting the ledger read into
its own session "to release the connection sooner" would break it silently.

**Verifier: a test that commits a receipt from a second session while the
read is in flight, asserting the response is internally consistent.** It does
not assert *which* snapshot won — both are correct — only that one did.

**This is a real property and a modest one.** It does not make the figure
current at the moment the teacher reads it; nothing can. It makes the figures
within one response describe **one instant** rather than two.

---

## 2. The concurrency obligations D5 does not inherit

Named individually, because each was live one unit ago:

| D3/D4 obligation | Why inapplicable |
|---|---|
| `attendance_version` conditional update [NFR6.44] | D5 updates nothing |
| Replay by `client_mutation_id` [NFR6.50] | D5 writes nothing to replay |
| Generation idempotency [NFR6.51] | D5 runs no job |
| N-thread barrier race tests | No contended write exists |
| `ON CONFLICT DO NOTHING` | No insert |

**Design statement: D5's reads leave every table byte-identical, and this is
asserted rather than reviewed** [NFR6.61]. A test comparing a table checksum
or row set across the unit's reads **fails on a write added later by someone
who has not read this table** — which is worth more than the table.

---

## 3. Growth, and the bound this design accepts

At the stated ceiling the largest fold is **~3,000 ledger rows**
[performance-requirements § 1]. The fold is one pass over four-field tuples.

**Design statement: no pagination, no streaming, no cursor.** A dues list at
the ceiling is at most 100 rows and a teacher scrolling 100 rows is not a
problem worth a paging contract — which would also make "the dues view" a
thing with pages, and AC7.1.4's "renders current data on open" a per-page
claim.

**The trigger for revisiting is stated and unwatched** [NFR6.63]: a teacher
whose seat set or ledger exceeds roughly an order of magnitude beyond the
nominal — around 50,000 rows per read — would make the row transfer dominate
and would justify moving the sum into SQL [performance § 3]. **Nothing
watches for it**, and building a per-teacher size alert for a bound no
upstream artifact sets would be inventing a requirement.

**That trade is recorded rather than hidden**: this project's own history
includes an N+1 that shipped green and was found by mapping a traceability id
[D3], so a stated bound with an unwatched trigger is a known risk rather than
an oversight.

---

## 4. What does not scale with anything

**Request rate** [NFR6.60]. Two reads per teacher per session against a
ceiling of 100 teachers. **No rate limit, no connection-pool sizing, no
caching layer** is designed, because the arithmetic gives no reason to and a
cache would contradict BR1.4 outright.

---

## 5. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| One snapshot per read [NFR6.62] | A concurrent-write test asserting internal consistency | yes |
| Reads leave tables byte-identical [NFR6.61] | A row-set comparison across the reads | yes |
| Statement count flat in batches [NFR6.59] | The property assertion of performance § 1 | yes |
| No rate or throughput requirement [NFR6.60] | **None, and none claimed** | **no — a recorded decision** |
| The fold's bound and its trigger [NFR6.63] | **None. The trigger is unwatched** | **no — stated plainly** |

---

## Assumptions & Open Questions

- **The single request-scoped session already provides § 1's property**, so
  the test asserts a property the built code has rather than one D5 adds. It
  is specified anyway because the property is easy to lose and nothing else
  would notice.
- **The ~50,000-row revisit threshold is this document's estimate**, an order
  of magnitude above the computed ~3,000. Nothing upstream sets it, and
  nothing watches it.
- **No figure here was measured.** D5's code does not exist yet.
