# Contract Summary — Unique usernames

Intent `261113-unique-usernames`. Inputs: `units-generation/unit-of-work.md`
and `unit-of-work-dependency.md` (U1–U4 and their edges),
`domain-design/components.md` and `decisions.md` (ADR-001 to ADR-012), and
`requirements-analysis/requirements.md` (FR1–FR11, NFR1–NFR9). Answers Q1–Q5
are in `contract-design-questions.md`.

Every contract below extends the existing `/v1` API additively (NFR6). The
committed `openapi.json`, kept current by the schema-diff gate, becomes the
contract of record when each backend unit merges; the blocks here pin the
shapes that both clients build against before then.

**Direction recorded at this stage's approval (2026-11-14).** The person said:
"Currently hardly anyone using this application. So, don't worry much about
old user." So compatibility with app versions installed before this change is
not a constraint for this intent, which settles the two Major review findings
without a compatibility shim:

- `SignupRequest.username` is **required**; a sign-up without one is a 422
  validation error. A draft stored before the deploy and verified after it is
  created without a username and gets `username_required: true`, like any
  existing account.
- `MemberResponse.phone` becomes **nullable** for an email-only invitation;
  both clients are updated in U3 and U4 to read it as optional.
- This narrows NFR6, FR4.6 and FR5.3 to "the current Android and web clients",
  not every installed version. Existing **accounts** still choose a username at
  next sign-in (FR5), and sign-in by phone or email keeps working for everyone
  (FR4.2).

The minor review findings (R-03 to R-07) are settled in Functional Design for
U1 and U2.

## Contracts

| # | Provider Unit | Consumer | Mechanism | Owner |
|---|---|---|---|---|
| C1 | U1 usernames-backend | U3 android-identity, U4 web-identity (External: installed Android and web clients) | Synchronous REST/HTTP, `/v1`, JSON | U1 |
| C2 | U2 contacts-and-invites-backend | U3 android-identity, U4 web-identity (External: installed Android and web clients) | Synchronous REST/HTTP, `/v1`, JSON | U2 |
| C3 | U1 usernames-backend and U2 contacts-and-invites-backend | Each other (no DAG edge; shared integration point) | Shared PostgreSQL schema and one in-process call in `app.accounts` | Shared; U2 owns the matcher signature, U1 owns account creation |

There is no other external consumer: the admin console's routes do not change,
and no partner API exists.

## C1 — Usernames API (U1 → clients)

Changes to existing operations are additive: new optional request fields and
new response fields. Two operations are new. Every error uses the existing
`ErrorEnvelope` (`code`, `retryable`, `message_key`).

```yaml
openapi: 3.1.0
info:
  title: ShikkhokPlus identity — usernames (C1, additive to /v1)
  version: v1
paths:
  /v1/accounts:                      # existing: verify-first sign-up draft
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/SignupRequest' }
      responses:
        '201': { description: Draft stored and code sent; identical whether or not the contact has an account }
        '422': { description: "Validation; message_key in account.username.* for a username refusal (FR1.6)" }
  /v1/auth/verify:                   # existing
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/VerifyRequest' }
      responses:
        '200': { description: As today (password-setup token); the account now has the draft's username }
        '409':
          description: >
            account.username.unavailable — the draft's username was taken after
            the draft was stored. Nothing was consumed: the code still works.
            Retry this call with the same code and a replacement `username`
            (ADR-011). After the draft's replacement limit,
            account.username.retry_limit and the draft must be started again.
  /v1/auth/password:                 # existing: password sign-in
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/PasswordSignInRequest' }
      responses:
        '200': { description: As today (VerifyResponse with tokens, or the MFA challenge) }
        '422': { description: "auth.password.wrong for unknown, password-less and wrong alike (NFR1); auth.password.too_many_attempts at a ceiling" }
  /v1/accounts/username-availability:   # NEW, public, allowlisted (FR3.3)
    get:
      parameters:
        - { name: username, in: query, required: true, schema: { type: string, maxLength: 64 } }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/UsernameAvailabilityResponse' }
        '429': { description: "auth.lookup.too_many — availability ceilings (FR3.2); the form can still be submitted" }
  /v1/me/username-availability:      # NEW, authenticated, lens-exempt
    get:
      description: As the public lookup, except a name held by the caller's own account answers available (reclaim, ADR-012). Used in Settings.
      parameters:
        - { name: username, in: query, required: true, schema: { type: string, maxLength: 64 } }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/UsernameAvailabilityResponse' }
  /v1/me/username:                   # NEW, authenticated, lens-exempt
    put:
      description: Choose the first username (no password needed, no limit), rename, or reclaim.
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/UsernameChangeRequest' }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/UsernameChangeResponse' }
        '409': { description: "account.username.unavailable, or account.username.change_too_soon (with next_change_at in the response body's details)" }
        '422': { description: "account.username.* format refusals; auth.password.current_wrong when a rename's password is wrong" }
  /v1/me:                            # existing
    get:
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/MeResponse' }
components:
  schemas:
    SignupRequest:                   # existing fields unchanged; one addition
      properties:
        username: { type: string, minLength: 1, maxLength: 64, description: "REQUIRED (added to the schema's required list); validated by FR1 on the server (ADR-003: clients send what was typed)" }
    VerifyRequest:
      properties:
        username: { type: [string, 'null'], maxLength: 64, description: "Optional replacement username, used only after account.username.unavailable" }
    PasswordSignInRequest:
      description: Exactly one of login, phone, email (Q1). phone and email keep their meaning.
      properties:
        login: { type: [string, 'null'], maxLength: 254, description: "What the person typed: username, phone or email; classified on the server (ADR-003)" }
    UsernameAvailabilityResponse:
      required: [status]
      properties:
        status: { type: string, enum: [available, unavailable, invalid, reserved] }
        message_key: { type: [string, 'null'], description: "For invalid: which FR1 rule failed (account.username.*)" }
    UsernameChangeRequest:
      required: [username]
      properties:
        username: { type: string, maxLength: 64 }
        password: { type: [string, 'null'], description: "Required when the account already has a username (rename or reclaim); ignored for the first choice" }
    UsernameChangeResponse:
      required: [username, next_change_at]
      properties:
        username: { type: string, description: "As stored (display casing). Owner-only: an OWN_ACCOUNT_FIELDS pair (ADR-010)" }
        next_change_at: { type: [string, 'null'], format: date-time, description: "When an ordinary rename is next allowed; null when no limit applies" }
    MeResponse:                      # existing fields unchanged; two additions
      properties:
        username: { type: [string, 'null'], description: "Owner-only: an OWN_ACCOUNT_FIELDS pair (ADR-010)" }
        username_required: { type: boolean, description: "True while the account has no username (FR5.1, ADR-008)" }
```

