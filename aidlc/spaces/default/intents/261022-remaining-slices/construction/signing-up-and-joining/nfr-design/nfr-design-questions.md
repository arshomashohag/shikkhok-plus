# NFR Design — Questions

**Stage**: nfr-design (3.3)
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

## How this stage was answered

This unit designs **how** 46 stated requirements are met inside a running
system, and almost every mechanism they need already exists: a ceiling
cascade, an error taxonomy, an append-only audit log, a lens dependency, a
row-level-security policy, a gateway adapter. The design work is choosing
**where D1 attaches** to each, and what must not be attached to.

Each answer below is settled from an upstream requirement or from a direct
read of the module it extends, and the source is named. Where nothing settles
it, the answer says so.

---

## Q1. Does signup get a circuit breaker on the SMS gateway?

[Answer]: No, and this is a deliberate departure from the usual pattern.
The gateway already attempts a send **once with no automatic retry**, records
a timeout as `unknown` rather than `failed`, and treats a ceiling breach as a
`ConflictError` rather than a `TransientError`.

A circuit breaker protects a caller from a slow dependency by failing fast
after repeated failures. Here the caller already fails fast — one attempt —
and the thing being protected is a **budget**, which the ceiling cascade
protects directly and more precisely than a failure-rate breaker would. A
breaker would add a second, differently-shaped control over the same
resource, and the two would disagree at the edges.

[team: Error handling] [NFR12.3]

## Q2. What is the retry design for signup?

[Answer]: **The person is the retry.** `ValidationError`, `AuthorizationError`
and `ConflictError` are all non-retryable by class, and signup's failures are
all three: a duplicate number is a conflict, a ceiling breach is a conflict, a
bad input is a validation error. The one retryable class — `TransientError`,
mapped to 503 — is the database being unavailable, and the client's response
to that is to show the error and keep what was typed.

Retryability is a property of the error class and is read off the type in
exactly one place, never decided at a raise site [NFR19.6].

[code: `app/errors/handler.py:66`] [team: Error handling]

## Q3. Where does the signup ceiling check sit relative to the write?

[Answer]: **Before it, and the cascade's own ordering is preserved.** The
check runs narrowest-first and a refusal increments nothing — including the
scope that refused, which the built module releases explicitly.

Placing the check before the transaction means a refused signup writes no
account. Placing it inside would make the refusal a rollback, which costs a
transaction and makes the counter's own increment part of the rolled-back
work.

[NFR12.3] [NFR12.4] [code: `ceilings.py:_release`]

## Q4. Is there a cache anywhere in this unit?

[Answer]: **No, and that is a requirement rather than an omission.** NFR21.1
forbids a cached summary table, denormalised acceptance counts and any
cross-request lens cache. Request-scoped memoization on the request object is
permitted and already exists.

The pressure to cache will arrive with plausible numbers attached, because
lens resolution is the hottest query in the system. The answer the design
gives is the one the built module already gives: one statement, three
booleans, and a memo whose lifetime is the request object's.

[NFR21.1] [NFR20.1] [code: `resolve.py` MEMO_ATTRIBUTE]

## Q5. What is the blast radius of the new unauthenticated routes?

[Answer]: Three routes reachable without a session — signup, the lookup, and
the OTP path they feed. All three write or read only identity data; none
reaches a batch, a fee or a mark. The failure domain is the identity
component, and the component boundary is the thing containing it.

The sharpest blast-radius question is **the staging outbox**, which hands an
OTP to anyone who can call it and is kept out of production three independent
ways. D1 adds a route that causes an OTP to be sent, so it widens what the
outbox would expose if it ever ran in production — without changing any of
the three controls. Stated explicitly rather than assumed.

[code: `app/gateway/outbox.py`] [NFR14.22]

## Q6. How is the privacy boundary enforced for the new address field?

[Answer]: By the mechanism that already exists, plus the enrolment step that
mechanism needs. `Profile` carries the row-level-security policy keyed on the
session account; the schema-wide invariant iterates every teacher-lens
response schema and matches a **field-name set** that is maintained by hand.

So the design is: no new mechanism, one new membership [BR3.4]. The
structural layer and the schema layer both already cover a `Profile` column;
only the name list needs the new entry.

[NFR14.25] [NFR10.14] [BR3.4]

## Q7. Does the invitation lens need its own failure design?

[Answer]: It needs one property: **resolving no invitation is not an error.**
A person with no pending seats holds no invitation lens, and the route returns
an empty list rather than a 403. A 403 would tell a caller that invitations
exist for someone, which is a disclosure the lens exists to avoid.

[BR1.3] [NFR14.24]

## Q8. What propagates the correlation id through signup?

[Answer]: The existing mechanism, unchanged. Every error log carries the
request or correlation id, and the audit row ties a row to a request without
carrying its contents. D1 adds events to that log; it adds no new propagation
path.

[NFR24.2] [code: `app/audit/log.py`]

## Q9. Which alerts does this unit add?

[Answer]: **None.** NFR25.1 through NFR25.4 are all existing alerts, and
NFR25.2 is explicitly a non-alert: narrow ceilings must not page, because they
fire constantly once the product has users and would train the operator to
ignore the global ceiling sitting in the same channel.

D1 doubles the number of narrow ceilings, which doubles the temptation. The
design records the non-alert as a decision so it is not quietly reversed.

[NFR25.1] [NFR25.2] [code: `ceilings.py:fire_ceiling_alert`]

## Q10. Does anything here need a new logical component?

[Answer]: No. Signup, the lookup and the acceptance actions all sit inside the
identity-and-access component, which already owns `Account`, `Profile`,
`Owner` and the lens hierarchy. The decision columns sit on `Enrollment`,
owned by batches-and-enrollment, and D1 writes them through that component's
own service rather than reaching past it.

[components.md] [NFR6.20]

## Assumptions & Open Questions

- **Assumed**: the signup ceiling's IP prefix derivation is shared with the
  OTP cascade rather than reimplemented. Two derivations would make the two
  cascades disagree about what one caller is.
- **Assumed**: no distributed tracing in V1. Phase 1 is a single host with two
  workers and a USD 50/month ceiling; a correlation id through structured logs
  is the tracing this scale supports, and NFR24.2 already requires it.
- **Open, and not D1's**: the scheduled job enforcing the declared 48-hour
  retention on `rate_limit_counter` [NFR6.22]. The disposition exists; the job
  does not, and D1 enlarges the table rather than creating the gap.
