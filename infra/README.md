# Infrastructure

Terraform for the backend: one app host per environment in an
auto-scaling group of one, CloudFront in front, RDS behind it. The
monthly figure against the USD 50 ceiling [OC-4] is
`terraform output monthly_cost_estimate` -- the same expression the
budget precondition enforces. It is not restated here: figures restated
in this file were wrong more than once.

**Read with:** `../deploy/README.md` (how a deploy runs),
`RESTORE.md` (restoring the database -- written, not yet exercised),
`bootstrap/README.md` (the OIDC roles and which ARN goes where).

**No SSH anywhere.** Access is SSM Session Manager:
`aws ssm start-session --target $(terraform output -raw app_instance_id)`

```
                    ┌──────────────┐
   api.example.com  │  Route53     │  ALIAS A + AAAA
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  CloudFront  │  ACM TLS 1.2+, Shield Standard
                    │  CACHING OFF │  free tier: 1 TB / 10M req
                    └──────┬───────┘
                           │  X-Origin-Secret header
                    ┌──────▼───────┐
                    │   nginx      │  403 without the secret
                    │  EC2 t4g.small│ 2 GB arm64, Elastic IP
                    │  NO PORT 22  │  SSM Session Manager
                    │  ┌────────┐  │
                    │  │ API    │  │  uvicorn, 2 workers
                    │  │ Postgres│ │  bound to 127.0.0.1
                    │  └────────┘  │
                    └──────────────┘
```

## Three decisions worth reading before you change anything

### 1. CloudFront caches nothing, and that is correct

**1 of 11 routes is safely cacheable and it is the health check.**
Everything else requires a Bearer token, and a cached authenticated
response is a cross-teacher data leak — this project's stated top risk.

So why have it? Free ACM TLS (the alternative is certbot and a renewal
nobody checks until it has expired), a stable hostname so the origin IP
can change without a DNS edit, TLS 1.2 enforced at the edge, Shield
Standard, and a permanently free tier. Caching becomes available later
without re-architecture — it is a cache-policy change, not a new
component.

### 2. The origin lock is a shared secret, not a CIDR allowlist

**CloudFront publishes 214 origin-facing CIDR ranges. A Lightsail
firewall rule accepts 5.** The CIDR approach is not merely worse here;
it cannot be expressed at all and would fail at apply time.

CloudFront sends `X-Origin-Secret` and nginx returns 403 without it.
Port 443 is open to the internet, but a direct request is refused by
our own host before it reaches the application. Rotate with
`terraform taint module.app.random_password.origin_secret`.

### 3. There is no SSH, and that replaced an IP allowlist

The first version restricted port 22 to an operator IP held as a CI
secret. **That was wrong.** A home IP is dynamic, so recovering access
after a router restart meant editing a secret, dispatching a workflow,
waiting for approval and waiting for an apply — and that friction is
exactly what makes somebody widen the rule to `0.0.0.0/0` once "just to
get in", after which it stays.

Session Manager removes the question: no inbound port, no key pair, no
address to track. `team.md` asks for production access to be "named,
logged and bounded"; CloudTrail records who opened a session, which
nothing previously enforced.

Moving to EC2 for SSM cost USD 8.34/month over Lightsail — and bought
something the old design could not have at any price. See below.

### 4. Postgres is on the app host, not RDS — in Phase 1

You asked for RDS in a public subnet with ingress only from Lightsail.
**That was not expressible as stated**: Lightsail instances live
outside your VPC and have no security group for a database to name, so
the options were a public endpoint allowing one `/32` — routing
children-identifying traffic out of AWS and back over the internet — or
VPC peering, which grants a whole range rather than one instance.

**Moving to EC2 fixed that too.** The app host now has a real security
group, so Phase 2's rule is exact:

```hcl
security_groups = [var.app_security_group_id]   # not a CIDR guess
```

**The database is RDS, not on the box.** The deploy replaces the host
on every release and the root volume goes with it, so a database there
would be deleted by the next deploy. Production refuses
`enable_rds = false` at plan time, and the deploy refuses to release
without an RDS instance to snapshot first [OPS-7].

