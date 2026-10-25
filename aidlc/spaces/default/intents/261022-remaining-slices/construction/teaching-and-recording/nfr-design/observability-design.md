# Observability Design — D4 `teaching-and-recording`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 is the unit where a careless log line becomes a child-safety
> incident.** Everything this unit stores is a record of a named child: where
> they were on a given afternoon, and what they scored. § 1 is therefore the
> longest section and is designed as **prohibitions with a named positive
> half**, because a prohibition alone produces an undebuggable system and the
> next engineer re-adds the field.
>
> **The second theme is that the pilot must answer a question this design
> cannot answer in advance: how often does a conflict actually happen?** The
> whole unit is built around refuse-on-conflict and nobody knows the rate.
> § 3 designs the instrument, and it is the one genuinely new thing D4 adds
> here.
>
> **There is no metrics backend in this product.** § 3.1 designs around that
> fact rather than specifying a dashboard against a backend that does not
> exist.

## Sources

- [upstream] `nfr-requirements/observability-requirements.md` — NFR24.13–
  NFR24.20, NFR25.18–NFR25.27, NFR26.7–NFR26.10
- [upstream] `nfr-requirements/reliability-requirements.md` — NFR19.41,
  NFR19.42, NFR19.36, the heartbeat and envelope this document's alerting
  and conflict-logging design depend on
- [upstream] `nfr-requirements/security-requirements.md` — NFR14.63,
  NFR14.64, whose replay and ordering properties § 1.3 must not undo
- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.44,
  NFR6.48, the conflict guarantee and granularity cost § 3.2's counter
  measures
- [upstream] `nfr-requirements/performance-requirements.md` — NFR20.29,
  NFR20.30, the generation run whose counters § 3.3 designs
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR1.8, NFR17.8
- [upstream] `functional-design/rules.md` — BR1.3, BR3.4, BR3.6, BR3.8,
  BR4.4, BR5.3, BR6.2, BR7.1, BR7.5
- [upstream] `functional-design/entities.md` — `AttendanceSubmission`
  (`base_version`, `composed_at`), `Mark`
- [upstream] `functional-design/functional-spec.md` §§ 2.1, 3.2, 3.6, 4.1
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.8
- [code] read 2026-10-24: `app/audit/log.py`, `app/fees/commands.py`,
  `app/db/models.py` (`JobHeartbeat`, `FEE_GENERATION_JOB`),
  `app/errors/codes.py`

---

## 1. What must never be logged

The standing rules hold and are not restated. What follows is what **D4 adds**
to the prohibited set, and **each is a thing a reasonable debugging session
reaches for** — which is why each is paired with what may be logged instead.

### 1.1 No child name, ever [NFR24.13]

**Design statement: no student or child name reaches any log line, at any
level.** D4 is the first unit whose core operation is a list of named children.

**What is logged instead**: the `enrollment_id`. It is already the identifier
the roster carries on the wire [BR5.3], it is meaningless without the server's
mapping, and it is sufficient to find the row while debugging.

**Verifier: review, plus the existing structured-logging convention that log
lines carry the correlation id and identifiers rather than prose. There is no
automated scanner for this, and saying so plainly is the requirement's honest
half.**

### 1.2 No mark, ever [NFR24.14]

**No mark, and no exam result of any kind, reaches a log line.** Not in an
error, not at debug level, not in a validation message.

**The validation message is the specific trap.** A mark exceeding the exam
total is refused [BR4.2], and the natural message is *"42 exceeds total 40"* —
which logs a child's mark while reporting a routine validation failure.

**What is logged instead**: the `exam_id`, the `enrollment_id` and the fact of
the violation. **The message_key carries no interpolated mark.**

**Verifier: review; the same absence of an automated check applies.**

### 1.3 No roster, and the conflict path specifically [NFR24.15, NFR24.16]

**No attendance roster reaches a log line** — and in particular the
`ATTENDANCE_VERSION_CONFLICT` path **must not log `current_state`, which IS
the roster**, when it logs the conflict.

