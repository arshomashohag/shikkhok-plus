# Infrastructure Specification — D4 `teaching-and-recording`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 adds two lines of infrastructure, and one of them is not in Terraform.**
>
> The first is a second cron entry for session generation — the ask
> `logical-components.md` § 6.1 makes, and the only Terraform change in the
> unit. The second is not infrastructure at all in the usual sense: **the
> freshness check that watches for a silent job is hardcoded to the fee job**,
> so D4's heartbeat row would be written and never read. That is a one-argument
> change in the application, and it is recorded here because this is the
> document that owns the question "does the alert mechanism cover the new job".
>
> Everything else D4 needs already exists: the migration path runs at boot, the
> grant pattern is established, the governance gates are built, and the queue is
> entirely client-side. **D4 adds USD 0.00/month and no new resource** [NFR6.57].

## Sources

- [upstream] `construction/teaching-and-recording/nfr-design/logical-components.md`
  § 6 — the hand-off this document answers; § 1.3, the device queue; § 7, the
  component diagram's two jobs against one heartbeat table
- [upstream] `construction/teaching-and-recording/nfr-design/reliability-design.md`
  § 8 — the generation job; § 9, the migration and its six tables; § 3, the
  offline queue, which provisions nothing
- [upstream] `construction/teaching-and-recording/nfr-design/security-design.md`
  § 1.2 — the per-table grant; § 6, the governance obligations; § 7.2, the
  unencrypted queue file as a recorded decision
- [upstream] `construction/teaching-and-recording/nfr-design/observability-design.md`
  §§ 3–4 — the counters and the one alert, implemented in `monitoring-design.md`
- [upstream] `construction/teaching-and-recording/nfr-design/performance-design.md`
  §§ 1.2, 3.1 — the absent latency budget, and the job's computed cost
- [upstream] `construction/teaching-and-recording/nfr-design/scalability-design.md`
  §§ 3.3, 4.1 — no leader election, and no new resource
- [upstream] `construction/teaching-and-recording/nfr-requirements/tech-stack-decisions.md`
  — NFR1.6–NFR1.8, the cron ask and the job-name separation
- [upstream] `construction/teaching-and-recording/functional-design/functional-spec.md`
  and `rules.md` — BR1.1–BR1.7, the generation the schedule invokes
- [upstream] `inception/domain-design/components.md` — the component
  catalogue, to which D4 adds no deployable
- [prior] D3's `collecting-fees/infrastructure-design/` — the cron entry this
  unit extends, and the cost model it computed
- [code] `infra/main.tf`, `infra/variables.tf`, `infra/terraform.tfvars.example`,
  `infra/modules/app/main.tf`, `infra/modules/app/user_data.sh.tftpl`,
  `infra/modules/cdn/main.tf`, `.github/workflows/deploy.yml`,
  `.github/workflows/check.yml`, `Makefile`, `app/fees/commands.py`,
  `app/governance/dispositions.py`, `migrations/versions/0005_fee_system.py`,
  `tests/db/test_governance.py`, read 2026-10-24

---

## 1. Deployment

Every row checked against `infra/` in this session rather than inherited.

| Facet | Choice | D4's change |
|---|---|---|
| Compute | Containerized app on EC2 behind an ASG, pinned at one instance | none |
| Image identity | SHA-tagged; `latest` never deployed | none |
| Networking | CloudFront to origin FQDN; no ALB, no NAT, no inbound SSH | none |
| Origin TLS | certbot issues a real certificate by DNS-01 in `user_data` | none |
| Database | PostgreSQL; RDS `db.t4g.micro` Single-AZ when enabled, encrypted at rest [NFR10.20] | **six tables — § 4** |
| Environments | Production; staging enablement depends on a gitignored file — § 5.1 | none; the rehearsal need is § 6 |
| IaC | Terraform, five modules | **One cron entry in `user_data.sh.tftpl` — § 3** |
| Secrets | SSM Parameter Store `SecureString`, written by `deploy.yml` | **none — D4 introduces no secret** |
| Scheduling | Host cron for the fee job; a `Restart=always` systemd service for its freshness check | **A second cron entry, and a gap in the check — § 3** |
| Budget | `terraform_data` precondition failing the plan over the ceiling | **D4 adds USD 0.00 — § 5** |

