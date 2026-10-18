# Scalability Design — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-requirements/scalability-requirements.md` — NFR10.5–NFR10.9
- [upstream] `functional-design/rules.md` — BR2.2, BR6.1
- [upstream] `construction/identity-and-access/nfr-design/scalability-design.md`
- [team] `## Deployment`

---

## A. The constraint that must be partial

```sql
CREATE UNIQUE INDEX uq_enrollment_batch_student
    ON enrollment (batch_id, student_account_id)
    WHERE student_account_id IS NOT NULL;
```

**Verified against real PostgreSQL**, all seven cases:

| Case | Result |
|---|---|
| Second and third dormant seat in one batch | admitted |
| Same account twice in one batch | **refused** |
| Same account in two batches of one teacher [AC2.2.3] | admitted |
| Re-enrolling an **erased** account into the same batch | admitted |

> **The last is correct, not a hole.** The catalogue says a teacher may
> enroll that number again, creating a new enrollment with no link to
> the old. The constraint permits it because the erased row's account
> column is NULL, while that row stays blocked from *automatic*
> reattachment. A deliberate teacher action and a silent re-link are
> different things, and this shape distinguishes them with no extra
> code.

**Without `WHERE student_account_id IS NOT NULL`** the second dormant
seat in a batch is refused — which is the normal state early in a
batch's life, when a teacher records four numbers before anyone signs
in.

---

## B. What the ceiling licenses

100 teachers, a few thousand students, one instance under USD 50/month.

| Decision | Licensed by |
|---|---|
| No read replica | The budget — and a replica would be an authorization bug for the computed lens, since stale ownership resolves stale permissions |
| No server-side cache of lens-scoped data | Correctness, not cost: that is how cross-teacher leakage happens |
| `Owner` created lazily on first batch | Most accounts are students and guardians who will never own one |

---

## C. What does not scale, stated rather than assumed

| Limit | When it bites |
|---|---|
| An unpaginated roster | Nothing caps students per batch. A constant query count makes a large roster survivable, but the payload grows linearly — revisit above ~200 |
| One Postgres instance | Beyond the stated ceiling, which is a Phase 2 question |

> §C exists because an earlier draft claimed rosters are "tens of
> rows" as though NFR6 implied it. It does not: the ceiling bounds the
> total, not the per-batch maximum.

---

## Assumptions & Open Questions

**None.** [assumption] The partial index is the only new constraint
this Unit adds; `Batch`, `BatchSubject` and `ScheduleSlot` need no
uniqueness beyond their primary keys, because duplicate subject names
in one batch are a teacher's choice rather than an error.
