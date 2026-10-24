# Infrastructure Specification — D3 `collecting-fees`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3 adds one thing to the infrastructure and it is a scheduling mechanism.**
> Everything else it needs is built: the migration path runs on every boot, the
> secret path is an SSM `SecureString` the deploy already writes, and the new
> tables land through a step that already exists.
>
> **The scheduling mechanism is the human's choice**, and this document is
> written so that either choice remains possible. It does not pick one. What it
> does is state precisely what each would add, and make one constraint
> unambiguous: **if cron is chosen, the entry is provisioned by
> `user_data.sh.tftpl`, never by an operator over SSM.**

## Sources

- [upstream] `construction/collecting-fees/nfr-design/reliability-design.md`
  §§ 5–6 — the FCM adapter's placement, and the scheduler held across both
  options; § 8, the migration
- [upstream] `construction/collecting-fees/nfr-design/observability-design.md`
  § 1 — the `job_heartbeat` table and the absence-of-success alert
- [upstream] `construction/collecting-fees/nfr-design/logical-components.md`
  §§ 4, 6 — shared resources, and the hand-off table this document answers
- [upstream] `construction/collecting-fees/nfr-design/security-design.md`
  §§ 5, 7 — the narrowed `ledger_entry` grant and governance rows
- [upstream] `construction/collecting-fees/nfr-design/performance-design.md`
  § 6 — the job's cost against a 2 GB host
- [upstream] `construction/collecting-fees/nfr-design/scalability-design.md`
  §§ 2, 6 — the constraint as the lock, and the capacity property
- [upstream] `construction/collecting-fees/nfr-requirements/tech-stack-decisions.md`
  § 2 — the two scheduler options and their costs
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 3, 5 — the generation run the schedule invokes, and the claim path whose
  tables this migration creates
- [upstream] `inception/domain-design/components.md` — the component
  catalogue, to which D3 adds no deployable
- [prior] D1's and D2's `infrastructure-design/` — the topology and the gaps
  table this unit inherits
- [code] `infra/main.tf`, `infra/variables.tf`, `infra/modules/app/main.tf`,
  `infra/modules/app/user_data.sh.tftpl`,
  `infra/modules/app/deployment_state.tf`, `infra/terraform.tfvars.example`,
  `.github/workflows/deploy.yml`, `Makefile`, `tests/db/test_governance.py`,
  read 2026-10-24

---

## 1. Deployment

Every row verified against `infra/` rather than inherited on trust.

| Facet | Choice | D3's change |
|---|---|---|
| Compute | Containerized app on EC2 behind an ASG, pinned at one instance | none |
| Image identity | SHA-tagged; `latest` never deployed | none |
| Networking | CloudFront → origin FQDN; no ALB, no NAT, no inbound SSH | none |
| Database | PostgreSQL; RDS `db.t4g.micro` Single-AZ when enabled, encrypted at rest [NFR10.16] | **four tables, plus a fifth — § 4.2** |
| Environments | Production; staging module **defaults off** | none; the rehearsal need is § 7 |
| IaC | Terraform, five modules | **none, unless cron is chosen — § 3** |
| Secrets | SSM Parameter Store `SecureString`, written by `deploy.yml` | **FCM credentials join the same parameter — § 5** |
| Scheduling | **None exists** | **The one real addition [NFR6.38]. The human's choice — § 3** |
| Budget | `terraform_data` precondition failing the plan over the ceiling | **D3 adds USD 0.00 — § 6** |

**D3 adds no deployable and no environment.** The job is an entry point into
the same image, not a second compute target.

---

## 2. Infrastructure Services

