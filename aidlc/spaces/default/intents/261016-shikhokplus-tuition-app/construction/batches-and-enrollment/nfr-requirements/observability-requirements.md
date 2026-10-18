# Observability Requirements — `batches-and-enrollment` (U4)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **One operator, no pager rotation.** The question is not what could
> be measured but **what must reach a human, and what must never
> appear in a log line**.

## Sources

- [upstream] `functional-design/rules.md` — BR6.2, BR6.3
- [upstream] `inception/requirements-analysis/requirements.md` — NFR8, NFR14
- [upstream] `construction/identity-and-access/nfr-requirements/observability-requirements.md`
  — NFR8.1–NFR8.7, which this Unit inherits unchanged
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. What a U4 log line may never carry

U3's rule was "no phone number, no OTP, no token". **U4 introduces the
first child-identifying strings**, so the rule gains two entries.

| ID | Requirement | Why |
|---|---|---|
| **NFR8.8** | No log line carries `display_name` or `guardian_phone` | Both are child-identifying under RC-1/RC-2/RC-3. `display_name` is the first such string in the system — U3 had none |
| **NFR8.9** | An enrollment is identified in logs by `enrollment_id` only | It is already the teacher-facing key [ADR-001], so this costs nothing and removes the temptation to log a name "for readability" |
| **NFR8.10** | A failed removal logs the **reason class**, never the history it found | "refused: has history" is actionable; "refused: 14 attendance rows for Rahim" is a disclosure |

---

## B. What alerts, and what deliberately does not

| ID | Requirement | Why |
|---|---|---|
| **NFR8.11** | Nothing in U4 alerts | No U4 operation costs money, loses data irrecoverably, or indicates an attack. An alert nobody acts on trains the operator to ignore the ones that matter |

> **Stated as a requirement rather than an omission.** U3 added six
> alerts and each earned its place. Adding a seventh for "enrollment
> failed" would dilute them, and the correct signal for a broken write
> is the request's own error response.

---

## C. The audit log is NOT extended here

| ID | Requirement | Why |
|---|---|---|
| **NFR8.12** | U4 writes no `AuthAuditLog` row | That log's five events are authentication events, and its closed enum is the mechanism keeping it that way [U3 NFR8.1] |
| **NFR8.13** | Enrollment changes are **not** audited in V1 | Per-row access logging is disproportionate and unaffordable in storage [team.md]. The question COPPA and GDPR-K assume answerable is about *access to a child's data*, which the auth log already covers at the session boundary |

> **NFR8.13 is a real limitation, recorded rather than glossed.** If a
> teacher edits a display name, nothing records who or when. That is
> acceptable because the teacher authored the field and it is their own
> record — but it would **not** be acceptable for attendance or marks,
> and U5 and U6 should reach their own conclusion rather than
> inheriting this one.

---

## Assumptions & Open Questions

**None.** [assumption] NFR8.11's "nothing alerts" holds for V1's
feature set; if a later Unit adds a scheduled job touching enrollments,
that job's failure is an operational event and alerts under U3's
existing backup-failure precedent.