**D4 adds no deployable, no environment and no compute target.** The session
job is a second entry point into the same image, exactly as the fee job is.

---

## 2. Infrastructure Services

| Service | Role | D4's change |
|---|---|---|
| EC2 + ASG | The application, and the host both jobs run on | **A second scheduled invocation** |
| PostgreSQL | All state | **Six new tables**; one more row in `job_heartbeat` |
| SSM Parameter Store | Image tag (String), runtime env (SecureString) | none |
| ECR | Image registry | none |
| CloudFront, Route53, ACM, S3 | Edge, DNS, certificates, compose artifact | none |
| FCM | Push delivery, D3's adapter | **Imported, not rebuilt** [NFR19.24] |
| BulkSMSBD | SMS | Not on any D4 path |

**No queue, no cache, no read replica, no metrics backend, no log sink, no
object store for the device queue.** Each was considered by the NFR design and
declined [NFR6.57, OC-4].

### 2.1 The offline queue provisions nothing

**The queue is the largest thing in this unit and the smallest thing in this
document**, which is worth stating because a reader who has read
`reliability-design.md` § 3 arrives here expecting a sync service.

| Property | Infrastructure consequence |
|---|---|
| Stored in a file on the device [NFR5.10] | No server storage, no bucket, no managed sync |
| Sync is one HTTPS call to a host that already exists | No new network path, no second port |
| Four states live on the device [NFR5.2] | No server-side state machine, no session store |
| Not encrypted at rest, a recorded decision [NFR5.12] | No KMS key, no keystore provisioning |

**The queue adds exactly one server edge** — the sync path — and it terminates
on the FastAPI process already running [logical-components § 7].

---

## 3. The one Terraform change, and the gap beside it

### 3.1 The ask, and the built precedent it copies

`logical-components.md` § 6.1 asks for **one cron entry**, installed by
`user_data.sh.tftpl` and never by hand over SSM [NFR1.7]. **That mechanism is
built and in production**: `user_data.sh.tftpl:425-443` installs
`/etc/cron.d/shikkhokplus-fee-generation` at `0 2 * * *`, invoking
`docker compose run --rm api python -m app.fees.commands generate`.

**D4's entry is a near-copy of a line that already exists**, which is the same
argument D3 made for cron over an in-process scheduler and it holds more
strongly now, because the precedent is no longer hypothetical.

| Facet | The fee entry (built) | D4's session entry |
|---|---|---|
| Installed by | `user_data.sh.tftpl` | **The same file** |
| Invocation shape | `docker compose run --rm api python -m <module> generate` | The same, a different module |
| Survives instance replacement | Yes, re-created on every boot | The same property, same reason |
| Recurring cost | USD 0.00 | **USD 0.00** |
| New IAM, network or compute | None | **None** |

**The constraint is unchanged and not optional**: the ASG refreshes on every
deploy (`deploy.yml:361-412`, `start-instance-refresh`), the instance is
replaced and `user_data` re-runs. An entry added over SSM survives until the
next routine deploy and no longer — and because generation self-heals,
**nothing looks wrong** until a teacher opens the app and there is no class to
mark against [NFR1.7, BR1.1].

**Verifier: the entry's presence in the Terraform template, reviewed in the
infrastructure diff. Nothing automated asserts that a registered job name has a
cron entry**, which is the same class of gap as § 3.3 and is stated here so the
review verifier is not read as a mechanical one.

### 3.2 The scheduling time is a real choice, not a copy

The fee entry runs at **02:00 UTC, which is 08:00 in Dhaka**, chosen in its own
comment as "after any overnight deploy window and before a teacher opens the
app to check the month's fees."

**Session generation wants to be earlier than attendance-taking, not earlier
than fee-checking**, and those are not the same deadline. A session that does
not exist when a morning class starts is BR1.1's violation reached
operationally. This design does not fix an hour — `performance-design.md` § 3.2
owns the schedule — but it records the constraint the hour must satisfy:
**generation completes before the earliest plausible class**, and the job's
computed cost makes a wide margin affordable.

