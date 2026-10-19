# Staging on Lightsail

> **Every command here is one you run.** I cannot create the instance,
> hold your AWS credentials, or accept the charges — so this is written
> as a runbook rather than a script that assumes access it does not
> have.
>
> Budget: Lightsail `small_2_0` is **USD 12/month**, bringing the Phase
> 1 total to roughly USD 25 against the USD 50 ceiling [OC-4, D-29].

## What you need first

- An AWS account with Lightsail access
- The `aws` CLI, authenticated (`aws sts get-caller-identity` answers)
- About 15 minutes

---

## 1. Create the instance

```bash
aws lightsail create-instances \
  --instance-names shikkhokplus-staging \
  --availability-zone ap-south-1a \
  --blueprint-id ubuntu_22_04 \
  --bundle-id small_2_0
```

`ap-south-1` (Mumbai) is the nearest region to Bangladesh, which
matters for the mid-class attendance path [TC-17].

**`small_2_0` is 2 GB RAM, and that figure is load-bearing**: it is the
instance size every performance decision in this project assumed
[team.md], and it is why lens resolution is memoized per request rather
than cached across them.

Wait for it to report `running`:

```bash
aws lightsail get-instance-state --instance-name shikkhokplus-staging
```

## 2. Open the ports

```bash
aws lightsail open-instance-public-ports \
  --instance-name shikkhokplus-staging \
  --port-info fromPort=443,toPort=443,protocol=TCP

aws lightsail open-instance-public-ports \
  --instance-name shikkhokplus-staging \
  --port-info fromPort=80,toPort=80,protocol=TCP
```

**Do not open 5432.** The database is reachable only from the instance
itself; `docker-compose.yml` binds it to `127.0.0.1` for the same
reason.

## 3. Give it a static IP

```bash
aws lightsail allocate-static-ip --static-ip-name shikkhokplus-staging-ip
aws lightsail attach-static-ip \
  --static-ip-name shikkhokplus-staging-ip \
  --instance-name shikkhokplus-staging
aws lightsail get-static-ip --static-ip-name shikkhokplus-staging-ip \
  --query 'staticIp.ipAddress' --output text
```

A static IP costs nothing while attached, and the SMS gateway may need
one allowlisted — which is an open vendor question recorded in B3.

## 4. Prepare the host

SSH in (`aws lightsail get-instance-access-details` gives you the key),
then:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
# log out and back in for the group to apply
git clone <your-repo-url> shikkhokplus && cd shikkhokplus
```

## 5. Write the environment file

```bash
cat > .env <<'ENVFILE'
SHIKKHOKPLUS_ENVIRONMENT=staging
POSTGRES_PASSWORD=<generate: openssl rand -base64 32>
SHIKKHOKPLUS_OTP_HMAC_KEY=<generate: openssl rand -base64 32>
SHIKKHOKPLUS_JWT_KEYS=k1:<generate: openssl rand -base64 32>
SHIKKHOKPLUS_JWT_ACTIVE_KID=k1
SHIKKHOKPLUS_SMS_APP_HASH=<11 chars from the Play release>
SHIKKHOKPLUS_GLOBAL_DAILY_SMS=50
# Absent selects the NULL gateway. Only the literal "bulksmsbd"
# selects the real, money-spending adapter -- fail-safe by design.
SHIKKHOKPLUS_SMS_ADAPTER=
ENVFILE
chmod 600 .env
```

> **`SHIKKHOKPLUS_ENVIRONMENT=staging`, not `production`.** The startup
> check only refuses a misconfigured *production* process. Setting
> `production` here would be more honest about the rigour but would also
> make staging refuse to start without real gateway credentials, which
> is the opposite of what staging is for.
>
> **The three generated secrets are not recoverable.** Losing the JWT
> key force-logs-out every holder of a 30-day refresh token; losing the
> OTP HMAC key invalidates every outstanding code. Record them in your
> password manager as you generate them, not afterwards.

## 6. Deploy

**The ordering is load-bearing** [B5 infrastructure-specification §B]:

```bash
# 1. Back up first. On the very first deploy there is nothing to back
#    up, and this is a no-op -- but run it anyway so the habit exists
#    before there is real data.
docker compose exec -T db pg_dump -U shikkhok shikkhokplus \
  > "backup-$(date +%Y%m%d-%H%M%S).sql" || true

# 2. Pull and start. NOT --build: the host runs the artifact CI
#    tested and pushed, never a rebuild of it. API_IMAGE is written
#    into .env by the deploy workflow.
docker compose pull && docker compose up -d

# 3. Migrate as a DISTINCT step, never on container start.
docker compose exec -T api alembic upgrade head

# 4. Smoke. A container that started is not a container that serves.
make smoke BASE_URL=http://localhost:8000
```

## 7. TLS, before the app talks to it

The Android client must not talk to a plaintext endpoint: the manifest
sets no `usesCleartextTraffic` and the backend is https-only by design.

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
# point a domain at the static IP first, then:
sudo certbot --nginx -d staging.yourdomain.example
```

Proxy `/` to `127.0.0.1:8000`. The container already runs with
`--proxy-headers --forwarded-allow-ips '*'`, so the real client IP
reaches the rate limiter rather than nginx's.

> **Without TLS the IP-based OTP rate limit counts nginx as every
> caller**, which turns a per-IP limit into a global one. That is why
> the proxy flags are in the image rather than left to the deploy.

---

> **This manual path is the fallback, not the normal one.** A deploy
> is `Actions -> deploy-staging -> Run workflow`: it builds, pushes a
> SHA-tagged image to ECR, delivers over SSM and polls `/health`.
> Follow the steps here only when that workflow cannot run.

## Rolling back

```bash
# Point .env at the previous image and restart. The ECR repository
# is IMMUTABLE, so a SHA is the artifact -- this redeploys exactly
# what ran before, rather than rebuilding it.
sed -i "s|^API_IMAGE=.*|API_IMAGE=<repo>:<previous-sha>|" .env
docker compose pull && docker compose up -d
```

Or simply dispatch `deploy-staging` with the earlier ref, which does
the same thing and records it.

**Never `--build` here.** A rebuild from an old commit resolves base
images and transitive dependencies afresh, so it produces a DIFFERENT
artifact from the one that ran -- which is the opposite of what a
rollback is for.

**Not `alembic downgrade`.** Migration `0002` raises on downgrade: it
can reverse its renames but cannot reconstruct which student a deleted
guardian row belonged to. The honest rollback for a schema change is
restoring the step-1 dump.

## What this does not yet have

| Missing | Why it matters |
|---|---|
| Automated deploy workflow | Every deploy is manual SSH today |
| Off-host backups | The dump sits on the same instance that holds the database |
| Real SMS | Staging uses the null gateway, so **nobody can sign in from a device yet** |

The last one is the open question: either BulkSMSBD sandbox
credentials, or a staging-only retrieval path for the code.
