# Functional Specification — D5 `knowing-how-it-is-going`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5 is the only unit of the six that creates no table.** Every figure it
> shows derives from rows D3 and D4 already built [A5]. That makes its risk
> profile different from every unit before it: there is no migration to get
> wrong, no constraint to forget, no concurrency to lose. **The risk is
> entirely arithmetic over existing rows, and arithmetic that is wrong
> balances.**
>
> Two things carry that risk, and § 3 and § 4 are each about one of them:
> **what counts as money received** (counting `credit_apply` overstates a
> teacher's headline earnings by exactly the credit, twice-counted), and
> **who appears in the dues view** (reusing D4's roster predicate drops
> exactly the people worth chasing).
>
> D5 also carries the outstanding half of release packaging. § 7 reports what
> of it actually exists, checked rather than inherited: **Syft is built; the
> 15 MB assertion and the ZAP baseline are not.**

## Sources

- [upstream] this stage's `entities.md` — read models, the ledger-kind table
- [upstream] this stage's `rules.md` — BR1.1–BR4.5
- [upstream] `inception/units-generation/unit-of-work.md` — D5's scope, OQ-2
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US7.1,
  US8.1–US8.4
- [upstream] `inception/requirements-analysis/requirements.md` — FR7.1–FR7.3,
  FR8.1, FR8.2, FR8.4, A5
- [upstream] `inception/domain-design/components.md`
- [prior] `261016-.../inception/user-stories/stories.md` — the AC rows
- [prior] `261016-.../inception/delivery-planning/bolt-plan.md` — Bolt 5's
  confidence hypothesis
- [code] read 2026-10-25: `app/money/_kinds.py`, `app/money/_ledger.py`,
  `app/fees/views.py`, `app/fees/balances.py`, `app/marks/exams.py`,
  `app/contract/routes.py`, `.github/workflows/release-android.yml`,
  `.github/workflows/check.yml`

---

## 1. What this unit delivers

| Story | Delivers | Rules |
|---|---|---|
| US7.1 | The cross-batch dues view | BR1.1–BR1.6 |
| US8.1 | This month's earnings | BR2.1, BR2.2, BR2.5 |
| US8.2 | Earnings over time | BR2.3, BR2.4 |
| US8.3 | **Nothing.** `collection_rate` does not ship | BR4.1 |
| US8.4 | The next upcoming exam | BR3.1–BR3.4 |

Plus **two screens** — the cross-batch dues list and the teacher overview
carrying earnings, the trend and the next exam — and the outstanding release
packaging of § 7.

**US8.3 delivering nothing is a decision, not a gap.** BR4.1 states it and
the Assumptions record exactly what remains open.

---

## 2. Workflows

### 2.1 The teacher opens the dues view

```
GET /v1/me/dues
  -> teacher lens resolves, carrying owner_id
  -> seats = every enrollment in a batch this owner owns,
             student_decision <> 'declined'
             [NO predicate on inactive_from -- BR1.2]
  -> ONE select: ledger rows WHERE enrollment_id IN (:seat_ids)
  -> fold per seat in memory, giving per_cycle and total_outstanding
  -> rows = seats whose total_outstanding > 0        [BR1.1, BR1.3]
            each carrying its oldest unpaid period, taken from the
            SAME per_cycle map, never a second query   [BR1.6]
  -> 200 with the rows, or 200 with an empty list     [BR1.5]
```

**Two statements, whatever the seat count.** One for the seats, one for the
ledger. The fold is in memory because that is where D3 arrived after its N+1
defect, and D5 widens the seat set from one batch to all of them — which makes
the property more load-bearing, not less.

### 2.2 The teacher opens the overview

```
GET /v1/me/overview
  -> teacher lens resolves
  -> earnings    = fold of receipt + credit_grant for the current period
                   across the owner's seats            [BR2.1, BR2.2]
  -> trend       = the same fold per period, ordered ascending IN THE
                   QUERY; absent when fewer than two periods have
                   history                             [BR2.3, BR2.4]
  -> next_exam   = soonest exam dated >= today in the owner's batches,
                   with whole days remaining computed server-side;
                   absent when none                    [BR3.1–BR3.4]
  -> 200
```

### 2.3 What neither workflow does

- No generate step, no refresh action, no materialised rollup [BR1.4].
- No write of any kind. D5 is read-only against every table it touches.
- No figure computed on the client: not the days remaining, not the
  ordering, not the membership of the dues list [TC-9].

---

## 3. The earnings arithmetic, which is this unit's money risk

**`receipt + credit_grant`, never `credit_apply`** [BR2.1]. The built money
module already states why — *"Cash in is receipts plus credit grants: money
received as credit is money received"* [`app/money/_kinds.py:58-60`] — and D5
is the first consumer of that sentence.

**The failure is a double-count that balances.** Computed by running it:

| | `receipt` | `credit_grant` | `credit_apply` | Cash in |
|---|---|---|---|---|
| Month 1 — owes 1000, hands over 1500 | 1000 | 500 | — | **1500** |
| Month 2 — owes 1000, settled part from credit | 500 | — | 500 | **500** |
| | | | | **2000** |

2000 is exactly what the student handed over. Counting `credit_apply` makes
month 2 read 1000 and the total **2500** — overstated by exactly the credit,
counted once on arrival and again on use. Every ledger row still balances,
so nothing signals the error.

**Test-first by the predicate**: the correct output is knowable from the
requirement without the code, and a wrong answer is a money error. The test
asserts **2000 and specifically not 2500** — asserting only "positive" or only
month 1 passes against the defect.

---

## 4. The dues predicate, which is this unit's authorization-shaped risk

| Clause | D4's roster [BR1.5] | D5's dues [BR1.2] |
|---|---|---|
| batch ownership | lens `owner_id` | lens `owner_id` |
| `student_decision` | excludes `declined` | excludes `declined` |
| `inactive_from` | **excludes an inactive seat** | **no predicate at all** |

Two of three clauses agree, which is exactly what makes the third dangerous:
the predicate reads as shared and is not. Reusing D4's drops every student who
left owing money — the people the view exists for [FR7.2].

**This is the inverse of the trap D4 recorded**, where reusing BR1.5's
predicate for `results_for_exam` would have made the `joined_after` state
unreachable. Same lesson from the other side: **a predicate that reads as
shared is two predicates that happen to agree in some clauses.**

**Bolt 5's confidence hypothesis is precisely this**: *a student who left
mid-year owing money appears on the cross-batch dues screen; an active student
owing nothing does not.* BR1.2 and BR1.3 are its two halves and **both must be
asserted**, because a test covering one passes against an implementation
failing the other.

---

## 5. Authorization

Every route resolves a **teacher lens** and scopes by its `owner_id`
[BR2.5, BR4.4]. Nothing in this unit is reachable by a student or guardian
lens: the dues view, the earnings and the trend are the teacher's business
data, and the next exam is already visible to families through D4's own reads.

**D5 adds nothing to `PUBLIC_ROUTES`**, which holds eight entries with the
count asserted in two places, so an addition fails `make check`.

**A dues list is a list of people**, which makes it the natural place to leak
a student's self-authored name to a teacher. The response carries an
`enrollment_id` and the teacher-recorded display name, never a
`student_account_id` and never an owner-private profile field — enforced by
the built gate in `app/contract/privacy.py`, which iterates the generated
OpenAPI document rather than relying on a per-endpoint test being remembered.

---

## 6. What D5 does not build

| Thing | Why |
|---|---|
| `collection_rate` | OQ-2 open [BR4.1]; see Assumptions |
| Any table, column or migration | Every figure derives from built rows [BR4.2] |
| Any money arithmetic | `derive()` and `Money` are built [BR4.3] |
| A cache or scheduled rollup | AC7.1.4 requires current data on open [BR1.4] |
| A Macrobenchmark harness | Closed by the human 2026-10-23; PU-3.6 takes a manual pilot check in D4 |
| Any latency assertion | BR1.6 is a statement-count rule, which is D3's established shape |

---

## 7. Release packaging — what exists, checked rather than inherited

D5 carries "the 15 MB download-size assertion, Syft and the ZAP baseline"
[unit-of-work]. Checked against the repository on 2026-10-25:

| Item | State | Note |
|---|---|---|
| **Syft SBOM** | **Built** | `.github/workflows/release-android.yml` |
| **15 MB download-size assertion** | **Absent** | No size, byte or MB check anywhere in the workflows; the AAB's existence is asserted, its size is not |
| **ZAP baseline** | **Absent** | No reference in any workflow |

**So two of the three are real work for this unit, not inherited.** Recorded
as a table rather than a sentence because the unit-of-work names all three
together and a reader would reasonably assume none or all exist.

**The size assertion measures the wrong artifact if taken literally**, and
**NFR2 has already chosen the right one** — corrected 2026-10-25, during this
unit's NFR Requirements pass. An earlier draft of this section said the
measurement choice was open and belonged to `nfr-design`. It is not open:
NFR2 reads *"Release AAB download size at or below 15 MB, **measured from the
Play Console's reported download size for the `arm64-v8a` split** and asserted
at the release gate."*

The distinction the draft drew is still right — an AAB is not a download,
because Play generates per-device APKs from it — and NFR2 resolves it by
naming the split and the source. What follows from that is the part
`nfr-requirements` must settle: **a Play Console figure is not available to a
CI job**, so "asserted at the release gate" cannot mean an automated step in
`release-android.yml`. Either the gate reads a figure a person transcribes
from the Console, or `bundletool get-size total --dimensions ABI` stands in
for it as a computable proxy whose relationship to the Console figure is
stated. That choice is `nfr-requirements`', and it is made there rather than
here.

---

## 7a. The two screens, specified to the field

Named here rather than left to a filename, because everything else in this
unit is specified to the field and a screen described only by its name is the
part an implementation invents.

**The cross-batch dues list** renders `DuesRow` and nothing else: per row the
teacher-recorded display name, the batch name, the outstanding amount and the
oldest unpaid period. Ordered by outstanding **descending**, so the largest
debt is first — ordered **in the query** [BR2.4's rule applied here]. No
badge, no status chip, no client-side grouping by batch: a row is a row, and
any grouping a teacher wants is a later decision with its own criterion. The
empty state is the defined one of BR1.5 and says nobody owes anything, which
is good news rather than an absence of data.

**The teacher overview** renders three independent blocks, each able to be
absent without the others:

| Block | Present when | Absent form |
|---|---|---|
| This month's earnings | always | never absent — zero is a value [BR2.2] |
| The trend | two or more periods have history | absent entirely, not a one-point chart [BR2.3] |
| The next exam | an exam is dated today or later | the defined empty state [BR3.4] |

**No composable compares a domain value.** The server sends the figures and
the absences; the client renders what it is given. `if (outstanding > 0)` on
the client would be the dues membership rule, reimplemented where nothing
tests it.

---

## 8. Definition of done

- Both screens ship as specified in § 7a, each with a row in
  `docs/delivery/bangla-layout-check.md` [BR4.5].
- **The two absent release-packaging items of § 7 are built by this unit**:
  the download-size assertion and the ZAP baseline. Syft is already present
  and is not re-built. Named as owned work here, because § 7 reports their
  absence and a reported absence with no owner is how a release obligation
  reaches D6 unbuilt.
- `make check` green, with the statement-count assertion of BR1.6 passing.
- BR2.1's worked case asserted at **2000, not 2500**.
- Bolt 5's hypothesis asserted in **both** halves [BR1.2, BR1.3].
- The generated OpenAPI document carries **no** `collection_rate` field
  [BR4.1], and `PUBLIC_ROUTES` still holds eight.
- `app/governance/dispositions.py` still holds **25** entries, and
  `migrations/versions/` has no new revision [BR4.2].

---

## Assumptions & Open Questions

- **OQ-2 stays open; `collection_rate` does not ship** [BR4.1]. What is open
  is narrower than "the arithmetic is unwritten": US8.3 specifies it across
  five criteria. What is open is that **FR8.3's definition is annotated open
  to correction and AC8.3.4's credit rule postdates it**, so those criteria
  may not be consistent with the requirement they cite. By `team.md`'s own
  test that is a real open question — it needs the human's judgement, not
  someone's commitment. **For the human.**
- **OQ-2 costs more than it looks, and this is the half an earlier draft
  missed.** BR2.1 and AC8.3.4 take **opposite sides on when a credit counts**:
  earnings count it **on arrival** (`credit_grant`), while AC8.3.4 counts it
  in **the period whose charge it settles**. Both are right for their own
  figure — earnings answer "how much came in this month" and the money arrived
  when the student handed it over; a collection ratio answers "what proportion
  of this period's charges did I collect" and the credit settles this period.
  **If OQ-2 closes in AC8.3.4's favour, two figures on the same screen will
  disagree about which month a credit belongs to.** That is defensible and
  must be stated on the screen rather than left for a teacher to discover. So
  closing OQ-2 is not only "define the arithmetic" but "decide whether two
  figures may use different month conventions". **For the human, with OQ-2.**
- **Two of the three release-packaging items do not exist** (§ 7): the 15 MB
  assertion and the ZAP baseline are this unit's work; Syft is built.
- **The 15 MB ceiling is a DOWNLOAD size and an AAB is not a download.** The
  measurement choice is `nfr-design`'s; this document records only that
  asserting the AAB's own bytes against a download ceiling would measure the
  wrong thing.
- **"This month" is the server's calendar month in UTC** -- corrected
  2026-10-25 after review, which found the code and this assumption
  disagreed. An earlier draft said "the project's timezone", which
  Bangladesh is not: Dhaka is UTC+6, so for the first **6 hours of each
  month** (00:00-05:59 local on the 1st) the overview reports the
  PREVIOUS month's total labelled as this month, then self-corrects.
  **72 hours a year**, computed.
  .
  **The human chose to record it rather than change it** [2026-10-25],
  because D5 is CONSISTENT with `app/fees/generation.py` and
  `app/teaching/generation.py`, which both use UTC. Fixing one module
  would make two parts of the product disagree about which month it is.
  The boundary is a project-wide decision for a change of its own.
  **The code is right and this sentence was wrong**, which is the order
  that matters: a design assumption nothing checks is a claim.
- **The `(date, created_at, exam_id)` tiebreaker is this design's choice**
  [BR3.3]; AC8.4.3 requires determinism and names no key.
- **The nominal five batches per teacher is D4's documented assumption**, used
  here only to size the statement-count argument in § 2.1.
- **Every figure in this document was computed, not quoted.** The 1500 / 500 /
  2000 / 2500 case in § 3 was produced by executing the fold over the stated
  entries.
