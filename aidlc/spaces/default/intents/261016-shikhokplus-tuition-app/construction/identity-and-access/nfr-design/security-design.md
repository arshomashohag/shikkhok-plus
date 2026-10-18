# Security Design — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**
**Depth**: Comprehensive

> Requirements stated **what** must hold. This states **how**: the concrete
> mechanism per requirement, where it physically lives, and what fails when
> it is violated.
>
> **This is a design stage.** Snippets are interface-level and
> illustrative; implementations belong to Code Generation.
>
> Two mechanisms here were **corrected under scrutiny rather than designed
> correctly first time**, and both are recorded as corrections because the
> wrong version of each read as more security-conscious than the right one.

## Sources

- [stage] `nfr-design-questions.md` — the six design questions
- [upstream] `construction/identity-and-access/nfr-requirements/security-requirements.md` — T1–T8
- [upstream] `construction/identity-and-access/nfr-requirements/tech-stack-decisions.md` — A.1–A.6
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR1.1–BR6.3
- [upstream] `construction/identity-and-access/functional-design/functional-spec.md`
- [upstream] `inception/contract-design/contract-summary.md` — §B.3, §B.4, §C.4
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.1, US1.2, US1.5, US1.8, US1.9
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12, NFR13, NFR14
- [team] `## Walking Skeleton`, `## Deployment`, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Where everything lives

```
app/
  authz/
    lenses.py          # the types          (from U2)
    annotations.py     # the resolver       (from U2)
    resolve.py         # NEW - lens resolution against Owner/Enrollment
    rls.py             # NEW - the RLS session context
  auth/
    otp.py             # issue and verify
    tokens.py          # JWT + refresh rotation
    hashing.py         # the HMAC chokepoint        [T1]
    ceilings.py        # the four counters          [T6]
  gateway/
    sms.py             # the SmsGateway protocol
    bulksmsbd.py       # the real adapter           [T2, T3]
    null.py            # the default outside prod   [BR5.4]
  audit/
    log.py             # append-only, redacted      [T8]
  db/
    migrations/        # Alembic, from zero
    seed_skeleton.py   # BR6.3 - manual, never imported

tests/
  auth/                # the seven controls, adversarially
  authz/               # lens resolution, including the two cache tests
  privacy/             # RLS probes, behind the meta-test
  gateway/             # adapter contract against a stub
```

**One chokepoint per asset.** Every OTP hash goes through
`auth/hashing.py`; every gateway call through `gateway/`; every audit row
through `audit/log.py`. That is what makes each control assertable by an
import test rather than by reading every call site.

---

## B. T1 — A leaked database yields nothing

### B.1 The OTP chokepoint

```python
def store_hash(code: str) -> str:
    """Hash an OTP for storage. The only way a code reaches the database.

    :param code: The transmitted code
    :return: The value to store
    """
    return hmac.new(_otp_key(), code.encode(), hashlib.sha256).hexdigest()
```

**The key is read from the environment, never from the database**, and is
one of the three named secrets. A `SELECT *` on `otp_request` therefore
yields values that cannot be reversed without a second, separately-held
secret.

> **This design reversed under measurement, and the first version read as
> more rigorous.** "Use bcrypt" is the instinct. Measured on this machine:
>
> | Scheme | Per issue | Offline exhaustion of 10⁶ |
> |---|---|---|
> | SHA-256 | ~0.1 µs | **0.07 s** |
> | bcrypt(8) | 15 ms | 4 h |
> | bcrypt(10) | 58 ms | 16 h |
> | **HMAC+key** | **~1 µs** | **not without the key** |
>
> bcrypt slows an attacker who will get there anyway; HMAC stops one who
> has only the database. The attempt ceiling [BR2.3] already defends the
> online path, so the offline path is the whole question here — and a
> 6-digit space is too small for work-factor delay to be the answer.

**Verification**: read the stored column, assert it differs from the
transmitted code, and assert it is **not reproducible** without the key.
The second half is what distinguishes HMAC from a bare digest, and the
first half alone would pass against SHA-256.

### B.2 Refresh tokens

Same shape: `token_hash` only, through one function. A leaked table yields
no usable session.

---

## C. T6 and T7 — The two mechanisms that were wrong first

### C.1 The ceiling cascade — narrowest first

