# Reliability Design — D4 `teaching-and-recording`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **The offline queue is the heart of this unit and it is § 3.** A queue is a
> reliability mechanism that becomes a reliability *hazard* the moment one of
> its states is rendered wrong — which is what `project.md`'s NEVER was
> written to prevent, and what the four-state design makes mechanically
> impossible rather than merely discouraged.
>
> The second theme is **atomicity** (§ 4): a roster is one write covering
> every seat, a correction appends and supersedes in one transaction, and a
> submission row commits with its attendance rows or not at all. Each is
> designed with **what a partial commit would actually produce**, because that
> is the thing an implementation has to be shown rather than told.
>
> **The queue's storage is a recommendation, not a settled decision**
> [tech-stack § 2]. Every property in § 3 is designed against the queue's
> BEHAVIOUR; § 3.7 states exactly which parts would differ under Room.

## Sources

- [upstream] `nfr-requirements/reliability-requirements.md` — NFR5.2–NFR5.9,
  NFR18.6–NFR18.8, NFR19.29–NFR19.47
- [upstream] `nfr-requirements/tech-stack-decisions.md` — **NFR5.10**,
  NFR5.11, NFR5.12, NFR1.6, NFR1.7, NFR1.8, NFR17.4
- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.44,
  NFR6.47, NFR6.50, NFR6.51, the concurrency guarantees this document's
  atomicity designs sit inside
- [upstream] `nfr-requirements/security-requirements.md` — NFR14.62–NFR14.64,
  the replay and ordering properties § 3.6 must preserve
- [upstream] `nfr-requirements/observability-requirements.md` — NFR25.23,
  NFR26.7, the freshness alert this document's job design feeds
- [upstream] `nfr-requirements/performance-requirements.md` — NFR2.8, the
  render-without-network property § 3.2 delivers
- [upstream] `functional-design/rules.md` — BR1.3, BR1.6, BR1.7, BR2.1,
  **BR3.1, BR3.2, BR3.5, BR3.6, BR3.7, BR3.8**, BR4.4, BR4.5, BR5.5, BR6.1,
  BR7.1, BR7.3
- [upstream] `functional-design/entities.md` — `AttendanceSubmission` and the
  six tables' governance obligation
- [upstream] `functional-design/functional-spec.md` §§ 2.1, 3.1–3.7, 8
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
- [prior] `261016-.../inception/contract-design/contract-summary.md` —
  **§ B.7, § B.8**, § G
- [code] read 2026-10-24: `app/errors/_classes.py`, `app/errors/codes.py`,
  `app/main.py`, `app/fees/commands.py`, `app/db/models.py` (`JobHeartbeat`,
  `FEE_GENERATION_JOB`), `app/notifications/fcm.py`,
  `app/governance/dispositions.py`,
  `android/src/main/kotlin/com/shikkhokplus/app/core/network/TokenStore.kt`

---

## 1. Availability

### 1.1 No target, stated as a decision [NFR18.6]

**D4 states no availability target of its own.** The product has set none, and
a figure invented at this stage would be derived from nothing [following D3's
NFR18.3].

**Verifier: none; stated so the absence is a decision rather than an
oversight.**

### 1.2 The job's posture is daily, not continuous [NFR18.7]

The session-generation job's availability requirement is **daily**, and must
not inherit the API's posture. **A run missed entirely is recovered by the next
run** [BR1.1].

**Verifier: the freshness SLI** [`observability-design.md` § 4].

### 1.3 Deploys, and the one place the queue helps [NFR18.8]

Deploys are scheduled **outside Bangladesh classroom hours** [`team.md`
Deployment], and D4 makes the reason literal: a dropped attendance write
**during a live class** is the failure a teacher will not forgive [D-9, TC-8].

**Verifier: the deploy runbook, reviewed. There is no automated check.**

**A nuance that cuts the other way, stated because it is easy to over-read:**
the queue **reduces the cost of a restart window on the two paths it covers** —
a roster composed during a restart is held and synced afterwards. It does
**not** reduce it for any other write, which still fails with a retry prompt
[BR3.1]. A reader who takes the queue as general deploy insurance has
misread it.

---

## 2. Resilience patterns: what is designed and what is deliberately not

The NFR design guide offers circuit breakers, bulkheads, retry-with-backoff,
timeouts, fallbacks and rate limiters. Applying all of them here would be
pattern-matching rather than design, so each is decided:

