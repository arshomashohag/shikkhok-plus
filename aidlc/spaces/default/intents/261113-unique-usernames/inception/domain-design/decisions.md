# Architecture Decisions — Unique usernames

Domain Design, intent `261113-unique-usernames`, 2026-11-13. Each ADR traces
to the requirements (`requirements.md`), the code findings U1–U17
(`codekb/shikkhok-plus/code-quality-assessment.md`) and, where noted, the
review findings R-01 to R-06 accepted at the Requirements Analysis gate.
Answers Q1–Q6 are in `domain-design-questions.md`.

## ADR-001: The username lives on `account`, with a canonical key column

- **Context** — Sign-in and the availability lookup must find a username
  before anyone is authenticated (FR3, FR4). `profile` has forced row-level
  security keyed on the session's account (U6), so it cannot be read there.
  Uniqueness is case-insensitive while the display keeps the person's casing
  (FR1.3). The only precedent is `account.email`, stored lowercased under a
  plain UNIQUE (U9). The schema-parity test compares models with migrations.
- **Decision** — Add `account.username` (as typed), `account.username_key`
  (lowercase, plain UNIQUE, CHECK `username_key = lower(username)`) and
  `account.username_changed_at`, all nullable. AccountDirectory is their only
  writer. [Q1]
- **Consequences** — Positive: lookups are a plain equality on an indexed
  column; the parity test needs no expression-index support; the CHECK makes
  drift between the two impossible. Negative: the username sits outside
  row-level security, so its only runtime protection is the response-schema
  gate (ADR-010), and that gate's field set is hand-maintained. Neutral: two
  columns where one would do.
- **Alternatives Rejected** — On `profile`: unreadable before authentication.
  One column plus a unique index on `lower(username)`: works, but an expression
  index is a second thing the parity test must learn and nothing else in the
  schema uses one. `citext`: a new extension for one column.

## ADR-002: A released username is held as a keyed digest, for 30 days

- **Context** — A released username must not be taken by someone else for 30
  days (FR7.3), and after a deletion no readable identifier of the deleted
  person may remain (FR7.4, U14). Usernames are low-entropy, so a plain hash is
  reversible by trying likely names.
- **Decision** — A new `UsernameHold` ledger owned by Usernames: HMAC-SHA256
  under `SHIKKHOKPLUS_OTP_HMAC_KEY` (read from the environment, never the
  database) of the fixed purpose prefix `username-hold:v1:` followed by the
  username key, so a hold digest can never collide with an OTP digest;
  `held_until`; and `releasing_account_id`, a nullable link to the account
  that released it by rename, set to null when that account is erased (a
  foreign key with set-null). One row per digest: a second release of the same
  name replaces the expiry and the releasing account. The ledger is created in
  the same migration as, and after, the new account columns. Expired holds are
  purged by a scheduled job. The deletion disposition table and the generated
  privacy policy gain an entry for it, and the OTP-key rotation runbook gains a
  line: rotating the key releases every live hold early. [Q2] [R-04] [R-05]
- **Consequences** — Positive: a copy of the database alone reveals no held
  name; reclaim works without storing the name; no second secret to rotate.
  Negative: rotating the OTP key, which the runbook treats as routine, releases
  every hold (acceptable: the worst case is a name freed up to 30 days early,
  and the runbook now says so); the key matters to two features. Neutral: one
  more table and one more purge job.
- **Alternatives Rejected** — Plain SHA-256: reversible by dictionary for short
  names. Storing the text until expiry: retains an identifier of an erased
  person, against the deletion disposition.

## ADR-003: One sign-in field, classified on the server

- **Context** — One field accepts a username, a phone or an email (FR4.1), and
  installed clients send the existing `phone`/`email` shape (FR4.6, D-26). The
  username rule that it starts with a letter (FR1.2) and contains no `@` makes
  the three kinds disjoint.
- **Decision** — SignIn classifies: contains `@` → email; parses as a
  Bangladeshi mobile number in any accepted spelling → phone; otherwise →
  username key. The existing fields stay accepted unchanged. The exact request
  shape (a new optional field on the existing request, or a new request) is
  Contract Design's (OQ4). Classification lives in one server function; the
  clients send what the person typed.
