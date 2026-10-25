# Infrastructure Specification — D1 `signing-up-and-joining`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **D1 provisions nothing.** Every row below describes infrastructure that
> exists, verified against `infra/` on 2026-10-23. The value of this document
> is the last two sections: what D1 depends on, and which obligations the NFR
> design placed on infrastructure are not yet built.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-design/logical-components.md`
  — the hand-off table, failure domains, shared resources
- [upstream] `construction/signing-up-and-joining/nfr-design/` — security,
  performance, scalability, reliability, observability designs
- [upstream] `construction/signing-up-and-joining/nfr-requirements/` — NFR7.5,
  NFR19.x, NFR6.2x
- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md`
  — § 5, the migration whose four steps the deploy path must run safely
- [upstream] `inception/domain-design/components.md` — the component catalogue
- [code] `infra/main.tf`, `infra/variables.tf`, `infra/modules/`,
  `.github/workflows/`, read 2026-10-23

---

## Deployment

| Facet | Choice | Rationale |
|---|---|---|
| Compute model | Containerized app on EC2 behind an Auto Scaling Group | Recreate-style refresh at this scale; the ASG is the rollback unit |
| Image identity | Tagged with the commit SHA; `latest` never deployed | The tag **is** the artifact, so a rollback is a redeploy [NFR19.1] |
| Networking | CloudFront in front of an origin FQDN; app in public subnets, database private | CloudFront points at a name so the address behind it can move |
| Database | RDS PostgreSQL, `db.t4g.micro`, Single-AZ, **no public endpoint**, encrypted at rest [NFR10.13] | Multi-AZ doubles cost for a failover this scale does not justify |
| Storage | No instance-persistent state; the database is not on the instance | Every ASG refresh would otherwise wipe it — see below |
| Environments | Production; a staging instance exists as a module and **defaults to off** | Staging is where a migration is rehearsed [NFR19.4] — see the gap below; no availability target of D1's own [NFR18.1] |
| IaC | Terraform `>= 1.10, < 2.0`, AWS provider `~> 5.70`, five modules | The one properly locked surface in the project |
| DNS | Route53 zone with a delegation record | |
| Registry | ECR, **immutable tags** | What makes the SHA tag an artifact rather than a label |
| Budget | A `terraform_data` precondition that **fails the plan** over the acknowledged ceiling | [OC-4] made mechanical, not a dashboard |

### The decision that shaped the rest

`enable_rds` defaults to `true`, and its own description records why: the
deploy pipeline refreshes the ASG on every deploy, which terminates the
instance — and a containerized database lived on a root EBS volume with
`delete_on_termination = true`. **Every deploy would have wiped the
database.**

That is worth repeating in D1's specification because D1's migration is the
first to touch live rows carrying the old model's data. The property it
depends on — that compute is replaceable and data is not on it — is the same
property that makes the migration's tag-rollback story work [NFR19.1], and it
is what lets the conditional backfill run without an ASG refresh destroying
the rows it is rewriting [NFR19.2].

---

## Infrastructure Services

| Service | Role | Configuration | Notes |
|---|---|---|---|
| EC2 + ASG | The application | Instance refresh on deploy | Blast radius: process-level, total but short |
| RDS PostgreSQL | All state | `db.t4g.micro`, Single-AZ, private, deletion protection on, encrypted at rest [NFR10.13] | 7-day automated backups, window ~midnight Dhaka |
| CloudFront | Edge and origin indirection | Origin FQDN, not an IP | |
| ECR | Image registry | Immutable tags | |
| Route53 | DNS | Project zone + delegation | |
| S3 | Config bucket | `docker-compose.yml` pulled at boot | |
| SSM | Operator access and deploy verification | Session Manager; `AWS-RunShellScript` for the health probe | No SSH |
| BulkSMSBD | SMS delivery | External; test credentials in non-production | **Not AWS**; the only third party in D1's path |

**D1 adds no row to this table** [NFR7.5]. No cache tier is provisioned, which is what
makes the no-cache design unviolatable by configuration rather than only by review
[NFR21.1].

---

## Shared Resources

**Shared *within* the deployable, not across units.** This is a modular
monolith: one process, one database, and every unit's code in the same image.
So there is no cross-unit resource sharing in the Unit-DAG sense — no unit
provisions a resource another unit consumes, and D1 provisions nothing at all
[NFR7.5]. What the table records is the resources D1's new code paths share
with code that is already running, which is where contention and blast radius
actually live here.

| Resource | Shared by | D1's effect | Contention design |
|---|---|---|---|
| `rate_limit_counter` | OTP cascade, **signup cascade (new)** | More rows, from unauthenticated traffic | Upsert increments then compares; a refusal releases its own increment [NFR6.25] |
| `auth_audit_log` | All auth events, **signup events (new)** | More rows | Savepoint-isolated writes; fails open and alerts [NFR12.11] |
| Connection pool | Everything | Unchanged | D1 adds no concurrent workload class |
| The RDS instance | Every component | Two columns, one nullable column | Additive migration, backward compatible [NFR19.1] |

---

## What D1 needs from infrastructure

| Needs | Why |
|---|---|
| The staging instance **turned on** (it defaults to off) | NFR19.4 requires the migration rehearsed before production; costs USD 14.66 and stays under the ceiling |
| The existing migration step ordering | NFR19.1: migrate before the new container serves traffic |
| Non-production gateway credentials | So a staging signup sends no real SMS |
| Nothing else | NFR7.5 |

### A note on the migration path