| Pattern | Applied? | Reasoning |
|---|---|---|
| **Retry with backoff** | **Yes, on the device queue only** (§ 3.4) | The queue's whole purpose is a flaky connection |
| **Timeout** | Yes, on the client's HTTP calls | Already in the Ktor stack; D4 adds no boundary |
| **Fallback (cached read)** | **Yes, with staleness shown** (§ 6.1) | NFR4, AC3.4.3 |
| **Circuit breaker** | **No** | D4 adds **no new external dependency** — see the note below |
| **Bulkhead** | **No** | One process, one connection pool, one host [`desired_capacity = 1`]. There is nothing to isolate from anything |
| **Rate limiter** | **No new one** | D4 adds no unauthenticated route and no SMS cost surface. The built OTP ceilings stand |

**On the circuit breaker specifically.** The only external call in the product
is the SMS gateway, which **D4 does not touch**; FCM is best-effort and already
fire-and-forget (§ 6.2), so a breaker would wrap a call whose failure is
already ignored. A breaker on the app's **own** database would fail the request
anyway, which is what happens without one.

**Stating the four "no"s is the design contribution**, because each is a
pattern a reader would otherwise expect to find and read the absence as an
oversight.

---

## 3. The offline queue

### 3.1 Four states, and none of them is a lie [NFR5.2, NFR5.3, NFR5.5]

```
                  ┌──────────────────────────────────────┐
                  │                                      │
   compose        ▼           send ok                    │
  ──────────► [queued] ──────────────────► [confirmed]   │
                  │                                      │
                  ├── network/5xx ──► [failed] ──────────┘
                  │                      ▲   auto-retry on reconnect
                  │                      │   (no teacher action)
                  │                      │
                  └── 409 version ──► [conflicted]
                                         │
                       teacher decides ──┼──► re-apply: NEW item, fresh id
                                         └──► discard: item removed
```

**Exactly four states** — `queued`, `confirmed`, `failed`, `conflicted` — every
one distinct and visible to the teacher.

**Verifier: an enumeration test over the queue's state type asserting exactly
these four** (a `when` over a sealed type is exhaustive at compile time in
Kotlin, so the test asserts the *count* and the *names*, which a fifth state
would break), **plus the UI assertions below.**

**Design statement [NFR5.3]: a `queued` item is NEVER rendered as confirmed,
at any point, in any state of connectivity.**

This is the requirement that reconciles the queue with `project.md`'s NEVER.
What the NEVER protects is **a queue that looks like success**; NFR5.3 is its
mechanical negation, and it is assertable rather than a matter of intent.

**Verifier: BR3.1's `violation_behaviour` (a), asserted in BOTH directions** —
while an item is `queued`, the UI state is not the confirmed state **and** the
server holds no row. One direction alone is weak: a UI assertion passes against
a client that renders correctly while having already written, and a
server-state assertion passes against a client that renders a lie.

**`failed` and `conflicted` are visually distinct** [NFR5.5], because `failed`
means *try again* and `conflicted` means *look at what changed*. **Verifier: an
assertion that the two states render differently — not merely that both exist
in the type.** The type-level assertion is the one that passes while both
states render identically, which is the actual failure.

### 3.2 Exactly two paths queue [NFR5.4]

**Attendance and the session topic. Nothing else.** Every other write in this
unit — exam creation, mark entry, announcements, reschedule, cancel, the
marksheet toggle — **requires connectivity and fails with an explicit retry
prompt that preserves what was typed**.

**Verifier: BR3.1's `violation_behaviour` (b) — a write to any endpoint other
than the two named fails with a retry prompt when offline, with nothing
enqueued.** Asserting "nothing enqueued" is the load-bearing half; a prompt
that appears while the write also queues is the silent-queue failure wearing a
prompt.

**Enqueue-then-render, never send-then-render** [NFR2.8]: a composed roster is
written to device storage and shown as `queued` without the server being
reachable at all.

### 3.3 Durability [NFR5.6, NFR5.10]

**A queued item is persisted to device storage, not held in memory**, and
survives the app process being killed and relaunched **in the same state**.

The failure this prevents is specific and likely: **Android kills a backgrounded
app on a 2 GB device** [NFR2] — mid-class, which is exactly when the queue holds
something. An in-memory queue loses the roster in the one circumstance it was
built for.

