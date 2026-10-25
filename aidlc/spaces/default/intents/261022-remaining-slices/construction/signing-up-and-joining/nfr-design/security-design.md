# Security Design — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **Almost nothing here is a new mechanism.** D1's security design is a set of
> attachment decisions: which built control each new route extends, and which
> controls must *not* be extended. The one genuinely new thing is a fourth
> lens type, and it exists so that a pending read is not a special case inside
> the resolver.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-requirements/security-requirements.md`
  — NFR12.x, NFR14.x, NFR10.x, NFR11.1, NFR13.4, NFR23.x
- [upstream] `construction/signing-up-and-joining/functional-design/rules.md`
  — BR1.x, BR2.x, BR3.x
- [upstream] `inception/domain-design/components.md` — the lens hierarchy
- [code] `app/auth/ceilings.py`, `app/audit/log.py`, `app/contract/privacy.py`,
  `app/gateway/outbox.py`, `app/errors/`, read 2026-10-23

---

## 1. Authorization architecture

### The lens as a data dependency

The built model makes authorization a **value the handler needs** rather than
a check it can forget: a lens is a dependency returning the scoping value, so
a handler cannot compile a scoped query without one. D1 adds a fourth type to
that hierarchy rather than a branch inside the resolver.

```
Lens (base)                     carries account_id
├── TeacherLens                 carries owner_id
├── StudentLens                 account's own seats
├── GuardianLens                carries child_enrollment_id | None
└── InvitationLens  ← D1        carries enrollment_id
```

**Why a type rather than a conditional** [NFR14.24]:

| Property | A fourth type gives it | A resolver branch would not |
|---|---|---|
| The route-enumeration gate sees it | Matches on the return annotation being a `Lens` subtype | A branch is invisible to the gate |
| A handler cannot skip the scoping value | The `enrollment_id` lives inside the lens object | A branch leaves the handler free to query |
| Grant is on stored state | Reads the decision column | A conditional above the query can be bypassed by the next query |

### Two grants, two statements, deliberately

| Grant | Query | Shape | Why |
|---|---|---|---|
| Role lenses | `_LENS_QUERY`, per request | **One statement**, three scalars | Hot path [NFR20.1] |
| Invitation | Its own statement, invitation route only | A **set** of enrollments | A person may hold several pending seats; a fourth scalar returns only the first [NFR20.3] |

Both gain the `decision = 'accepted'` predicate — the role grants require it,
the invitation grant requires its negation (`pending` or `declined`). Changing
one without the other is a silent half-fix, which is why `_SUMMARY_QUERY` is
named separately [NFR12.1 of the prior record is unrelated; see NFR20.1].

### Defence in depth for the privacy boundary

Three independent layers, all built, one needing an entry:

| Layer | Mechanism | D1's change |
|---|---|---|
| Table | Personal data on `Profile`, written only by its owner | `address` added here, not to `Account` |
| Row | PostgreSQL row-level security keyed on the session account | None — inherited |
| Schema | Teacher-lens response schemas carry no `Profile` field, checked by iterating the generated OpenAPI document | **`address` must join the matched field-name set** [BR3.4] |

**The third layer is the one that does not extend itself.**
`OWNER_PRIVATE_FIELDS` is a hand-maintained frozenset matched by field name.
The invariant iterates every schema, so it is immune to someone forgetting a
per-endpoint test — but it is not immune to someone forgetting to add a field
name. That is the design's single manual step and it carries a test.

---

## 2. Abuse-control design

### Extending the cascade, not duplicating it

Signup needs its own counters [NFR12.3]. The built module is already
scope-parameterised over a datastore-backed counter table, so the design is
**new scope members plus a second cascade builder**:

```
ScopeKind (declaration order IS evaluation order)
  NUMBER_HOURLY     ─┐
  NUMBER_DAILY       │ OTP cascade
  IP_HOURLY          │
  GLOBAL_DAILY      ─┘
  SIGNUP_NUMBER_*   ─┐ signup cascade, narrowest first
  SIGNUP_IP_*       ─┘
