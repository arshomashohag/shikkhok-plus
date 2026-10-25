# Performance Requirements — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **This is the thinnest of the six documents, and that is a finding rather
> than an omission.** D4's hazards are concurrency, replay and privacy. Its
> arithmetic is a rank over at most twenty integers. The one place a latency
> requirement would naturally sit — the mid-class attendance path — carries
> **no performance obligation in V1**, because the requirement was dropped
> [BR7.4, Q14.3 answer C]. § 5 states that absence rather than leaving a gap
> a reader would fill.
>
> **Every figure below is computed in this file from a stated input.** None is
> quoted from another document.

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3, recomputed for this stage across
> both records and the whole workspace. A bare `NFR20.17`, `NFR6.39` or
> `NFR2.5` appearing below is a **citation** of an earlier unit's requirement,
> never an ID defined here.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ 2.1, 3.3, 4.2, 8
- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.1, BR1.3, BR1.5, BR3.3, BR3.5, BR6.2, BR6.4, BR6.5, BR7.3, **BR7.4**
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  `Session`, `Attendance`, `Mark`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20, NFR21,
  NFR22
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR2,
  NFR4, NFR6, NFR20's ancestors; **the "Deliberately absent" note at line 210**
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.8
- [code] `app/fees/commands.py`, `app/batches/service.py`,
  `android/coverage-floor.txt` — read 2026-10-24

---

## 1. The attendance path has no latency target, and this is the requirement

**NFR2.6** — No latency target, timing budget, benchmark or timing assertion
is defined for the attendance-marking path in V1. A proposal to add one is
refused as out of scope [BR7.4]. **Verifier: the absence of any timing
assertion on this path, checkable as a file-level review item — there is no
automated verifier, and that is the deliberate position rather than a gap.**

The history matters, because this requirement has been re-opened twice and
will be again:

- The prior record's `requirements.md` carries, at line 210, the sentence
  **"Deliberately absent: there is no mid-class speed requirement."**
- **Q14.3, answer C** settled it: *"The mid-class speed statement is dropped as
  a requirement... It carries no acceptance criterion, no numeric target and no
  verifier, and PU-3.6 has no performance obligation in V1."*
- **AC3.1.8** exists so a developer "neither invents a latency budget nor reads
  the gap as licence".
- Three artifacts still presuppose the obligation exists, in different ways,
  and § 6 states which is which. The precise claim matters: this record's
  `unit-of-work.md` and `bolt-plan.md` record the 2026-10-23 verifier choice
  **accurately**, and are stale only in the words around it — "the obligation
  is **not weakened**, only differently verified", and "PU-3.6's mid-class
  latency obligation **is discharged by** a named manual check" — each of
  which presupposes an obligation Q14.3 removed. `team.md` is stale about the
  decision itself.

**NFR2.7** — What stands in place of a latency target is structural and is
tested as correctness, not as speed: a freshly opened roster has every seat
defaulted to present [AC3.1.4], so a teacher marks only exceptions, and the
roster commits as **one** write [AC3.1.5, BR3.5], so a dropped connection
loses nothing rather than half a roster. **Verifier: the two structural tests
named in BR7.4's `violation_behaviour`.** Neither is a performance test and
neither is presented as one.

---

## 2. Query count, which is the real cost in this unit

D3 established that this product's performance problem is statement count
rather than arithmetic [NFR20.16]. D4 inherits the shape and adds three
screens that iterate a roster.

**NFR20.24** — The session roster read issues a **constant** number of
statements regardless of roster size. BR1.5's predicate is four clauses over
`enrollment`, which is one indexed query; the attendance rows for the session
are a second. **Verifier: a statement-count assertion, following D3's
NFR20.18 — never a latency assertion, which on one small instance is flaky.**

**NFR20.25** — The session list for a batch issues a constant number of
statements regardless of how many sessions the horizon has produced.
**Verifier: the same statement-count assertion, over a batch seeded with a
full horizon.**

**NFR20.26** — The marksheet computation is **one pass over the live marks of
one exam** and issues no statement per student. The partial unique index of
BR4.5 is what makes "the live mark per seat" a single indexed read rather than
a per-seat lookup for a null `superseded_by_id`. **Verifier: a statement-count
assertion plus the index's presence in the migration.**

**NFR20.27** — Guardian progress over time [BR6.6] returns the live mark per
exam **ordered by exam date in the query**, never sorted in the client. This
is the layer-boundary rule as much as a performance one: a client that sorts a
domain list is the second of the five erosion paths `team.md` names.
**Verifier: a statement-count assertion, and the ordering asserted in the
response rather than in the client.**

### The input sizes, computed

The scale ceiling is 100 teachers and a few thousand students [NFR6], and a
batch holds **8 to 20 students** [BR6.2]. From those two stated inputs:

| Quantity | Computed from | Figure |
|---|---|---|
| Seats on one roster | the batch size ceiling | **20** |
| `attendance` rows per session | one per seat [BR3.5] | **20** |
| Sessions per batch per year | a twice-weekly slot over 52 weeks: 2 × 52 | **104** |
| `attendance` rows per batch per year | 104 × 20 | **2,080** |
| Live `mark` rows per exam | one per seat | **20** |

