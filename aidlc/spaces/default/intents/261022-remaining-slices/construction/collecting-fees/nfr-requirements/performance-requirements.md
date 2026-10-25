# Performance Requirements — D3 `collecting-fees`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3's performance problem is query count, not arithmetic.** The fold is
> cheap and verified cheap. What is expensive is asking for it sixty times —
> once per student on a teacher's fee view — which is the same N+1 shape the
> batch listing already had to design around.
>
> Every figure below is derived in this file from a stated input. None is
> quoted from another document.

> **`NFRx.y` IDs are GLOBAL across units.** D3's start above the high-water
> mark each base had reached after D2: NFR20 from **.12**, NFR2 from **.5**,
> NFR3 from **.4**, NFR6 from **.26**, NFR7 from **.6**. A bare `NFR20.10` or
> `NFR20.11` in this file is a **citation** of D2's requirement, not an ID
> defined here.

## Sources

- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 2.4, 3, 6.2, 7, 11
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR1.2,
  BR1.3, BR1.4, BR3.5, BR6.1, BR6.2, BR6.6
- [upstream] `construction/collecting-fees/functional-design/entities.md` —
  `FeeCycle`, `LedgerEntry`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20, NFR21,
  NFR22
- [prior] NFR2, NFR3, NFR6, NFR9 of `261016-shikhokplus-tuition-app`
- [code] `app/money/_ledger.py`, `app/batches/service.py`,
  `android/.../core/format/Numerals.kt`, read 2026-10-23

---

## 1. The fold, checked against its own docstring

`derive()` claims *"a single linear pass, with no nested iteration"*. That
claim was checked against the code rather than taken: `app/money/_ledger.py`
holds **one** `for` over `entries` at line 117, a `match` over the kind enum
closed by `assert_never`, and two `defaultdict` accumulators
(`cycle_charged`, `cycle_relieved`) filled inside that same pass. The only
loop after it iterates the **distinct periods**, bounded by months rather than
by entries.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.12 | `derive()` stays **O(entries), single pass**; no change D3 makes introduces a nested iteration or a second pass | The docstring's claim is a contract, and the fold is already at 100% branch coverage | [code: `_ledger.py:117`] |
| NFR20.13 | The **per-cycle breakdown costs nothing extra** — accumulated in the same pass, not by a second fold and not by a `GROUP BY` | `cycle_charged` and `cycle_relieved` fill inside the entry loop; the period loop after it is bounded by months | [code: `_ledger.py:114-117,174`] |

**NFR20.13 is stated because the natural assumption is the opposite.** A
reader who wants outstanding-per-period alongside the totals reaches for a
second pass or a SQL `GROUP BY period`. Neither is needed, and adding either
would be a regression dressed as an optimisation.

---

## 2. Ledger growth, computed

**The ledger is append-only and nothing bounds its growth.** I searched the
prior record's `inception/domain-design/decisions.md` and this unit's
`entities.md` for a snapshot, compaction, closing-balance or archive
mechanism and found none. That is a design property rather than an oversight:
a stored rollup would be the second source of truth `FeeCycle`'s thinness
[BR1.2] exists to avoid.

Entries per enrollment, at two per month (a `charge` and a `receipt`) and at
four (adding a carry pair or a credit pair):

| Horizon | 2 entries/month | 4 entries/month |
|---|---|---|
| 12 months | 24 | 48 |
| 36 months | 72 | 144 |
| 60 months | 120 | 240 |

A teacher's batch-wide fee view folds every enrolled seat. At **60 students**
and four entries per month:

| Horizon | Rows folded for one batch-wide view |
|---|---|
| Year 1 | 60 × 48 = **2,880** |
| Year 3 | 60 × 144 = **8,640** |
| Year 5 | 60 × 240 = **14,400** |

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.14 | The ledger grows **without bound by design**; V1 ships no compaction, snapshot or closing-balance mechanism | At the five-year horizon above, one batch-wide view folds **14,400 rows in a single linear pass** — trivial for PostgreSQL, and V1's audience is closed testing | [BR1.2] [ADR-002] [NFR6] |
| NFR20.15 | If the fold ever does bite, the mitigation is the **materialized rollup ADR-002 already names**, not a schema change | Append-only is what makes a rollup safe to rebuild from source, so this stays additive | [ADR-002] [spec § 2.4] |

**Why "not a V1 problem" is a conclusion rather than a hope.** Three
independent bounds hold it: NFR6 caps the product at 100 teachers and a few
thousand students; Phase 1 is closed testing, so no enrollment reaches the
five-year row count during V1; and the work per view is a linear scan of rows
already filtered to one teacher's own batch. The quantity that would change
this is not elapsed time but **enrollments per fold**, which class size bounds.

---

## 3. Query count — the real hazard

A fold is cheap. **Sixty folds, each fetching its own entries, is the N+1
shape**, and it lands on the two views D3 and D5 care most about.

