# Infrastructure Design — Questions

**Stage**: infrastructure-design (3.4)
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

## How this stage was answered

**D1 provisions nothing.** The infrastructure is built: Terraform across five
modules, an EC2 app behind CloudFront, RDS (on by default), a registry, DNS,
and a budget guard that fails the plan when the estimate exceeds the
acknowledged ceiling. A staging module exists and is **switched off**. Three
GitHub Actions workflows run checks, deploys and Android releases.

So this stage's work is not choosing infrastructure. It is stating **what D1
needs from what exists**, **what D1 changes about how it is operated**, and —
the part with teeth — **which obligations the NFR design placed on
infrastructure are not yet built**.

Each answer is settled from an upstream design or a direct read of `infra/`
and `.github/workflows/`, and the source is named.

---

## Q1. Does D1 need any new infrastructure?

[Answer]: No. No service, no datastore, no queue, no cache tier, no scheduled
job, no new environment [NFR7.5]. D1 adds routes to a running application and
two columns to a running schema.

The hand-off table in `nfr-design/logical-components.md` § 6 already states
this; this stage confirms it against `infra/` rather than repeating it on
trust.

[NFR7.5] [logical-components § 6]

## Q2. Does the deployment model change?

[Answer]: No. Containerized app on EC2 behind CloudFront, image tagged with
the commit SHA, `latest` never deployed, recreate-style instance refresh. A
rollback is redeploying the previous immutable tag — which the workflow's own
comment calls out as the reason the tag *is* the artifact.

D1 inherits this unchanged. The one property it depends on is that the
migration runs **before** the new container serves traffic [NFR19.1].

[code: `.github/workflows/deploy.yml`] [NFR19.1]

## Q3. Is the migration step already wired?

[Answer]: Yes, and in two places, which is worth knowing. `deploy.yml` carries
a `skip_migrations` input whose description reads "Skip Alembic (the instance
still migrates at boot)" — so the instance's `user_data` migrates on boot
regardless, and the workflow input controls only the explicit pre-deploy step.

That satisfies NFR19.1's "distinct, logged step before the new container
serves traffic" for the explicit path. The boot-time path is a second
migration trigger, and D1's migration is backward-compatible, so neither
ordering breaks it.

[code: `deploy.yml`, `infra/modules/app/user_data.sh.tftpl`] [NFR19.1]

## Q4. Is the pre-migration backup built?

[Answer]: **Not as written, and it is largely moot — but one half of it is
not.** This answer was drafted as a serious gap and the code corrected it.

NFR19.3 requires a verified `pg_dump` to S3 before any production migration
*in Phase 1*. No workflow does that. But `enable_rds` **defaults to `true`**
(`infra/variables.tf:174`), so the Phase 2 database is already the one
running — with 7-day automated backups, a backup window at ~midnight Dhaka, a
final snapshot on destroy, and deletion protection.

The database module's comment — "Phase 1 has pg_dump to S3 and no
point-in-time recovery; this is what replaces it" — describes the replacement
as future and it is present. RDS was enabled for a different reason, recorded
in the variable's own description: the deploy refreshes the ASG on every
deploy, and with the database in a container on a root EBS volume with
`delete_on_termination = true`, **every deploy would have wiped it**.

So the backup obligation is met by a better mechanism than the one the
practice named. What is **not** met is the second half of NFR19.3: nothing
*asserts* a recoverable backup exists immediately before a migration runs. An
automated backup window is not the same as a verified pre-migration
checkpoint, and the practice's own standard is that an unverified backup is
not a backup.

[code: `infra/variables.tf:159-175`, `infra/modules/database/main.tf:106-121`]
[NFR19.3]

## Q5. Is the post-deploy smoke set built?

[Answer]: **Partly.** `deploy.yml`'s final step, "The API responds", reaches
the new instance over SSM, prints the provisioning log and curls
`/health`. That is a real health check and it fails the deploy when the
instance does not answer.

It is **not** the smoke set the practice names: OTP issue and verify against
the real gateway, authenticated lens resolution, one read of a fee cycle.
The health endpoint proves the process is up and the database reachable; it
does not prove the path a person uses works.

D1 is the unit that makes the difference visible, because signup is the first
step of that path.

[code: `deploy.yml` "The API responds"] [team: Deployment]

## Q6. What does D1 change about monitoring?

[Answer]: Nothing structural, and one thing by implication. The alert set is
unchanged [NFR25.1–NFR25.4], and D1 deliberately adds no alert — narrow
ceilings must not page [NFR25.2].

What D1 changes is **what the existing logs now contain**: two new personal
fields that must never appear in them [NFR24.1, NFR12.8], and new audit event
members [NFR12.9, NFR12.10]. Those are application-level obligations, and the
infrastructure consequence is nil — the same sink, the same collection.

[NFR25.x] [NFR24.1] [NFR12.8]

## Q7. Does the CI pipeline need a new stage for D1?

[Answer]: No new stage, and one existing step gains a target. `check.yml`
already runs secrets scanning, a lockfile install and check, CVE annotation,
`make check`, and the Android job's money-boundary, format, static-analysis,
Lint and coverage-ratchet steps.

D1's new obligations — the adversarial lens test, the acceptance-transition
tests, the `address` privacy-set membership test — are **pytest tests**, so
they run inside `make check` without a pipeline change. That is the design
working as intended: the gate is one command, locally and in CI.

[code: `.github/workflows/check.yml`] [team: Testing Posture]

## Q8. Do the two purge jobs land here?

[Answer]: No, and the reason is scope rather than convenience. Both
`rate_limit_counter` (48 hours) and `auth_audit_log` (12 months) carry
declared dispositions with no enforcing job. A scheduled purge is
infrastructure, and D1 adds none [NFR7.5].

They are recorded in this stage's specification as **named gaps with an
owner**, because the alternative — leaving them in a design document nobody
revisits — is how the Android toolchain went three Bolts without a mechanism.

[NFR6.22] [observability-design § 6]

## Q9. Does the budget change?

[Answer]: No. D1 adds no resource, so the estimate the budget guard checks is
unchanged. Worth stating because the guard is a **precondition that fails the
plan**, not a dashboard.

**And the headroom is larger than a draft of this answer claimed.** That draft
quoted "USD 50.20" from the guard's own error message and concluded headroom
was zero. Computing it from `infra/main.tf`'s breakdown gives **USD 32.62**
today (staging off, which is the default) and **USD 47.28** with staging on —
both under the ceiling. The error message's figure matches neither, so it was
written against assumptions the defaults have since moved past.

[code: `infra/main.tf:86-101`] [NFR7.5] [OC-4]

## Assumptions & Open Questions

- **Checked, and it is off.** `enable_staging_instance` defaults to `false`,
  so NFR19.4's rehearsal has nowhere to happen today. It is listed as a gap
  with an owner rather than an assumption, and enabling it costs USD 14.66
  without needing the acknowledged budget raised.
- **Assumed**: non-production environments hold the gateway's test or sandbox
  credentials, so a staging signup sends no real SMS.
- **Open, and the human's**: whether a **pre-migration backup assertion** is
  added before D1's migration reaches production. RDS automated backups
  already cover the data [Q4], so this is not the serious gap the first draft
  called it — it is the difference between a backup that exists on a schedule
  and one verified to exist at the moment a schema changes. A one-step
  snapshot-and-assert before the migration step closes it.
- **Resolved by reading, not asked**: the first draft of Q4 treated the
  missing `pg_dump` as a blocking gap. `enable_rds` defaults to `true`, so
  the Phase 2 database with automated backups is what is running. Recorded
  because the draft would have put a wrong premise in front of the human.