**Two entries at the same minute is the one combination to avoid.** Both would
start `docker compose run --rm api` simultaneously on a 2 GB host. Nothing
breaks — the jobs touch disjoint tables — but the memory peak doubles for no
reason, and staggering costs nothing.

### 3.3 The finding: the freshness check cannot see D4's job

**This is the most consequential thing in this document, and it is not in
Terraform.**

`observability-design.md` § 4.1 specifies that the session job registers under
its own name beside `FEE_GENERATION_JOB` so the two are tracked independently
[NFR1.8], and states the mechanism is "parameterised, so D4 adds a name, not a
table." **That is true at the function level and false at the entry-point
level**, and the gap is exactly where the alert lives.

Read from `app/fees/commands.py`:

| Layer | Parameterised by `job_name`? | Evidence |
|---|---|---|
| `stamp_heartbeat(...)` | **Yes**, `job_name: str = FEE_GENERATION_JOB` | `:92` |
| `check_generation_freshness(...)` | **Yes**, `job_name: str = FEE_GENERATION_JOB` | `:170` |
| `main_check_freshness()` | **No.** Calls with no argument; logs `job_name: FEE_GENERATION_JOB` | `:244`, `:251` |
| `main()` verb dispatch | **No.** `sys.argv[1]`; verbs are `generate` and `check-freshness` only | `:269-277` |

And the host-side check at `user_data.sh.tftpl:470-478` invokes
`python -m app.fees.commands check-freshness` hourly with **no job argument**.

**The consequence, stated without softening**: if D4 writes a heartbeat row
under a new job name and changes nothing else, **the row is written and nothing
reads it.** The freshness service keeps checking the fee job, keeps returning
healthy, and a session job that never fires produces no signal at all — which
is precisely the failure NFR25.23 exists to detect, reached by the one route
the design assumed was covered.

**This is not a defect in the built code.** `app/fees/commands.py` was written
for one job and parameterised its functions in anticipation of a second. It is
a D4 obligation that the NFR design believed was already discharged, and the
belief traces to a true sentence about the wrong layer.

**What it costs to close: small, and the shape is the human's choice.**

| Option | Change | Covers a third job later? |
|---|---|---|
| **A. A job-name argument on the verb** | `check-freshness <job_name>`; the systemd script loops over both names | Only if someone edits `user_data` again |
| **B. Check every registered job** | `check-freshness` reads all `job_heartbeat` rows, alerting per stale row | **Yes, with no `user_data` change** |
| **C. A second systemd service** | A duplicate unit file hardcoded to the session module | Only by further duplication |

**Option B is the only one that cannot be forgotten by the next unit**, which
is this project's stated preference for mechanical over remembered controls
[team.md]. It also carries a cost the others do not: a job registered once and
then retired leaves a row that goes stale forever and alerts indefinitely. That
cost is real and bounded — two jobs exist, and a retired job's row is deleted
by the migration that retires it.

**This design did not choose; the human did.**

**DECIDED 2026-10-25 by the human: option B.** The check reads every row in
`job_heartbeat` and alerts per stale row. Code Generation builds it as follows,
and this is now an obligation of D4 rather than an open question:

- `main_check_freshness()` stops calling `check_generation_freshness` with a
  default and instead enumerates the registered jobs, calling the existing
  parameterised function once per row. The function itself is already
  parameterised at `:170` and does not change.
- The per-job log line replaces the hardcoded `FEE_GENERATION_JOB` at `:251`
  with the row's own name, so a stale session job names itself in the alert.
- The host invocation at `user_data.sh.tftpl:470-478` is **unchanged** — a bare
  `check-freshness` with no argument is now correct rather than incomplete,
  which is the property that made option B the choice.
- **A job's row is deleted by the migration that retires it.** This is option
  B's one accepted cost written as a rule, because the alternative is a retired
  job alerting forever. Nothing enforces it today and nothing retires a job in
  D4; it is recorded here so the first retirement does not have to rediscover it.
- Each threshold stays per-job: the session job's staleness window is its own,
  not the fee job's. `observability-design.md` § 4.1 sets it.

