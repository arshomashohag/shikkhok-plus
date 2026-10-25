# Performance Design — D5 `knowing-how-it-is-going`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **Three statements for the dues read and three for the overview, whatever
> the teacher's size.** That is the whole performance design, and the rest of
> this document is about the two ways an implementation reaches a higher
> number without anyone noticing.
>
> **The trap is not a badly written query.** It is a correct function called
> at the wrong granularity [NFR20.32], and the built
> `app/fees/balances.py:72` `oldest_unpaid_period` is exactly that function:
> correct, tested, and one `derive_for_enrollment` per call.

## Sources

- [upstream] `nfr-requirements/performance-requirements.md` — NFR20.31–
  NFR20.36, NFR2.10–NFR2.16, NFR2.21
- [upstream] `functional-design/rules.md` — BR1.1, BR1.2, BR1.6, BR1.7,
  BR2.1, BR2.4, BR2.6, BR3.1, BR3.3
- [upstream] `functional-design/entities.md` § 4 — the departure from D4's
  roster predicate
- [prior] D3's `app/fees/views.py:295-357` — the built shape this generalises
- [code] read 2026-10-25: `app/fees/views.py` (`_owned_batch`,
  `batch_fee_overview`), `app/fees/balances.py`, `app/money/_ledger.py`,
  `tests/fees/test_query_count.py:129-160`

---

## 1. The dues read, statement by statement

```sql
-- 1. The seat set. ONE statement across every owned batch, joined
--    rather than looped, so there is no per-batch query and no batch
--    id from the request to validate.
SELECT e.id, e.batch_id, e.display_name, b.name
  FROM enrollment e JOIN batch b ON b.id = e.batch_id
 WHERE b.owner_id = :owner_id
   AND e.student_decision <> 'declined'      -- BR1.7
-- NO predicate on inactive_from              -- BR1.2
-- NO predicate on joined_on                  -- entities.md § 4

-- 2. Their ledger rows. ONE statement.
SELECT enrollment_id, kind, period, amount
  FROM ledger_entry
 WHERE enrollment_id IN (:seat_ids)

-- 3. Fold in Python. derive(entries) per seat, over rows in hand.
```

**NFR20.31 and NFR20.32 are satisfied structurally rather than by
discipline**: there is no seat loop to accidentally put a query inside,
because the fold runs over a dict already populated from statement 2.

**The join in statement 1 is what removes a whole class of authorization
bug.** D3's `_owned_batch` validates a batch id *from the request*; D5 takes
no batch id at all, so `b.owner_id = :owner_id` is the only scoping there is
and a seat from another teacher cannot enter the set. **Fewer inputs, fewer
checks, nothing to forget** [security § 1].

### The `oldest_unpaid_period` trap, and its fix

`derive()` returns `per_cycle`, a period→balance map, for free — the same
fold that produces `total_outstanding`. The oldest unpaid period is
`min(period for period, bal in per_cycle.items() if bal > Money.ZERO)`
[NFR20.33].

**The built function computes exactly this and takes one enrollment.** It is
correct and reusing it per row is what makes the read O(seats). The design
obligation is therefore not "write this logic" — it is **"do not call that
function here"**, which is why NFR20.32 names it rather than stating a
principle.

**NFR20.33's pinning test is the part that keeps the two honest**: the
in-fold value must equal `oldest_unpaid_period`'s for the same seat. Without
it the reimplementation is merely cheap; with it, a later change to the
built function that this copy does not track fails a test.

---

## 2. The overview read

```sql
-- 1. The seat set. Identical to the dues read's statement 1.
-- 2. Ledger rows for those seats, with period.             -- BR2.6
-- 3. The next exam, ONE statement with LIMIT 1.            -- BR3.1
SELECT x.id, x.title, x.date, b.name, s.name
  FROM exam x JOIN batch b ON b.id = x.batch_id
              JOIN batch_subject s ON s.id = x.batch_subject_id
 WHERE b.owner_id = :owner_id AND x.date >= :today
 ORDER BY x.date, x.created_at, x.id                        -- BR3.3
 LIMIT 1
```

**The earnings total and the trend come from the same statement 2**, folded
twice: once for the current period and once grouped by period. **Two figures,
one read** — because both are sums over the same rows and a second query
would be a second chance to disagree with the first.

**No join to `fee_cycle`** [NFR20.35]: `period` is a plain string on the
ledger row, so the month grouping is a dict key.

**The `LIMIT 1` with a three-column ORDER BY is the tiebreaker** [BR3.3]
rather than a separate decision applied after fetching. Fetching all upcoming
exams and picking in Python would work and would make the determinism a
property of the code rather than of the query — a later `ORDER BY` change
could then silently alter which exam is "next" with nothing failing.

---

## 3. Where the fold happens, and why not in SQL

**The earnings sum is `receipt + credit_grant` by kind** [BR2.1], which
PostgreSQL could do as
`SUM(amount) FILTER (WHERE kind IN ('receipt','credit_grant'))`. **This
design keeps the fold in Python**, for one reason that outweighs the
efficiency:

**`app/money/` owns money arithmetic, and a SQL `SUM` over `NUMERIC` is money
arithmetic outside it** [BR4.3, NFR19.48]. The built import-boundary checks
forbid raw `decimal` outside `app/money/**` precisely so there is one place
that knows how money adds up; a `SUM()` in a query is that logic in a second
place, invisible to those checks and to the 100%-branch gate.