**This is the specific hazard in this unit, and it is structural rather than
careless.** The conflict is interesting, so it will be logged. The error body
already carries the roster, because § B.8 requires it for the
conflict-resolution screen [`reliability-design.md` § 3.5]. **And the obvious
implementation logs the error body.**

**The design is that the conflict is logged from its METADATA, never from its
payload:**

| Field | Logged? | Why |
|---|---|---|
| `session_id` | **yes** | Finds the session |
| `expected_version`, `current_version` | **yes** | The whole diagnostic content of a conflict |
| `submitted_by_account_id` | **yes** | Which device/teacher |
| `client_mutation_id` | **yes** [NFR24.16] | Correlates the queue item to the server event |
| `composed_at` | **yes** [NFR24.16] | The pilot's queue-latency question |
| `current_state` / `entries` | **NEVER** | This is the roster |

**NFR24.16 is the positive half stated deliberately**, so the conflict path
remains debuggable. A prohibition without it produces a log line reading
"conflict occurred" and an engineer who re-adds the body next sprint.

**Verifier: a test asserting the conflict log record carries the session id,
the two version numbers and the account id, and NO entries collection.** This
is the one of the three logging obligations that **does** get an automated
test, because the field is structured and the assertion is over a record rather
than over prose.

### 1.4 No traceback, no verbatim database error [NFR24.17]

An exception traceback never reaches a client, and a database error on these
tables is **never returned verbatim** — a unique-violation message on
`attendance` names the session and enrollment ids.

**Verifier: the existing exception-handler contract test.**

---

## 2. The audit trail is the data, not a parallel log

### 2.1 Who and when, on the row itself [NFR24.18]

**Every attendance row records who marked it and when** (`recorded_by_account_id`,
`recorded_at`), and every mark records the same.

The correction history is:

| Entity | The trail is | Not |
|---|---|---|
| `mark` | the **supersession chain** [BR4.4] | a parallel log |
| `attendance` | the **submission sequence** [entities.md] | a parallel log |

**The reasoning is D3's and transfers: a parallel audit log is a second record
that drifts from the first. Here the data IS the trail.**

**Verifier: a test asserting a correction leaves the prior state readable.**

**D4 writes nothing to `auth_audit_log`.** That table holds authentication
events only, and D4 adds no credential, no session and no token
[`security-design.md` § 9]. Stated because "audit" is the word that invites a
second writer.

### 2.2 Submissions are never deleted [NFR24.19]

`attendance_submission` rows are never deleted, because **the sequence of
submissions for a session IS the attendance correction history**.

**Verifier: review of the migration for the absence of any cleanup path.**

This is also why the table's growth is append-only by design and accepted
[`scalability-design.md` § 1.4]: pruning it would destroy both the replay key
and the correction history.

### 2.3 `composed_at` is recorded and used in no decision [NFR24.20]

**Design statement: `composed_at` appears in no comparison and no ordering.**

**It is a device clock**, and a device clock in a conflict rule would let a
wrong phone time silently reorder two teachers' writes. It exists for the
pilot's queue-latency question only.

**Verifier: a code-level assertion that `composed_at` appears in no
comparison, orderings included — checkable by review, and worth a grep in the
review checklist rather than left to memory.** Nothing automated enforces it.

**The design pressure is real**: `composed_at` looks exactly like the field a
developer would reach for to decide which of two queued rosters is "newer".
The version is what decides that, and the version is a server counter.

---

## 3. Metrics

### 3.1 The constraint: there is no metrics backend

**Design statement: the counters below are specified as FACTS THAT MUST BE
COUNTABLE, not as emissions to a metrics pipeline.**

I searched both records' `inception/` trees, `infra/`, and the built `app/` for
Prometheus, StatsD, CloudWatch metrics or any metrics client, and found
**none**. The observability surface today is **structured logs plus the
`JobHeartbeat` row**.

Two consequences, both designed rather than lamented:

1. **Every counter below is answerable by querying the data**, because the
   columns that make it answerable are on the schema. Whether it is also
   emitted as a metric is left to implementation.
