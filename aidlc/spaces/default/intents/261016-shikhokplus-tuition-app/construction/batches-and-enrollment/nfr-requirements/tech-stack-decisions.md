# Tech Stack Decisions — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **Almost nothing new.** The stack was chosen at B1 and B3; this Unit
> adds one library on the Android side and builds one component the
> project has specified since `team.md` and never had a table to need.

## Sources

- [upstream] `functional-design/rules.md` — BR3.2, BR3.3, BR7.1
- [upstream] `inception/requirements-analysis/requirements.md` — NFR1, NFR2, NFR9
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md`
- [upstream] `construction/money-core/code-generation/code-summary.md`
- [team] `## Code Style`, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Inherited unchanged

| Layer | Choice | Decided at |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 | B3 |
| Money | `app.money` with `Money`, one rounding mode | B1 |
| Android | Kotlin 2.0, Compose (BOM-pinned), kotlinx.serialization | B3 |
| Tests | pytest + testcontainers; JUnit + Robolectric | B3 |

---

## B. What U4 adds

| ID | Decision | Why |
|---|---|---|
| **A.5** | **Room** for the Android read cache | `team.md` names it, and U4 is the first Unit with a list worth caching. Entities mirror the DTO and derive nothing [BR7.1] |
| **A.6** | **Build the SQLAlchemy `TypeDecorator`** `team.md` specifies for `Money` | It does not exist. B1 correctly never built it — a library Unit with no tables has nothing to map — and U4 has the first real money column |

### B.1 The TypeDecorator is a deliverable, not a dependency

**A review found BR3.2 naming it as the enforcing mechanism while
nothing implemented it.** That overstatement is worth keeping in view,
because the honest version changes what this Unit must do:

- the **schema assertion** in `tests/db/test_governance.py` is the
  enforcement that exists, and it works regardless of how a column was
  created — including by raw SQL that never touches the ORM;
- the **TypeDecorator** is what U4 builds, and it catches a `Float`
  reaching the ORM at author time.

Neither alone suffices, and the gap between them is recorded rather
than papered over: **a badly-named money column created by raw SQL is
caught by neither.** The name check matches tokens like `fee` and
`amount`; a column called `tuition` or `stipend` matches nothing.

### B.2 The money gate needs a non-money allowlist [BR3.3]

Verified against a real container with U4's `batch` table applied: the
gate reports exactly one offender, `batch.fee_due_day` — an integer
1–31 by design that matches both `fee` and `due`.

**The obvious fix is the dangerous one.** Dropping a token would turn
the build green while silently retiring the check on every genuine fee
column in U7 and U8. A per-column allowlist keeps the tokens intact.

---

## C. What is deliberately not added

| Not added | Why |
|---|---|
| A query builder or repository framework | SQLAlchemy Core is already the seam, and a repository layer would hide the `owner_id` scoping that must be visible |
| Paging or cursor libraries | No pagination at this ceiling [NFR6] |
| A client-side cache library beyond Room | Room is the decision; a second cache is a second place for staleness rules to diverge |
| An ORM-level soft-delete plugin | Deletion is anonymize-in-place per the Governance manifest, not a tombstone — a plugin would impose the shape this project explicitly does not use |

---

## Assumptions & Open Questions

**None.** [assumption] Room's version follows the Compose BOM's
companion releases rather than being pinned independently, matching how
B3 pinned Compose — one version source per family, so a mismatched pair
cannot arrive through a transitive bump.
