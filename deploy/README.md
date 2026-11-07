# Deploying the backend

> **Rewritten 2026-11-02.** This file used to be a Lightsail runbook
> (SSH, a static IP, a containerised Postgres, `pg_dump` on the same
> host). None of that exists any more, and following it would have built
> a second, unreviewed environment. What follows is how a deploy
> actually happens now.

## The normal path: one dispatch

`Actions -> deploy -> Run workflow`, choosing `staging` or `production`
and optionally a ref. `.github/workflows/deploy.yml` then:

1. **plan** -- resolves the ref to one commit SHA (`git rev-parse HEAD`),
   which every later job checks out and which tags the image [OPS-9].
2. **infrastructure** -- `terraform plan` then `apply` of that plan, in
   the `<env>-infra` environment (production's has a required reviewer).
3. **release**, in the `<env>` environment:
   - builds and pushes `shikkhokplus-<env>-backend:<sha>` (skipped when
     that tag already exists; the repository is IMMUTABLE);
   - remembers the running release (image tag and runtime env);
   - **snapshots RDS** as `shikkhokplus-<env>-predeploy-<sha12>-...` and
     fails if it cannot [OPS-7];
   - writes the new image tag and runtime env to SSM;
   - runs `deploy/roll.sh`: an instance refresh that **launches the new
     host before terminating the old one**, gated by the launch
     lifecycle hook the boot script answers only once the origin serves
     `/health` over verified TLS [OPS-6];
   - runs `deploy/smoke.py` against the **public URL** through
     CloudFront, requiring the database at this commit's migration head;
   - on any failure after the state was written, **restores the previous
     release** in SSM, and if the smoke failed, rolls the host back.

There is no SSH and no manual host step. A shell, when one is needed, is
`aws ssm start-session --target <instance-id>`.

## What runs on the host

`infra/modules/app/user_data.sh.tftpl` provisions every new host, and a
deploy IS a new host. In order: packages and the AWS CLI; secrets from
SSM (never from user data [OPS-4]); nginx; the persisted origin
certificate [OPS-8]; the compose file from the config bucket; then

```
docker compose --profile migrate run --rm migrate alembic upgrade head
docker compose --profile migrate run --rm migrate python -m app.db.commands set-app-role-password
docker compose up -d
```

The `migrate` service is the only one that ever receives the owner's
database URL; the API and every scheduled job connect as the restricted
`shikkhok_app` role [OPS-5]. Then the cron entries, the freshness
service, the readiness probe, DNS self-registration and the lifecycle
signal.

## The runtime environment

The deploy writes this to the SSM SecureString
`/shikkhokplus/shikkhokplus-<env>/runtime-env`, the boot script writes
it to `/srv/shikkhokplus/.env`, and `deploy/docker-compose.staging.yml`
passes each variable to the containers explicitly. Values come from the
GitHub environment's secrets and variables.

| Variable | Source | Notes |
|---|---|---|
| `SHIKKHOKPLUS_ENVIRONMENT` | the dispatch input | `staging` or `production` |
| `SHIKKHOKPLUS_OTP_HMAC_KEY` | secret | not recoverable; keep a copy |
| `SHIKKHOKPLUS_JWT_KEYS`, `SHIKKHOKPLUS_JWT_ACTIVE_KID` | secret, `k1` | losing the key logs everyone out |
| `SHIKKHOKPLUS_SMS_*`, `SHIKKHOKPLUS_GLOBAL_DAILY_SMS` | secrets and variables | no API key selects the null gateway |
| `SHIKKHOKPLUS_STAGING_OUTBOX` | variable, default `0` | a production process with it set refuses to start |
| `SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER` | fixed: `X-Client-Address` | **every environment**; production refuses to start without it |
| `SHIKKHOKPLUS_DATABASE_URL` | SSM `database-url`, by the boot script | the `shikkhok_app` role |
| `SHIKKHOKPLUS_MIGRATION_DATABASE_URL`, `SHIKKHOKPLUS_APP_DB_PASSWORD` | SSM, by the boot script | `migrate` service only, never written to `.env` |
| `API_IMAGE` | the image tag in SSM | a commit SHA, never `latest` |

**The client IP.** The per-IP OTP ceiling needs the caller's real
address. nginx always **overwrites** `X-Client-Address` with the viewer
IP from CloudFront's `CloudFront-Viewer-Address` header (port stripped;
one bare IPv4 or IPv6 address, never a list) and clears
`X-Forwarded-For`; uvicorn trusts no forwarded header at all. The
setting is identical in staging and production so staging exercises
the path production depends on.

