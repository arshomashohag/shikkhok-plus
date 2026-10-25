# Observability Design — D3 `collecting-fees`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **One mechanism carries this file: the absence-of-success alert.** D3 is
> the first thing in this product that acts without a user, and the failure
> that matters is not a job that fails loudly — it is a job that **stops
> existing**. Self-healing is what makes that silence invisible: the system
> looks healthy right up to the moment someone notices nobody has been billed
> since March.
>
> Everything else here is a restatement of a rule the product already holds,
> or a refusal to build a monitor for something a constraint makes impossible.

## Sources

- [upstream] `construction/collecting-fees/nfr-requirements/observability-requirements.md`
  — NFR24.5–NFR24.12, NFR25.8–NFR25.17, NFR26.3–NFR26.6
- [upstream] `construction/collecting-fees/nfr-requirements/reliability-requirements.md`
  — NFR19.8, NFR19.10, NFR19.22, NFR19.27, the failure modes this file watches for
- [upstream] `construction/collecting-fees/nfr-requirements/tech-stack-decisions.md`
  — § 2, the two scheduler options this design holds across
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3, 5.5, 9
- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR1.3,
  BR1.4, BR2.4, BR3.3, BR5.6, BR5.7, BR7.1, BR7.2
- [upstream] `construction/collecting-fees/functional-design/entities.md` —
  `LedgerEntry`, `ReminderEvent`
- [prior] `261016-shikhokplus-tuition-app/inception/contract-design/contract-summary.md`
  § G — OQ-1
- [code] `app/audit/log.py:118-140`, `app/auth/ceilings.py:226`,
  `app/api/health.py`, `app/contract/privacy.py:55-78`,
  `.github/workflows/deploy.yml:352-410`, `infra/modules/app/main.tf:323-335`,
  read 2026-10-23

---

## 1. The absence-of-success alert [NFR25.9]

**This is the most important mechanism in the unit**, and the requirement is
explicit that a run-failure alert cannot deliver it: a run-failure alert
monitors a job that is *running*. The alert must fire on **absence of
success**.

### 1.1 What records a successful run

A single row, updated in place, written **by the job** as its last action:

```
job_heartbeat
  job_name          text   PRIMARY KEY     -- 'fee_cycle_generation'
  last_success_at   timestamptz NOT NULL
  cycles_created    integer NOT NULL
  cycles_skipped    integer NOT NULL
  periods_failed    integer NOT NULL
```

Written as an upsert on `job_name`, in its **own transaction after the run's
last enrollment-period has committed** — never inside one of them, because a
run that generated 2,900 of 3,000 enrollment-periods did succeed at the 2,900
and its heartbeat must not roll back with the 2,901st.

Four design properties, each of which answers a specific way this could be
built uselessly:

| Property | Why |
|---|---|
| **Written by the job, not by the scheduler** | A scheduler that fires a command which immediately crashes would still stamp a timer-level heartbeat. This row means *the work ran*, not *a timer fired* |
| **One row, updated in place** | The question is "when did this last succeed", which is a single value. An append-only run log would answer the same question and grow unboundedly for a value only ever read as its maximum |
| **The counts ride along** | NFR25.13's three per-run metrics are already in hand at the moment the row is written, so they cost nothing extra and are queryable without a metrics backend |
| **It is a table, not a file and not process memory** | The instance is replaced on every deploy. A file on the host or a counter in a worker is erased by exactly the event § 1.3 exists to detect |

### 1.1a A run that finds nothing due still writes the row

**This is the case that would otherwise make the alert useless, and it is the
common case rather than the edge.** Generation is monthly, so on most days of
most months there is no enrollment-period to create: a run starts, finds
nothing due, and ends. If the heartbeat were written only when
`cycles_created > 0`, the row would stop advancing for up to a month at a
time during correct operation, the 48-hour alert would fire constantly, and
an operator would mute it — reaching the exact outcome § 1.3 describes, by
the opposite route.

So the write is unconditional on the run's *outcome* and conditional only on
its *completion*: the job reaching its last enrollment-period without an
unhandled error writes the row, with `cycles_created = 0` where that is the
honest count. **"Nothing was due" and "nothing ran" are different facts and
the row distinguishes them** — the first advances `last_success_at` with a
zero count, the second advances nothing at all.

