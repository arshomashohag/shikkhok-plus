# Monitoring Design — D4 `teaching-and-recording`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **Two findings shape this document, and they point in opposite directions.**
>
> The first is that **D4's one alert does not currently reach anything**, not
> because the channel is weak but because the check is hardcoded to the fee
> job. That is `infrastructure-specification.md` § 3.3 and it is a defect in
> coverage, not in design.
>
> The second is about the conflict rate, which the unit exists to measure.
> **Half of it is permanently answerable from the database and half of it is
> not answerable at all without a counter**, because a refused write leaves no
> row. This document says where that counter goes, and says plainly that
> nothing reads it.

## Sources

- [upstream] `construction/teaching-and-recording/nfr-design/observability-design.md`
  — the whole file; §§ 3–4 in particular, implemented here against the real
  platform
- [upstream] `construction/teaching-and-recording/nfr-design/reliability-design.md`
  §§ 5, 8 — `AttendanceSubmission` and the generation job, the two things
  being counted
- [upstream] `construction/teaching-and-recording/nfr-design/security-design.md`
  §§ 5.4–5.5, 6 — the 409 disclosure ordering, and governance rows
- [upstream] `construction/teaching-and-recording/nfr-design/logical-components.md`
  §§ 6.3, 7 — the gaps handed forward, and the two jobs against one heartbeat
- [upstream] `construction/teaching-and-recording/nfr-design/performance-design.md`
  §§ 1.2, 2 — why there is no latency monitor; statement count as the target
- [upstream] `construction/teaching-and-recording/nfr-design/scalability-design.md`
  §§ 2.7–2.8 — session-level granularity, and two counters rather than one
- [upstream] `construction/teaching-and-recording/nfr-requirements/observability-requirements.md`
  — NFR24.13–NFR24.20, NFR25.18–NFR25.27, NFR26.7–NFR26.10
- [upstream] `construction/teaching-and-recording/functional-design/rules.md`
  — BR1.1–BR1.3, BR3.4, BR3.10, BR6.3, the rules these signals watch
- [upstream] `inception/domain-design/components.md` — the Governance section,
  whose row shape the six new tables owe
- [prior] D3's `collecting-fees/infrastructure-design/monitoring-design.md` —
  the `log.critical` finding this unit inherits unchanged
- [code] `app/fees/commands.py`, `app/db/models.py`,
  `app/governance/dispositions.py`, `infra/modules/app/user_data.sh.tftpl`,
  `infra/`, `tests/db/test_governance.py`, read 2026-10-24

---

## 1. Collection: what exists

Unchanged from D3, re-verified rather than inherited.

| Signal | Where it goes | Retained | Readable off-host |
|---|---|---|---|
| Application logs, all levels | The container's stdout | Until the instance is replaced | **No** |
| `log.critical` alert lines | The same stdout | The same | **No** |
| Provisioning failures | `/var/log/shikkhokplus-provision.log` on the instance | The same | Only by `cat` over SSM |
| Job logs | `/var/log/shikkhokplus-fee-generation.log` on the instance | The same | Only over SSM |
| `job_heartbeat` rows | **PostgreSQL** | **Indefinitely** | **Yes** |
| `attendance_submission` rows | **PostgreSQL** | **Indefinitely** | **Yes** |
| `mark` supersession chain | **PostgreSQL** | **Indefinitely** | **Yes** |

**The last three survive a deploy; the first four do not.** That distinction
organises this document exactly as it organised D3's.

**There is no metrics backend.** I searched `app/`, `infra/` and
`pyproject.toml` for Prometheus, StatsD, OpenTelemetry, a CloudWatch metrics
client, `put_metric_data`, `aws_cloudwatch_metric_alarm`, `alarm_actions` and
`aws_sns_topic`, and found none. `observability-design.md` § 3.1 reports the
same search with the same result, and this is a confirmation of it rather than
a restatement.

---

## 2. The conflict rate: half is data, half is a counter