The accepted consequence is that **D5 and D6 get freshness coverage with no
further change to `user_data`**, which was the deciding property: `user_data`
takes effect only on instance replacement, so a control that requires editing
it is a control the next unit can silently fail to apply.


### 3.4 The freshness check's own survival property is unchanged

`user_data.sh.tftpl:445-456` records why the check is a `Restart=always`
systemd service and **not** a second cron entry: a check sharing the job's
trigger is circular, so a corrupted crontab silences both. That reasoning is
unaffected by D4 and D4 must not undo it — **whichever option in § 3.3 is
chosen, the check stays on the systemd service and does not become a cron
entry.**

The same comment is honest that **an instance replacement wipes and reinstalls
both together**, so the check cannot detect its own absence. Unchanged by D4,
restated because D4 doubles what rides on it.

---

## 4. The migration: six tables, no pipeline change

### 4.1 The path already exists, and it is the boot path only

**D4's six tables need no deploy-pipeline change** [NFR19.46].
`user_data.sh.tftpl:394-412` runs `alembic upgrade head` as a distinct logged
step that **fails closed** — exiting non-zero and serving nothing, because "an
instance that starts the API against a schema the migration could not apply is
worse than an instance that does not start."

| Requirement | State | Evidence |
|---|---|---|
| A distinct logged step before serving | **Built** | `user_data.sh.tftpl:394-412` |
| Fails closed on a bad migration | **Built** | `exit 1` before `docker compose up` |
| Forward-only, backward-compatible [NFR19.47] | **A property of D4's migration**, which only creates | § 4.3 |
| Rehearsed on staging [NFR19.47] | **Depends on configuration** | § 5.1, § 6 |
| Verified `pg_dump` before production | **Absent** | Inherited gap — § 6 |

### 4.2 Finding: `deploy.yml` has no migration step, and advertises one

> **Resolved 2026-10-25, during this stage's review.** The input was removed
> from `deploy.yml`, verified as a single occurrence — its own declaration,
> with no `if:` and no expression anywhere else in the file — so removing it
> changed no behaviour. A comment at `:39` records what it was and why it went.
> **The misleading toggle is gone; the two real gaps below are not closed**:
> there is still no pipeline-side Alembic step and no preview of what is about
> to be applied. Removing a control that did nothing does not supply one that
> does something, and D4's six tables are still migrated only at instance boot.
> The finding as written below is the state the documents were drafted against
> and is kept for the record.

**D3's infrastructure documents and `team.md` both describe Alembic running as
a step in the deploy pipeline. It does not.**

I searched the whole of `.github/workflows/deploy.yml` for `alembic` and
`migrat`, case-insensitively. The matches are a comment at `:21`, the
`skip_migrations` input's own description at `:40`, and a comment at `:414`.
**There is no Alembic invocation in any job**, and **`skip_migrations` is
referenced nowhere after its declaration** — no `if:`, no expression, no
environment variable.

| Claim | Reality |
|---|---|
| `team.md`: "*Verified 2026-10-22: `deploy.yml` runs Alembic as a separate logged step, after a distinct plan job*" | The distinct logged step is in **`user_data.sh.tftpl`**, not `deploy.yml` |
| D3 § 4.1: "`deploy.yml` runs Alembic after a plan job" | Not in the file as it stands today |
| `deploy.yml:40`: "Skip Alembic (the instance still migrates at boot)" | **The input skips nothing.** It is wired to no step |

**The substance is safe and the record is wrong.** Migration does happen, on
every boot, fails closed, and the rollout replaces the instance — so a deploy
cannot serve against an unmigrated schema. What does not exist is the
pipeline-side step, a preview of what is about to be applied, and any meaning
for the input a dispatcher can toggle.

**Why it matters for D4 specifically**: six tables is this unit's largest
irreversible act, and a dispatcher reading the input list would reasonably
believe they could deploy D4's image while holding its schema back, or that
ticking the box changes something. **It changes nothing in either direction.**
Being wrong in the safe direction is still being wrong about the one control
standing between a release and the database.

