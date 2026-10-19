# Security Design — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **The first Unit with two teachers in it.** Every mechanism below
> exists because there are now two parties for data to move between,
> and the project's stated top risk becomes testable here.

## Sources

- [upstream] `nfr-requirements/security-requirements.md` — NFR14.12–NFR14.21
- [upstream] `functional-design/rules.md` — BR2.1, BR5.0–BR5.4, BR6.1–BR6.3
- [upstream] `inception/domain-design/components.md` — the Governance manifest
- [upstream] `construction/identity-and-access/nfr-design/security-design.md`
- [team] `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Cross-teacher isolation — the mechanism, not the intention

**The scoping value lives inside the lens object** [TC-11], so a
teacher-facing query cannot be compiled without it:

```python
def list_roster(
    batch_id: UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Session,
) -> list[RosterRow]:
    # owner_id comes from the LENS. There is no parameter to forge
    # and no default to forget.
    ...WHERE batch.owner_id = lens.owner_id AND batch.id = batch_id
```

| Mechanism | What it stops |
|---|---|
| `owner_id` from the lens, never a parameter | A handler scoping on a value the caller supplied |
| **404** on another owner's batch [NFR14.13] | A 403 confirming the batch exists |
| The route-enumeration gate U2 built | An endpoint added later with no lens at all |
| A two-teacher test [NFR14.14] | The leak itself, at the first Bolt where two parties exist |

> **The two-teacher test is the one B3 could not write.** U3 had one
> account and no second party; every isolation claim it made was about
> a mechanism rather than an outcome.

### A.1 Guardian reachability resolves through the recorded number

```sql
-- reachable enrollments, for an authenticated guardian
WHERE enrollment.guardian_account_id = :authenticated_account
```

**Never through the child** [NFR14.15, BR5.3]. Resolving by "find this
guardian's children, then show every enrollment of those children"
merges two teachers' records: a guardian recorded by teacher A under
one number would see teacher B's batch for the same child.

Worked both rules — the child-keyed one leaks, the number-keyed one
does not — which is why the rule names the column rather than the
intent.

### A.2 The administrator field set, stated as columns

`Owner` carries `id`, `kind`, `account_id`, `state`, `plan`,
`plan_valid_to`, `deleted_at`. A platform administrator may read
**`state`, `plan` and `plan_valid_to`** and nothing else
[NFR14.18, BR1.2].

> There is no admin surface in V1, so nothing enforces this yet. It is
> stated in columns rather than in prose because `Owner` is written
> for the first time in this Unit, and the temptation — an endpoint
> joining to `Enrollment` "to show how many students" — arrives with
> the table.

---

## B. The erasure markers, and why they are per link

| Mechanism | Detail |
|---|---|
| `student_relink_blocked_at` | Set by U11 when a student erases |
| `guardian_relink_blocked_at` | Set by U11 when a guardian erases |
| Dormant resolution skips a blocked **link** | Not a blocked row |

**One flag could not express the four states.** Worked:

| State | Student may claim | Guardian may claim |
|---|---|---|
| Never claimed | yes | yes |
| Student erased | **no** | yes |
| Guardian erased | yes | **no** |
| Both erased | no | no |

With a single flag, row three blocks the student — who never claimed
that seat and never erased anything. That is **one person's erasure
revoking another person's access**, and it is silent.

> This diverges from the upstream catalogue, which declares a single
> `relink_blocked_at`. The divergence is flagged in BR6.2 rather than
> made quietly: the catalogue's rationale is written entirely about an
> erased *student* and never considers the guardian link erasing
> independently.

### B.1 Removal must test two conditions, not one

```sql
student_account_id IS NULL AND student_relink_blocked_at IS NULL
```

**After an erasure the first condition is true again.** A null-only
test therefore deletes the erased row and destroys the marker §B
depends on — so the erased number silently reattaches on its next
sign-in, which is the harm the whole mechanism exists to prevent.

---

## C. The privacy boundary, first written against here

U3 made it structural by splitting the tables. **U4 is the first Unit
that writes `display_name`**, so it is the first that can violate the
split — and the likely violation is a *read*, not a write:

```python
# The plausible bug. It looks like a kindness.
name = enrollment.display_name or profile.self_name
```

| Mechanism | What it stops |
|---|---|
| A test asserting no U4 module imports or references `Profile` | Exactly the fallback above |
| RLS on `Profile`, already in force | The fallback failing closed even if written |

> **Two layers, and the second is why the first is not merely
> advisory.** If the fallback were written, RLS would return no row
> for a teacher's session — so the bug surfaces as a missing name
> rather than as a leak. The test makes it not compile; the policy
> makes it not matter.

---

## D. What this design does not defend against

| Not defended | Why |
|---|---|
| A teacher photographing their own roster | Their own record; no technical control applies |
| A compromised teacher account | U3's token rotation is the control; U4 adds nothing |
| An administrator with database access | Named, logged access is the control [team.md]; there is no admin surface to harden |
| A guardian number entered wrongly | The teacher typed it. The correction path is an edit, not a control |

---

## Assumptions & Open Questions

**One, carried from the functional design rather than opened here.**
[assumption] The per-link erasure markers diverge from the catalogue
and U11 must implement erasure against this shape. Recorded in BR6.2
with the four worked states so U11 inherits the reasoning, not just
the column names.