**This is the unit's one genuinely new instrument** [NFR25.18–NFR25.20], and
getting the honest version of it written down matters more than the counters
themselves, because the interesting half is the half the database cannot hold.

### 2.1 The split

| Outcome | Writes a row? | Answerable from data later? |
|---|---|---|
| **Applied** | Yes, an `attendance_submission` row with `base_version` | **Yes, permanently** |
| **Replayed** | No second row; returns the stored result [NFR19.34] | **Partly** — the original row exists, the fact of the replay does not |
| **Conflicted** | **No row at all.** The write is refused | **No. Never** |

**`base_version` is stored precisely so the applied side survives the pilot**
[NFR25.20]. That is the load-bearing schema decision and it works: long after
any counter is lost, the submissions table still shows what was accepted.

**But a refusal writes nothing.** There is no refused-submission table, and
`observability-design.md` § 3.1 states the limit inside its own SQL comment:
the conflicts are the refused writes, which write no row, so the counter of
§ 3.2 is what makes them visible at all.

**So "the conflict rate is answerable from the data" is true of the
denominator and false of the numerator.** A reader who takes the stored-data
route alone can count how many submissions applied and learn nothing about how
many were turned away — and the ratio is the entire question the unit was
built to answer.

### 2.2 Where the counter goes, and what reads it

**The question D3 answered by making its signal a database row rather than a
log line, asked again here.** D3's answer worked because `job_heartbeat` is a
row: it survives instance replacement, and a row can be read by anything with
database access.

Three shapes are available for the refusal counter. They are not equally
costly and they are not equally honest.

| Option | What it is | Survives a deploy? | Read by |
|---|---|---|---|
| **A. A log line at the refusal site** | `log.info` with an outcome field | **No.** Destroyed on the next deploy | **Nothing** |
| **B. A counter row, D3's shape** | A small table or a `job_heartbeat`-style row incremented per refusal | **Yes** | A query a person runs |
| **C. A refused-submission row** | A row per refusal carrying `base_version` and `current_version` | **Yes**, and it is the richest | A query a person runs |

**Option A is what "a counter" means by default in a product with no metrics
backend, and it is the one that answers nothing.** The pilot's whole purpose is
a number read *after* the pilot; a signal destroyed by every deploy cannot
produce one. Three units have deployed in this record; a conflict logged in
week one of a pilot would not survive to week three.

**Option C deserves a caution that is not obvious.** A refused-submission row
would be the most informative artifact and it carries a privacy cost the
applied rows do not: the refused payload **is a roster**, and
`observability-design.md` § 1.3 forbids a roster in any log or diagnostic.
A refused row storing only `(session_id, base_version, current_version,
submitted_by, timestamp)` and **never the roster itself** is compatible with
that rule; a row storing the rejected payload "for debugging" is not. **If C is
chosen, that boundary is the design, not a detail.**

**This document does not choose.** It states the consequence of each, and it
states the one thing that must not happen: **describing the conflict rate as
observable while implementing option A.** That is the project's rule about
unverified obligations [project.md], applied to a metric rather than a test.

### 2.3 The honest V1 position, if nothing is built

**If the human's answer is "a log line is accepted for V1", the sentence this
document must carry is: nothing reads it, and the conflict rate will not be
answerable after the pilot.** The applied count remains answerable forever; the
refusal count does not exist. That is a defensible choice for a closed-testing
pilot with a handful of teachers — a conflict is a visible event to the teacher
who hits it, and they can be asked — but it is a choice to measure by asking
people rather than by querying, and it should be made knowing that.

**Verifier: none, under option A.** Under B or C, the verifier is a test that
exercises each of the three outcomes without moving the other two
[observability § 3.2], which is the cross-assertion the NFR design requires
because a test checking only that a counter increments passes against an
implementation that increments all three.

---

## 3. Metrics and KPIs

**Counts only, never the values.** A metric labelled by child name, mark or
roster is that data in a metrics store [NFR24.13, NFR24.14, NFR24.15].

