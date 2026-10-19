# Functional Design Questions — identity-and-access (U3)

**Stage**: functional-design (3.1)
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **THE WALKING SKELETON**
**Phase**: Construction
**Depth**: Comprehensive

> This is the first Unit that **runs**. U1 was arithmetic with no process; U2
> was a contract with no routes. U3 is a Compose screen calling a real FastAPI
> endpoint, reading a real PostgreSQL row, through a real OTP — not a mock at
> any layer, which is what `team.md` means by a walking skeleton.
>
> It is also where the two structurally unusual decisions in this system
> become real: **the lens is computed per request and never stored**, and
> **the privacy boundary is enforced by the database rather than by a
> query filter**. Both are easy to implement in a way that passes every
> happy-path test and is silently wrong.

---

## Q1 — What exactly makes a cached lens indistinguishable from a computed one, and what test tells them apart?

AC1.9.1 forbids a stored or cached role; `project.md` makes it one of the
most-mandated rules in the project. But a cache is invisible on every happy
path.

[Answer]: **Only a mid-session ownership change tells them apart**, which is
exactly what AC1.9.2 and AC1.9.3 describe, and they are therefore the two
tests that carry the whole rule:

- An account owning no batches creates one. Its **next request** must offer a
  teacher lens, with no re-authentication and no new token.
- An account whose last enrollment is removed. Its **next request** must no
  longer offer the student lens.

A cache keyed on the account — the obvious implementation — passes every other
test in this Unit and fails exactly these two. So they are named tests, not
incidental coverage.