> **The rehearsal host and RDS together now exceed the ceiling.** The
> cost model gained the public IPv4 charge (USD 3.65 per host per
> month, billed since 2024 on every public address) and the alarms and
> logs [OPS-11, OPS-12], and with those `enable_staging_instance = true`
> alongside RDS crosses USD 50. The precondition refuses it; retiring
> the rehearsal host or raising `acknowledged_monthly_budget` is a
> deliberate choice, not a bill surprise.

---

## Terraform runs in GitHub Actions, not on your laptop

**Once**, to break the chicken-and-egg (CI needs state and credentials;
Terraform creates state and credentials):

```bash
cd infra/bootstrap && terraform init && terraform apply
```

No key pair to create: there is no SSH.

See [bootstrap/README.md](bootstrap/README.md) for the variables and
environments to configure afterwards.

**Every time after that:**

1. Edit `infra/**` on a branch, open a PR, merge
2. Actions → deploy → Run workflow → choose the environment
3. The `plan` job renders the plan, read-only, into its summary; the
   `infrastructure` job then applies exactly that saved plan. In
   production, read the plan BEFORE approving `production-infra` -- the
   approval is for that plan and nothing else [C-11]

**ACM validation takes 5–30 minutes** on the first apply, and
CloudFront another 10–15. The job's 45-minute timeout exists for that.
It is not a hang.

### Why apply is manual

An apply can change IAM, DNS, the CDN and the database in one run, so
it happens only from a dispatched deploy in an `*-infra` environment --
never on merge, and never from a branch: the infrastructure role trusts
no `ref:` subject [OPS-2]. Production's apply additionally waits for a
human to read the plan.

## The public site

`modules/site` serves `site/` (the marketing pages and FAQ, English and
Bangla) at the project zone's apex -- `https://shikkhokplus.<apex>` in
staging, `https://shikkhokplus-prod.<apex>` in production -- with
`www.` redirecting to it. A private bucket behind its **own**
distribution and certificate, not the API's: the site calls no API, so
sharing would buy nothing and would add cached behaviours to the one
distribution that must cache nothing by default.

