# Reliability Design — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **This Unit cannot be highly available at this budget**, so the design is
> about failing in the right direction and knowing the state — not about
> not failing.

## Sources

- [stage] `nfr-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-requirements/reliability-requirements.md` — NFR6.4–NFR6.10, NFR10.3, NFR10.4, NFR13.3
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.6
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR5.3
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1
- [team] `## Deployment`
- [project] `## Mandated`

---

## A. Which direction each component fails

| Component | Direction | Why that direction |
|---|---|---|
| Ceilings | **Closed** | A ceiling that fails open can be disabled by causing database trouble |
| Lens resolution | **Closed** | No lens, no access. An authorization check that fails open is not a check |
| RLS context | **Closed** | An unset session variable denies, it does not permit |
| Gateway | **Degrades** | `UNKNOWN`, budget consumed, user offered a resend |
| Audit write | **Open, but alerted** | Must not fail the authentication it records |

> **The audit row is the uncomfortable one**, and it is a real tension: a
> log that can be suppressed by causing write failures is weaker than one
> that cannot. The resolution is that the failure is silent to the *user*
> and loud to the *operator* — the write failure itself alerts.

## B. No retry, anywhere on this path

```python
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
_TRANSPORT = httpx.AsyncHTTPTransport(retries=0)   # explicit, not default
```

- **The gateway**: no idempotency key, no message id, real money per
  attempt. A timeout is `UNKNOWN` because the SMS may have been delivered
  [BR5.3]. The most-installed community client for this gateway ships
  exponential backoff; it must not be copied.
- **The database**: a connection failure **fails fast inside a request**
  [NFR10.4]. A 2 GB instance under connection pressure gets *worse* if
  every request retries — failing fast sheds load, retrying amplifies it.

## C. Knowing the state

```python
@router.get("/health")
async def health() -> HealthResponse:
    """Liveness plus the applied migration revision."""
```

Answers *"is it up, and is it the version I shipped"* — which is what makes
the post-deploy smoke set meaningful [NFR6.4, NFR6.8].

## D. The database is what cannot be rolled back

- A **verified** `pg_dump` to S3 before any production migration, with
  object existence and non-trivial size asserted after upload [NFR6.6].
  An untested backup is not a backup; an unverified upload is not one
  either.
- Migrations forward-only, run as a **distinct logged step** before the new
  container serves traffic [NFR6.10].
- Rollback is redeploying the previous **immutable image tag**; `latest` is
  never deployed [NFR6.9].
- Deploys scheduled **outside Bangladesh classroom hours** [NFR6.5] — a
  dropped attendance write during a live class is the failure a teacher
  will not forgive.

## E. One transaction per request

Committed by the endpoint, never by a repository method [NFR10.3].
Otherwise a partial write becomes possible on the auth path — an
`OtpRequest` row without its counter increment, or a rotated token without
its audit row.

---

## Assumptions & Open Questions

**None.** [assumption] An availability SLO becomes statable at Phase 2 with
RDS and a second instance class. At Phase 1 it would be fiction.
