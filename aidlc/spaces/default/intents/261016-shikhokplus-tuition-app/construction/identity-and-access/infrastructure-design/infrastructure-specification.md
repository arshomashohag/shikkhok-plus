# Infrastructure Specification — `identity-and-access` (U3)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

> **This Unit owns the first real infrastructure.** B1 shipped a library and
> B2 a contract — neither needed a database, a host or a secret. B3 needs
> all three, plus the one thing nothing before it required: **a deployed
> environment a human can point a phone at**.
>
> Everything here is sized against **USD 50/month total** [OC-4, NFR7], and
> the budget decides the topology rather than preference.

## Sources

- [stage] `infrastructure-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-design/security-design.md` — §A–§H
- [upstream] `construction/identity-and-access/nfr-design/reliability-design.md`
- [upstream] `construction/identity-and-access/nfr-design/logical-components.md`
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.2–A.4
- [upstream] `construction/money-core/infrastructure-design/cicd-pipeline.md` — what B1 deferred here
- [upstream] `inception/contract-design/contract-summary.md` — §C.4 BulkSMSBD
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7, NFR8, NFR10
- [upstream] `inception/domain-design/components.md` — the entity catalogue the
  migration realises
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
  — §2.6, the migration this stage provisions for
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.8
- [team] `## Deployment`
- [project] `## Mandated`

---

## A. Phase 1 topology

| Environment | Compute | Database | Cost |
|---|---|---|---|
| Local | Docker Compose | Postgres 16 container | — |
| **Staging** | Lightsail instance | Containerized Postgres | ~USD 12/mo |
| **Production** | Lightsail instance | Containerized Postgres | ~USD 12/mo |

**A staging instance exists in Phase 1**, taking hosting from ~USD 13 to
~USD 25 against the USD 50 ceiling. `team.md` pays for it deliberately:
staging is where a migration gets rehearsed before it touches real teacher
and child data, and there is **no multi-AZ database to fail over to** if it
does not.

**What staging is faithful about**: schema, migration path, and
authorization behaviour. **What it is not**: performance. Both environments
share an instance class and differ by configuration and data, and that
trade is accepted rather than discovered.

---

## B. The database

| Property | Value | Why |
|---|---|---|
| Engine | **PostgreSQL 16** | Row-level security, `ON CONFLICT DO NOTHING`, partial indexes — the behaviours under test [A.4] |
| Encryption at rest | **Required** | NFR10, RC-8. Disqualifies any tier without it |
| Roles | **Two**: owner and restricted application role | §B.1 |
| Migration | Alembic, from zero | Continuous exercise of the path |

### B.1 Two roles, and the restricted one is load-bearing

```sql
CREATE ROLE shikkhok_app NOINHERIT LOGIN;   -- the application connects as this
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO shikkhok_app;
-- deliberately NOT the owner, and deliberately NOT a superuser
```

> **This is not hygiene, it is the thing that makes the privacy suite
> mean anything.** PostgreSQL documents that superusers and table owners
> **bypass row-level security entirely**. The application must therefore
> connect as a role that is neither — otherwise the RLS policy on `Profile`
> is decorative, and a privacy suite passes identically whether the policy
> is correct, broken, or absent.
>
> The same role is used in tests [BR3.3], and a meta-test asserts
> `current_user` is not a superuser **before** the privacy suite runs.

**Production access is a third, named role** — never the application's own
— with every interactive session logged with the person and the stated
reason [NFR8.5]. With no admin surface at this budget, every production
operation happens by `psql` against a live database holding children's
names.

---

## C. Secrets

**Four** enter the system here — the three `team.md` names, plus the OTP
HMAC key that NFR9.5 introduced. None is in the repository or the image.

| Secret | Phase 1 | Phase 2 | Rotation |
|---|---|---|---|
| Gateway credentials | Environment variable | SSM `SecureString` | Runbook, exercised once |
| **OTP HMAC key** | Environment variable | SSM `SecureString` | Runbook — see C.1 |
| JWT signing key | Environment variable | SSM `SecureString` | `kid` makes it non-breaking |
| Database URL | Environment variable | SSM `SecureString` | Runbook |

**SSM Parameter Store rather than Secrets Manager**: SSM is free, and
paying for rotation that is not wired up is the definition of a control
that does not earn its place.

### C.1 The HMAC key rotation has a consequence worth stating

Rotating the OTP HMAC key **invalidates every in-flight code**, because
stored digests were computed under the old key. With a 5-minute expiry the
blast radius is five minutes of sign-ins — acceptable, but it means
rotation is a *deliberate* operation rather than a routine one, and the
runbook says so.

> Contrast the JWT key, where `kid` makes rotation non-breaking: two valid
> verification keys mean a 30-day refresh token issued under the old key
> still verifies. That asymmetry is why one needs `kid` and the other does
> not.

---

## D. The gateway boundary

| Environment | Adapter | Can it spend money? |
|---|---|---|
| Local | Stub | No |
| CI | Stub | No — the blocking suite needs no secret |
| **Staging** | **Null adapter** | **No** |
| Production | BulkSMSBD | Yes |

**The null adapter is the default**, and selection is by explicit
configuration [BR5.4]. A missing or misspelt setting therefore fails
*toward not sending* rather than toward spending real money.

> **BulkSMSBD has no sandbox** (OQ-3a), so `team.md`'s rule that
> non-production holds test credentials cannot hold as written — the
> mechanism it names does not exist. The property it protects is preserved
> by a different one: staging still cannot spend money or message a real
> person.
>
> **The consequence, recorded rather than hidden**: the gateway leg is
> verified exactly once, at this Bolt's checkpoint, against production
> credentials with a single send to the developer's own number. That is the
> only place real money is spent before launch.

### D.1 IP whitelisting may apply

Code 1032 ("IP not whitelisted") appears in community sources though not
the vendor's published table. If enforced on this account, **both Lightsail
instances need a static IP attached**, and any later move to multiple
instances or a NAT gateway would break sends with what looks like an auth
failure. 1032 is non-retryable and alerting: retrying from the same IP
never succeeds.

---

## E. What this Unit does not provision

| Not provisioned | Why |
|---|---|
| Load balancer | An ALB would consume a third of the budget before any compute [D-29] |
| Multi-AZ / replica | Not affordable at Phase 1, and a replica would be an authorization bug for the computed lens |
| Redis | A second store can disagree with the database about whether a send happened [A.2] |
| WAF / CDN | No budget; the SMS ceilings bound the **cost**, not availability |
| Admin surface | None at this budget, which is why production access is named and logged |

---

## Assumptions & Open Questions

**Two, both values rather than decisions.** [assumption] The global daily
SMS ceiling's number derives from BulkSMSBD's per-SMS rate against the
budget; the mechanism is designed and tested at a test-configured
threshold. [assumption] Whether IP whitelisting is enforced on this account
is a vendor question (§D.1); the design works either way, and a static IP
is attached regardless because it costs nothing while attached.
