# CI/CD Pipeline — D3 `collecting-fees`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3 needs no pipeline change to ship its schema, and it needs two things
> before it ships to production that the pipeline does not do today.**
>
> The migration path is built and runs on every boot. What is missing is the
> rehearsal host it should be rehearsed on, and the verified backup that should
> precede it — both inherited, both escalating here, because D3 is the first
> unit whose effects a rollback cannot undo.

## Sources

- [upstream] `construction/collecting-fees/nfr-design/reliability-design.md`
  § 8 — the migration, and what a rollback does and does not undo
- [upstream] `construction/collecting-fees/nfr-design/observability-design.md`
  § 1 — the heartbeat, whose absence the rehearsal would reveal
- [upstream] `construction/collecting-fees/nfr-design/security-design.md`
  §§ 5, 7 — the grant issued in the creating migration, and governance rows
- [upstream] `construction/collecting-fees/nfr-design/logical-components.md`
  § 5 — the two new import-boundary checks `make check` must carry
- [upstream] `construction/collecting-fees/nfr-design/performance-design.md`
  § 3 — the query verifier that runs in the suite
- [upstream] `construction/collecting-fees/nfr-design/scalability-design.md`
  § 3 — the concurrency test, which needs a real database
- [upstream] `construction/collecting-fees/nfr-requirements/tech-stack-decisions.md`
  § 6 — test tooling, unchanged and newly exercised
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  § 3 — the generation path a smoke step would drive; § 5, the claim path
- [prior] D1's and D2's `infrastructure-design/cicd-pipeline.md` — the smoke
  gap this unit inherits
- [upstream] `inception/domain-design/components.md` — its Governance section
  is the row shape the governance gate in § 3 checks for, and D3 adds no
  component to that catalogue
- [code] `.github/workflows/check.yml`, `.github/workflows/deploy.yml`,
  `Makefile`, `infra/modules/app/user_data.sh.tftpl`, read 2026-10-24

---

## 1. Where D3's work lands in the existing pipeline

**No new stage, no new job, no new workflow.**

| Stage | Trigger | D3's change |
|---|---|---|
| `check.yml` → `backend` | Every push | **More tests, same command** |
| `check.yml` → `android-unit` | Every push | D3's fee and payment screens |
| `deploy.yml` → `plan` | Manual dispatch | none |
| `deploy.yml` → `infrastructure` | Manual dispatch | **Only if cron is chosen** — a `user_data` diff |
| `deploy.yml` → `release` | Manual dispatch | none; the image is built the same way |
| Migration | Pipeline step **and** every boot | **Five new tables through the existing step** |
| Rollout | ASG instance refresh | none |
| Post-deploy | `/health` over SSM | **Should extend — § 4** |

### What `make check` runs for D3

`make check` is `lint typecheck test android android-quality`, and it is the
same entrypoint locally and in CI — the property this project treats as the
most important one in a solo build.

| Gate | D3's addition |
|---|---|
| `ruff format --check` / `ruff check` | D3's modules; the banned-api rule on raw `decimal` already covers them, because it is stated over paths |
| `mypy app` | D3's modules; `app.money` and `app.schemas` strict islands already apply |
| Money coverage, 100% branch [NFR23.8] | **`Money.format(locale)` is the one addition to the module and must not drop it below 100**, and the floor is never weakened to make a step pass |
| Backend floor, 80% line | D3's services and routes |
| Import gates | **Two new ones — § 2** |
| Schema-diff gate | **D3's new endpoints and error responses change `openapi.json`** |
| Governance test | **Fails until `job_heartbeat` has a disposition row — § 3** |
| Android unit, quality, coverage ratchet | D3's screens and mapping functions |

---

## 2. Two new mechanical checks `make check` must carry

`logical-components.md` § 5 asks for both, and names D3 as the unit that
installs them. The project's standing rule is that a practice naming a
mechanical control names the deliverable unit that installs it — and a
boundary with no check is a convention.

| Boundary | Check | Why it is not review-enforced |
|---|---|---|
| **Payments never inserts a ledger row** | An import or call-graph assertion that no Payments module writes `LedgerEntry` directly | Every money movement must pass through Fees' API inside one invariant; a direct insert bypasses the pairing that makes the ledger balance |
| **No feature package defines an FCM client** | An import-boundary assertion in the shape of the money module's | This is exactly what OQ-4 exists to prevent: D4 copying the adapter and shipping a second `UNREGISTERED` behaviour |

**Both have a working precedent in this codebase** — the money module's
banned-api rule and its pytest AST walk, each of which ships with a violation
fixture proving the check can fire. **The new checks should ship with the same
fixtures**, because a boundary check that has never failed is a check nobody
has confirmed works.

**These are cheap and they are D3's.** Absent them, the second rule is
enforced only by D4's author remembering, which is the failure mode the
Android toolchain gap already demonstrated in this project.

---

## 3. The one gate D3 will trip, and the fix