The counts are what carry the difference to a reader. A string of days at
`cycles_created = 0` around the start of a month is a signal worth looking
at; the same string mid-month is simply correct. That interpretation is not
automated and this design does not claim it is — the alert fires on
staleness alone [§ 1.2], and the counts are for the person who then looks.

**It is not on `/health`.** `app/api/health.py` is public, one of the
`PUBLIC_ROUTES`, and its model sets `extra="forbid"` precisely so that
"every field added here is information disclosed" stays a deliberate edit.
Hours-since-last-billing-run is operational detail about a teacher's business,
and the health endpoint is the wrong place for it. The freshness SLI is read
from the table, not from a public endpoint.

### 1.2 What queries it

```sql
SELECT now() - last_success_at AS staleness
  FROM job_heartbeat
 WHERE job_name = 'fee_cycle_generation'
```

**Three results, three meanings, and the third is the one that matters:**

| Result | Meaning | Action |
|---|---|---|
| `staleness < 48h` | Healthy | None |
| `staleness >= 48h` | The job ran before and has stopped | **Alert** |
| **No row at all** | The job has **never** run since this table existed | **Alert** — see below |

**The no-row case must alert, and it is the one a naive query silently
swallows.** `SELECT ... WHERE job_name = ...` returning zero rows is falsy in
most shapes a developer would write, so a check reading "if staleness > 48
hours then alert" treats *never ran* as *fine*. That is precisely the
scheduler-never-wired failure. The check is therefore written as **"alert
unless a row exists and is fresh"**, not "alert if a row is stale".

### 1.3 The two silences it must detect

| Silence | Likelihood | Why the heartbeat catches it |
|---|---|---|
| **The scheduler was never wired up** | Lower — it is a build-time omission | No row, ever. § 1.2's no-row branch |
| **A cron entry wiped by a deploy** | **Higher**, and it is an infrastructure mistake rather than an application one | The row exists and stops advancing. Staleness crosses 48h two days later |

**The second is the likelier one and deserves its own sentence.** The instance
is **replaced on every deploy**: `deploy.yml`'s rollout step refreshes the ASG
so the new instance re-runs `user_data`, deliberately — "a refresh exercises
the same path a replacement takes after a failure." A cron entry added by hand
over SSM therefore survives until the next deploy and no longer. **Nothing
fails.** The timer simply stops existing, and the self-healing job that would
have caught up is the thing that is no longer running.

This is why the scheduling mechanism must be provisioned by
`user_data.sh.tftpl` rather than by an operator action if the cron option is
chosen [tech-stack § 2], and **why this alert is the backstop for an
infrastructure mistake as much as for an application one.**

### 1.4 What fires it

**The existing alert channel, which is `log.critical`.** I searched `app/`
and `infra/` for a CloudWatch metric alarm, an SNS topic or any
`alarm_actions` and found none; the product's two alerting sites today are
`app/auth/ceilings.py:226` and `app/audit/log.py:130`, both `log.critical` on
the host's standard output. D3 adds no alerting infrastructure and no
recurring cost [NFR7.6].

So the check is **a second management command** — `check-generation-freshness`
— that runs § 1.2's query and emits `log.critical` when the answer is "no row,
or stale". It is a separate command from the job for one reason:

> **A freshness check that runs only when the job runs is circular.** If the
> job is not running, neither is its own self-check. The check must be
> triggered by something other than the thing it is checking.

**This is the design's one genuine gap and it is named rather than
papered over.** The freshness check needs a trigger, and the only triggers
available are the same two the job itself has. If both the job and its check
are wired to the same wiped cron, both go silent together and the alert never
fires. Three options, none of which this design picks, because the scheduler
choice is the human's:

| Trigger for the check | Catches a wiped cron? |
|---|---|
| The same cron mechanism as the job | **No** — both die together |
| In-process in the API container, hourly | **Yes** — the API container is what the deploy replaces *and restarts*, so the check comes back even when a host cron entry does not |
| Externally, from the CI schedule or a person | **Yes**, and it is outside the host entirely |

