# Monitoring Design — D3 `collecting-fees`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **The most important thing in this document is a negative finding, and it
> changes what the absence-of-success alert actually is.**
>
> `observability-design.md` § 1.4 specifies that the alert fires as
> `log.critical`, matching the product's two existing alert sites. That is the
> right thing for D3 to *emit*. But **nothing reads it**: there is no log
> shipping of any kind, and the instance that holds the line is destroyed on
> every deploy.
>
> So this document does not describe `log.critical` in terms that read as an
> alert. It states what exists, and it gives the human costed options —
> including the one that needs no log infrastructure at all, because the
> heartbeat is a database row and a row can be read directly.

## Sources

- [upstream] `construction/collecting-fees/nfr-design/observability-design.md`
  — the whole file; § 1 in particular, which this document implements against
  the real platform
- [upstream] `construction/collecting-fees/nfr-design/reliability-design.md`
  §§ 5–6 — the failure modes being watched for, and the scheduler split
- [upstream] `construction/collecting-fees/nfr-design/logical-components.md`
  §§ 4, 6 — the shared-resource table and the gaps handed forward
- [upstream] `construction/collecting-fees/nfr-design/security-design.md` § 7 —
  governance rows, which bear on the heartbeat table
- [upstream] `construction/collecting-fees/nfr-design/performance-design.md`
  § 6 — why the job's cost needs no monitor
- [upstream] `construction/collecting-fees/nfr-design/scalability-design.md`
  § 6 — the per-worker reading of the skipped count
- [upstream] `construction/collecting-fees/nfr-requirements/observability-requirements.md`
  — NFR24.5–NFR24.12, NFR25.8–NFR25.17, NFR26.3–NFR26.6
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3, 9 — the generation run and the reminder path these metrics count
- [upstream] `inception/domain-design/components.md` — its Governance section
  is the shape a disposition row takes (table, disposition, retention), which
  is the form `job_heartbeat` owes in § 7
- [code] `infra/modules/app/user_data.sh.tftpl`, `docker-compose.yml`,
  `deploy/docker-compose.staging.yml`, `infra/` as a whole,
  `app/auth/ceilings.py:226`, `app/audit/log.py:130`, `app/api/health.py`,
  read 2026-10-24

---

## 1. Collection: what exists

| Signal | Where it goes | Retained | Readable off-host |
|---|---|---|---|
| Application logs (all levels) | The container's stdout | Until the instance is replaced | **No** |
| `log.critical` alert lines | The same stdout | The same | **No** |
| Provisioning failures | `/var/log/shikkhokplus-provision.log` on the instance | The same | Only by `cat` over SSM |
| `job_heartbeat` row | **PostgreSQL** | **Indefinitely** | **Yes** |
| Audit log rows | PostgreSQL | Per its disposition | **Yes** |
| Ledger entries | PostgreSQL | In full [NFR6.28] | **Yes** |

**The last three rows are the ones that survive a deploy.** That distinction
is the organising fact of this document.

---

## 2. The finding: nothing reads `log.critical`

### 2.1 What I searched and what I found

I searched `infra/modules/app/user_data.sh.tftpl`, `docker-compose.yml`,
`deploy/docker-compose.staging.yml` and all of `infra/` for a Docker
`logging:` stanza, a `log_driver`/`log-driver` setting, the `awslogs` driver,
an `amazon-cloudwatch-agent` install, a CloudWatch log group, an SNS topic,
`alarm_actions` and `aws_cloudwatch_metric_alarm`. **I found none of them.**

The only log handling anywhere in provisioning is `user_data.sh.tftpl:351`,
which on a **provisioning failure** appends `docker compose logs --tail 50` to
a file on the instance. That is a boot-failure diagnostic, not log shipping.

`infra/README.md:207` records the decision not to add CloudWatch alarms, with
its reasoning: the application already holds the alerts, and duplicating them
would mean two places to change one threshold. That reasoning is sound for a
threshold. **It does not provide a delivery path**, and the README does not
claim it does.

### 2.2 The three consequences, stated plainly

