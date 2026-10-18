# NFR Requirements Questions — identity-and-access (U3)

**Stage**: nfr-requirements (3.2)
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**
**Phase**: Construction
**Depth**: Comprehensive

> **The first Unit where the full NFR set binds.** U1 was a library and U2
> a spec Unit, so most inception NFRs were N/A with a structural reason.
> U3 has a process, a database, a network boundary and a screen — which
> means availability, latency, scaling, observability and cost all become
> real at once, on a 2 GB instance under a USD 50/month ceiling.
>
> The interesting answers here are the ones where the budget and the
> security requirements *conflict*, because that is where a target gets
> quietly weakened later unless it is written down now.

---

## Q1 — What is the latency budget, given lens resolution runs on every request?

[Answer]: **There is no stated millisecond target, and that is deliberate.**
Two reasons, and the second is the important one.

First, the honest one: nothing in this project has measured a request yet.
A number invented now would be a guess carrying the authority of a
requirement, and the first person to miss it would weaken it rather than
investigate — which is how a target becomes decoration.

Second, and this is the real constraint: **lens resolution hits the database
on every request by design** [TC-11], making it the hottest query in the
system. The pressure to cache it will arrive with plausible numbers, and
`project.md` forbids caching it in the most absolute terms. So the binding
requirement is **structural, not numeric**:

- **NFR6.1** — lens resolution is **one query**, not three. Teacher,
  student and guardian lenses resolve from a single statement over `Owner`
  and `Enrollment` rather than three round trips, because three round trips
  is what makes the caching argument persuasive.
- **NFR6.2** — that query is **indexed on the columns it filters**:
  `Owner.account_id` and `Enrollment.account_id`.
- **NFR6.3** — a test asserts the **query count per request**, not its
  duration. A count is stable across machines; a duration is not, and a
  flaky performance assertion gets deleted.

> This is the same reasoning as the money module's branch coverage: pick
> the obligation that is mechanically checkable rather than the one that
> sounds stricter.

---

## Q2 — What availability target, on a single instance with no failover?

[Answer]: **None stated, because any number would be dishonest.** Phase 1
is one Lightsail instance with containerized Postgres and no multi-AZ, no
load balancer and no standby. An instance restart is a total outage. An SLO
of "99.9%" would be a number nobody could defend and nobody could act on.

What **is** stated, because it is actionable:

- **NFR6.4** — a **health endpoint** reporting database connectivity and
  the applied Alembic revision. That is what makes a deploy's smoke test
  meaningful and what answers "is it up and is it the version I shipped".
- **NFR6.5** — **deploys are scheduled outside Bangladesh classroom
  hours.** Recreate-style deployment means a restart window, and a dropped
  attendance write during a live class is the failure a teacher will not
  forgive. This is a reliability requirement expressed as a scheduling
  constraint, which is the only form available at this budget.
- **NFR6.6** — **a verified `pg_dump` to S3 before any production
  migration**, with object existence and non-trivial size asserted after
  upload. An untested backup is not a backup, and an unverified upload is
  not one either.

> The honest summary: this Unit cannot be highly available at this budget,
> so the requirements are about **recovering quickly and knowing the
> state**, not about not failing.

---

## Q3 — The SMS budget is a hard cost ceiling. What makes it a requirement rather than a hope?

[Answer]: **Three numeric requirements and one alert**, because this is the
one place where an attacker directly spends the project's money.

- **NFR7.1** — a **global daily SMS ceiling**, configured, checked before
  every send, and enforced by a datastore counter.
- **NFR7.2** — **per-number and per-IP-prefix sub-ceilings beneath it**, so
  the breaker degrades rather than cliff-edges. A global-only ceiling
  converts a financial attack into a total lockout of every legitimate
  teacher for the rest of the day.
- **NFR7.3** — **every outcome consumes budget**, including `UNKNOWN` and
  `BUDGET_REFUSED`. An `UNKNOWN` may have cost money; counting only `SENT`
  lets a flapping gateway spend without bound.
- **NFR7.4** — **the ceiling breach alerts**, and the alert is verified in
  staging before the auth slice reaches production.