| Service | Role | D3's change |
|---|---|---|
| EC2 + ASG | The application, and the host the job would run on | **A scheduled invocation, if cron is chosen** |
| PostgreSQL | All state | **Five new tables** |
| SSM Parameter Store | Image tag (String), runtime env (SecureString) | **One more key inside the existing SecureString** |
| ECR | Image registry | none |
| CloudFront, Route53, ACM, S3 | Edge, DNS, certificates, compose artifact | none |
| FCM | Push delivery | **First use in the product.** An outbound HTTPS call; no inbound surface, no new network rule |
| BulkSMSBD | SMS | **Not on any D3 path.** Reminders are push |

**No queue, no cache, no read replica, no metrics backend, no log sink, no
second compute target.** Each was considered by the NFR design and each was
declined against the USD 50/month ceiling [NFR7.6, OC-4].

---

## 3. The scheduling mechanism — the decision this stage does not make

**D3 introduces the product's first scheduled job** [NFR6.38], and there is no
scheduler to host it. I searched
`infra/modules/app/user_data.sh.tftpl`, `infra/` as a whole,
`.github/workflows/`, `docker-compose.yml`, `deploy/docker-compose.staging.yml`
and the `Makefile` for `cron`, `crontab`, `systemd`, `timer` and `APScheduler`,
and found no scheduling mechanism of any kind.

Both options cost **USD 0.00/month** in additional AWS charges. Neither adds a
compute target, an IAM role or a network path. The choice is therefore not a
cost decision, and this document does not make it.

### 3.1 What each option adds to the infrastructure

| | Host-level cron | In-process (APScheduler) |
|---|---|---|
| **Terraform change** | **Yes** — lines in `user_data.sh.tftpl` | **None** |
| **Image change** | None | A dependency and a startup hook |
| **Recurring cost** | USD 0.00 | USD 0.00 |
| **New IAM, network or compute** | None | None |
| **Survives instance replacement** | Only via `user_data` — § 3.2 | Yes, it ships in the image |
| **Fires per** | Host (one, pinned) | **Worker** — so more than once daily |
| **Runnable by hand for recovery** | Yes, the same command | No handle of its own |
| **Exit status outside the app's own logs** | Yes | No |

### 3.2 If cron is chosen: the entry is provisioned, never hand-added

**This constraint is not optional and it is the single most consequential
sentence in this document.**

`deploy.yml`'s rollout step calls `aws autoscaling start-instance-refresh`,
replacing the instance so it re-runs `user_data` — deliberately, so that "a
refresh exercises the same path a replacement takes after a failure."
`infra/modules/app/main.tf:323-333` pins the group at
`min_size = max_size = desired_capacity = 1`.

So **a cron entry added by an operator over SSM survives until the next deploy
and no longer.** And because generation self-heals, nothing fails when it
disappears: no error, no failed run, no alert. The system looks healthy right
up to the moment someone notices that nobody has been billed since that
deploy.

| Where the entry lives | Survives a deploy? | Acceptable? |
|---|---|---|
| `user_data.sh.tftpl`, Terraform-managed | **Yes** — re-created on every boot | **Yes. This is the requirement** |
| Added by hand over SSM Session Manager | **No** — wiped by the next routine deploy | **No**, and it fails silently |

### 3.3 The cron option's new surface is smaller than it looks

**The invocation pattern already exists and is exercised on every boot.**
`user_data.sh.tftpl:325` runs:

```
sudo -u ubuntu docker compose run --rm api alembic upgrade head
```

That is structurally what a generation job needs: a command in the app image,
against the real database, outside the serving container, returning an exit
status. A cron entry invoking the management command would be a near-copy of a
line that is already written, already Terraform-managed, and already tested on
every single boot. "Add a cron entry" and "add a cron entry in the same shape
as the migration step three lines above it" are different amounts of risk, and
this is the second.

**Stated symmetrically, because the human is choosing on the real
difference**: the in-process option adds nothing to Terraform at all, which is
genuinely less infrastructure. What it costs is the two properties the NFR
requirements named — runnable by hand for recovery, and answerable from
outside the application — and it fires once per worker, which costs the
skipped-by-conflict metric its meaning [NFR25.13]. The cron option costs a
Terraform edit and buys both properties back. Neither is wrong, and the
tech-stack document's recommendation of cron is a recommendation, not a
decision already taken.