`deploy.yml` carries a `skip_migrations` input described as "Skip Alembic (the
instance still migrates at boot)" — so **two** paths run migrations: the
explicit pre-deploy step, and the instance's `user_data` at boot.

D1's migration is additive and backward-compatible, so neither ordering breaks
it: the previous image runs against the new schema, and the new image runs
against either. Recorded because a non-backward-compatible migration later
would meet two triggers rather than one, and that is a property worth knowing
before it matters.

---

## Gaps: NFR obligations infrastructure does not yet meet

Each row is an obligation the NFR design placed on infrastructure, checked
against the repository on 2026-10-23. **This project's standing rule is that a
practice naming a mechanical control names the unit that installs it**, so
each carries an owner rather than a hope.

| Obligation | State | Severity for D1 | Owner |
|---|---|---|---|
| **Staging instance not enabled** [NFR19.4] | `enable_staging_instance` **defaults to `false`**; the module exists and provisions nothing | **Medium — D1's migration has nowhere to be rehearsed** | **Before D1's production deploy** |
| **Pre-migration backup assertion** [NFR19.3] | RDS automated backups cover the data; **nothing asserts a recoverable backup exists at the moment the migration runs** | Medium — the data is covered, the verification is not | **Before D1's production deploy** |
| **Post-deploy smoke set** [team: Deployment] | `deploy.yml` curls `/health` over SSM and fails on no answer; the named set (OTP issue and verify, authenticated lens resolution, a fee-cycle read) does not exist | Medium — D1 is the first step of exactly that path | **D1 can extend it; D5/D6 complete it** |
| **`rate_limit_counter` purge** [NFR6.22] | `HARD_DELETE` at `HOURS_48` declared in the governance manifest; **no job** | Low now, compounding | Not D1 [NFR7.5] |
| **`auth_audit_log` purge** | `RETAIN_WITH_BASIS` at `MONTHS_12` declared; **no job** | Low now | Not D1 |
| **ZAP baseline against staging** | Absent | None for D1 | **D5** |
| **Trivy on the release image, backend SBOM** | Absent | None for D1 | **D6** |

### The staging gap, and the arithmetic that was wrong about it

A draft of this document assumed staging stays enabled through D1 and asserted
that "staging plus RDS together already come to USD 50.20 against the USD 50
ceiling, so the headroom is zero by construction". **Both halves were wrong**,
and computing the figures rather than quoting them is what showed it:

| Configuration | Monthly | Under USD 50? |
|---|---|---|
| `variables.tf` defaults — RDS on, staging **off** (what runs today) | **USD 32.62** | Yes, by 17.38 |
| Defaults plus staging **on** | **USD 47.28** | Yes, by 2.72 |
| `terraform.tfvars.example` — staging on, RDS **off** | **USD 29.92** | Yes, by 20.08 |

`cost_host` is `12.26 + 30 × 0.08 = 14.66`; the breakdown adds Route53 at
0.50, ECR at 0.10 and RDS at 17.36 when enabled.

**The "USD 50.20" in the budget guard's error message matches none of the
three.** It is not the example file's configuration either — that one comes to
29.92, because the example disables RDS. The figure is a leftover from
assumptions the variable defaults have since moved past, sitting inside the
error message of a control whose whole purpose is to be numerically correct.

That is worth one more sentence, because it is this project's own rule turned
on itself: a comment may not state a number that nothing checks. The guard
*computes* `monthly_cost` correctly and compares it correctly; only the prose
it prints on failure is stale. Low severity, trivially fixable, and exactly
the class of defect that survives because everything around it works.

**The consequence is the opposite of what the draft implied.** There is
headroom — enabling staging costs USD 14.66 and lands at 47.28, still under
the ceiling and needing no change to `acknowledged_monthly_budget`. So
NFR19.4's rehearsal is affordable, and what stands between D1 and it is one
variable, not a budget conflict.

### Why the backup and smoke gaps matter here

**The backup assertion** is the smaller gap than it first appears, and the
reason is worth recording: a draft of this stage treated the missing Phase 1
`pg_dump` as serious, then found `enable_rds = true` by default — so the
Phase 2 database with automated backups is what is actually running. The
obligation is met by a **better** mechanism than the practice named. What
remains is the verification half: an automated backup on a schedule is not a
checkpoint taken immediately before a schema changes, and this project's own
standard is that an unverified backup is not one.

**The smoke set** is where D1 is directly implicated. `/health` proves the
process is up and the database reachable. It does not prove a person can sign
up, receive a code, verify it and reach their batch list — which is precisely
what D1 builds, and precisely what the practice's named smoke set checks. D1
is the unit that makes the difference between those two visible.

---

## Assumptions & Open Questions

- **Checked, not assumed, and it came back the other way.** A draft assumed
  staging stays enabled and that the budget had zero headroom. Both were
  wrong: `enable_staging_instance` defaults to `false`, and the configuration
  running today costs USD 32.62 against a USD 50 ceiling. The arithmetic is
  in the gaps section; the lesson is that quoting a figure from an error
  message is not the same as computing it.
- **Assumed**: D1 adds no Terraform change at all, so the budget estimate the
  guard checks is unchanged.
- **Open, and the human's**: whether a pre-migration snapshot-and-assert step
  is added before D1's migration reaches production. One step; closes the
  verification half of NFR19.3.
- **Open, and the human's**: whether D1 extends the post-deploy check from
  `/health` to the signup path it builds, or whether that waits for a later
  unit.