- **Consequences** — Positive: no ambiguity, no client-side business rule
  (TC-9). Negative: a person who types a username that happens to be a valid
  number is impossible by construction, but a mistyped number falls through to
  a username lookup and gets the ordinary uniform refusal, not a "bad number"
  hint. Neutral: `IdentifierFields`, shared by nine request types (U2), is not
  widened.
- **Alternatives Rejected** — Widening `IdentifierFields` with a third kind:
  changes nine request types and the closed `Channel` type that is interpolated
  into SQL column names (U2, debt item 5). Client-side classification: puts a
  rule on the client.

## ADR-004: One contact matcher; links, never decisions

- **Context** — Today only a phone links records, in three places (U4, U5).
  The change needs the same for email at three moments: sign-up, phone add,
  email add (FR6.5). Linking must never accept (BR5.1, FR6.6). The records
  belong to StudentRoster and CentreMembership.
- **Decision** — A new ContactMatching component takes an account id and one
  verified contact and calls each owner's own link statement (matching on phone
  or on email, unlinked and not relink-blocked rows only). Called by
  Registration and AccountSettings inside their transaction. [Q6]
- **Consequences** — Positive: one call site per moment; owners keep their own
  row rules; the dependency graph stays acyclic. Negative: one more module.
  Neutral: the existing `link_phone_seats` becomes a thin caller of it.
- **Alternatives Rejected** — Email twins of every phone statement in each
  module: doubles the places to keep in step. Putting matching in
  AccountDirectory: creates a cycle with the roster and centres, which already
  look accounts up through it.

## ADR-005: Teacher edits, two contacts on one record, and recycled contacts

- **Context** — Review finding R-02: the requirements did not say who keeps
  access when a teacher edits a contact on a linked seat, when a record carries
  a phone and an email held by different accounts, or when a removed contact is
  later verified by someone else. Today a teacher's change of a recorded number
  relinks that seat and resets it to pending, and is refused when that link is
  accepted or erased (`app/students/service.py:_apply_identity`,
  `_refuse_relink`).
- **Decision** —
  1. The existing relink rule extends to email unchanged: changing a recorded
     phone or email relinks that link and resets it to pending; it is refused
     when the link is accepted or erased.
  2. One precedence rule, used on every path that writes a link (a teacher or
     centre saving a record, and ContactMatching at sign-up and contact add):
     **when a link records a phone, only that phone's account may take it,
     now or later; the email is used only when the link records no phone.**
     At save time the link goes to the account holding the recorded phone if
     there is one, otherwise stays unlinked until that phone is verified; an
     email-only link goes to the account holding the email. At match time an
     email links only records whose link records no phone. Saving is never
     refused for this, so the teacher learns nothing about who holds which
     contact. [Q3] [review R-02]
  3. A removed contact leaves existing links in place (FR8.3). When another
     account later verifies that contact, it is linked only to records that
     are still unlinked; records already linked stay with their account.
  4. Test-first cases (the authorization predicate holds): the phone's owner
     signs up after the email's owner and takes the seat; an email never
     links a record that records a phone; a recycled phone links only
     unlinked records.
- **Consequences** — Positive: no new access path for a teacher; no existence
  hint; a mistaken or recycled email can never reach a seat recorded with a
  phone; consistent with the current number rule. Negative: a teacher who
  records both contacts for someone who signs up by email only sees the seat
  linked once that person adds the phone; the Settings copy for adding a
  phone says so. Neutral: the rule is one predicate in each link statement.
- **Alternatives Rejected** — Refusing the save: tells the teacher the two
  contacts belong to different people. Linking neither: leaves both people
  without their invitation.

## ADR-006: Contact changes are confirmed, announced and bounded

- **Context** — Review finding R-01: removing or replacing a contact moves the
  account's recovery channel on a children's-data app, with only a password
  between a thief and the change.
- **Decision** — Replace and remove need password confirmation; replacement
  verifies the new contact first and removes the old in the same transaction.
  After commit, a short best-effort notice goes to the removed contact (email
  through SES, or one SMS segment), not retried, failure logged and not
  surfaced, like FCM today. At most 5 contact changes per account per day.
  Other devices stay signed in. [Q4]
