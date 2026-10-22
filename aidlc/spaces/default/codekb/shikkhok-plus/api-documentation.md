# API Documentation

## The contract and its gate

`openapi.json` at the repository root is the committed OpenAPI **3.1.0**
document. It is an **output**, not a source: the only sanctioned way to
change it is `make openapi`, which runs `python -m app.contract.emit`.
`tests/contract/test_schema_diff.py` compares the committed bytes against a
freshly generated document and fails on any difference — and it generates in
a **subprocess**, because Python seeds hash randomization once per process,
so two generations inside one process would agree however unstable the
serialization actually is.

Hand-editing `openapi.json` to turn a red diff green would invert the control
into a rubber stamp, and the Makefile target says so beside the file.

**Reconciliation against `app/api/`:** the committed document and the
registered routers agree exactly. Twelve operations across eleven paths, from
four routers (`auth`, `batches`, `me`, `health`). The staging router
(`GET /staging/last-otp`) is registered only when the environment permits it,
so it is correctly absent from the committed document; the route-enumeration
gate still allowlists it because it must be reachable before anyone can
authenticate.

## Authentication

No password anywhere. A phone number receives a one-time code by SMS; the
code is exchanged for a token pair.

- **Access token** — JWT, HS256, 15-minute lifetime, carries a `kid` so the
  signing key can rotate without invalidating 30-day refresh tokens.
  Presented as `Authorization: Bearer <token>`.
- **Refresh token** — opaque, 30-day lifetime, stored hashed. Rotation
  detects reuse and invalidates the whole token family.

There is **no OpenAPI security scheme declared** on the operations. The
bearer requirement is enforced by the `authenticated_account` dependency and
asserted by the route-enumeration gate, not described in the document. A
client author reading `openapi.json` alone would not learn that eight of the
twelve operations require a bearer token.

## Authorization: every route names its lens

Each endpoint below lists the lens dependency it resolves. The lens is a
**value**, not a guard: `TeacherLens` carries the `owner_id` the query scopes
on, so the handler cannot build a scoped query without it.

Two explicit allowlists, kept separate on purpose:

**`PUBLIC_ROUTES`** — reachable with no authentication at all:

```
("POST", "/v1/auth/otp")
("POST", "/v1/auth/verify")
("GET",  "/health")
("GET",  "/account-deletion")      <- NO HANDLER EXISTS
("POST", "/account-deletion")      <- NO HANDLER EXISTS
("GET",  "/staging/last-otp")      <- staging only, not registered in production
```

**`LENS_EXEMPT_AUTHENTICATED`** — authenticated, but resolving no lens:

```
("POST", "/v1/auth/refresh")   -- authenticates by refresh token in the body
("GET",  "/v1/me")             -- the route that REPORTS the lenses
```

The two sets are separate because, with one combined list, whoever first hits
a failing authenticated route takes the cheapest green edit and makes it
public, after which nothing records that it must stay authenticated.

> **Finding.** `PUBLIC_ROUTES` holds **six** entries while the comment above
> it states "exactly five, and the count is asserted"
> (`app/contract/routes.py:33-49`). Two of the six —
> `("GET", "/account-deletion")` and `("POST", "/account-deletion")`,
> asserted present by `tests/contract/test_route_lenses.py:86-87` — allowlist
> routes that **no handler registers anywhere**. Nothing is reachable, so
> this is not a live authorization hole; it is pre-declared scope for the
> unbuilt deletion unit, and it means the allowlist is currently wider than
> the application. The deletion unit should land those handlers against
> entries that already exist rather than adding new ones.

---

## Endpoints

### Public

#### `POST /v1/auth/otp` — issue a one-time code

Lens: **none (public)**. Request `IssueRequest { phone: string }`. Response
200 `IssueResponse { status?: string }`.

Four datastore-backed ceilings are checked **narrowest first**, with the
increment in the same statement as the check so a refused request never
consumes a wider allowance:

| Scope | Limit | Constant |
|---|---|---|
| per number, hourly | 3 | `PER_NUMBER_HOURLY` |
| per number, daily | 5 | `PER_NUMBER_DAILY` |
| per IP, hourly | 10 | `PER_IP_HOURLY` |
| global, daily | `SHIKKHOKPLUS_GLOBAL_DAILY_SMS` (test default 500) | `GLOBAL_DAILY` |

A breach is a **`ConflictError` (409)**, never a `TransientError` — retrying
into a cost ceiling is exactly wrong.

The response is **byte-identical for a known and an unknown number**. The
asserted property is structural (the unknown-number path performs the same
hash computation rather than returning early), not a wall-clock bound.

Only the HMAC hash of the code is stored. The code has a 5-minute lifetime
and may be verified once.

#### `POST /v1/auth/verify` — exchange a code for tokens

Lens: **none (public)**. Request `VerifyRequest { phone, code }`. Response
200 `TokenResponse { access_token, refresh_token, expires_in: int }`.

At most 5 verify attempts per OTP (`ATTEMPT_CEILING`); the 6th is refused and
the OTP is dead afterwards.

#### `GET /health` — liveness, connectivity and schema revision

