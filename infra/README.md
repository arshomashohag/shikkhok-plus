# Infrastructure

Terraform for the Phase 1 backend. **USD 24.50/month** against the USD
50 ceiling [OC-4], with the Phase 2 path to RDS written and disabled.

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
                    │  Lightsail   │  2 GB, static IP
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

### 3. Postgres is on the app host, not RDS — in Phase 1

You asked for RDS in a public subnet with ingress only from Lightsail.
That is **not expressible as stated**: RDS security groups reference
CIDRs or other security groups, and Lightsail instances live outside
your VPC with no security group to name.

The three real options, and why this one:

| | Exposure | Traffic path | Cost |
|---|---|---|---|
| **Postgres on the host** | none | localhost | $24.50 |
| RDS private + peering | none | private | $41.86 |
| RDS public + /32 | public endpoint | **leaves AWS, re-enters** | $41.86 |

A public-subnet RDS reachable from one IP is **weaker than keeping the
database on the box**, and the traffic carries children's names,
attendance and marks. `project.md` mandates encryption at rest; it does
not require a publicly resolvable endpoint.

`modules/database` is written and disabled. Phase 2 is
`enable_rds = true` plus Lightsail VPC peering — and it provisions a
**private** subnet, never a public one.

---

## First run

```bash
# 1. A key pair, once. Terraform does not create one: that would put
#    the private key in state, and state is a file on disk.
aws lightsail create-key-pair --key-pair-name shikkhokplus \
  --query 'privateKeyBase64' --output text > ~/.ssh/shikkhokplus.pem
chmod 600 ~/.ssh/shikkhokplus.pem

# 2. Your variables.
cp terraform.tfvars.example terraform.tfvars
curl -s https://checkip.amazonaws.com   # your IP, for operator_ip_cidr

# 3. Read the plan before applying it.
terraform init
terraform plan

terraform apply
```

**ACM validation takes 5–30 minutes** on the first apply, and
CloudFront takes another 10–15 to deploy. The apply blocks on both.
That is not a hang.

## After apply

```bash
terraform output api_url              # build the Android client against this
terraform output app_static_ip        # ssh here to deploy
terraform output -raw origin_secret   # when nginx needs it again
terraform output monthly_cost_estimate
```

Then deploy the application itself — Terraform provisions the machine
and never the release:

```bash
ssh -i ~/.ssh/shikkhokplus.pem ubuntu@$(terraform output -raw app_static_ip)
# then the six-step ordering in ../deploy/README.md
```

## State

**Local, deliberately.** A solo operator with one workstation does not
need S3 plus DynamoDB locking, and an unused state bucket is a thing to
secure for no benefit. Uncomment the `backend "s3"` block in
`versions.tf` when a second person or a CI runner applies.

**State holds the origin secret and, in Phase 2, the database password
in plaintext.** It is gitignored — verified, not assumed. If you move
to S3, enable encryption and versioning on the bucket.

## What is deliberately absent

| Not here | Why |
|---|---|
| **ALB** | A third of the budget before any compute, for 100 teachers on one instance [D-29] |
| **Auto-scaling group** | One instance is the design; a group of one implies a capability we do not have |
| **WAF** | USD 5/month plus per-rule charges, for an API authenticated on 10 of 11 routes, where the OTP ceilings already live in the application |
| **Multi-AZ RDS** | Doubles the database cost for a failover this scale does not justify |
| **CloudWatch alarms** | U3 shipped six alerts in the application; duplicating them here would mean two places to change one threshold |

## Scaling path, when it is needed

Each step is additive — none requires re-architecting what is here:

1. **Bigger instance.** `instance_bundle = "medium_3_0"` (4 GB,
   USD 24). One variable.
2. **RDS.** `enable_rds = true` plus VPC peering. The app's database
   URL changes; nothing else does.
3. **A second app instance + ALB.** The application is already
   stateless — sessions are JWTs and rate limits are datastore-backed
   precisely so a second worker, or a second host, changes nothing.
4. **Caching.** The cache policy becomes a per-route decision once
   there is anything safe to cache. CloudFront is already there.
