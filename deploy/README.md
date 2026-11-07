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
| `SHIKKHOKPLUS_SMS_*`, `SHIKKHOKPLUS_GLOBAL_DAILY_SMS` | secrets and variables | no API key selects the null gateway; **production has no fallback** for the app hash or the ceiling, and the deploy fails without them [C-19] |
| `SHIKKHOKPLUS_STAGING_OUTBOX` | variable, default `0` | a production process with it set refuses to start |
| `SHIKKHOKPLUS_STAGING_OUTBOX_NUMBERS` | variable, staging only | the operator numbers the outbox serves; on staging the outbox is off without it [C-19] |
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
earlier image boots against the newer schema -- its boot runs
`migrate-if-behind`, which skips the upgrade when the database is at a
later revision [C-12] -- and that is safe only because migrations stay
backward-compatible. When one was not, the rollback for the schema is
the pre-deploy snapshot: `infra/RESTORE.md`.

## What this does not yet have

| Missing | Why it matters |
|---|---|
| A smoke of a fee read, and any sign-in smoke in production | on staging, with the outbox on and `SHIKKHOKPLUS_SMOKE_PHONE` set to an allowlisted number that has an account, `deploy/smoke.py` signs in and resolves `/v1/me` [C-38]; production smokes `/health` only |
| An exercised restore | `infra/RESTORE.md` is written and has never been run |
