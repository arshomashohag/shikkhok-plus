# NFR Requirements — Questions

**Stage**: nfr-requirements (3.2)
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

## How this stage was answered

D1 adds no new runtime surface class: it adds endpoints to a built FastAPI
application, two columns to a built schema, and a fourth type to a built lens
hierarchy. The product's NFRs are written and traced in the prior record
(NFR1–NFR17), this record adds NFR20–NFR23, and the hosting, budget and device
floor are decided. Asking the human to re-answer any of that would be asking
them to repeat themselves.

What remained were the places where D1's *specific* change meets a built
mechanism, and where the mechanism's shape constrains the answer. Each is
answered below from an upstream source or from a direct read of the code, and
the source is named. Where nothing settles it, the answer says so and records
the assumption.

---

## Q1. Do signup's ceilings reuse the built ceiling mechanism or stand beside it?

[Answer]: Reuse the mechanism, extend the scope set. `app/auth/ceilings.py`
already implements a scope-parameterised cascade over a datastore-backed
counter table, with the narrowest-first order as its stated control. BR2.1
requires signup's ceilings to be **separate counters**, not separate
machinery.

Two properties of the built module constrain how: `ScopeKind`'s **declaration
order is the evaluation order** by explicit design, and `_scopes()` is a
hardcoded static list. So signup's scopes are new enum members and a second
cascade builder, and the narrowest-first invariant has to hold in the new
cascade for the same reason it holds in the OTP one.

[code: `app/auth/ceilings.py`] [BR2.1]

## Q2. Does signup consume the global daily SMS ceiling?

[Answer]: Yes, through the OTP path it triggers, and that is correct. Signup
does not send an SMS itself — step 9 of W1 triggers the existing OTP path,
which carries its own cascade including the global ceiling. Signup's own
ceilings bound how many *accounts* one number or IP can attempt, which is a
different quantity from how many *messages* the system sends.

NFR12.1 made the SMS budget per-purpose with `otp` as V1's only purpose.
Signup does not add a purpose: the message it causes is an OTP.

[NFR12] [NFR12.1] [FR1.7d]

## Q3. What latency budget does the new lens predicate carry?

[Answer]: No measurable addition, and the requirement is stated as a
**property rather than a number**. NFR20 already fixes the property: lens
resolution cost tracks the data belonging to the requesting account, never
the total data in the system, measured at 0.20 ms at 500× the target scale.

D1's two predicates are on columns of rows `_LENS_QUERY` already reads, so
neither adds a join nor a round trip. The requirement that matters is that
the single-statement shape survives [NFR6.1] — the hot-path query stays one
statement, and the invitation grant pays for its own query on its own route
[ADR-011].

[NFR20] [NFR21] [NFR22] [ADR-011]

## Q4. Is the invitation route on the hot path?

[Answer]: No. It is read on one screen, by a person who has just signed in and
has no other lens to reach. Its query may be a second statement precisely
because it is not per-request; that is the ADR-011 trade and it is what keeps
the per-request path at one statement.

[ADR-011] [NFR6.1]

## Q5. Does the audit log gain signup events?

[Answer]: Yes, and the vocabulary is closed by design, so this is an
**extension with a reason rather than an addition**. `AuthEvent` is a closed
enum whose docstring states that an open vocabulary is how a free-form value
re-enters a log specified not to have one.

Account creation is an authentication-surface event with the same abuse
profile as OTP issue — it is rate-limited, it is reachable unauthenticated,
and it is where an enumeration attempt would show up. It belongs in the same
log, as a named member, under the same no-free-form-field rule.

[code: `app/audit/log.py`] [NFR12]

## Q6. What must never appear in a signup log line?

[Answer]: The same set the built log already forbids, plus the new personal
fields. No phone number, no OTP, no token — and now no `address` and no
`self_name`. The structural guarantee is the one already built: the audit row
dataclass carries no free-form string field but `correlation_id`, asserted by
a test.

[team: Deployment] [BR3.2]

## Q7. Does the address change the data-at-rest requirement?

[Answer]: No, it inherits it. RC-8 and NFR10 require children's data encrypted
at rest, which disqualified any tier without storage encryption and is already
satisfied by the chosen hosting. The address is more sensitive than what is
already there, and it is on a table that is already covered.

What the address *does* change is the privacy-gate membership, which is a
functional rule [BR3.4] and not an NFR.

[NFR10] [RC-8] [BR3.4]

## Q8. Does D1 change the availability or scale targets?

[Answer]: No. NFR6 fixes the ceiling at 100 teachers and a few thousand
students, and D1 is the unit that lets those accounts exist rather than one
that changes how many there can be.

The one growth fact worth recording: before D1, accounts were created by hand,
so the account table's growth rate was zero. After D1 it is driven by signup
and bounded by signup's own ceilings — which makes those ceilings a capacity
control as well as an abuse control.

[NFR6] [NFR7] [FR1.7d]

## Q9. Is the tech stack a decision in this unit?

[Answer]: No. Every technology D1 uses is built, configured and in CI:
FastAPI, SQLAlchemy, Alembic, PostgreSQL 16, PyJWT, Compose. `tech-stack-decisions.md`
records what D1 uses and the one choice genuinely open inside it — the enum
representation — rather than re-deciding a settled stack.

[codekb: `technology-stack.md`] [components.md]

## Assumptions & Open Questions

- **Assumed**: signup's per-number and per-IP ceiling *values* are Code
  Generation's to set from the existing configuration, in the same shape as
  the OTP ones. The requirement fixes that they are separate counters, that
  the narrowest-first order holds, and that they live in the datastore rather
  than in process memory — not the integers.
- **Assumed**: the IP scope uses the same prefix derivation the OTP cascade
  uses, since using a different one would make the two cascades disagree about
  what one caller is.
- **Open, and D5/D6's**: the ZAP baseline pass and the backend SBOM. The
  delivery plan assigns them to D5 and D6; D1 adds routes they will cover and
  installs neither.
