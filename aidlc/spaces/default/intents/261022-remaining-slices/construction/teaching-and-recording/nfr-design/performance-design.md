# Performance Design — D4 `teaching-and-recording`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **This document designs no latency mechanism, and that is its first
> decision rather than an omission.** PU-3.6's mid-class speed requirement was
> dropped at Q14.3 answer C and carries no obligation in V1 [NFR2.6, BR7.4].
> A timing budget, a benchmark harness or a latency assertion designed here
> would be inventing an obligation an upstream decision removed. § 1 designs
> what stands in its place, which is **structural and verified as
> correctness**.
>
> What this unit actually costs is **statement count** and the design for that
> is § 2. Every figure below is computed in this file from an input stated
> here; none is quoted.

## Sources

- [upstream] `nfr-requirements/performance-requirements.md` — NFR2.6–NFR2.9,
  NFR20.24–NFR20.30
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR1.6, NFR2.9's
  AAB ceiling, NFR5.10's atomic-write property, NFR17.6
- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.41's row
  volumes, which this document's statement counts are read against
- [upstream] `nfr-requirements/reliability-requirements.md` — NFR19.43's
  server timestamp, the server half of the offline-read contract
- [upstream] `nfr-requirements/security-requirements.md` — NFR14.55's
  marksheet shape, whose one-pass computation is designed in § 3
- [upstream] `nfr-requirements/observability-requirements.md` — NFR26.8, the
  SLO deliberately not set on this path
- [upstream] `functional-design/functional-spec.md` §§ 2.1, 3.3, 4.2, 8
- [upstream] `functional-design/rules.md` — BR1.1, BR1.5, BR3.5, BR4.5,
  BR6.2, BR6.6, BR7.3, **BR7.4**
- [upstream] `functional-design/entities.md` — `Session`, `Attendance`,
  `Mark`, and the constraint set that creates every index this unit relies on
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.8
- [code] `infra/modules/app/main.tf`, `app/fees/commands.py`,
  `app/db/models.py` — read 2026-10-24

---

## 1. The attendance path: a structural design, not a fast one

### 1.1 What is designed instead of a latency budget [NFR2.6, NFR2.7]

Two mechanisms, both already decided by the functional design, and both
verified as **correctness**:

| Mechanism | Rule | What it removes | Verifier |
|---|---|---|---|
| Every seat defaults to `present` | BR3.5, AC3.1.4 | Up to 20 taps become 0–3 taps | Correctness test on the default |
| The roster commits as ONE write | BR3.5, AC3.1.5 | A half-saved roster after a dropped connection | The atomicity test, `reliability-design.md` § 4.1 |

**Neither is a performance test and neither is presented as one.** The
project's rule is explicit that a performance obligation is never discharged
by a correctness test; the resolution here is that **there is no performance
obligation to discharge**, so these tests discharge the structural
requirements they are actually about.

### 1.2 The design decision stated as an absence [NFR2.6, NFR26.8]

No timing assertion, latency budget, Macrobenchmark, or performance SLO is
designed for the attendance path, the topic-log path, or any D4 path.

**Verifier: review of this unit's test files for the absence of a timing
assertion. There is no automated verifier, and that is the deliberate
position rather than a gap** — stated in that sentence because the project's
correction of 2026-10-23 requires both halves to be written when a choice
lands on the option with no automated verifier.

The risk this absence creates is a developer inventing a budget to fill the
gap. AC3.1.8 exists for that and this section is its design-stage counterpart.

---

## 2. Statement count is the design target

### 2.1 Why statement count and not latency [NFR20.24–NFR20.27]

The product runs on one instance at `desired_capacity = 1`
[`infra/modules/app/main.tf`]. On a single small host a latency assertion is
**flaky in both directions**: it fails on an unrelated noisy neighbour and it
passes on a sequential scan of a table that happens to be small today. A
statement-count assertion fails on exactly the defect it names — a query per
roster entry — and is stable under load.

This is D3's established position [NFR20.16, NFR20.18] and D4 inherits the
mechanism rather than reinventing it.

### 2.2 The four reads and their designed statement counts

