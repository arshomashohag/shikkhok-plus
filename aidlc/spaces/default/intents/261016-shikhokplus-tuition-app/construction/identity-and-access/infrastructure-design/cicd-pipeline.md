# CI/CD Pipeline — `identity-and-access` (U3)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

> **B1 designed this pipeline to grow and named exactly what B3 adds.** This
> document honours that rather than redesigning it: a PostgreSQL service
> container, the restricted role, and the first deployment path.
>
> It is also the first Bolt that **deploys**, so the second half of this
> document is new rather than incremental.

## Sources

- [stage] `infrastructure-design-questions.md`
- [upstream] `construction/money-core/infrastructure-design/cicd-pipeline.md` — §C, §F
- [upstream] `construction/identity-and-access/infrastructure-design/infrastructure-specification.md`
- [upstream] `construction/identity-and-access/nfr-design/reliability-design.md` — §C, §D
- [upstream] `construction/identity-and-access/nfr-design/security-design.md` — §D.1
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.3, A.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7, NFR17
- [upstream] `inception/domain-design/components.md` — the entity catalogue the
  migration realises
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
  — §2.6, the migration this stage provisions for
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.5
- [team] `## Deployment`, `## Testing Posture`
- [project] `## Mandated`

---

## A. What B3 adds to the backend job

```
┌─ backend (ubuntu-latest) ───────────────────────────────┐
│  B1: lint, typecheck, money tests, both import gates    │
│  B2: + OpenAPI diff gate, money-pattern assertion,      │
│       privacy assertion, route-enumeration harness      │
│  B3: + PostgreSQL 16 service container                  │ ← new
│      + Alembic from zero                                │ ← new
│      + the restricted role                              │ ← new
│      + the RLS meta-test, FIRST                         │ ← new
│      + the privacy probe suite                          │ ← new
│      + the money column type-and-precision assertion    │ ← B1's, inherited
└─────────────────────────────────────────────────────────┘
```

### A.1 The service container

```yaml
services:
  postgres:
    image: postgres:16
    env: { POSTGRES_PASSWORD: ci }
    options: >-
      --health-cmd pg_isready --health-interval 10s
      --health-timeout 5s --health-retries 5
```

**Real PostgreSQL 16, never SQLite** [A.4]. Row-level security,
`ON CONFLICT DO NOTHING` and partial indexes are the behaviours under test,
and SQLite emulates none of them — a privacy suite against SQLite would
pass without RLS existing at all.

### A.2 Ordering: the meta-test runs before the privacy suite

```
1. migrate from zero (Alembic)
2. create the restricted role
3. RLS META-TEST          ← must pass before step 4 runs
4. privacy probe suite
```

> **Step 3 is not a formality.** A superuser bypasses RLS entirely, and the
> default container connection is `postgres`. Without step 3, step 4
> passes identically whether the policy is correct, broken, or absent — so
> the strongest test obligation in the project would certify nothing. The
> ordering is the control.

### A.3 The assertion B1 authored and could not run

**The money column type-and-precision assertion** iterates the migrated
schema and asserts every money-carrying column has the exact declared type
and precision — **regardless of how it was created**.

> That last clause is the point: it catches a raw SQL migration or a
> string-typed column declaration, neither of which imports anything an
> import rule could ban. B1 authored it with no table to run it against;
> B3 is the first Bolt with a schema, and **B3's DoD already lists it**, so
> the obligation B1 recorded is discharged here rather than lost.

---

## B. The blocking suite still needs no secret

`team.md`'s most important property for a solo build, preserved:

| Needs a secret? | Component |
|---|---|
| No | Every test, including the full privacy suite |
| No | The gateway — **stubbed in CI** |
| No | The database — a service container |

A gate reproducible only by pushing is a gate that gets bypassed. A fresh
clone runs the complete gate immediately.

---

## C. Deployment — new at this Bolt

### C.1 The ordered sequence

```
1. build image, tagged with the COMMIT SHA        (never `latest`)
2. push to registry
3. pg_dump → S3, VERIFIED (existence + non-trivial size)
4. alembic upgrade head                            — a distinct, logged step
5. stop old container, start new
6. smoke: health, OTP issue, verify, lens resolution
7. on smoke failure → redeploy previous tag immediately
```

