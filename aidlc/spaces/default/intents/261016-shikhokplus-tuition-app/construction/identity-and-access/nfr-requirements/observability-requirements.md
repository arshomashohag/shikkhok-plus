# Observability Requirements — `identity-and-access` (U3)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **Two questions must be answerable, and they drive everything else.** With
> no admin surface and a solo operator, observability here is not about
> dashboards — it is about whether a specific question can be answered when
> it is asked, by one person, possibly months later.

## Sources

- [stage] `nfr-requirements-questions.md` — Q4
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR6.2
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.8
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. The two questions

1. ***"Was this child's data accessed improperly?"*** — which both COPPA and
   GDPR-K assume can be answered, and which a parent complaint will ask.
2. ***"Is something burning the SMS budget right now?"***

| ID | Requirement |
|---|---|
| **NFR8.1** | An **append-only** auth audit log: OTP issued, verify failed, verify succeeded, refresh rotated, refresh reuse detected |
| **NFR8.2** | It holds **no OTP, no token, no phone number and no child name** |
| **NFR8.5** | Every interactive production database session is logged with the person and the stated reason |
| **NFR8.4** | `getBalanceApi` is polled and alerts |

> **NFR8.2 is not a caveat on NFR8.1, it is half the requirement.** An
> audit log that carries the thing it audits is a common and self-defeating
> mistake. The correlation id ties a row to a request without carrying its
> contents.
>
> **NFR8.4 exists because the gateway offers nothing else.** There is no
> delivery report and no message id, so the balance is the only hook — and
> it catches both *"about to run out"* and, indirectly, *"something is
> burning SMS"*.

## B. What is deliberately not built

| Not built | Why |
|---|---|
| Per-row access logging | Disproportionate at this scale and unaffordable in storage. The auth log plus the production-session log is the honest middle |
| Distributed tracing | One process. There is nothing to correlate across |
| A metrics dashboard | No operator watches one. An alert that reaches a phone is worth more than a chart nobody opens |
| An SLI/SLO pair | Requires an availability target, which Phase 1 cannot honestly state |

## C. Logging rules

| ID | Requirement |
|---|---|
| **NFR8.6** | Every error log carries the correlation id |
| **NFR8.7** | No log line carries a phone number, an OTP, a token or a child name [BR6.2] |
| **NFR9.2** | `error_message` from the gateway is never logged — it echoes the API key in plaintext |
| **NFR9.7** | The gateway request body is never logged — it carries the number and the code together |

> NFR8.7 is a **compliance** rule rather than hygiene: phone numbers are
> children's-adjacent personal data under RC-1/RC-2/RC-3.

---

## Assumptions & Open Questions

**None.** [assumption] Alert *delivery* — where an alert goes and who sees
it — belongs to Infrastructure Design. This document states what must alert.