**Verifier: enqueue, kill the process, relaunch, assert the item is present and
still shows as not-yet-sent.** Asserting the *state* and not merely the
*presence* is the point: an item that survives as `confirmed` is worse than one
that is lost.

#### The atomic write [NFR5.10]

**The file is written to a temporary path and renamed over the live one**, so a
process killed mid-write leaves the **previous complete queue** rather than a
truncated file.

```
write  queue.json.tmp   (full serialized list)
fsync  queue.json.tmp
rename queue.json.tmp -> queue.json   (atomic on the filesystem)
```

**This is the one property the serialized-file option does not get for free,
and it is why the recommendation is "written atomically" rather than simply "a
file".** Without it the option is strictly worse than Room.

**Verifier: a test that interrupts the write part-way and asserts the previous
queue is readable.** The honest form of that test writes a corrupt or partial
`.tmp` and asserts the live file still parses — simulating the kill rather than
actually killing the process, which a unit test cannot do.

**A corrupt live file is still possible** if the rename itself is interrupted
on a filesystem that does not guarantee atomicity. **The design's answer is to
fail loudly**: an unparseable queue file surfaces as an error the teacher sees,
never as an empty queue. A silently-emptied queue is the same class of failure
as a queue that renders as confirmed.

### 3.4 Sync is automatic; resolution is not [NFR5.7]

**Sync is automatic on reconnect with no teacher action. Resolving a conflict
is not, because it needs the teacher's decision.**

| State | On reconnect |
|---|---|
| `queued` | Sent automatically |
| `failed` | Retried automatically |
| `conflicted` | **Nothing happens.** It waits for the teacher |

**Verifier: a test asserting a `failed` item retries on reconnect without
input, and a `conflicted` item does not.** Both halves in one test shape,
because the defect is a retry wrapper that treats all non-confirmed states
alike.

**Retry policy for `failed`**: bounded exponential backoff with jitter, reset
on a successful send. The jitter matters less here than in a server fleet —
there is one device — but the bound matters: an unbounded retry against a
server returning 500 drains the battery mid-class.

**A `failed` item is never silently abandoned.** After the retry bound is
reached it remains `failed` and visible, awaiting a manual retry. The bound
stops the *retrying*, never the *item*.

### 3.5 Refusal, and the conflict-resolution design [NFR5.8]

**Design statement: a write refused for a version mismatch becomes
`conflicted`, NEVER `failed`, and the teacher's offline entry is retained until
they explicitly re-apply or discard.** Nothing is merged, nothing is silently
applied, nothing is silently discarded [ADR-006].

**Why `failed` would be actively harmful**: it means *try again*, which would
invite a retry guaranteed to be refused again — or worse, a retry wrapper that
strips the version and overwrites, which is the exact failure ADR-006 exists to
prevent.

**Merging is excluded for a stated reason rather than for simplicity**: it
would mean inventing a rule for a student the two rosters disagree about, and
no layer is authorized to invent one.

#### What the screen needs, and where it comes from

The screen renders **the teacher's composed roster against the current one**.
Both are already in hand: the composed roster is the queue item, and the
current roster arrives **in the 409 body** as `error.details.current_state`
[§ B.8, NFR19.36].

**This is why the error envelope must carry `current_state`**: without it the
client would have to re-fetch, which fails if connectivity dropped again — and
**a `conflicted` item with nothing to compare against is a dead end**. The
teacher can neither re-apply meaningfully nor discard with confidence.

**Verifier: a contract test over the error body's shape** asserting
`expected_version`, `current_version` and `current_state` are all present
[NFR19.36].

#### The unresolved-conflict question

**Design statement: a conflicted item the teacher never resolves is retained
indefinitely and remains visible. There is no expiry, no auto-discard and no
auto-apply.**

This is a deliberate choice against three alternatives:

| Alternative | Why rejected |
|---|---|
| Expire after N days | An expiry is a **discard rule**, and discarding a composed roster is what BR3.6 forbids. The teacher's attendance record would vanish silently |
| Auto-apply on expiry | The stale-overwrite failure ADR-006 was written about, merely delayed |
| Auto-discard on next successful write to the same session | Plausible and still wrong: the teacher may have recorded a *different class's* marks in the interim and the conflicted item may be the correct record |