### 3.4 The freshness check must not share a failure mode with the job

`observability-design.md` § 1.4 names this and declines to resolve it, because
it follows from the scheduler choice. Resolved here only as a constraint:

| Scheduler chosen | Where the freshness check must run |
|---|---|
| **In-process** | Anywhere — the job and the API share a lifecycle, so the wiped-cron failure cannot occur |
| **Cron** | **Not also cron.** In-process in the API container, or external |

**A check wired to the same cron as the job dies with it**, and the alert that
exists to detect silence is then itself silent.

### 3.5 Double-firing is prevented by a database constraint, not by the schedule

**Stated as a property rather than left as a happy accident.** At
`desired_capacity = 1` neither option can fire on two hosts. **If that capacity
is ever raised, both options fire once per instance**, and the only thing
between that and double-billing is the `(enrollment_id, period)` unique
constraint with `ON CONFLICT DO NOTHING` [NFR6.30, NFR19.9].

That is the correct safety net — it is why the guarantee is specified against
the constraint rather than against the scheduler's uniqueness. It is recorded
here because **raising capacity is an infrastructure edit that would not
otherwise prompt anyone to think about billing**: the comment at
`main.tf:326-330` explains the pin in terms of containerised Postgres and DNS
registration, neither of which mentions fees.

---

## 4. The migration: no pipeline change, and a fifth table

### 4.1 The path already exists

**D3's new tables need no deploy-pipeline change at all.** This is the
second-biggest thing this stage can tell Code Generation, after the scheduler.

| Requirement | State | Evidence |
|---|---|---|
| NFR19.26 — distinct logged step before serving | **Built** | `user_data.sh.tftpl:314-332`; `deploy.yml` runs Alembic after a plan job |
| Fails closed on a bad migration | **Built** | The boot script exits non-zero and serves nothing, because "an instance that starts the API against a schema the migration could not apply is worse than an instance that does not start" |
| NFR19.28 — rehearsed on staging | **Blocked** | `enable_staging_instance` defaults `false` — § 7 |
| NFR19.27 — verified `pg_dump` before production | **Absent** | Inherited gap — § 7 |

**One thing a reader could get wrong.** `deploy.yml:40` offers a
`skip_migrations` input whose own description says "the instance still migrates
at boot". That is a skip of the *pipeline's* migration step, **not of
migration** — `user_data` runs `alembic upgrade head` regardless. A reader who
believed otherwise could think they had deployed D3's code without its schema.

### 4.2 The fifth table, and the test that will fail

**`observability-design.md` § 1.1 adds `job_heartbeat`, which makes five
tables, not four.** Every governance and security requirement in D3 is written
against "the four new tables" [NFR10.15, NFR14.36, security-design § 7].

This is not pedantry, because the control is mechanical and already built:
`tests/db/test_governance.py:35` iterates **live tables** and asserts each has
a disposition; `:45` asserts a retention class; `:56` asserts the reverse
direction. A `job_heartbeat` table created without a disposition row
**fails `make check`**.

| Table | Governance row needed | Named by a requirement? |
|---|---|---|
| `fee_cycle`, `ledger_entry`, `payment_claim`, `reminder_event` | Yes | Yes — NFR10.15 |
| **`job_heartbeat`** | **Yes** | **No** |

Its disposition is the straightforward one — a job name, a timestamp and three
counts, with no personal data — but it must be written.

**Verifier: the existing governance test**, which fails on a live table with no
row. This finding needs no new mechanism; it needs the row. I confirmed the
check can fail today rather than assuming it: the test reads the live schema
through a restricted session, so a table added by a migration is in scope the
moment the migration runs.

### 4.3 Grant ordering

