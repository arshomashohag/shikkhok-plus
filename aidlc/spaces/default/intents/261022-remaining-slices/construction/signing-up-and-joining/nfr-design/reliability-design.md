# Reliability Design — D1 `signing-up-and-joining`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> Two transactions and one migration. The migration is the only part that
> cannot be undone, and it runs against live staging data — so most of this
> design is about that, and about one deliberate absence: there is no circuit
> breaker here, for a reason worth stating.

## Sources

- [upstream] `construction/signing-up-and-joining/nfr-requirements/reliability-requirements.md`
  — NFR18.x, NFR19.x
- [upstream] `construction/signing-up-and-joining/functional-design/functional-spec.md` § 5
- [team] Deployment practice and Error handling, 2026-10-22
- [code] `app/errors/`, `app/gateway/`, `app/audit/log.py`, read 2026-10-23

---

## 1. Resilience patterns: what is used and what is refused

| Pattern | Used? | Reason |
|---|---|---|
| **Timeout** | Yes, existing | Every gateway call already carries one |
| **Retry with backoff** | **No** | The gateway attempts a send once, by design |
| **Circuit breaker** | **No** | See below |
| **Bulkhead** | No | One process, one database; nothing to isolate from |
| **Fallback** | No | A signup with no code sent is not degraded; it is retriable by the person |
| **Rate limiter** | Yes, extended | The ceiling cascade, with signup's own scopes [NFR12.4] |

### Why no circuit breaker

A breaker protects a caller from a slow dependency by failing fast once
failures accumulate. Both halves of that are already true here, differently:

- **The caller already fails fast.** One attempt, no automatic retry, a
  timeout recorded as `unknown` rather than `failed` — because a timeout is a
  failure of unknown class, not evidence the message was not delivered.
- **The resource actually at risk is a budget**, and the ceiling cascade
  protects it directly and per-scope.

Adding a breaker would put a second, differently-shaped control over the same
resource. The two would disagree at the edges — a breaker opens on failure
*rate* while the ceiling refuses on *count* — and reconciling them would mean
deciding which is authoritative during an incident, which is the worst moment
to have that question.

**The ceiling breach is a `ConflictError`, never a `TransientError`**, so
nothing in the stack treats it as retryable [NFR12.6].

---

## 2. Retry design: the person is the retry

Retryability is a property of the error **class**, read off the type in
exactly one place and never decided at a raise site [NFR19.6].

| Failure | Class | Retryable | What happens |
|---|---|---|---|
| Duplicate number | `ConflictError` | No | Directed to log in [BR4.4] |
| Ceiling breached | `ConflictError` | No | Told, not silently dropped |
| Bad input | `ValidationError` | No | Field-level correction |
| Database unavailable | `TransientError` | **Yes** | 503; the client shows the error and **keeps what was typed** |

There is no automatic client retry and no local write queue. NFR5 permits
offline writes for the mid-class path only — the topic log and attendance,
which are D4's. A queued signup would be an account that may or may not exist,
which is worse than an error message.

---

## 3. Transactional design

### Signup is one transaction

```
BEGIN
  INSERT account   (phone)
  INSERT profile   (account_id, self_name, address)
  INSERT owner     (account_id)        -- only if role = Teacher
COMMIT
→ then trigger the OTP path
```

Three properties [NFR19.5, NFR19.7]:

1. **All three or none.** A failure anywhere leaves no account, so the
   assumption every later reader will make — that an account has a profile —
   holds from the first row.
2. **The owner row is conditional**, and its absence is the non-teacher case
   rather than a missing row [BR4.1].
3. **The OTP trigger is outside the transaction.** Sending inside would make a
   gateway timeout roll back a committed-worthy account.

### The deliberate asymmetry

**A gateway failure leaves the account created** [NFR19.6]. That is the better
failure: the person signs in by requesting a new code, through a path that
already exists and is already rate-limited. The alternative — account creation
conditional on a successful send — turns a third party's outage into a failure
to exist.

### Acceptance is one column write