1. **A `log.critical` goes to the container's stdout and stops there.** It is
   not shipped, not retained off-host, and not read by anything. The two
   existing sites — `app/auth/ceilings.py:226` and `app/audit/log.py:130` —
   have the same property. **This is not a D3 regression.** D3 is simply the
   first unit that depends on an alert *being delivered* rather than on a log
   being available if someone goes looking.

2. **The instance is replaced on every deploy**, so even the on-host record is
   destroyed routinely. A critical logged on Tuesday is gone after Wednesday's
   deploy.

3. **Therefore the absence-of-success condition is currently detectable only
   by someone running the freshness check by hand.** Writing it any other way
   would be describing an unread log line in terms that read as an alert.

### 2.3 Why this is worse for NFR25.9 than for anything before it

The thing NFR25.9 detects — **nobody has been billed** — is by construction
the condition nobody is watching for. Self-healing makes it invisible: no
error, no failed run, no degraded response. The one notification that exists
lands in a stream nobody reads and that is then deleted on the next deploy.

**An alert that fires into a destroyed stream is not an alert.** It is a log
line with an urgent name.

### 2.4 The cheapest honest answer needs no log infrastructure at all

**The mechanism is not actually dependent on logs**, and the design already
contains the reason: `job_heartbeat` is **a row in the database**.

| Property | Consequence |
|---|---|
| It is in PostgreSQL, not a file or process memory | It survives instance replacement — the exact event that destroys the log |
| It is one row with a timestamp | `SELECT now() - last_success_at ...` answers the question directly |
| It is readable by anything with database access | A person, a `make` target, or an external check — no agent, no log group, no topic |

So **the freshness question is answerable today, at zero cost, by querying the
table.** What does not exist is anything that asks the question on a schedule
and tells a person the answer. That gap is a *delivery* gap, not a *data* gap,
and the distinction is what makes the options below cheap.

### 2.5 Options for delivery, with costs — the human's choice

The first option is the one this design recommends be available regardless of
the others, because it costs nothing and makes the condition checkable at all.

| Option | What it adds | Cost/month | Catches a wiped cron? |
|---|---|---|---|
| **A. A `make` target running the freshness query** | One Makefile target over the existing database connection | **USD 0.00** | Only when a person runs it |
| **B. The freshness check as a scheduled in-process task emitting `log.critical`** | Nothing infrastructural | **USD 0.00** | Yes, but **the alert still reaches nobody** |
| **C. A Docker `awslogs` log driver plus a metric filter, alarm and SNS email** | A log group, a metric filter, one alarm, one topic, and IAM for the instance to write logs | **≈ USD 0.60–1.20** at 0.5–2 GB/month | **Yes, and it reaches a person** |
| **D. An external scheduled check against the database** | A scheduler outside the host | Depends; a managed scheduler was declined at USD-ceiling grounds [NFR7.6] | Yes |

**On the cost figures in row C**: unlike every number in
`infrastructure-specification.md` § 6, these are **not computed from anything
in this repository** — there is no log-volume measurement to compute from,
because nothing collects logs. They are list-price arithmetic over an assumed
volume (CloudWatch Logs ingestion at USD 0.50/GB, storage at USD 0.03/GB-month,
one standard-resolution alarm at USD 0.10, SNS email within the free tier at
this volume), and the volume is the assumption. **Treat the range as an order
of magnitude, not as a quotation**, and confirm against the Pricing API before
committing.

**It fits the budget either way.** Headroom is **USD 17.38** at the
`variables.tf` defaults (32.62) and **USD 2.72** with staging also enabled
(47.28). Option C fits both, though at 2.72 it consumes a visible share of
what is left.

**This design does not choose.** Option A is close to free and should exist
regardless; whether to go further is a judgement about how much the silent
failure is worth preventing, and that is the human's.

---

## 3. Metrics and KPIs

**Counts only, never the values.** A metric labelled by enrollment id, phone
number or amount is that data in a metrics store [NFR24.6].

