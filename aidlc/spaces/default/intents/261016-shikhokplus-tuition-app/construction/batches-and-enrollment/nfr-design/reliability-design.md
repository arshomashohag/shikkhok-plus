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

### A.0 The fold has two failure modes, and the second was found by running it

**The first draft of this section was wrong about production data, and
its guard did not cover the case that actually exists.**

| Case | Fold behaviour | Guard needed |
|---|---|---|
| Guardian row, one student in batch | folds correctly | — |
| Guardian row, **two** students | ambiguous: U3's row names a batch, not a child | assert |
| Guardian row, **zero** students | **UPDATE matches nothing, DELETE removes the row** | assert |

The third is not hypothetical. `app/db/seed_skeleton.py` — the script
the **approved B3 checkpoint instructs the operator to run** — creates
exactly one `role='guardian'` row and **no student row**. Run against
that state, the fold silently destroys the guardian link: the UPDATE
matches zero rows, the DELETE removes the only row, and the table ends
empty.

> My draft said "production holds no guardian rows at all". It holds
> exactly one, put there by a script this project ships and tells
> people to run. And the guard I wrote — assert if a batch has more
> than one student — **does not fire**, because that batch has zero.

So the migration asserts on **both** shapes before folding:

```sql
-- refuse to guess, in either direction
SELECT 1 FROM enrollment g
 WHERE g.role = 'guardian'
   AND (SELECT count(*) FROM enrollment s
         WHERE s.role = 'student' AND s.batch_id = g.batch_id) <> 1
```

Any row returned raises. **The deploy then stops before touching
data**, which is the right failure: a migration that cannot establish
what a guardian row refers to must not decide for itself.

**The recovery path is named rather than left to the moment**: delete
the skeleton seed's rows before deploying `0002`. That is already a
B5 obligation — the functional spec lists removing `seed_skeleton.py`
— and this makes the ordering explicit. Remove the data, then the
script, then migrate.

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