The edge caches everything for up to a year (a cache policy that honours
the origin's `Cache-Control`); the deploy uploads hashed assets as
`immutable` and pages with `max-age=300, s-maxage=31536000`, then
invalidates `/*`. `site/README.md` has the details, and the first deploy
needs `bootstrap/` re-applied (see `bootstrap/README.md`).

**The one exception is `/hub/*`, the public hub**, which this
distribution forwards to the API host: credential-less, GET and HEAD
only, with the query-string allowlist enforced at the edge
(`modules/site/functions/hub-query.js`) and the API's own
`Cache-Control` and CSP honoured. The API's distribution answers `/hub*`
404 (`modules/cdn/functions/hub-block.js`). After every deploy the
`hub` job smokes both sides (`deploy/README.md`, step 5).

The hub's takedown invalidations are sent by the **app host**, not the
container: a cron entry runs `/usr/local/bin/shikkhokplus-hub-invalidate`
every two minutes with the instance role, which may call
`cloudfront:CreateInvalidation` on this distribution only. Its id
reaches the boot script from `module.site.distribution_arn`.

**What a takedown does not evict.** An owner's takedown invalidates
`/hub/{locale}/t/{owner}*` in both locales, which covers its batch pages
and any query string on them; a single batch's takedown invalidates that
batch's exact path in both locales; every takedown also invalidates the
sitemap (`app/hub/public/invalidation.py`). Two kinds of cached page
outlive a takedown and expire only by their TTL:

- **search and landing pages** (`/hub/en`, `/hub/bn?q=…&district=…`): a
  result list naming a taken-down owner stays cached for up to **300
  seconds** (`s-maxage=300`). Its link to the owner's page, which was
  evicted, already gets the 404.
- **query-string variants of a batch page taken down on its own**
  (`/hub/en/t/owner/batch?page=2`, any allowed key): the exact path is
  evicted, but each variant is its own cache entry and stays for up to
  **600 seconds** (`s-maxage=600`).

So moderation should promise "gone from the hub within ten minutes", not
"immediately". Evicting search pages would mean invalidating `/hub/*` on
every takedown, emptying the whole hub's cache each time; the TTLs are the
bound instead.

## Scheduled jobs reach a host only by replacement

Every scheduled job is a cron entry `user_data` writes at boot (fee and
session generation, the retention purge, and the hub's badge refresh,
demand question and invalidation sender). Applying a template change
does **not** roll the host: the group references the launch template's
`$Latest` and its `instance_refresh` has no triggers, deliberately, so an
apply never replaces a running instance by itself.

**The deploy workflow is what installs new entries.** Its release job
waits for the infrastructure job's apply and then always runs
`deploy/roll.sh`, which starts an instance refresh; the replacement
boots from `$Latest` and so carries every entry the template now holds.
No separate operator step is needed for a job that ships through the
workflow. The freshness check reports a newly expected job as
`never_ran` until its first scheduled run, so expect that alert for up
to a day after the deploy that adds the job.

**If you apply outside the workflow** (from a laptop, for instance), the
running host keeps its old crontab. Replace it with

```bash
deploy/roll.sh shikkhokplus-<env>    # with the deploy role's credentials
```

which launches the replacement before terminating the old host, exactly
as a deploy does.

## The platform admin surface

`modules/admin` serves the admin UI and the admin API (`/v1/admin/*`) at
`https://admin.<project zone>` -- its **own** distribution, certificate
and bucket, because the IP allowlist is a CloudFront Function and a
function can gate only its own distribution's behaviours. WAF would do
the same for USD 5/month plus rules; the function costs nothing.

```
admin.<zone>/            admin-gate: IP check, then SPA rewrite -> admin bucket (OAC)
admin.<zone>/v1/admin/*  admin-gate: IP check -> origin.<zone>, adding
                         X-Origin-Secret (nginx) and X-Admin-Edge (the app)
api.<zone>/v1/admin*     admin-block: 404 at the edge, never forwarded
anyone off the list      403 "Not available from this network." on every path
```

- **IPv4 only.** `is_ipv6_enabled = false` and an A record with no AAAA,
  so every viewer arrives over IPv4 and `admin_allowed_cidrs` holds IPv4
  CIDRs only (validated).
- **Empty allowlist = nobody gets in.** The default. In CI the list is the
  `SHIKKHOKPLUS_ADMIN_ALLOWED_CIDRS` repository secret (a secret, not a variable: the repository and its Actions logs are public) (comma-separated);
  changing it is a deploy, which republishes the function in seconds.
- **Three independent locks on the admin API:** the edge allowlist; the
  `X-Admin-Edge` secret only this distribution sends, which the
  application requires (`SHIKKHOKPLUS_ADMIN_EDGE_SECRET`, copied from the
  `admin-edge-secret` SecureString into the runtime env by the deploy);
  and the application's own check of `X-Client-Address` against the same
  list (`SHIKKHOKPLUS_ADMIN_ALLOWED_CIDRS`). Then sign-in and the second
  factor.
- The deploy's `admin` job smokes it from the GitHub runner, which is not
  on the list: `https://admin.<zone>/` must answer **403** and
  `https://api.<zone>/v1/admin/overview` **404**.

The CloudFront Functions are tested without dependencies:
`make infra-functions` (`node --test`). The first deploy needs
`bootstrap/` re-applied (see `bootstrap/README.md`).

## Email: one-time codes through SES

`modules/email` sends from `no-reply@<project zone>` --
`no-reply@shikkhokplus.<apex>` in staging,
`no-reply@shikkhokplus-prod.<apex>` in production -- through Amazon SES's
**SMTP interface**, with the credentials of an IAM user that can do
nothing but send from that one address.

- **One identity per environment, on its own zone.** Both environments
  share one account and one region but not one domain, so each owns its
  identity, DKIM/MAIL FROM/DMARC records, configuration set, alarms and
  SMTP user, and the two applies never contend for a resource.
- **SMTP and an IAM user, because the container has no role.** The host's
  IMDS hop limit is 1 (`modules/app/main.tf`), deliberately, so the API
  container cannot reach the instance role. The user's key is the one
  long-lived AWS credential in the project; it is bounded by its inline
  policy (`ses:SendRawEmail` on this identity and configuration set, From
  `no-reply@<zone>` only) and by bootstrap's
  `shikkhokplus-email-sender-boundary-<env>`. Rotation: raise
  `smtp_credential_generation` in `modules/email/main.tf` and deploy.
- **DNS.** Easy DKIM (three CNAMEs), MAIL FROM `bounce.<zone>` (MX to
  `feedback-smtp.<region>.amazonses.com` and SPF), and
  `_dmarc.<zone>` at **`p=none`** -- a published policy that changes no
  delivery outcome. Move it to `p=quarantine` once real traffic shows DKIM
  and SPF aligned.
- **Alarms.** Bounce rate at 4% and complaint rate at 0.08%, per
  configuration set, to the environment's alert topic -- below the 5% and
  0.1% at which AWS reviews the account.
- **Cost.** USD 0.10 per 1,000 messages, priced in `monthly_cost_estimate`
  as the whole daily ceiling (`SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL`, default
  1,000) sent every day: about USD 3 a month. No dedicated IP, no Virtual
  Deliverability Manager.

### Manual steps, in order

1. **Re-apply `bootstrap/`** from a laptop (see `bootstrap/README.md`).
   It creates the sender boundary and gives the infrastructure, plan and
   deploy roles the SES, IAM-user and parameter grants. Without it the
   infrastructure job stops at `CreateEmailIdentity` or `CreateUser` with
   AccessDenied, and the release at "Cannot read the SES sender from SSM",
   having changed nothing.
2. **Deploy** each environment. The apply creates the identity and writes
   its DNS records into the environment's zone; SES verifies the domain
   and DKIM once they resolve -- usually minutes, at most 72 hours. Until
   then SES refuses to send from it. Check with
   `aws sesv2 get-email-identity --email-identity <zone>`
   (`VerifiedForSendingStatus: true`, `DkimAttributes.Status: SUCCESS`).
3. **Request production access** in the SES console for **us-east-1**
   (Account dashboard -> Request production access). A new account is in
   the **sandbox**: it can send only to addresses verified in SES, at most
   200 messages a day. The sandbox is per account and region, so one
   request covers staging and production. AWS answers within about a day
   and asks how bounces and complaints are handled: suppression of both
   is on in the configuration set, and the two alarms above report rates.
4. **Confirm the alarm subscription** (`alert_email_status`) if not done,
   and after the first real sends check that CloudWatch shows
   `AWS/SES Reputation.BounceRate` for the configuration set -- the alarms
   treat no data as OK, so a metric that never arrives looks the same as
   a healthy one.
5. Optionally set `SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL` per environment; unset
   means 1,000.

## Hub photos: the media bucket and its credentials

`modules/media` holds the hub's photos in one private bucket,
`shikkhokplus-<env>-media-<account id>`, in the app's runtime region:

```
quarantine/{media_id}         presigned POST from the web app     expires after 1 day
staged/{media_id}/            the sanitiser Lambda's WebP variants expires after 30 days
public/{public_key}/          approved copies; the ONLY prefix CloudFront reads
archive/{media_id}/           variants frozen at completion; preview and approval read only these
```

- **Served at `/m/*` on the site distribution** (`modules/site`), through
  Origin Access Control, cached a year, with `nosniff` and
  `Content-Security-Policy: default-src 'none'; sandbox`; the objects carry
  their own `image/webp` type.
  `functions/media-path.js` maps `/m/{key}/{w}.webp` to
  `public/{key}/{w}.webp` and answers any other shape 404 at the edge:
  CloudFront's origin path can only prepend, never strip `/m/`.
- **The API container gets the media role, never the instance role.**
  IMDS hop limit 1 still keeps the container from the instance role. The
  host's `shikkhokplus-media-creds` job (cron, every 15 minutes, and once
  at boot before compose starts) assumes `shikkhokplus-<env>-media` for an
  hour and writes the credentials to
  `/srv/shikkhokplus/media-creds/credentials` (0640, group 10001: the
  container's `app` user), mounted read-only at `/run/media-creds`. A
  failed refresh keeps the previous file and logs to
  `/var/log/shikkhokplus-media-creds.log`. The role can read, write, list
  and delete only the four prefixes above; the rehearsal host gets no role.
- **Uploads come from the web app's origin only** (bucket CORS: `POST`
  from `web-url` less `/ui/`), and the web and admin pages' CSP admit the
  bucket's regional endpoint and nothing else new.
