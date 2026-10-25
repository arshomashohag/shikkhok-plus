# Monitoring Design — D1 `signing-up-and-joining`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> D1 adds **no monitoring infrastructure and no alert**. What it changes is
> what the existing logs contain and what the existing audit log records. The
> design decision carried forward from `nfr-design/observability-design.md` is
> a **non-alert**, and this document exists partly to keep it from being
> quietly reversed.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-design/observability-design.md`
- [upstream] `construction/signing-up-and-joining/nfr-design/reliability-design.md`
  — the fail-open audit component
- [upstream] `construction/signing-up-and-joining/nfr-requirements/observability-requirements.md`
  — NFR24.x, NFR25.x, NFR26.x
- [code] `app/audit/log.py`, `app/auth/ceilings.py`, `.github/workflows/deploy.yml`,
  read 2026-10-23

---

## Collection

| Signal | Mechanism | Destination | D1's change |
|---|---|---|---|
| Application logs | Structured, carrying the correlation id | Host stdout, existing collection | Two new forbidden fields [NFR24.1] |
| Auth audit | `auth_audit_log` table, closed event vocabulary | PostgreSQL | **New members**: account creation [NFR12.9], signup ceiling breach [NFR12.10] |
| Ceiling alerts | `log.critical` on the global scope only | Operator channel | **None** — narrow scopes do not alert [NFR25.2] |
| Deploy verification | SSM `AWS-RunShellScript`, provisioning log plus `/health` | Workflow step summary | None |
| Metrics | Derived by query from the above | — | Four new counts [NFR25.5–25.7] |

**No metrics backend, and no distributed tracing** [NFR7.5]. Phase 1 is one
host, two workers, under a USD 50/month ceiling; a correlation id through
structured logs is the tracing this scale supports, and it already exists.

---

## Alerting

| Condition | Alerts? | Channel | Requirement |
|---|---|---|---|
| **Global** daily SMS ceiling trips | **Yes** | `log.critical` | NFR25.1 |
| Signup per-number / per-IP ceiling trips | **No** | — | NFR25.2 |
| OTP per-number / per-IP ceiling trips | **No**, unchanged | — | NFR25.2 |
| Audit write fails | **Yes** | `log.critical` | NFR12.11, NFR25.3 |
| Pre-migration backup fails | **Yes** | Deploy step failure | NFR25.4 |
| Deploy health check fails | **Yes** | Workflow failure + `::error::` | existing |

### The non-alert, restated because D1 is where it would be reversed

The built module states the reasoning: narrow sub-ceilings fire constantly
once the product has users, and an alert firing constantly in the same channel
as the global one **trains the operator to ignore the global one** — which is
the alert that means money is being spent on an attack.

**D1 doubles the number of narrow ceilings.** Each new one individually looks
like a reasonable thing to be told about. The design's answer is that a rate
of narrow breaches belongs on a dashboard, not in a pager.

### The alert that makes a fail-open component acceptable

The audit write runs inside `session.begin_nested()` so a failure confines
itself to the savepoint and leaves the caller's transaction committable. That
is deliberate — the log must not fail the authentication it records — and it
makes the component **suppressible by anyone who can cause write failures**.

The `log.critical` is what converts that from a weakness into a trade
[NFR12.11]. It is a monitoring requirement with a security purpose, which is
why it appears in this table rather than only in the reliability design.

---

## Metrics

Counts only, **never the values** — a metric labelled by phone number is a
phone number in a metrics store [NFR24.1].

| Metric | Dimensions | Source | Answers |
|---|---|---|---|
| Signup attempts | success / ceiling / duplicate / validation | Audit + app logs | Is signup working, and is it being attacked [NFR25.5] |
| Acceptance transitions | accepted / declined | Audit | **Teacher data-entry quality** [NFR25.6] |
| Pending-seat population | age bucket | Query | Is the pending set *growing* [NFR25.7] |
| Lookup calls | found / not-found | App logs | Enumeration shape |

**Two of these are the product's feedback on whether this unit worked.** D1
exists because a mistyped phone number silently granted a stranger a guardian
lens. After D1 that same mistype surfaces as a decline or a seat nobody
accepts — so the decline rate and the pending population are the only visible
evidence that the exposure is being *caught* rather than merely prevented.

A seat pending indefinitely is expected [FR1.9e]; a rising population of them
is not, which is why the metric is bucketed by age rather than counted flat.

---

## Dashboards

One view, derived by query rather than provisioned:

| Panel | Contents | Why not an alert |
|---|---|---|
| Signup health | Attempts by outcome over time | A refusal rate is a trend, not an incident |
| Acceptance | Decline rate, pending population by age | Data-entry quality is a conversation, not a page |
| Ceilings | Narrow-scope breach counts | [NFR25.2] |

**No dashboard infrastructure is provisioned** [NFR7.5]. These are queries
over the audit log and application logs; naming them here is what keeps them
from being re-derived from scratch when someone asks whether D1 worked.

---

## Logging rules D1 must honour

| Rule | Requirement |
|---|---|
| No phone number, OTP, token, `address` or `self_name` at any level | NFR24.1, NFR12.8 |
| Every error log carries the request or correlation id | NFR24.2 |
| Gateway request bodies never logged — the OTP is in the body | NFR24.3 |
| Tracebacks never returned to a client | NFR24.4 |
| A ceiling breach records its scope **kind**, never its scope **value** | NFR12.10 |

**NFR24.4 matters more in this unit than elsewhere**: signup is
unauthenticated, so its tracebacks would reach the public rather than a
signed-in user.

---

## SLIs and SLOs

| SLI | Target | Discharged by | Requirement |
|---|---|---|---|
| Signup success rate, excluding ceiling refusals | **None set for V1** | Measured through the pilot | NFR26.1 |
| Accounts on only unaccepted links that resolve a role lens | **Zero** | The adversarial test, **not a monitor** | NFR26.2 |

**NFR26.2 is deliberately a test rather than a monitor.** It is the unit's
whole purpose, it is machine-checkable before deployment, and a monitoring
threshold on it would be an admission that it might be non-zero in production.
Recorded here so it is not later re-invented as a dashboard panel.

**No SLO percentages are invented.** Phase 1 is closed testing with a small
pilot audience; a 99.x% target set now would be a number nobody derived from
anything, which this project's own rule forbids.

---

## Retention

| Table | Disposition | Retention | Enforced? |
|---|---|---|---|
| `auth_audit_log` | `RETAIN_WITH_BASIS` | 12 months | **No job** |
| `rate_limit_counter` | `HARD_DELETE` | 48 hours | **No job** |

Both dispositions are declared in `app/governance/dispositions.py` with stated
bases — the audit log's being that COPPA and GDPR-K both assume a question
about improper access to a child's data can be answered later.

**D1 adds rows to both and installs neither job** [NFR7.5]. Named here with
that owner so the gap has a reader.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to the host's stdout and existing collection; D1
  adds no sink.
- **Assumed**: the metrics above are derived by query rather than emitted to a
  backend Phase 1 does not have.
- **Open, and not D1's**: both purge jobs above.