**Step 3 before step 4, and verified.** The database is the thing that
cannot be rolled back. An untested backup is not a backup — and an
unverified *upload* is not one either, which is the half usually skipped.
A failed backup **alerts**: it is a fatal operational event even though no
user notices.

**Step 4 is distinct from step 5.** Migrations never run as a side effect
of application start, because a failed migration must not leave a container
serving traffic against a half-migrated schema.

**Step 7 is a rollback, not an investigation.** Smoke failure on a live
system is not the moment to debug.

### C.2 What rollback can and cannot undo

| Undoable | Not undoable |
|---|---|
| The image — redeploy the previous SHA tag | **The migration** |

Which is why migrations are forward-only and backward-compatible: a
migration that cannot be rolled *forward* past a mistake is not merged.
This matters more than usual because the fee model is known to be changing
and there is no failover.

### C.3 Scheduling

**Production deploys happen outside Bangladesh classroom hours.** Recreate
deployment means a restart window, and a dropped attendance write during a
live class is the failure a teacher will not forgive [NFR6.5].

---

## D. The staging gateway, and the one real send

| Environment | Adapter | Spends money |
|---|---|---|
| CI | Stub | No |
| Staging | **Null adapter** (the default) | No |
| Production | BulkSMSBD | Yes |

**The ceiling and its alert are verified in staging** before the auth slice
reaches production [NFR7.4] — against the null adapter, which verifies
**our ceiling logic**, the part we wrote. It does not exercise the real
gateway, and that is stated rather than implied.

> **The gateway leg is verified exactly once**, at this Bolt's checkpoint,
> against production credentials with a single send to the developer's own
> number. BulkSMSBD has no sandbox, so there is no other way. It is the one
> place real money is spent before launch, and it is bounded and
> deliberate.

---

## E. Scanning, at two speeds

Unchanged from `team.md`, restated because this Bolt adds the first
secrets:

| Speed | What | On failure |
|---|---|---|
| **Blocks every push** | Gitleaks; dependency lockfile/checksum | No threshold, no exception |
| **Annotates every push** | Dependency CVEs, all severities | A PR comment |
| **Blocks at release** | Critical and High CVEs | Fix, or a dated written exception |

Four secrets now exist to leak — gateway credentials, the OTP HMAC key, the
JWT signing key, the database URL — so Gitleaks earns its place here more
than at B1 or B2.

---

## F. Obligations this stage records and cannot execute

1. **A static IP on both Lightsail instances.** If BulkSMSBD enforces IP
   whitelisting (code 1032), sends fail with what looks like an auth error.
   Free while attached to a running instance; costs nothing to do
   pre-emptively, and is an operational step rather than a pipeline one.
2. **The production HMAC key must exist before the first deploy.** Unlike
   the JWT key, there is no two-key grace period: rotating it invalidates
   every in-flight code, so it is generated once and recorded in the
   runbook at provisioning time.
3. **`SHIKKHOKPLUS_GLOBAL_DAILY_SMS` must be set before the first
   production deploy.** Added after review, which found that three
   documents independently called this number "a value set at
   deployment" while **none of them said who sets it, when, or what
   catches its absence**. The value derives from BulkSMSBD's per-SMS
   rate against the monthly budget.

   Unset, the code's **test default** silently becomes the production
   money ceiling. Too high is a budget risk; too low locks every
   legitimate teacher out for the rest of the day — and the second
   failure is indistinguishable from an attack in the alert channel.

   **This one is now mechanical rather than remembered**, which is what
   the other two items still are not: `app/config.py` refuses to start a
   production process with this variable unset, and reports it alongside
   every other missing production value so one deploy surfaces them all.
   The same check covers the SMS Retriever app hash, where an empty
   value renders a *valid* SMS that simply never triggers autofill.

---

## Assumptions & Open Questions

**None.** [assumption] Items 1 and 2 in §F are operational steps with
named owners rather than open questions. Item 3 was an operational step
and is now a startup assertion — the difference being that the first two
still fail at first use, while the third fails on the deploy.