| Metric | Source | Threshold | Why it matters |
|---|---|---|---|
| Hours since last successful generation [NFR26.3] | `job_heartbeat.last_success_at` | **48h** | The only property that degrades without raising an error |
| Cycles created per run [NFR25.13] | `job_heartbeat.cycles_created` | None | Zero is normal mid-month; zero at month start is worth a look |
| Cycles skipped by conflict [NFR25.13] | `job_heartbeat.cycles_skipped` | None | Self-healing made visible — **reading differs by scheduler, § 3.1** |
| Enrollment-periods failed [NFR25.13] | `job_heartbeat.periods_failed` | None | A rising count is a data problem in one batch |
| Total charged per run [NFR25.14] | Aggregate over the run, no enrollment attached | None | The one number noticed if fee resolution breaks for everyone identically |
| Claims by status [NFR25.15] | `GROUP BY status` over `payment_claim` | None | A high rejection rate means the claim flow confuses people |
| Verification corrections [NFR25.16] | Count of rows with a non-null `previous_decision` | None | A usability finding about the verification screen |
| Push outcomes incl. `UNREGISTERED` [NFR25.17] | `reminder_event.outcome` | None | Token lifecycle; `UNREGISTERED` is not a failure |

**None of these needs a metrics backend.** Phase 1 carries none [NFR7.6] and
every one of them is a query over a table that exists. They are read by a
person running a query, which is honest about Phase 1 and costs nothing.

### 3.1 The one metric whose meaning depends on the scheduler

| Scheduler | Normal reading of `cycles_skipped` | What a sustained non-zero means |
|---|---|---|
| **Cron, one host** | Near zero | **A double-scheduling bug** |
| **In-process, per worker** | **Large every day by design** | Nothing — the second worker skips what the first created |

**If the in-process option is chosen, this count must be read per worker or it
loses its signal entirely.** It stays harmless either way; it stops being
informative under one of the two.

---

## 4. Alerts

| Alert | Condition | Severity | Routes to |
|---|---|---|---|
| Generation has not succeeded [NFR25.9] | **No heartbeat row, or `now() - last_success_at >= 48h`** | **Critical** | **`log.critical` — which reaches nobody today [§ 2]** |
| Generation run failed [NFR25.8] | A run raises out | Critical | The same stdout, same caveat |
| Pre-migration backup unverified [NFR25.12] | Object missing or trivially sized | Critical | **Nothing — the backup step does not exist** [spec § 7] |
| Individual enrollment-period failed [NFR25.10] | Any single failure in a healthy run | **Not an alert** | A counter on the heartbeat row |
| Push notification failed [NFR25.11] | FCM returns a failure | **Not an alert** | A `reminder_event` row with a failure outcome |

**The query must be written as "alert unless a row exists and is fresh."**
`observability-design.md` § 1.2 is emphatic and it is the easiest thing here to
get wrong: a check reading "if staleness > 48 hours then alert" treats *zero
rows* — the job never ran at all — as healthy, because the comparison is never
evaluated. That is precisely the scheduler-never-wired failure.

**NFR25.10 is a deliberate non-alert**, and the reason is about this unit's
most important alert: per-enrollment commit granularity exists so one bad row
does not abort a run, and paging on one bad row converts that resilience into
noise in the same channel as NFR25.9 — training whoever reads it to ignore the
alert that means nobody is being billed.

---

## 5. SLIs and SLOs

| SLI | SLO target | Measurement window | Measured by |
|---|---|---|---|
| Generation freshness [NFR26.3] | **Under 48 hours** | Continuous | The heartbeat query — the alert threshold *is* the target |
| Per-enrollment ledger identity balances [NFR26.4] | Always | Pre-deployment | **A property test, not a monitor** |
| Rows per `(enrollment_id, period)` [NFR26.5] | Exactly one | Always | **A unique constraint, not a monitor** |
| Claim submission success rate [NFR26.6] | **No target in V1** | The pilot | Observation |

**NFR26.4 and NFR26.5 are recorded here precisely so they are not later
re-invented as dashboard panels.** A production threshold on an invariant the
database enforces would be an admission it might not hold. This is the specific
way a team ends up monitoring a guarantee instead of relying on it.

**No SLO percentages are invented for V1.** A 99.x% target set now would be a
number nobody derived from anything.

---

## 6. Logs and tracing

| Facet | Design |
|---|---|
| Aggregation | **None.** Container stdout, destroyed on each deploy [§ 2] |
| Structure | Existing structured logs with a request/correlation id |
| Tracing | **None.** One host, two workers, a USD 50 ceiling — the correlation id is the tracing this scale supports |
| Dashboards | **None.** The metrics in § 3 are queries, run by a person |

