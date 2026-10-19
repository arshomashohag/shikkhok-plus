# Logical Components — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **One process, one database, one third-party boundary.** The component
> view matters here less for scaling than for **blast radius**: which
> failure takes what down, on an instance with no failover.

## Sources

- [stage] `nfr-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-requirements/security-requirements.md`
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.1–A.6
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
- [upstream] `inception/contract-design/contract-summary.md` — §C.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.8
- [team] `## Deployment`
- [project] `## Mandated`

---

## A. Components

| Component | Responsibility | Fails how |
|---|---|---|
| `app/auth/otp` | Issue and verify | Refuses; no data at risk |
| `app/auth/tokens` | JWT + rotation | Refuses; sessions end |
| `app/auth/ceilings` | The four counters | **Fails closed** — see A.1 |
| `app/auth/hashing` | The HMAC chokepoint | Fails closed; no code storable |
| `app/authz/resolve` | Lens resolution | **Fails closed** — no lens, no access |
| `app/authz/rls` | The session context | Fails closed; RLS denies |
| `app/gateway/*` | One call site | Degrades — `UNKNOWN`, no retry |
| `app/audit/log` | Append-only | **Must not fail the operation** — see A.2 |

### A.1 The ceilings fail closed, deliberately

If the counter table is unreachable, the ceiling cannot be evaluated — and
the choice is to **refuse the send** rather than allow it.

> That is the opposite of the usual availability instinct, and it is right
> here: a ceiling that fails open under database trouble is a ceiling an
> attacker can disable by causing database trouble. The cost of failing
> closed is that OTP issue is unavailable while the database is; the cost
> of failing open is an unbounded SMS bill. The budget is USD 50/month.

### A.2 The audit log must not fail the operation

The one component where a failure is **logged and not surfaced**. An audit
write that fails must not fail the authentication it was recording.

> This is the stated exception to "silent failures are not acceptable", and
> it is a genuine tension: an audit log that can be suppressed by causing
> write failures is weaker than one that cannot. The resolution is that the
> write failure is itself alerted — so it is silent to the *user* and loud
> to the *operator*.

---

## B. Blast radius

| Failure | Takes down | Survives |
|---|---|---|
| Database unreachable | Everything — one instance, one database | Nothing |
| Gateway unreachable | OTP **issue** only | Verify, refresh, every authenticated request |
| Gateway slow | Issue latency, bounded by an explicit timeout | The rest, since no retry amplifies it |
| HMAC key missing | OTP issue and verify | Refresh and authenticated requests |
| Ceiling table locked | OTP issue (fails closed) | Everything else |

> **The gateway row is the useful one.** A gateway outage is the most
> likely third-party failure and it degrades to "existing sessions keep
> working, new sign-ins do not" — which is the correct shape. Teachers
> mid-class are unaffected.

---

## C. Shared resources

| Resource | Shared by | Contention risk |
|---|---|---|
| The connection pool | Every request | **Real** — lens resolution queries on every request [NFR6.1 keeps it to one] |
| The counter rows | Every OTP issue | Low — distinct keys per number and window |
| The HMAC key | Issue and verify | None — read-only |

**No shared in-process state.** Deliberately: a single Lightsail host runs
several Uvicorn workers, so any in-process state is per-worker and
therefore wrong. That is why the counters are rows [NFR10.1] and the lens
memo is per-request [BR1.4].

---

## Assumptions & Open Questions

**None.** [assumption] Phase 2's component topology — RDS, a separate
instance class — belongs to Infrastructure Design.