**The accepted cost: the queue can accumulate conflicted items indefinitely.**
At the computed sizes this is bounded in practice by what one teacher can
compose [`scalability-design.md` § 4.2], so it is a visibility problem rather
than a storage one.

**The mitigation is visibility, not cleanup**: a conflicted item is surfaced
persistently rather than as a dismissible notice, so the queue cannot
accumulate items the teacher has forgotten about. **Verifier: an assertion that
a conflicted item remains visible after an app restart** — which the durability
test of § 3.3 already exercises for the general case and which this applies to
the state that can persist longest.

### 3.6 Re-apply is a NEW write [NFR5.9]

**Design statement: re-apply composes a NEW write carrying the CURRENT version
and a FRESH `client_mutation_id`** [BR3.7, § B.8].

**This is the non-obvious one, and the default implementation gets it wrong.**
The obvious code reuses the queued item's existing id. But that id carries a
unique constraint, and § B.7 makes a duplicate **return the original stored
result with `200` and write nothing** — so re-apply would **report success and
change nothing at all**. The teacher would see a confirmation while the record
still held the other device's roster.

**A test that asserts only "re-apply returns 200" passes against exactly that
bug.**

**Verifier: force a conflict, re-apply, then assert BOTH:**

1. the two `client_mutation_id`s **differ**, and the `base_version`s differ;
2. the **stored roster is the re-applied one**.

The second assertion is what catches the bug; the first is what names it.

**Discard** removes the queue item and writes nothing. It is a teacher decision
and is never automatic.

### 3.7 What would differ under Room [NFR5.10, tech-stack § 2]

**The queue's storage is the human's choice.** Every requirement above is
stated against behaviour and holds either way. What genuinely changes:

| Property | Serialized file (recommended) | Room |
|---|---|---|
| Atomicity per write | **Designed**: temp-write + rename (§ 3.3) | **Free**: transactional by construction |
| Durability across process death | File on disk | SQLite on disk |
| Partial read / query | Not available; the list is read whole | Available and unused — there is no query, no join, no index |
| Build cost | None; `kotlinx-serialization` is in the stack | **A new dependency plus KSP** |
| State mutation | Rewrite the whole list | An `UPDATE` on one row |

**The decisive asymmetry is the KSP bet.** The codekb records that **Retrofit
was rejected because KSP could not parse eight untouched files on this
Kotlin/AGP pairing**, which is why Ktor is in the stack at all. Room on the
same pairing re-runs that experiment — and if it fails, it fails inside the
unit whose entire purpose is the queue.

**If Room is chosen, § 3.3's atomic-rename design is deleted rather than
adapted**, because transactionality replaces it; everything else in § 3 stands
unchanged. **That is the whole delta**, and stating it is what makes the
decision reversible.

---

## 4. Atomicity

### 4.1 The roster is one transaction [NFR19.29]

**Design statement: a roster is applied in ONE transaction covering every
seat** — the `attendance_submission` row, the version increment, and one
`attendance` row per roster entry commit together or none of them does
[BR3.5, AC3.1.5].

```
BEGIN
  UPDATE session SET attendance_version = :base + 1
   WHERE id = :sid AND attendance_version = :base   -- 0 rows -> conflict, ROLLBACK
  INSERT INTO attendance_submission (...)            -- the replay + version key
  UPSERT attendance ON (session_id, enrollment_id)   -- one per entry, set-based
COMMIT
```

**What a partial commit would produce**: attendance **half-saved** after a
mid-roster connection drop, and nothing on screen can reconcile it — the
teacher cannot tell which seats reached the server.

**Verifier: an injected mid-roster failure leaves ZERO rows and an UNCHANGED
version.** Asserting "zero, not k−1" is the point; an assertion of "fewer rows
than entries" passes against the half-saved state.

The upsert is **set-based, not a loop**, which is the same statement-count
design `performance-design.md` § 2.2 requires.

### 4.2 A mark correction is one transaction [NFR19.30]

**The new row is appended and the old row's `superseded_by_id` is set in the
SAME transaction** [BR4.4].

**What each committed half would produce:**

| Half committed | Result |
|---|---|
| Insert only | **Two live marks** — which the partial unique index of BR4.5 then rejects, so this half fails loudly |
| Update only | **A superseded row with no successor** — a seat whose result has vanished |