| Metric | Source | Threshold | Why it matters |
|---|---|---|---|
| Hours since last successful session generation [NFR26.7] | `job_heartbeat` under D4's job name | **48h** | The only property that degrades without raising an error |
| Sessions created per run [NFR25.21] | The run's heartbeat row | None | Zero is normal between schedule changes |
| Sessions skipped by conflict [NFR25.21] | The same row | None | **Normal and expected** — the conflict is the success path [BR1.3] |
| Occurrences failed [NFR25.21] | The same row | None | **A rising count is a defect**, unlike the row above it |
| Attendance submissions applied [NFR25.18] | `count(*)` over `attendance_submission` | None | The denominator of the conflict rate [§ 2] |
| Attendance submissions conflicted [NFR25.18, NFR25.19] | **A counter — § 2.2** | None | **The numerator, and it exists nowhere today** |
| Attendance submissions replayed [NFR25.19] | **A counter — § 2.2** | None | **Opposite meaning to a conflict** — § 3.1 |
| Mark corrections [NFR25.22] | `count(*) FROM mark WHERE superseded_by_id IS NOT NULL` | None | A finding about the mark-entry screen, not about the teacher |

**Only the heartbeat counts and the two SQL rows need no new mechanism.** The
conflict and replay counters are the two entries in this table that do not
exist in any form today.

### 3.1 Conflict and replay must never be one number

`observability-design.md` § 3.2 is emphatic and the reason is worth repeating
where someone reading a dashboard will see it: **they look identical from the
teacher's side and mean opposite things.**

| Signal | What happened | What a high rate calls for |
|---|---|---|
| **Conflict** | Two devices disagreed about one session | Revisit session-level granularity [scalability § 2.7] |
| **Replay** | One device sent the same write twice | **A client sync bug** |

Collapsed into one number, a high value is uninterpretable and the two
responses are opposite. **This is the cheapest mistake to make and the most
expensive to discover late**, because the single number looks like a working
instrument.

### 3.2 Skipped and failed must never be one number either

The same rule, one level down, inherited from D3's NFR25.13 and restated by
NFR25.21: a **sustained non-zero skip count is normal** — the conflict is the
success path when a session already exists [BR1.3] — while a **sustained
non-zero failure count is a defect**. Collapsing them produces a number that is
alarming when it should not be and silent when it should not be.

**The `job_heartbeat` row already carries three counts of this shape**,
verified by reading `app/db/models.py`: `cycles_created`, `cycles_skipped`,
`periods_failed`. **D4 reuses the columns rather than adding a table**, which
is what makes its counts queryable with no new mechanism.

---

## 4. Alerts

| Alert | Condition | Severity | Routes to |
|---|---|---|---|
| **Session generation has not succeeded** [NFR25.23, NFR26.7] | **No heartbeat row under D4's job name, or staleness ≥ 48h** | **Critical** | **`log.critical` — and today the check never runs for this job [§ 4.1]** |
| A single failed occurrence in a run [NFR25.24] | Any one failure in an otherwise healthy run | **Not an alert** | A counter on the heartbeat row |
| The attendance conflict rate [NFR25.25] | — | **Not an alert** | **A metric read after the pilot** — § 4.3 |
| Push delivery failure [NFR25.26] | FCM returns a failure | **Not an alert** | An event outcome, continuing D3's NFR25.11 |

### 4.1 The alert must be registered with the checker, not only with the table

**D4's alert has two halves and only one of them is designed upstream.**

| Half | State |
|---|---|
| The job writes a heartbeat row under its own name [NFR1.8] | **Designed and straightforward** — `stamp_heartbeat` already takes `job_name` |
| **Something reads that row and alerts on staleness** | **Does not happen.** The checker is hardcoded to the fee job |

