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