Each is designed to be **constant in the roster size**, with the index that
makes it constant named. Every index below comes from a constraint
`entities.md` already declares — **this design adds no index** [NFR20.28].

| Read | Statements | Index relied on | Source of that index |
|---|---|---|---|
| Session roster [NFR20.24] | **2** | `enrollment` by batch; `UNIQUE (session_id, enrollment_id)` | BR1.5; `Attendance` constraint |
| Session list for a batch [NFR20.25] | **2** | `UNIQUE (batch_id, date, start_time)` | `Session` constraint |
| Batch marksheet [NFR20.26] | **2** | the partial unique on `mark` | BR4.5 |
| Guardian progress [NFR20.27] | **2** | `mark` partial unique; `exam` by batch | BR4.5, BR6.6 |

**The two statements, in every row above, are: one for the scoping entity and
one set-based read for its children.** The design rule that produces the
figure is stated once rather than per row:

> **No read in this unit issues a statement inside a loop over seats, sessions
> or exams.** A roster read fetches its enrollments as one set-based query and
> its attendance rows as a second, then joins them in memory.

**Verifier: a statement-count assertion per read, following D3's NFR20.18
shape — a counting hook over the SQLAlchemy engine asserting the count does
not grow when the fixture's roster grows from 2 seats to 20.** The
growth-based form is the load-bearing one: an assertion of a fixed number
passes against an implementation whose count happens to equal it at one
fixture size.

### 2.3 The marksheet's one pass [NFR20.26]

The marksheet computes rank, average, highest and the banded distribution
over the live marks of one exam. The design is:

```
live_marks = SELECT ... FROM mark
             WHERE exam_id = :exam AND superseded_by_id IS NULL
# one pass in Python over the result set:
#   rank, average, highest, bands  -- no further statement
```

**The partial unique index of BR4.5 is what makes "the live mark per seat" a
single indexed read** rather than a per-seat lookup for a null
`superseded_by_id`. Without it the same query is a filtered scan, and the
supersession chain would have to be walked.

**Verifier: a statement-count assertion, plus an assertion that the partial
index exists in the migration** [NFR20.26, NFR20.28].

### 2.4 Ordering is the server's, not the client's [NFR20.27]

Guardian progress over time returns live marks **ordered by exam date in the
query**. This is a layer-boundary design as much as a performance one: a
client that sorts a domain list is the second of the five erosion paths
`team.md` names.

**Verifier: the ordering asserted in the response body, and a client-side
test asserting the client does not re-sort** [NFR20.27].

### 2.5 The computed input sizes

Recomputed here from the two stated inputs rather than carried across —
the scale ceiling of 100 teachers and a few thousand students [NFR6], and a
batch of 8 to 20 students [BR6.2]:

| Quantity | Computed from | Figure |
|---|---|---|
| Seats on one roster | the batch ceiling | **20** |
| `attendance` rows per session | one per seat [BR3.5] | **20** |
| Sessions per batch per year | 2 × 52 | **104** |
| `attendance` rows per batch per year | 104 × 20 | **2,080** |
| Live `mark` rows per exam | one per seat | **20** |

The twice-weekly slot is an assumption, labelled in the closing section. At
these sizes **the in-memory join of § 2.2 is over at most 20 rows**, which is
why a set-based read plus an in-memory join is the design rather than a
database-side join with a sort.

---

## 3. The session-generation job [NFR20.29, NFR20.30]

### 3.1 The cost bound, computed

Generation's cost is *active batches × schedule slots × occurrences in the
horizon*, and **a missed day adds no work**, because the horizon is a function
of the calendar rather than of the last run [BR1.1, § 2.1].

Computed at the ceiling, from the figures stated in this sentence —
100 teachers, a nominal 5 batches each, 2 slots per batch, 9 occurrences in a
two-month horizon:

```
100 × 5 × 2 × 9 = 9,000 candidate inserts per run
```

Nearly all of them conflict and do nothing after the first run of a month.
The nominal 5 batches and 2 slots are assumptions, labelled below.

**The design consequence is that the job needs no batching, no chunking and no
pagination**: 9,000 single-row inserts with `ON CONFLICT DO NOTHING`, committed
per occurrence [NFR19.32], is well within one run on this host.