`security-design.md` § 5's narrowed `ledger_entry` grant is issued **in the
same migration that creates the table, after the `CREATE TABLE`**. Issued
earlier it names a table that does not exist; issued in a later migration it
leaves a window in which `0001`'s blanket grant applies.

---

## 5. FCM credentials

**Delivered exactly the way the other secrets are**, with no new mechanism.

| Facet | Mechanism |
|---|---|
| At rest | `/shikkhokplus/shikkhokplus-<env>/runtime-env`, SSM **SecureString**, KMS-encrypted |
| Written by | `deploy.yml`'s "Record the deployment state" step, from a GitHub secret |
| Read by | `user_data.sh.tftpl` at boot, into the container environment |
| In the repository or the image | **Never** [project.md] |
| Non-production | A separate parameter per environment; staging holds test credentials |

The file is written under `umask 077` and `rm -f`'d after upload. **One
parameter rather than one per variable**, so D3 adds a key to the existing
`runtime.env` block rather than a new parameter — the shape
`deployment_state.tf:41-43` chose deliberately, because a partial file is
worse than a stale one.

**The FCM adapter is shared code, not provisioned infrastructure.**
`reliability-design.md` § 5 places it beside the SMS gateway client so D4
imports rather than copies it [NFR19.24; OQ-4 decided at
`inception/units-generation/unit-of-work.md:134`, which is the document that
assigns the adapter to D3 — contract-summary § G is where the question is
asked, not where it is answered]. It provisions nothing and appears in this
document only because its credential path does.

---

## 6. Cost

**Computed from `infra/main.tf`'s own `cost_breakdown` at the values in
`infra/variables.tf`**, not quoted from any document.

Model: `cost_instance = 12.26`, `cost_storage = root_volume_gb × 0.08`
(default 30 → 2.40), so `cost_host = 14.66`; `route53_zone = 0.50`,
`ecr = 0.10`, `rds = 17.36` when enabled; staging adds a second `cost_host`.
CloudFront, ACM and the attached Elastic IP are 0.00.

| Configuration | USD/month | Under USD 50? |
|---|---|---|
| Host alone (instance + 30 GB) | 14.66 | — |
| App only, no staging, no RDS | 15.26 | Yes |
| **`variables.tf` defaults — RDS on, staging off** | **32.62** | **Yes, by 17.38** |
| `terraform.tfvars.example` — staging on, RDS off | 29.92 | Yes, by 20.08 |
| **Defaults plus staging on** | **47.28** | **Yes, by 2.72** |

**Staging and RDS together fit.** Enabling the rehearsal host costs USD 14.66
and lands at 47.28, needing no change to `acknowledged_monthly_budget`.

**D3 adds USD 0.00.** Both scheduler options run on the existing host, FCM is
an outbound call, and the five tables add rows to a database that is already
paid for.

### 6.1 Finding: the budget guard's error message states a figure nothing produces

`infra/main.tf`'s `error_message` heredoc reads **"Staging and RDS together are
USD 50.20."** That figure matches **none** of the configurations the code can
produce. The true staging-plus-RDS figure, from the same file's own model, is
**47.28** — which is *under* the ceiling the message says it breaches.

The same literal appears in `infra/variables.tf`'s `acknowledged_monthly_budget`
description and in `infra/terraform.tfvars.example`'s note.

**D1's infrastructure stage found this and it was not corrected.** It is
recorded again rather than fixed, because whether to edit the string is the
human's call and not this stage's to make silently. It matters because the
message tells a reader that Phase 2 requires retiring the rehearsal host or
raising the ceiling, **and the arithmetic says it requires neither** — a
reader acting on it would retire a host they could afford to keep, which is
precisely the host NFR19.28 needs.

**Verifier: none.** The expression computing `monthly_cost` is checked by the
precondition; the prose inside the error message is checked by nothing. This is
the project's own standing rule — where a comment states a number, the number
is a claim [project.md].

### 6.2 Finding: the variable default and the example file disagree