### What must never be logged

| Rule | Value |
|---|---|
| NFR24.5 | **`PaymentClaim.transaction_id`** — joins the phone number, OTP and token in the never-log set |
| NFR24.6 | **No money amount beside an identifiable enrollment.** An unattached aggregate is permitted |
| NFR24.7 | **The teacher's collection number** |
| NFR24.8 | Correlation id on every error line; **no traceback to a client** |

**NFR24.5 is listed first because it is the one a developer would not think
of.** A bKash transaction id is not a phone number, an OTP or a token, and is
exactly as sensitive: a handle on a real payment at a real provider, authored
by a child or their guardian.

**The structural guarantee that makes NFR24.6 enforceable is already built**:
`app/audit/log.py`'s row dataclass has no free-form string field but
`correlation_id`, asserted by a test — because a `message` or `note` column is
where an amount eventually lands, added by someone debugging in good faith.
D3 must not weaken it.

**D3's own exposure**: the generation job is the most tempting place in the
product to log a per-enrollment line, because when it goes wrong a developer
wants to know which enrollment. The answer is the correlation id plus the
enrollment id, **and no amount**.

**Verifier: none for the new call sites.** I searched `tests/` for a scanner
asserting the absence of these values in emitted log lines and found none.
NFR24.5–NFR24.7 are **review-enforced** for D3's new code, which is weaker
than the structural guarantee the audit row carries. Stated rather than
glossed.

---

## 7. Retention

| Record | Disposition | State |
|---|---|---|
| `ledger_entry` | Retained in full [NFR6.28] | By design |
| `fee_cycle`, `payment_claim` | Per `dispositions.py` | **D3 must write the rows** |
| `reminder_event` | **D3 creates the table**; period and purge are D6's | Open |
| **`job_heartbeat`** | **No requirement names it** | **A finding — spec § 4.2** |
| Container logs | Destroyed on instance replacement | Not a policy, a side effect |

**`job_heartbeat` is the fifth table and every requirement says four.** The
existing governance test iterates live tables, so the table fails `make check`
without a disposition row. Its content is a job name, a timestamp and three
counts — no personal data — so the row is easy; it simply has to be written.

---

## 8. What has no automated verifier

Stated in one place, because a manual check described without this sentence
reads, to the next person, as a verifier.

| Obligation | Verifier | Automated? |
|---|---|---|
| **NFR25.9's alert reaches a person** | **Nothing.** The signal is emitted to a stream nothing reads [§ 2] | **No** — and under option A it is a person running a query |
| The 48-hour query is correct across its three branches | A unit test over no-row, stale and fresh against a real database | **Yes** |
| The heartbeat is written after the last commit, not inside it | A test asserting the row advances after a run in which one period raised | **Yes** |
| NFR24.5–NFR24.7: no transaction id, amount or collection number in a log line | Review of D3's new call sites | **No** |
| `job_heartbeat` carries a governance row | `tests/db/test_governance.py` | **Yes** — already built |
| NFR18.5: the deploy does not land inside the generation window | The person dispatching the deploy | **No** |

**The first row is the one to act on.** The others are either already
mechanical or honestly manual; that one is an obligation whose mechanism was
assumed to exist and does not.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to container stdout with no new sink unless
  the human chooses option C. D3 itself adds no observability infrastructure
  and no recurring cost [NFR7.6].
- **Assumed**: the metrics in § 3 are read as queries by a person rather than
  scraped, which is what Phase 1 supports and what costs nothing.
- **Assumed**: `job_heartbeat` carries a governance disposition like the other
  tables; its content makes that disposition the straightforward one.
- **Open, and the human's**: the delivery option in § 2.5. Option A costs
  nothing and should exist regardless; anything beyond it is a judgement about
  the value of catching a silent billing stoppage.
- **Open, and the human's**: whether 48 hours is right. Derived as two missed
  daily runs; a monthly cycle would tolerate longer, a teacher watching for a
  fee would not.
- **Open, and the human's**: the freshness check's trigger, which follows the
  scheduler choice [spec § 3.4].
- **Open, and D6's**: `reminder_event` retention, and OQ-1 — whether
  `PaymentClaim.transaction_id` survives the claimant's deletion.