2. **NFR25.20 is the load-bearing design decision here**: `base_version` is
   stored on every submission precisely so **the conflict rate is answerable
   from data after the pilot**, rather than only from counters sampled at the
   time. If no metrics pipeline is ever built — which is the outcome to bet on
   for V1 — the question is still answerable.

```sql
-- the conflict rate, answerable from the data alone, with no metrics backend
SELECT count(*) FILTER (WHERE base_version <> resulting_version - 1) AS anomalies,
       count(*)                                                      AS applied
  FROM attendance_submission;
-- and the conflicts themselves are the REFUSED writes, which write no row --
-- so the counter of 3.2 is what makes them visible at all.
```

**That last line is the honest limit of the data-only route, and it is why
§ 3.2's counter is required rather than optional**: a refused write leaves no
row, so the stored data can show what applied but never what was refused.

### 3.2 Attendance submissions counted by outcome [NFR25.18, NFR25.19]

**Design statement: attendance submissions are counted by outcome — applied,
conflicted, and replayed — as THREE separate counters.**

**Why this is the unit's one genuinely new instrument**: D4 is built entirely
around a hypothesis nobody has measured — that conflicts are rare enough for
refuse-and-re-apply to be the right trade, and common enough to be worth
building for. Bolt 4's confidence hypothesis says so in as many words.

| Pilot outcome | What it means |
|---|---|
| Conflict rate near zero | The conflict-resolution screen was cheap insurance |
| Conflict rate high | **Session-level granularity** [`scalability-design.md` § 2.7] is the thing to revisit |

**Neither conclusion is reachable without this counter.**

**Conflict and replay must be separately dimensioned** [NFR25.19], because
**they look identical from the teacher's side and mean opposite things**: a
conflict means two devices disagreed; a replay means one device sent twice.
Collapsed into one number, a high value is uninterpretable — and the two call
for opposite responses, since a high replay rate is a client sync bug while a
high conflict rate is a granularity question.

**Verifier: the three counters exist, and a test exercises each without moving
the other two.** The cross-assertion is the design requirement: a test that
only checks a counter increments passes against an implementation that
increments all three.

### 3.3 Generation counted per run [NFR25.21]

**Sessions created, sessions skipped by conflict, occurrences failed** — three
values, **never collapsed into one**.

Following D3's NFR25.13: **a sustained non-zero SKIP count after the first run
of a month is NORMAL** — the conflict is the success path [BR1.3] — **while a
sustained non-zero FAILURE count is a defect.** Collapsing them produces a
number that is alarming when it should not be and silent when it should not be.

The `JobHeartbeat` row already carries counts of exactly this shape, verified
by reading `app/db/models.py`: `cycles_created`, `cycles_skipped`,
`periods_failed`. **The counts ride along on the heartbeat row**, which is what
makes them queryable without a metrics backend.

**Verifier: the counters, asserted in a test over a seeded run** — including
the zero-created case [NFR19.41].

### 3.4 Mark corrections are countable [NFR25.22]

**A rising correction rate is a finding about the mark-entry screen rather than
about the teacher.** D3 established the same instrument for payment
verification corrections [NFR25.16] and the reasoning is unchanged.

Answerable from the data with no counter at all, which is worth stating:

```sql
SELECT count(*) FROM mark WHERE superseded_by_id IS NOT NULL;
```

**Verifier: the counter, or the query above.** Either discharges it; the
supersession chain is what makes the data route available.

---

## 4. Alerting

### 4.1 The one alert D4 adds [NFR25.23, NFR26.7]

**Design statement: session generation not having run for 48 hours alerts**,
reusing the `JobHeartbeat` mechanism and the separate freshness-check command
D3 built.

**The job is registered under its OWN name, beside `FEE_GENERATION_JOB`** so
the two jobs' freshness is tracked independently [NFR1.8]. Verified by reading
`app/db/models.py`: `JobHeartbeat` is keyed by `job_name` as its primary key,
and `app/fees/commands.py` already takes `job_name` as a parameter defaulting
to `FEE_GENERATION_JOB` — **so the mechanism is parameterised and D4 adds a
name, not a table.**