```python
SCOPES = (                       # ORDER IS THE CONTROL
    ("number_hour",   lambda r: r.phone,      3,  HOUR),
    ("number_day",    lambda r: r.phone,      5,  DAY),
    ("ip_hour",       lambda r: r.ip_prefix, 10,  HOUR),
    ("global_day",    lambda r: "global",   CEIL,  DAY),
)
```

Each scope is checked **and incremented only if it passes**, in this
order. A refusal at `number_hour` therefore never touches `global_day`.

> **An earlier design checked global first, and the rule argued against
> itself.** BR2.5's prose said sub-ceilings exist *"so an attacker burning
> one number's allowance does not exhaust everyone else's"* — while its
> logic checked the global counter first. That order lets one attacker
> consume the global daily budget before their own per-number limit trips:
> they are stopped eventually, but only after spending every legitimate
> teacher's allowance for the day.
>
> Caught at review. Recorded because **global-first still looks like
> defence in depth** — it reads as "check the big one first", which is
> exactly backwards.

**Atomicity**: one statement per scope.

```sql
INSERT INTO rate_limit_counter (scope_kind, scope_value, window_start, count)
VALUES (:kind, :value, :window, 1)
ON CONFLICT (scope_kind, scope_value, window_start)
DO UPDATE SET count = rate_limit_counter.count + 1
RETURNING count;
```

The returned count is compared **after** the increment, so two workers
racing on the same window cannot both read a stale value and both pass at
the limit [NFR10.2].

### C.2 The existence oracle — symmetric work, including the write

```python
async def issue(phone: str) -> Response:
    """Issue a code. Both branches perform the same work."""
    account = await find_account(phone)        # may be None
    code, digest = generate_and_hash()         # ALWAYS
    async with transaction() as tx:
        await tx.insert(OtpRequest(phone=phone, otp_hash=digest, ...))
        if account is None:
            await tx.rollback()                # same work, discarded
        else:
            await send_and_commit(tx, account, code)
    return SAME_RESPONSE                       # byte-identical
```

> **The hash was the smaller asymmetry, and the first design addressed only
> that one.** The known branch performs a transactional INSERT; the unknown
> branch originally performed none. A database write means lock acquisition
> and a WAL flush — a far louder and more reliable timing signal than a
> hash computation. A test asserting only hashing symmetry would guard the
> quiet channel while leaving the loud one open, **and the accompanying
> "honest limitation" note would make that read as closed**.
>
> Caught at review.

**Verification**: assert both branches issue the **same statements**, at
the statement level, not by timing.

**What remains, stated rather than implied**: equivalent work is not
constant time. A patient attacker with a very large sample could still
find residual variance. Closing that needs a fixed response deadline —
returning only after a wall clock elapses regardless of path — which is
implementable but would become a latency floor on every OTP request.
Disproportionate here; recorded so the control is not read as stronger
than it is.

---

## D. T4 — The privacy boundary, three layers

| Layer | Mechanism | Owned by |
|---|---|---|
| Schema | Teacher-lens response schemas carry no profile field | **U2** |
| Tables | `Profile` vs `Enrollment.display_name`, different writers | **U3** [BR3.1] |
| Database | Row-level security on `Profile` | **U3** [BR3.2] |

```sql
ALTER TABLE profile ENABLE ROW LEVEL SECURITY;
CREATE POLICY profile_owner_only ON profile
  USING (account_id = current_setting('app.account_id')::uuid);
```

The session variable is set by `app/authz/rls.py` as part of lens
resolution, inside the request transaction, so it cannot outlive it.

### D.1 The meta-test, which runs first

```python
def test_rls_is_actually_in_force() -> None:
    """Assert the suite can observe RLS at all, before trusting it."""
    assert not current_user_is_superuser()
    assert row_security_is_on()
    assert policy_exists("profile", "profile_owner_only")
```

> **Without this, the other two layers certify nothing.** PostgreSQL
> documents that superusers and table owners bypass RLS entirely, and the
> default testcontainers connection is `postgres` — a superuser. A privacy
> suite run as superuser passes identically whether the policy is correct,
> broken, or **absent**.
>
> So the migration creates a **restricted role** that owns nothing, and the
> suite connects as that role. This is a `project.md` NEVER rule, and it is
> what makes the strongest obligation in the project mean something.