**`tests/db/test_governance.py` fails the moment the migration runs**, unless
`job_heartbeat` carries a disposition and a retention class.

The test iterates **live tables** (`:35`, `:45`) and asserts a declaration for
each, plus the reverse (`:56`). `observability-design.md` § 1.1 introduces
`job_heartbeat` as a fifth table while every requirement in D3 is written
against "the four new tables" [NFR10.15].

**This is a good failure.** It is the control working as designed, catching a
table nobody wrote a requirement for. The fix is one row; the point of
recording it is that Code Generation should write the row with the migration
rather than discovering it as a red suite.

**I confirmed this check can fail today rather than assuming it**: the test
reads the live schema through the restricted session fixture, so any table a
migration creates is in scope as soon as the migration has run.

---

## 4. Deploy

| Facet | Mechanism | D3's change |
|---|---|---|
| Trigger | **Explicit `workflow_dispatch`**, never on merge | none |
| Inputs | Environment, ref, `skip_migrations` | none |
| Concurrency | Per environment, **never cancelled mid-run** | none |
| Image | SHA tag, immutable repository, `latest` never deployed | none |
| Migration | Alembic as a distinct logged step, before serving | **Five tables through it** |
| Rollout | ASG instance refresh, re-running `user_data` | none |
| Post-deploy | `curl /health` over SSM; the deploy fails if it does not answer | **Should extend — § 4.2** |
| Rollback | Redeploy the previous SHA tag | **Incomplete for D3 — § 4.3** |
| Auth | GitHub OIDC, no long-lived keys | none |

### 4.1 `skip_migrations` does not skip migration

`deploy.yml:40`'s input is described as "Skip Alembic (the instance still
migrates at boot)", and that description is accurate and easy to misread. The
input skips **the pipeline's** migration step; `user_data.sh.tftpl:325` runs
`alembic upgrade head` on every boot regardless, and the rollout replaces the
instance.

**A reader who believed otherwise could think they had deployed D3's code
without its schema.** They would be wrong in the safe direction — the schema
arrives anyway — but the belief is worth correcting, because it would also
mean the migration ran without the plan step that prints what is about to be
applied.

### 4.2 The smoke gap finally becomes executable

The team practice names a post-deploy smoke set: OTP issue and verify,
authenticated lens resolution, **one read of a fee cycle**, and a health
endpoint reporting database connectivity and applied migration revision.

**What exists is `/health` over SSM.** D1 and D2 both recorded this gap and
neither could close the fee-cycle line, because fee cycles did not exist.

**D3 is where that line stops being aspirational.** The path
`functional-spec.md` § 3 describes — a generated cycle, read back through an
authenticated lens — is exactly what the practice names, and it is buildable
for the first time in this unit.

| Smoke step | Buildable before D3? | Now |
|---|---|---|
| Health + migration revision | Yes | Partly built (`/health`) |
| OTP issue and verify | Yes, since B3 | Still not in the deploy |
| Authenticated lens resolution | Yes, since B3 | Still not in the deploy |
| **One read of a fee cycle** | **No** | **Yes** |

**This design does not add the smoke set**, because three of its four lines
are not D3's and the choice of how far to extend it is the human's. It records
that the blocking reason for the fee line has gone.

#### 4.2a The smoke set would fail today, and that is the point of it

*(Added 2026-10-24, after a live diagnosis during this stage.)*

**No request has ever reached the staging application through the CDN.** The
origin returns 502 to every request, and the host's nginx access log is zero
bytes since the instance launched on 21 October.

The cause is a false premise in the infrastructure, not a fault in D3:
`infra/modules/cdn/main.tf:131` states that the origin "presents a
self-signed certificate which CloudFront does not validate for a custom
origin", and `user_data.sh.tftpl:9` builds on it ("certbot is ABSENT").
CloudFront **does** validate a custom origin's certificate. AWS documents
that it does not support self-signed origin certificates and returns 502 when
no certificate domain matches the origin domain. Demonstrated on the host:
with verification on, the handshake fails `no alternative certificate subject
name matches target host name 'origin.shikkhokplus.nirmatabd.com'`; with
verification off, nginx answers normally. The application itself is healthy
and returns 200 on `/health` locally.

**D3 introduces none of this and changes nothing about it.** It is recorded
here because this section is the one place in the unit that reasons about
requests arriving at the deployed system, and a reader planning the fee-cycle
smoke line would otherwise build a step that cannot pass for a reason having
nothing to do with fees.

It also settles the open question in § 4.2 more sharply than the cost
argument does. **The smoke gap is not a nice-to-have here: a smoke set of any
kind, even the single `/health` line through the CDN rather than over SSM,
would have caught this on the day it shipped.** `/health` over SSM tests the
container; it deliberately bypasses the path every real user takes. Three
units have now deployed behind an origin nobody could reach, and nothing in
the pipeline noticed, because nothing in the pipeline looks.

### 4.3 Rollback is incomplete for D3, in a way it was not for D1 or D2

