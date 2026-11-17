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
4. **web**, **site** and **admin** -- the web client, the public site and
   the platform admin UI, each built, uploaded, invalidated and smoked.
5. **hub** -- once the release and the site have both shipped, runs
   `deploy/smoke.py <site-url> --hub --api-url <api-url>`: the public hub's
   pages are rendered by the API but served only through the site's
   distribution, so neither earlier smoke reaches them. It requires
   `{site}/hub/en` to answer 200 with the hub's own CSP (the site
   distribution turns an origin 403 or 404 into its own 404 page, so an
   origin-secret mismatch would otherwise read as a missing page), a
   canonical link on the site's origin and a stylesheet the site serves;
   then `{site}/hub/sitemap.xml` 200, `{site}/hub/en?utm=x` 400,
   `{site}/hub/en/t/no_such_teacher` 404, and `{api}/hub/en` 404. It holds
   no AWS credentials and rolls nothing back: what it catches is edge
   wiring between two distributions, which the previous image would not
   undo.

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

**A new scheduled job reaches a host with the deploy that ships its
code.** The cron entries (fee and session generation, the retention
purge, the hub badge refresh at 02:30, the hub demand question at 03:00,
the hub invalidation sender every two minutes) are written by this boot
script, so only a host booted from the current launch template has them.
Every deploy gets one: the release waits for the infrastructure job's
apply, which writes the new template version, and `deploy/roll.sh`
replaces the host from the group's `$Latest` template
(tests/gates/test_deploy_workflow.py,
`test_every_deploy_boots_a_host_from_the_applied_template`). Until the
first run of a new job, the freshness check reports it `never_ran`;
that is expected for up to a day after the deploy that adds it. An
apply run **outside** this workflow changes the template and leaves the
running host on the old one, missing the new entries, until the next
deploy or `deploy/roll.sh shikkhokplus-<env>` with the deploy role.

## The runtime environment

The deploy writes this to the SSM SecureString
`/shikkhokplus/shikkhokplus-<env>/runtime-env`, the boot script writes
it to `/srv/shikkhokplus/.env`, and `deploy/docker-compose.staging.yml`
passes each variable to the containers explicitly. Values come from the
GitHub environment's secrets and variables.

| Variable | Source | Notes |
|---|---|---|
| `SHIKKHOKPLUS_ENVIRONMENT` | the dispatch input | `staging` or `production` |
| `SHIKKHOKPLUS_OTP_HMAC_KEY` | secret | not recoverable; keep a copy. It also keys username holds and username sign-in counters, so **rotating it invalidates in-flight codes, releases every live username hold early** (a renamed-away or deleted name becomes free at once) **and resets the username failure counters** (one more window of guesses) |
| `SHIKKHOKPLUS_GLOBAL_HOURLY_USERNAME_LOOKUPS` | variable, default `1000` | username existence answers served per hour before the operator is alerted; alert only, never refuses |
| `SHIKKHOKPLUS_JWT_KEYS`, `SHIKKHOKPLUS_JWT_ACTIVE_KID` | secret, `k1` | losing the key logs everyone out |
| `SHIKKHOKPLUS_SMS_*`, `SHIKKHOKPLUS_GLOBAL_DAILY_SMS` | secrets and variables | no API key selects the null gateway; **production has no fallback** for the app hash or the ceiling, and the deploy fails without them [C-19] |
| `SHIKKHOKPLUS_STAGING_OUTBOX` | variable, default `0` | a production process with it set refuses to start |
| `SHIKKHOKPLUS_STAGING_OUTBOX_NUMBERS` | variable, staging only | the operator numbers the outbox serves; on staging the outbox is off without it [C-19] |
| `SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER` | fixed: `X-Client-Address` | **every environment**; production refuses to start without it |
| `SHIKKHOKPLUS_EMAIL_ADAPTER` | fixed: `ses` | one-time codes by email; see `infra/README.md` "Email" |
| `SHIKKHOKPLUS_SES_SMTP_USERNAME`, `SHIKKHOKPLUS_SES_SMTP_PASSWORD` | SSM `ses-smtp-username`, `ses-smtp-password` (SecureStrings, Terraform) | the sender IAM user's SMTP credentials; the release stops before writing anything if either is unreadable |
| `SHIKKHOKPLUS_SES_SMTP_HOST`, `SHIKKHOKPLUS_SES_SMTP_PORT` | SSM `ses-smtp-host`, fixed `587` | STARTTLS |
| `SHIKKHOKPLUS_EMAIL_FROM`, `SHIKKHOKPLUS_SES_CONFIGURATION_SET` | SSM `email-from`, `ses-configuration-set` | the only From address the credentials may send as |
| `SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL` | variable, default `1000` | the daily send ceiling; the same variable prices email in the plan's budget guard |
| `SHIKKHOKPLUS_SITE_URL` | SSM `site-url` | the public site's origin: the code email's website link, and the public hub's canonical, `hreflang` and sitemap links. Unreadable, the release warns and writes it empty; the hub smoke then fails on the canonical link |
| `SHIKKHOKPLUS_WEB_APP_URL` | SSM `web-url`, less its `/ui/` | the web app's origin: every public hub page's report link opens `{origin}/ui/hub-report`. The release stops before writing anything if it is unreadable or not `https://<host>/ui/` |
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
2. Set the variable `ENABLE_SEEDER` = `true` -- on the `staging-infra`
   environment, or at repository level: the workflow passes it to
   staging's plan only, so it cannot reach production.
3. Dispatch `deploy` for staging. The infrastructure job runs BEFORE the
   build, so the function is created from the image staging is already
   running -- and an image built before `provenance: false` is an OCI
   index Lambda refuses. When that is so, the run says so in a notice,
   skips the seeder and releases a plain-manifest image; **dispatch the
   same ref again** and the seeder is created then. From there every
   deploy moves it to the new release after the smoke passes.

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
| A smoke of a fee read, and any sign-in smoke in production | on staging, with the outbox on and `SHIKKHOKPLUS_SMOKE_PHONE` set to an allowlisted number that has an account, `deploy/smoke.py` signs in and resolves `/v1/me` [C-38]; production smokes `/health` only |
| An exercised restore | `infra/RESTORE.md` is written and has never been run |