**NFR20.28** — These volumes are small enough that no index beyond the ones the
constraints already create is required for V1, and this is stated so the
absence is a decision rather than an oversight. The constraints of
`entities.md` create: `UNIQUE (batch_id, date, start_time)` on `session`,
`UNIQUE (session_id, enrollment_id)` on `attendance`, both uniques on
`attendance_submission`, and the partial unique on `mark`. **Verifier: the
statement-count assertions above, which fail on a sequential scan only
indirectly — so this requirement's real verifier is review of the migration,
and that is stated plainly rather than implied.**

---

## 3. The session-generation job

**NFR20.29** — Generation's cost is bounded by *active batches × schedule slots
× occurrences in the horizon*, and a missed day adds **no** work, because the
horizon is a function of the calendar rather than of the last run [BR1.1,
§ 2.1]. Computed at the ceiling: 100 teachers × a nominal 5 batches × 2 slots
× 9 occurrences in a two-month horizon = **9,000** candidate inserts per run,
nearly all of which conflict and do nothing after the first run of a month.
**Verifier: the same counting assertion D3's NFR20.21 uses for fee cycles.**

**NFR20.30** — The job runs outside Bangladesh classroom hours, for the reason
D3's NFR20.22 already states: it contends for the single host the app serves
from [`infra/modules/app/main.tf`, `desired_capacity = 1`]. **Verifier: the
cron expression in `user_data.sh.tftpl`, reviewed — no automated check.**

---

## 4. Client

**NFR2.8** — The queue's persistence must not make the mid-class path depend on
a network round trip to render. A composed roster is written to device storage
and shown as `queued` without the server being reachable at all [BR3.1, BR3.2].
This is a *correctness* property of the queue, and it is listed here because it
is the only client-side performance-shaped property D4 has. **Verifier: the
offline-enqueue test of BR3.1's `violation_behaviour` (a).**

**NFR2.9** — D4 adds screens to an app with a 15 MB download ceiling and a
2 GB-RAM, `minSdk` 24 device floor [NFR2]. The queue's storage choice is
constrained by that ceiling and is settled in `tech-stack-decisions.md` § 2.
**Verifier: the release-gate AAB size assertion that already exists for NFR2.**

---

## 5. What D4 states no performance target for

Stated as a list, because each of these is a place a reader would otherwise
invent a number:

| Path | No target, because |
|---|---|
| **Attendance marking** | The requirement was dropped at Q14.3. § 1. |
| Topic log write | The same path, the same answer. |
| Conflict-resolution screen render | It renders two rosters already in hand; no server call is on its critical path. |
| Marksheet computation | Twenty integers. A target would be smaller than measurement noise on this host. |
| Session generation wall-clock | The job self-heals and may run twice or miss a day [BR1.3]. Its SLI is freshness, not duration — `observability-requirements.md` § 4. |
| API response time generally | No unit of this product has set one. D4 does not start, because a figure set now would be derived from nothing. |

---

## 6. Open items

- **Three artifacts presuppose a PU-3.6 obligation that Q14.3 removed**, and
  they are stale in two different ways. **Corrected 2026-10-24 after review**:
  an earlier draft of this document called all three stale about the same
  thing, which is not right.
  - `inception/units-generation/unit-of-work.md` and
    `inception/delivery-planning/bolt-plan.md` **record the human's
    2026-10-23 verifier choice accurately**. What is stale is the framing
    around it: "the obligation is not weakened, only differently verified"
    and "PU-3.6's mid-class latency obligation is discharged by a named
    manual check". Both sentences are true only if an obligation exists.
  - `team.md`'s Testing Posture bullet is stale about the **decision**, not
    merely its framing: it still names a Macrobenchmark "assigned to D5",
    which the human declined on 2026-10-23.
  The functional design corrected itself this turn [BR7.4]. The three upstream
  artifacts are for the human; the two records are a wording fix and `team.md`
  is a learnings-gate matter.
- **The generation horizon** — the current calendar month plus the next — is
  the functional design's stated assumption and no upstream artifact fixes it.
  NFR20.29's 9,000 figure is computed from that assumption and moves with it.

## Assumptions & Open Questions

- **The nominal 5 batches per teacher in § 3 is this document's assumption.**
  I searched this record's `requirements.md`, the prior record's NFR6 and the
  feasibility constraint register, and found a ceiling of 100 teachers and a
  few thousand students with **no per-teacher batch count anywhere**. Five is
  used to compute an order of magnitude and is labelled where it is used; the
  requirement NFR20.29 states is the *bound's shape*, not the figure.
- **The twice-weekly slot in § 2 is likewise this document's assumption**, used
  only to compute an annual row count. No upstream artifact states a typical
  slot count; `ScheduleSlot` permits any number.
- **No figure in this document was measured.** Every one is derived
  arithmetically from a stated input, and none is presented as a measurement.
  D3's performance work could measure, because `derive()` existed to read; D4's
  code does not exist yet.