The cost is bounded and computed: **~3,000 rows per read**
[performance-requirements § 1], each a four-field tuple. The fold is a single
pass. **This is the right trade at this scale and the trigger for revisiting
it is stated**: a teacher whose ledger exceeds roughly 50,000 rows per read
would make the transfer cost dominate, and nothing watches for that
[scalability § 3].

---

## 4. The two measurements this design does not take

**No latency assertion anywhere** [NFR2.10]. D3 established that statement
count is the measurable property on this product's single small instance, and
a timing assertion there is flaky in both directions. **The absence is
checkable only by review, and that is the deliberate position.**

**No query-plan assertion.** NFR20.36 records that no index beyond the
existing constraints is needed; `ledger_entry.enrollment_id` is already
indexed by its foreign key and `batch.owner_id` by D1's. **Asserting a plan
would pin an optimiser decision that PostgreSQL is entitled to change** —
the statement-count assertions are the real verifier and this document says
so rather than adding a brittle one.

---

## 5. The release-gate size check

**NFR2.11–NFR2.16 and NFR2.21** specify it; the design here is one step in
`release-android.yml`, placed beside the existing signature assertion whose
shape it follows — assert rather than assume, with the reason in the
comment.

```
- name: The download size is under the ceiling
  run: |
    # Pinned and checksum-verified [NFR2.21]: an unpinned tool
    # computes the number this gate blocks on, and nothing would
    # record which version produced the verdict.
    <install bundletool at the pinned version, verify its checksum>

    # get-size reads an APK SET, not an AAB, so the set is built
    # first. SIGNING IS REQUIRED -- build-apks refuses unsigned --
    # and the keystore is already present in this job at
    # $RUNNER_TEMP/upload.jks, written by the existing
    # "Write the keystore" step.
    bundletool build-apks \
      --bundle=android/build/outputs/bundle/release/android-release.aab \
      --output="$RUNNER_TEMP/app.apks" \
      --ks="$RUNNER_TEMP/upload.jks" --ks-pass=... --ks-key-alias=...

    # --dimensions=ABI varies the ABI and holds density, language
    # and SDK at defaults, giving one row per ABI. Take arm64-v8a's
    # and compare against 15 MB [NFR2.11].
    bundletool get-size total --apks="$RUNNER_TEMP/app.apks" \
      --dimensions=ABI

    # A CLOSE PROXY for Play's reported download, not the same
    # quantity [NFR2.13]. The first release records the observed
    # difference against the Console figure in this comment.
```

**Two properties of that sketch are load-bearing and were checked rather
than assumed**: `get-size` takes an **APK set** rather than an AAB, so a step
that points it at the bundle fails; and `build-apks` **requires signing**,
which is why this gate sits in the release job after the keystore step rather
than in `check.yml` where no keystore exists. **The gate's placement is a
consequence of the tool's requirements, not a preference.**

**The gate fails rather than warns** [NFR2.14], demonstrated once against a
lowered threshold — this project's standing rule that a gate nobody has
watched fail is a gate nobody knows works.

**Headroom, measured 2026-10-25: the AAB is 4.1 MB against 15 MB.** A gate
breached on the day it is written gets lowered rather than respected; this
one has roughly 3.6× of room.

---

## 6. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Dues read is constant in statements [NFR20.31] | A property assertion growing **batches per teacher** | yes |
| No single-enrollment function per row [NFR20.32] | The same assertion; it fails on the per-row call | yes |
| The in-fold period matches the built function [NFR20.33] | An equality test per seat | yes |
| Overview is constant across its three blocks [NFR20.34] | A property assertion | yes |
| No join to `fee_cycle` [NFR20.35] | The statement-count assertion | yes |
| No new index needed [NFR20.36] | Review of the migration — **there is no migration** | **no — a recorded decision** |
| No latency assertion exists [NFR2.10] | Review | **no — the deliberate position** |
| Size gate blocks at 15 MB [NFR2.11, NFR2.14] | The gate's exit code, demonstrated once | yes |
| The proxy's difference is recorded [NFR2.13] | **A human comparison at the first release** | **no — a human step** |
| `bundletool` is pinned [NFR2.21] | The pin in the workflow diff | yes |

---

## Assumptions & Open Questions

- **The statement counts above are three and three**, which is the design's
  intent rather than a measurement — D5's code does not exist. What the
  tests assert is the **property** (the count does not grow with batches),
  following `tests/fees/test_query_count.py:160`'s
  `at_two == at_twenty_five` shape, because a literal count gets updated to
  whatever a refactor produces and is thereby retired while staying green.
- **The ~3,000-row fold and the 50,000-row revisit trigger** are computed in
  `performance-requirements.md` § 1 from D4's nominal five-batch assumption.
  Nothing watches the trigger, which § 3 states plainly.
- **`bundletool get-size` needs a signed APK set built from the AAB**, and
  § 5 now specifies that step rather than deferring it. An earlier draft
  called it "implementation, not design" — which was the wrong call: the two
  facts it hides (get-size takes a set, build-apks requires signing) are what
  **determine where the gate can live**, and a design that left them out
  would have invited a `check.yml` placement that cannot work. The keystore's
  presence at `$RUNNER_TEMP/upload.jks` was verified in the built workflow.
- **Two figures here were measured** — the AAB at 4.1 MB and its four native
  libraries. Everything else about D5's own behaviour is designed and
  unmeasured.