**Verifier: an injected failure between the two writes leaves the original row
live and un-superseded.** The second case is the dangerous one precisely
because no constraint catches it — the index forbids two live rows, not zero.

### 4.3 A reschedule updates, never deletes and recreates [NFR19.31, BR1.7]

**Verifier: record a topic and a roster, reschedule, assert the session id is
unchanged and both survive.**

**The same property holds for a schedule-slot change** [BR1.2]: changing a
batch's slots never alters an existing session, and only future occurrences
follow the new slots. Designed here rather than in § 8 because it is the same
hazard as a reschedule — a generation job that *reconciled* against the new
slots would rewrite history [NFR19.40] — and it is the reason sessions are
materialised rows rather than a computed view of the recurrence rule
[entities.md]. **Verifier: change the slots, assert existing sessions and
their attendance are untouched.**

Implemented as delete-and-recreate, **a reschedule silently discards everything
recorded against the class** — the attendance cascades away with the session
row, and the teacher sees an empty roster for a class they marked.

### 4.4 Generation commits per occurrence [NFR19.32]

A partial failure costs only the uncommitted remainder, and the next run
completes it [BR1.3].

**Verifier: an injected failure part-way through a run leaves the
already-created sessions present.**

This is the opposite granularity from § 4.1 and deliberately so: a roster is
**one teacher's single decision** and must be all-or-nothing; a generation run
is **thousands of independent occurrences** and must not lose 8,999 of them to
one failure.

---

## 5. Why `AttendanceSubmission` exists [NFR19.33, NFR19.34]

Stated because the next reader will compare the schema to the prior catalogue
and conclude the table is surplus.

§ B.7 places `client_mutation_id` on `Attendance`, "per `components.md`". But
**a roster is many `attendance` rows sharing one `client_mutation_id`**, so a
unique constraint on that column cannot exist there: per-row it is not unique
for the write it is meant to protect, and absent it leaves idempotency to
application logic. **The upstream catalogue is internally inconsistent for the
attendance case specifically**, and the submission row is what makes the
constraint expressible.

**Both guarantees become database constraints on the one row per write that
can carry them:**

| Constraint | Guarantees |
|---|---|
| `UNIQUE (submitted_by_account_id, client_mutation_id)` | Replay safety [§ B.7] |
| `UNIQUE (session_id, resulting_version)` | The version increment [BR3.4] |

**This is the shape D3's double-crediting defect had** — a write with no
natural key to conflict on, guarded only by application logic. **Here the key
exists.**

**Verifier: both constraints present in the migration, each with a test that
fires it** — a test that provokes the violation, not merely one that asserts
the constraint's existence in the schema.

### The replay response [NFR19.34, NFR14.63]

A replayed `(submitted_by_account_id, client_mutation_id)` returns the
**original stored result** with `200` — not `201`, not an error — writes no
second `attendance` row, does not increment the version, and leaves the
original's **`created_at` unchanged**.

**Verifier: submit the same body twice; assert one submission row, one
increment, and that `created_at` did not move.**

**The `created_at` assertion is the load-bearing one: a replay is observably a
replay.** An assertion that merely counts rows passes against an implementation
that **overwrites the original in place** — the row count is right, the version
is right, and the original decision's timestamp is destroyed.

---

## 6. Graceful degradation

### 6.1 Offline reads degrade to cache, with staleness shown [NFR19.43]

**The server's half of the contract is a server timestamp on every schedule and
topic read** [BR7.3].

**The client cannot state an age the server never sent.** It would have to use
the device clock — which is the very thing excluded from decisions, for the
same reason `composed_at` is recorded and never used [NFR24.20]. A phone with a
wrong clock would display a confidently wrong age.

**Verifier: the response carries the timestamp**, asserted as a contract test.

**A related nullability property travels with the topic read** [BR2.2]: an
**unwritten** topic is distinguishable from one **written as empty**, which is
why `Session.topic` is nullable rather than defaulting to `''` [entities.md].
A cached read that collapses the two tells the teacher a class was logged as
blank when nobody logged it. **Verifier: a test asserting null and empty-string
round-trip distinctly through the API.**
The client-side rendering of the age has **no automated verifier** in this
unit; it is one of the seven screens covered by the written per-screen check
[NFR17.8].

### 6.2 Push is best-effort [NFR19.44]

