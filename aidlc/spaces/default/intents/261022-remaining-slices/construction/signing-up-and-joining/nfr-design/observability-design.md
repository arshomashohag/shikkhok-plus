# Observability Design — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> The design problem here is **alert discipline** and **what must not be
> observable**. D1 doubles the number of narrow rate-limit ceilings in a
> system whose one meaningful alert sits in the same channel, and it adds two
> personal fields to a product whose logs already forbid five.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-requirements/observability-requirements.md`
  — NFR24.x, NFR25.x, NFR26.x
- [upstream] `construction/signing-up-and-joining/nfr-requirements/reliability-requirements.md`
  — NFR25.3
- [code] `app/audit/log.py`, `app/auth/ceilings.py`,
  `app/governance/dispositions.py`, read 2026-10-23

---

## 1. The audit log

### Structure, and why it has no free-form field

```
auth_audit_log row:
  id              uuid
  account_id      uuid | null
  event           AuthEvent        ← closed enum
  occurred_at     timestamp
  correlation_id  str              ← the ONLY string
```

Two properties carry the whole design [NFR24.1, NFR24.2]:

- **The vocabulary is closed.** An open one is how a free-form value re-enters
  a log specified not to have one. D1 adds **named members** for account
  creation [NFR12.9] and signup ceiling breaches [NFR12.10], not a `detail`
  column [NFR12.7]. Account creation earns its place in the authentication
  log on its merits: rate-limited, reachable unauthenticated, and the point
  where an enumeration attempt would surface.
- **`correlation_id` is the only string**, and it ties a row to a request
  *without carrying its contents*. A test asserts the dataclass has no other
  `str` field — stronger than a review comment, and the mechanism rather than
  the intent.

### A ceiling breach records its scope kind, never its scope value

The scope *value* is a phone number or an IP prefix [NFR12.10]. The scope
*kind* (`signup_number_hour`) is the diagnostic fact and carries no identity.
This is the specific place where an operator debugging in good faith would
otherwise add the number.

### The write path, and why it alerts

```
savepoint = session.begin_nested()
  try:    INSERT ...; savepoint.commit()
  except: savepoint.rollback(); log.critical(...)