`infra/variables.tf` sets `enable_rds` **`default = true`**; the same file's
description states the resulting total as "about USD 32.62", which my
computation confirms exactly. `infra/terraform.tfvars.example` sets
**`enable_rds = false`** under a heading reading "Phase 2. Leave false."

Both are internally defensible and they describe different configurations —
32.62 and 29.92. Recorded because **"what runs today" depends on whether a
`terraform.tfvars` exists**, which is gitignored and therefore not knowable
from the repository. A reader consulting one file gets a different answer from
a reader consulting the other. Neither figure changes D3's conclusion, since
D3 adds nothing to either.

---

## 7. Gaps: inherited, and what D3 changes about them

| Obligation | State | D3's relationship | Owner |
|---|---|---|---|
| Staging instance enabled [NFR19.28] | `enable_staging_instance` defaults `false` | **Escalates.** Five new tables is the record's largest schema change, with nowhere to be rehearsed | **D3, before its production deploy** |
| Pre-migration `pg_dump` to S3 [NFR19.27] | Nothing asserts one | **Escalates.** D3 is the first unit whose effects a rollback cannot undo | **D3, before its production deploy** |
| Post-deploy smoke set | `/health` only, curled over SSM | **Becomes executable.** "One read of a fee cycle" was written before fee cycles existed | **D3 can extend it** |
| Alert delivery path | **Nothing reads `log.critical`** | **Escalates sharply** — `monitoring-design.md` § 2 | **The human, at this gate** |
| `job_heartbeat` governance row | Not written | **D3 creates the table** | **D3** — § 4.2 |
| `rate_limit_counter` / `auth_audit_log` purge | Dispositions declared, no job | Unaffected; D3 adds no rows to either | Not D3 |
| `reminder_event` retention | **D3 creates the table** | Period and purge are D6's | **D6** |
| ZAP baseline, Trivy, backend SBOM | Absent | None for D3 | D5, D6 |

**The first two escalate rather than merely persist, and for the same reason**:
D1 added columns, D2 added none. D3 adds five tables and a job that writes
money rows without a user present. A tag rollback restores the previous image;
**it does not un-charge a student** — the ledger is append-only and the remedy
is a compensating entry, never a delete [BR3.3].

---

## 8. Hand-off

| Needs | Does not need |
|---|---|
| **A scheduling mechanism** — the human's choice [§ 3] | A managed scheduler, a second compute target, new IAM |
| **A trigger for the freshness check** not sharing the job's failure mode [§ 3.4] | A metrics backend, a tracing backend, an ALB |
| **FCM credentials** in the existing SecureString [§ 5] | A new secret mechanism, a queue, a cache, a read replica |
| **Staging enabled** for the rehearsal [§ 7] | A new environment |
| **A verified `pg_dump`** before the production migration [§ 7] | A new backup service |
| **A governance row for `job_heartbeat`** [§ 4.2] | A new test — the existing one already fails without it |

---

## Assumptions & Open Questions

- **Assumed**: the generation job is a management command in the app image,
  taking no required arguments and safe to run at any time, so both scheduler
  options invoke the same artifact and neither needs a second image.
- **Assumed**: FCM credentials are a key inside the existing `runtime-env`
  SecureString rather than a new parameter, matching the shape
  `deployment_state.tf` chose and its stated reason.
- **Assumed**: `job_heartbeat` lives in the same database and the same
  migration as the other four tables, which is what makes it survive the
  instance replacement that `observability-design.md` § 1.1 requires it to
  survive.
- **Open, and the human's**: the scheduler choice [§ 3]. This document is
  written so both remain possible and states what each adds.
- **Open, and the human's**: whether to correct the "USD 50.20" literal
  [§ 6.1], and which of the two `enable_rds` values is intended [§ 6.2].
- **Open, and the human's**: enabling staging and adding the pre-migration
  backup assertion before D3's production deploy [§ 7].
