# Performance Requirements — D5 `knowing-how-it-is-going`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D5 `knowing-how-it-is-going`
**Record**: 261022-remaining-slices

> **D5's performance risk is statement count, and it is the unit where that
> risk peaks.** Every other unit queries within one batch; D5 is the first to
> read across **every batch a teacher owns**. A per-seat query that was
> tolerable at twenty seats becomes up to a hundred statements for one screen
> here — and the trap is not a badly written query but **a correct function
> reused at the wrong granularity** [BR1.6].
>
> **No latency target is set, and that is this project's established
> position** rather than an omission: D3 settled that statement count is the
> measurable property and that a latency assertion on one small instance is
> flaky in both directions [NFR20.16, NFR20.18].

> **`NFRx.y` IDs are GLOBAL across units.** D5's new IDs start above the
> high-water mark each base reached after D4, recomputed for this stage across
> **both records and the whole `aidlc/` tree**. A bare `NFR20.18`, `NFR2.6` or
> `NFR6.44` appearing below is a **citation** of an earlier unit's
> requirement, never an ID defined here.

## Sources

- [upstream] `construction/knowing-how-it-is-going/functional-design/rules.md`
  — BR1.1, BR1.6, BR2.1, BR2.4, BR2.6, BR3.1, BR4.2
- [upstream] `.../functional-design/entities.md` — the four read models, § 4's
  statement-count argument
- [upstream] `.../functional-design/functional-spec.md` §§ 2.1, 2.2, 3
- [upstream] `inception/requirements-analysis/requirements.md` — NFR6's scale
  ceiling, NFR20's ancestors
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR2,
  NFR6, **NFR2's measurement clause**
- [prior] D3's `nfr-requirements/performance-requirements.md` — NFR20.16,
  NFR20.18, the established statement-count shape