**Verifier: the counting assertion D3's NFR20.21 uses for fee cycles —
assert the candidate count, not the wall-clock.**

### 3.2 Scheduling [NFR20.30]

The job runs **outside Bangladesh classroom hours**, because it contends for
the single host the app serves from [`infra/modules/app/main.tf`,
`desired_capacity = 1`]. Its cron entry is installed by `user_data.sh.tftpl`
and never by hand [NFR1.7].

**Verifier: the cron expression in the Terraform template, reviewed. There is
no automated check that the chosen hour is outside classroom hours.**

---

## 4. Client-side [NFR2.8, NFR2.9]

### 4.1 The queue removes the network from the render path [NFR2.8]

A composed roster is written to device storage and shown as `queued` **without
the server being reachable at all** [BR3.1, BR3.2]. This is a correctness
property of the queue and is listed here because it is the only
performance-shaped property on the client that D4 has.

**The design that delivers it**: the write path is *enqueue-then-render*, never
*send-then-render-on-response*. The UI state is derived from the queue item,
so no response is on the critical path.

**Verifier: the offline-enqueue test of BR3.1's `violation_behaviour` (a)** —
which already asserts the stronger thing, that the item renders as not-sent
while the server holds no row.

### 4.2 The AAB ceiling [NFR2.9]

D4 adds **seven screens and no new dependency**, which is what keeps the 15 MB
ceiling and the `minSdk` 24 / 2 GB floor undisturbed. The queue's storage
recommendation — a serialized file via `kotlinx-serialization`, already in the
stack — is chosen partly for this [NFR5.10, tech-stack § 2].

**If the human chooses Room instead**, the AAB grows by the Room runtime and
the build gains KSP. The ceiling is not obviously threatened by that, but the
figure would have to be re-measured rather than assumed — and this document
has not measured it.

**Verifier: the release-gate AAB size assertion that already exists for
NFR2.**

---

## 5. What this unit designs no performance mechanism for

Stated as a list, because each is a place a reader would otherwise invent one:

| Path | No mechanism, because |
|---|---|
| Attendance marking | The obligation was dropped at Q14.3 [NFR2.6]. § 1. |
| Topic log write | The same path, the same answer. |
| Conflict-resolution screen | It renders two rosters already in hand; no server call is on its critical path [NFR2.8]. |
| Marksheet computation | Twenty integers [§ 2.5]. A target would sit below measurement noise on this host. |
| Generation wall-clock | Its SLI is freshness, not duration [NFR26.7]. |
| API response time | No unit of this product has set one. D4 does not start. |
| Caching (server) | None is added. Request-scoped memoization remains the only permitted form [tech-stack § 6]. |

**On the last row specifically.** The NFR design guide offers a cache-placement
matrix and a cache-consistency rule set. **Neither is applied here, and the
reason is a decision rather than an oversight**: every read in this unit is
scoped to one session, one exam or one enrollment by an indexed key over at
most a few thousand rows, and a cache would add an invalidation path to a
query that costs two statements. Cross-request caching is forbidden for the
lens anyway [`team.md` Code Style].

---

## Assumptions & Open Questions

- **The nominal 5 batches per teacher and 2 slots per batch in § 3.1 are this
  document's assumptions**, inherited as assumptions from
  `performance-requirements.md` § 3 and re-labelled here rather than
  silently promoted to fact. I searched this record's `requirements.md`, the
  prior record's NFR6 and the feasibility constraint register, and found a
  ceiling of 100 teachers and a few thousand students with **no per-teacher
  batch count and no slot count anywhere**. The 9,000 figure is an order of
  magnitude; what NFR20.29 requires is the bound's *shape*.
- **The twice-weekly slot in § 2.5 is likewise an assumption**, used only to
  compute an annual row count. `ScheduleSlot` permits any number.
- **No figure in this document was measured.** Every one is computed
  arithmetically from an input stated at the point of use. D4's code does not
  exist yet, so there is nothing to measure, and no table here carries a header
  claiming otherwise.
- **The AAB impact of Room, should the human choose it, is unmeasured** [§ 4.2].
  Stating it as unmeasured is deliberate: the alternative is a number nobody
  computed.
