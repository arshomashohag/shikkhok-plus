# Reliability Requirements — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **The offline queue's reliability properties are the heart of this unit**,
> and they are § 2. A queue is a reliability mechanism that becomes a
> reliability *hazard* the moment one of its states is rendered wrong — which
> is what `project.md`'s NEVER was written to prevent, and what the four-state
> design exists to make mechanically impossible.
>
> The second theme is **atomicity**: a roster is one write covering every seat
> [BR3.5], a correction appends and supersedes in one transaction [BR4.4], and
> a submission row and its attendance rows commit together or not at all. Each
> is specified below with what a partial commit would actually produce.

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3. A bare `NFR19.21`, `NFR19.25` or
> `NFR5.1` below is a **citation**, never an ID defined here. Note that
> **`NFR5.1` is an inception requirement in the prior record** — the queue
> semantics — and not a derived ID of this stage.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ 2.1, 3.1–3.7, 8
- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.3, BR1.6, BR1.7, BR2.1, **BR3.1, BR3.2, BR3.5, BR3.6, BR3.7, BR3.8**,
  BR4.4, BR4.5, BR5.5, BR6.1, BR7.1
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  `AttendanceSubmission`, and the six tables' governance obligation
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  **NFR5, NFR5.1**, NFR4, NFR16, NFR19's ancestors
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
- [prior] `261016-.../inception/contract-design/contract-summary.md` —
  **§ B.7, § B.8**, § G
- [code] `app/errors/_classes.py`, `app/errors/codes.py`, `app/main.py`,
  `app/fees/commands.py`, `app/notifications/fcm.py`,
  `app/governance/dispositions.py` — read 2026-10-24

---

## 1. Availability

