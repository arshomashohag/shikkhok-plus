# Monitoring Design — D2 `running-a-batch`

**Stage**: infrastructure-design (3.4)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 adds no alert, no audit event and no metric backend.** What it adds is
> one number a teacher reads and one failure mode nothing on the server can
> see — and those two are the whole of this document.

## Sources

- [upstream] `construction/running-a-batch/nfr-design/security-design.md` § 1
  — the obligation with no server-side backstop
- [upstream] `construction/running-a-batch/nfr-requirements/security-requirements.md`
  — NFR14.30, NFR23.4–NFR23.6
- [prior] D1's `infrastructure-design/monitoring-design.md` — the alert set
  and retention table this unit inherits
- [code] `app/audit/log.py`, `app/auth/ceilings.py`, read 2026-10-23

---

## Collection

| Signal | D2's change |
|---|---|
| Application logs | None. Same sink, same correlation id |
| Auth audit | **No new event** |
| Ceiling alerts | None. D2's routes are authenticated |
| Deploy verification | None |
| Metrics | One countable outcome worth naming, below |

**D2 adds no `AuthEvent` member**, deliberately. The authentication log
records authentication events; reading a roster is not one. Widening that
closed vocabulary for ordinary reads would weaken the property that makes the
log reviewable — and it is the same reasoning that kept D1's signup events
*in* the log, because those genuinely are authentication-surface events.

---

## Alerting

| Condition | Alerts? | Change |
|---|---|---|
| Global daily SMS ceiling | Yes | **unchanged, not on a D2 path** |
| Narrow ceilings | **No** | unchanged |
| Audit write failure | Yes | unchanged |
| Pre-migration backup failure | Yes | **not applicable — D2 has no migration** |
| Deploy health check | Yes | unchanged |

**D2 adds no alert.** Stated rather than omitted because a unit that renders
four new screens invites one — "tell me when a removal is refused" reads as
helpful and is not: a refused removal is a teacher learning a rule, not an
incident, and the refusal already explains itself on screen.

---

## The one metric worth naming

| Metric | Dimensions | Answers |
|---|---|---|
| Decline rate per batch | accepted / declined / pending | **Whether teachers are mistyping numbers** |

D1 named this as one of the two metrics that measure whether the acceptance
model worked. **D2 is where it becomes readable**, because `accepted_count`
against `enrollment_count` is the same number a teacher sees on the batch
list — so the operational metric and the product's own display are the same
derivation, and they cannot disagree.

That identity is a consequence of [NFR20.9], the rule that the server computes
the count. Had the client counted rows, the metric and the display would be
two derivations of one number, and the first disagreement would be a bug
nobody could locate.

Derived by query from existing data; Phase 1 carries no metrics backend and
D2 adds none [NFR7.5 of D1].

---

## The failure mode nothing can observe

**Back after a guardian switches child** [NFR14.30].

| Property | Consequence for monitoring |
|---|---|
| Both requests are legitimately authorized | No server-side signal distinguishes them |
| The lens is correct in both cases | No authorization log entry differs |
| The data returned is correct for the child named | No response is anomalous |

**There is nothing to alert on, nothing to log, and nothing to count.** This
is the one obligation in D2 that monitoring cannot help with at all, which is
why the design answers it structurally — the switch is a selection, so no
back entry exists — and why its verifier is a Robolectric rendering test
rather than anything operational [NFR23.6].

Recorded here rather than left to the security design, because "no monitoring
coverage" is exactly the kind of gap that is invisible unless a monitoring
document says so.

---

## Logging

Unchanged. D2 adds two response fields, and neither is personal data: both are
decision enums. The existing rules carry over without extension:

| Rule | Status |
|---|---|
| No phone number, OTP, token, address or self-authored name in any log | unchanged |
| Every error log carries the correlation id | unchanged |
| Tracebacks never returned to a client | unchanged |

---

## Retention

| Table | Disposition | Enforced? | D2's effect |
|---|---|---|---|
| `auth_audit_log` | `RETAIN_WITH_BASIS`, 12 months | **No job** | **adds no row** |
| `rate_limit_counter` | `HARD_DELETE`, 48 hours | **No job** | **adds no row** |

Both gaps are unchanged and neither is enlarged by this unit: D2's routes are
authenticated, so they touch no counter, and D2 raises no audit event.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to the host's stdout and existing collection.
- **Assumed**: the decline-rate metric is derived by query rather than
  emitted, consistent with D1.
- **Open, and not D2's**: both purge jobs above.
