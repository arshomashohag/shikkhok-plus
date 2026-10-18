# Entity Model — `identity-and-access` (U3)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

> **The first Unit with tables.** Seven entities it owns, plus two it
> creates empty and never writes. Three carry a security property in their
> *shape* rather than in the code that uses them, and those are called out:
> a hash column instead of a value column, a family id instead of a lone
> token, a counter row instead of a process variable.

## Sources

- [stage] `functional-design-questions.md` — Q1 (the lens is computed),
  Q2 (the seven controls), Q3 (byte-identical responses), Q4 (the privacy
  boundary), Q5 (reuse detection), Q6 (the empty shells)
- [upstream] `inception/domain-design/components.md` — the Identity and
  Ownership component entities
- [upstream] `inception/user-stories/stories.md` — US1.1, US1.2, US1.5,
  US1.8, US1.9
- [upstream] `inception/contract-design/contract-summary.md` — §B.3 the auth
  endpoints, §B.4 the lens contract, §C the SMS gateway
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12,
  NFR13, NFR14
- [team] `## Walking Skeleton`, `## Testing Posture`, `## Deployment`
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
entities:

  # ---- Owned by this Unit ----

  - name: Account
    identifier: id
    attributes: [id, phone, created_at, activated_at, deleted_at]
    description: >
      An identity keyed on a permanent phone number. Created dormant when a
      teacher records a number, activated on first successful sign-in.
    constraints:
      - phone is UNIQUE and is the permanent key. A number is never reused for a different person.
      - activated_at distinguishes a dormant record from a signed-in one. AC1.2.1 turns on this column - a teacher recorded the number, and the person claims it later without being invited.
      - "NO ROLE COLUMN, EVER. There is deliberately no `role`, `is_teacher` or `kind` attribute: the lens is computed per request from owned batches and enrollments [AC1.9.1]. A column here would be the exact stale-role defect the rule exists to prevent, and it would look entirely reasonable to whoever added it."
      - phone is children's-adjacent personal data [RC-1, RC-2, RC-3], so it never appears in a log line, an error payload or an audit row.

  - name: Profile
    identifier: account_id
    attributes: [account_id, self_name, photo_ref]
    description: >
      What a person writes about themselves. Visible only to its owner.
    constraints:
      - ROW-LEVEL SECURITY, with a policy keyed on the session's account id. One of the three layers of the privacy boundary; U2 shipped the schema layer, this Unit adds this one and the table split.
      - Written ONLY by its owner. The teacher-typed display name lives on Enrollment, written only by the teacher, so 'which name does a teacher see' is answered by WHICH TABLE THE QUERY READS rather than by a filter someone remembers to apply [AC1.5.2].
      - The privacy suite connects as a RESTRICTED NON-SUPERUSER ROLE, with a meta-test asserting that before it runs. Superusers and table owners bypass RLS entirely, and the default container connection is `postgres` — so the suite would pass identically against a correct policy, a broken one, or none at all.

  - name: OtpRequest
    identifier: id
    attributes: [id, phone, otp_hash, purpose, issued_at, expires_at, consumed_at]
    description: >
      One issued code. Carries four of the seven abuse controls in its own
      columns.
    constraints:
      - otp_hash, NOT otp. The column holds a hash and never the transmitted value [AC1.8.6]. The test reads this column and asserts it differs from what was sent — asserting that a correct code verifies is satisfied by storing it in plaintext.
      - expires_at is compared SERVER-SIDE. A client-supplied timestamp would make the 5-minute window advisory [AC1.1.3].
      - consumed_at is set in the SAME TRANSACTION as the check that reads it, so a concurrent second verify cannot slip between them [AC1.1.4].
      - purpose is required and has exactly one V1 value (`otp`). A default would let a second consumer arrive without anyone choosing its ceiling, which is the one control protecting the project's wallet.
      - The code never appears in any log line at any level, and the gateway request body is never logged, because that call carries the phone number and the code together.

  - name: VerifyAttempt
    identifier: id
    attributes: [id, otp_request_id, attempted_at, succeeded]
    description: >
      One attempt against one code. Separate from OtpRequest so the attempt
      ceiling is countable and auditable.
    constraints:
      - The 6th attempt is refused AND THE CODE IS DEAD AFTERWARDS, so a correct 7th also fails [AC1.1.4]. An implementation that counts but does not invalidate passes a confirmatory test and leaves brute force open.
      - A row per attempt rather than a counter on OtpRequest, so the audit log can answer "was this code attacked" rather than only "how many times".

  - name: RefreshToken
    identifier: id
    attributes: [id, account_id, token_hash, family_id, issued_at, expires_at, rotated_at, reuse_detected_at]
    description: >
      One refresh token in a rotation chain. The family is the unit of
      invalidation, not the token.
    constraints:
      - token_hash, never the token. Asserted by reading the column.
      - family_id is what makes reuse detection work. Presenting a rotated-out token invalidates THE WHOLE FAMILY, not just that token [US1.8]. Invalidating only the presented one leaves the thief's token working, which inverts the control.
      - rotated_at distinguishes "superseded" from "still current". A token with rotated_at set, presented again, is the reuse signal.
      - reuse_detected_at records the event for the audit log. It is also the thing that makes a mass-logout incident explicable afterwards.

  - name: RateLimitCounter
    identifier: id
    attributes: [id, scope_kind, scope_value, window_start, count]
    description: >
      A counter in the DATASTORE, not in a process. Carries three of the
      seven controls: per-number, per-IP-prefix, and the global ceiling.
    constraints:
      - DATASTORE-BACKED IS A CORRECTNESS REQUIREMENT, NOT HARDENING [AC1.8.3]. A per-process dictionary is the obvious implementation, passes every naive test, and silently stops working the moment there are two workers — which Phase 1 has, since one Lightsail host runs several Uvicorn workers. The test must FAIL against a per-process dictionary.
      - scope_kind distinguishes number, ip_prefix and global, so the per-number and per-IP sub-ceilings sit BENEATH the global one. A global-only ceiling converts a financial attack into a total lockout of every legitimate teacher for the rest of the day; the breaker must degrade rather than cliff-edge.
      - UNIQUE on (scope_kind, scope_value, window_start) with an atomic upsert-and-increment, so two workers racing on the same window cannot both read a stale count.

  - name: AuthAuditLog
    identifier: id
    attributes: [id, account_id, event, occurred_at, correlation_id]
    description: >
      Append-only. Holds OTP issued, verify failed, verify succeeded,
      refresh rotated, refresh reuse detected.
    constraints:
      - NO OTP, NO TOKEN, NO PHONE NUMBER, NO CHILD NAME. An audit log that leaks what it audits is a common and self-defeating mistake. The correlation id is how a row is tied back to a request without carrying its contents.
      - "Append-only: no UPDATE, no DELETE. This is what lets the project answer \"was this child's data accessed improperly\", which both COPPA and GDPR-K assume can be answered and which a parent complaint will ask."
      - account_id is nullable, because an OTP issued for an unknown number has no account — and recording a placeholder would reintroduce the existence oracle the issue path exists to close.

  # ---- Created empty, read, never written ----

  - name: Owner
    identifier: id
    attributes: [id, account_id, created_at]
    ownership: U4 owns behaviour; U3 creates the table
    description: >
      A teacher's ownership of batches. Read by lens resolution.
    constraints:
      - "U3's migration CREATES THIS TABLE EMPTY and never writes it. Empty is not absent: a query against a table that does not exist fails, so the skeleton could not run end to end without it."
      - Table shape only. Not an ownership transfer, and not a dependency on U4. A test asserts U3 contains no INSERT, UPDATE or DELETE here.

  - name: Enrollment
    identifier: id
    attributes: [id, batch_id, account_id, display_name, created_at]
    ownership: U4 owns behaviour; U3 creates the table
    description: >
      A student's place in a batch, and the teacher-typed display name.
      Read by lens resolution.
    constraints:
      - Same shell rule as Owner.
      - display_name is the TEACHER-TYPED name and lives here rather than on Profile, which is the table split that makes the privacy boundary structural. A teacher reads this column; they never reach Profile.