**A shared name would let a healthy fee run mask a session job that has never
fired.**

#### The alert fires on the ABSENCE of success, not on failure

D3's reasoning applies here **with more force**: session generation
**self-heals**, so a job whose cron entry was never wired **looks completely
healthy** — right up to the morning a teacher opens the app and there is no
class to mark attendance against. That is BR1.1's `violation_behaviour`
reached by an operational route rather than a code one.

**The failure mode this is designed against is concrete** [NFR1.7]: the ASG
refreshes on every deploy, the instance is replaced and `user_data` re-runs, so
**a hand-added cron entry is wiped by the next routine deploy**. Nothing looks
wrong, because generation self-heals.

**Verifier: the heartbeat row and the freshness command, both covered by D3's
existing test shape.**

### 4.2 The channel [NFR25.27]

**`log.critical` on the host's standard output is this product's only alerting
mechanism.** `app/fees/commands.py` records that there is no CloudWatch alarm,
no SNS topic and no `alarm_actions` anywhere in `app/` or `infra/`, and that
the two alerting sites today are `app/auth/ceilings.py` and `app/audit/log.py`.

**D4 adds no alerting infrastructure and no recurring cost** [OC-4].

**Verifier: the `log.critical` call. Nothing automated proves the alert reaches
a person** — D3 records that as a once-performed skipped-run rehearsal in
staging, and **D4's session job rides on whatever that rehearsal established
rather than needing a second one.**

### 4.3 What does not alert

| Condition | Treatment | Why |
|---|---|---|
| A single failed occurrence in a run [NFR25.24] | **Counted, not paged** | Paging would convert the per-occurrence commit resilience of NFR19.32 into noise |
| The attendance conflict rate [NFR25.25] | **No alert** | A metric to read after the pilot, not a condition with a known-bad threshold — **a threshold set now would be invented** |
| Push delivery failure [NFR25.26] | **No alert** | Recorded as an event outcome, continuing D3's NFR25.11 |

**Verifier for the conflict-rate row: none; stated so the absence is a
decision.** This is the entry most likely to be read as an oversight, which is
why it is in the table rather than omitted.

---

## 5. SLIs and SLOs

| SLI | Target | Verifier |
|---|---|---|
| **Session-generation freshness** [NFR26.7] | hours since last success **< 48** | the freshness command's verdict |

**That is the only one D4 adds.** Three deliberate absences:

- **No SLO on attendance write latency** [NFR26.8], because the requirement it
  would measure was dropped [Q14.3; `performance-design.md` § 1]. **This is the
  entry whose absence a reader is most likely to try to fill.**
- **No SLO on the conflict rate** [NFR26.9]. The pilot measures it; V1 sets no
  target.
- **No availability SLO** [NFR18.6]. The product has set none.

### 5.1 Constraints instead of monitors [NFR26.10]

**The guarantees that would otherwise be monitored are enforced by
constraints**, and a monitor would watch a value the database cannot produce:

| Invariant | Constraint |
|---|---|
| One row per `(batch_id, date, start_time)` | `UNIQUE` on `session` |
| One live `mark` per seat per exam | the partial unique index [BR4.5] |
| One submission per `(session_id, resulting_version)` | `UNIQUE` on `attendance_submission` |

**Verifier: the constraints and their concurrency tests** [`scalability-design.md`
§ 2]. This is D3's NFR26.5 reasoning applied to three more invariants: a
constraint that cannot be violated needs no alert telling you it was.

---

## 6. Correlation and structured logging

D4 adds **no new correlation mechanism**. Every log line carries the request or
correlation id, which is the built convention, and **never a phone number, an
OTP or a token** [`team.md` Deployment].

**What D4 adds to that prohibition is § 1: never a child name, never a mark,
never a roster.**

**No distributed tracing is designed.** The NFR design guide offers a tracing
architecture; it is not applied, and the reason is a decision rather than an
omission: **this is one process on one host with one database.** A trace would
have exactly one span worth having, which the correlation id already provides.