`list_batches` is the built precedent, and it is worth stating precisely
rather than loosely: it runs a **bounded number of statements** — the batches,
one grouped aggregate over `Enrollment.batch_id.in_(batch_ids)` with a
`count(...) FILTER (WHERE ...)`, and one grouped subject fetch over the same
ids — not one statement, and not one per batch.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.16 | The batch-wide fee view issues a **constant number of statements**, however many students are enrolled | One statement fetches every `LedgerEntry` for the batch's enrollments via `enrollment_id.in_(...)`; the fold is then per-enrollment **in Python**, over rows already in hand | [code: `service.py:601-617`] [BR6.1] |
| NFR20.17 | Per-seat outstanding on the **roster** is derived the same way, adding no statement per row | D3 closes what D2 deliberately left open, and must not close it with a query per seat | [spec § 11] [NFR20.10] |
| NFR20.18 | The **verifier is an assertion on statement count**, not on latency | A latency assertion on one 2 GB host is flaky; a statement-count assertion is deterministic and fails for the right reason | [team: Testing Posture] |
| NFR20.19 | `(enrollment_id, period)` on `LedgerEntry` is indexed; `FeeCycle`'s unique constraint supplies its own index | Every read path filters on `enrollment_id`, so the fold's input must not be a sequential scan | [entities: `LedgerEntry`] [BR1.3] |

**NFR20.18 is the requirement that makes the others checkable.** This project
forbids an obligation without a verifier, and "the fee view must be fast" has
none that is not flaky. Counting statements — with SQLAlchemy's event hooks
over a known fixture — discharges the property that actually matters: cost
does not scale with the roster.

**NFR20.16 deliberately folds in Python, not in SQL.** Moving the arithmetic
into a `GROUP BY` would re-implement `derive()` in a second language, outside
the module that owns it, outside its 100% branch coverage, and outside the
import boundary this project enforces two ways. One statement plus a Python
fold keeps the arithmetic in exactly one place.

**D5 inherits this shape.** The cross-batch dues query [FR7.2] is the same
list-plus-fold at a larger scale and is where it first genuinely matters.

---

## 4. The daily generation job

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR20.20 | Generation commits **per enrollment-period**, so one bad row cannot abort the run | A single large transaction makes a partial failure total, leaving the self-healing re-run more to heal rather than less | [spec § 3.1 step 10] [BR1.4] |
| NFR20.21 | The job's cost is bounded by **candidate enrollments × periods considered**, and the period range is bounded by how long the job has been failing | At the stated ceiling — a few thousand enrollments, one period each on a normal day — this is a few thousand insert attempts, most of which conflict and do nothing | [NFR6] [BR1.4] |
| NFR20.22 | The job runs **outside Bangladesh classroom hours**, consistent with the deploy practice | It contends for the same single host the app serves from | [team: Deployment] |

**NFR20.21 has an honest edge.** A job that has not run for three days
considers three periods per enrollment rather than one, so a long outage makes
the recovery run proportionally larger — which is correct behaviour and the
price of self-healing. It stays bounded because periods are months: a
thirty-day outage adds one period, not thirty.

---

## 5. Client

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR2.5 | D3's fee screens run within the device floor: `minSdk` 24, 2 GB RAM | New feature packages and no new dependency | [NFR2] |
| NFR3.4 | Money renders in **Latin digits under the Bangla locale**, matching the rule the client already settled | `Numerals.kt` states it: numbers the app shows are Latin; text people typed is shown as typed. `Money.format(locale)` must **agree**, not decide independently | [BR6.6] [code: `Numerals.kt:10-13`] |
| NFR20.23 | The client performs **no money arithmetic and no status derivation** | Every balance and the status enum arrive computed; `if (balance > 0) "Due"` is a business rule in presentation's clothes and diverges on the first waiver | [BR6.1] [TC-9] [D-31] |

**NFR3.4 earns its place here because it has a real failure mode.** Had
`Money.format` gone the other way, the same amount would render in two digit
sets depending on which surface drew it — the server's string on one screen,
the client's formatter on another.

---

## 6. What D3 states no target for

| Quantity | Why no number |
|---|---|
| Fee-view latency in milliseconds | No measurement exists, and one taken on a developer machine would not predict a 2 GB Lightsail host. NFR20.18 gives the property a deterministic verifier instead. |
| Generation job wall-clock | Depends on a backlog length that is an outage duration, not a design parameter. NFR20.21 bounds the work instead. |
| Mid-class latency | PU-3.6 is **D4's** attendance path and carries its own named manual verifier. Not borrowed, not restated. |

---

## Assumptions & Open Questions

- **Assumed**: the batch-wide fee view is not paginated in V1, on NFR20.11's
  reasoning — a batch is one teacher's class, in the tens. What makes the
  absence safe is NFR20.23: because every figure is the server's, pagination
  later changes nothing a client computed.
- **Assumed**: four entries per month per enrollment is a generous upper bound
  for the growth table. A seat paying on time produces two. The conclusions
  quote the four-per-month column, so they hold at the generous end.
- **Open, and D5's**: the cross-batch dues query is the same shape across every
  batch a student belongs to, and is where a statement-count regression would
  cost most.