Lens: **none (public)**. Response 200 `HealthResponse { status: "ok",
database: "ok" | "fail", migration_revision: string | null }`.

`extra="forbid"` on the model, so adding a field is a deliberate edit rather
than a dictionary key someone slipped in. Every field here is information
disclosed to an unauthenticated caller, which is why it reports only these
three things. This is what makes the post-deploy smoke set meaningful: a
container that started is not a container whose schema migrated.

#### `GET /staging/last-otp` — the staging outbox

Lens: **none (public)**. **Not registered in production**, and not in the
committed contract. Query `phone`. Returns the whole rendered message (not
the extracted code, which would mean this module knowing the template).
Three independent mechanisms gate it, and the startup check refuses to start
a production process with `SHIKKHOKPLUS_STAGING_OUTBOX=1` — it hands out an
OTP for any number to an unauthenticated caller.

### Authenticated, lens-exempt

#### `POST /v1/auth/refresh` — rotate the token pair

Request `RefreshRequest { refresh_token }`. Optional `authorization` header.
Response 200 `TokenResponse`.

Rotation with reuse detection: presenting a rotated-out token invalidates the
entire family. Untested, this degrades silently into non-rotating refresh
tokens, because the happy path is identical — hence a named test.

#### `GET /v1/me` — which lenses this account has

Response 200 `MeResponse { lenses: LensEntry[] }`, where
`LensEntry { kind: "teacher" | "student" | "guardian", count: int }`.

**Resolves no lens, deliberately and safely.** It is the route that *reports*
the lenses, so requiring one would mean an account had to already know what
it was in order to ask. Every value it returns derives from the authenticated
account id; it reads nothing another account could own.

**No role, and no default lens.** The list says what is available; a
server-chosen default would be a stored role by another name. A single-entry
list is the app's cue to skip the picker; an empty list is its cue to
explain itself. Order is fixed — teacher, student, guardian — so the picker
does not reshuffle between sign-ins as counts change.

Answered in **one SQL statement** carrying all three counts. An account with
an owner row and no batches is still a teacher: the lens is present with a
count of zero.

### Teacher lens

All five scope on `lens.owner_id`. A batch or enrolment belonging to another
teacher returns **404, deliberately indistinguishable from one that does not
exist** — a 403 for a real id and a 404 for an invented one is an existence
oracle.

#### `GET /v1/batches` — list this teacher's batches

Response 200 `BatchResponse[]`.

#### `POST /v1/batches` — create a batch

Request `BatchCreateRequest { name, subjects[], teacher_display_name?,
default_fee?, fee_due_day? (1-31), collection_number?,
collection_channel? }`. Response **201** `BatchResponse`.

`default_fee` is a `$ref` to the shared `Money` component — a JSON string.
`fee_due_day` is an integer day-of-month and is the **one keyed exemption**
in `NON_MONEY_FIELDS`, because it matches both the `fee` and the `due` money
tokens while carrying a day. Values 29-31 are legal and clamp to the month's
last day at generation time, which is why the column must admit them.

#### `GET /v1/batches/{batch_id}/roster` — read a roster

Response 200 `RosterRowResponse[]`:

| Field | Type | Note |
|---|---|---|
| `enrollment_id` | string | the teacher-facing key; **never** an account id |
| `display_name` | string | teacher-typed |
| `guardian_phone` | string \| null | teacher-typed |
| `fee_amount` | `Money` \| null | null means inherit the batch default |
| `inactive_from` | date \| null | |
| `status` | string | **server-computed**: `dormant`, `active` or `inactive` |

`status` is the pattern the whole layering rule turns on: the server sends a
decision, the client switches on the enum, and no composable compares a date
or an amount of its own (`app/api/batches.py:71-85`).

Note for the roster work ahead: the field **already exists** and already
carries three values. The pending-seat state the plan calls for is a fourth
value in this enum plus the acceptance columns behind it, not a new field.

#### `POST /v1/batches/{batch_id}/enrollments` — add a student

Request `EnrollmentCreateRequest { display_name, student_phone?,
guardian_phone?, fee_amount?, joined_on? }`. Response **201**
`RosterRowResponse`.

Both the student link and the guardian link go on **one row**, so the
enrolment a guardian reaches *is* the child's enrolment.

#### `PATCH /v1/enrollments/{enrollment_id}/inactive-from`

Request `InactiveFromRequest { inactive_from?: date }`. Response **204**.

The semantics are money-adjacent and fail quietly: it must stop future fee
cycles, leave existing dues standing, and leave the student active in other
batches. `tests/batches/test_inactive_from.py` covers it.

#### `DELETE /v1/enrollments/{enrollment_id}` — remove a seat

Response **204**. Removal only while the seat is unclaimed; otherwise raises
`EnrollmentNotRemovable`, a `ConflictError` (409), and the caller marks it
inactive instead.

### Guardian lens

#### `GET /v1/guardian/children` — the children this account guards

Response 200 `GuardianChildResponse[] { enrollment_id, display_name,
batch_name, teacher_display_name? }`.