- [code] read 2026-10-25: `app/fees/views.py:331-357`, `app/fees/balances.py`,
  `app/db/models.py` (`LedgerEntryRow`'s `period` and `amount` notes),
  `.github/workflows/release-android.yml`

---

## 1. Statement count, which is the whole of it

**NFR20.31** — The cross-batch dues read issues a **constant** number of
statements regardless of how many seats the teacher has. One select for the
seats, one for their ledger rows with `enrollment_id IN (:seat_ids)`, and an
in-memory fold [BR1.6]. **Verifier: a statement-count assertion, following
D3's NFR20.18 — never a latency assertion.**

**The form is already built and is reused rather than reinvented.**
`tests/fees/test_query_count.py:129-160` asserts
`at_two == at_twenty_five` — **a property, not a literal count** — and its
own source comment says why: *"a correct change that moves the number does
not retire the check."* A literal `assert count == 2` would fail on an
unrelated refactor and get updated to whatever the new number is, which
retires the check while leaving it green.

**D5 changes the dimension, not the shape.** D3 grew seats within one batch;
D5 grows **batches per teacher**, holding seats per batch fixed — because
that is the axis this unit newly spans and the one BR1.6's trap lives on. A
test that grew seats within a single batch would pass against a correct
per-batch loop.

**NFR20.32** — No function taking a single `enrollment_id` is called per dues
row. **This names the specific hazard rather than the general principle**,
because the general principle is already stated and was still nearly missed:
`app/fees/balances.py:72` `oldest_unpaid_period` is correct, built, and takes
one enrollment — so calling it per row is one `derive_for_enrollment` per
seat. **Verifier: the same statement-count assertion, which fails on the
per-row call; plus review of any new call site of a single-enrollment
function.**

**NFR20.33** — The oldest unpaid period is computed from the **same in-memory
`per_cycle` map** the outstanding balance comes from — the minimum period
whose balance exceeds zero. Same definition as the built function, no second
query. **Verifier: the statement-count assertion, plus a test that the value
matches `oldest_unpaid_period`'s for the same seat**, so the reimplementation
is pinned to the original rather than merely cheap.

**NFR20.34** — The overview read issues a constant number of statements for
all three of its blocks together. The earnings fold, the trend and the next
exam are **three reads, not three reads per batch**. **Verifier: a
statement-count assertion over a teacher with several batches.**

**NFR20.35** — Grouping ledger entries by month requires **no join to
`fee_cycle`**, because `period` is a plain string on the ledger row
[`app/db/models.py:927`]. **Verifier: the statement-count assertion above; the
absence of the join is what keeps it constant.**

### The input sizes, computed

From the two stated inputs — the scale ceiling of 100 teachers and a few
thousand students [NFR6], and a batch of 8 to 20 students [BR6.2 of D4]:

| Quantity | Computed from | Figure |
|---|---|---|
| Seats in one batch | the batch size ceiling | **20** |
| Batches per teacher | D4's documented nominal assumption | **5** |
| Seats across one teacher's batches | 5 × 20 | **100** |
| Ledger rows per seat per year | a charge and a receipt monthly, plus carries | **~30** |
| Ledger rows in one dues read | 100 × 30 | **~3,000** |

**NFR20.36** — Three thousand rows folded in memory is the scale this design
is sized for, and it is small. **No index beyond the ones the existing
constraints create is required**, and this is stated so the absence is a
decision rather than an oversight. The ledger is already indexed on
`enrollment_id` by its foreign key. **Verifier: review of the query plan is
NOT claimed; the statement-count assertions are the real verifier, and this
requirement records that no index work was skipped by accident.**

---

## 2. What D5 sets no target for

| Path | No target, because |
|---|---|
| Dues read latency | D3 settled that statement count is the measurable property; a latency assertion on one small instance is flaky in both directions [NFR20.16] |
| Overview read latency | The same |
| The in-memory fold | It is arithmetic over ~3,000 rows with no I/O |
| Any client render | No unit of this product has set one, and D5 does not start |

**NFR2.10** — D5 defines **no** latency target, timing budget, benchmark or
timing assertion on any path. **Verifier: the absence of any timing assertion
in this unit's tests, checkable as a file-level review item. There is no
automated verifier, and that is the deliberate position rather than a gap.**

This is the same position D4 recorded for the attendance path [NFR2.6], and it
is stated again rather than cross-referenced because a reader arriving at D5
would otherwise read the silence as an oversight.

---

## 3. The download-size ceiling, which D5 owns and NFR2 has already specified

**This section corrects this unit's own functional design.** That document
said the measurement choice was open and belonged to this stage. It is not
open: **NFR2 already specifies it.**

> *"Release AAB download size at or below 15 MB, **measured from the Play
> Console's reported download size for the `arm64-v8a` split** and asserted at
> the release gate."*

**NFR2.11** — The release gate asserts a download size at or below **15 MB**
for the `arm64-v8a` split. The ceiling and the split are NFR2's and are not
re-decided here.

**That the split exists was verified against the artifact, not inferred from
the build file**, because the inference was wrong. `android/build.gradle.kts`
declares only Kotlin/JVM dependencies — Compose, Ktor, kotlinx.serialization,
security-crypto — with no NDK configuration, no `abiFilters` and no `splits`
block, which reads as an app with no native code and therefore no ABI
dimension at all. The built AAB says otherwise:

```
base/lib/arm64-v8a/libandroidx.graphics.path.so     10096
base/lib/armeabi-v7a/libandroidx.graphics.path.so    7252
base/lib/x86/libandroidx.graphics.path.so            9284
base/lib/x86_64/libandroidx.graphics.path.so        10760
```

A Compose transitive dependency ships native code for four ABIs. **A
dependency list says what was declared; the artifact says what ships, and the
requirement measures the artifact.**

**Measured 2026-10-25: the release AAB is 4.1 MB against the 15 MB ceiling.**
Recorded because a gate whose threshold is already breached on the day it is
written gets lowered rather than respected — this one has roughly 3.6× of
headroom, so NFR2.14's "fails the release" is a credible commitment rather
than an immediate blocker.

**NFR2.12** — **The Play Console's figure is not available to a CI job**, so
"asserted at the release gate" cannot mean an automated step reading the
Console. Two forms satisfy NFR2 and this requirement names which one D5
builds:

| Form | What it costs | What it measures |
|---|---|---|
| **A transcribed Console figure** | a person reads it and a gate compares it | exactly what NFR2 names |
| **`bundletool get-size total --dimensions ABI`** | a new tool dependency; `bundletool` is **absent** today, checked | a close proxy for it, computed from the AAB with density, language and SDK held at defaults [NFR2.13] |

**D5 builds the `bundletool` form**, and the reasoning is this project's own:
a gate that depends on a person transcribing a number is a gate that is
skipped under release pressure, and `team.md`'s organising principle is that
where a rule is important it is mechanical. The transcribed form is also
**unverifiable after the fact** — nothing records which figure was read.

**NFR2.13** — The computed figure is a **close proxy for NFR2's named source,
not the same quantity**, and the gate's own output says which. An earlier
draft of this requirement said "the same quantity Play reports" — that is
wrong, and the error was pointed enough to be worth recording: NFR2.13
requires the claim to be **written into the release gate's failure message**,
so an overstatement here ships as an assertion a reader has no way to check.

What differs: `get-size total --dimensions ABI` varies the ABI and holds
**density, language and SDK level at their defaults**, reporting one figure
per ABI across the rest. Play reports the download for **one concrete device
configuration**, with its own density bucket and language splits. The two
track each other closely and are not equal.

**Verifier: the gate's failure message names the computed figure, the
ceiling, and the dimensions held fixed.** The one-off comparison against a
Console figure at the first release **records the observed difference** rather
than confirming an identity — a number in the gate's comment, so the next
reader can see how close the proxy ran rather than taking the word "close" on
trust. That comparison is a human step and is stated as one.

**Immaterial today and stated anyway**: at 4.1 MB against 15 MB the gap
between the two measurements cannot change a verdict. **The claim outlives
the headroom**, which is exactly why it is corrected now rather than when it
starts to matter.

**NFR2.14** — The gate **fails the release** when the figure exceeds 15 MB.
It does not warn. **Verifier: the gate's own exit code, demonstrated once by
running it against a deliberately lowered threshold** — this project's
standing rule is that a gate nobody has watched fail is a gate nobody knows
works.

---

## Assumptions & Open Questions

- **The nominal five batches per teacher is D4's documented assumption**, not
  an upstream figure. It is used here only to compute an order of magnitude,
  and NFR20.31's requirement is the bound's **shape** rather than the figure.
- **The ~30 ledger rows per seat per year is this document's estimate**,
  derived from a monthly charge and receipt plus occasional carries. It sizes
  the fold and nothing depends on its precision.
- **`[NFR2-note]` is a dangling citation.** NFR2's row cites it and no such
  note exists anywhere in the prior record — checked. The requirement text is
  unambiguous without it, so nothing here rests on the missing note, but it is
  recorded because a citation that resolves to nothing is the shape of a
  decision whose reasoning was lost.
- **`bundletool` is not currently a dependency**, checked across `android/`
  and `.github/`. NFR2.12 adds it, and that is new scope this unit owns.
- **Two figures in this document WERE measured**, and they are the two the
  release gate depends on: the four native libraries in the built AAB, and
  its 4.1 MB size. Both come from `unzip -l` and `ls` against
  `android/build/outputs/bundle/release/android-release.aab` on 2026-10-25.
  **Every other figure is derived arithmetically from a stated input**, and
  D5's own code does not exist yet, so nothing about this unit's query
  behaviour is measured.