## Rolling back

Dispatch `deploy` with the earlier ref. The image for that commit
already exists, so nothing is rebuilt: the run re-points the image tag
and rolls the host, and the ECR tag is the exact artifact that ran
before.

**Not `alembic downgrade`.** Migration `0002` raises on downgrade. The
rollback for a schema change is the pre-deploy snapshot:
`infra/RESTORE.md`.

## Seeding test data for performance testing (staging only)

A Lambda function, `shikkhokplus-staging-seeder`, fills one teacher's
account with a realistic history: three batches (two Math and Physics,
one Math only) of twenty seats, 48 students with a dozen in two
batches, every class since the 1st of the month three months back with
attendance and topics, a weekly test per subject on that week's topics,
monthly fees paid on time, late, in part, ahead, together, in cash on
the same class day, one rejected and resent, some still awaiting review
and some not paid last month, plus an exam fee, expenses, notices,
reminders, and family accounts with their inboxes. It writes through the
application's own services as the restricted role, under a simulated
clock, so every timestamp sits where it would have. `app/seed/` is the
code; `infra/modules/seeder/` says why it is built the way it is.

**Once, to create it:**

1. Re-apply `infra/bootstrap` from a laptop. The CI role needs
   `lambda:*` on `shikkhokplus-*` functions and `iam:PassRole` to
   Lambda; the workload boundary needs Lambda's VPC network-interface
   actions; the deploy role needs `lambda:UpdateFunctionCode` on the
   seeder. Without this the next apply fails at `CreateFunction`.
2. **Deploy once with the seeder still off**, from a commit that
   includes it. The infrastructure job runs BEFORE the build, so the
   function is created from the image staging is already running -- and
   an image built before the release step set `provenance: false` is an
   OCI index with an attestation, which Lambda refuses
   (`CreateFunction`: image manifest media type not supported). This
   deploy releases a plain-manifest image first.
3. Settings → Environments → `staging-infra` → add the variable
   `ENABLE_SEEDER` = `true`.
4. Dispatch `deploy` for staging again, same ref. Nothing is rebuilt;
   the apply creates the function on the image step 2 released, and
   every later deploy moves it to the new release after the smoke
   passes.

**Then, any time:** sign up a teacher on staging (or
`python -m app.db.seed_staging +8801XXXXXXXXX` on the host), and:

```bash
aws lambda invoke --function-name shikkhokplus-staging-seeder --cli-binary-format raw-in-base64-out --cli-read-timeout 900 --payload '{"phone": "+8801711111111"}' seed.json
```

`seed.json` holds the counts written and six seeded family numbers to
sign in with (`/staging/last-otp` gives their codes). Optional fields:
`"months"` (1-12, default 3) and `"seed"` (an integer; the same seed
gives the same history). A refusal -- production, an unknown number, a
non-teacher account, an account already seeded -- comes back as a
`FunctionError` naming the reason, with nothing written. The run is one
database transaction: it lands whole or not at all. Seed a fresh
teacher account for each run; the family numbers are derived from the
account, so two seeded teachers never share a family.

Locally, against `make up`: `python -m app.seed 01711111111`.

**Turn it off after testing** (set `ENABLE_SEEDER` back, deploy). While
it exists its database URL is readable by anyone with
`lambda:GetFunctionConfiguration` on it -- the trade-off
`infra/modules/seeder/main.tf` states. Deleting a VPC function's
security group can take up to an hour while AWS releases its network
interfaces; a slow apply there is that, not a hang.

## What this does not yet have

| Missing | Why it matters |
|---|---|
| A smoke of OTP, lens resolution and a fee read | `deploy/smoke.py` proves serving, database and schema head only; team.md's smoke set asks for more |
| An exercised restore | `infra/RESTORE.md` is written and has never been run |
