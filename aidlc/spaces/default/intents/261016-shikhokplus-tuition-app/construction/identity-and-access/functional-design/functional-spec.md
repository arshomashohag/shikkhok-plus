# Functional Specification — `identity-and-access` (U3)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access` — **the walking skeleton**

> **The first Unit that runs.** U1 was arithmetic with no process, U2 a
> contract with no routes. This Unit opens the first endpoint, applies the
> first migration, and renders the first screen — against a real gateway,
> a real database and a real handset.
>
> Three endpoints, one resolver, one adapter, one migration. The volume is
> in the controls, not the surface area.

## Sources

- [stage] `functional-design-questions.md` — all seven answers
- [upstream] `construction/identity-and-access/functional-design/rules.md`
  — BR1.1–BR6.2
- [upstream] `construction/identity-and-access/functional-design/entities.md`
- [upstream] `inception/contract-design/contract-summary.md` — §B.3, §B.4, §C, §C.4
- [upstream] `inception/user-stories/stories.md` — US1.1, US1.2, US1.5, US1.8, US1.9
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — the
  six stories this Unit owns: US1.1, US1.2, US1.5, US1.8, US1.9
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12, NFR13, NFR14
- [upstream] `construction/api-contract/functional-design/rules.md` — BR4.4
- [team] `## Walking Skeleton`, `## Testing Posture`, `## Code Style`
- [project] `## Forbidden` / `## Mandated`

---

## 1. What this Unit delivers

| # | Deliverable | Surface |
|---|---|---|
| 1 | `POST /v1/auth/otp` — issue | Public route |
| 2 | `POST /v1/auth/verify` — verify, returns a token pair | Public route |
| 3 | `POST /v1/auth/refresh` — rotate | Authenticated, lens-exempt |
| 4 | The lens resolver | A FastAPI dependency, used by every later Unit |
| 5 | The BulkSMSBD adapter + null adapter | One call site |
| 6 | The first Alembic migration, from zero | 7 owned tables + 2 shells |
| 7 | Row-level security on `Profile` | A policy, plus the restricted role |
| 8 | The append-only auth audit log | 5 event types |
| 9 | Android: OTP entry, lens switcher, both language bundles | Compose |

**Three of the five `PUBLIC_ROUTES` U2 fixed are opened here.** The other
two are U11's deletion routes. The refresh route goes in
`LENS_EXEMPT_AUTHENTICATED`, which is why U2 kept that set separate.

---

## 2. Operations

### 2.1 Issue a code — `POST /v1/auth/otp`

1. Read the phone number **from the request body**. It is never read from
   the SIM, and the app holds no SMS read permission [AC1.1.6].
2. Check the ceilings **in this order, before any gateway call** [BR2.2]:
   global daily → per-IP-prefix hourly → per-number hourly → per-number
   daily. Each is an atomic upsert-and-increment on a counter row [BR2.1].
3. On any breach: return a **temporary-unavailability** message_key. Never
   "invalid number", and never the limit itself [BR2.6].
4. Resolve the account. **Both branches continue identically** [BR2.7]:
   generate a code, hash it, and either store the row (known number) or
   discard the hash (unknown number).
5. Send through the adapter — **once**, with no retry [BR5.3].
6. Record the outcome. Budget is consumed on **every** outcome including
   `UNKNOWN` and `BUDGET_REFUSED`, because an `UNKNOWN` may have cost
   money and counting only `SENT` would let a flapping gateway spend
   without bound.
7. Write `OTP_ISSUED` to the audit log — correlation id, no number, no code
   [BR6.2].
8. Return the **same response** whether or not the number had an account.

> **Step 4 is the one an implementer will shortcut.** The natural shape is
> "look up the account; if absent, return early". That early return is what
> makes the unknown path measurably cheaper, and it is the defect NFR14.4
> describes — deferred to this Unit by U2's BR4.4. The test asserts the
> hash function ran on both branches, structurally, never as a wall-clock
> bound.

### 2.2 Verify a code — `POST /v1/auth/verify`