`infrastructure-specification.md` § 3.3 has the evidence:
`main_check_freshness()` calls `check_generation_freshness(session)` with no
argument and logs `job_name: FEE_GENERATION_JOB`, and the host-side service
invokes it with no job argument. **Writing the row changes nothing on its
own.**

**The query must be written as "alert unless a row exists and is fresh."**
This is `check_generation_freshness`'s built shape and the easiest thing here
to get wrong: a check reading "if staleness > 48 hours then alert" treats
**zero rows** — the job never ran at all — as healthy, because the comparison
is never evaluated. **That is exactly the never-wired-cron failure**, and under
a new job name zero rows is the starting state.

**Verifier: a test over all three branches — no row, stale row, fresh row —
under a job name that is not the fee job.** The last clause is the part that
catches this unit's specific failure: a test using the default job name passes
against a checker that can only ever see the default job name.

**DECIDED 2026-10-25 by the human: the checker enumerates every registered
job** (spec § 3.3, option B). The three-branch verifier above is unchanged and
gains a fourth obligation: **a test asserting that a second job's stale row
alerts, with the fee job fresh**. That is the assertion that distinguishes a
checker which enumerates from one which checks only the first row it finds —
and it is the one a test written against a single job cannot make.

Two consequences for this document:
- The per-job **threshold stays per-job**. Enumerating the jobs does not mean
  one staleness window for all of them; § 4.3's open question about whether 48
  hours suits session generation is untouched by this decision and still open.
- The alert line **names the stale job**. `main_check_freshness()`'s hardcoded
  `job_name: FEE_GENERATION_JOB` log field becomes the row's own name, or the
  only alerting mechanism this product has would report a session-job failure
  under the fee job's name.

### 4.2 The channel, unchanged and still unproven

**`log.critical` on the host's stdout is this product's only alerting
mechanism** [NFR25.27]. D3's finding stands in full and D4 adds nothing to it:
no CloudWatch alarm, no SNS topic, no log shipping, and the instance is
destroyed on every deploy.

**Verifier: the `log.critical` call. Nothing automated proves the alert reaches
a person.** D3 records that as a once-performed skipped-run rehearsal in
staging, and **D4's session job rides on whatever that rehearsal established
rather than needing a second one** [observability § 4.2] — with one caveat that
is this unit's own: **a rehearsal performed against the fee job proves nothing
about the session job while § 4.1 is open.** The delivery path is shared; the
coverage is not.

### 4.3 The conflict rate is deliberately not an alert

**A threshold set now would be invented** [NFR25.25]. Nobody has measured a
conflict rate in this product, there is no known-bad value, and an alert
firing at a number somebody guessed trains its reader to ignore the channel
that also carries NFR25.23.

**Verifier: none; stated so the absence reads as a decision.** This is the row
most likely to be mistaken for an oversight, which is why it is in the table
rather than omitted.

---

## 5. SLIs and SLOs

| SLI | SLO target | Measurement window | Measured by |
|---|---|---|---|
| Session generation freshness [NFR26.7] | **Under 48 hours** | Continuous | The heartbeat query — the alert threshold *is* the target |
| One `attendance` row per `(session, enrollment)` [NFR26.5-shape] | Always | Always | **A unique constraint, not a monitor** |
| One submission per `(account, client_mutation_id)` [NFR19.33] | Always | Always | **A unique constraint, not a monitor** |
| Version increments by exactly one [BR3.4] | Always | Always | **A unique constraint on `(session_id, resulting_version)`** |
| Mid-class attendance speed [PU-3.6] | **No V1 target** | — | **Nothing. See § 5.2** |
| Attendance conflict rate [NFR26.9] | **No target in V1** | The pilot | § 2 |

### 5.1 Constraints instead of monitors [NFR26.10]

**Three of the six rows are database constraints and are listed here precisely
so they are not later re-invented as dashboard panels.** A production threshold
on an invariant the database enforces would be an admission it might not hold,
and this is the specific way a team ends up monitoring a guarantee instead of
relying on it.

