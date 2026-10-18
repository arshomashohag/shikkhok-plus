# Unit Test Instructions — `identity-and-access` (U3)

**Stage**: code-generation (3.5)
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**
**Test strategy**: Comprehensive (10–15 tests per component)
**Methodology**: custom — the predicate, not a list

---

## The exact command

```bash
python3 -m pytest tests/auth tests/authz tests/privacy tests/gateway -q
```

Requires a **Docker daemon** — the suite starts a PostgreSQL 16
testcontainer. That is a new prerequisite at this Bolt and B1 anticipated
it.

Full gate, local and in CI:

```bash
make check
```

**Still no secret required.** The gateway is stubbed; the database is a
container. A fresh clone runs the complete gate.

---

## The one fixture everything depends on

```python
@pytest.fixture(scope="session")
def restricted_session():
    """A session connected as the RESTRICTED role, not postgres."""
```

> **Connecting as `postgres` would silently void the entire privacy
> suite.** Superusers and table owners bypass row-level security, so every
> probe would pass against a missing policy. The meta-test below runs
> first precisely because this fixture is easy to get wrong in a way
> nothing else detects.

---

## Which tests are written first

The predicate: **test-first when the correct output is knowable from the
requirement AND a wrong answer is a money or authorization error.** On
this Unit that is most of it.

**Test-first**: the RLS meta-test, lens resolution, the seven abuse
controls, token rotation, the privacy probes.

**Test-after**: the HMAC chokepoint, the gateway adapter, the migration,
and every Compose screen — the last by `team.md`'s stated exception, since
with no declared Android experience a Compose test written first is as
likely to encode a misunderstanding of the framework as to catch a defect.

---

## Per-component inventory

### `app/authz/resolve.py` — 12 tests

The two that carry the rule, named rather than incidental:

| # | Test | Why it exists |
|---|---|---|
| 1 | Gaining an `Owner` row → teacher lens on the **next request** | **Fails against a cached lens** |
| 2 | Losing the last `Enrollment` → student lens gone **next request** | **Fails against a cached lens**, and the more dangerous direction |

Plus: no lens for an account with neither; both lenses for an account with
both; a guardian-only account gets no student lens; two lookups in one
request hit the DB **once**; two requests hit it **twice**; the lens is
never read from a column; `request.state` is cleared between requests; the
RLS session variable is set; it is unset after the transaction; **one
query, not three**.

### `app/auth/ceilings.py` — 14 tests

| Control | Adversarial form |
|---|---|
| 3/hour per number | The 4th is refused |
| 5/day per number | The 6th is refused |
| 10/hour per IP | The 11th is refused |
| Global daily | Refused **and the alert fires** |
| **Order** | A per-number refusal **does not increment** the global counter |
| **Two workers** | The limit holds across two sessions — *fails against a dict* |
| Atomicity | Concurrent increments at the boundary admit exactly one |

> The order test and the two-worker test are the two that cannot be
> satisfied by a plausible-but-wrong implementation.

### `app/auth/otp.py` — 13 tests

5m01s refused; a verified code cannot re-verify; the 6th attempt refused
**and the code dead so a correct 7th also fails**; a concurrent second
verify loses; the stored value differs from the transmitted one; **it is
not reproducible without the key**; both known and unknown responses are
byte-identical; **both issue the same statements**; budget consumed on
every outcome; `OTP_ISSUED` written; no phone number in the audit row; the
code never reaches a log; a dormant account activates on first verify.

### `app/auth/tokens.py` — 11 tests

The five-transition state machine (rotate → replay refused → **family
invalidated** → hashed → expiry), plus: `kid` present; two verification
keys both work; **no role claim**; **no lens claim**; a second 401 ends the
session; the crash-lockout recovery path is re-auth by OTP.

### `app/gateway/` — 12 tests

`response_code == 202` is the **only** success; **HTTP 200 with an error
code is not success**; a non-https base URL **raises at construction**;
one attempt only; a timeout is `UNKNOWN`; `error_message` is **never
logged**; the request body is never logged; the null adapter is the
**default**; the null adapter makes no network call; per-purpose ceiling
checked before the call; a ceiling breach is `ConflictError`; the OTP
template + app hash ≤ 160 GSM-7.

### `tests/privacy/` — 10 tests

**The meta-test runs first** (not a superuser; `row_security` on; policy
present). Then the probes: a teacher's direct query on `Profile` returns
zero rows; a join returns zero; an ORM traversal returns zero; a teacher
reads `Enrollment.display_name` successfully; an owner reads their own
`Profile`; a non-owner does not; the two name columns are in different
tables with different writers.

### `app/audit/log.py` — 6 tests

Append-only (no UPDATE, no DELETE); the event enum is closed; **the
dataclass has no `str` field but `correlation_id`**; `account_id` is
nullable; a correlation id appears on every row; the five event types
round-trip.

### Android — 8 tests

ViewModel state machine (loading, success, error, **explicit retry**); no
SMS read permission in the merged manifest; the number is typed rather
than read; both language bundles present on screen one.

---

## Coverage

| Module | Floor | Source |
|---|---|---|
| `app/authz` | **Branch** | Lens resolution is pure branching; line coverage on it is close to meaningless |
| `app/auth` | 80% line | `classic` scope |
| `app/gateway` | 80% line | `classic` scope |
| `app/money` | **100% branch**, unchanged | B1 |
| Android | Reported, no floor yet | The ratchet starts after three Android Bolts |

**No floor is weakened to make a step pass.** That is a `project.md` NEVER
rule.

---

## Not tested here

- **Batch and enrollment behaviour** — U4's. This Unit reads both tables
  and writes neither, and a test asserts the absence of writes.
- **Deletion** — U11's.
- **The real gateway** — stubbed everywhere except the one manual
  verification send at the checkpoint, because BulkSMSBD has no sandbox.