Push notification failure is **logged and not surfaced** — the project's stated
exception to "silent failures are not acceptable" — and **D4 reuses D3's FCM
adapter rather than building a second one** [§ G].

**Verifier: the absence of a second adapter, and D3's existing push tests.**
The absence is the real assertion: § G of the prior contract summary assigned
adapter ownership to *both* this unit and D3, which is the ambiguity that
produces two adapters. D3 built it; D4 reuses it.

### 6.3 An unrecorded past session stays `scheduled` [NFR19.45]

**A session whose time has passed and which nobody recorded does NOT become
`held` by the clock** [functional-spec § 2.2].

**Verifier: a test asserting an unrecorded past session's status is
unchanged.**

This is a reliability property in the sense that matters to a teacher: **an
unrecorded class stays visible rather than silently becoming history.** A
clock-driven transition would quietly bury the classes most needing attention.

### 6.4 Degradation tiers

| Tier | What | Behaviour when degraded |
|---|---|---|
| **Critical** | Attendance and topic writes | **Queue** (§ 3) — the only writes that survive no connectivity |
| **Critical** | Every other write | Explicit retry prompt preserving input [NFR5.4] |
| **Important** | Schedule, roster, marksheet reads | Cached with staleness shown (§ 6.1) |
| **Nice to have** | Push notification | Fire-and-forget, logged, never surfaced (§ 6.2) |

---

## 7. Error classes [NFR19.35–NFR19.38]

### 7.1 No new exception class [NFR19.35]

**D4 introduces no new exception class.** A version conflict is
`ConflictError`, whose built docstring already states this semantic exactly:
*"Valid request; current state forbids it. Refetch and decide. Retrying as-is
is wrong."*

`retryable: false` **follows from the class and is read in one place** — a
raise site cannot set it [`app/errors/_classes.py`]. That is the property that
keeps two sites of the same class from disagreeing.

**Verifier: the existing error-contract test, plus review that no new subclass
appears.**

### 7.2 The conflict envelope [NFR19.36]

`ATTENDANCE_VERSION_CONFLICT` carries `expected_version`, `current_version` and
`current_state` in `error.details` [§ B.8]. **Verifier: a contract test over
the error body's shape.**

Why it is load-bearing is designed in § 3.5: **without `current_state` a
`conflicted` item is a dead end.**

The refusal **ordering** — authorization before the version check — is a
security property and is designed in `security-design.md` § 5.4.

### 7.3 Declared error responses [NFR19.37]

**Every D4 route declares its error responses in the OpenAPI document**,
continuing what D3 finished.

A framing point worth stating, because the previous draft of the upstream
requirement got it backwards: `app/main.py`'s component injection is **not an
ongoing stopgap**. D3's nine fee routes made it a **no-op**, and
`test_the_injection_is_now_redundant` asserts the no-op is real rather than
claimed. The injection is kept deliberately, because a unit whose routes
stopped referencing a component would silently drop it from the committed
contract and the diff gate would pass over the absence.

**D4's obligation is therefore to keep that no-op true for its own routes**,
not to work around a stopgap. **Verifier: the schema-diff gate, plus an
assertion that each D4 route declaring a 409 references the envelope.**

### 7.4 Two state-based refusals [NFR19.38]

A write to a `cancelled` session [BR1.6] and any write to an `inactive` batch
[BR5.5] are `ConflictError`, not `ValidationError`: **the request is
well-formed and the current state is what forbids it.**

**Verifier: a test per case asserting the class AND that existing rows are
untouched.**

---

## 8. The generation job

### 8.1 Safe by construction [NFR19.39, NFR19.40]

Running the job any number of times, on any number of days, is safe: **the
conflict is the success path** [BR1.3].

**Design statement: generation NEVER deletes and NEVER updates, and never
considers rows with `origin: ad_hoc`** [BR1.4].

**Verifier: create an ad-hoc session on a non-slot date, run generation, assert
the row and its attendance still exist with its origin unchanged.**

**A job that *reconciles* rather than *inserts* would delete the extra class a
teacher held on a Saturday, taking its attendance with it** — and that is the
shape a reasonable implementation reaches for if the rule is not written down.
`origin` has **no default** for the same reason [entities.md, ADR-013]: an
insert path that does not state the origin is one that forgot to think about
it.

### 8.2 The heartbeat is written on completion, unconditionally [NFR19.41]

