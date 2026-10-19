# Monitoring Design — `identity-and-access` (U3)

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **One operator, no pager rotation, no dashboard anyone watches.** So the
> design question is not "what could we measure" but **"what must reach a
> human, and what must it not contain"**.
>
> Every alert below either costs money, leaks data, or means the system is
> lying about its state. Nothing else alerts, because an alert nobody acts
> on trains the operator to ignore the ones that matter.

## Sources

- [stage] `infrastructure-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-design/observability-design.md`
- [upstream] `construction/identity-and-access/nfr-design/logical-components.md` — §A, §B
- [upstream] `construction/identity-and-access/nfr-requirements/observability-requirements.md` — NFR8.1–NFR8.7
- [upstream] `construction/identity-and-access/infrastructure-design/infrastructure-specification.md`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR7, NFR12
- [upstream] `inception/domain-design/components.md` — the entity catalogue the
  migration realises
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
  — §2.6, the migration this stage provisions for
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.8
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. What alerts, and why each earns it

| Alert | Trigger | Why it reaches a human |
|---|---|---|
| **SMS ceiling breached** | Global daily ceiling hit | Money. Also the signal for an active attack |
| **Gateway balance low** | `getBalanceApi` below threshold | Money, with lead time rather than after the fact |
| **Backup failed** | `pg_dump` or its upload fails | The one thing that cannot be rolled back |
| **Refresh reuse detected** | `REFRESH_REUSE_DETECTED` written | A stolen token, or a client bug — both need a human |
| **Audit write failed** | The append-only write fails | §A.1 |
| **Smoke failed after deploy** | Post-deploy smoke set | The system is serving and wrong |

### A.1 The audit-write alert closes a deliberate hole

The audit log is the one component that **fails open** — it must not fail
the authentication it was recording. That makes it suppressible by causing
write failures, which would be a real weakness if it were silent.

> So the failure is **silent to the user and loud to the operator**. That
> is the whole resolution of the tension, and it only works if this alert
> exists. An audit log that can be disabled without anyone noticing is
> worse than one that fails loudly.

### A.2 What deliberately does not alert

| Not alerted | Why |
|---|---|
| A single failed OTP verify | Normal. Users mistype |
| A per-number ceiling trip | Normal under the design — the sub-ceiling is *working* |
| Gateway `UNKNOWN` | Expected; the user is offered a resend |
| High request latency | No baseline yet, so any threshold is invented |

> **The per-number row matters.** It is tempting to alert on every refused
> send, and that would fire constantly once the product has users — which
> trains the operator to ignore the global ceiling alert sitting in the
> same channel.

---

## B. What is retained, and for how long

| Data | Retention | Why bounded |
|---|---|---|
| Auth audit log | **12 months** | Long enough to answer a parent complaint; the COPPA/GDPR-K question is about the recent past |
| OTP records | **7 days** | High volume, contains a phone number, obviously short-lived |
| Rate-limit counters | **48 hours** | The longest window is a day |
| Refresh tokens | Until expiry + 30 days | Reuse detection needs the rotated-out row to exist |
| Production session log | **12 months** | Matches the audit log; same question |

> **The OTP and counter rows carry phone numbers and are high-volume**, so
> an unbounded table is both a storage cost and a growing disclosure
> surface. `team.md` already names these as the data class where the
> retention answer is uncontroversial and the win is largest.

**A scheduled purge enforces these**, and its own failure alerts — an
unenforced retention policy is a policy that exists only in a document.

---

## C. Health, and what it must not become

```
GET /health → { status, database: ok|fail, migration_revision }
```

**Unversioned, public, and deliberately thin.** It reports liveness, database
connectivity and the applied Alembic revision — enough for the post-deploy
smoke set to be meaningful.

> **It must not grow into a diagnostic endpoint.** It is one of the five
> `PUBLIC_ROUTES`, reachable by anyone, so every field added is
> information disclosed. Version numbers, dependency states and queue
> depths do not belong here.

---

## D. The correlation id ties an investigation together

Every request carries one; it appears in every log line and every audit
row [NFR8.6], and **nowhere does it travel with the content it
correlates**. That is what makes an investigation possible without the log
itself becoming the leak.

---

## E. What is not built

| Not built | Why |
|---|---|
| Metrics dashboard | No operator watches one. An alert reaching a phone beats a chart nobody opens |
| Distributed tracing | One process |
| Per-row access logging | Disproportionate and unaffordable in storage |
| SLI/SLO tracking | Needs an availability target Phase 1 cannot honestly state |
| Log aggregation service | Budget. Container logs plus the audit table are the Phase 1 answer |

---

## Assumptions & Open Questions

**One.** [assumption] Alert **delivery** — email, SMS or push, and to
which address — is a provisioning decision taken at deployment. This
document states what must alert and why; the channel does not change the
design. Worth noting the irony: alerting the SMS ceiling *by SMS* would be
the one alert that costs money to deliver.
