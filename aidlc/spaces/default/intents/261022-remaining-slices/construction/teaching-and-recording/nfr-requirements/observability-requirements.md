# Observability Requirements — D4 `teaching-and-recording`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 is the unit where a careless log line becomes a child-safety incident.**
> Everything this unit stores is a record of a named child: where they were on
> a given afternoon, and what they scored. § 1 is therefore the longest section
> and is stated as prohibitions rather than as guidance.
>
> **The second theme is that the pilot needs to answer one question this design
> cannot answer in advance: how often does a conflict actually happen?** The
> whole unit is built around refuse-on-conflict, and nobody knows the conflict
> rate. § 3 specifies the metric that answers it, and it is the one genuinely
> new instrument D4 adds.

> **`NFRx.y` IDs are GLOBAL across units.** D4's new IDs start above the
> high-water mark each base reached after D3. A bare `NFR24.8`, `NFR25.9` or
> `NFR26.3` below is a **citation** of an earlier unit's requirement, never an
> ID defined here.

## Sources

- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  §§ 2.1, 3.2, 3.6, 4.1
- [upstream] `construction/teaching-and-recording/functional-design/rules.md` —
  BR1.3, BR3.4, BR3.6, BR3.8, BR4.4, BR5.3, BR6.2, BR7.1
- [upstream] `construction/teaching-and-recording/functional-design/entities.md` —
  `AttendanceSubmission` (`base_version`, `composed_at`), `Mark`
- [prior] `261016-.../inception/requirements-analysis/requirements.md` — NFR14,
  NFR5.1
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.8
- [code] `app/audit/log.py`, `app/fees/commands.py`, `app/db/models.py`
  (`JobHeartbeat`, `FEE_GENERATION_JOB`) — read 2026-10-24

---

## 1. What must never be logged

The standing rules hold and are not restated. What follows is what **D4 adds**
to the prohibited set, and each is a thing a reasonable debugging session
reaches for.

**NFR24.13** — **No student or child name reaches any log line, at any level.**
D4 is the first unit whose core operation is a list of named children.
**Verifier: review, plus the existing structured-logging convention that log
lines carry the correlation id and identifiers rather than prose.** There is no
automated scanner for this and saying so plainly is the requirement's honest
half.

**NFR24.14** — **No mark, and no exam result of any kind, reaches a log line.**
Not in an error, not at debug level, not in a validation message. A mark is the
most sensitive single datum this product holds about a child. **Verifier:
review; the same absence of an automated check applies.**

**NFR24.15** — **No attendance roster reaches a log line**, and in particular
the `ATTENDANCE_VERSION_CONFLICT` path must not log `current_state` — which
*is* the roster — when it logs the conflict. **Verifier: a test asserting the
conflict log record carries the session id, the two version numbers and the
account id, and no entries collection.**

This is the specific hazard in this unit. The conflict is interesting, so it
will be logged; the error body already carries the roster; and the obvious
implementation logs the error body. The requirement is that it logs the
*metadata* and not the *payload*.

**NFR24.16** — **A `client_mutation_id` may be logged; a `composed_at` may be
logged; the roster entries may not.** Stated as the positive half of NFR24.15
so the conflict path remains debuggable. **Verifier: the same test.**

**NFR24.17** — An exception traceback never reaches a client, and a database
error on these tables is never returned verbatim — a unique-violation message
on `attendance` names the session and enrollment ids. **Verifier: the existing
exception-handler contract test.**

---

## 2. The audit trail is the data, not a parallel log

**NFR24.18** — Every attendance row records **who marked it and when**
(`recorded_by_account_id`, `recorded_at`), and every mark records the same
[entities.md, FR9.2]. The correction history is the **supersession chain** for
marks and the **submission sequence** for attendance — not a parallel audit
log. **Verifier: a test asserting a correction leaves the prior state
readable.**

The reasoning is D3's and transfers: a parallel audit log is a second record
that drifts from the first. Here the data *is* the trail.

