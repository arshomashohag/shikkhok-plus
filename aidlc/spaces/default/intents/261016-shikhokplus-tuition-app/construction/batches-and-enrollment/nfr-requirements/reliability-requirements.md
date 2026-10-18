# Reliability Requirements — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `functional-design/functional-spec.md` — §2.1, §2.1a, §2.5
- [upstream] `functional-design/rules.md` — BR4.2, BR4.3, BR5.0, BR6.1
- [upstream] `inception/requirements-analysis/requirements.md` — NFR4, NFR5
- [upstream] `construction/identity-and-access/nfr-requirements/reliability-requirements.md`
- [team] `## Deployment`, `## Way of Working`
- [project] `## Forbidden`

---

## A. This Unit's migration is the first that alters a populated table

B3's migration created everything from zero against an empty database.
**U4 renames columns on `Enrollment` and `Owner`, which U3 already
shipped** — and by the time it runs there may be real rows.

| ID | Requirement | Why |
|---|---|---|
| **NFR6.15** | Forward-only and backward-compatible [team.md] | No failover, no multi-AZ database. A migration that cannot be rolled forward past a mistake is not merged |
| **NFR6.16** | Renames preserve data, never drop-and-recreate | `ALTER TABLE ... RENAME COLUMN` keeps the rows; a drop loses dormant enrollments the teacher recorded and cannot recover |
| **NFR6.17** | The lens-query correction [BR5.0] ships in the **same** migration as the rename | Separating them leaves `_LENS_QUERY` reading a column that no longer exists — a window in which authentication is broken for everyone |
| **NFR6.18** | A test migrates from the B3 head revision **with rows already present**, and asserts the **values survive** | From-zero is what CI runs; from-B3-head-with-data is what production does |

> **NFR6.18 is the one a green CI would hide**, and the first version
> of this requirement reproduced the defect it was written to catch.
>
> Verified against a live container. Two things had to be fixed:
>
> 1. **Seeded rows are part of the requirement.** With the table empty
>    at `0001`, a rename and a drop-and-recreate are *indistinguishable* —
>    so "migrate from B3 head" alone asserts nothing.
> 2. **Counting rows is not enough.** With one dormant enrollment
>    present, both shapes leave the table at one row. What
>    drop-and-recreate destroys is the **link**: the account column
>    comes back NULL. The assertion must be on the VALUE — the dormant
>    enrollment still points at the account it pointed at before.
>
> That is the same "the assertion is real, the setup makes it vacuous"
> shape as NFR6.12's fixture size and the privacy suite's superuser
> connection. Three instances now; it is the project's most common
> defect class.

---

## B. Writes that must not partially apply

| ID | Requirement | Why |
|---|---|---|
| **NFR10.10** | Batch plus subjects plus slots commit together or not at all | A batch with no subject is unrenderable, and U6 would attach exams to nothing |
| **NFR10.11** | Marking inactive touches **exactly one row**, asserted [BR4.3] | The requirement is phrased about a *student*; the operation is on an *enrollment*, and that gap is where the bug lives |
| **NFR10.12** | Marking inactive modifies **no** fee or ledger row [BR4.2] | Those belong to U7. A cascade cancelling outstanding dues erases money a student actually owes |

---

## C. What is deliberately not specified

| Not specified | Why |
|---|---|
| An availability target | Phase 1 cannot honestly state one, and an SLO nobody measures is decoration |
| Retry on a failed roster read | V1 accepts no write without connectivity [TC-8]; a read failure surfaces the cache with its staleness shown |
| A backup cadence beyond `team.md`'s | Deployment already requires a verified `pg_dump` before any production migration — which this Bolt's rename turns from hypothetical into concrete |

---

## Assumptions & Open Questions

**None.** [assumption] NFR6.18 assumes B3's revision `0001` is the
production head when U4 deploys, which holds because no Bolt between
them ships a migration.