1. Load the `OtpRequest` for this number, newest first.
2. Refuse if `now > expires_at`, if `consumed_at` is set, or if attempts
   `>= 5` [BR2.3]. Each refusal records a `VerifyAttempt`.
3. Compare the **hash**, never a stored plaintext [BR2.4].
4. On success, set `consumed_at` **in the same transaction as the check
   that read it**, so a concurrent second verify cannot slip between them.
5. Activate the account if dormant — this is what lets a student or
   guardian claim a record a teacher created, without being invited
   [AC1.2.1].
6. Issue an access token (15 min, `kid` header, **no role and no lens
   claim**) and a refresh token (30 days, opaque, stored hashed, new
   `family_id`).
7. Write `VERIFY_SUCCEEDED` or `VERIFY_FAILED` to the audit log.

> **No lens claim in the token, deliberately.** A lens baked into a
> 15-minute token is a cached role by another name, and it would survive an
> ownership change for up to fifteen minutes — which is exactly what
> BR1.2 and BR1.3 forbid.

### 2.3 Rotate — `POST /v1/auth/refresh`

1. Hash the presented token and load its row.
2. **If `rotated_at` is set, this is reuse**: invalidate every token sharing
   its `family_id`, write `REFRESH_REUSE_DETECTED`, and return 401
   `REFRESH_TOKEN_REUSED` [BR4.1].
3. Otherwise rotate: mark the presented token rotated, issue a new pair in
   the same family, write `REFRESH_ROTATED`.
4. The response carries **both** new tokens. The client replaces them
   atomically; a crash in between means the next refresh fails as reuse,
   which is the correct conservative outcome.

> **Step 2 is the whole mechanism and the happy path cannot see it.** A
> client that refreshes normally behaves identically whether or not the old
> token was invalidated. Only a *replayed* token reveals the difference —
> and that is the stolen-token case the control exists for. Invalidating
> only the presented token would leave the thief's working, inverting it.

### 2.4 Resolve the lens — a dependency, not a guard

1. Read `request.state` for a memo. If present, return it [BR1.4].
2. Otherwise query **at this moment**: `Owner` rows for a teacher lens,
   `Enrollment` rows for student and guardian lenses [BR1.1].