```

---

## Part B — The lens, which is not an entity

**`Lens` has no table and that is the point.** It is computed per request
from `Owner` and `Enrollment`, and the absence of a row is what makes
AC1.9.1 mechanical rather than aspirational:

```
teacher lens  ⟸  this account owns ≥ 1 Owner row
student lens  ⟸  this account has ≥ 1 Enrollment as the student
guardian lens ⟸  this account has ≥ 1 Enrollment as a guardian
```

An account with none of these has no lens, which is why AC1.2.3 holds for
free rather than by a check: a number appearing only as a student is offered
only a student lens because the guardian query returns nothing.

**Memoization lives on the request object**, so it is garbage-collected with
the request. There is no module-level dict, no `lru_cache`, and no cache key
that could outlive a request — the three mechanisms that would turn
request-scoped memoization into the cross-request caching AC1.9.4 forbids.

---

## Part C — What the shape buys

Three entities carry a security property in their columns rather than in the
code that touches them, which is the `team.md` principle that where a rule
matters it should be mechanical:

| Entity | The shape | What it prevents |
|---|---|---|
| `OtpRequest` | `otp_hash`, not `otp` | A leaked row yielding live codes |
| `RefreshToken` | `family_id` | Invalidating one token and leaving the thief's |
| `RateLimitCounter` | A row, not a variable | A limit that works in testing and not in production |

And one entity carries it in an **absence**: `Account` has no role column,
so there is nothing to read a stale role from.

---

## Assumptions & Open Questions

**None.** [assumption] The three BulkSMSBD questions closed before this
stage: the vendor is selected, there is no sandbox (non-production runs a
null adapter), and the Bangla-body rule does not apply to OTP traffic. All
three are recorded in `contract-summary.md` §C.4 and none changes an entity
here.