| Unit | What a tag rollback restores |
|---|---|
| D1 | The previous image against additive columns the old image never selects |
| D2 | Everything — no schema moved at all |
| **D3** | **The previous image. Not the charges.** |

**The migration is additive**, so the previous application version runs
against the new schema and a tag rollback is a valid *code* rollback. Four of
the five tables are new rather than altered, so nothing the old image reads
has changed shape.

**What a rollback does not undo is a generated charge.** If the job runs and
the release is then rolled back, the fee cycles and ledger entries remain —
correctly, because they record obligations that were real. The ledger is
append-only; the remedy is a compensating entry, never a delete [BR3.3].

**This is the first unit in the record where "redeploy the previous tag" is
not a complete answer**, and it is the reason the two gaps in § 5 escalate
here rather than merely persisting.

### 4.4 Deploy timing

Deploys carrying D3 are scheduled outside Bangladesh classroom hours **and
outside the generation window** [NFR18.5, NFR20.22]. A restart during
generation kills a run mid-flight; per-enrollment commit granularity makes
that survivable, so colliding is avoidable rather than dangerous.

**Verifier: the person dispatching the deploy. Nothing automated prevents a
deploy landing inside the generation window**, and under the cron option the
window is written in `user_data.sh.tftpl` where a dispatcher would have to go
looking for it.

---

## 5. What must be true before D3 reaches production

Both are inherited, both were recorded by D1, and both are listed as D3's
because D3 is the unit that makes them consequential.

| Obligation | State | Why it escalates at D3 | Cost |
|---|---|---|---|
| **Staging enabled** [NFR19.28] | `enable_staging_instance` defaults `false` | Five new tables is the record's largest schema change and has nowhere to be rehearsed | **USD 14.66/month**, landing at 47.28 against the 50 ceiling |
| **Verified `pg_dump` to S3** [NFR19.27] | Nothing asserts one | D3's effects survive a code rollback; the database is the thing that cannot be rolled back | A pipeline step |

**The staging figure is computed, not quoted**: `cost_host` is
`12.26 + 30 × 0.08 = 14.66`, and the defaults-plus-staging total is 47.28 —
**under the ceiling, needing no change to `acknowledged_monthly_budget`**. The
budget guard's error message claims this configuration costs USD 50.20, which
the same file's own model does not produce; see
`infrastructure-specification.md` § 6.1.

**The backup assertion must assert, not just upload.** An unverified upload is
not a backup: object existence and non-trivial size are checked after the
upload, and a failed backup alerts [NFR19.27]. The alert caveat in
`monitoring-design.md` § 2 applies to this alert too.

**The rehearsal would also exercise something nothing else can.** The one
unproven thing in the absence-of-success design is whether its alert reaches
anybody, and a deliberate skipped-run rehearsal on staging is the named manual
check for it. That rehearsal needs a staging host.

---

## 6. Secrets in CI/CD

| Secret | Path | D3 |
|---|---|---|
| OTP HMAC key, JWT keys, SMS credentials | GitHub secret → `runtime.env` → SSM `SecureString` | unchanged |
| **FCM credentials** | **The same path, as another key in the same parameter** | **New** |
| AWS access | **OIDC**, no long-lived keys | unchanged |

The runtime file is written under `umask 077` and removed after upload; the
parameter is KMS-encrypted and read by `user_data` at boot. **D3 introduces no
new secret mechanism** — one more key in a parameter that already exists.

**Non-production holds test credentials**, so a staging reminder dispatches to
a test project rather than to a real device.

---

## 7. What D3 does not add

| Not added | Why |
|---|---|
| A new workflow, job or stage | The work lands in `check.yml` and `deploy.yml` as they are |
| A deployment strategy change | Recreate-style at one instance; blue/green needs a second host and an ALB |
| A feature flag system | Nothing in D3 needs dark-launching; the job is idempotent and the endpoints are additive |
| A separate migration pipeline | The distinct logged step already exists and already fails closed |
| An artifact store change | ECR, SHA-tagged, immutable |

---

## Assumptions & Open Questions

- **Assumed**: the generation job ships inside the same image as the API, so
  the release stage is unchanged and both scheduler options invoke one
  artifact.
- **Assumed**: D3's new endpoints and declared error responses change the
  committed `openapi.json`, so the schema-diff gate shows them as a reviewable
  diff — which is also the moment the published-but-unreferenced
  `ErrorEnvelope` stops being a stopgap [team: Code Style].
- **Assumed**: the Android coverage ratchet absorbs D3's screens the way D2's
  did; if it drops, the diagnosis is a glob catching a non-composable —
  narrow the glob, do not lower the floor.
- **Open, and the human's**: whether the `infrastructure` job sees a
  `user_data` diff, which follows entirely from the scheduler choice
  [`infrastructure-specification.md` § 3].
- **Open, and the human's**: enabling staging and adding the backup assertion
  before D3's production deploy [§ 5].
- **Open, and the human's**: how far to extend the post-deploy smoke set now
  that the fee-cycle line is buildable [§ 4.2].