3. Apply the client's `X-Lens-Hint` **only to select among lenses the
   account already has**. An unsupported hint is refused 403
   `LENS_NOT_AVAILABLE`; a missing hint on a lens-ambiguous route is
   refused 400 `LENS_HINT_REQUIRED` [U2's BR1.7].
4. Set the row-level-security session context to the resolved account.
5. Memoize **on the request object** and return.

> **The memo's location is the control.** On `request.state` it is
> garbage-collected with the request. In a module-level dict, an
> `lru_cache`, or a Redis key it is not — and at the call site the three
> look identical. That is why BR1.4 names the mechanism rather than the
> intent.
>
> An account with no `Owner` and no `Enrollment` rows has **no lens**,
> which is why AC1.2.3 holds for free: a number appearing only as a student
> is offered only a student lens because the guardian query returns
> nothing.

### 2.5 Send an SMS — the adapter

1. Construct only when the scheme is `https`; **raise otherwise** [BR5.2].
2. Check the per-purpose ceiling before the call. A breach is a
   `ConflictError` (409), never `TransientError` — retrying into a cost
   ceiling is exactly wrong.
3. POST to BulkSMSBD. **Success is `response_code == 202` and nothing
   else** [BR5.1]; a non-2xx HTTP status means a transport problem, never
   an application rejection.
4. Map the outcome: `SENT`, `FAILED`, `UNKNOWN` (timeout or 1005), or
   `BUDGET_REFUSED`.
5. Log `(purpose, outcome, correlation_id)` and **nothing else** — never
   the request body, which carries the number and the code together, and
   never `error_message`, which **echoes the API key back in plaintext**
   [BR6.2].

> **Outside production this is the null adapter, by default** [BR5.4]. It
> records the intended send, returns `SENT`, and makes no network call.
> Selection is explicit, so a missing or misspelt setting fails *toward not
> sending* rather than toward spending real money. BulkSMSBD has no
> sandbox, so this is how `team.md`'s non-production rule is satisfied —
> by a different mechanism than the one it names, recorded rather than
> quietly reinterpreted.

### 2.6 Migrate — from zero, against a real Postgres

1. Create the seven owned tables.
2. Create `Owner` and `Enrollment` **empty** [BR6.1]. Empty is not absent:
   lens resolution queries all three, and a query against a table that does
   not exist fails — so the skeleton could not run end to end without them.
3. Enable row-level security on `Profile` and create the policy [BR3.2].
4. Create the **restricted application role**, which is not the owner of
   these tables and is not a superuser.

> The test container migrates with Alembic **from zero** rather than
> loading a schema dump, which gives the migration path continuous exercise
> at no extra cost. This matters more than usual because the fee model is
> known to be changing and there is no failover.

---

## 3. The Android surface

Deliberately thin, and that is the point [TC-9, D-31]:

- **OTP entry** via the SMS Retriever API — no SMS read permission, and the
  number is typed by the user, never read from the SIM [AC1.1.6].
- **The lens switcher** changes the active lens without re-authenticating
  [AC1.2.4]. It sends a hint; it does not decide anything.
- **Both language bundles on screen one** [TC-15, D-43]. Bangla text that
  breaks a layout is a per-screen problem, and discovering it on screen one
  is how it is not discovered on screen forty.
- **No business logic.** The client renders what the server computed. The
  response names the lens that produced it, and the client renders from
  that rather than from the hint it sent.

---

## 4. Boundary cases

| Case | Behaviour | Why |
|---|---|---|
| Unknown number requests a code | Identical response, same hashing work, budget consumed | Existence oracle [BR2.7] |
| Code entered at 5m01s | Refused as expired, new one offered | [AC1.1.3] |
| 6th wrong attempt | Refused **and the code is dead** — a correct 7th also fails | [BR2.3] |
| Verified code reused | Refused | `consumed_at` set in the checking transaction |
| SMS never arrives | "Delivery failed", resend offered after cooldown | Never "wrong code" [AC1.1.5] |
| Gateway times out | `UNKNOWN`, budget consumed, no retry | May have been delivered [BR5.3] |
| Ceiling tripped | "Temporarily unavailable" | Never "invalid number" [BR2.6] |
| Rotated-out token replayed | **Whole family invalidated**, 401 | [BR4.1] |
| Account creates first batch | Teacher lens on the **next** request | [BR1.2] |
| Account loses last enrollment | Student lens gone on the **next** request | [BR1.3] |
| Two requests, same account | **Both** hit the database | [BR1.4] |
| Teacher reads a roster | Sees `Enrollment.display_name`, never `Profile` | [BR3.1] |

---

## 5. What this Unit does not build

- **No batch or enrollment creation.** U4's. This Unit creates the tables
  empty and reads them.
- **No money.** U1 owns the type; no money crosses this Unit's surface.
- **No deletion.** US1.6 and US1.7 moved to U11 deliberately, so the
  deletion paths are specified once against the full schema rather than
  twice.
- **No admin surface.** There is none in this product, at any budget.

---

## 6. Rules summary — derived

| Group | Covers | Rules |
|---|---|---|
| **BR1.x** | The lens is computed, never stored | BR1.1–BR1.4 |
| **BR2.x** | The seven OTP abuse controls | BR2.1–BR2.7 |
| **BR3.x** | The privacy boundary | BR3.1–BR3.3 |
| **BR4.x** | Token lifecycle | BR4.1–BR4.3 |
| **BR5.x** | The gateway | BR5.1–BR5.5 |
| **BR6.x** | Boundaries not to cross | BR6.1–BR6.2 |

---

## Assumptions & Open Questions

**None.** [assumption] The three BulkSMSBD questions closed before this
stage and their answers are binding here as BR5.1–BR5.5. The one
consequence worth restating: the gateway leg is verified exactly once, at
this Bolt's checkpoint, against production credentials with a single send
to the developer's own number — because no sandbox exists.