**The second row is a real finding**: if the human chooses in-process
scheduling for the job, the job and the check share a lifecycle and the
cron-wipe failure cannot occur in the first place. If the human chooses cron,
then **the check should not also be cron** — it should be in-process or
external, so the two do not share a failure mode. That is the one piece of
the scheduler decision this design can usefully constrain without making it.

### 1.5 The verifier, stated plainly

| Obligation | Verifier | Automated? |
|---|---|---|
| The query is right — no row and stale row both alert, fresh does not | A unit test over the three branches of § 1.2 against a real database | **Yes** |
| The heartbeat is written after the last commit and not inside it | A test asserting the row advances after a run in which one enrollment-period raised | **Yes** |
| **The alert actually reaches a person** | A deliberate skipped-run rehearsal in staging before the first production generation | **No.** Nothing automated proves an alert's delivery path works end to end; this is a once-performed manual check, and until it is performed the alert is unproven |

**The last row is the honest one.** This project's standing rule is that a
manual check described without that sentence reads, to the next person, as a
verifier. The 48-hour threshold's *arithmetic* is testable; its *delivery* is
not, on this infrastructure.

### 1.6 The threshold [NFR26.3]

**48 hours, derived as two missed daily runs** — the shortest window that does
not page on a single transient failure the next run would heal. Computed: the
job runs daily, so one missed run is 24 hours of staleness at the moment the
next run would have fired; two missed runs is 48. Alerting at 24 would page
on every single-run failure, which NFR25.8 already covers loudly.

**The requirement records this threshold as open and the human's**, and this
design does not close it. A monthly billing cycle would tolerate longer; a
teacher watching for a fee to appear would not.

---

## 2. What must never be logged [NFR24.5–NFR24.8]

| Requirement | Design |
|---|---|
| NFR24.5 | **`PaymentClaim.transaction_id` never reaches a log line, at any level.** It joins the phone number, the OTP and the token in the never-log set |
| NFR24.6 | **No money amount tied to an identifiable enrollment.** An aggregate with no enrollment attached is permitted [NFR25.14]; a balance beside an enrollment id is not |
| NFR24.7 | **The collection number never reaches a log line.** It is a teacher's personal payment account and the one field D3 deliberately discloses downward — to a narrower audience than a log store's |
| NFR24.8 | Every error log carries the request or correlation id and nothing identifying; **tracebacks are never returned to a client** |

**NFR24.5 is listed first because it is the one a developer would not think
of.** The standing rule names a phone number, an OTP and a token. A bKash
transaction id is none of those and is exactly as sensitive: a handle on a
real payment at a real provider, authored by a child or their guardian — and
OQ-1 asks whether it even survives the claimant's deletion.

**The structural guarantee that makes NFR24.6 enforceable is already built
and D3 must not weaken it.** `app/audit/log.py`'s row dataclass has **no
free-form string field but `correlation_id`**, asserted by a test — because a
`message` or `note` column is where an amount or a phone number eventually
lands, added by someone debugging in good faith.

**D3's own exposure to that rule**: the generation job is the most tempting
place in the product to log a per-enrollment line, because when it goes wrong
a developer wants to know *which enrollment*. The design's answer is the
correlation id plus the enrollment id — **and no amount**. An enrollment id
alone is a key into a table with its own access control; an enrollment id
beside a balance is the child's financial position in a log store with
different retention and different readers.

**No verifier beyond the built dataclass test.** I searched `tests/` for a log
scanner asserting the absence of these values in emitted lines and found none.
NFR24.5–NFR24.7 are review-enforced for D3's new call sites, which is weaker
than the structural guarantee the audit row has, and that difference is
stated rather than glossed.

---

## 3. The ledger is the audit trail [NFR24.9–NFR24.12]

**Most of what would otherwise be logging is already a row**, and the design's
work is to not build the parallel thing.

| Requirement | Design |
|---|---|
| NFR24.9 | Every money movement is a **row, not a log line**. `LedgerEntry` is append-only with `created_by_account_id` and `created_at`. **No parallel money log**, which would be a second record that drifts from the first |
| NFR24.10 | `created_by_account_id` is **NULL for job-created entries**, and that is the honest value |
| NFR24.11 | A correction is **visible as history**: the prior decision retained with its actor and timestamp, the compensating entries carrying their own |
| NFR24.12 | `ReminderEvent` records **every** send attempt including failures, as `(enrollment, period, channel, sent_at, sent_by, outcome)` |

