# Reliability Design — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-requirements/reliability-requirements.md` — NFR6.15–NFR6.18, NFR10.10–NFR10.12
- [upstream] `functional-design/rules.md` — BR4.2, BR4.3, BR5.0, BR6.1
- [upstream] `construction/identity-and-access/nfr-design/reliability-design.md`
- [team] `## Deployment`

---

## A. The migration, which is the riskiest thing in this Bolt

B3 created tables from nothing. **U4 alters tables that may hold real
rows**, and the alteration includes a rename the lens query depends on.

**It is a RESHAPE, not a rename, and calling it a rename would lose
data.** Found by working U3's actual rows rather than its column list.

U3 stores **one row per (account, batch, role)** — a guardian holds
their *own* enrollment row with `role='guardian'`. U4 stores **one row
per student**, with the guardian as a column on it. Two rows become
one.

> A plain `RENAME COLUMN account_id TO student_account_id` would leave
> the guardian's row with `student_account_id = <the guardian>`. Drop
> `role` and nothing remains to say otherwise: **every guardian
> appears on the roster as a pupil.**

```
0002_batches_and_enrollment:
  ADD COLUMN guardian_account_id, student_relink_blocked_at,
             guardian_relink_blocked_at, guardian_phone, joined_on
  RENAME COLUMN account_id TO student_account_id

  -- THE FOLD, which a rename does not cover:
  UPDATE enrollment s SET guardian_account_id = g.student_account_id
    FROM enrollment g
   WHERE g.role = 'guardian' AND s.role = 'student'
     AND g.batch_id = s.batch_id
  DELETE FROM enrollment WHERE role = 'guardian'

  DROP COLUMN role            -- only now is it redundant
  ... and the Batch / BatchSubject / ScheduleSlot tables
  -- same revision: the rewritten _LENS_QUERY ships with it
```

| Mechanism | What it protects |
|---|---|
| The **fold** before the drop | Guardians appearing as students on every roster |
| `RENAME COLUMN`, never drop-and-add [NFR6.16] | Dormant enrollments a teacher recorded |
| Rename and lens rewrite in **one** revision [NFR6.17] | A window where authentication reads a column that is gone |
| `role` dropped **last** | The information the fold reads |

> **The fold is ambiguous when a batch has two students**, because
> U3's guardian row names a batch and not a child — which is the same
> ambiguity BR5.0 cites for correcting the lens query. At B5 the
> production database holds no guardian rows at all (U3 could not
> write `Enrollment`, and the seed script creates one `guardian` row
> for the skeleton demo only), so the fold is exact in practice. The
> migration **asserts** that: if it finds a batch with more than one
> student and a guardian row, it raises rather than guessing.

### A.1 The migration test needs seeded rows, and must assert values

**The first version of this requirement was vacuous and that is worth
keeping visible.** Verified against a live container:

| Setup | Rename | Drop-and-add | Distinguishable? |
|---|---|---|---|
| Empty table | ok | ok | **no** |
| One row, count asserted | 1 row | 1 row | **no** |
| One row, **value** asserted | link intact | link NULL | **yes** |

So the test migrates from the real `0001`, seeds a dormant
enrollment, and asserts **the enrollment still points at its
account** — not that the table still has a row.

---

## B. Writes that must not partially apply

| Mechanism | Rule |
|---|---|
| Batch + subjects + slots in one transaction | NFR10.10 |
| Mark-inactive touches one row, asserted by count | NFR10.11 |
| Mark-inactive issues **no** statement against fee tables | NFR10.12 |

> **NFR10.12 is testable before U7 exists**: assert the statements
> issued, not the rows unchanged. There are no fee tables to leave
> alone yet, and a test written against absent tables passes
> vacuously — the statement-level assertion does not.

---

## C. Degradation

| Failure | Behaviour |
|---|---|
| Database unreachable during a roster read | The client renders its Room cache **with staleness shown** [NFR4.1] |
| Database unreachable during any write | Refuse. V1 accepts no write without connectivity [TC-8] |
| `HISTORY_TABLES` unreadable during removal | **Refuse** — fails closed [logical-components A.1] |
| Relink markers unreadable during resolution | **Do not attach** — fails closed [A.2] |

---

## Assumptions & Open Questions

**None.** [assumption] Revision `0001` is the production head when
`0002` runs, which holds because no Bolt between B3 and B5 ships a
migration. If that changes, the from-head test's starting revision
changes with it and the test names the revision explicitly rather
than using `head`.