```

**The savepoint is load-bearing**: a nested transaction confines the abort, so
an audit failure leaves the caller's work intact and committable. That is what
makes the component fail open — and what makes it suppressible by anyone who
can cause write failures.

**The alert is therefore part of the design, not a nicety** [NFR12.11,
NFR25.3]. Without it, this is a security control with a documented off switch.
The two halves — silent to the user, loud to the operator — are one decision:
the savepoint buys the silence, and the `critical` log is what makes the
silence acceptable.

---

## 2. Alerting design

| Event | Alerts? | Design reason |
|---|---|---|
| **Global** daily SMS ceiling trips | **Yes** | Money, and the signal of an active attack [NFR25.1] |
| Signup per-number or per-IP ceiling trips | **No** | [NFR25.2] — see below |
| OTP per-number or per-IP ceiling trips | **No**, unchanged | Same reason |
| Audit write fails | **Yes** | [NFR25.3] |
| Pre-migration backup fails | **Yes** | An unverified upload is not a backup [NFR25.4] |

### The non-alert is the design decision

The built module states the reasoning plainly: narrow sub-ceilings fire
constantly once the product has users, and an alert that fires constantly in
the same channel as the global one **trains the operator to ignore the global
one**.

D1 doubles the number of narrow ceilings, which doubles the temptation to
wire them up — each individually looks like a reasonable thing to know about.
The thing being protected is the signal value of the one alert that means
*money is being spent on an attack*.

**A rate of narrow breaches is a dashboard, not a page.** A sustained rise in
signup refusals is genuinely interesting — it is what an enumeration attempt
looks like — but it is a trend to read, not an interruption.

---

## 3. Metrics

Counts only, **never the values** — a metric labelled by phone number is a
phone number in a metrics store [NFR24.1].

| Metric | Dimensions | What it answers |
|---|---|---|
| Signup attempts | outcome: success / ceiling / duplicate / validation | Is signup working, and is it being attacked [NFR25.5] |
| Acceptance transitions | kind: accepted / declined | **Teacher data-entry quality** [NFR25.6] |
| Pending-seat population | age bucket | Is the pending set *growing* [NFR25.7] |
| Lookup calls | outcome: found / not-found | Enumeration shape |

### Two of these are the product's feedback on itself

**The decline rate and the pending population** [NFR25.6, NFR25.7] measure the
thing this unit exists for. D1 was built because a mistyped phone number
silently granted a stranger a guardian lens; after D1, that same mistype
surfaces as a decline or as a seat nobody accepts. So these are not
operational metrics that happen to be available — they are the only visible
evidence that the exposure is being caught rather than merely prevented.

A seat pending indefinitely is **expected** [FR1.9e]. A rising population of
them is not, which is why the metric is bucketed by age rather than counted
flat.

### Derivation, not a backend

These are derivable from the audit log and application logs. Phase 1's budget
carries no metrics backend [NFR7.5], and these are low-cardinality counts — so
the design is a query over existing data rather than a new system.

---

## 4. Logging design

| Rule | Scope | Requirement |
|---|---|---|
| No phone number, OTP, token, `address` or `self_name` at any level | Application logs, error output, exception context | NFR24.1, **NFR12.8** |
| Every error log carries the request or correlation id | All | NFR24.2 |
| Gateway request bodies never logged | Any level | NFR24.3 — the OTP is in the body |
| Tracebacks never returned to a client | All | NFR24.4 |

**NFR24.4 matters more in this unit than elsewhere**: signup is
unauthenticated, so its tracebacks would reach the public rather than a
signed-in user.

**No distributed tracing in V1.** One host, two workers, a USD 50/month
ceiling. A correlation id through structured logs is the tracing this scale
supports, and it already exists.

---

## 5. SLIs and SLOs

| SLI | Target | Discharged by |
|---|---|---|
| Signup success rate, excluding ceiling refusals | **None set for V1** | Measured through the pilot [NFR26.1] |
| Accounts holding only unaccepted links that resolve a role lens | **Zero** | The adversarial test, not a monitor [NFR26.2] |

**NFR26.2 is an SLI with a target of zero and a test rather than a monitor**,
deliberately. It is the unit's whole purpose, it is machine-checkable before
deployment, and a monitoring threshold on it would be an admission that it
might be non-zero in production. Recorded so it is not later re-invented as a
dashboard panel.

**No SLO percentages are invented.** Phase 1 is closed testing with a small
pilot audience; a 99.x% target set now would be a number nobody derived from
anything.

---

## 6. Retention

| Table | Disposition | Retention | Enforced? |
|---|---|---|---|
| `auth_audit_log` | `RETAIN_WITH_BASIS` | 12 months | **No job** |
| `rate_limit_counter` | `HARD_DELETE` | 48 hours | **No job** |

Both dispositions are declared in the governance manifest with stated bases —
the audit log's is that both COPPA and GDPR-K assume a question about improper
access to a child's data can be answered later.

**Neither has an enforcing job**, and D1 adds rows to both. The design does
not invent the job here: it is infrastructure, D1 adds none, and the team
practice already names auth records as the first data class to carry a
scheduled purge. What this unit owns is naming that it enlarges both tables
against retentions nothing currently applies.

---

## Assumptions & Open Questions

- **Assumed**: logs continue to go to the host's standard output and existing
  collection. D1 adds no sink [NFR7.5].
- **Assumed**: the metrics above are derived by query rather than emitted to a
  metrics backend, which Phase 1 does not have.
- **Open, and not D1's**: the purge jobs for both tables above. The
  dispositions exist; the enforcement does not.
