# Observability Design — `batches-and-enrollment` (U4)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [upstream] `nfr-requirements/observability-requirements.md` — NFR8.8–NFR8.13
- [upstream] `functional-design/rules.md` — BR6.2, BR6.3
- [upstream] `construction/identity-and-access/nfr-design/observability-design.md`
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. The forbidden-value set grows, and the mechanism must grow with it

U3's rule was "no phone number, no OTP, no token". **U4 introduces the
first child-identifying strings in the system**: `display_name` and
`guardian_phone`.

| Mechanism | What it stops |
|---|---|
| Enrollments identified by `enrollment_id` only [NFR8.9] | A name logged "for readability" |
| A failed removal logs a **reason class** [NFR8.10] | "refused: 14 attendance rows for Rahim" |
| A test scanning captured log records for fixture names | The above, mechanically rather than by review |

> **The test is the half U3 proved necessary.** Its gateway adapter
> had a comment saying `error_message` must never be logged, and a
> review-era change added exactly that line. The test caught it; the
> comment had not.

---

## B. Nothing in U4 alerts, and that is a design decision

| Why | Detail |
|---|---|
| No U4 operation costs money | The SMS ceilings are U3's; U4 sends nothing |
| No U4 operation loses data irrecoverably | Removal fails closed; the migration is tested from the real head |
| No U4 operation indicates an attack | Cross-teacher access is **refused**, not detected — a 404 is the correct response, not an event |

> U3 added six alerts and each earned its place. A seventh for
> "enrollment failed" would dilute them, and the correct signal for a
> broken write is the request's own error response.

---

## C. What is NOT recorded, and the honest reason

| Not recorded | Reason |
|---|---|
| Who edited a `display_name`, and when | Cost. Per-row audit is unaffordable in storage at this budget |
| Who edited a `guardian_phone`, and when | **Cost, and this one is weaker** — see C.1 |
| Any roster read | Disproportionate; `team.md` names this explicitly |

### C.1 `guardian_phone` is the uncomfortable one

`display_name` is teacher-authored and the teacher's own record, so
"we do not audit it" follows cleanly.

**`guardian_phone` is also a contact route to a third party.** Editing
it redirects who receives information about a child. The "teacher's
own record" argument does not reach that, and review was right to
press on it.

> V1 still does not audit it, because the alternative is per-row
> logging the budget cannot carry. **That is a cost decision, not a
> principled one**, and it is written here as such so nobody later
> mistakes it for a considered privacy position.
>
> **The revisit trigger is concrete**: the first time the product
> *sends* anything to that number, which is U7's fee-reminder path.
> An unaudited edit to a passive contact field is one thing; an
> unaudited redirect of outbound messages about a child is another.

---

## Assumptions & Open Questions

**None.** [assumption] U5 and U6 inherit the log-content rules
(NFR8.8–NFR8.10) but **not** the no-audit conclusion: attendance and
marks are records *about* a child rather than the teacher's own
contact notes, and each Unit should reach its own answer.
