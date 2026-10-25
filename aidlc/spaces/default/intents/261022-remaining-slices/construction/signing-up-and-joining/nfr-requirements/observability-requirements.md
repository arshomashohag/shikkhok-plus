# Observability Requirements — D1 `signing-up-and-joining`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> This unit's observability problem is **what must not be observable**. It
> handles phone numbers, one-time codes, a self-authored name and a home
> address, on a children's-data product. The second problem is alert
> discipline: D1 adds a rate-limit cascade, and the built one is explicit that
> narrow ceilings must not alert.

## Sources

- [upstream] `construction/signing-up-and-joining/functional-design/rules.md` — BR2.x, BR3.x
- [prior] NFR12 of `261016-shikhokplus-tuition-app`
- [team] Deployment practice, 2026-10-22
- [code] `app/audit/log.py`, `app/auth/ceilings.py`, read 2026-10-23

---

## What must never be logged

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR24.1 | No log line at any level carries a phone number, an OTP, a token, an `address`, or a `self_name` | Applies to application logs, error output and exception context alike | [team: Deployment] [BR3.2] |
| NFR24.2 | Every error log carries the request or correlation id and nothing identifying | The correlation id ties a row to a request **without carrying its contents** | [code: `audit/log.py`] |
| NFR24.3 | Gateway request bodies are never logged at any level | The OTP is in the body | [team: Deployment] |
| NFR24.4 | Exception tracebacks are never returned to a client | Signup is unauthenticated, so its tracebacks reach the public | [team: Deployment] |

**NFR24.1 extends an existing rule to two new fields and that is the whole
change.** The structural guarantee is already built and worth not weakening:
the audit row dataclass has **no free-form string field** but
`correlation_id`, asserted by a test, because a `message` or `note` column is
where a phone number eventually lands — added by someone debugging in good
faith.

---

## The audit log

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR12.9 | Account creation is recorded as a **named member** of the closed `AuthEvent` vocabulary | Not a free-form value, not a new open field | [code: `audit/log.py`] |
| NFR12.10 | A signup ceiling breach is recorded with its scope kind and no scope value | The scope *value* is a phone number or an IP prefix | [NFR24.1] [BR2.1] |
| NFR12.11 | The audit write fails **silent to the user, loud to the operator** | It must not fail the authentication it records, and its suppression must not be silent | [code: `audit/log.py`] [NFR25.3] |

**NFR12.11 is the requirement that makes the fail-open design safe.** The
audit component deliberately does not fail the operation it records, which
means anyone who can cause write failures can suppress it. That trade is only
acceptable because the failure alerts; without the alert, the component is a
security control with a documented off switch.

---

## Alerting

| ID | Requirement | Alert? | Source |
|---|---|---|---|
| NFR25.1 | The **global** daily SMS ceiling tripping | **Yes** — money, and the signal of an active attack | [code: `ceilings.py`] |
| NFR25.2 | A signup **per-number** or **per-IP** ceiling tripping | **No** | [code: `ceilings.py`] |
| NFR25.3 | An audit-write failure | **Yes** | [NFR12.11] |
| NFR25.4 | A failed pre-migration backup | **Yes** | [team: Deployment] [NFR19.3] |

**NFR25.2 is a deliberate non-alert and D1 is where it would be got wrong.**
The built module states the reasoning: the per-number and per-IP sub-ceilings
fire constantly once the product has users, and an alert that fires constantly
in the same channel as the global one trains the operator to ignore the global
one. Adding a second cascade doubles the number of narrow ceilings, so it
doubles the temptation — and the thing worth protecting is the signal value of
the one alert that means *money is being spent on an attack*.

**A rate of narrow breaches is a dashboard, not an alert.** A sustained rise
in signup refusals is genuinely interesting — it is what an enumeration
attempt looks like — but it is a trend to look at, not a page.

---

## Metrics and dashboards

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR25.5 | Signup attempts, successes and refusals are countable by outcome | Refusals distinguishable by cause: ceiling, duplicate number, validation | [BR2.1] [BR4.4] |
| NFR25.6 | Acceptance and decline transitions are countable | A decline rate is the signal that teachers are mistyping numbers | [BR5.2] |
| NFR25.7 | Pending-seat age is observable | A seat pending indefinitely is expected [FR1.9e]; a *rising* population of them is not | [FR1.9e] |

**NFR25.6 and NFR25.7 are the two numbers that tell this unit whether it
worked.** The unit exists because a mistyped number silently granted a
stranger a lens. After D1 that mistype surfaces as a decline or as a seat
nobody accepts — so the decline rate and the pending population are the
product's feedback on data-entry quality, not just operational metrics.

**Counts only, never the values.** A metric labelled by phone number is a
phone number in a metrics store [NFR24.1].

---

## SLIs and SLOs

| ID | SLI | SLO | Source |
|---|---|---|---|
| NFR26.1 | Signup success rate: `successful_signups / signup_attempts_excluding_ceiling_refusals` | No target set in V1; measured through the pilot | [OC-5] |
| NFR26.2 | Lens resolution correctness: accounts holding only unaccepted links that resolve a role lens | **Zero**, asserted by the adversarial test rather than monitored | [BR1.1] |

**NFR26.2 is an SLI with a target of zero and a test rather than a monitor.**
It is the unit's whole purpose, it is machine-checkable before deployment, and
a monitoring threshold on it would be an admission that it might be non-zero
in production. It is recorded here so it is not later re-invented as a
dashboard.

**No SLO numbers are invented for V1.** Phase 1 is closed testing with a small
pilot audience. A 99.x% target set now would be a number nobody derived from
anything, which the project's own practice forbids.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to the host's standard output and the
  existing collection, with no new sink in D1. D1 adds no infrastructure
  [NFR7.5].
- **Assumed**: the metrics in NFR25.5–25.7 are derivable from the audit log
  and application logs rather than needing a metrics backend. Phase 1's budget
  does not carry one, and these are low-cardinality counts.
- **Open, and D6's**: the retention period and scheduled purge for the signup
  audit events, under the practice naming auth records as the first data class
  to carry one.
