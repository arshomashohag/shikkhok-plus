# Infrastructure Specification — `batches-and-enrollment` (U4)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **U4 provisions nothing new.** B3 brought the database, the host, the
> secrets and the deployed environment. This Unit adds tables to an
> existing schema and routes to an existing container.
>
> What it does bring is **the first migration that alters live data**,
> and that is an operational concern rather than an infrastructural
> one — so most of this document is about the deploy, not the kit.

## Sources

- [upstream] `nfr-design/reliability-design.md` — §A, §A.0, §A.1
- [upstream] `nfr-design/logical-components.md`
- [upstream] `nfr-requirements/reliability-requirements.md` — NFR6.15–NFR6.18
- [upstream] `construction/identity-and-access/infrastructure-design/infrastructure-specification.md`
- [team] `## Deployment`
- [project] `## Mandated`

---

## A. Topology — unchanged from B3

| Environment | Compute | Database |
|---|---|---|
| Local | Docker Compose | Postgres 16 container |
| Staging | Lightsail instance | Containerized Postgres |
| Production | Lightsail instance | Containerized Postgres |

No new instance, no new service, no new secret. The budget position is
unchanged at roughly USD 25/month against the USD 50 ceiling.

---

## B. The deploy is the risk, and it has an ordering

B3's deploy applied a migration to an empty database. **B5's applies
one to a database holding rows a teacher created** — and the ordering
below is load-bearing rather than procedural.

| # | Step | Why it is here and not elsewhere |
|---|---|---|
| 1 | `pg_dump`, verified for existence and non-trivial size | `team.md` already requires it; this is the first Bolt where losing the dump would lose real data |
| 2 | **Delete the skeleton seed's ROWS** | See B.1 — the migration refuses to run while they exist |
| 3 | Delete `app/db/seed_skeleton.py` | A B5 obligation. After the rows, not before |
| 4 | Apply `0002` as a distinct logged step | Never a side effect of container start |
| 5 | Start the new container | The rewritten lens query ships in the same image |
| 6 | Smoke: sign in, resolve a lens, read a roster | A roster read is new at this Bolt and exercises the rename |

### B.1 Step 2 is not housekeeping

`app/db/seed_skeleton.py` — which the **approved B3 checkpoint
instructs the operator to run** — creates one `role='guardian'`
enrollment with **no student row**.

The `0002` migration's fold guard refuses to proceed against that
shape, because a guardian row whose batch has no student cannot be
folded into anything. **That is the correct behaviour**: the
alternative silently deletes the row and the link with it.

> So the deploy **stops at step 4** if step 2 was skipped, with the
> data untouched. That is a good failure — recoverable, loud, and
> before anything is altered — but only if the operator knows why.
> Hence the ordering is written here rather than left to the runbook's
> author to infer.

---

## C. Rollback

| Property | Detail |
|---|---|
| Image | Previous SHA tag; `latest` is never deployed |
| Schema | `0002` has a `downgrade()` that reverses the renames |
| **The fold is not reversible** | See C.1 |

### C.1 The fold cannot be undone, and the dump is the real answer

`downgrade()` can rename columns back and re-add `role`. It **cannot**
reconstruct the deleted guardian rows: the fold collapses two rows
into one, and the information about *which* row the guardian came
from is gone.

> So the honest rollback story for `0002` is **restore from the
> step-1 dump**, not `alembic downgrade`. Writing a `downgrade()` that
> appears to work while silently losing guardian links would be worse
> than not writing one — it would be reached for in exactly the
> moment when care matters most.
>
> `downgrade()` therefore **raises** rather than attempting the fold's
> inverse, with the dump named in the error message.

---

## D. What this Unit does not provision

| Not provisioned | Why |
|---|---|
| A read replica | Budget, and a replica would be an authorization bug for the computed lens |
| Object storage | `photo_ref` is U6's or later; U4 stores no media |
| A second environment | Staging and production already exist |
| Any new secret | U4 reads nothing the container does not already hold |

---

## Assumptions & Open Questions

**None.** [assumption] The B3 checkpoint was approved but the device
leg — a real SMS and the seed script — was never run, so production
may hold **no** seed rows at all. Step 2 is then a no-op, which is
harmless; the migration's guard makes the deploy correct either way
rather than depending on which happened.