**NFR24.19** — `attendance_submission` rows are **never deleted**, because the
sequence of submissions for a session is the attendance correction history
[entities.md]. **Verifier: review of the migration for the absence of any
cleanup path.**

**NFR24.20** — `composed_at` is recorded and **used in no decision** — it is a
device clock, and a device clock in a conflict rule would let a wrong phone
time silently reorder two teachers' writes [entities.md]. It exists for the
pilot's queue-latency question only. **Verifier: a code-level assertion that
`composed_at` appears in no comparison, orderings included — checkable by
review, and worth a grep in the review checklist rather than left to memory.**

---

## 3. Metrics — the conflict rate is the one that matters

**NFR25.18** — **Attendance submissions are counted by outcome**: applied,
conflicted, and replayed. **Verifier: the counters exist and are asserted in a
test.**

This is the unit's one genuinely new instrument, and the reason is that **D4
is built entirely around a hypothesis nobody has measured**: that conflicts are
rare enough for refuse-and-re-apply to be the right trade, and common enough to
be worth building for. Bolt 4's confidence hypothesis says so in as many words.
If the conflict rate in the pilot turns out to be near zero, the
conflict-resolution screen was cheap insurance; if it is high, the
session-level granularity decision [NFR6.48] is the thing to revisit. **Neither
conclusion is reachable without this counter.**

**NFR25.19** — The conflict counter is dimensioned to distinguish a **version
conflict** from a **replay**, because they look identical from the teacher's
side and mean opposite things: a conflict means two devices disagreed, a replay
means one device sent twice. **Verifier: the two counters are separate, and a
test exercises each without moving the other.**

**NFR25.20** — `base_version` is stored on every submission precisely so the
conflict rate is **answerable from data** after the pilot rather than only from
counters sampled at the time [entities.md]. **Verifier: the column's presence
and a test asserting it is written.**

**NFR25.21** — Session generation is counted per run: **sessions created,
sessions skipped by conflict, occurrences failed**. **Verifier: the counters,
asserted in a test over a seeded run.** Following D3's NFR25.13, a sustained
non-zero *skip* count after the first run of a month is normal, while a
sustained non-zero *failure* count is a defect — and the two must not be
collapsed into one number.

**NFR25.22** — Mark corrections are countable. A rising correction rate is a
finding about the mark-entry screen rather than about the teacher.
**Verifier: the counter.** D3 established the same instrument for payment
verification corrections [NFR25.16] and the reasoning is unchanged.

---

## 4. Alerting

**NFR25.23** — **Session generation not having run for 48 hours alerts**,
reusing the `JobHeartbeat` mechanism and the separate freshness-check command
D3 built [`app/fees/commands.py`, NFR25.9]. The job is registered under its own
name, beside `FEE_GENERATION_JOB`, so the two jobs' freshness is tracked
independently. **Verifier: the heartbeat row and the freshness command, both
covered by D3's existing test shape.**

The alert fires on the **absence of success**, not on failure, and D3's
reasoning applies with more force here: session generation **self-heals**, so
a job whose cron entry was never wired looks completely healthy — right up to
the morning a teacher opens the app and there is no class to mark attendance
against. That is BR1.1's `violation_behaviour` reached by an operational route
rather than a code one.

**NFR25.27** — The alert channel is `log.critical` on the host's standard
output, which is this product's only alerting mechanism: `app/fees/commands.py`
records that there is no CloudWatch alarm, no SNS topic and no `alarm_actions`
anywhere in `app/` or `infra/`, and that the two alerting sites today are
`app/auth/ceilings.py` and `app/audit/log.py`. D4 adds no alerting
infrastructure and no recurring cost. **Verifier: the `log.critical` call.
Nothing automated proves the alert reaches a person** — D3 records that as a
once-performed skipped-run rehearsal in staging, and D4's session job rides on
whatever that rehearsal established rather than needing a second one.