- **Cost**: `media` and `image_lambda` in `monthly_cost_estimate`.

### Manual step

**Re-apply `bootstrap/` before the deploy that ships H3.** It lets the
infrastructure role manage the bucket's CORS, lifecycle, ownership and
event notification, lets the plan role read it, lets the deploy role read
`media-bucket` and `media-bucket-domain`, and raises the workload boundary
to allow the media role's object actions and the host's `sts:AssumeRole`
on that one role. Without it the infrastructure job stops at
`PutBucketCORS` or `CreateRole` with AccessDenied, and the release at
"Cannot read the hub media bucket from SSM", having changed nothing.

**Also before the deploy that ships H3 (HUMAN STEPS):**

1. **Bootstrap additionally gives** the deploy role
   `lambda:UpdateFunctionCode` and `lambda:GetFunctionConfiguration` on the
   image sanitiser (and no other function), and the plan role
   `lambda:GetFunctionEventInvokeConfig`. Without the first, the deploy
   stops at "image sanitiser"; without the second, `terraform plan` fails
   refreshing the Lambda. (The media role and the image Lambda themselves
   are created by the infrastructure job once bootstrap allows it.)
2. **No Lambda concurrency is reserved.** The sanitiser shares the
   account's unreserved pool. AWS keeps at least 10 executions unreserved,
   so on an account whose concurrency quota is 10 any reservation fails the
   apply; adding one back needs a quota increase first
   (`aws lambda get-account-settings` shows the limit).