**NFR18.6** — D4 states no availability target of its own. The product has set
none, and a figure invented at this stage would be derived from nothing
[following D3's NFR18.3]. **Verifier: none; stated so the absence is a
decision rather than an oversight.**

**NFR18.7** — The session-generation job's availability requirement is
**daily, not continuous**, and must not inherit the API's posture. A run
missed entirely is recovered by the next run [BR1.1, NFR6.52]. **Verifier: the
freshness SLI in `observability-requirements.md` § 4.**

**NFR18.8** — Deploys are scheduled outside Bangladesh classroom hours
[`team.md` Deployment], and D4 is the unit that makes the reason literal: a
dropped attendance write **during a live class** is the failure a teacher will
not forgive [D-9, TC-8]. **Verifier: the deploy runbook, reviewed — no
automated check.**

A nuance worth stating, because it cuts the other way: **the queue reduces the
cost of a restart window on the two paths it covers** — a roster composed
during a restart is held and synced afterwards. It does **not** reduce it for
any other write, which still fails with a retry prompt [BR3.1].

---

## 2. The offline queue

### 2.1 Four states, and none of them is a lie

**NFR5.2** — The queue has **exactly four** states — `queued`, `confirmed`,
`failed`, `conflicted` — and every one is distinct and visible to the teacher
[NFR5.1, BR3.2]. **Verifier: an enumeration test over the queue's state type
asserting exactly these four, plus the UI assertions below.**

**NFR5.3** — **A `queued` item is never rendered as confirmed**, at any point,
in any state of connectivity [BR3.1, AC3.1.3]. **Verifier: BR3.1's
`violation_behaviour` (a), asserted in both directions — while an item is
`queued`, the UI state is not the confirmed state *and* the server holds no
row.**

This is the requirement that reconciles the queue with `project.md`'s NEVER.
What the NEVER protects is **a queue that looks like success**; NFR5.3 is the
mechanical negation of that, and it is assertable rather than a matter of
intent.

**NFR5.4** — **Exactly two paths queue**: attendance and the session topic
[NFR5, FR3.6, BR3.1]. Every other write in this unit — exam creation, mark
entry, announcements, reschedule, cancel, the marksheet toggle — requires
connectivity and fails with an explicit retry prompt that preserves what was
typed. **Verifier: BR3.1's `violation_behaviour` (b) — a write to any endpoint
other than the two named fails with a retry prompt when offline, with nothing
enqueued.**

**NFR5.5** — `failed` and `conflicted` are **visually distinct**, because
`failed` means "try again" and `conflicted` means "look at what changed"
[AC3.1.10, BR3.2]. **Verifier: an assertion that the two states render
differently — not merely that both exist in the type.**

### 2.2 Durability

**NFR5.6** — A queued item is **persisted to device storage, not held in
memory**, and survives the app process being killed and relaunched in the same
state [BR3.2, AC3.1.9]. **Verifier: enqueue, kill the process, relaunch,
assert the item is present and still shows as not-yet-sent.**

The failure this prevents is specific and likely: Android kills a backgrounded
app on a 2 GB device [NFR2] — mid-class, which is exactly when the queue holds
something. An in-memory queue loses the roster in the one circumstance it was
built for.

**NFR5.7** — Sync is **automatic on reconnect with no teacher action**;
resolving a conflict is **not**, because it needs the teacher's decision
[NFR5.1, BR3.1]. **Verifier: a test asserting a `failed` item retries on
reconnect without input, and a `conflicted` item does not.**

### 2.3 Refusal, and what must never happen to a refused write

**NFR5.8** — A write refused for a version mismatch becomes `conflicted`,
**never `failed`**, and the teacher's offline entry is **retained** until they
explicitly re-apply or discard [BR3.6, FR11.5]. Nothing is merged, nothing is
silently applied, nothing is silently discarded [ADR-006]. **Verifier: a
forced-conflict test asserting the state, and asserting the composed entry is
still readable afterwards.**

Merging is excluded for a stated reason rather than for simplicity: it would
mean inventing a rule for a student the two rosters disagree about, and no
layer is authorized to invent one.

**NFR5.9** — **Re-apply composes a NEW write carrying the current version and
a FRESH `client_mutation_id`** [BR3.7, § B.8]. **Verifier: force a conflict,
re-apply, assert the two mutation ids differ — and assert the re-applied
roster is what is stored.**

This is the non-obvious one, and the default implementation gets it wrong. The
obvious code reuses the queued item's existing id. But that id carries a
unique constraint, and § B.7 makes a duplicate **return the original stored
result with `200` and write nothing** — so re-apply would report success and
change nothing at all. The teacher would see a confirmation while the record
still held the other device's roster. **A test that asserts only "re-apply
returns 200" passes against exactly that bug**, which is why the verifier is
the id comparison and the stored roster, not the status code.

---

## 3. Atomicity

**NFR19.29** — A roster is applied in **one transaction** covering every seat:
the `attendance_submission` row, the version increment, and one `attendance`
row per roster entry commit together or none of them does [BR3.5, AC3.1.5].
**Verifier: an injected mid-roster failure leaves zero rows and an unchanged
version.**

A per-student write leaves attendance **half-saved** after a mid-roster
connection drop, and nothing on screen can reconcile that — the teacher cannot
tell which seats reached the server.

**NFR19.30** — A mark correction appends the new row and sets the old row's
`superseded_by_id` **in the same transaction** [BR4.4]. **Verifier: an
injected failure between the two writes leaves the original row live and
un-superseded.** A committed half leaves either two live marks — which the
partial unique index of BR4.5 then rejects — or a superseded row with no
successor, which is a seat whose result has vanished.

**NFR19.31** — A reschedule **updates the existing row** and never
delete-and-recreates [BR1.7]. **Verifier: record a topic and a roster,
reschedule, assert the session id is unchanged and both survive.** Implemented
as delete-and-recreate, a reschedule silently discards everything recorded
against the class.

**NFR19.32** — Session generation commits **per occurrence**, so a partial
failure costs only the uncommitted remainder and the next run completes it
[BR1.3, following D3's NFR19.8]. **Verifier: an injected failure part-way
through a run leaves the already-created sessions present.**

---

## 4. Why `AttendanceSubmission` exists — a reliability note, not an extra table

Stated here because the next reader will compare the schema to the prior
catalogue and conclude the table is surplus.

§ B.7 places `client_mutation_id` on `Attendance`, "per `components.md`". But
**a roster is many `attendance` rows sharing one `client_mutation_id`**, so a
unique constraint on that column cannot exist there: per-row it is not unique
for the write it is meant to protect, and absent it leaves idempotency to
application logic. **The upstream catalogue is internally inconsistent for the
attendance case specifically**, and the submission row is what makes the
constraint expressible.

**NFR19.33** — The replay guarantee and the version-increment guarantee are
both **database constraints**, on the one row per write that can carry them:
`UNIQUE (submitted_by_account_id, client_mutation_id)` and
`UNIQUE (session_id, resulting_version)` [entities.md, BR3.4, BR3.8].
**Verifier: both constraints present in the migration, each with a test that
fires it.**

This is the shape D3's double-crediting defect had — a write with no natural
key to conflict on, guarded only by application logic. Here the key exists.

**NFR19.34** — A replayed `(submitted_by_account_id, client_mutation_id)`
returns the **original stored result** with `200` — not `201`, not an error —
writes no second `attendance` row, does not increment the version, and leaves
the original's **`created_at` unchanged** [BR3.8, § B.7]. **Verifier: submit
the same body twice; assert one submission row, one increment, and that
`created_at` did not move.**

The `created_at` assertion is the load-bearing one: *a replay is observably a
replay*. An assertion that merely counts rows passes against an implementation
that overwrites the original in place.

---

## 5. Error classes, and the one new code

**NFR19.35** — D4 introduces **no new exception class**. A version conflict is
`ConflictError`, whose built docstring already states this semantic exactly:
*"Valid request; current state forbids it. Refetch and decide. Retrying as-is
is wrong."* `retryable: false` follows from the class and is read in one place
— a raise site cannot set it [`app/errors/_classes.py`]. **Verifier: the
existing error-contract test, plus review that no new subclass appears.**

**NFR19.36** — `ATTENDANCE_VERSION_CONFLICT` carries `expected_version`,
`current_version` and `current_state` in `error.details` [§ B.8]. **Verifier:
a contract test over the error body's shape.** The client cannot render the
conflict-resolution screen without the current state, so an envelope missing
it turns a `conflicted` item into a dead end.

**NFR19.37** — Every D4 route **declares its error responses** in the OpenAPI
document, continuing what D3 finished. *(Framing corrected 2026-10-24 after
review: an earlier draft called `app/main.py`'s component injection an ongoing
stopgap. It is not — D3's nine fee routes made it a **no-op**, and
`test_the_injection_is_now_redundant` asserts the no-op is real rather than
claimed.)* The injection is kept deliberately, because a unit whose routes
stopped referencing a component would silently drop it from the committed
contract and the diff gate would pass over the absence. **D4's obligation is
therefore to keep that no-op true for its own routes**, not to work around a
stopgap. **Verifier: the schema-diff gate, plus an assertion that each D4
route declaring a 409 references the envelope.**

**NFR19.38** — These writes are refused as `ConflictError` rather than
`ValidationError`, because the request is well-formed and the **current state**
is what forbids it: a write to a `cancelled` session [BR1.6], and any write to
an `inactive` batch [BR5.5]. **Verifier: a test per case asserting the class
and that existing rows are untouched.**

---

## 6. The generation job

**NFR19.39** — Running the session-generation job any number of times, on any
number of days, is safe by construction: the conflict is the success path
[BR1.3]. **Verifier: NFR6.51 and NFR6.52's tests in
`scalability-requirements.md`.**

**NFR19.40** — Generation **never deletes and never updates**, and never
considers rows with `origin: ad_hoc` [BR1.4]. **Verifier: create an ad-hoc
session on a non-slot date, run generation, assert the row and its attendance
still exist with its origin unchanged.** A job that *reconciles* rather than
*inserts* would delete the extra class a teacher held on a Saturday, taking its
attendance with it — and that is the shape a reasonable implementation reaches
for if the rule is not written down.

**NFR19.41** — The job writes a heartbeat on **completion**, unconditionally on
outcome, reusing the `JobHeartbeat` mechanism D3 built [`app/db/models.py:977`,
`app/fees/commands.py`]. A run that finds nothing to create still writes the
row. **Verifier: a test asserting the heartbeat is written for a run that
creates zero sessions.** D3's docstring already records why: a heartbeat
written only when rows were created goes stale during correct operation, fires
the alert constantly, and gets it muted.

**NFR19.42** — The job is runnable **by hand with no required arguments**,
because that is the recovery procedure when the freshness alert fires
[`app/fees/commands.py`, D3's § 2]. **Verifier: the management command's
signature.**

---

## 7. Graceful degradation

**NFR19.43** — Offline reads degrade to cache with **staleness shown** [NFR4,
AC3.4.3], and the server's half of that contract is a **server timestamp on
every schedule and topic read** [BR7.3]. **Verifier: the response carries the
timestamp.** The client cannot state an age the server never sent — it would
have to use the device clock, which is the thing excluded from decisions for
the same reason `composed_at` is recorded and never used.

**NFR19.44** — Push notification failure is **best-effort, logged and not
surfaced** — the project's stated exception to "silent failures are not
acceptable" — and D4 reuses **D3's FCM adapter** rather than building a second
one [§ G, D3's NFR19.24]. **Verifier: the absence of a second adapter, and
D3's existing push tests.**

**NFR19.45** — A session whose time has passed and which nobody recorded stays
`scheduled` rather than becoming `held` by the clock [functional-spec § 2.2].
**Verifier: a test asserting an unrecorded past session's status is
unchanged.** This is a reliability property in the sense that matters to a
teacher: an unrecorded class stays **visible** rather than silently becoming
history.

---

## 8. Governance and migration

**NFR19.46** — The six new tables arrive in **one migration**, each with a
`TableGovernance` entry written in the same change [BR6.1]. **Verifier:
`tests/db/test_governance.py`, already built, asserting in both directions.**
The second direction is what D4 needs: a typo in a table name yields a **stale
entry naming a table that does not exist**, which a one-directional check
misses entirely.

**NFR19.47** — The migration is forward-only and backward-compatible, runs as a
distinct logged step before the new container serves traffic, and is rehearsed
on staging [`team.md` Deployment]. A verified `pg_dump` precedes any production
run. **Verifier: `deploy.yml`'s existing plan-then-apply steps.** D4's six
tables make this record's largest schema change after D3's four.

---

## Assumptions & Open Questions

- **`project.md`'s NEVER on local write queues contradicts NFR5, which it
  cites.** This document specifies the queue in detail. The reconciliation is
  BR3.1's and the amendment is a learnings-gate matter; this document does not
  edit memory. **For the human.**
- **The queue's device-side storage mechanism is not decided by any upstream
  artifact.** I searched the prior record's § B.8, NFR5, NFR5.1, FR3.6, and the
  Android module itself — the only persistence in the app today is
  `TokenStore.kt` using `EncryptedSharedPreferences`. The choice is made in
  `tech-stack-decisions.md` § 2, which is where it belongs; the requirements
  above are stated against the queue's **behaviour** and hold under any
  storage choice.
- **No disaster-recovery objective (RPO/RTO) is set by any unit of this
  product.** I searched both records' requirements, `team.md`'s Deployment
  section and the infrastructure design. What exists is the backup and rollback
  procedure, not a stated objective. D4 does not introduce one, and its data is
  covered by the same `pg_dump` and snapshot path as everything else.
