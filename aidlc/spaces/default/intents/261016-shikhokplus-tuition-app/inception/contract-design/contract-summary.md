# Contract Summary

**Stage**: contract-design (2.8)
**Phase**: Inception
**Depth**: Comprehensive
**Scope**: the whole boundary set, mapped once for the workflow

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — 11 Units and their kinds
- [upstream] `inception/units-generation/unit-of-work-dependency.md` — the DAG; every edge a candidate contract
- [upstream] `inception/domain-design/components.md` and `decisions.md` — entity shapes and ADR-001..008
- [upstream] `inception/requirements-analysis/requirements.md` — NFRs shaping SLAs, errors and retries
- [team] the affirmed error taxonomy, money-as-a-type and layer-boundary practices
- [project] the permanent NEVER/ALWAYS rules

---

---

## A. The boundary inventory

### A.1 The honest position on DAG edges

**Most DAG edges are not contracts, and this artifact says so once rather than inventing a spec per edge.** All eleven Units deploy as one FastAPI container plus one Android `:app` module (`unit-of-work.md`, "Deployment model, stated once"). Between backend Units there is no wire, no serialization, no partial failure and no version skew. Their boundaries are **Python import boundaries and SQLAlchemy ownership rules**, already specified at Domain Design as the five cross-component invariants (`components.md` § Cross-component invariants) and enforced by Ruff `flake8-tidy-imports`, the import-linter test and the route-enumeration test.

Accordingly, these nine edges carry **no contract spec of their own**:

| Edge | Why it is not a wire contract |
|---|---|
| `batches-and-enrollment -> identity-and-access` | In-process; the lens arrives as a FastAPI dependency value |
| `sessions-and-attendance -> batches-and-enrollment` | In-process; `enrollment_id` foreign key |
| `exams-and-marksheets -> batches-and-enrollment` | In-process; same |
| `fee-cycles-and-ledger -> batches-and-enrollment` | In-process; same |
| `payment-claims-and-verification -> fee-cycles-and-ledger` | In-process Python call. ADR-007's "Payments never inserts a `LedgerEntry` directly" is an **import rule**, not an API. Spec'd in §E.3 |
| `teacher-insights -> payment-claims-and-verification` | In-process read of ledger-derived aggregates |
| `teacher-insights -> exams-and-marksheets` | In-process read |
| `release-packaging -> identity-and-access` | Build-time only; U10 needs a buildable app, not a running endpoint |
| `privacy-and-governance -> {U3..U9}` | Declarative manifest coverage, enforced by a schema-iterating test. Spec'd in §E.4 |

What *is* contractual on those edges is the **route surface each Unit adds to the public REST API** (§B) and the **manifest row each table must carry** (§E.4). Both are already owned by U2 and U11 respectively, which is why they are Units rather than obligations.

### A.2 The real contracts

| # | Contract | Provider | Consumer | Mechanism | Owning Unit | Versioned? |
|---|---|---|---|---|---|---|
| C1 | **Public REST API** | FastAPI backend (routes contributed by U3–U9, U11) | Android app; any installed version in the field | HTTPS/JSON, OpenAPI 3.1, `/v1/` | **U2 `api-contract`** (the schema and its gates); route bodies by the contributing Unit | Yes — additive-only, NFR16 |
| C2 | **Money wire representation** | `app.money` Pydantic annotated type | every response and request schema; Kotlin `Money` serializer | In-process chokepoint + a JSON-string invariant asserted on both sides | **U1 `money-core`** (type + chokepoints); U2 asserts it schema-wide | Not versioned — permanent, TC-7/D-20 |
| C3 | **Money import boundary** | `app.money` public surface | every backend module | Ruff banned-api + import-linter test | **U1** | Permanent |
| C4 | **Lens as a data dependency** | `app.authz` lens resolvers | every route handler | FastAPI `Depends` returning a `Lens` subtype; route-enumeration test with `PUBLIC_ROUTES` | **U3** (resolvers) / **U2** (the enumeration harness) | Permanent |
| C5 | **SMS gateway** | **BulkSMSBD** (`bulksmsbd.net`), selected 2026-10-18 — see §C.4 | `SmsGateway` adapter, PU-1.4 | HTTPS, vendor-specific, wrapped in exactly one adapter | **U3 `identity-and-access`** | Vendor-owned; our adapter interface is ours |
| C6 | **FCM** | Google FCM | `PushDispatcher` adapter | FCM HTTP v1 | **U7** if built first, else U6 — the latent ownership question from `unit-of-work-dependency.md` | Vendor-owned |
| C7 | **External account-deletion web route** | FastAPI (public, non-app surface) | a browser, no app installed; Play reviewer | HTTPS HTML form + a POST route; `PUBLIC_ROUTES` member | **U11 `privacy-and-governance`** | Separately versioned — it is not `/v1/` app surface |
| C8 | **Governance manifest pair** | `app.governance` manifests | deletion endpoints, purge job, privacy-policy generator | In-process structured data, one source | **U11** | Permanent |
| C9 | **OpenAPI committed schema** | generated from the live app | ZAP baseline, Schemathesis, the client's DTOs, the schema-diff gate | Committed file + CI diff gate | **U2** | Mirrors C1 |

C2, C3, C4, C8 and C9 are in-process. They are listed as contracts because **a violation fails CI** — which is the operative meaning of "contract" in a modular monolith reviewed by one person (`team.md`: "Where a rule is important, it is mechanical").

---

## B. The public REST API contract

### B.1 Base path and versioning

- **Base path**: `/v1`. Health is `/health` (unversioned — it reports liveness and the applied Alembic revision for the smoke set, and must not move when `/v2` arrives). The external deletion route is `/account-deletion` (unversioned, §B.9).
- **Scheme**: HTTPS only. No HTTP listener.
- **Versioning scheme — additive-only within `/v1/`** [NFR16, D-26]. The binding reason is specific to this project and worth stating in the artifact: **an installed Android app cannot be forced to update**, and the audience is closed-testing teachers on low-end devices who may not update for months. A `/v2` is a last resort, not a release cadence.

  Permitted within `/v1/` without a version bump:
  - adding a new endpoint;
  - adding an **optional** request field with a server-side default;
  - adding a response field;
  - adding a value to a **server-supplied data list** (payment channels, FR6.11 — this is why the channel set is data and not a client enum);
  - relaxing a validation rule.

  Forbidden within `/v1/` (each requires `/v2` or a parallel endpoint):
  - removing or renaming any response field;
  - changing a field's type, including number↔string;
  - adding a required request field;
  - adding a value to an **enum the client switches on** (`result_state`, `fee_status`, `queue_state`, `lens`, error `code`) — see B.1.1;
  - tightening validation;
  - changing an endpoint's path or method.

- **B.1.1 — the enum problem, resolved by rule rather than by hope.** The client switches on server enums (`team.md`: the server sends `status`, the client never compares a balance). An added enum value therefore reaches a client that has no branch for it. Two rules:
  1. **Every client switch over a server enum has an `else` branch** that renders a neutral, non-blocking state and never crashes or shows an empty screen. Asserted by a Kotlin test per enum-consuming mapper.
  2. **A new enum value is still a `/v2` change for any enum whose values drive a money or authorization decision** (`fee_status`, `lens`). For purely presentational enums the `else` branch is sufficient.

- **Unknown-field tolerance** [NFR16]: the Kotlin serializer is configured `ignoreUnknownKeys = true`, asserted by a test that decodes a payload carrying an invented field. The server **never** rejects an unknown field in a request body silently — it rejects it as `ValidationError`, because silent ignoring of a misspelt field on a money write is a defect.

### B.2 The error envelope

Exactly as `team.md` specifies, with no additions to the client-visible shape:

```json
{
  "error": {
    "code": "FEE_CYCLE_ALREADY_SETTLED",
    "retryable": false,
    "message_key": "error.fee_cycle_already_settled"
  }
}
```

Three properties, restated because each is load-bearing:

- `retryable` is **server-provided**. The client never infers retryability from an HTTP status, because the client holds no business logic [TC-9, D-31].
- `code` is a stable machine value. The client switches on `code`, never on text.
- `message_key` names a `strings.xml` key. **No `message` field is ever emitted** — a server-sent English string cannot be localized, and in a Bangla-first UI [TC-15, D-43] it guarantees untranslated English error text.

**Taxonomy mapping** (the five classes from `team.md`, mapped to status and envelope):

| Class | HTTP | `retryable` | Client behaviour |
|---|---|---|---|
| `ValidationError` | 400, or 422 for schema-shape failures | `false` | Fix and resubmit; never retry as-is |
| `AuthorizationError` | 401 (no/expired token), 403 (token valid, no lens grants it) | `false` | 401 → refresh once, then re-auth. 403 → stop |
| `ConflictError` | 409 | `false` | Refetch and decide. For a queued write this is the `conflicted` state (§B.8) |
| `TransientError` | 503 | `true` | Retry with backoff |
| `FatalError` | 500 | `false` | Do not retry; alert server-side |

- **`retryable: false` on a 401 is correct, and refresh-then-replay is the one
  documented exception to it.** The two are not in conflict, but the distinction
  has to be stated or a client author reading only this table will build a client
  that cannot do what the refresh rule (§B.3) requires, while one reading only
  §B.3 will treat 401 as retryable and build a refresh loop. The rule:
  `retryable` answers **"may the client repeat this request unchanged?"** — for a
  401 the answer is genuinely no, because repeating it with the same expired
  token fails identically. What §B.3 permits is not a retry of the same request
  but **a different request first** (`POST /v1/auth/refresh`), followed by **one**
  replay with a *new* access token. Exactly one replay, only on
  `code: "ACCESS_TOKEN_EXPIRED"`, and any second 401 logs out. This keeps
  `team.md`'s "re-auth or stop; never retry" intact: re-auth is precisely what
  happens, and the original request is never repeated as-is.