**NFR24.10 is a small decision with a disproportionate consequence.** The
question an auditor asks of a fee ledger is *who did this*. A NULL answers
"the scheduled job, which nobody triggered". A synthetic `system` account
answers with something that **looks like a person**, and an audit query
asking "who charged this student?" would then return a lie that reads as an
answer. The column is nullable for this reason and not for convenience.

**NFR24.11's mechanism, and the part that is easy to get half-right.**
Supersession drives what a teacher *sees*; **the balance still folds every
row**, because a compensating pair sums to zero. So `superseded_by_id` is a
display concern and never a filter in the fold — `derive()` takes every entry
for the enrollment, and a correction that worked by *excluding* rows would
make the ledger stop being append-only in effect while remaining append-only
in storage.

**NFR24.12 is why a reminder is an event and not a boolean.** The
teacher-facing state is the **latest event per `(enrollment, period)`**. A
`last_reminded_at` column cannot express a failed send, a channel, or a second
reminder — and the failed send is the one that matters, because a teacher who
believes a reminder went out when it did not will wonder why nobody paid.

---

## 4. Alerting [NFR25.8–NFR25.12]

| Event | Alerts? | Design reason |
|---|---|---|
| NFR25.8 — the job **fails to complete a run** | **Yes** | `log.critical` at the end of a run that raised out |
| NFR25.9 — the job has **not run at all** for 48h | **Yes** | § 1. The failure a run-failure alert cannot catch |
| NFR25.10 — an individual enrollment-period fails within an otherwise successful run | **No** | A counted metric, not a page |
| NFR25.11 — a push notification fails | **No** | Recorded as an event outcome [NFR24.12] |
| NFR25.12 — a failed pre-migration backup | **Yes** | An unverified upload is not a backup [NFR19.27] |

**NFR25.10 is a deliberate non-alert and the reasoning is inherited from D1.**
The per-enrollment commit granularity exists so one bad row does not abort a
run [NFR19.8]; paging on one bad row converts that resilience into noise. And
noise in the same channel as NFR25.9 **trains the operator to ignore the alert
that means nobody is being billed** — which is the precise mechanism by which
this unit's most important alert would stop working.

**A rising per-enrollment failure count is a dashboard, not a page.** It is
genuinely interesting — it is what a data problem in one batch looks like —
but it is a trend to read, not an interruption.

---

## 5. Metrics [NFR25.13–NFR25.17]

**Counts only, never the values.** A metric labelled by enrollment id, phone
number or amount is that data in a metrics store [NFR24.6].

| Requirement | Metric | What it answers |
|---|---|---|
| NFR25.13 | Per run: **cycles created, skipped by conflict, enrollment-periods failed** | The skipped count is the self-healing property made visible |
| NFR25.14 | **Total charged per run**, an aggregate with no enrollment attached | The one number that would be noticed if fee resolution broke |
| NFR25.15 | Claims submitted / approved in full / approved partially / rejected | The rejection rate is the signal the claim flow confuses people |
| NFR25.16 | **Verification corrections** | A rising rate is a usability finding about the verification screen, not a defect report |
| NFR25.17 | Push dispatch outcomes **including `UNREGISTERED`** | The token-lifecycle signal, and the one push outcome that is not a failure |

### Where they come from

**NFR25.13's three counts are columns of the heartbeat row** (§ 1.1), written
at the moment they are known. **NFR25.15 and NFR25.16 are queries over
`payment_claim`** — a `GROUP BY status` and a count of rows with a non-null
`previous_decision` — rather than emitted metrics at all. Phase 1 carries no
metrics backend [NFR7.6] and these are low-cardinality counts, so the design
is a query over existing data rather than a new system.

**NFR25.14 is the closest this unit gets to a correctness monitor**, and it is
deliberately an aggregate. The fee resolution rule [BR2.4] — enrollment fee
when not NULL, else batch default, with zero a real fee — has a failure mode
where **every student is charged the same wrong amount** and no per-row check
notices, because every row is internally consistent. A tenfold jump in the
run's total is a defect; it is invisible in a per-row view.

