# Logical Components — D2 `running-a-batch`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 adds no component and no infrastructure.** One client package, two
> response fields, one aggregate. This file records where the NFR patterns
> attach and what Infrastructure Design needs to know — which, for this unit,
> is almost nothing, and saying so precisely is the point.

## Sources

- [upstream] this stage's `security-design.md` and `performance-design.md`
- [upstream] `construction/running-a-batch/nfr-requirements/` — NFR20.x,
  NFR14.x, NFR23.x
- [upstream] `inception/domain-design/components.md` — the component catalogue
- [prior] D1's `nfr-design/logical-components.md` — the failure domains this
  unit inherits
- [code] `app/` module layout, `android/` feature packages, read 2026-10-23

---

## 1. Component inventory

A modular monolith; D2 changes two components and creates none.

| Component | D2's change |
|---|---|
| `batches-and-enrollment` | **Two response fields** on `RosterRowResponse`, **one `accepted_count`** on `BatchResponse`, **one conditional aggregate** in `list_batches` |
| `identity-and-access` | None. D2 renders the lens; it does not change it |
| `api-contract` | The widened schemas flow through the committed OpenAPI document and its diff gate |
| `money-core` | Untouched |

**Why `feature/guardian` is a new client package and not part of
`feature/roster`.** The guardian home is a *different lens's* view: the roster
is what a teacher sees of a batch, the child home is what a guardian sees of
one seat. Different lens, different route, different navigation. Features
split by what a person is doing, not by which table the data came from — and
putting two lenses' views in one package is how a shared helper eventually
reads one lens's data into the other's screen.

---

## 2. Where each NFR pattern attaches

| Pattern | Component | Module | Requirement |
|---|---|---|---|
| Conditional aggregate for the count | batches-and-enrollment | `app/batches/service.py:list_batches` | NFR20.7, NFR20.8 |
| The two roster decision fields | batches-and-enrollment | `app/api/batches.py`, `app/schemas/batches.py` | NFR14.26 |
| Teacher-lens schema invariant | api-contract | `app/contract/privacy.py` | NFR14.27 — **inherited, no change** |
| Removability decision | batches-and-enrollment | `app/batches/service.py:remove_enrollment` | NFR14.31 — **inherited, no change** |
| Guardian reach | batches-and-enrollment | `app/batches/service.py:list_guardian_children` | NFR14.29 — **inherited, no change** |
| `displayLabel` resolution | client | `feature/roster` mapper | NFR14.28 |
| Child-switch replacement | client | `feature/guardian` | **NFR14.30 — the only new mechanism** |

**Four of seven rows are inherited unchanged**, which is what a `ui` unit over
built endpoints should look like. The two that are genuinely new are the
aggregate and the switch behaviour.

---

## 3. Failure domains

Unchanged from D1, and D2 adds nothing to any of them:

| Domain | Contains | D2's effect |
|---|---|---|
| Process | The app, two workers | None |
| Database | All state | **No migration, no new table, no new column** |
| SMS gateway | OTP delivery | Not on any D2 path |
| Audit write | The auth log | **No new event** |

**D2 is the first unit of this record that touches the schema not at all.**
Worth stating because it bounds what can go wrong: there is no migration to
rehearse, no backfill to get right, and no rollback question. The deploy
risk of this unit is the risk of any application change.

### The one failure domain that is client-only

**The child switch** [NFR14.30]. Its failure mode — Back reaching the previous
child — is confined to one screen in one package, invisible to the server, and
caught only by a rendering test. That is a smaller blast radius than any
server-side failure in this unit, and a harder one to detect, which is the
combination worth recording rather than either property alone.

---

## 4. Shared resources

| Resource | Shared by | D2's effect |
|---|---|---|
| The `enrollment` table | D1 writes decisions, D2 reads them, D3–D5 will read them | **Read-only for D2** |
| The batch listing query | Every teacher sign-in | One more aggregate over rows it already scans |
| The committed OpenAPI schema | Both surfaces | Two shapes widen; the diff gate makes it a reviewable change |
| Connection pool | Everything | Unchanged; no new workload class |

**The OpenAPI row is the one with a mechanism behind it.** Widening a response
is a contract change, and the schema-diff gate means it appears as a diff
somebody reviews rather than as a surprise in a client. That gate is why D2
can widen two shapes without a version bump: `/v1/` stays additive and the app
handles unknown fields rather than failing to parse [D-26].

---

## 5. Hand-off to Infrastructure Design

| Needs | Does not need |
|---|---|
| **Nothing** | A migration, a job, a service, a datastore, an alert, a new environment |

D2 is a code change behind an unchanged deploy. The two gaps D1 handed
forward — the staging instance being off and the missing pre-migration backup
assertion — are **not D2's**, and D2 does not make either worse: with no
migration, this unit's deploy does not need the rehearsal that staging exists
for.

**That is worth one sentence rather than silence**, because "no infrastructure
change" is also what a unit says when nobody checked.

---

## Assumptions & Open Questions

- **Assumed**: the widened schemas need no API version bump, per the additive
  `/v1/` policy and the client's tolerance of unknown fields.
- **Assumed**: `feature/guardian` needs no navigation dependency, which is
  what makes the switch a selection [NFR14.30].
- **Open, and D5's**: pagination would be the first D2-shaped change that
  needed an infrastructure conversation, and it is deliberately not in V1.
