# Reliability Requirements — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **No availability target, because any number would be dishonest.** Phase 1
> is one Lightsail instance with containerized Postgres: no multi-AZ, no
> load balancer, no standby. An instance restart is a total outage. "99.9%"
> would be a figure nobody could defend and nobody could act on.
>
> This Unit cannot be highly available at this budget. So the requirements
> are about **recovering quickly and knowing the state**, not about not
> failing — which is the honest form available here.

## Sources

- [stage] `nfr-requirements-questions.md` — Q2
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR5.3
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7, NFR8
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1
- [team] `## Deployment`
- [project] `## Mandated`

---

## A. Knowing the state

| ID | Requirement |
|---|---|
| **NFR6.4** | A **health endpoint** reporting database connectivity and the applied Alembic revision |
| **NFR6.8** | The post-deploy smoke set covers the skeleton path end to end: OTP issue, verify, authenticated lens resolution |

> The health endpoint answers *"is it up, and is it the version I
> shipped"* — which is what makes a deploy's smoke test meaningful rather
> than decorative.

## B. Recovering

| ID | Requirement |
|---|---|
| **NFR6.5** | **Deploys are scheduled outside Bangladesh classroom hours** |
| **NFR6.6** | A **verified** `pg_dump` to S3 before any production migration, with object existence and non-trivial size asserted after upload |
| **NFR6.9** | Rollback is redeploying the previous immutable image tag; `latest` is never deployed |
| **NFR6.10** | Migrations are forward-only and backward-compatible, run as a distinct logged step before the new container serves traffic |

> **NFR6.5 is a reliability requirement expressed as a scheduling
> constraint**, which is the only form available at this budget.
> Recreate-style deployment means a restart window, and a dropped
> attendance write during a live class is the failure a teacher will not
> forgive.
>
> **NFR6.6 is two requirements in one sentence.** An untested backup is not
> a backup — and an *unverified upload* is not one either, which is the
> half usually skipped. The database is the thing that cannot be rolled
> back.

## C. Failing well

| ID | Requirement |
|---|---|
| **NFR10.4** | A database connection failure **fails fast inside a request**, with no retry |
| **NFR10.3** | One transaction per request, committed by the endpoint and never by a repository method |
| **NFR13.3** | A gateway timeout is `UNKNOWN`, never `FAILED`, and is never retried [BR5.3] |

> **NFR10.4 is counter-intuitive and deliberate.** A 2 GB instance under
> connection pressure gets *worse*, not better, if every request retries.
> Failing fast sheds load; retrying amplifies it.
>
> **NFR13.3** is the gateway's unavoidable consequence: BulkSMSBD offers no
> delivery report and no message id, so a timeout genuinely cannot be
> distinguished from a delivery. Retrying would double-charge and
> double-message.

---

## Assumptions & Open Questions

**None.** [assumption] The absence of an availability SLO is recorded as a
decision. It becomes statable when Phase 2 introduces RDS and a second
instance class; at Phase 1 it would be fiction.