- **404 is deliberately not in the taxonomy.** A resource a lens does not reach is `AuthorizationError`/403, not 404, because a 404-vs-403 distinction is an existence oracle across the owner boundary [ADR-001: teacher B's existence must not be observable]. A genuinely absent id under a lens that *would* reach it is also 403. This is a one-line rule with real teeth, and it belongs in the artifact.
- **429 is not used.** OTP rate-limit refusals are `ConflictError`/409 with a distinct `code` — `team.md` is explicit that retrying into a cost ceiling is wrong, and 429 carries a retry-after convention that invites exactly that. `retryable: false` plus a `retry_after_seconds` **hint field** (see below) is the correct shape.
- **Error extension fields.** Some errors carry a payload the client must render without computing anything. Permitted as an optional `error.details` object, typed per `code`, never interpreted beyond rendering:
  - `OTP_COOLDOWN_ACTIVE` → `{"retry_after_seconds": 42}` (FR1.13)
  - `ATTENDANCE_VERSION_CONFLICT` → the current server state (§B.8)
  - `TEACHER_NUMBER_EXISTS` → `{"confirmation_required": true}` (FR1.11)
- **Tracebacks never reach a client**, and no error log line carries a phone number, an OTP or a token [`team.md` Deployment]. Every error response carries an `X-Correlation-Id` header matching the logged id.

### B.3 Authentication

- **Access token**: JWT, **15 minutes** [NFR13], `Authorization: Bearer <jwt>`. Signed with a `kid` header; the server holds **two valid verification keys** so a signing-key rotation does not force-log-out every refresh-token holder (`team.md` Walking Skeleton).
- **Access-token claims**: `sub` (account id), `iat`, `exp`, `kid` in the header. **No role, no lens, no owner id.** Role is computed per request [TC-11, D-2] — a lens claim in a 15-minute token is a cached role by another name.
- **Refresh token**: **30 days**, opaque, rotating. Stored hashed server-side. Presenting a rotated-out token **invalidates the whole family** (`family_id` on `RefreshToken`). Reuse detection emits `REFRESH_REUSE_DETECTED` to the append-only auth audit log and returns 401 `REFRESH_TOKEN_REUSED`.
- **Refresh is a single endpoint**, `POST /v1/auth/refresh`, which returns a new access **and** a new refresh token. The client replaces both atomically; a crash between receiving and persisting means the next refresh fails as reuse, which is the correct conservative outcome.
- **Client refresh rule**: on 401 with `code: "ACCESS_TOKEN_EXPIRED"`, refresh **once** and replay the original request once. Any other 401, or a second 401, logs out. No refresh loop.

**`PUBLIC_ROUTES` — the explicit frozenset** (`team.md`: the allowlist is the important half; adding to it is a reviewable, deliberate act):

```
POST /v1/auth/otp          # OTP issue
POST /v1/auth/verify       # OTP verify
GET  /health               # liveness + applied migration revision
GET  /account-deletion     # external deletion form (U11, TC-19)
POST /account-deletion     # external deletion submit (U11, TC-19)
```

Exactly five. `POST /v1/auth/refresh` is **not** public: it authenticates by the refresh token itself and resolves no lens, so it is the one route that needs an explicit `NO_LENS_BY_DESIGN` marker rather than a `Lens` return annotation. Recorded as a sixth entry in a separate `LENS_EXEMPT_AUTHENTICATED` set so the route-enumeration test does not need a hole in its main allowlist.

### B.4 The lens contract

**Every response that carries lens-scoped data declares the lens that produced it.** A `lens` field on the response envelope, value `"teacher" | "student" | "guardian"`. This is `team.md`'s rule 5 made concrete: *"the server response is self-describing and says which lens produced it. The client renders from the response, not from the hint it sent."*

- **The client may send a lens hint** as a header, `X-Lens-Hint: teacher`. It affects **navigation and UI shaping only**. The server:
  - uses it to decide *which* lens to resolve when an account holds more than one [FR1.5, FR1.6];
  - **re-derives that lens from owned batches and enrollments on every request** [TC-11, D-2] and refuses with 403 `LENS_NOT_AVAILABLE` if the hinted lens has no data behind it [FR1.4];
  - never grants anything on the hint's say-so. The hint selects among lenses the account already has; it never creates one.
- **A missing hint** resolves to the account's single available lens, or 400 `LENS_HINT_REQUIRED` when more than one is available and the route is lens-ambiguous.
- **The teacher lens carries `owner_id` and never an account id** [ADR-001]. The lens object handed to a handler *is* the scoping value, so a handler cannot compile a query without it.
- **Teacher-facing responses expose `enrollment_id` and never `student_account_id`** [ADR-001]. Asserted schema-wide (§E.2), not per endpoint.
- **Guardian responses carry `child_enrollment_id`**, and the guardian's selected child is a path or query parameter the server validates against reachable enrollments [FR2.14, FR2.17]. Back-stack correctness across a child switch is a **privacy** case [AC9.4.2], so the response always names the child it describes.

### B.5 Money representation

- Every money value crosses the API as a **JSON string**, both directions, always [TC-7, D-20, NFR9, project.md NEVER-rule]. `"1500.00"`, two decimal places, no currency symbol, no thousands separator, no sign for positive. BDT is implicit — there is no currency field, because there is no second currency.
- **The server never emits a JSON number for a money field.** Guaranteed by U1's single Pydantic annotated type, not by per-field serializers.
- **The client rejects a JSON number loudly.** The Kotlin `Money` serializer reads only a string; a number raises. A lenient decoder that quietly coerces is the actual failure mode, and it passes a happy-path both-sides test — hence the explicit negative test obligation in `team.md`.
- **Formatting is the server's job** for locale-sensitive rendering [`Money.format(locale)`, TC-15]. Where a screen needs a formatted string the response carries **both** the canonical `amount` string and a `amount_display` string. The client renders `amount_display` and never formats `amount` itself.
- **Money fields are never used for comparison on the client.** The server sends a decision — `fee_status: "paid" | "partial" | "due" | "overdue"` — alongside the amount. `team.md` rule 1 names `if (balance > 0) "Due" else "Paid"` as the exact erosion this prevents.

### B.6 OpenAPI 3.1 fragment

Representative, not exhaustive: the envelope, Money, the auth scheme, and four endpoints — one auth, one teacher-lens read, one student/guardian write, one money read. The remainder follows by pattern.

```yaml
openapi: 3.1.0
info:
  title: ShikhokPlus API
  version: "1.0.0"
  description: >
    Additive-only within /v1. An installed Android client cannot be forced to
    update; see NFR16 and D-26. Every money value is a JSON string.
servers:
  - url: https://api.shikkhokplus.com
    description: Production

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: >
        15-minute access token. Carries sub/iat/exp only; no role and no lens
        claim, because role is computed per request (TC-11, D-2).

  parameters:
    LensHint:
      name: X-Lens-Hint
      in: header
      required: false
      description: >
        UI-shaping hint only. The server re-derives the lens from owned
        batches and enrollments on every request and refuses a hinted lens
        with no data behind it. Never trusted for authorization (D-2).
      schema:
        $ref: '#/components/schemas/Lens'

  schemas:
    Money:
      type: string
      pattern: '^[0-9]+\.[0-9]{2}$'
      examples: ["1500.00", "0.00"]
      description: >
        Fixed-point decimal BDT, always a JSON string, never a JSON number
        (TC-7, D-20). Two decimal places always present. Emitted through the
        single Pydantic annotated type in app.money; decoded in Kotlin by a
        serializer that rejects a JSON number.

    Lens:
      type: string
      enum: [teacher, student, guardian]

    ErrorClass:
      type: string
      enum: [validation, authorization, conflict, transient, fatal]

    ErrorEnvelope:
      type: object
      required: [error]
      additionalProperties: false
      properties:
        error:
          type: object
          required: [code, retryable, message_key]
          properties:
            code:
              type: string
              description: >
                Stable machine value. The client switches on this and never on
                message text.
              examples: ["FEE_CYCLE_ALREADY_SETTLED", "OTP_COOLDOWN_ACTIVE"]
            retryable:
              type: boolean
              description: >
                Server-provided. The client never infers retryability from the
                HTTP status, because the client holds no business logic (TC-9).
            message_key:
              type: string
              description: >
                Names a strings.xml key. No English message is ever sent; a
                server-authored string cannot be localized (TC-15, D-43).
              examples: ["error.fee_cycle_already_settled"]
            error_class:
              $ref: '#/components/schemas/ErrorClass'
            details:
              type: object
              description: >
                Optional, typed per code. Rendered, never interpreted.
              additionalProperties: true

    FeeStatus:
      type: string
      enum: [paid, partial, due, overdue, waived]
      description: >
        Server-computed. The client switches on this and never compares an
        amount (team.md, layer boundaries rule 1).

    QueueConflict:
      type: object
      required: [expected_version, current_version, current_state]
      properties:
        expected_version:
          type: integer
        current_version:
          type: integer
        current_state:
          type: object
          description: >
            The server's current roster, rendered side by side with what the
            teacher recorded offline (FR11.5).

  responses:
    Unauthorized:
      description: No valid access token, or the token expired.
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorEnvelope' }
    Forbidden:
      description: >
        The resolved lens does not reach this resource. Also returned for a
        resource that does not exist under a lens that would reach it: a
        404/403 distinction would be an existence oracle across the owner
        boundary (ADR-001).
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorEnvelope' }
    Conflict:
      description: Valid request, current state forbids it. Never retry as-is.
      content:
        application/json:
          schema: { $ref: '#/components/schemas/ErrorEnvelope' }

security:
  - bearerAuth: []

paths:

  # ---- 1. Auth (public) ----------------------------------------------
  /v1/auth/otp:
    post:
      operationId: issueOtp
      summary: Issue an OTP to a phone number.
      security: []
      description: >
        Public (PUBLIC_ROUTES). The response is byte-identical whether or not
        the number has an account, and the unknown-number path performs the
        same hash work rather than returning early (NFR12, structural
        assertion). A ceiling breach is a ConflictError, never a
        TransientError: retrying into a cost ceiling is exactly wrong.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [phone]
              additionalProperties: false
              properties:
                phone:
                  type: string
                  pattern: '^01[3-9][0-9]{8}$'
      responses:
        '202':
          description: >
            Accepted for delivery. Never confirms that a number exists, and
            never confirms that the SMS was delivered (the gateway send is
            attempted once and a timeout is recorded as unknown).
          content:
            application/json:
              schema:
                type: object
                required: [cooldown_seconds]
                properties:
                  cooldown_seconds:
                    type: integer
                    description: Before a resend is offered (FR1.13).
        '409':
          description: >
            Rate limit or SMS budget ceiling. Distinct codes:
            OTP_RATE_LIMITED_NUMBER, OTP_RATE_LIMITED_IP,
            SMS_BUDGET_CEILING_REACHED. retryable is false in all three.
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorEnvelope' }

  # ---- 2. Teacher-lens read ------------------------------------------
  /v1/batches/{batch_id}/roster:
    get:
      operationId: getBatchRoster
      summary: The enrollments in one batch, teacher lens.
      parameters:
        - $ref: '#/components/parameters/LensHint'
        - name: batch_id
          in: path
          required: true
          schema: { type: string, format: uuid }
      description: >
        Teacher lens only, rooted at owner_id (ADR-001). Carries
        enrollment_id and never student_account_id, and no profile field.
        Both exclusions are asserted schema-wide by U2, not per endpoint.
      responses:
        '200':
          description: The roster, in the order the server decided.
          content:
            application/json:
              schema:
                type: object
                required: [lens, batch_id, enrollments]
                properties:
                  lens:
                    $ref: '#/components/schemas/Lens'
                  batch_id: { type: string, format: uuid }
                  enrollments:
                    type: array
                    description: >
                      Server-ordered. The client may not filter or re-sort a
                      domain list (team.md, layer boundaries rule 2).
                    items:
                      type: object
                      required: [enrollment_id, display_name, enrollment_state]
                      properties:
                        enrollment_id: { type: string, format: uuid }
                        display_name:
                          type: string
                          description: Teacher-authored, never the account's own name.
                        enrollment_state:
                          type: string
                          enum: [dormant, active, inactive]
                        inactive_from:
                          type: [string, 'null']
                          format: date
                        fee_amount:
                          $ref: '#/components/schemas/Money'
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/Forbidden' }

  # ---- 3. Student / guardian write -----------------------------------
  /v1/payment-claims:
    post:
      operationId: submitPaymentClaim
      summary: Submit a payment claim. Identical form in both lenses (FR6.1).
      parameters:
        - $ref: '#/components/parameters/LensHint'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [batch_id, channel, transaction_id, claimed_amount, client_mutation_id]
              additionalProperties: false
              properties:
                batch_id:
                  type: string
                  format: uuid
                  description: >
                    Resolves to the enrollment, which resolves to the open fee
                    cycle (FR6.2). The client never names the cycle.
                channel:
                  type: string
                  description: >
                    One value from the server-supplied channel list (FR6.11).
                    Not a client enum: adding a channel is a data change, not
                    an app release.
                transaction_id: { type: string, maxLength: 64 }
                claimed_amount: { $ref: '#/components/schemas/Money' }
                client_mutation_id:
                  type: string
                  format: uuid
                  description: >
                    Client-generated, unique-constrained server-side. A replay
                    returns 200 with the original claim, never a duplicate.
      responses:
        '201':
          description: Claim recorded.
          content:
            application/json:
              schema: { $ref: '#/components/schemas/PaymentClaimView' }
        '200':
          description: >
            Idempotent replay. Same client_mutation_id, same stored claim,
            returned unchanged.
          content:
            application/json:
              schema: { $ref: '#/components/schemas/PaymentClaimView' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/Forbidden' }
        '409':
          description: >
            No open fee cycle for that enrollment, or a settled cycle.
            retryable false.
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorEnvelope' }

  # ---- 4. Money read --------------------------------------------------
  /v1/enrollments/{enrollment_id}/fee-cycles:
    get:
      operationId: listFeeCycles
      summary: Fee cycles for one enrollment, with server-computed status.
      parameters:
        - $ref: '#/components/parameters/LensHint'
        - name: enrollment_id
          in: path
          required: true
          schema: { type: string, format: uuid }
      description: >
        Reachable in all three lenses, each rooted differently: teacher by
        owner_id, student by own enrollment, guardian by reachable child
        enrollment. Every amount is a JSON string; every status is computed
        server-side so the client never compares a balance.
      responses:
        '200':
          description: Cycles, newest first, in the order the server decided.
          content:
            application/json:
              schema:
                type: object
                required: [lens, enrollment_id, cycles]
                properties:
                  lens: { $ref: '#/components/schemas/Lens' }
                  enrollment_id: { type: string, format: uuid }
                  cycles:
                    type: array
                    items:
                      type: object
                      required:
                        - fee_cycle_id
                        - period
                        - due_date
                        - charged
                        - outstanding
                        - fee_status
                      properties:
                        fee_cycle_id: { type: string, format: uuid }
                        period:
                          type: string
                          pattern: '^[0-9]{4}-[0-9]{2}$'
                        due_date:
                          type: string
                          format: date
                          description: >
                            Clamped to the last day of a short month (FR5.2).
                            Computed server-side; the client never clamps.
                        charged:     { $ref: '#/components/schemas/Money' }
                        received:    { $ref: '#/components/schemas/Money' }
                        forgiven:    { $ref: '#/components/schemas/Money' }
                        carried_in:  { $ref: '#/components/schemas/Money' }
                        outstanding: { $ref: '#/components/schemas/Money' }
                        outstanding_display:
                          type: string
                          description: >
                            Locale-formatted by the server (Money.format).
                            The client renders this and never formats the
                            canonical value itself.
                        fee_status:  { $ref: '#/components/schemas/FeeStatus' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/Forbidden' }
```

(`PaymentClaimView` is referenced and not expanded; it follows the pattern — `claim_id`, `fee_cycle_id`, `channel`, `transaction_id`, `claimed_amount` as `Money`, `status`, `submitted_at`.)

### B.7 Idempotency

- **`client_mutation_id`** — a client-generated UUIDv4 — is **required** on exactly the writes where a replay is plausible and a duplicate is expensive:
  - `POST /v1/sessions/{id}/attendance` (the queued mid-class roster — AC9.2.4 double-submit and the reconnect replay);
  - `PUT /v1/sessions/{id}/topic` (the other queued path);
  - `POST /v1/payment-claims` (double-tap on a money write);
  - `POST /v1/payment-claims/{id}/verification` (double-tap on the teacher's approve).
- **It is not required elsewhere.** Adding it to every write is cost without benefit: an interactive write that fails is retried by the user, and FR11.4 already settles interactive concurrency as last-write-wins with correction history. Stating the four explicitly is what makes the rule reviewable.
- **Server behaviour on replay**: the id carries a **unique constraint** (`client_mutation_id` already exists on `Attendance` and `PaymentClaim` per `components.md`). On a duplicate the server **returns the original stored result with `200`** — not `201`, not an error, and never a second write. The original's `created_at` is unchanged, so a replay is observably a replay.
- **Scope**: the uniqueness is scoped per account per endpoint, so two clients cannot collide, and a malicious replay of someone else's id is an `AuthorizationError`, not a silent success.
- **Not an idempotency key for reads.** `GET` is idempotent by method.
- **The fee-cycle generation job does not use `client_mutation_id`.** Its idempotency is the `(enrollment_id, period)` unique constraint with `ON CONFLICT DO NOTHING` [TC-12, D-21, project.md ALWAYS-rule] — a database constraint, never an application guard, and tested with overlapping concurrent generations.

### B.8 Concurrency — the queued write contract

Per FR11.4, FR11.5, NFR5.1 and ADR-006, and the split is the point:

- **Interactive writes** (online, sent immediately): last-write-wins per field, correction history records actor and time. **No version is sent and no conflict is possible.** The client sends no `If-Match` and the server requires none.
- **Queued writes** (the mid-class path only — attendance and topic log, FR3.6): the write **carries the version it was composed against**.

**Mechanism.** The version travels in the **request body**, not in an `If-Match` header. Reason: the queued write is composed offline, persisted in the client's queue, and replayed hours later by a sync worker; a body field survives serialization into the queue table naturally, whereas a header is a second thing the queue has to remember to carry and the first thing a retry wrapper drops.

```jsonc
// POST /v1/sessions/{session_id}/attendance
{
  "base_attendance_version": 7,
  "client_mutation_id": "…uuid…",
  "composed_at": "2026-10-18T10:15:00+06:00",
  "entries": [
    { "enrollment_id": "…", "present": true },
    { "enrollment_id": "…", "present": false }
  ]
}
```

- The roster is **one atomic write**, never one write per student [AC3.1.5]. That is why per-field last-write-wins cannot apply here — field granularity does not exist.
- **On match**: the server applies the whole roster, increments `attendance_version`, returns `200` with the new version. The client moves the queued item to `confirmed`.
- **On mismatch**: the server **refuses** with `409` `ATTENDANCE_VERSION_CONFLICT`, `retryable: false`, and `error.details` carrying a `QueueConflict`:

```json
{
  "error": {
    "code": "ATTENDANCE_VERSION_CONFLICT",
    "retryable": false,
    "message_key": "error.attendance_version_conflict",
    "details": {
      "expected_version": 7,
      "current_version": 9,
      "current_state": { "entries": [ { "enrollment_id": "…", "present": false } ] }
    }
  }
}
```

  The client moves the item to **`conflicted`** — the fourth NFR5.1 state, distinct from `failed` because `failed` means "try again" and this one means "look at what changed". The offline entry is **preserved** until the teacher chooses re-apply or discard [FR11.5].
- **Re-apply** is an ordinary new queued write carrying the *current* version and a **new** `client_mutation_id` — because it is a new decision by the teacher, not a replay of the old one. Reusing the old id would make re-apply an idempotent no-op, which is the exact opposite of what the teacher asked for. This is a non-obvious consequence worth stating in the artifact.
- **Never merged, never silently applied, never silently discarded** [ADR-006]. Merging would mean inventing a rule for a student the two rosters disagree about, which no layer is authorized to invent.
- **The four queue states** `queued | confirmed | failed | conflicted` are a **client-side** vocabulary. They do not appear in any response schema; the server returns `200` or `409` and the client derives the state. Stating this prevents someone adding a `queue_state` field to the API that the server cannot possibly know.

### B.9 The external deletion route (TC-19)

- **Path**: `/account-deletion`, **not under `/v1/`**. It is a browser surface, not app surface, and it versions on its own schedule. Play reviewers and guardians reach it by URL with no app installed.
- `GET` returns an HTML form (Bangla and English); `POST` initiates deletion.
- **Authentication is OTP**, the same mechanism and the same abuse controls as `/v1/auth/otp` — a deletion route authenticated by phone number alone is an account-destruction oracle. It consumes the **same per-number and per-IP ceilings** and the same `purpose` budget (see §C), so it cannot be used to drain the SMS budget around the app's limits.
- **Idempotent** [FR11.3]: a second request for an already-deleted account succeeds with no further effect and no disclosure that the account was already gone.
- **The confirmation copy names what is retained** [RC-5, FR11.1], generated from the Governance disposition manifest and not written independently.
- Both deletion paths are **release-blocking V1 deliverables** [D-41, RC-4, RC-5], each with a test asserting that deletion removes what the Data Safety form claims and retains only what the privacy policy discloses.

---

## C. The SMS gateway contract

**One adapter, one call site** [PU-1.4]. No other module may reach the gateway; enforced by the same import-boundary mechanism as `app.money`.

### C.1 Adapter interface

```python
class SmsPurpose(StrEnum):
    OTP = "otp"


class SendOutcome(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"
    BUDGET_REFUSED = "budget_refused"


class SmsGateway(Protocol):
    def send(
        self,
        phone: str,
        body: str,
        purpose: SmsPurpose,
        correlation_id: str,
    ) -> SendOutcome:
        ...
```

Three properties of the signature, each deliberate:

- **`purpose` is required, not defaulted** [NFR12.1]. A default would let a second consumer arrive without anyone choosing its ceiling. V1 has exactly one value, `otp`; the enum exists so the second one is a data change rather than a redesign of the one control protecting the project's wallet.
- **The return is an outcome, not `None` and not a bool.** `unknown` cannot be expressed by a bool, and `unknown` is the whole point (§C.3).
- **No vendor type crosses the boundary.** The adapter returns our enum, never the gateway's response object, so a vendor swap touches one file.

### C.2 Per-purpose budget

- Each `SmsPurpose` carries its **own daily ceiling and its own alert**. There is no global-only ceiling [NFR12.1, D-33].
- Beneath each purpose ceiling sit the **per-number and per-IP-prefix sub-ceilings** (`team.md`: a global-only ceiling converts a financial attack into a total lockout of every legitimate teacher for the rest of the day; the breaker must degrade rather than cliff-edge).
- **The ceiling is checked before the call**, never after. A breach is a **`ConflictError` → 409**, never a `TransientError` — retrying into a cost ceiling is exactly wrong.
- **Counters are datastore-backed, not per-process.** A per-process dictionary passes every test and silently stops working with two Uvicorn workers, which Phase 1 has. This is a correctness requirement, not a hardening step.
- The ceiling, its sub-ceilings and its alert must be **live and verified in staging** before the auth slice reaches production.
- **`SmsPurpose` has exactly one value in V1 (`otp`), so the per-purpose design
  is verified by signature review rather than by observable behaviour until a
  second purpose exists.** Worth stating plainly, because a one-value enum looks
  like speculative generality and the obvious "simplification" is to drop the
  parameter. That would be the wrong call: NFR12.1 exists precisely so a later
  teacher-triggered consumer cannot make one ceiling arbitrate between an abuse
  burst and a legitimate bulk action — a shared ceiling either lets reminders
  exhaust the OTP budget and lock teachers out of login, or throttles reminders
  unpredictably. The parameter costs one argument now; retrofitting it means
  re-reasoning about the one control protecting the project's wallet while a
  second consumer is already live. The first test that genuinely exercises the
  separation arrives with that second purpose.

### C.3 The send rule — the important part

> **A send is attempted exactly once. There is no automatic retry, at any layer.**

- **A timeout or an ambiguous gateway response is recorded as `UNKNOWN`, never as `FAILED`** — because the SMS may well have been delivered, and `failed` invites a retry that double-charges and double-messages. Automatic retry at this boundary is a bug, not resilience.
- **The user-facing path for every non-`SENT` outcome is "request a new OTP"** after the cooldown [FR1.13], a deliberate user action. It is presented as a **delivery failure, never as an incorrect code**.
- **Every outcome, including `UNKNOWN` and `BUDGET_REFUSED`, consumes budget**, because an `UNKNOWN` may have cost money. Counting only `SENT` would let a flapping gateway spend without bound.
- **Gateway request bodies are never logged at any level**, because the call carries a phone number and the OTP itself. The OTP never appears in any log line. Each send logs `(purpose, outcome, correlation_id)` and nothing else.
- **Non-production environments hold the gateway's test or sandbox credentials**, so a staging run can never spend real money or message a real teacher. CI stubs the gateway entirely — the blocking suite needs no secret to run locally.

### C.4 The selected vendor — BulkSMSBD (added 2026-10-18, closing OQ-3)

**The vendor is BulkSMSBD** (`bulksmsbd.net`), selected by the human. The
§C.1 adapter interface is unchanged — that is what being vendor-neutral
bought — but six vendor behaviours below are **binding on the
implementation** and two of them are not optional judgement calls. Every
claim marked *verified* was probed directly against the live endpoint on
2026-10-18 **using an invalid API key only**; no SMS was sent and no
credentials were used.

**The call:**

```
POST https://bulksmsbd.net/api/smsapi
  api_key, senderid, number, message        # form/query parameters
```

**C.4.1 — Success is `response_code == 202` and nothing else.** *(verified)*

An application-level failure returns **HTTP 200** with the error in the body:

```
$ curl -i ".../api/smsapi?api_key=INVALID&..."
HTTP/1.1 200 OK
{"response_code":1011,"success_message":"","error_message":"user id not found in this INVALID key"}
```

So `raise_for_status()` is worthless as a success check here. A non-2xx
status means a transport problem — proxy, DNS, a typo'd path — and never an
application rejection. **The adapter determines `SENT` solely from
`response_code == 202`.**

The field is **`response_code`** (an integer), not `code`. Named explicitly
because the most-installed Python client for this gateway parses `code`,
and its unit tests mock `{'code': 202}` — so the tests pass against a
fiction while the library would treat every real response, success and
failure alike, as unrecognised. That is precisely the defect `team.md`
rejects: *"tests that always pass regardless of implementation are defects
in their own right."* **Do not copy that parsing.**

**C.4.2 — HTTPS is mandatory and enforced in code, not in configuration.**
*(verified)*

The certificate is valid (Let's Encrypt, TLS 1.2/1.3, hostname matches).
But **plain HTTP serves the same API with no redirect and no HSTS**:

```
$ curl -o /dev/null -w "%{http_code} redirect='%{redirect_url}'" "http://bulksmsbd.net/api/smsapi?..."
200 redirect=''
```

A misconfigured `http://` therefore ships **the phone number and the OTP in
cleartext and succeeds silently** — nothing fails, warns or logs. Under
[RC-1, RC-2, RC-3] that is a privacy failure on children's-adjacent data,
so per `team.md`'s *"where a rule is important, it is mechanical"* the
scheme is **not a configuration value**: the adapter asserts
`urlparse(base_url).scheme == "https"` at construction and raises
otherwise, never exposes a TLS-verification toggle, and carries a test
asserting the resolved URL starts with `https://`.

**C.4.3 — `error_message` echoes the API key back in plaintext.**
*(verified)* `"user id not found in this <key> key"`. `team.md` forbids
logging secrets and forbids logging gateway request bodies. The adapter
therefore **logs `response_code` only, never `error_message`**, and the
existing rule that each send logs `(purpose, outcome, correlation_id)` and
nothing else already covers it — stated here because this is a live
credential-leak path into the logs, not a hypothetical one.

**C.4.4 — Response codes mapped onto the taxonomy.**

| Code(s) | Class | Outcome |
|---|---|---|
| 202 | — | `SENT` |
| 1001 | `ValidationError` | `FAILED` — the number is wrong |
| 1003 | `ValidationError` | `FAILED` — a bug in our request |
| 1011, 1018, 1031, 1032 | `AuthorizationError` | `FAILED` + alert — account or IP problem |
| 1006, 1007 | `ConflictError` | `BUDGET_REFUSED` — **never** `TransientError`; retrying into an empty balance is the same error as retrying into a cost ceiling |
| 1012 | `ValidationError` | `FAILED` — masking sender requires a Bangla body (C.4.6) |
| 1002, 1013–1017, 1019–1021 | `FatalError` | `FAILED` + alert — vendor provisioning |
| **1005** | — | **`UNKNOWN`**, not `TransientError` |
| unrecognised | `FatalError` | `FAILED` + alert |

**1005 ("Internal Error") is `UNKNOWN`, and so is a timeout**, because the
gateway offers no delivery report and no message id (C.4.5): the SMS may
have been sent and billed. The published code table is **not closed** —
three codes appear in community sources but not the vendor's table — so an
unrecognised code is a failure of unknown class rather than evidence the
enumeration is complete.

**C.4.5 — There is no delivery report and no message id.** *(verified
negative: nine plausible endpoint names all 404)*

`202` means **submitted to the gateway**, permanently and finally. Whether
the handset received it is unknowable at any price on this API. This makes
§C.3's existing design *mandatory rather than cautious*: there is no
`delivered` state to model, the states are `submitted` / `rejected` /
`unknown`, and user-initiated "request a new OTP" is the only recovery.

`GET /api/getBalanceApi?api_key=...` exists and is the **only** observability
hook into the gateway — worth polling and alerting on, since it catches both
"about to run out" and, indirectly, "something is burning SMS", feeding
[D-33]'s circuit breaker.

**C.4.6 — Two open vendor questions that need answers before PU-1.**

**Both answered by the human on 2026-10-18. Neither is open.**

**OQ-3a — there is no sandbox.** So `team.md`'s rule that *"non-production
environments hold the gateway's test or sandbox credentials, so a staging
run can never spend real money or message a real teacher"* **cannot hold as
written**, because the mechanism it names does not exist. The practice is
not weakened; it is **satisfied by a different mechanism**, and the
distinction matters because the property it protects still holds:

- **Every non-production environment runs a null adapter** behind the §C.1
  `SmsGateway` protocol. It records the intended send — purpose, outcome,
  correlation id, never the body — returns `SENT`, and makes no network
  call. A staging run therefore still **cannot spend money and cannot
  message a real person**, which is the property the practice exists to
  guarantee.
- **Selection is by explicit configuration, and the default is the null
  adapter.** The real adapter is constructed only when a setting names it,
  so a missing or misspelt value fails *toward not sending* rather than
  toward spending real money. Same reasoning as C.4.2's scheme enforcement:
  the dangerous value is never the default.
- **One consequence is recorded rather than papered over.** `team.md` also
  requires the SMS ceiling to be *"live and verified in staging before the
  auth slice reaches production"*. Against a null adapter that verifies
  **our ceiling logic** — which is entirely our own code, and for which a
  stub is the correct test double — but it does **not** exercise the real
  gateway. The gateway leg is therefore verified exactly once, at the B3
  skeleton checkpoint, against production credentials with a single real
  send to the developer's own number. That is the only place real money is
  spent before launch, and it is a bounded, deliberate exception.
- **`team.md`'s wording should be corrected** at a future learnings gate to
  read "test credentials **or a null adapter**", since the present phrasing
  names a mechanism this vendor does not offer. Flagged, not silently
  reinterpreted.

**OQ-3b — code 1012 does not apply to our OTP traffic.** The masking
Bangla-body rule is not enforced for this message class, which removes the
3–4× cost multiplier and resolves the tension favourably on both counts:

- The OTP body is **English and GSM-7**, so **160 characters per segment**
  rather than 70. C.4.7's length test still applies and still matters — the
  SMS Retriever app hash [TC-5] still consumes 12 characters — but the
  budget it polices is more than twice as large, and a single-segment OTP
  is comfortable rather than tight.
- A **masking sender ID stays available** without forcing a Bangla body, so
  the teacher sees a branded sender rather than an unfamiliar number. That
  is the better trust signal on an OTP, which matters for a product whose
  first screen is a login.
- **This does not change the Bangla-first UI** [TC-15, D-43]. The OTP *SMS*
  is one English message from a gateway; every in-app string stays
  localized. Stated so the two are not later conflated.
- **[D-33]'s ceiling can now be calibrated** against the cheaper arithmetic,
  which was the blocking reason this question existed.

**C.4.7 — The OTP message length is a tested budget constraint.**

A single Bangla character forces the whole message to UCS-2, cutting
capacity from 160 characters to **70**. Adding a brand name, an expiry
notice, or the **11-character SMS Retriever app hash** [TC-5] can push past
70 silently and **double the per-OTP cost with no error and no signal**.

So U3 carries a test asserting the rendered OTP template, in both `bn` and
`en`, encodes to ≤70 UCS-2 / ≤160 GSM-7 characters **including the app
hash**. Mechanical, cheap, and it catches a 2× cost regression at commit
time rather than on the invoice.

**C.4.8 — Timeouts are explicit and retry stays forbidden.**

Observed latency against auth-failing requests was ~320–380 ms, but those
short-circuit before any carrier handoff, so a real send will be slower and
these numbers must not be used to size a timeout. The adapter sets an
explicit **connect timeout (~5 s)** and **read timeout (~10–15 s)** — never
a library default and never unbounded, because an unbounded gateway call
blocks a Uvicorn worker, and on a 2 GB Lightsail instance with few workers
that is a self-inflicted availability incident.

No automatic retry, at any layer, unchanged from §C.3. There is no
idempotency key and no message id, so a retry risks double-sending and
double-billing.

**C.4.9 — IP whitelisting may apply.** Code 1032 ("IP not whitelisted")
appears in community sources though not the vendor's published table. If
enforced on our account, the Lightsail instance needs a **static egress
IP** attached for both staging and production, and any later move to
multiple instances or a NAT gateway would break sends with what looks like
an auth failure. 1032 is non-retryable and alerting: retrying from the same
IP never succeeds.

---

## D. The FCM contract

**One adapter, owned by whichever of U6/U7 is built first** (the latent ownership question flagged in `unit-of-work-dependency.md`; the other reuses it). V1 triggers: fee-due reminder [FR10.1, FR10.4] and entered marks [FR10.1].

```python
class PushDispatcher(Protocol):
    def dispatch(
        self,
        account_id: UUID,
        notification: NotificationPayload,
        correlation_id: str,
    ) -> None:
        ...
```

The contract, in five rules:

- **Best-effort.** A failed push **never** fails the operation that triggered it. This is the **stated exception** to "silent failures are not acceptable" (`construction.md`), and `team.md` names it explicitly so it is not implemented wrongly.
- **Post-commit, outside the request transaction.** Dispatch happens after the transaction commits, never inside it. A push for a write that then rolled back is worse than no push.
- **Failure is logged and not surfaced.** No error envelope, no client-visible state, no retry queue in V1.
- **`UNREGISTERED` is not an error — it deletes the stored `DeviceToken`** [D-42]. It is the token-lifecycle signal, and treating it as an error is how a dead-token table grows forever.
- **No device or advertising identifier is ever transmitted** [TC-3, NFR11, project.md NEVER-rule]. FCM uses app-instance-scoped installation ids only.

**The reminder event is written regardless of push outcome** [FR10.3, FR10.4]: `(enrollment, fee_cycle, channel, sent_at, sent_by, outcome)`. The teacher-facing "reminded 3 days ago" / "Never reminded" state derives from the latest event per `(enrollment, period)`. A failed push produces an event with a failure `outcome` — which is precisely why it is an event and not a boolean.

---

## E. In-process contracts worth pinning

### E.1 `money-core`'s public surface (U1)

**What callers may do** — the complete public surface of `app.money`:

| Member | Contract |
|---|---|
| `Money(value: Decimal \| str \| int)` | Quantized to 2dp at construction. **Construction from a `float` raises**, and `Decimal(<float>)` is banned (Ruff `RUF032` plus the type) |
| `Money.ZERO` | The zero constant. Callers write `balance > Money.ZERO`, never `balance > 0` |
| `__add__`, `__sub__` | Accept **only** `Money`. `money + 5` is a mypy error |
| `apply_rate(rate: Decimal) -> Money` | The only multiplication. Named so the caller states intent; rounds with the module's single mode |
| `allocate(n: int) -> list[Money]` | The only division-shaped operation; the returned list sums **exactly** to the original by remainder distribution |
| `Money.sum(iterable) -> Money` | Zero identity. Exists because a cross-batch dues total is the operation most likely to be written as Python `sum()` with a `0` start |
| `is_zero()`, `is_positive()` | Sign-convention knowledge lives on the type |
| `format(locale) -> str` | The server is the only thing deciding digit rendering and separator placement under Bangla locale [TC-15, TC-9] |
| `MoneyField` (Pydantic annotated type) | The **single** serialization chokepoint for the API. Not a per-field `field_serializer` — that is how one endpoint eventually emits a number |
| `MoneyType` (SQLAlchemy `TypeDecorator`) | The **single** storage chokepoint, mapping to `NUMERIC(12,2)`. Without it, one model eventually declares `Numeric(10,2)` or a `Float` |
| `ROUND_HALF_UP` | Declared once as a module constant. Not Python's `Decimal` default (`ROUND_HALF_EVEN`), which is wrong for consumer-facing BDT |

**What callers may not do:**

- No `float()`, no `int()` — neither is defined.
- No `__mul__`, no `__truediv__` — neither is defined.
- No raw `decimal` import outside `app/money/**` (Ruff `flake8-tidy-imports` banned-api, re-permitted by `per-file-ignores` inside).
- No money arithmetic outside the module, including in a route handler or in Kotlin [project.md ALWAYS-rule].

**The import direction is itself a contract.** `app.money` imports nothing from `app.api`, `app.db`, `app.repositories`, `app.authz` or `app.schemas`. Asserted by an import-linter test — the one that catches the *plausible* violation: someone giving `app.money` a `Session` "just to look up the batch default fee", which destroys the testability and the mypy story in one commit.

**Kotlin counterpart**: `@JvmInline value class Money(val amount: BigDecimal)` with a kotlinx serializer that reads **only** a JSON string and **rejects a JSON number loudly**. `Double` and `Float` are banned package-wide in `core/model` by detekt as a backstop.

### E.2 `api-contract`'s CI-enforced guarantees (U2)

Four gates. Each blocks the merge.

1. **Schema-diff gate.** The committed OpenAPI 3.1 file must match the one generated from the live app. CI fails on divergence. *A stale committed schema is worse than none, because the contract tests then pass against fiction.* The schema is committed so a contract change shows up as a reviewable diff [D-26].

2. **Route enumeration with `PUBLIC_ROUTES`.** Every route resolves a lens; the allowlist (§B.3) is an explicit `frozenset` of exactly five entries, plus the separate `LENS_EXEMPT_AUTHENTICATED` set holding only `/v1/auth/refresh`. The check:
   - walks `route.dependant` **recursively**, because a lens may be nested in a composed dependency;
   - matches on the dependency's **return annotation being a `Lens` subtype**, never on the function's name — name-matching is how this check gets defeated by a rename;
   - runs against the **real app object at collection time**, so a new un-lensed endpoint reddens CI on the commit that adds it.

3. **Schema-wide privacy assertions.** Iterating the generated OpenAPI rather than per-endpoint tests, because per-endpoint tests fail to cover the endpoint added in U9 after everyone stopped thinking about it. Two forbidden field sets:
   - **no teacher-lens response schema contains any owner-private profile field** [TC-13, D-7];
   - **no teacher-facing response schema contains `student_account_id` or any account id** [ADR-001].
   Both are one mechanism with two field sets — ADR-001 explicitly chose "one more forbidden field set rather than a new mechanism".

4. **Money-as-string, asserted on both sides.** The backend never emits a JSON number for a money field (schema-level: every money property is `type: string` with the `Money` pattern); the client rejects a JSON number (Kotlin negative test). Schemathesis covers conformance — unexpected 500s, type and required-field drift, auth present on every route — and **never counts as privacy coverage**, because a response wrongly including profile fields is perfectly conformant.

### E.3 The `Payments -> Fees` ledger contract (ADR-007)

Not a wire contract, but worth pinning because it is the money boundary inside the monolith:

- **No component except `Fees` writes `LedgerEntry`** [components.md invariant 3]. Enforced by an import-boundary rule.
- `Payments` appends entries **through Fees' Python API**, never by inserting a row.
- The call is `Fees.record_verification(claim, approved_amount, disposition)`, which appends the entries and returns them. `Payments` does not choose the entry kinds — an over-approval becoming a `credit_grant` rather than a `receipt` [FR5.9] is Fees' decision, so the ledger identity has exactly one author.
- **One transaction per request**, committed by the endpoint and never by a repository method — or a partial money write becomes possible. The "approve and append" atomicity spanning a component boundary is ADR-007's named cost and is paid by the single request transaction.

### E.4 The Governance manifest contract (U11)

- **Two manifests as structured data**: a deletion disposition per table, and a retention period per data class.
- **Three consumers read one source**: the two deletion endpoints, the scheduled purge, and the privacy-policy generator. That single source is what stops the published policy drifting from the implementation.
- **The gate**: one test iterates the live schema and asserts **every table appears in both manifests**. A table added in a later Bolt reddens CI until someone decides its disposition. The test is vacuous until the last table exists, which is why U11 depends on seven Units.
- **The privacy-policy text is generated from the dispositions**, never written independently. A privacy policy that contradicts the implementation is worse than a vague one.

---

## F. Ownership and change policy

### F.1 Ownership

| Contract | Spec owner | Implementation owners |
|---|---|---|
| C1 public REST API (the schema) | **U2 `api-contract`** | each contributing Unit writes its routes; U2 owns the committed schema and all four gates |
| C2/C3 Money wire + import boundary | **U1 `money-core`** | every money-carrying Unit consumes; none may extend |
| C4 Lens | **U3** (resolvers) and **U2** (enumeration harness) | every `service` Unit |
| C5 SMS gateway adapter | **U3 `identity-and-access`** | sole call site |
| C6 FCM adapter | **U7 if built first, else U6** — must be recorded at Delivery Planning rather than left latent | the other Unit reuses, never reimplements |
| C7 external deletion route | **U11** | — |
| C8 Governance manifests | **U11** | three consumers |
| C9 committed OpenAPI file | **U2** | regenerated by whichever Unit changes a route; U2's gate catches a stale commit |

With one developer, "ownership" means **which Unit's definition of done includes the contract's gate**, not which team to negotiate with. That is the useful reading here and the artifact should say so.

### F.2 How a breaking change is agreed

There is no second team, so the process is a **sequence of mechanical facts, not an approval chain**:

1. The schema-diff gate fails. CI names the diff; this is the detection step and it is automatic.
2. The change is classified against §B.1's two lists. If it is on the forbidden list, it is breaking.
3. A breaking change requires **one of**:
   - a parallel additive endpoint under `/v1/` with the old one kept and marked `deprecated: true` in OpenAPI (preferred — this is almost always available);
   - a `/v2/` path (last resort, and carrying the full cost of maintaining two surfaces on a USD 50/month budget);
   - a **field-level additive migration**: new field added, both populated for a release, old field removed only after Play Console confirms no active installs below the version that stopped reading it.
4. The decision and its rationale are recorded in the commit touching the committed schema, which is where the diff lives.
5. **The old surface is never removed while any install in the field reads it.** For a closed-testing audience of a dozen teachers that is checkable in the Play Console; at launch it is not, so the removal bar rises rather than falls.

### F.3 Why additive-only matters here specifically

Stated plainly, because "additive-only" is a slogan in most projects and a hard constraint in this one:

- **An installed Android app cannot be forced to update** [D-26, NFR16]. There is no forced-upgrade mechanism in V1 and no budget to build one.
- **The audience makes it worse.** Low-end devices on `minSdk` 24, possibly metered data, in a market where auto-update is often disabled to save bandwidth. The realistic update lag is months, not days.
- **The surface in the field holds money and children's data.** A client that fails to parse a fee response is not a cosmetic bug — it is a teacher who cannot collect this month and a guardian who cannot see what is owed.
- **The payment channel list is the worked example** [FR6.11]: it is server-supplied data precisely so that adding Nagad's successor is a database row, not a release teachers must install. The same reasoning generalizes to every list the client renders.
- **Consequence for design**: prefer server-supplied data over client enums; prefer a server-computed decision over a value the client interprets; give every client-side enum switch an `else` branch. All three are already `team.md` rules — additive-only is the reason they exist, not an independent rule.

---

## G. Open questions

| # | Question | Blocks | Why it is not decided here |
|---|---|---|---|
| OQ-1 | **Does `PaymentClaim.transaction_id` survive the claimant's deletion?** It is student/guardian-authored (so FR11.1 says remove) and simultaneously the teacher's only evidence of a verified payment (so the business-record argument says retain). | **U11** disposition manifest; the privacy-policy text generated from it; **U8**'s payment-history response schema, which must know whether the field can be null post-deletion | A product and legal judgement, carried in from Domain Design. The contract can express either answer; it cannot choose |
| OQ-2 | **FR8.3's collection-rate definition is annotated open to correction**, and AC8.3.4's rule that a credit counts in the period whose charge it settles postdates it. | **U9** analytics response schema and its field semantics; **U1**'s property test, which should be extended to cover the credit rule | A requirements question. Shipping a `collection_rate` field whose arithmetic is under revision would pin the wrong number into a client in the field |
| ~~OQ-3~~ | **DECIDED 2026-10-18 — the vendor is BulkSMSBD.** See §C.4, which records six binding implementation behaviours probed against the live endpoint. The §C.1 interface is unchanged, which is what vendor-neutrality bought. | — | Resolved by the human |
| ~~OQ-3a~~ | **ANSWERED 2026-10-18 — there is no sandbox.** `team.md`'s non-production rule cannot hold as written, because the mechanism it names does not exist. Satisfied instead by a **null adapter** behind the §C.1 protocol in every non-production environment, selected by explicit configuration with the null adapter as the default, so a missing setting fails toward not sending. The gateway leg is verified exactly once, at the B3 skeleton checkpoint, with a single real send to the developer's own number. `team.md`'s wording should be corrected to "test credentials or a null adapter" at a future learnings gate. | — | Resolved by the human |
| ~~OQ-3b~~ | **ANSWERED 2026-10-18 — 1012 does not apply to our OTP traffic.** The OTP body is English GSM-7, so **160 characters per segment rather than 70**, and a masking sender ID stays available without forcing a Bangla body. Removes the 3–4× per-OTP cost multiplier and unblocks [D-33]'s ceiling calibration. Does not change the Bangla-first UI: the OTP SMS is one English gateway message; every in-app string stays localized. | — | Resolved by the human |
| OQ-4 | **The FCM adapter's owning Unit is latent** — U6 or U7, whichever is built first. | **U6 and U7**. Left unrecorded it becomes two adapters with two different `UNREGISTERED` behaviours | A Delivery Planning sequencing decision. Flagged, not invented: the dependency artifact deliberately declined a `U6 -> U7` edge, because that would destroy the three-way parallel set for a shared adapter |
| OQ-5 | **The external deletion route's web surface is uncosted** [TC-19]. §B.9 specifies it as FastAPI-served HTML on the existing container, which is the only option under the USD 50/month ceiling [OC-4] — but this has not been confirmed against Play's expectations for the deletion URL. | **U11**, which is release-blocking | A hosting and compliance confirmation, not a contract decision. The contract is written assuming the same container; a separate static host would change the path, not the semantics |
| ~~OQ-6~~ | **DECIDED** — see "The `*_display` rule" below. It was listed here as open while carrying a proposed default, which is a decision wearing a question's clothes. Leaving it open would make every money response schema in U7, U8 and U9 provisional. | — | Resolved at this stage's review |
| OQ-7 | **Does a guardian's `X-Lens-Hint` carry the selected child, or is the child always a path parameter?** §B.4 assumes a path parameter, which is safer (explicit, loggable, testable per request) but makes every guardian route carry an extra segment. | **U4** (child selection, FR2.14–FR2.17) and every guardian-facing route thereafter | A route-shape decision with a privacy consequence — AC9.4.2 makes back-stack correctness across a child switch a privacy case — that should be taken once, with the guardian screens in front of the decider |

---

### The `*_display` rule (resolves OQ-6)

**A money field carries a sibling `*_display` string only where a screen renders
that value directly. Everywhere else the raw `Money` string travels alone.**

The two halves of the trade are both real: [TC-15] puts digit rendering and
separator placement under Bangla locale on the server, because the client holds
no business logic and a client-side formatter is a second place for locale rules
to diverge. But a display string beside every amount roughly doubles money
payload on list endpoints, against the low-end-device discipline — and a list
endpoint is exactly where the cost lands.

The rule resolves it without weakening either: the server still owns every
rendering decision, and it simply does not send renderings nobody displays. In
practice a dues list sends `outstanding` plus `outstanding_display` (the number
the teacher reads) while an itemised ledger behind it sends raw amounts the
client never formats, because the screen shows the already-formatted total.

**Which fields carry a display sibling is recorded in the schema, not decided per
endpoint by whoever writes it.** That is what keeps this from drifting back into
a per-endpoint judgement, and it means the schema-diff gate catches a field
quietly gaining or losing its sibling.

If measurement later shows the payload difference is immaterial at this scale,
the cheap change is to emit the sibling everywhere — additive, and therefore
safe under the `/v1/` policy. The expensive direction is the other one, which is
why the default starts narrow.

---

## Assumptions & Open Questions

**Six open questions remain** (OQ-1..OQ-5 and OQ-7), each naming the Unit it
blocks. OQ-6 was resolved at this stage's review: it had been listed as open
while carrying a proposed default, which is a decision wearing a question's
clothes, and leaving it open would have made every money response schema in U7,
U8 and U9 provisional. The `*_display` rule above settles it.

Two points deserve attention above the rest, because each is cheap to settle now
and expensive once a client version is in the field:

- **The 404-instead-of-403 rule** in the error section. It is unusual enough that
  an implementer will "fix" it back to 403 unless the reasoning is in front of
  them: returning 403 for a resource the caller may not see confirms the resource
  exists, which is an enumeration oracle.
- **Re-apply uses a new `client_mutation_id`.** The obvious implementation reuses
  the old id, which silently turns a conflict re-apply into a no-op — the write
  appears to succeed and nothing changes.

Two further items are carried in from earlier stages rather than raised here:
OQ-1 (`PaymentClaim.transaction_id` after deletion) and OQ-2 (FR8.3's
collection-rate definition). Both are product or legal judgements the contract
can express either way but cannot itself decide.