### D.2 The adversarial probes

Not "does a teacher see the right name" but **"can a teacher reach the
wrong one"**: a direct query against `Profile` under a teacher session, a
join attempted from a teacher-facing query, and an ORM relationship
traversal. Each must return zero rows rather than being prevented by
application code.

---

## E. T5 — Token lifecycle as a state machine

```
issue ──▶ [current] ──refresh──▶ [rotated] ──replay──▶ FAMILY DEAD
                │                                          ▲
                └──────────── replay ──────────────────────┘
```

Five transitions, tested as a machine rather than a happy path:

1. A valid refresh returns a new pair and marks the old `rotated_at`.
2. The rotated-out token, replayed, is **refused**.
3. That refusal **invalidates every token sharing `family_id`** — including
   the one just issued.
4. `token_hash` only, asserted by reading the column.
5. A 15-minute-expired access token is refused.

> **Transition 3 is the one most likely to be missed**, and missing it
> inverts the control: invalidating only the presented token leaves the
> *thief's* token working. The happy path is identical either way, which is
> why this is a state machine and not a sequence of unit tests.

**The access token carries no role and no lens claim.** A lens baked into
a 15-minute token is a cached role by another name and would survive an
ownership change for up to fifteen minutes — exactly what BR1.2 and BR1.3
forbid.

**The crash-lockout recovery path**, stated because it has a cost: a client
crashing between receiving and persisting a rotated pair is locked out, and
recovers by re-authenticating via OTP. That code draws on the per-number
ceiling, so three such crashes in an hour lock a legitimate teacher out
until the window rolls. The interaction is invisible from either rule
alone.

---

## F. T2 and T3 — Secrets and transport

```python
class BulkSmsBdGateway:
    def __init__(self, base_url: str, api_key: str) -> None:
        if urlparse(base_url).scheme != "https":      # NOT configurable
            raise ValueError("the SMS gateway requires https")
```

> **Verified against the live endpoint**: plain HTTP serves the same API
> with **no redirect and no HSTS**, so a misconfigured `http://` ships the
> phone number and the OTP in cleartext and **succeeds silently** —
> nothing fails, warns or logs. Under RC-1/RC-2/RC-3 that is a privacy
> failure on children's-adjacent data, which is why the scheme is a
> mechanism rather than a review item.

**Logging**: `(purpose, outcome, correlation_id)` and nothing else.

- **Never `error_message`** — verified: it echoes the API key back in
  plaintext (`"user id not found in this <key> key"`). A live credential
  leak path, not a hypothetical one.
- **Never the request body** — it carries the number and the code together.

Both are enforced by an import-and-call test over `gateway/`, not by
reviewing every log statement.

---

## G. T8 — The audit log

Append-only, five event types, and **redaction is half the requirement**:

```python
@dataclass(frozen=True)
class AuditEvent:
    event: AuthEvent          # a closed enum
    account_id: UUID | None   # nullable: an unknown number has no account
    correlation_id: str
    occurred_at: datetime
```

There is **no free-form field**, which is the mechanism: there is nowhere
to put a phone number, an OTP, a token or a child name. A test asserts the
dataclass has no `str` field other than `correlation_id`.

> `account_id` is nullable deliberately. An OTP issued for an unknown
> number has no account, and writing a placeholder would reintroduce the
> existence oracle the issue path exists to close.

---

## H. What this design does not defend against

| Not defended | Why |
|---|---|
| An attacker with the HMAC key **and** the database | Defence in depth stops here; the key has an exercised rotation runbook |
| Timing analysis with a very large sample | §C.2 closes the dominant asymmetry; constant-time needs a response deadline and a latency floor |
| SIM swap | The phone number is the identity by design [D-35]; no second factor at this scale |
| A compromised production host | No admin surface at this budget; the controls are the named-role access log and the append-only audit |
| Denial of service | One instance, no WAF. The ceilings bound the **cost**, not the availability |

---

## Assumptions & Open Questions

**One, a value rather than a decision.** [assumption] The global daily SMS
ceiling's number derives from BulkSMSBD's per-SMS rate against the USD
50/month budget. The mechanism is designed and tested at a
test-configured threshold; the production value is set at deployment.