A decision moves `pending → accepted` or `pending → declined`, or
`declined → accepted` [BR5.4]. Nothing resets to `pending` [NFR19.7]. Two taps
on accept converge: the transition is **idempotent in its target state**,
which is a property of the state machine rather than a lock.

---

## 4. The migration

The one irreversible step, run against live staging data.

```
1. ADD COLUMN student_decision, guardian_decision   (nullable for now)
2. UPDATE ... SET decision = CASE WHEN <link> IS NOT NULL
                             THEN 'accepted' ELSE 'pending' END
3. ALTER COLUMN ... SET NOT NULL     (no column default, ever)
4. ADD COLUMN profile.address        (nullable)
```

| Property | Design | Requirement |
|---|---|---|
| Forward-only, backward-compatible | The columns are additive, so the **previous image still runs against the new schema** | NFR19.1 |
| A distinct logged step | Alembic runs before the new container serves traffic, never as a side effect of app start | NFR19.1 |
| Conditional backfill | Never `DEFAULT 'pending'` | NFR19.2 |
| Verified backup first | `pg_dump` to S3, with object existence and non-trivial size asserted after upload | NFR19.3 |
| Rehearsed on staging | Against realistic data, before production | NFR19.4 |

**Why the backfill is conditional, stated as a reliability property.** A plain
default would withdraw a working lens from every student already signed in.
The failure mode is a person opening the app and finding their batches gone —
an availability incident caused by a schema default, recoverable only by a
second migration after the complaint.

**What backward-compatibility buys.** Rollback is redeploying the previous
image tag, which does **not** revert a migration. Because the columns are
additive and the old code never reads them, a tag rollback is a complete
rollback of the application without touching the schema.

**The honest consequence**, recorded rather than hidden: the backfill grants
`accepted` to people who were never asked, because under the old model nobody
was. The alternative — making every existing user re-accept — would log them
out of their own records to fix a problem they do not have.

---

## 5. Failure domains and degradation

**D1 states no availability target of its own** [NFR18.1]. Phase 1 is a single
Lightsail host with a recreate-style deploy and an accepted short restart
window, and nothing in this unit argues for changing that: a signup that fails
is retried by a person already looking at the screen. **Deploys carrying D1
are scheduled outside Bangladesh classroom hours** [NFR18.2] on the existing
practice — not because signup is time-critical, but because the same deploy
carries everything else.

| Dependency | Tier | Degradation |
|---|---|---|
| PostgreSQL | **Critical** | None. Signup and acceptance are writes; without the database there is nothing to degrade to |
| SMS gateway | **Critical for completion, not for creation** | The account exists; the code is retriable [NFR19.6] |
| FCM | Not used by D1 | D3 owns the adapter |

### The audit log fails open, and that is why it alerts

The component must not fail the authentication it records, so it catches,
logs `critical`, and swallows — leaving the caller's transaction intact via a
savepoint.

**That makes it suppressible by anyone who can cause write failures.** The
trade is only acceptable because the failure is loud to the operator
[NFR25.3]. Without the alert, this is a security control with a documented off
switch. The alert is therefore part of the reliability design, not an
observability nicety.

---

## 6. Health and smoke

| Check | Covers |
|---|---|
| Health endpoint: database connectivity + applied migration revision | That the migration ran and the app can reach the database |
| Post-deploy smoke: OTP issue and verify, authenticated lens resolution | D1's path minus the new write |
| **Extension**: one signup call against the staging gateway | D1's new write, end to end |

The smoke set already exercises almost all of D1. Adding a signup call is a
small, natural extension and is Code Generation's to wire.

**A smoke failure triggers an immediate tag rollback**, not an investigation
on a live system [team: Deployment].

---

## Assumptions & Open Questions

- **Assumed**: the signup ceiling check runs before the transaction opens, so
  a refusal writes nothing and the counter increment is not inside rolled-back
  work.
- **Assumed**: non-production environments hold the gateway's test or sandbox
  credentials, so a staging signup sends no real SMS.
- **Open, and not D1's**: the scheduled job enforcing the declared 48-hour
  retention on `rate_limit_counter` [NFR6.22]. The disposition exists; nothing
  enforces it, and D1 enlarges the table rather than creating the gap.