**The sustained-non-zero reading of NFR25.13 depends on the scheduler**, and
this is the one observability element the human's choice changes. Under a
single cron invocation, `cycles_skipped` is near zero on a normal day and a
sustained non-zero is a double-scheduling bug. **Under in-process scheduling
the job fires once per worker**, so with two workers the second worker skips
everything the first created and the skipped count is large every single day
by design — which costs that signal its meaning unless it is read per worker
rather than per run. `reliability-design.md` § 6 names this as the one element
that differs; the metric is harmless either way, but its *interpretation* is
not portable between the two.

---

## 6. SLIs and SLOs [NFR26.3–NFR26.6]

| Requirement | SLI | Target | Discharged by |
|---|---|---|---|
| NFR26.3 | **Generation freshness**: hours since the last successful run | **Under 48** | § 1's query. The alert threshold *is* the target rather than a second number |
| NFR26.4 | The per-enrollment ledger identity balances | **Always** | The Hypothesis property test and the per-cycle invariant — **not a production monitor** |
| NFR26.5 | Rows per `(enrollment_id, period)` | **Exactly one, always** | The unique constraint — **not a monitor** |
| NFR26.6 | Payment claim submission success rate | **No target in V1** | Measured through the pilot |

**NFR26.4 and NFR26.5 are SLIs with a target and a test rather than a monitor,
and that is the right shape for both.** The invariant is machine-checkable
before deployment and already at 100% branch coverage with a property test; a
production threshold on it would be an admission it might not hold. NFR26.5 is
enforced by a database constraint, so a monitor would watch for something the
constraint makes impossible. Both are recorded here **so they are not later
re-invented as dashboard panels** — which is the specific way a team ends up
monitoring a guarantee instead of relying on it.

**NFR26.3 is the one genuine production SLI in this unit**, because it is the
only property that can degrade **without anything raising an error**.

**No SLO percentages are invented for V1.** Phase 1 is closed testing with a
small pilot audience, and a 99.x% target set now would be a number nobody
derived from anything — which this project's own practice forbids.

**No distributed tracing.** One host, two workers, a USD 50/month ceiling. A
correlation id through structured logs is the tracing this scale supports, and
it already exists. D3 adds no sink and no recurring cost.

---

## 7. What has no automated verifier

Stated plainly and in one place, because a manual check described without this
sentence reads, to the next person, as a verifier.

| Obligation | Verifier | Automated? |
|---|---|---|
| NFR25.9's alert actually fires and reaches a person | A deliberate skipped-run rehearsal in staging before the first production generation | **No** — a once-performed manual check |
| Bangla layout on D3's fee screens | A row per screen in `docs/delivery/bangla-layout-check.md` | **No** — the project has no screenshot harness; the per-screen manual check is the chosen alternative |
| NFR24.5–NFR24.7: no transaction id, amount or collection number in a log line | Review of D3's new call sites | **No** — unlike the audit row, whose absence of free-form fields is structurally asserted |
| NFR18.5: the deploy does not land inside the generation window | The person dispatching the deploy | **No** |

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to the host's standard output and the
  existing collection, with no new sink. D3 adds no observability
  infrastructure and no recurring cost [NFR7.6].
- **Assumed**: `job_heartbeat` is a D3-owned table and therefore carries a
  governance disposition like the other four [NFR10.15]. It holds no personal
  data — a job name, a timestamp and three counts — so its disposition is the
  straightforward one, unlike `ledger_entry`'s.
- **Assumed**: the freshness check is a management command rather than a
  route, so it is reachable without widening the public surface. `/health`
  forbids extra fields deliberately and is public; see § 1.1.
- **Open, and the human's**: the trigger for the freshness check (§ 1.4). It
  must not share a failure mode with the job it checks, which constrains the
  choice without making it.
- **Open, and the human's**: whether 48 hours is right. Derived as two missed
  daily runs; a monthly billing cycle would tolerate longer, a teacher
  watching for a fee to appear would not.
- **Open, and D6's**: the retention period and scheduled purge for
  `reminder_event`. The ledger is retained in full by design [NFR6.28], but a
  reminder event is operational rather than financial and is the D3 table most
  plausibly purgeable.
