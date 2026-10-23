# Scalability Design — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> At 100 teachers and a few thousand students on one Lightsail host, the
> scaling design is mostly a statement of what the product does **not** need.
> The one real design decision is that signup's ceilings are a capacity
> control and not only an abuse control — because D1 is the unit that lets the
> public grow a table.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-requirements/scalability-requirements.md`
  — NFR6.20–NFR6.25, NFR7.5
- [upstream] `construction/signing-up-and-joining/nfr-requirements/security-requirements.md`
  — NFR12.4, NFR12.5
- [code] `app/auth/ceilings.py`, `app/governance/dispositions.py`, read 2026-10-23

---

## 1. Scaling architecture

| Axis | Design | Why not more |
|---|---|---|
| **Horizontal (app)** | Two Uvicorn workers on one host, as built | NFR6.20 fixes the ceiling at 100 teachers; a second host costs more than the budget allows [NFR7.5] |
| **Vertical** | The Phase 2 path, not this unit's | Raising the instance is the lever that exists if the ceiling moves |
| **Database** | Single PostgreSQL, no read replica | At this scale the hot query runs at 0.20 ms with index-only scans |
| **Partitioning / sharding** | None | A shard key is a decision that is expensive to reverse; nothing justifies one |
| **Queue-based decoupling** | None | The only async-shaped work is the OTP send, which is fire-after-commit |

**Stateless by construction.** The app holds no session state: tokens are
JWTs, the lens is resolved per request, and the only per-request state is a
memo on the request object. That is what makes two workers safe and three
equally safe, and it is the property D1 must not break.

### What D1 could have broken and does not

| Temptation | Why it would break multi-worker | Design |
|---|---|---|
| In-process signup counters | Worker A's count is invisible to worker B | Datastore-backed [NFR12.5] |
| A cached lens summary | Two workers, two stale views | Forbidden [NFR21.1] |
| In-memory OTP readback | Already learned: the built outbox is a table for exactly this reason | Unchanged |

The outbox module records the general form: an in-memory version "would work
in a single-worker test and fail about half the time on a real host". D1
inherits that rule rather than rediscovering it.

---

## 2. Growth, and the control that bounds it

**Before D1 the account table's growth rate was zero** — a row existed only if
somebody typed SQL. After D1 it grows at whatever rate the public can reach
it.

That makes the signup cascade a **capacity control as well as an abuse
control** [NFR6.21], and it is the reason NFR12.5 (counters in the datastore)
is a scalability requirement and not only a security one: a per-process
counter under two workers limits nothing, so the capacity bound would not
exist either.

### Capacity model

| Table | Growth driver after D1 | Bound |
|---|---|---|
| `account` | Public signup | Signup ceilings [NFR6.21] |
| `profile` | One per account, from creation | Follows `account` [BR3.3] |
| `owner` | One per teacher signup | Follows `account` |
| `enrollment` | Teacher action, unchanged | [NFR6.20] |
| `rate_limit_counter` | Both cascades, unauthenticated traffic | 48h declared, **unenforced** [NFR6.22] |
| `auth_audit_log` | Signup events added | 12-month retention class, no purge job |

**`profile` changes shape rather than size.** It was optional and populated on
first edit; now every account has one from creation. The row count is the same
order of magnitude and the *assumption a reader may make* is not — which is
why BR3.3 makes the two-row creation one transaction.

### The one real gap

`rate_limit_counter` carries a declared disposition — `HARD_DELETE` at
`HOURS_48`, with the stated basis that the longest window is a day so 48 hours
covers every live counter — and **no job enforces it** [NFR6.22].

The design does not invent one here: a scheduled purge is infrastructure, D1
adds none [NFR7.5], and the team practice already names auth records as the
first data class to carry a scheduled purge. What this unit owns is naming
that it enlarges the table.

---

## 3. Concurrency design

| Race | Converges because | Requirement |
|---|---|---|
| Two signups on one number | `Account.phone` is unique; the constraint reports it and the second attempt is directed to log in | NFR6.23 |
| Two accepts on one link | The transition is idempotent in its target state | NFR6.24 |
| Two workers on one ceiling window | The upsert increments **then** compares, so neither can read a passing count | NFR6.25 |

**The pattern is the same in all three: a database-level guarantee, not an
application-level check.** This project's standing rule is that
"has this already happened" guards fail under concurrency, and all three of
these inherit the shape the fee-cycle idempotency rule established.

NFR6.25 is worth stating because it is the non-obvious one: a check-then-act
counter would let two workers both observe a passing count and both proceed,
which is the failure mode a rate limiter exists to prevent.

---

## 4. Capacity thresholds

No auto-scaling rules, and no invented thresholds. Phase 1 is a fixed host
with a fixed budget; the trigger to revisit is a **decision**, not a metric
crossing a line:

| Signal | Means | Action |
|---|---|---|
| Teacher count approaching NFR6.20's ceiling | The product outgrew its stated scale | Re-open the hosting decision, not an autoscaler |
| Sustained signup refusals | Likely enumeration, possibly real demand | Read the dashboard [NFR25.5]; a page would be wrong [NFR25.2] |
| `rate_limit_counter` row count rising | The unenforced retention is now material | The purge job |

**No numeric threshold is set for any of these**, because a number set now
would be derived from nothing — and this project forbids recording an
obligation without naming its verifier.

---

## Assumptions & Open Questions

- **Assumed**: Phase 1 stays at two Uvicorn workers on one Lightsail host.
  The stateless design means a third worker needs no change, which is the
  property worth having rather than a plan to add one.
- **Assumed**: no connection-pool resizing for D1. Signup is a low-volume
  write and the lookup is a bounded indexed read.
- **Open, and D5/D6's**: the Phase 2 topology — a separate RDS instance and
  the separate-database split. D1 neither assumes nor precludes it.