The job writes a heartbeat on **completion, unconditionally on outcome**,
reusing the `JobHeartbeat` mechanism D3 built. **A run that finds nothing to
create still writes the row.**

**Verifier: a test asserting the heartbeat is written for a run that creates
ZERO sessions.**

D3's docstring already records why, and it transfers without modification: **a
heartbeat written only when rows were created goes stale during correct
operation, fires the alert constantly, and gets it muted.**

Verified by reading `app/db/models.py`: `JobHeartbeat` is **keyed by
`job_name`** (primary key), so a second job name is a second row and needs no
schema change. `FEE_GENERATION_JOB = "fee_cycle_generation"` is the existing
constant and `app/fees/commands.py` already takes `job_name` as a parameter
defaulting to it — so **the mechanism is parameterised rather than hard-wired**
and D4 registers its own name beside it [NFR1.8].

**The two jobs' freshness is tracked independently.** A shared name would let a
healthy fee run mask a session job that has never fired.

### 8.3 Runnable by hand with no required arguments [NFR19.42]

**That is the recovery procedure when the freshness alert fires.** An
entry point that needs arguments is one nobody can run correctly at the moment
it is needed.

**Verifier: the management command's signature.**

---

## 9. Migration and governance

### 9.1 One migration, six tables [NFR19.46]

The six new tables arrive in **one migration**, each with a `TableGovernance`
entry written in the same change [BR6.1], and each **granted explicitly** to
the restricted role [`security-design.md` § 1.2].

**Verifier: `tests/db/test_governance.py`, already built, asserting in BOTH
directions.** The second direction is what D4 needs: a typo in a table name
yields a **stale entry naming a table that does not exist**, which a
one-directional check misses entirely.

### 9.2 Forward-only, rehearsed, backed up [NFR19.47]

The migration is forward-only and backward-compatible, runs as a **distinct
logged step before the new container serves traffic**, and is rehearsed on
staging [`team.md` Deployment]. A verified `pg_dump` precedes any production
run.

**Verifier: `deploy.yml`'s existing plan-then-apply steps.**

**D4's six tables make this record's largest schema change after D3's four** —
which is the reason the staging rehearsal matters more here than it has so far,
and the reason § 9.1's both-directions check is worth naming twice.

---

## Assumptions & Open Questions

- **`project.md`'s NEVER on local write queues contradicts NFR5, which it
  cites.** This document designs the queue in full. BR3.1 reconciles them —
  what the NEVER protects is a queue that *looks like success*, and § 3.1 is
  its mechanical negation. **This document does not edit memory. For the
  human, at a learnings gate.**
- **The queue's device-side storage is a recommendation, not a decision**
  [tech-stack § 2]. § 3.7 states the complete delta under Room. I searched
  § B.8, NFR5, NFR5.1, FR3.6 and the Android module, and confirmed by reading
  that **the only persistence in the app today is `TokenStore.kt`'s
  `EncryptedTokenStore`**, using `MasterKey` plus `EncryptedSharedPreferences`,
  with an `InMemory` fallback when the Keystore is unavailable. There is no
  Room, no DataStore and no SQLite. **The queue's storage is a genuine design
  choice, not a reuse.**
- **The retry bound and backoff parameters in § 3.4 are not fixed by any
  upstream artifact.** I searched NFR5, NFR5.1, § B.8 and this unit's NFR
  requirements and found the *behaviour* required (automatic sync on reconnect,
  no automatic retry for `conflicted`) and **no numbers**. The design states
  the shape — bounded, jittered, reset on success, item retained after the
  bound — and leaves the figures to implementation, because a number invented
  here would be derived from nothing.
- **No disaster-recovery objective (RPO/RTO) is set by any unit of this
  product.** I searched both records' requirements, `team.md`'s Deployment
  section and the infrastructure design. What exists is the backup and rollback
  procedure, not a stated objective. D4 does not introduce one, and its data is
  covered by the same `pg_dump` and snapshot path as everything else.
- **I could not execute any test suite.** Docker is unavailable in this
  session. Every claim about built code above — `JobHeartbeat`'s primary key,
  `app/fees/commands.py`'s `job_name` parameter, `ConflictError`'s docstring,
  `TokenStore.kt`'s two implementations — is from **reading the file**, cited
  by path so it is checkable.
