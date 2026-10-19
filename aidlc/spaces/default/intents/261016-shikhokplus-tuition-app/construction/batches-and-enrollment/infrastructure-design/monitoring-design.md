# Monitoring Design — `batches-and-enrollment` (U4)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **U4 adds no alert**, and that is a decision with reasons rather
> than an omission. What it does add is one thing the operator must be
> able to see at deploy time, and two retention rows.

## Sources

- [upstream] `nfr-design/observability-design.md` — §A, §B, §C.1
- [upstream] `nfr-requirements/observability-requirements.md` — NFR8.8–NFR8.13
- [upstream] `construction/identity-and-access/infrastructure-design/monitoring-design.md`
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. Nothing new alerts

U3's six alerts stand. U4 adds none, because no U4 operation costs
money, loses data irrecoverably, or indicates an attack.

| Candidate | Rejected because |
|---|---|
| "Enrollment failed" | The request's own error response is the signal |
| "Removal refused" | The refusal **is** the correct behaviour, fired on every protected row |
| "Cross-teacher access attempted" | A 404 is the response, not an event. Alerting would also make a scanner into a pager storm |

> U3 added six and each earned its place. A seventh that fires on
> normal operation trains the operator to ignore the channel the SMS
> ceiling shares.

---

## B. The one thing the deploy must surface

The `0002` migration **refuses to run** when it finds a guardian row
whose batch has a student count other than one — the shape the
skeleton seed leaves behind.

| Requirement | Why |
|---|---|
| The refusal message names the **batch id** and the **count found** | "Migration failed" sends the operator to the logs; "batch X has 0 students and a guardian row" sends them to the fix |
| It names the **remedy**: delete the seed rows, then redeploy | The ordering is not inferable from the error alone |

> This is the only new operational failure mode in the Bolt, and it
> fires **before** any data is altered. Its message is the whole user
> interface for that situation.

---

## C. Retention, extended for two tables

| Data | Retention | Why |
|---|---|---|
| `Batch`, `BatchSubject`, `ScheduleSlot` | Life of the owner | The teacher's own record; `active = false` retires without deleting |
| `Enrollment` | Life of the owner | Anonymize-in-place on erasure, never a hard delete [Governance manifest] |
| `HiddenBatchPreference` | Hard delete with the account | Purely the viewer's own UI preference; no teacher ever sees it |

> **No new purge job.** U3's scheduled purge covers the short-lived
> auth tables; nothing U4 creates is high-volume or short-lived, and a
> purge over teacher records would be a deletion mechanism this
> project deliberately does not have.

---

## D. What is deliberately not measured

| Not measured | Why |
|---|---|
| Roster read latency | No baseline; the query-count assertion is the stable check |
| Enrollment counts per teacher | A business metric with no operator action attached |
| Who edited a `display_name` | Per-row audit is unaffordable here [NFR8.13] |
| Who edited a `guardian_phone` | **Same, and weaker** — recorded in observability-design §C.1 as a cost decision with a revisit trigger at U7's first send to that number |

---

## Assumptions & Open Questions

**None.** [assumption] Alert delivery remains the provisioning
decision B3 left open; U4 adds no alert, so it does not reopen it.