**No SLO percentages are invented for V1.** A 99.x% target set now would be a
number nobody derived from anything.

### 5.2 There is no latency monitor for the attendance path, and that is settled

**PU-3.6 carries no V1 obligation** — it was dropped, and
`performance-design.md` § 1.2 records the absence as a decision rather than an
omission. **This document designs no timing budget, no Macrobenchmark and no
latency SLI for the attendance path**, and it specifies no correctness test
standing in for one, which the project forbids outright [project.md].

**One stale cross-reference, flagged rather than inherited**: `team.md` still
assigns a Macrobenchmark harness to D5 under its Walking Skeleton table, which
predates the decision. **D4 does not inherit it** and does not design against
it. The structural property that replaces it is statement count
[`performance-design.md` § 2], which is verified in the test suite rather than
monitored in production.

---

## 6. Logs and tracing

| Facet | Design |
|---|---|
| Aggregation | **None.** Container stdout, destroyed on each deploy [§ 1] |
| Structure | Existing structured logs with a request/correlation id [NFR24.8] |
| Tracing | **None.** One host, a USD 50 ceiling — the correlation id is the tracing this scale supports |
| Dashboards | **None.** The metrics in § 3 are queries, run by a person |

### 6.1 What must never be logged

D4 is the unit that makes "children's data" literal, and its four prohibitions
are stronger than any before it.

| Rule | Value | Why it is the one a developer would reach for |
|---|---|---|
| NFR24.13 | **No child name, ever** | The natural debug line for an attendance failure names the student |
| NFR24.14 | **No mark, ever** | A mark is an academic record about a child; a "value out of range" log is the obvious place it lands |
| NFR24.15, NFR24.16 | **No roster, and the conflict path specifically** | The conflict payload **is** a roster, and a diagnostic logging "what was rejected" logs it in full |
| NFR24.17 | **No traceback, no verbatim database error** | A constraint violation message carries column values |

**NFR24.15 is listed with its conflict clause because that is where it will
actually be violated.** A developer debugging a refused submission wants to see
the submitted roster beside the current one. That diff is the single most
useful debugging artifact in this unit and it is a class register of children
with their attendance — **it is forbidden, and the counter of § 2.2 is the
sanctioned substitute.** The two facts belong in the same sentence, because
offering the prohibition without the substitute is how the prohibition gets
worked around.

**The structural guarantee that helps is already built**: `app/audit/log.py`'s
row dataclass has no free-form string field but `correlation_id`, asserted by a
test — because a `message` or `note` column is where a name eventually lands,
added by someone debugging in good faith. **D4 must not weaken it.**

**Verifier: none for the new call sites.** I searched `tests/` for a scanner
asserting the absence of these values in emitted log lines and found none.
NFR24.13–NFR24.17 are **review-enforced** for D4's new code, which is weaker
than the structural guarantee the audit row carries, and weaker than this
unit's content warrants. Stated rather than glossed.

### 6.2 The 409's disclosure is an authorization property, not a logging one

`security-design.md` §§ 5.4–5.5 establish that `ATTENDANCE_VERSION_CONFLICT`
carries `current_state` — **which is the roster** — in `error.details`, and is
therefore refused only **after** authorization [NFR14.64, BR3.10].

**It appears in this document for one reason**: the same roster that must not
reach an unauthorized caller must not reach a log line either, and the two
controls are independent. **A correct authorization order with a logging
statement at the raise site discloses the roster to whoever reads the logs**,
which is a narrower audience and a longer retention than the error response.

**Verifier for the authorization half: the probe at `security-design.md`
§ 5.4, run for both a matching and a non-matching version. Verifier for the
logging half: review.** The built oracle test
(`test_exactly_one_resource_refusal_code_is_registered`) does not cover either,
because the code is a 409 `ConflictError` and never enters `AUTH_403_CODES`.

---

## 7. Retention and governance