3. **After the first deploy, upload one real photo to staging from the
   Android debug build and one from the web app**, and see each reach
   "pending review". The two clients send different multipart forms and
   only S3 can confirm it accepts both.
4. **Moderation checklist line**: before the first production publish of
   H3, approve one photo, open its `/m/` URL, then hold it and see the URL
   stop answering. The deploy smoke only proves that unapproved paths are
   refused.

## Switching reviews on

Hub reviews are **off** until someone turns them on, in every
environment. The switch is one SSM parameter per environment, a plain
`String` holding exactly `on` or `off`:

| Environment | Parameter |
|---|---|
| staging | `/shikkhokplus/shikkhokplus-staging/hub-reviews` |
| production | `/shikkhokplus/shikkhokplus-production/hub-reviews` |

Its name is `/shikkhokplus/${var.name_prefix}/hub-reviews`
(`modules/app/deployment_state.tf`) with `name_prefix =
"shikkhokplus-${var.environment}"` (`main.tf`), the same path the release
reads (`ses_param hub-reviews` in `deploy.yml`);
`tests/gates/test_hub_reviews_switch_infra.py` keeps the table and the
commands below equal to it. Terraform creates it `off` and ignores its
value afterwards, so an apply never changes it.

**The deploy role must be able to read it.** Every release reads the
switch, on or off, so if the last deploy succeeded this is already true.
If a release stops at "Cannot read the hub reviews switch", re-apply
`bootstrap/` once from a laptop: H4 added `hub-reviews` to the
parameters the deploy role may read (`bootstrap/deploy_role.tf`). The
release stops before changing anything.

**Turning it on publishes what families write about a class**, so each
step below is a human check, done in this order, and a step that is not
met stops the list. Steps 4 to 6 run on staging first; production
repeats steps 4 and 5 only after step 6 has passed on staging.