New `message_key` values (added to `message-keys.json` and to both clients'
Bangla and English bundles in U1): `account.username.too_short`,
`account.username.too_long`, `account.username.invalid_character`,
`account.username.must_start_with_letter`, `account.username.bad_dot`,
`account.username.reserved`, `account.username.unavailable`,
`account.username.change_too_soon`, `account.username.retry_limit`,
`auth.lookup.too_many`.

Behaviour the shapes do not show:

- The public availability lookup never distinguishes a held name from a taken
  one (ADR-007, amending FR3.1 and FR1.6).
- `login` classification: `@` means email; a valid Bangladeshi mobile number in
  any accepted spelling means phone; anything else is a username key (ADR-003).
- The sign-in success response and the token responses do not change;
  `username_required` is read from `GET /v1/me` (Q2), which both clients
  already call after sign-in to read `has_password`. This narrows FR5.1's
  "and the sign-in success response" to `GET /v1/me`; the flag is still
  server-computed and still drives the screen (FR5.2).

## C2 — Contacts and email invitations API (U2 → clients)

```yaml
openapi: 3.1.0
info:
  title: ShikkhokPlus identity — contacts and email invitations (C2, additive to /v1)
  version: v1
paths:
  /v1/students:                      # existing
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/StudentCreateRequest' }
      responses:
        '201':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/StudentResponse' }
        '409': { description: "student.email.taken — another of this teacher's students has that student email (FR6.2)" }
  /v1/students/{student_id}:         # existing
    patch:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/StudentUpdateRequest' }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/StudentResponse' }
        '409': { description: "student.email.taken; or the existing refusal for changing an accepted or erased link, now for email too (ADR-005)" }
  /v1/centre/members:                # existing
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/MemberInviteRequest' }
      responses:
        '201':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/MemberResponse' }
        '409': { description: "centre.member.already_invited — now also for a live invitation with the same email (ADR-009)" }
  /v1/accounts/already-added:        # existing, public
    get:
      parameters:
        - { name: phone, in: query, required: false, schema: { type: string } }
        - { name: email, in: query, required: false, schema: { type: string, maxLength: 254 }, description: "NEW. Exactly one of phone or email (FR6.7)" }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/AlreadyAddedResponse' }
  /v1/me/contact:                    # existing: start adding a contact (sends a code)
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ContactRequest' }
      responses:
        '200': { description: As today (IssueResponse) }
        '409': { description: "account.contact.change_limit at 5 changes per day (ADR-006)" }
        '422': { description: "auth.password.current_wrong, or account.contact.password_required when replacing without a password" }
  /v1/me/contact/verify:             # existing: finish adding or replacing
    post:
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/MeResponse' }
  /v1/me/contact/remove:             # NEW, authenticated, lens-exempt
    post:
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ContactRemoveRequest' }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/MeResponse' }
        '409': { description: "account.contact.last_one (FR8.4), or account.contact.change_limit" }
        '422': { description: "auth.password.current_wrong" }
components:
  schemas:
    StudentCreateRequest:            # existing fields unchanged; two additions
      properties:
        student_email: { type: [string, 'null'], maxLength: 254 }
        guardian_email: { type: [string, 'null'], maxLength: 254 }
    StudentUpdateRequest:            # existing fields unchanged; two additions
      properties:
        student_email: { type: [string, 'null'], maxLength: 254, description: "null clears it; absent leaves it" }
        guardian_email: { type: [string, 'null'], maxLength: 254 }
    StudentResponse:                 # existing fields unchanged; two additions
      properties:
        student_email: { type: [string, 'null'], description: "As the teacher typed it, lowercased. Teacher-written (ADR-010)" }
        guardian_email: { type: [string, 'null'] }
    MemberInviteRequest:
      description: "At least one of phone or email (was: phone required)"
      properties:
        phone: { type: [string, 'null'] }
        email: { type: [string, 'null'], maxLength: 254 }
    MemberResponse:
      properties:
        phone: { type: [string, 'null'], description: "Was a required string; now null for an email-only invitation (no compatibility shim, by the person's direction)" }
        invited_email: { type: [string, 'null'] }
    ContactRequest:                  # existing: exactly one of phone or email
      properties:
        password: { type: [string, 'null'], description: "Required when the account already holds a contact of this kind: the request is then a replacement (Q3)" }
    ContactRemoveRequest:
      required: [kind, password]
      properties:
        kind: { type: string, enum: [phone, email] }
        password: { type: string }
```