**The one thing I will flag rather than decide**: the actual ceiling
*number* depends on BulkSMSBD's per-SMS rate against the USD 50/month
total, and the rate is commercial information the project has but this
stage does not. The requirement is that a number exists, is configured
rather than hardcoded, and is derived from the budget — not that it is any
particular value.

---

## Q4 — What observability is affordable, and what does it have to answer?

[Answer]: **Two questions must be answerable, and they drive everything
else.** With no admin surface and a solo operator, observability is not
about dashboards — it is about whether a specific question can be answered
when it is asked.

1. *"Was this child's data accessed improperly?"* — which both COPPA and
   GDPR-K assume can be answered, and which a parent complaint will ask.
2. *"Is something burning the SMS budget right now?"*

So:

- **NFR8.1** — an **append-only auth audit log** holding OTP issued,
  verify failed, verify succeeded, refresh rotated, refresh reuse detected,
  plus every interactive production database session.
- **NFR8.2** — **the audit log holds no OTP, no token, no phone number and
  no child name.** An audit log that leaks what it audits is a common and
  self-defeating mistake. The correlation id ties a row to a request
  without carrying its contents.
- **NFR8.3** — **not per-row access logging.** Disproportionate here and
  unaffordable in storage. The auth log plus the production-session log is
  the honest middle.
- **NFR8.4** — **`getBalanceApi` is polled and alerts**, since it is the
  only observability hook the gateway offers and it catches both "about to
  run out" and, indirectly, "something is burning SMS".

---

## Q5 — What does this Unit add to the security requirements U1 and U2 already carry?

[Answer]: **The first real attack surface.** U1 had no I/O and U2 no
routes; U3 has three public endpoints, a phone number, and a gateway that
costs money per call.

Beyond the seven abuse controls already specified as business rules:

- **NFR9.1** — **no secret in the repository or the image.** Three named
  secrets here: gateway credentials, the JWT signing key, the database URL.
  Environment variables in Phase 1, SSM `SecureString` in Phase 2.
- **NFR9.2** — **`error_message` from the gateway is never logged**,
  because it **echoes the API key back in plaintext** — verified against
  the live endpoint. Only `response_code` is logged.
- **NFR9.3** — **the scheme is enforced in code**, not configuration. Plain
  HTTP serves the same BulkSMSBD API with no redirect and no HSTS, so a
  misconfigured `http://` ships the phone number and the OTP in cleartext
  and **succeeds silently**.
- **NFR9.4** — **Ruff's `S` ruleset is the SAST gate** and runs on this
  Unit's code: hardcoded passwords, `assert` in production paths, weak
  hashing, unsafe deserialization.
- **NFR9.5** — **the OTP is stored as an HMAC under a server-held key**,
  not as a bare digest and not as a password hash. Measured rather than
  assumed, on this machine:

  | Scheme | Cost per issue | Offline exhaustion of the 10⁶ space |
  |---|---|---|
  | SHA-256 | ~0.1 µs | **0.07 seconds** |
  | bcrypt cost 8 | 15 ms | 4 hours |
  | bcrypt cost 10 | 58 ms | 16 hours |
  | **HMAC-SHA256** | **~1 µs** | **impossible without the key** |

  A 6-digit code has only 10⁶ possibilities, so a leaked table under a bare
  digest is exhausted in **under a tenth of a second** — the attempt
  ceiling protects the *online* path and does nothing for the *offline*
  one. But a password hash is the wrong tool here: it buys hours of delay
  at 15–60 ms of CPU **per OTP issue**, on a 2 GB instance, against an
  attacker who already has the database.

  **HMAC with a key held outside the database defeats the offline attack
  outright** rather than slowing it, at a thousandth of bcrypt's cost. The
  key is one of the three named secrets, so a database leak alone yields
  nothing.

> I had written "use a real password hash" and the measurement changed the
> answer. The instinct was right about the threat and wrong about the
> remedy: bcrypt is designed for secrets an attacker must guess from a
> large space, and a 6-digit OTP is not one. Recorded because the wrong
> version reads as more security-conscious, which is how it would survive
> review.

---

## Q6 — What are the scaling and capacity requirements at 100 teachers?