- **Consequences** — Positive: the real owner learns of a takeover through the
  channel being removed; a stolen password cannot churn contacts. Negative: an
  SMS notice costs a segment, bounded by the ceiling and the existing send
  budget. Neutral: the notice text carries no username and no new contact.
- **Alternatives Rejected** — Signing out every other device: protects against
  a thief already signed in elsewhere, but signs out a family's shared tablet
  on every legitimate number change; revisit if abuse appears. No notice: the
  owner would not learn of the change.

## ADR-007: Username sign-in failures cannot lock out the owner; held reads as taken

- **Context** — Review finding R-04: the availability lookup makes username
  existence public, so a per-username failure counter would let anyone lock a
  known name out of sign-in; and a distinct "held" answer would reveal recent
  renames and deletions.
- **Decision** — Username failures are counted per username and network prefix
  (`un_fail_net_hour`, 10 per hour) and per username across all networks
  (`un_fail_hour`, 30 per hour). Their scope values are `u:` plus 62 hex
  characters of SHA-256 over the username key (with a `|` and the network
  prefix for the per-network scope), so no username is stored plain, keys
  cannot collide with phone or `e:` email keys, and they fit the 64-character
  column; names fit the 16-character column (full list in components.md,
  RateCeilings). The public lookup answers available, unavailable, invalid or
  reserved; a held name is "unavailable". The authenticated check used in
  Settings answers "available" for a name held by the caller's own account,
  because a rename by that account would reclaim it (ADR-012). **This amends
  FR3.1 and FR1.6:** there is no separate "held" answer or refusal key on the
  public surface; a held name reads as taken. [Q5] [review R-06, R-07]
- **Consequences** — Positive: an attacker on one network cannot lock out the
  owner on another; distributed guessing is still bounded. Negative: the
  across-networks ceiling is a lockout lever for a distributed attacker, at
  three times the single-network effort. Neutral: phone and email keep their
  existing counter; the exact lookup ceilings are NFR Requirements' (OQ3).
- **Alternatives Rejected** — Per username only, like phone and email today:
  one network can lock the owner out. No per-username ceiling at all: unbounded
  distributed guessing against one known name.

## ADR-008: `username_required` is a server decision; the clients enforce it

- **Context** — Existing accounts must choose a username at next sign-in (FR5)
  while installed clients that predate the change keep working (FR5.3, NFR6).
  Review finding R-06 asked what the flag means for principals with no
  username.
- **Decision** — AccountDirectory computes `username_required` = the account
  has no username; IdentityApi carries it on `GET /v1/me` and the sign-in
  success response. The server does not refuse other routes. Platform
  administrators sign in through the separate admin flow, which neither carries
  nor reads the flag; usernames for administrators are out of scope.
- **Consequences** — Positive: one rule, server-side; old clients unaffected.
  Negative: an old client never asks for a username, so some accounts may stay
  without one until the person updates; sign-in by phone or email keeps working
  for them. Neutral: the flag disappears from the problem once every active
  account has a username.
- **Alternatives Rejected** — Refusing routes until a username exists: locks out
  every installed old client.

## ADR-009: Email invitations: optional phone, uniqueness where phone has it

- **Context** — Review finding R-03: `owner_member.invited_phone` is NOT NULL
  (`app/db/models.py:978`) with a live-invitation uniqueness index per centre;
  guardian and centre email uniqueness was unstated while student email's was
  (FR6.2).
- **Decision** — `owner_member.invited_email` is added and `invited_phone`
  becomes nullable, with a CHECK that at least one is present; a live
  invitation's email is unique per centre, mirroring the phone index. On the
  roster, `student_email` is unique among one teacher's students (as the
  student phone is), and `guardian_email` is not unique, because one guardian
  is recorded on many children, exactly like `guardian_phone`.
- **Consequences** — Positive: email follows the phone's existing rules
  everywhere, so nothing new to learn. Negative: relaxing NOT NULL is a schema
  change on a live table; it is forward-safe (no rows rewritten). Neutral: none.
- **Alternatives Rejected** — A separate invitation-by-email table: two places
  to look for one invitation.

## ADR-010: Username privacy is enforced by the gate and by a membership test