New `message_key` values (added in U2): `student.email.taken`,
`account.contact.last_one`, `account.contact.change_limit`,
`account.contact.password_required`. `MemberInviteRequest.phone` changing from
required to optional is a relaxation, not a break: every request valid today
stays valid.

Behaviour the shapes do not show:

- A replacement is completed by the existing `/v1/me/contact/verify`; the old
  contact is removed in the same transaction and a best-effort notice goes to
  it after commit (ADR-006).
- Linking on verify follows the one precedence rule of ADR-005 and never sets a
  decision.
- `MeResponse.phone` and `MeResponse.email` become nullable in practice for
  whichever kind the person removed; both are already typed nullable today.

## C3 — Shared schema and the one shared call site (U1 ↔ U2)

No DAG edge exists between U1 and U2 (unit-of-work-dependency.md). This
contract fixes what each may assume about the other, so either can merge
first.

```yaml
shared-schema:
  database: PostgreSQL 16, one Alembic chain
  rule: Each unit adds only its own columns and tables, in its own forward-only migration; whichever merges second rebases its migration onto the first's revision.
  u1_adds:
    account: [username, username_key (UNIQUE, CHECK = lower(username)), username_changed_at]
    pending_signup: [username, username_replacements]
    username_hold: [key_digest (PK), held_until, releasing_account_id (FK account.id ON DELETE SET NULL), created_at]
  u2_adds:
    student: [student_email, guardian_email]
    enrollment: [student_email, guardian_email]
    owner_member: [invited_email; invited_phone made NULLable; CHECK at least one of the two; unique live email per centre]
  neither_reads_the_others_columns: true
in-process-call:
  call_site: app.accounts.service.create_account_rows, at the existing "if phone is not None: link_phone_seats(...)" line
  owner_of_signature: U2
  before: link_phone_seats(session, *, account_id, phone)
  after: match_contact(session, *, account_id, contact: Identifier)  # called once per verified contact; link_phone_seats remains as a thin wrapper until no caller uses it
  u1_may_assume: the call exists and keeps working with the phone it receives today; U1 does not edit this line
  u2_may_assume: create_account_rows keeps its keyword arguments; U1 adds a username argument and nothing else
shared-generated-files:
  files: [openapi.json, message-keys.json, the AuthEvent set in app/audit, PUBLIC_ROUTES and its count]
  rule: whichever of U1 or U2 merges second regenerates and rebases these; a merge-order cost, not a dependency edge
```

## Contract ownership rules

- **U1 owns C1** and **U2 owns C2**; each owner changes its own spec, and the
  change lands in the same PR as the code, through the committed
  `openapi.json` and its schema-diff gate.
- **Additive by default.** New request fields are optional; responses may gain
  fields; clients tolerate unknown fields (D-26). A field is never renamed,
  retyped or removed under `/v1`.
- **A breaking change** (making an optional request field required, removing or
  narrowing a response field) is not allowed under `/v1`; it would need a new
  version and is out of scope here.
- **Errors are keys, not text.** Every new refusal is a `message_key` added to
  `message-keys.json` and to both clients' bundles in the same change, which
  `MessageKeyCoverageTest` and the backend key test already enforce.
- **C3** is changed only by agreement of both units' design: U2 owns the
  matcher signature; U1 owns `create_account_rows` and adds only its username
  argument.

## Open questions

| Contract | Question | Blocks |
|---|---|---|
| C1 | Exact ceilings for the availability lookup (OQ3); the contract only fixes that a ceiling answers `auth.lookup.too_many` with HTTP 429. | U1 (NFR Requirements) |
| C1 | How the sign-up retry cap is counted so a rollback cannot undo it (Domain Design review R-09); the contract only fixes `account.username.retry_limit`. | U1 (Functional Design) |
| C1 | How a repeated reclaim is recorded so it cannot bypass the rename limit (Domain Design review R-10). | U1 (Functional Design) |