[Answer]: **The scale ceiling is not the constraint; the worker count is.**
100 teachers and a few thousand students is small. What matters at this
size is a specific correctness property that *looks* like a scaling
concern:

- **NFR10.1** — **rate-limit counters are datastore-backed, not
  per-process.** A single Lightsail host runs several Uvicorn workers, so a
  per-process dictionary silently stops enforcing the moment there is more
  than one. This is a correctness requirement wearing a scaling costume,
  and it is already BR2.1.
- **NFR10.2** — **the counter upsert is atomic**, so two workers racing on
  the same window cannot both read a stale count and both pass a check at
  the limit boundary.
- **NFR10.3** — **one transaction per request**, committed by the endpoint
  and never by a repository method. Otherwise a partial write becomes
  possible on the auth path.
- **NFR10.4** — **a database connection failure fails fast inside a
  request**, with no retry. A 2 GB instance under connection pressure gets
  worse, not better, if every request retries.

---

## Assumptions & Open Questions

**One, and it is a number rather than a decision.** [assumption] The global
daily SMS ceiling's *value* derives from BulkSMSBD's per-SMS rate against
the USD 50/month budget. The requirement here is that the ceiling exists,
is configured rather than hardcoded, and is derived from the budget. The
value is set at deployment and does not block this Unit's design or its
tests, which exercise the mechanism at a test-configured threshold.

---

## Consolidated Summary Confirmation

U3 is the first Unit where the full NFR set binds, and the interesting
answers are where the USD 50/month budget and the security requirements
conflict.

**No latency target and no availability target, deliberately.** Nothing has
measured a request yet, so a number now would be a guess carrying a
requirement's authority — and the first person to miss it would weaken it
rather than investigate. Instead the latency requirement is **structural**:
lens resolution is ONE query, indexed, with a test asserting the **query
count** rather than a duration, because a count is stable across machines
and a flaky duration assertion gets deleted. Three round trips is what
makes the caching argument persuasive, and `project.md` forbids caching in
the most absolute terms.

Availability is the same honesty: one instance, containerized Postgres, no
failover. An SLO would be undefendable. What is stated instead is
actionable — a health endpoint reporting connectivity and applied
migration revision, deploys scheduled outside Bangladesh classroom hours,
and a **verified** `pg_dump` before any production migration, since an
unverified upload is not a backup.

**The SMS budget gets four requirements** because it is the one place an
attacker spends the project's money directly: a global ceiling, sub-ceilings
beneath it so the breaker degrades rather than cliff-edges, budget consumed
on **every** outcome including UNKNOWN, and an alert verified in staging.
The ceiling's *value* is flagged rather than decided — it derives from a
commercial rate this stage does not hold.

**Observability answers two questions**, not a dashboard: whether a child's
data was accessed improperly, which COPPA and GDPR-K assume is answerable,
and whether something is burning SMS right now. An append-only auth audit
log carrying **no OTP, no token, no phone number and no child name** — an
audit log that leaks what it audits is self-defeating. Not per-row access
logging: disproportionate and unaffordable.

**Five security requirements beyond the seven abuse controls.** Two come
from facts verified against the live gateway: `error_message` echoes the
API key in plaintext so only `response_code` is logged, and plain HTTP
serves the same API with no redirect and no HSTS so the scheme is enforced
in code. **NFR9.5 changed when I measured it.** I had written "use a real
password hash". A leaked SHA-256 OTP table is exhausted in **0.07
seconds**, so the threat is real and the attempt ceiling does nothing about
it — that protects the online path only. But bcrypt is the wrong remedy: it
buys hours of delay at 15–60 ms of CPU **per OTP issue** on a 2 GB
instance. **HMAC under a server-held key defeats the offline attack
outright** rather than slowing it, at ~1 µs, because the key lives outside
the database. Recorded as a correction because the wrong version reads as
more security-conscious, which is how it would have survived review.

**Scaling is not the constraint; the worker count is.** The datastore-backed
counter requirement is a correctness requirement wearing a scaling costume:
a per-process dictionary silently stops enforcing the moment there is more
than one worker, which Phase 1 has.

Does this all look correct before I generate the artifact?

[Answer]:

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]:
