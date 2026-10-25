# Infrastructure Specification — D2 `running-a-batch`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 provisions nothing and migrates nothing.** It is the first unit of this
> record that touches the database schema not at all. Everything below is
> inherited; the value of this document is § 4, which records what that means
> for the deploy, and § 5, which keeps D1's two open gaps visible without
> claiming them.

## Sources

- [upstream] `construction/running-a-batch/nfr-design/logical-components.md`
  — the hand-off table and failure domains
- [upstream] `construction/running-a-batch/nfr-design/` — performance and
  security designs
- [upstream] `construction/running-a-batch/nfr-requirements/` — NFR20.x,
  NFR14.x, NFR2.x
- [upstream] `construction/running-a-batch/functional-design/functional-spec.md`
  — § 1, the response-shape change the deploy carries
- [upstream] `inception/domain-design/components.md` — the component
  catalogue, which D2 changes in two components and adds none to
- [prior] D1's `infrastructure-design/infrastructure-specification.md` — the
  topology and the gaps table this unit inherits
- [code] `infra/`, `.github/workflows/`, `migrations/versions/`, read
  2026-10-23

---

## Deployment

Unchanged from D1. Every row verified against `infra/` rather than copied.

| Facet | Choice | D2's change |
|---|---|---|
| Compute | Containerized app on EC2 behind an ASG | none |
| Image identity | SHA-tagged; `latest` never deployed | none |
| Networking | CloudFront → origin FQDN; app public subnets, database private | none |
| Database | RDS PostgreSQL `db.t4g.micro`, Single-AZ, private, encrypted | none |
| Environments | Production; staging module **defaults off** | none |
| IaC | Terraform, five modules | **no resource added** |
| Budget | `terraform_data` precondition failing the plan over the ceiling | estimate unchanged at **USD 32.62** |

---

## Infrastructure Services

| Service | Role | D2's change |
|---|---|---|
| EC2 + ASG | The application | none |
| RDS PostgreSQL | All state | **read-only for D2** |
| CloudFront, ECR, Route53, S3, SSM | Edge, registry, DNS, config, access | none |
| BulkSMSBD | SMS | **not on any D2 path** |

**D2 adds no row to this table**, and no row changes.

**Nor does it add a component.** The catalogue in
`inception/domain-design/components.md` is unchanged: D2's server work is two
fields and one aggregate inside `batches-and-enrollment`, and its client work
is a `feature/guardian` package — a package, not a component. Infrastructure
serves the same deployable it served before.

---

## What the deploy carries

| Change | Where | Deploy consequence |
|---|---|---|
| `accepted_count` on `BatchResponse` | `app/schemas/batches.py` | Additive response field |
| `student_state`, `guardian_state` on `RosterRowResponse` | `app/schemas/batches.py` | Additive response fields |
| One conditional aggregate | `app/batches/service.py` | Query change, no schema change |
| Four screens, one package | `android/` | Client build |

**No migration.** `migrations/versions/` ends at D1's `0004`.

### Why the additive widening needs no version bump

`/v1/` stays additive and the client handles unknown fields rather than
failing to parse [D-26, NFR16]. Two responses gaining fields is the case that
policy exists for.

**What makes it safe to do without ceremony is the schema-diff gate**: the
committed `openapi.json` must match the generated one, so the widening appears
as a reviewable diff rather than as a surprise in a client. A contract change
that nobody sees is the failure that gate prevents.

---

## 4. What "no migration" buys

Worth stating rather than skipping, because it is the one way D2's deploy
differs from D1's:

| Obligation | D1 | D2 |
|---|---|---|
| Migration rehearsed on staging [NFR19.4] | Required | **Not applicable** |
| Pre-migration backup assertion [NFR19.3] | Required | **Not applicable** |
| Conditional backfill correctness [NFR19.2] | Required | **Not applicable** |
| Tag rollback completeness | Needed the additive-columns argument | **Unconditional** — no schema moved |
| Post-deploy `/health` | Inherited | Inherited |

**The rollback row is the substantive one.** D1's tag rollback was complete
only because its columns were additive and the old image never read them — an
argument that had to be made. D2's rollback needs no argument: redeploying the
previous tag restores the previous behaviour against an unchanged schema.

### The fact the whole argument rests on

**D2 writes no decision column**, and that is worth checking rather than
inferring from "it is a `ui` unit".

`app/batches/service.py` **does** write both columns, at `add_enrollment`
(lines 535–536), setting each to `pending` — because there is no column
default and every insert path must state the seat's initial state [ADR-013].
That is **D1's code, landed in D1's unit**, and D2 neither changes it nor adds
another writer. D2's own additions to that module are a conditional aggregate
over `enrollment` and a read of `_nobody_accepted`.

So the precise claim is: **D2 adds no write path to the acceptance columns and
changes none of the existing one.** Stated because a reader checking "does
this unit touch the schema?" would find `student_decision=` in a file D2
edits, and the answer is that the line was already there.

---

## 5. Gaps: still open, still D1's

Each row is an obligation **D1 handed forward**. D2 neither closes nor
worsens any of them, and listing them here is about not losing them between
units rather than about claiming them.

| Obligation | State | D2's relationship | Owner |
|---|---|---|---|
| Staging instance enabled [NFR19.4] | `enable_staging_instance` **defaults `false`** | Does not apply — no migration to rehearse | **D1, before its production deploy** |
| Pre-migration backup assertion [NFR19.3] | RDS automated backups cover the data; nothing asserts one at migration time | Does not apply — same reason | **D1, before its production deploy** |
| Post-deploy smoke set | `/health` only; the named set does not exist | **Unchanged.** D2 adds screens over endpoints that already worked | D1 can extend; D5/D6 complete |
| `rate_limit_counter` purge | 48h disposition declared, no job | Unaffected — D2's routes are authenticated and add no counter row | Not D2 |
| `auth_audit_log` purge | 12mo disposition declared, no job | Unaffected — **D2 adds no audit event** | Not D2 |
| ZAP baseline, Trivy, backend SBOM | Absent | None for D2 | D5, D6 |

**"Does not apply to D2" is not "closed".** Both of the first two block D1's
production deploy and are unchanged since that unit named them.

---

## 6. Hand-off to Infrastructure's next reader

| Needs | Does not need |
|---|---|
| **Nothing** | A migration, a job, a service, a datastore, an alert, an environment, a Terraform change |

One thing for **Build and Test** rather than for infrastructure: D2 adds four
Compose screens against the coverage exclusion D1 introduced, with the floor
at 45.84. If the ratchet drops, the diagnosis is that `**/ui/*Kt*` is catching
a non-composable — **narrow the glob, do not lower the floor**.

---

## Assumptions & Open Questions

- **Assumed**: the two new response fields flow through the committed
  `openapi.json` and its diff gate with no pipeline change, as D1's did.
- **Assumed**: no observability change — no new audit event, alert or metric
  beyond what the existing logs carry.
- **Open, and D1's**: the staging instance and the pre-migration backup
  assertion, both unchanged since D1 named them.
