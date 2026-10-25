# Infrastructure

Terraform for the Phase 1 backend. **USD 32.84/month** against the USD
50 ceiling [OC-4], with the Phase 2 path to RDS written and disabled.

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

Phase 1 still keeps Postgres on the box: a database bound to
`127.0.0.1` is exposed to nothing, and the reason to pay for RDS is
automated backups and PITR, which is a Phase 2 concern.

> **Phase 2 fits, and the collision this note used to claim was an
> arithmetic error.** Staging plus RDS is **USD 47.28** against the
> USD 50 ceiling — 2.72 of headroom. Until 2026-10-24 this read
> "USD 50.20" and said Phase 2 meant retiring the rehearsal host or
> raising the budget; neither is required. The `precondition` still
> blocks an apply that genuinely crosses the ceiling, computing from
> `cost_breakdown` rather than from a number written in prose.
>
> | configuration | USD/month |
> |---|---|
> | app only | 15.26 |
> | + staging | 29.92 |
> | + RDS | 32.62 |
> | + staging and RDS | 47.28 |

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

1. Edit `infra/**` on a branch, open a PR
2. The plan appears as a PR comment
3. Merge
4. Actions → terraform → Run workflow → **apply** → approve

**ACM validation takes 5–30 minutes** on the first apply, and
CloudFront another 10–15. The job's 45-minute timeout exists for that.
It is not a hang.

### Why apply is manual

A Terraform run can replace the Lightsail instance, and in Phase 1 that
**destroys the containerised Postgres with it** — a database whose only
backup is `pg_dump`. Auto-applying on merge would make a routine merge
capable of losing teacher data.

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
| **Auto-scaling group** | One instance is the design; a group of one implies a capability we do not have |
| **WAF** | USD 5/month plus per-rule charges, for an API authenticated on 10 of 11 routes, where the OTP ceilings already live in the application |
| **Multi-AZ RDS** | Doubles the database cost for a failover this scale does not justify |
| **CloudWatch alarms** | U3 shipped six alerts in the application; duplicating them here would mean two places to change one threshold |

## Scaling path, when it is needed

Each step is additive — none requires re-architecting what is here:

1. **Bigger instance.** `instance_type = "t4g.medium"` (4 GB, USD 27).
   One variable.
2. **RDS.** `enable_rds = true`. The ingress rule already references
   the app's security group, so nothing about the network changes —
   only the app's database URL.
3. **A second app instance + ALB.** The application is already
   stateless — sessions are JWTs and rate limits are datastore-backed
   precisely so a second worker, or a second host, changes nothing.
4. **Caching.** The cache policy becomes a per-route decision once
   there is anything safe to cache. CloudFront is already there.