**NFR25.24** — A **single failed occurrence** within a run is a counted metric,
not a page [NFR25.21, following D3's NFR25.10]. Paging on it would convert the
per-occurrence commit resilience of NFR19.32 into noise.

**NFR25.25** — **No alert is defined on the attendance conflict rate.** It is a
metric to read after the pilot, not a condition with a known-bad threshold —
and a threshold set now would be invented. **Verifier: none; stated so the
absence is a decision.**

**NFR25.26** — D4 adds no alert on push delivery, continuing D3's NFR25.11: a
push failure is recorded as an event outcome and does not alert.

---

## 5. SLIs and SLOs

**NFR26.7** — The one production SLI D4 adds is **session-generation
freshness**: hours since the last successful run, with a threshold of under 48
[NFR25.23]. **Verifier: the freshness command's verdict.**

**NFR26.8** — **No SLO is set on attendance write latency**, because the
requirement it would measure was dropped [BR7.4, Q14.3; see
`performance-requirements.md` § 1]. **Verifier: none — and this is the entry
whose absence a reader is most likely to try to fill.**

**NFR26.9** — **No SLO is set on the conflict rate** [NFR25.25]. The pilot
measures it; V1 sets no target.

**NFR26.10** — The guarantees that would otherwise be monitored are instead
**enforced by constraints**, and a monitor would watch a value the database
cannot produce: exactly one row per `(batch_id, date, start_time)`, exactly one
live `mark` per seat per exam, and exactly one submission per
`(session_id, resulting_version)`. **Verifier: the constraints and their
concurrency tests.** This is D3's NFR26.5 reasoning applied to three more
invariants.

---

## 6. What has no automated verifier

Collected, because the project's standing rule is that an obligation without a
named verifier is a wish — and that where a verifier is manual, the sentence
saying so must be present or the obligation reads as verified.

| Obligation | Verifier | Note |
|---|---|---|
| No child name in logs [NFR24.13] | Review | **Nothing automated checks this.** |
| No mark in logs [NFR24.14] | Review | **Nothing automated checks this.** |
| `composed_at` used in no decision [NFR24.20] | Review, with a grep in the checklist | **Nothing automated checks this.** |
| Deploys outside classroom hours [NFR18.8] | The runbook | **Nothing automated checks this.** |
| Per-screen Bangla layout, 7 screens [BR7.5] | A row each in `docs/delivery/bangla-layout-check.md` | A file check, not a screenshot test. **No screenshot harness exists.** |

**On the last row specifically.** `team.md` records that of the two verifiers
offered for the Bangla layout obligation — Compose screenshot tests or an
explicit per-screen manual check — neither existed across three shipped
screens. D4 ships **seven** more. BR7.5 chooses the written per-screen check
and makes a missing row an incomplete unit, which is a real verifier of the
*process*; it is not a verifier of the *layout*. **The conflict-resolution
screen is the one to check hardest**: it renders two rosters side by side, in
Bangla, which is the densest text this unit produces.

---

## Assumptions & Open Questions

- **The metrics backend is not specified by any unit of this product, and D4
  does not specify one.** I searched both records' `inception/` trees,
  `infra/`, and the built `app/` for Prometheus, StatsD, CloudWatch metrics or
  any metrics client, and found **none** — the observability surface today is
  structured logs plus the `JobHeartbeat` row. The counters NFR25.18 through
  NFR25.22 are therefore stated as **required facts to be countable**, and
  whether they are emitted as metrics or derived by querying
  `attendance_submission` is left to implementation. NFR25.20 exists so the
  conflict rate is answerable **from the data** even if no metrics pipeline is
  ever built, which is the outcome I would bet on for V1.
- **The session-generation job's name constant** is assumed to follow
  `FEE_GENERATION_JOB`'s pattern in `app/db/models.py:129`. The requirement is
  that the two jobs' freshness be tracked **independently**; the constant's
  spelling is an implementation detail.
- **No dashboard is specified**, by this unit or any prior one. With no metrics
  backend there is nothing to put on one, and specifying a dashboard against a
  backend that does not exist would be the empty-promise shape this record has
  been correcting.
