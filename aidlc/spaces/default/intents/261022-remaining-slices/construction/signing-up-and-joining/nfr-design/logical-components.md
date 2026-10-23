# Logical Components — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **D1 adds no component.** It adds routes and a lens type inside
> `identity-and-access`, and writes two columns owned by
> `batches-and-enrollment` through that component's own service. This file
> records where the NFR patterns attach, and where the failure domains are,
> for Infrastructure Design to build against.

## Sources

- [upstream] `inception/domain-design/components.md` — the component catalogue
- [upstream] this stage's `security-design.md`, `reliability-design.md`,
  `scalability-design.md`, `observability-design.md`
- [upstream] `construction/signing-up-and-joining/nfr-requirements/` — NFR6.x, NFR7.5, NFR12.x
- [code] `app/` module layout, read 2026-10-23

---

## 1. Component inventory

A **modular monolith**: one deployable, with module boundaries enforced by
import rules and CI gates rather than by wires [prior: contract-design].

| Component | Owns | D1's change |
|---|---|---|
| `identity-and-access` | `Account`, `Profile`, `Owner`, the lens hierarchy, OTP and tokens, the ceiling cascade, the audit log | **Routes added**: signup, lookup, accept/decline/un-decline. **Type added**: `InvitationLens`. **Column added**: `profile.address` |
| `batches-and-enrollment` | `Batch`, `Enrollment` | **Columns added**: the two decision enums. Read by D1 through this component's service, never by reaching past it |
| `money-core` | `Money`, the arithmetic | Untouched |
| `api-contract` | The error envelope, route enumeration, privacy invariants, the committed OpenAPI schema | **Field-set entry**: `address` joins the owner-private name set [BR3.4] |

**Why no new component.** Signup creates an identity; acceptance grants a
lens. Both are what `identity-and-access` is for. A `signup` component would
split one concern across two modules and duplicate the thing the boundary
exists to protect — the rule this project recorded at units-generation, that a
delivery boundary is not a component boundary.

---

## 2. Where each NFR pattern attaches

| Pattern | Component | Module | Requirement |
|---|---|---|---|
| Ceiling cascade (signup scopes) | identity-and-access | `app/auth/ceilings.py` | NFR12.4, NFR12.5 |
| Lens resolution predicate | identity-and-access | `app/authz/resolve.py` | NFR20.1 |
| Lens summary predicate | identity-and-access | `app/authz/summary.py` | NFR20.1 |
| Invitation grant (own statement) | identity-and-access | new resolver | NFR20.3 |
| Row-level security | identity-and-access | `profile` policy | NFR10.14 |
| Owner-private field set | api-contract | `app/contract/privacy.py` | NFR14.25 |
| Error taxonomy mapping | api-contract | `app/errors/handler.py` | NFR19.6 |
| Audit events | identity-and-access | `app/audit/log.py` | NFR12.8 |
| Removability predicate | batches-and-enrollment | `app/batches/service.py` | BR7.1 |
| Roster dormancy derivation | batches-and-enrollment | `app/batches/service.py` | BR7.2 |

**The last two rows are the cross-component ones and they are the risk.** D1's
migration changes what `student_account_id` *means* to code
`batches-and-enrollment` already owns. The design's rule is that the predicate
changes in the same unit that changes the meaning, through the owning
component's service — not by D1 reaching into another component's queries.

---

## 3. Failure domains

| Domain | Contains | Blast radius if it fails |
|---|---|---|
| **Process** | The whole app, two workers | Total: no reads, no writes. Recreate-style deploy accepts a short restart window |
| **Database** | All state | Total. The thing that cannot be rolled back [NFR19.3] |
| **SMS gateway** | OTP delivery only | **Bounded**: accounts still create; codes do not arrive [NFR19.6] |
| **Audit write** | The log only | **Bounded by a savepoint**: the caller's transaction survives; the failure alerts [NFR25.3] |

**Two bounded domains are bounded by design decisions, not by luck.** The
gateway's blast radius is bounded because the account is created before the
send; the audit log's is bounded because the write runs in a nested
transaction. Both are recorded here so Infrastructure Design does not treat
either as total.

---

## 4. The unauthenticated surface

D1 is the unit that creates one. Three routes reachable with no session:

| Route | Reads / writes | Bounded by |
|---|---|---|
| `POST /v1/accounts` | Writes identity | Signup ceilings [NFR12.4] |
| The already-added lookup | Reads one seat's name and role | Signup ceilings; discloses no teacher, no batch [NFR14.23] |
| `POST /v1/auth/otp` | Existing | OTP ceilings, byte-identical responses [NFR14.22] |

**None reaches a batch, a fee, a mark or an attendance record.** The
unauthenticated surface is confined to identity, which is what makes its blast
radius the identity component rather than the product.

### The staging outbox is adjacent to this surface

`app/gateway/outbox.py` hands an OTP to any caller, and is kept out of
production three independent ways (environment allowlist read fresh per call,
route not registered when disabled, startup refusal). **D1 adds a route that
causes an OTP to be sent**, so it increases what that outbox would expose if
it ever ran in production — while changing none of the three controls, and
adding no signup-specific readback.

Recorded as a component-level fact because it is the one place where D1's new
surface and an existing high-risk surface meet.

---

## 5. Shared resources

| Resource | Shared by | Contention | Design |
|---|---|---|---|
| `rate_limit_counter` | Both cascades | Per `(kind, value, window)` row | Upsert increments then compares; a refusal releases its own increment [NFR6.25] |
| `auth_audit_log` | All auth events | Append-only | Savepoint-isolated writes |
| Connection pool | Everything | Two workers | Unchanged; D1 adds no concurrent workload class |
| `enrollment` | D1 writes decisions, D2–D5 read them | Row-level | Per-link columns, so student and guardian writes never contend [BR5.2] |

**The last row is a design property worth stating.** Because a decision is
per-link rather than per-row, a student accepting and a guardian declining the
same seat touch different columns — so the independent-facts data model is
also a contention-avoidance property.

---

## 6. Hand-off to Infrastructure Design

What D1 needs from infrastructure, and what it does not:

| Needs | Does not need |
|---|---|
| Nothing new — no service, no datastore, no scheduled job [NFR7.5] | An autoscaler, a queue, a cache tier, a replica |
| The existing staging environment for the migration rehearsal [NFR19.4] | A new environment |
| The verified `pg_dump` to S3 before the production migration [NFR19.3] | A new backup mechanism |

**Two gaps are handed forward rather than closed** — both pre-existing, both
enlarged by D1: the scheduled purge enforcing `rate_limit_counter`'s declared
48-hour retention, and the one enforcing `auth_audit_log`'s 12-month
retention. The dispositions exist in the governance manifest; the jobs do not.

---

## Assumptions & Open Questions

- **Assumed**: D1 writes the decision columns through
  `batches-and-enrollment`'s service rather than directly, keeping the
  component boundary intact even though the columns are D1's to add.
- **Assumed**: Phase 1 topology is unchanged — one Lightsail host, two
  workers, containerized Postgres on staging.
- **Open, and not D1's**: both purge jobs above, and the Phase 2 split to a
  separate RDS instance.