---

## 7. What has no automated verifier

Collected, because the project's standing rule is that an obligation without a
named verifier is a wish — and that **where a verifier is manual, the sentence
saying so must be present or the obligation reads as verified**.

| Obligation | Verifier | Note |
|---|---|---|
| No child name in logs [NFR24.13] | Review | **Nothing automated checks this** |
| No mark in logs [NFR24.14] | Review | **Nothing automated checks this** |
| `composed_at` used in no decision [NFR24.20] | Review, with a grep in the checklist | **Nothing automated checks this** |
| No cleanup path for submissions [NFR24.19] | Review of the migration | **Nothing automated checks this** |
| Deploys outside classroom hours [NFR18.8] | The runbook | **Nothing automated checks this** |
| The alert reaches a person [NFR25.27] | D3's one-off staging rehearsal | **Nothing automated checks this** |
| Generation runs outside classroom hours [NFR20.30] | The cron expression, reviewed | **Nothing automated checks this** |
| Per-screen Bangla layout, 7 screens [BR7.5] | A row each in `docs/delivery/bangla-layout-check.md` | A file check, **not a screenshot test. No screenshot harness exists** |
| No latency assertion on the attendance path [NFR2.6] | Review | **The deliberate position, not a gap** |

**What IS automated on the Kotlin side** [NFR17.7]: the coverage ratchet built
at `android/coverage.gradle.kts`, whose floor in `android/coverage-floor.txt`
reads **52.54** and **moves only upward by deliberate commit**. D4's seven
screens and its queue land under it. It is listed beside the manual rows
deliberately — it is the one Kotlin-side mechanical control this unit
inherits, and `team.md`'s claim that the Kotlin coverage report is absent is
**stale**, verified by reading both files at this stage.

**On the Bangla row specifically.** `team.md` records that of the two verifiers
offered for the layout obligation — Compose screenshot tests or an explicit
per-screen manual check — **neither existed across three shipped screens**. D4
ships **seven** more. BR7.5 chooses the written per-screen check and makes a
missing row an incomplete unit, **which is a real verifier of the PROCESS; it
is not a verifier of the LAYOUT.**

**The conflict-resolution screen is the one to check hardest**: it renders
**two rosters side by side, in Bangla**, which is the densest text this unit
produces — and it is the screen a teacher reaches at the worst moment.

---

## Assumptions & Open Questions

- **The metrics backend is not specified by any unit of this product, and D4
  does not specify one.** I searched both records' `inception/` trees,
  `infra/`, and the built `app/` for Prometheus, StatsD, CloudWatch metrics or
  any metrics client, and found **none**. § 3.1 designs around that rather than
  around a pipeline that might arrive.
- **No dashboard is designed**, by this unit or any prior one. With no metrics
  backend there is nothing to put on one, and **specifying a dashboard against
  a backend that does not exist would be the empty-promise shape this record
  has been correcting.**
- **The session-generation job's name constant** is assumed to follow
  `FEE_GENERATION_JOB`'s pattern in `app/db/models.py:129`. The requirement is
  that the two jobs' freshness be tracked **independently**; the constant's
  spelling is an implementation detail.
- **The 48-hour threshold is inherited from D3's NFR25.9**, not computed here.
  It is appropriate for a daily job by the same reasoning — one missed run is
  self-healing, two consecutive misses are not — and I did not re-derive it.
- **The `JobHeartbeat` row's existing count columns are fee-shaped**
  (`cycles_created`, `cycles_skipped`, `periods_failed`). Whether the session
  job reuses those column names for its own three counts, or the schema gains
  neutral names, is an implementation question this design does not settle.
  **The requirement is that three distinct counts are recorded and that skip
  and failure are not collapsed** [NFR25.21].
- **I could not execute any test suite.** Docker is unavailable in this
  session. Every claim about built code — `JobHeartbeat`'s key and columns,
  `app/fees/commands.py`'s `job_name` parameter, the two alerting sites — is
  from **reading the file**, cited by path so it is checkable.