**This is a finding, not a fix.** Whether to remove the input, wire it, or add
a pipeline-side migration step is the human's call. **Verifier: none.** The
input's description is prose and nothing asserts it against the workflow's
steps — the project's own rule that a comment stating a scope is a claim
[project.md], applied to a workflow input.

### 4.3 Grants: the pattern is established and the list is the mechanism

`security-design.md` § 1.2 is correct and I confirmed it: **there is no
`ALTER DEFAULT PRIVILEGES` anywhere**, so every migration grants its own
tables. `0005_fee_system.py` declares `NEW_TABLES` at `:127-133` and loops the
grant at `:356-361`.

**D4's migration follows that shape**: a declared six-name tuple and a loop,
not six written-out statements. The reason is in `0005`'s own comment and it is
mechanical — a table in the list cannot be granted by accident, and a table
created without being added to it fails loudly.

**Why loudly rather than quietly** is the part to carry into D4: `0002`'s
docstring records that an ungranted table is **invisible to the restricted role
in `information_schema`**, so the governance gates stop covering it without
failing. A control that quietly narrows is worse than one that fails.

**Verifier: `tests/db/test_governance.py:171` and `:191`, both built.** D4
specifies no new reachability test. The grant is covered by assertions that
already exist and already iterate live tables.

### 4.4 Governance rows: six entries, none of them written

`app/governance/dispositions.py` holds **19 entries** — counted from the file,
matching `security-design.md` § 6.1 — and **none of D4's six tables is among
them**. `RETENTION` is derived from `DISPOSITIONS` by a dict comprehension at
`:279-281`, so there is one entry per table and no second map to drift.

| Table | Entry needed | Declared today |
|---|---|---|
| `session`, `attendance`, `attendance_submission`, `exam`, `mark`, `announcement` | **Yes, six** | **No** |

**The migration fails `make check` without them**, in both directions:
`test_every_live_table_has_a_disposition` catches a missing entry and
`test_no_disposition_names_a_table_that_does_not_exist` catches a typo'd one.
**That is the control working**, which makes this a note to Code Generation
rather than a risk.

---

## 5. Cost

**Computed from `infra/main.tf`'s own `cost_breakdown` at `infra/variables.tf`
values in this session**, not quoted from any document.

Model, read from `main.tf:74-94`: `cost_instance = 12.26`,
`cost_storage = root_volume_gb x 0.08` (default 30, so 2.40), giving
`cost_host = 14.66`; `route53_zone = 0.50`, `ecr = 0.10`, `rds = 17.36` when
enabled, and staging adds a second `cost_host`.

| Configuration | USD/month | Under USD 50? |
|---|---|---|
| App only — no staging, no RDS | 15.26 | Yes, by 34.74 |
| Staging on, RDS off | 29.92 | Yes, by 20.08 |
| Staging off, RDS on | 32.62 | Yes, by 17.38 |
| **Staging on and RDS on** | **47.28** | **Yes, by 2.72** |

**Staging and RDS fit together.** Enabling the rehearsal host costs USD 14.66
and lands at 47.28, needing no change to `acknowledged_monthly_budget`.

**D4 adds USD 0.00.** The cron entry runs on the existing host, the six tables
add rows to a database already paid for, and the queue is on the user's phone.

### 5.1 State the configuration beside the figure

`infra/variables.tf:166` sets `enable_rds` **`default = true`**, while
`infra/terraform.tfvars.example:30` sets `enable_rds = false` and `:21` sets
`enable_staging_instance = true`. Both are internally defensible and they
describe **different configurations** — 32.62 and 29.92.

**"What runs today" therefore depends on whether a `terraform.tfvars` exists,
and that file is gitignored**, so it is not knowable from the repository. Any
figure in this record is meaningful only beside the configuration it assumes,
which is why every row above names one. D4's conclusion is unaffected: it adds
nothing to any of the four.

**The stale "USD 50.20" has been corrected.** `main.tf:41-51` now records that
the true staging-plus-RDS figure is 47.28 and that the old literal matched no
configuration the code can produce. I recomputed it rather than trusting the
correction, and the arithmetic agrees.

---

## 6. Gaps: inherited, and what D4 changes about them

