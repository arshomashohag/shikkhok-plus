# Reliability Requirements — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 cannot corrupt anything, and that changes what reliability means
> here.** It writes nothing, so there is no partial write to roll back, no
> migration to fail forward, no job to self-heal. The failure modes that
> remain are **a figure that is wrong** and **a figure that is unavailable**,
> and the first is far worse: an unavailable earnings total shows an error a
> teacher can act on, while a wrong one shows a number they will believe.
>
> Every requirement below follows from that asymmetry.

> **`NFRx.y` IDs are GLOBAL.** D5's new IDs start above each base's
> high-water mark after D4. A bare `NFR19.35` or `NFR19.38` below is a
> **citation**, never an ID defined here.

## Sources

- [upstream] `.../functional-design/rules.md` — BR1.4, BR1.5, BR2.2, BR2.3,
  BR2.6, BR3.4, BR4.3
- [upstream] `.../functional-design/functional-spec.md` §§ 2.3, 7a
- [prior] D4's `nfr-requirements/reliability-requirements.md` — NFR19.29–
  NFR19.38, the error-taxonomy requirements this unit inherits unchanged
- [code] read 2026-10-25: `app/errors/_classes.py`, `app/errors/codes.py`,
  `app/money/_ledger.py`, `app/db/models.py:925-940`

---

## 1. A wrong figure is the failure that matters

**NFR19.48** — Every money figure in this unit comes from the **built fold**
[`derive()`] or a sum of `Money` values, and D5 adds **no** arithmetic to
`app/money/` [BR4.3]. **Verifier: the built import-boundary checks, which
fail `make check` on raw `decimal` outside `app/money/**` — plus a pytest AST
walk asserting D5's modules import no arithmetic helper of their own.**

**NFR19.49** — A ledger entry's month comes from its **`period` key**, never
its `created_at` [BR2.6]. **Verifier: a named test with an entry whose period
is `2026-10` and whose `created_at` falls in November, asserting it counts in
October.** This is the single most likely wrong-figure defect in the unit,
because a late-recorded payment is the normal case rather than an edge, and
grouping by `created_at` produces a trend with a dip and a spike that never
happened.

**NFR19.50** — The earnings fold selects by **kind**, never by summing
amounts. `LedgerEntryRow.amount` is always non-negative and the sign lives in
the kind [`app/db/models.py:936-937`], so a `SUM(amount)` over a period adds
charges to receipts and yields a number with no meaning. **Verifier: the
worked case of BR2.1, asserting 2000 and specifically not 2500 — and a
separate assertion that a period's charges do not appear in its earnings.**

**NFR19.51** — A figure that cannot be computed is an **error**, never a
zero. Zero is reserved for the fact that nothing was received [BR2.2], so
returning zero on a failure would report a true-looking fact about a month
whose data could not be read. **Verifier: a test injecting a read failure and
asserting the response is an error rather than a zero figure.**

---

## 2. Absence, distinguished from zero and from failure

**NFR19.52** — This unit returns three distinct kinds of nothing, and no two
may be collapsed:

| Case | Response | Rule |
|---|---|---|
| Nobody owes | an **empty collection**, 200 | BR1.5 |
| Nothing received this month | **zero** as a value, 200 | BR2.2 |
| Fewer than two months of history | the trend **absent**, 200 | BR2.3 |
| No upcoming exam | the next exam **absent**, 200 | BR3.4 |

**Verifier: a test per row.** Collapsing any pair is the defect: an empty dues
list rendered as an error shows a retry prompt for the best possible news;
zero earnings rendered as an absent block tells a teacher their records are
missing when they are complete.

**NFR19.53** — None of the four cases above is a 404 or a 5xx. **Verifier:
the status code asserted per case**, because "not a 200" is the assertion a
developer reaches for and it passes against all three wrong answers.

---

## 3. The error taxonomy, inherited unchanged

**NFR19.54** — D5 introduces **no new exception class and no new error
code**. The closed five-class hierarchy covers everything this unit raises:
an unreachable resource is the shared `NOT_AVAILABLE` `AuthorizationError`,
and there is no state-based refusal because there is no state to refuse
against. **Verifier: the built `tests/contract/test_error_contract.py`, with
no new mechanism.**

**NFR19.55** — Retryability remains a property of the error class, read in
one place; no raise site in this unit sets it. **Verifier: the built
`app/errors/_classes.py` design, unchanged.**

---

## 4. Consistency within one response

**NFR19.56** — Each read computes from **one consistent snapshot**, so the
figures within a single response agree with each other. Without it a receipt
committed mid-read could be counted in a seat's balance and missed in its
oldest unpaid period — two numbers on one row disagreeing about the same
money. **Verifier: a test issuing a concurrent write during the read and
asserting internal consistency, whichever snapshot won.**

This is the one reliability property D5 has that is **not** inherited, and it
exists because the unit computes several figures from the same rows in one
response. Stated in `scalability-requirements.md` § 2 as well, from the
concurrency side.

---

## 5. What does not apply

Named individually, because each was a live obligation in D3 or D4 and their
absence here would otherwise read as an oversight:

| Obligation | Why inapplicable |
|---|---|
| Transaction rollback on partial write [NFR19.39 of D4] | D5 performs no write |
| Forward-only migration [NFR19.46] | D5 ships no migration |
| Job self-healing and heartbeat [NFR19.41–NFR19.44] | D5 runs no job |
| Replay returning the original result [NFR19.33] | D5 has no replayable write |
| A cancelled or inactive state refusal [NFR19.38] | D5 refuses no write |

**NFR19.57** — D5's reads leave every table byte-identical. **Verifier: a
test asserting no row changes across the unit's reads** — which fails on a
write added later by someone who has not read this table, and is therefore
worth more than the table itself.

---

## Assumptions & Open Questions

- **NFR19.51's failure mode is stated without a known trigger.** No upstream
  artifact describes how a ledger read fails in this product; the requirement
  exists so the obvious implementation — a `.get(period, 0)` that silently
  yields zero — is a named defect rather than a reasonable-looking line.
- **"One consistent snapshot" is satisfied by the default transaction
  behaviour of a single request-scoped session**, which is what the built
  code already uses. NFR19.56 states it as a requirement because it is a
  property that can be lost by splitting a read across two sessions for an
  apparently good reason.
- **No figure in this document was measured.** D5's code does not exist yet.