`GuardianLens.child_enrollment_id` may be `None` on the first authenticated
request, because the selection list is exactly what that request renders. On
later requests the child arrives as a **path parameter**, never from a
client-supplied hint.

---

## Cross-cutting contracts

### Money on the wire

One shared component, referenced by every money-carrying property:

```json
"Money": {
  "type": "string",
  "pattern": "^[0-9]+\\.[0-9]{2}$",
  "description": "A BDT amount in canonical form: exactly two decimal places, no thousands separator, no currency symbol, no sign. Always a JSON string, never a JSON number."
}
```

**The pattern admits no sign.** Three properties reference it today:
`BatchResponse.default_fee`, `BatchCreateRequest.default_fee`,
`RosterRowResponse.fee_amount` — each as
`anyOf: [{$ref: Money}, {type: null}]`, because `null` means inherit while
zero means waiver.

That nullable shape is worth recording: it emits no top-level `type`, so an
earlier version of the money gate reading `node["type"]` directly saw nothing
and reported nothing — at exactly the project's most absolute rule. The gate
now looks through `anyOf`/`allOf`/`oneOf`, and through `items` and
`additionalProperties`, so a `list[float]` of amounts is caught by its
element type rather than passing as "array".

### The error envelope

```json
{"error": {"code": "...", "retryable": false, "message_key": "...", "details": {"k": "v"} | null}}
```

Three deliberate choices. `retryable` is **server-provided** — the client is
forbidden business logic, so it is told rather than inferring from a status.
`code` is a stable machine value, switched on and never parsed from message
text. **`message_key` rather than `message`** — a server-sent English string
cannot be localized, and in a Bangla-first UI that guarantees untranslated
English error text; the user-facing string comes from `strings.xml` and the
server names which one.

`message-keys.json` at the repository root is the registry, and
`tests/contract/test_message_keys.py` plus the Kotlin
`MessageKeyCoverageTest` keep the two sides in step.

Status mapping, from `app/errors/`:

| Class | HTTP | Retryable | Caller behaviour |
|---|---|---|---|
| `ValidationError` | 400/422 | no | fix and resubmit |
| `AuthorizationError` | 401, 403 or **404** | no | re-authenticate or stop |
| `ConflictError` | 409 | no | refetch and decide |
| `TransientError` | 503 | yes | retry with backoff |
| `FatalError` | 500 | no | do not retry; alert |

`AuthorizationError.status` is typed `Literal[401, 403, 404]`, so a fourth
value is a build-time error at the raise site. `app/errors/codes.py` holds a
single `NOT_AVAILABLE` code covering both "unreachable" and "absent", with a
test asserting the registry contains no `X_NOT_FOUND`/`X_NOT_YOURS` pair —
each reads as good practice alone and the pair is an existence oracle.

> **Finding.** The envelope is **published as a component but referenced by
> no operation's responses.** `app/main.py:144-182` injects `ErrorEnvelope`
> and `Money` into the document explicitly, precisely because FastAPI emits a
> component only when a route references it. The operations declare only
> their success response and FastAPI's own `HTTPValidationError` for 422. So
> a client author reading `openapi.json` sees the envelope defined but learns
> from no operation that a 403 or a 409 returns it. The project's own code
> acknowledges this is a stopgap ("this stays until a Unit whose routes
> genuinely reference them lands, at which point it becomes a no-op rather
> than a lie"). It also means the ZAP baseline pass the plan wires against
> this schema would not know which error shapes to expect.

### The lens hint header

`X-Lens-Hint: teacher | student | guardian`, defined client-side in
`feature/auth/LensHint.kt`. It travels **out** only, to say which lens the
person picked from the ones the server already told them they have. Nothing
travels in on the strength of it: the server response is self-describing and
names the lens that produced it. A hint naming an unsupported lens is refused
with `LENS_NOT_AVAILABLE`.

The header is **not declared in `openapi.json`** on any operation.

### Versioning

Every feature route is under `/v1/`. `/health` and the staging outbox are
unversioned. An installed Android app cannot be forced to update, so `/v1/`
stays additive and the client sets `ignoreUnknownKeys = true` — a client that
refused an unknown field would break on every server deploy until the user
updated.

## What the API does not yet have

No endpoint exists for account creation, seat acceptance or decline, fee
cycles, payment claims or verification, sessions, attendance, exams, marks,
insights, or either account-deletion path. See `component-inventory.md` for
the full absence list and which deliverable unit each belongs to.

## Sources

- [code] `openapi.json`, parsed 2026-10-22 at commit `b14b1fa`
- [code] `app/api/auth.py`, `app/api/batches.py`, `app/api/me.py`,
  `app/api/health.py`, `app/api/staging.py`, `app/api/deps.py`
- [code] `app/contract/routes.py` (the two allowlists),
  `app/schemas/money.py`, `app/errors/_classes.py`, `app/errors/codes.py`
- [code] `app/auth/ceilings.py` (the four limits), `app/auth/otp.py`,
  `app/auth/tokens.py` (the lifetimes)
- [verified] the twelve committed operations match the four registered
  routers, compared 2026-10-22