**Request-scoped memoization is permitted and cross-request caching is not**
[AC1.9.4], and the distinction needs a mechanism rather than a convention. The
memo lives on the **request object** (FastAPI's `request.state`), so it is
garbage-collected with the request and there is no module-level dict, no
`functools.lru_cache`, and no Redis key that could outlive it. A test asserts
that two requests from the same account each hit the database.

> Why this matters more here than it looks: lens resolution runs on **every**
> request, which makes it the hottest query in the system on a single 2 GB
> instance. The pressure to cache it will be real and will arrive with a
> plausible performance argument. The rule is mechanical so it survives that
> conversation.

---

## Q2 — The seven OTP abuse controls: which are application logic and which are database constraints?

`team.md` puts all seven inside the skeleton Bolt, each with an adversarial
test, because per-SMS billing makes abuse a direct attack on the project's
wallet.

[Answer]: **Six are application logic over datastore-backed counters; one is a
property of the storage.**

| Control | Mechanism | The failure it prevents |
|---|---|---|
| 3/hour, 5/day per number | Counter rows, checked before send | Budget drain on one number |
| 10/hour per IP | Counter rows keyed by IP prefix | Budget drain across numbers |
| 5-minute expiry | `expires_at` compared server-side | A code with no deadline |
| Single use | `consumed_at` set in the same transaction as the check | A code that verifies twice |
| 5 verify attempts | `attempt_count` incremented, then compared | Brute force over 10⁶ codes |
| Global daily ceiling | Counter row, checked before send | Total budget exhaustion |
| **Hashed storage** | **Column holds a hash, never the code** | A leaked database row yielding live codes |

**The counters are datastore-backed, and this is a correctness requirement
rather than hardening** [AC1.8.3]. A per-process dictionary is the obvious
implementation, passes every test, and silently stops working the moment
there are two workers — which Phase 1 has, because a single Lightsail host
runs multiple Uvicorn workers. So the test must **fail against a per-process
dictionary**: it exercises the limit through two independent sessions, which
a shared-nothing counter cannot survive.

**Three of the seven need a test that is adversarial rather than
confirmatory**, because the confirmatory version passes against the broken
implementation:

- *Single use*: verifying once then again must fail. Checking only that a
  correct code verifies proves nothing about the second attempt.
- *Attempt ceiling*: the 6th attempt must fail **and the code must be dead
  afterwards**, so a correct 7th attempt also fails. An implementation that
  counts but does not invalidate passes the first half.
- *Hashed storage*: the test reads the stored column and asserts it does
  **not** equal the transmitted code. Asserting that a correct code verifies
  is satisfied by storing it in plaintext.

---

## Q3 — AC1.8.7 requires byte-identical responses for a known and an unknown number. How is that achieved without a timing oracle?

This is the same structural property as BR1.4 from U2, now with real code
behind it — and NFR14.4 was explicitly deferred to this Unit by BR4.4.

[Answer]: **Three things must match, and the third is the one implementations
get wrong.**

1. **The response body and status are identical.** One code, one
   `message_key`, no field that varies with existence.
2. **Both paths send no SMS on the unknown branch** — but consume budget
   identically, so a prober cannot distinguish by watching the ceiling.
3. **Both paths perform the same hashing work.** The unknown-number path
   must not return early: it computes the OTP hash it would have stored and
   discards it.

The third is NFR14.4 and it is **asserted structurally, never as a wall-clock
bound** — a millisecond assertion is flaky and gets deleted the third time CI
fails on it. The test asserts the hash function was called on both paths,
which is stable and inspectable.

> **An honest limitation.** Structural equivalence proves the expensive
> operation ran on both paths; it does not prove the paths are
> indistinguishable to a patient attacker with a million samples. Closing
> that would need constant-time comparison and a fixed response deadline,
> which is disproportionate here. Recorded so nobody later reads the test as
> a stronger guarantee than it is.

---

## Q4 — How is the owner-private profile enforced, and what makes the test non-vacuous?

AC1.5.2 and `project.md` require that nothing a student or guardian writes
reaches any teacher. `team.md` requires three layers: separate tables by
writer, row-level security, and teacher-facing schemas without profile
fields.

[Answer]: **U2 already ships the third layer.** This Unit adds the first two:

- **Separate tables by writer.** `Profile` (self-entered name, photo) is
  written only by its owner. The teacher-typed display name lives on
  `Enrollment`, written only by the teacher. They are different rows in
  different tables with different writers — so "which name does a teacher
  see" is answered by **which table the query reads**, not by a filter
  someone remembers to apply.
- **Row-level security on `Profile`**, with a policy keyed on the session's
  account id.

**The test is non-vacuous only if it connects as a restricted non-superuser
role**, and this is a `project.md` NEVER rule for a specific reason:
PostgreSQL documents that superusers and table owners **bypass RLS
entirely**, and the default testcontainers connection is `postgres`, a
superuser. A privacy suite run as superuser passes identically whether the
policy is correct, broken, or absent — so the strongest obligation in the
project would certify nothing.

So: a **meta-test runs first** and asserts `current_user` is not a superuser,
`row_security` is on, and a policy exists on `Profile`. The privacy suite
does not run until that passes.

---

## Q5 — Refresh-token rotation: what is the security-critical failure mode, and why does it need a state machine test?

[Answer]: **Reuse detection degrades silently into non-rotating tokens,
because the happy path is identical.**

A client refreshes, gets a new token, uses it. That works whether or not the
old token was invalidated. The difference appears only when an **old token is
presented again** — which happens when a token has been stolen, which is the
case the mechanism exists for.

So the test is a state machine over five transitions:

1. A valid refresh returns a new token pair and invalidates the old.
2. The **rotated-out** token, presented again, is refused.
3. That refusal **invalidates the whole family** — the newly issued token
   stops working too, because reuse means the chain is compromised and the
   legitimate holder cannot be distinguished from the thief.
4. Refresh tokens are stored **hashed**, asserted by reading the column.
5. A 15-minute-expired access token is refused.

Transition 3 is the one most likely to be missed. Invalidating only the
presented token leaves the thief's token working, which inverts the control.

---

## Q6 — What does the `Owner`/`Enrollment` shell mean concretely, and what stops it becoming an ownership transfer?

The Unit definition says U3's migration creates these two tables empty, reads
them, and never writes them.

[Answer]: **Table shape only, and the boundary is enforced by a test rather
than a comment.**

Lens resolution reads all three tables — identity, `Owner`, `Enrollment` —
because the lens *is* "what does this account own and where is it enrolled".
Empty is not the same as absent: a query against a table that does not exist
fails, so the skeleton could not run end to end without them. That was a
recorded learning from Units Generation.

What stops drift: U3's code contains **no INSERT, UPDATE or DELETE against
either table**, asserted by a test that greps the Unit's own SQL and ORM
usage. U4 owns their behaviour and extends their columns. A migration adding
a column to `Enrollment` in U3 would be the signal that the boundary moved,
and it would show up in review as a schema change in the wrong Bolt.

---

## Q7 — What is the smallest honest definition of "the skeleton works"?

`team.md` binds the skeleton checkpoint to a verification command that
demonstrates the real end-to-end result on a device, not a passing suite.

[Answer]: **One path, all the way down, with nothing stubbed:**

A phone number typed on a Compose screen → OTP issue endpoint → **real
BulkSMSBD send** → a code arriving on a real handset → verify endpoint →
access and refresh tokens → an authenticated request whose **lens is computed
from owned batches and enrollments** → a response rendered by the client with
no business logic of its own.

Three things that are deliberately *not* part of "works":

- **A passing test suite.** The suite runs with the gateway stubbed, by
  `team.md`'s rule that the blocking suite needs no secret. It proves the
  logic; it does not prove the pieces connect.
- **A screenshot.** The lens must be observably computed, which means
  demonstrating AC1.9.2 or AC1.9.3 — ownership changing mid-session.
- **Both lenses for one account.** That needs U4's enrollment flow to create
  the second one. The skeleton proves one lens resolves correctly; the
  dual-lens case is exercised by tests here and demonstrated at B5.

> **The one place real money is spent before launch.** OQ-3a settled that
> BulkSMSBD has no sandbox, so staging runs a null adapter. The gateway leg
> is therefore verified exactly once — here — against production credentials
> with a single send to the developer's own number. That is a deliberate,
> bounded exception, and it is why this checkpoint is the one that cannot be
> satisfied by a green suite.

---

## Assumptions & Open Questions

**None.** [assumption] OQ-3 and its two follow-ups are closed: the vendor is
BulkSMSBD, there is no sandbox (so non-production runs a null adapter), and
code 1012 does not apply to OTP traffic (so the body is English GSM-7 at 160
characters per segment rather than 70). All three are recorded in
`contract-summary.md` §C.4 with the behaviours binding on this Unit.

---

## Consolidated Summary Confirmation

U3 is the first Unit that runs, and the two decisions most likely to be
implemented wrongly-but-passing are made mechanical here.

**The lens is computed per request**, and only a mid-session ownership change
can tell a computed lens from a cached one — so AC1.9.2 and AC1.9.3 become
named tests carrying the whole rule. Request-scoped memoization lives on the
request object, so it is garbage-collected with the request and there is no
module-level dict or cache key that could outlive it. This matters because
lens resolution is the hottest query in the system on a 2 GB instance, so
pressure to cache it will arrive with a plausible performance argument.

**All seven OTP abuse controls ship here**, six as application logic over
**datastore-backed** counters and one as hashed storage. The counter test must
fail against a per-process dictionary, because that implementation passes
every naive test and stops working with two workers — which Phase 1 has.
Three controls need adversarial rather than confirmatory tests: single-use,
the attempt ceiling (the code must be *dead* afterwards, not merely refused),
and hashed storage (read the column and assert it differs from the
transmitted code).

**Byte-identical responses for known and unknown numbers** need three things
to match, and the third — both paths performing the same hashing work — is
NFR14.4, deferred to this Unit by BR4.4. Asserted structurally, never as a
wall-clock bound. Recorded honestly: this proves the expensive operation ran
on both paths, not that they are indistinguishable to a patient attacker.

**The privacy boundary** gets separate tables by writer plus row-level
security, with U2 already shipping the schema layer. The suite connects as a
restricted non-superuser role and a meta-test runs first, because PostgreSQL
superusers bypass RLS entirely and the default container connection is one —
so the strongest obligation in the project would otherwise certify nothing.

**Refresh-token reuse detection** is tested as a state machine, because it
degrades silently into non-rotating tokens: the happy path is identical
either way. The transition most likely missed is family invalidation —
invalidating only the presented token leaves the thief's token working.

**`Owner` and `Enrollment` are created empty** because empty is not absent
and lens resolution reads all three tables. A test asserts U3 contains no
write against either.

**"The skeleton works"** means one path with nothing stubbed: a typed number,
a real SMS, a real code, a computed lens, a rendered response. Not a passing
suite — that runs with the gateway stubbed by design. This is the one place
real money is spent before launch, since BulkSMSBD has no sandbox.

Does this all look correct before I generate the artifact?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