| Record | Disposition | State |
|---|---|---|
| `session`, `attendance`, `exam`, `mark`, `announcement` | **`RETAIN_WITH_BASIS` is the expected case** — the teacher's business record and the child's personal data at once | **D4 must write five rows** |
| `attendance_submission` | **Takes `attendance`'s**, per security § 6.2 | **D4 must write the sixth** |
| `job_heartbeat` | Declared at D3 | Unchanged; D4 adds a row, not a table |
| Container and job logs | Destroyed on instance replacement | Not a policy, a side effect |

**Six entries, counted against the 19 in `app/governance/dispositions.py`
today, giving 25 after D4** — the same count `security-design.md` § 6.1
reached, which I confirmed by listing the file's keys rather than trusting it.

**The `basis` is the sentence the generated privacy policy is written from**,
so it is prose a parent could read, not a code comment.
`test_every_disposition_states_a_basis` enforces a 20-character floor, and
`test_no_disposition_names_a_table_that_does_not_exist` catches the failure
mode that six-tables-in-one-migration actually produces: a typo'd name
yielding a stale entry rather than a missing one.

**Verifier: `tests/db/test_governance.py`, both directions, already built.**

---

## 8. What has no automated verifier

Stated in one place, because a manual check described without this sentence
reads, to the next person, as a verifier.

| Obligation | Verifier | Automated? |
|---|---|---|
| **NFR25.23's alert reaches a person** | **Nothing**, and today **nothing reads D4's heartbeat at all** [§ 4.1] | **No** |
| The freshness query is correct across its three branches **under a non-default job name** | A unit test against a real database | **Yes**, once written |
| **The conflict rate is answerable after the pilot** | **Depends entirely on § 2.2.** Under option A, nothing | **No, as things stand** |
| The three submission counters move independently | A test exercising each without moving the other two | **Yes**, once the counters exist |
| NFR24.13–NFR24.17: no name, mark, roster or traceback in a log line | Review of D4's new call sites | **No** |
| The conflict's roster does not reach an unauthorized caller | The dual-version probe [security § 5.4] | **Yes** |
| Six governance rows exist and name real tables | `tests/db/test_governance.py` | **Yes** — already built |
| The six tables are granted to the restricted role | `test_the_restricted_role_can_read_every_live_table` | **Yes** — already built |
| A registered job name has a cron entry | **Nothing.** Review of the Terraform diff | **No** |
| Seven screens hold their layout at the longest Bangla string [NFR17.8] | **A written per-screen check.** No screenshot harness exists | **No** |

**The first and third rows are the ones to act on.** Both are obligations whose
mechanism was assumed to exist: the first because a parameterised function was
read as a parameterised command, the second because stored data was read as
answering a question half of which it cannot reach.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to container stdout with no new sink. D4
  adds no observability infrastructure and no recurring cost [NFR6.57, OC-4].
- **Assumed**: the metrics in § 3 are read as queries by a person rather than
  scraped, which is what Phase 1 supports and what costs nothing.
- **Assumed**: D4's job reuses `job_heartbeat`'s three count columns rather
  than adding its own, which is what `app/db/models.py` makes available and
  what keeps the two jobs symmetrical.
- **Decided 2026-10-25, no longer open**: how the freshness check learns about
  D4's job name [§ 4.1, spec § 3.3]. The human chose to enumerate every
  registered job, so D4's alert fires and D5's and D6's will too without a
  further `user_data` change.
- **Open, and the human's**: where the conflict and replay counters live
  [§ 2.2]. Option A is the default outcome of doing nothing and it answers
  nothing after the pilot; if it is chosen, § 2.3 is the sentence that must be
  written down with it.
- **Open, and the human's**: whether 48 hours is right for session generation.
  Inherited from the fee job's derivation of two missed daily runs; a class
  missed in the morning is a sharper consequence than a fee not raised, so a
  shorter window is defensible here than there.
- **Open, and D6's**: the retention periods behind the six dispositions, which
  this unit declares and D6's deletion work exercises.