| Obligation | State | D4's relationship | Owner |
|---|---|---|---|
| Staging enabled for rehearsal [NFR19.47] | Depends on a gitignored file — § 5.1 | **Escalates.** Six tables is the record's largest single migration | **D4, before its production deploy** |
| Pre-migration `pg_dump` to S3 | Nothing asserts one | **Escalates.** Attendance and marks are the first child-authored content at scale | **D4, before its production deploy** |
| **The freshness check covers only the fee job** | Hardcoded — § 3.3 | **D4 creates the condition.** Its alert does not exist until this is closed | **D4** |
| **No pipeline-side migration step or preview** | § 4.2. The unwired `skip_migrations` input was removed 2026-10-25; the missing step was not added | D4 does not cause it; D4's migration is the largest thing it affects | The human |
| Alert delivery path | **Nothing reads `log.critical`** | **Rides on D3's rehearsal** [observability § 4.2] | The human |
| Six governance rows | Not written | **D4 creates the tables** — § 4.4 | **D4** |
| Post-deploy smoke set | `/health` over SSM only | D4 adds a path worth smoking; does not close it | The human |
| Screenshot harness for seven screens [NFR17.8] | **Absent**; a written per-screen check instead, which **is not a verifier of the layout** | Unchanged by D4 | The human |
| ZAP baseline, Trivy, backend SBOM | Absent | None for D4 | D5, D6 |

**The third row is the one genuinely new.** The others are inherited or
escalating; that one is created by this unit, and it is created by a design
document's reasonable belief that the mechanism was already parameterised.

---

## 7. What D4 does not add

| Not added | Why |
|---|---|
| A sync service, queue or broker | The offline queue is a file on the device; sync is one HTTPS call [§ 2.1] |
| A metrics backend | None exists; `observability-design.md` § 3.1 designs around its absence rather than introducing one |
| A latency mechanism or benchmark harness for attendance | **PU-3.6 carries no V1 obligation.** `performance-design.md` § 1.2 states the absence as a decision; statement count is the target instead |
| A second compute target | Both jobs are entry points into the running image |
| A leader election or lock service | Idempotency is a database constraint [NFR6.51] |
| Row-level security on the six tables | Declined with a stated re-opening trigger [security § 3.1–3.2] |
| Any new secret | D4 introduces no credential; FCM's path is D3's and unchanged |
| A KMS key for the device queue | The queue is unencrypted as a recorded decision [NFR5.12] |

---

## 8. Hand-off

| Needs | Does not need |
|---|---|
| **One cron entry** in `user_data.sh.tftpl`, staggered from the fee entry [§ 3.1–3.2] | A managed scheduler, a second host, new IAM |
| **A freshness check covering the new job name** [§ 3.3] | A metrics backend, an alarm, a topic |
| **Six governance rows and a `NEW_TABLES` grant loop** [§ 4.3–4.4] | A new test — both directions are already built |
| **Staging enabled** for the six-table rehearsal [§ 6] | A new environment |
| **A verified `pg_dump`** before the production migration [§ 6] | A backup service |

---

## Assumptions & Open Questions

- **Assumed**: the session-generation job is a management command in the app
  image taking no required arguments, matching `main_generate()`'s built shape
  and NFR19.42, so the cron entry is a near-copy of the fee entry.
- **Assumed**: D4's six tables arrive in one migration [NFR19.46], so one
  `NEW_TABLES` tuple and one grant loop covers them, as `0005` does for five.
- **Assumed**: `attendance_submission` takes `attendance`'s disposition and
  retention, per `security-design.md` § 6.2. This document does not re-decide
  it, only records that six rows are owed.
- **Decided 2026-10-25, no longer open**: how the freshness check learns about
  the second job [§ 3.3]. The human chose **option B** — check every registered
  job. D4 builds it; D5 and D6 inherit coverage with no `user_data` change.
- **Open, and the human's**: the hour for the session cron entry, constrained
  only to complete before the earliest plausible class and not to collide with
  02:00 UTC [§ 3.2].
- **Open, and the human's**: what to do about `skip_migrations`, which skips
  nothing [§ 4.2].
- **Open, and the human's**: enabling staging and adding the pre-migration
  backup assertion before D4's production deploy [§ 6].