1. **D9: the day-90 demand bar in hub spec §9 is met** — opt-in (published
   owners ÷ owners with at least one active batch) **≥ 20%**, and **≥ 15%**
   of answering owners said Yes to "Did the hub bring you a student?".
   *Freeze* (opt-in < 10% or < 5% Yes) or *Hold* (anything between;
   re-measure at day 120) means stop here. No screen computes these two
   figures yet: they are read by hand from `owner_listing`, `batch` and
   `hub_feedback` in the production database, and the two figures and the
   date are written down with the decision. Read them **only through the
   production access path team.md requires** (Deployment, "Production
   access is named, logged and bounded"): your own named non-superuser
   role, never the application's `shikkhok_app` role or a superuser,
   opened through the session wrapper that records the session's start,
   the person and the stated reason ("D9 measurement") to the append-only
   log. Run aggregate counts only, and copy no row out of the session:
   the two percentages are all that leaves it. Neither the role nor the
   wrapper is defined in this repository; if either does not exist yet,
   this step waits until it does.
2. **D8: the legal review of the review policy is recorded** in
   `docs/legal/README.md`, "The D8 legal review of the review policy",
   with a date, a reviewer and an outcome. If the outcome requires a
   change to the review policy, that change ships first.
3. **D6: the declarations are published.** The Play Data Safety form and
   the Families user-content declaration have been updated against
   `docs/legal/README.md` item 5 and the Families note, the privacy policy
   on `main` describes reviews (`docs/legal/PRIVACY.md`, "Reviews"), and
   the site carries the reviews sentence under "Private by design". The
   policy promises an in-app notice before a material change takes
   effect; this is one, and nothing in the app sends such a notice, so
   decide how it is given and give it before step 4 on production.
4. **Write `on`** to the environment's parameter. **Staging first**, then
   steps 5 and 6 on staging:

   ```bash
   # staging
   aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-staging/hub-reviews --type String --value on
   ```

   **Production only after step 6 has passed on staging**, followed by
   step 5 on production:

   ```bash
   # production -- only once step 6 has passed on staging
   aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-production/hub-reviews --type String --value on
   ```

   Writing the parameter changes nothing by itself: the container reads
   its runtime env, which only a release writes.
5. **Dispatch a deploy** of the same environment (`Actions -> deploy ->
   Run workflow`; any ref already deployed will do). The release
   validates the value (`on` or `off`, nothing else), writes
   `SHIKKHOKPLUS_HUB_REVIEWS` into the runtime env, and the application
   reads it at each call.
6. **Check that a seeded batch page in staging shows the reviews
   section.** Open a published batch page on the staging site,
   `{site}/hub/en/t/<owner>/<batch>`: it must now carry a **Reviews**
   heading. With fewer than three published reviews the section reads
   "Ratings appear once a class has 3 reviews."; with the switch off
   there is no heading at all. The staging seeder publishes no listing,
   so sign in as a seeded teacher (`deploy/README.md`, "Seeding test
   data") and publish their listing and one batch first. Batch pages are
   cached at the edge for up to ten minutes (`s-maxage=600`), so open one
   not fetched since the deploy, or wait.

**Switching off is the same with `off`**: write `off` to the parameter and
dispatch a deploy. It hides every review surface — sections, ratings,
the sort choice, the teacher's and the admin's review routes — and stops
the weekly publication, but **never blocks a deletion**, and it deletes
nothing: the reviews come back as they were when it is turned on again.
Cached pages keep showing reviews for up to ten minutes (search pages
five). Switch off without waiting for the D-steps whenever a safety
reason calls for it; the admin overview's pull-reviews figure (more than
5% of public reviews reported in a quarter, hub spec §9) is one.

## Switching join requests on

Hub join requests ("Ask to join") are **off** until someone turns them
on, in every environment, and the switch is independent of the reviews
switch. It is one SSM parameter per environment, a plain `String`
holding exactly `on` or `off`:

| Environment | Parameter |
|---|---|
| staging | `/shikkhokplus/shikkhokplus-staging/hub-enquiries` |
| production | `/shikkhokplus/shikkhokplus-production/hub-enquiries` |

Its name is `/shikkhokplus/${var.name_prefix}/hub-enquiries`
(`modules/app/deployment_state.tf`) with `name_prefix =
"shikkhokplus-${var.environment}"` (`main.tf`), the same path the release
reads (`ses_param hub-enquiries` in `deploy.yml`);
`tests/gates/test_hub_enquiries_switch_infra.py` keeps the table and the
commands below equal to it. Terraform creates it `off` and ignores its
value afterwards, so an apply never changes it.

**The parameter must exist before anyone writes to it.** It is created
when you apply `infra/` with H5's change, which the first deploy of an
H5 ref does: its `infrastructure` job applies before the release reads
the switch ("Terraform runs in GitHub Actions" above). Writing `on` to a
name that does not exist yet creates a parameter outside Terraform's
state, which the next apply then fails on, so check with `aws ssm
get-parameter --name <path>` first.

**The deploy role must be able to read it.** Every release reads the
switch, on or off, so if the last deploy succeeded this is already true.
If a release stops at "Cannot read the hub join requests switch",
re-apply `bootstrap/` once from a laptop: H5 added `hub-enquiries` to the
parameters the deploy role may read (`bootstrap/deploy_role.tf`). The
release stops before changing anything.

**Turning it on lets a guardian's own words reach a teacher**, which the
project's rules forbid as they stand, so each step below is a human
check, done in this order, and a step that is not met stops the list.
Steps 3 to 5 run on staging first; production repeats steps 3 and 4 only
after step 5 has passed on staging. No step reads production data by
hand.

1. **The `project.md` rule is amended first.** Its Forbidden rule
   beginning "NEVER expose anything a student or guardian writes to any
   teacher" forbids join requests as worded: a request is written by a
   guardian to a teacher. The owner amends it **through the learnings
   ritual** (AI-DLC's human-gated learnings write path), never by
   editing `aidlc/spaces/default/memory/project.md` by hand, and the
   runbook does not do it for them. Its first sentence becomes:

   > NEVER expose anything a student or guardian writes to any teacher,
   > except a hub review its author explicitly submitted for public
   > display, and a join request a guardian explicitly sent to that
   > owner, which only that owner's managers see, never with the
   > guardian's contact unless they chose to share it on that request.

   The rule's existing review clauses ("Such a review reaches anyone
   ...", to "deletion is total.") stay as they are, after it. If the
   owner declines the amendment, stop here: the switch stays `off`.
2. **D6: the declarations are published.** The Play Data Safety form and
   the Families target-audience declaration have been updated against
   `docs/legal/README.md` item 6 ("New: join requests") and the Families
   note, and the privacy policy on `main` describes join requests
   (`docs/legal/PRIVACY.md`, "Join requests"). The site's sentences
   saying a teacher cannot see what a guardian writes (the home page and
   the FAQ, in English and Bangla) carry the same "where join requests
   are offered" exception, so the site needs no change; check only that
   the site released to the environment is from H5 or later. The policy
   promises an in-app notice before a material change takes effect; this
   is one, and nothing in the app sends such a notice, so decide how it
   is given and give it before step 3 on production.
3. **Write `on`** to the environment's parameter. **Staging first**, then
   steps 4 and 5 on staging:

   ```bash
   # staging
   aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-staging/hub-enquiries --type String --value on
   ```

   **Production only after step 5 has passed on staging**, followed by
   step 4 on production:

   ```bash
   # production -- only once step 5 has passed on staging
   aws ssm put-parameter --overwrite --name /shikkhokplus/shikkhokplus-production/hub-enquiries --type String --value on
   ```

   Writing the parameter changes nothing by itself: the container reads
   its runtime env, which only a release writes.
4. **Dispatch a deploy** of the same environment (`Actions -> deploy ->
   Run workflow`; any ref already deployed will do). The release
   validates the value (`on` or `off`, nothing else), writes
   `SHIKKHOKPLUS_HUB_ENQUIRIES` into the runtime env, and the application
   reads it at each call.
5. **Check in staging that a seeded owner with requests on shows "Ask to
   join", and that a test guardian's request reaches the owner's
   inbox.** The staging seeder publishes no listing, so sign in as a
   seeded teacher (`deploy/README.md`, "Seeding test data"), publish
   their listing and one batch, and turn on **Receive join requests**
   for the listing (the choice appears only once the switch is on).
   Their page on the staging site, `{site}/hub/en/t/<owner>`, must now
   carry an **Ask to join** link; with the switch off there is none.
   Owner and batch pages are cached at the edge for up to ten minutes
   (`s-maxage=600`), so open one not fetched since the deploy, or wait.
   Then sign in as one of the family numbers the seeder's `seed.json`
   lists, follow the link, send a request with **Share** chosen, and
   check that a "New join request" item reaches the teacher's inbox and
   that the request, opened from it, shows the family number. Withdraw
   it from the guardian's side afterwards; the teacher's copy goes with
   it.

**Switching off is the same with `off`**: write `off` to the parameter
and dispatch a deploy. It removes every "Ask to join" link and the
owner's join-request routes, but **never blocks a deletion** and deletes
nothing: guardians can still read and withdraw the requests they sent,
every request is still purged 90 days after it was sent, and the
owner's join requests list shows the rest again if the switch is turned
back on before then. Cached pages keep showing the link for up to ten minutes; a
request sent from one is refused. Switch off without waiting for
anything whenever a safety reason calls for it.

## Reading the outputs

The apply job writes `api_url`, `app_static_ip` and
`cloudfront_domain` to its **job summary**. That is the normal way to
read them.

The **origin secret is deliberately not printed there** — a CI log
persists for 90 days, and that value lets anyone bypass the CDN. To
read it you need the state, which means authenticating locally:

```bash
cd infra
terraform init -backend-config="bucket=<the state bucket>"
terraform output -raw origin_secret
```

That is a deliberate speed bump rather than an oversight: the secret is
already on the origin host, written by `user_data`, so you only need it
if you are reconstructing nginx by hand.

## Deploying the application

Terraform provisions the **machine** and never the **release** —
`user_data` runs once at first boot, so using it to deploy would make
every release require a new instance.

```bash
aws ssm start-session --target <app_instance_id>
sudo su - ubuntu
# then the six-step ordering in ../deploy/README.md
```

**The image must be built for arm64.** t4g is Graviton, and an x86
image fails at `docker run` with an exec format error that does not
mention architecture:

```bash
docker build --platform linux/arm64 -t shikkhokplus-backend .
```

## State

**S3, created by `bootstrap/`.** Versioned, encrypted, all public
access blocked. Local state cannot work for CI: a runner's filesystem
is discarded when the job ends, so the next run would not know which
resources exist and would try to create a Lightsail instance that is
already there.

Locking is `use_lockfile` — S3-native, Terraform 1.10+. That replaces
the DynamoDB table older setups needed: one fewer resource to
provision, pay for and secure.

**State holds the origin secret and, in Phase 2, the database password
in plaintext.** The local-state patterns remain gitignored — verified
with `git check-ignore`, not assumed — in case anyone runs Terraform
locally by accident.

## Authentication

**OIDC, no stored AWS keys.** A one-hour token per run, scoped to this
repository and branch. An access key in GitHub secrets never expires,
cannot be rotated without a human remembering, and is usable by anyone
who can edit a workflow file.

## What is deliberately absent

| Not here | Why |
|---|---|
| **ALB** | A third of the budget before any compute, for 100 teachers on one instance [D-29] |
| **SSH, bastion, key pairs** | Session Manager replaces all three, and leaves no inbound port to misconfigure |
| **NAT gateway** | USD 32/month — more than both instances — to avoid public IPs on hosts whose inbound is closed anyway |
| **Scaling** | The auto-scaling group is desired-one with no policy. It exists so a failed host is replaced and a deploy can launch before it terminates [OPS-6] |
| **WAF** | USD 5/month plus per-rule charges, for an API authenticated on 10 of 11 routes, where the OTP ceilings already live in the application |
| **Multi-AZ RDS** | Doubles the database cost for a failover this scale does not justify |
| **CloudWatch dashboards and paging** | Alarms exist (CRITICAL log lines, no host in service, status checks, certificate age, RDS storage, CloudFront 5xx) and email one SNS topic. Nothing pages; an unconfirmed email subscription means nothing is delivered -- see the `alert_email_status` output |

## Scaling path, when it is needed

Each step is additive — none requires re-architecting what is here:

1. **Bigger instance.** `instance_type = "t4g.medium"` (4 GB, USD 27).
   One variable.
2. **A second app instance + ALB.** The application is already
   stateless — sessions are JWTs and rate limits are datastore-backed
   precisely so a second worker, or a second host, changes nothing.
3. **Caching.** The cache policy becomes a per-route decision once
   there is anything safe to cache. CloudFront is already there.
