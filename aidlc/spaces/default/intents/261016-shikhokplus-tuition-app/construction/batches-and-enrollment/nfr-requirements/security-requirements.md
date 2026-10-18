# Security Requirements — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **This is the first Unit with two teachers in it.** U3 proved the
> lens mechanism against one account; here there are two parties for
> data to leak between, which is the project's stated top risk getting
> its first real test.

## Sources

- [upstream] `functional-design/rules.md` — BR1.2, BR2.1, BR5.0–BR5.4, BR6.1–BR6.3
- [upstream] `functional-design/entities.md` — the catalogue-aligned model
- [upstream] `inception/requirements-analysis/requirements.md` — NFR10, NFR14
- [upstream] `inception/domain-design/components.md` — the Governance manifest
- [upstream] `construction/identity-and-access/nfr-requirements/security-requirements.md`
- [team] `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Cross-teacher isolation — the top risk, first testable here

| ID | Requirement | Why |
|---|---|---|
| **NFR14.12** | Every teacher-facing query scopes on `owner_id` from the lens object, never on a request parameter | The lens **carries** the scoping value [TC-11], so a handler cannot compile a scoped query without it |
| **NFR14.13** | Another owner's batch returns **404**, not 403 | A 403 confirms the batch exists; the uniform rule is already in `app/errors/codes.py` |
| **NFR14.14** | A named test enrolls one account with **two teachers** and asserts neither roster shows the other's row | B3 could only demonstrate the mechanism; this is the first Bolt with two parties to leak between |
| **NFR14.15** | Guardian reachability resolves through `guardian_account_id`, never through the child [BR5.3] | Resolving through the child merges two teachers' records — worked, and it leaks |

---

## B. The privacy boundary U3 built structurally, now first written against

| ID | Requirement | Why |
|---|---|---|
| **NFR14.16** | No U4 module reads or writes `Profile` | U3 split the tables; **U4 is the first Unit that writes `display_name`**, so it is the first place a well-meant fallback to `Profile.self_name` could violate the split |
| **NFR14.17** | `display_name` and `guardian_phone` survive account deletion | They are teacher-authored and the teacher's own contact record [ADR-003, FR2.6, Governance manifest] |
| **NFR14.18** | A platform administrator reads `Owner.state`, `plan`, `plan_valid_to` and nothing else [BR1.2] | No admin surface exists in V1; the rule is recorded because the `Owner` table is written for the first time here |

---

## C. Erasure, and the mechanism that must not be defeated

| ID | Requirement | Why |
|---|---|---|
| **NFR14.19** | Dormant-enrollment resolution **skips** any row whose relevant relink marker is set | Without it, an erased student whose number returns is silently reattached to their own erased history — defeating the erasure invisibly |
| **NFR14.20** | The markers are **per link**: `student_relink_blocked_at` and `guardian_relink_blocked_at` | One flag means a guardian's erasure permanently blocks a student who never claimed that row. Worked all four states; three behave and one does not |
| **NFR14.21** | Removal requires the student seat dormant **and never erased**, plus no history [BR6.1] | After erasure the account column is NULL again, so a null-only test would **delete the erased row** and destroy the marker NFR14.19 depends on |

> **NFR14.21 is the subtle one.** The naive translation of "delete only
> if unclaimed" is `student_account_id IS NULL`, which is true both
> before a claim and after an erasure. Those are the two cases with
> opposite correct answers.

---

## D. What is deliberately not specified

| Not specified | Why |
|---|---|
| Field-level encryption on `display_name` | NFR10 requires encryption **at rest**, satisfied by the storage tier. Field-level encryption would make the roster unsearchable for no additional disclosure protection |
| Rate limits on roster reads | The authenticated surface has no per-SMS cost. U3's ceilings exist because sends spend money; reads do not |
| An audit row per roster read | Per-row access logging is disproportionate and unaffordable in storage, and `team.md` says so |

---

## Assumptions & Open Questions

**One, flagged rather than silently resolved.** [assumption] NFR14.20
**diverges from the upstream catalogue**, which declares a single
`relink_blocked_at`. The divergence is recorded in `rules.md` BR6.2
with the four worked states, and U11 implements erasure against the
per-link shape. Raising it rather than redesigning quietly is the
point: the catalogue's rationale is written entirely about an erased
*student* and never considers the guardian link erasing independently.