- **Context** — The username is owner-private (FR9) but lives on `account`,
  outside row-level security (ADR-001). The owner-private field set is
  maintained by hand and auto-enrolment covers `profile` columns only (U7); the
  admin contract has its own forbidden list. `email` is already a staff-private
  name (U8).
- **Decision** — `username` and `username_key` join `OWNER_PRIVATE_FIELDS`
  (`app/contract/privacy.py`), and `username` joins `FORBIDDEN_TOKENS`
  (`tests/contract/test_admin_contract.py`). The username is served only to its
  owner, on exactly two response schemas, `MeResponse.username` and the rename
  response's `username`; each is added pair by pair to `OWN_ACCOUNT_FIELDS`, as
  `("MeResponse", "email")` is, so the field reaching any other schema still
  fails. The sign-in success response carries `username_required`, never the
  username. A new test names the account's username columns and fails if
  either is missing from those sets. Teacher-recorded emails are named
  `student_email` and `guardian_email` and are teacher-written fields, visible
  to that teacher. No log line, audit row or message carries a username.
  [review R-08]
- **Consequences** — Positive: a leak fails CI before review sees it, which is
  how this team enforces important rules. Negative: the membership test matches
  on a name pattern; a column given an unrelated name would escape it, so the
  test names the columns too. Neutral: none.
- **Alternatives Rejected** — Relying on review: one reviewer, on the
  surface where this is easiest to miss.

## ADR-011: A username taken during sign-up rolls back; the same code retries

- **Context** — Review finding R-03. `complete_signup` runs inside the verify
  transaction: the code is consumed, the account created and the draft removed
  together, or none of them [C-07]. A username can be taken between the draft
  and verification (FR2.2), and the person should not need a new code.
- **Decision** — A username-unavailable outcome at account creation raises a
  conflict that rolls back the whole verify transaction: the code is not
  consumed, its attempt count is unchanged, the draft is untouched. The verify
  call accepts an optional replacement username; when present it replaces the
  draft's username inside the same transaction, before the account is created.
  Holding the draft's live, correct code is the authorization, exactly as it is
  for completing the sign-up. A wrong code counts as an ordinary verify failure
  under the existing ceilings. A draft allows at most 3 replacements
  (`username_replacements`); after that the person starts the draft again. The
  code's own 5-minute expiry still applies.
- **Consequences** — Positive: the person picks another name without a new SMS
  or email, and the all-or-nothing guarantee of C-07 holds. Negative: a
  username-unavailable response follows a correct code, so it tells the caller
  the code was right; acceptable, because only the person who received the code
  can send it, and the username's availability is public anyway. Neutral: the
  exact field is Contract Design's.
- **Alternatives Rejected** — Committing the code and keeping the draft for a
  separate "choose another username" call: breaks C-07 and needs a new token to
  authorize the second call. Reserving the username on the draft: lets anyone
  squat names with unverified drafts.

## ADR-012: Reclaiming your own released name is exempt from the rename limit

- **Context** — Review finding R-01. A rename starts both the 30-day hold on
  the old name and the 30-day rename limit, so as first designed the owner
  could never take the old name back: the limit refuses it for exactly as long
  as the hold exists. FR7.3 promises the reclaim and FR7.2 the limit.
- **Decision** — A rename to a name whose live hold names this account as the
  releaser is a reclaim, and is exempt from the rename limit. A reclaim clears
  that name's hold, places an ordinary 30-day hold on the name being given up,
  and does not change `username_changed_at`, so it neither starts nor extends
  the limit. Any other rename, including a second rename after a reclaim within
  the window, is subject to the limit as before.
- **Consequences** — Positive: "undo my rename" works for 30 days and FR7.2 and
  FR7.3 hold together. Negative: a person can alternate between two names
  (rename, reclaim, and the limit then refuses a further rename until 30 days
  after the first), which costs nobody anything. Neutral: one extra branch in
  the rename transaction, and test-first cases for both outcomes.
- **Alternatives Rejected** — Dropping reclaim and `releasing_account_id`: the
  person who renames by mistake loses their name for 30 days. Shortening the
  rename limit below the hold: weakens the anti-impersonation intent of the
  limit.
