# Tech Stack Decisions — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **Most of the stack is inherited.** Python 3.12, FastAPI, Pydantic v2,
> pytest, Ruff, mypy, `uv.lock` from B1; the error taxonomy, the `Lens`
> types and the committed contract from B2. Re-litigating them would be
> ceremony.
>
> **Six decisions are genuinely this Unit's**, and they arrive together
> because this is the first Unit with a database, a network boundary and a
> screen. One of them changed when it was measured.

## Sources

- [stage] `nfr-requirements-questions.md` — Q3, Q5, Q6
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR2.1, BR2.4, BR4.2, BR5.1–BR5.5
- [upstream] `construction/money-core/nfr-requirements/tech-stack-decisions.md` — the inherited B1 stack
- [upstream] `inception/contract-design/contract-summary.md` — §B.3, §C.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12, NFR13
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.8
- [team] `## Deployment`, `## Testing Posture`, `## Walking Skeleton`
- [project] `## Forbidden` / `## Mandated`

---

## A. The decisions

| # | Decision | Alternative rejected |
|---|---|---|
| A.1 | **HMAC-SHA256 under a server-held key** for the OTP | A bare digest; or bcrypt/argon2 |
| A.2 | **PostgreSQL rows** for rate-limit counters | An in-process dict; Redis |
| A.3 | **Alembic from zero** in the test container | Loading a schema dump |
| A.4 | **testcontainers with real PostgreSQL 16** | SQLite |
| A.5 | **PyJWT with a `kid` header** and two valid keys | A single-key verifier |
| A.6 | **`httpx` with explicit timeouts**, no retry transport | `requests`; any retrying client |

---

### A.1 — HMAC for the OTP, and why the obvious answer was wrong

**Measured on this machine rather than reasoned about:**

| Scheme | Cost per issue | Offline exhaustion of 10⁶ |
|---|---|---|
| SHA-256 | ~0.1 µs | **0.07 seconds** |
| bcrypt cost 8 | 15 ms | 4 hours |
| bcrypt cost 10 | 58 ms | 16 hours |
| **HMAC-SHA256 + key** | **~1 µs** | **impossible without the key** |

The threat is real: a 6-digit code has 10⁶ possibilities, so a leaked table
under a bare digest falls in under a tenth of a second, and BR2.3's attempt
ceiling does nothing about it — that defends the *online* path only.

**But a password hash is the wrong tool.** bcrypt is designed for secrets
drawn from a large space, where slowing each guess is the only available
lever. Against a 10⁶ space it buys hours, and costs 15–60 ms of CPU on
**every OTP issue** on a 2 GB instance that also has to resolve a lens on
every request.

HMAC under a key held outside the database **defeats the offline attack
outright** rather than delaying it, at a thousandth of the cost. The key is
one of the three named secrets, with an exercised rotation runbook.

> **This decision reversed under measurement**, and the first version read
> as more security-conscious. Recorded so the reasoning survives: the
> instinct identified the right threat and reached for a tool shaped for a
> different one.

### A.2 — Counters in PostgreSQL, not Redis

The obvious answer is Redis — it is what rate limiting usually uses, and it
is faster. It is rejected for a budget reason and kept out for a simplicity
one:

- **Budget**: another managed service against a USD 50/month ceiling that
  already carries two Lightsail instances.
- **Correctness**: an atomic upsert under a unique constraint on
  `(scope_kind, scope_value, window_start)` gives exactly the property
  NFR10.2 needs, in the datastore that already exists.
- **One failure domain**: a counter in a second store can disagree with the
  database about whether a send happened.

A per-process dictionary is rejected outright — it is NFR10.1, and the
reason is correctness rather than scale.

### A.3 — Alembic from zero in the test container

The container migrates with Alembic from an empty database rather than
loading a schema dump. That gives the migration path **continuous
exercise at no extra cost**, which matters more than usual here: the fee
model is known to be changing, and there is no failover.

### A.4 — Real PostgreSQL 16, never SQLite

`team.md` already requires this and the reason is specific to this Unit:
**row-level security, `ON CONFLICT DO NOTHING` and partial indexes are the
behaviours under test**, and SQLite emulates none of them faithfully. A
privacy suite against SQLite would pass without RLS existing at all.

### A.5 — PyJWT with `kid` and two valid verification keys

Rotating the signing key without `kid` support force-logs-out every holder
of a 30-day refresh token, at exactly the moment rotation is needed. It
costs almost nothing now and is a mass-logout incident to retrofit later,
which is why `team.md` pulls it into the skeleton.

### A.6 — `httpx` with explicit timeouts and no retry transport

- **Explicit connect (~5 s) and read (~10–15 s) timeouts**, never a library
  default and never unbounded. An unbounded gateway call blocks a Uvicorn
  worker, and on a 2 GB instance with few workers that is a self-inflicted
  availability incident.
- **No retry transport, configured off deliberately.** There is no
  idempotency key and no message id, so a retry double-charges and
  double-messages. The most-installed community client for this gateway
  ships exponential-backoff retries; it must not be copied.

---

## B. Inherited, and one thing that arrives here

**Inherited unchanged from B1 and B2**: Python 3.12, FastAPI, Pydantic v2,
pytest, Ruff with its named rule sets, mypy with `disallow_untyped_defs`
globally, `uv.lock`, Gitleaks; the five-class error taxonomy with its
single handler, the `Lens` type hierarchy, the shared annotation resolver,
and the committed OpenAPI contract with `make openapi`.

**`app.authz.*` becomes the third strict mypy island here**, completing the
set `team.md` names. B1 configured `app.money.*`; B2 added `app.schemas.*`
when it first populated that package; U3 creates `app.authz` resolvers, so
its override lands now. Lens resolution is pure branching over three lens
types and owned-batch membership — exactly the code where an implicit `Any`
would hide an authorization hole.

**Arriving with this Bolt by `team.md`'s sequencing**: testcontainers,
Alembic, and the restricted database role.

---

## C. What this Unit establishes for later Bolts

- **The lens resolver as a FastAPI dependency** — every later Unit's routes
  depend on it, and U2's route harness checks they do.
- **The migration baseline.** Every later migration builds on this one, and
  the from-zero test path exercises all of them.
- **The restricted test role**, without which no later privacy suite means
  anything.
- **The adapter pattern with its null default** — the shape any later
  third-party boundary follows.

---

## Assumptions & Open Questions

**One, and it is a value rather than a decision.** [assumption] The global
daily SMS ceiling's number derives from BulkSMSBD's per-SMS rate against
the USD 50/month budget. The requirement is that it exists, is configured
rather than hardcoded, and is derived from the budget; tests exercise the
mechanism at a test-configured threshold.