```

Three properties carried forward, each because the built module says why:

1. **Narrowest first.** An earlier design checked global first, and its own
   prose argued against its logic: global-first lets one attacker exhaust
   every legitimate user's daily allowance before their own limit trips. The
   module records that global-first *still looks like* defence in depth —
   which is exactly why a second cascade is where it would return [NFR12.4].
2. **A refusal consumes nothing**, including the refusing scope's own
   increment, which the module releases explicitly.
3. **Counters in the datastore.** Two Uvicorn workers on one host make a
   per-process counter a control that passes every naive test and limits
   nothing [NFR12.5].

### Two endpoints with opposite disclosure properties

This is the design's sharpest tension and the controls stay separate
[NFR14.22, NFR14.23]:

| Endpoint | Discloses whether a number is known? | Control |
|---|---|---|
| `POST /v1/auth/otp` | **Never** — byte-identical responses | Unchanged; the existing adversarial test re-runs |
| The already-added lookup | **Yes, by design** — that is its purpose | Bounded in *width* (no teacher, no batch) and in *rate* |

Conflating them is how one inherits the other's assumptions. Signup's ceilings
are therefore separate counters rather than extra conditions on the OTP ones.

---

## 3. What D1 must not widen

### The staging outbox

`app/gateway/outbox.py` is a staging-and-development-only route that **hands
an OTP to anyone who calls it**. Production impossibility is enforced three
independent ways: the enabling check reads the environment fresh on every call
and permits only `staging`, `development` and `test`; the route is not
registered at all when disabled; and the startup check refuses to boot a
production process with it forced on.

**D1 adds a route that causes an OTP to be sent**, so it increases what that
outbox would expose if it ever ran in production. The design's decision is to
add **nothing** to it — no signup-specific readback, no convenience for
testing the new path — and to let the three existing controls stand unchanged.

Recorded rather than assumed, because "it is obviously fine" is the exact
assumption the module's own docstring names as the most expensive one
available here.

### The audit vocabulary

`AuthEvent` is a closed enum because an open vocabulary is how a free-form
value re-enters a log specified not to have one. D1 adds **named members**,
not a `detail` column [NFR12.7, NFR12.10]. Account creation belongs in that log
on its merits: rate-limited, unauthenticated, and where an enumeration attempt
would surface.

---

## 4. Error and disclosure design

Retryability is a property of the error **class**, read off the type in
exactly one place [NFR19.6]:

| Signup failure | Class | Status | Retryable | Why |
|---|---|---|---|---|
| Duplicate number | `ConflictError` | 409 | No | The uniqueness constraint reporting itself [BR4.4] |
| Ceiling breached | `ConflictError` | 409 | No | A budget, not a blip [NFR12.6] |
| Bad input | `ValidationError` | 400 | No | |
| Database unavailable | `TransientError` | 503 | **Yes** | The one retryable case |

Every response carries `message_key` rather than `message`, because a
server-sent English string cannot be localized in a Bangla-first UI, and no
traceback reaches a client [NFR24.4] — which matters more here than elsewhere
because signup is unauthenticated.

### Signup issues no session

**`POST /v1/accounts` returns no access token and no refresh token**
[NFR13.4]. It creates rows and triggers the existing OTP path; the person then
authenticates through that path exactly as a returning user does.

This keeps **one route to a session**, which is the property that makes the
token design reviewable: refresh-token rotation with reuse detection and
family invalidation is built once, on one entry point, and signup does not add
a second. A signup that returned a session would also be a signup that
authenticated a phone number nobody had yet proven they control — the OTP
step is what proves it, and it comes after.

**An empty invitation list is not a 403** [NFR14.24]. A person with no pending
seats resolves no invitation lens, and the route returns an empty list. A 403
would disclose that invitations exist for *someone*.

---

## 5. Compliance controls

| Control | Design | Owner |
|---|---|---|
| Children's data encrypted at rest | The two new columns sit on an already-covered table | D1 [NFR10.13] |
| No device or advertising identifier | No new SDK; the manifest allowlist and release DEX scan already fail the build | D1 [NFR11.1] |
| Data Safety form declares the new collection | Address and self-authored name are newly collected | **D6** |
| Privacy policy discloses a declined seat's retained name | Generated from the governance basis text | **D6** |
| Both account-deletion paths | `PUBLIC_ROUTES` already allowlists both; no handler exists | **D6** |

**D1 creates two release-blocking obligations it does not discharge**, and
naming them here is the point: the form and the policy are D6 deliverables,
and this is the unit that changes what they must say.

---

## 6. Verification design

| Obligation | Mechanism | Fails today? |
|---|---|---|
| No role lens from unaccepted links | Adversarial test over the two granting queries | **Yes** [NFR23.2] |
| OTP byte-identical | Existing adversarial test, re-run | No |
| Teacher-lens schemas carry no `Profile` field | Schema-wide invariant over the generated OpenAPI document | No, until `address` is enrolled |
| Acceptance transitions | Test-first, per the affirmed predicate | **Yes** [NFR23.1] |
| Authorization branch coverage | Branch, not line [NFR23.3] | — |

**The adversarial test failing today is the design's load-bearing property.**
A test written after the predicate lands passes immediately and proves nothing
about the defect it names.

---

## Assumptions & Open Questions

- **Assumed**: signup's ceiling scopes share the OTP cascade's IP-prefix
  derivation. Two derivations would make the cascades disagree about what one
  caller is.
- **Assumed**: the signup ceiling check runs **before** the transaction, so a
  refusal writes no account and the counter's increment is not part of rolled
  back work [NFR12.4].
- **Open, and D5's**: the ZAP baseline pass against staging, driven from the
  committed OpenAPI schema. D1 adds routes it will cover.
