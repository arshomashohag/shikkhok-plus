# Requirements — Unique usernames

Intent record: `261113-unique-usernames`. Depth: Standard. Project type:
brownfield. Builds on the code knowledge base rebuilt on 2026-11-13
(`aidlc/spaces/default/codekb/shikkhok-plus/`): `business-overview.md`
§ "Identity and sign-in as built today", `architecture.md` § Interaction
Diagrams 1–4, `code-structure.md`, and findings U1–U17 in
`code-quality-assessment.md`.

## Intent analysis

**What the person is trying to achieve.** Today an account is reachable only by
a phone number or an email address, and that is also how the person signs in.
The change makes a **username** the stable sign-in name, chosen by the person,
and turns phone and email into what they really are in this product: ways to
prove who you are, recover access, and be found by a teacher or a centre who
recorded you.

Three goals follow:

1. **A name the person controls.** It survives a change of phone number, works
   for a family that shares one phone, and is the same on Android and web.
2. **Contacts that can change.** A person adds, replaces or removes a phone or
   email in Settings, as long as one verified contact remains.
3. **Invitations that reach people by email as well as phone.** A teacher, or a
   coaching centre, records either, and the person's account is matched to it
   whenever that contact is verified, whether at sign-up or later.

**Type**: enhancement to an existing, unreleased product (no Play Store release
yet, per `CHANGELOG.md`). **Scope**: multi-component — backend, Android, web.
**Complexity**: standard; risk is high because it changes authentication and
adds a private field on a children's-data app.

**A premise in the request is corrected here.** The request speaks of "dormant
teacher-recorded accounts" that a sign-up "claims". No such accounts exist in
the current code (finding U3): a teacher-recorded person exists only as a phone
number on `student`, `enrollment` or `owner_member`, and an account is created
only when verify-first sign-up completes. "Claiming" is therefore **seat
linking** (`link_phone_seats`), not taking over an account row. The
requirements below keep the request's intent — a person who signs up on a
recorded contact sees what was recorded for them — on the mechanism that
actually exists. The stale prose saying otherwise (`app/db/models.py:452-454`,
the comment in `app/auth/otp.py` `verify`) is corrected as part of this work
(FR8.4).

## Functional requirements

### FR1 Username rules

- **FR1.1** A username is 3 to 20 characters long, drawn only from Latin
  letters `a–z` / `A–Z`, digits `0–9`, underscore `_` and dot `.`. Bangla
  script and every other character are refused. [desc]
- **FR1.2** A username starts with a Latin letter, does not end with a dot, and
  does not contain two dots in a row. Starting with a letter is what guarantees
  a username never looks like a phone number; the absence of `@` guarantees it
  never looks like an email address. [desc] [assumption]
- **FR1.3** Usernames are unique without regard to case: `Rahim_01` and
  `rahim_01` cannot both exist. The username is displayed as the person typed
  it; comparison, uniqueness and sign-in use its lowercase form. [desc]
- **FR1.4** Leading and trailing whitespace is removed before validation;
  whitespace inside a username is invalid. [assumption]
- **FR1.5** A short list of reserved names is refused at sign-up and at rename,
  compared without regard to case: at least `admin`, `administrator`,
  `support`, `help`, `shikkhokplus`, `shikkhok`, `system`, `root`, `staff`,
  `teacher`, `official`. The list lives in one server-side place. [Q7]
- **FR1.6** Every refusal names the rule broken (too short, too long, invalid
  character, must start with a letter, reserved, taken, held) through a
  `message_key`, never a server-sent English sentence, and the form keeps what
  the person typed. [team: Error handling]

Acceptance criteria:

- Given the sign-up form, When the person enters `ab`, Then it is refused as too
  short; When they enter `a` followed by 19 more valid characters (20 total),
  Then it is accepted; When they enter 21 characters, Then it is refused as too
  long.
- Given an existing account with username `Rahim.Uddin`, When another person
  submits `rahim.uddin`, Then it is refused as taken.
- Given the sign-up form, When the person enters `01712345678`, `_rahim`,
  `rahim.`, `ra..him`, `রহিম` or `Admin`, Then each is refused with the rule
  it breaks.

### FR2 Sign-up with a username

- **FR2.1** Sign-up requires a username, exactly one of a phone number or an
  email address, and the existing profile fields. The username travels in the
  sign-up draft (`pending_signup`) and the account is created with it when the
  code is verified (`complete_signup`). [desc] [U10]
- **FR2.2** The username is checked when the draft is submitted and again when
  the account is created. If it was taken in between, account creation does not
  proceed; the person is told the username is no longer available and asked
  for another, without re-sending the code and without losing the other fields
  they entered. [U10] [assumption]
- **FR2.3** Two drafts may name the same username; whichever completes
  verification first gets it. A draft does not reserve a username. [U10]
  [assumption]
- **FR2.4** Sign-up keeps its existing guarantee that it is not an existence
  oracle for phone numbers or email addresses: the response to submitting a
  draft is the same whether or not the phone or email already has an account
  [BR2.7]. A username refusal (FR1) is allowed to differ, because availability
  is checked separately (FR3) and reveals nothing about phones or emails.
- **FR2.5** When the account is created, every seat and centre membership
  recorded against the verified phone or email is linked to it (FR6), exactly
  as phone seats are linked today. Linking is never acceptance: each linked
  seat stays `pending` until its holder decides [BR5.1].

Acceptance criteria:

- Given a person signs up with username `nadia_k` and an email, When they enter
  the code, Then an account exists with that username and email, and they go on
  to set a password as today.
- Given two people submit drafts with username `nadia_k`, When the first
  verifies, Then the second's verification asks them to choose another
  username and keeps their other answers.
- Given a teacher recorded `nadia@example.com` as a guardian email on a seat,
  When Nadia signs up with that email, Then the seat appears in her invitations
  as pending, not accepted.

### FR3 Username availability check

- **FR3.1** While typing a username at sign-up or rename, the person is told
  whether it is available, through a public lookup that answers only
  available / taken / held / invalid / reserved — never who holds it. [Q4]
- **FR3.2** The lookup has its own rate ceilings (per IP, per network prefix,
  and global), in the way the existing already-added lookup does (NFR2). A
  person who hits a ceiling can still submit the form; the final check at
  creation or rename is authoritative. [U13]
- **FR3.3** The lookup is added to the explicit public-route allowlist, with
  the count assertions and the justification comment updated in the same
  change. [U12] [project: NEVER let a comment state a count nothing checks]

Acceptance criteria:

- Given `nadia_k` is taken, When anyone checks it, Then the answer is "taken"
  and carries no account data.
- Given the per-IP ceiling is reached, When the person checks again, Then the
  lookup is refused as rate-limited and the form still lets them submit.

### FR4 Sign-in with one field

- **FR4.1** The sign-in form has one field that accepts a username, a phone
  number or an email address, plus the password. The server decides which it
  is: a value containing `@` is an email; a value that is a valid Bangladeshi
  mobile number in any accepted spelling is a phone; any other value is
  treated as a username. [desc] [U1]
- **FR4.2** Signing in by phone or email keeps working permanently, for every
  account, whether or not it has a username. [desc]
- **FR4.3** Sign-in answers identically for an unknown username, a username
  whose account has no password, and a wrong password: one refusal,
  `auth.password.wrong`, with the same timing behaviour as phone and email
  sign-in today [BR2.7].
- **FR4.4** Failed sign-ins are counted per username with the same ceiling as
  per phone or email today (10 per hour), and per network as today. A username
  key and a phone or email key can never collide in the counters. [U1] [desc]
- **FR4.5** Two-step verification, the password-setup flow and refresh are
  unchanged: a username sign-in that needs a second step gets the same
  challenge as a phone or email sign-in.
- **FR4.6** The existing request shape (`phone` or `email` field) stays
  accepted, so installed clients keep working; the single-field form is an
  addition. [D-26]

Acceptance criteria:

- Given an account with username `Nadia_K`, When the person signs in with
  `nadia_k` and the right password, Then they are signed in.
- Given the same account, When they sign in with its phone `01712345678` or
  `+8801712345678`, Then they are signed in.
- Given no account has username `ghost_1`, When someone signs in with it, Then
  the refusal is identical to a wrong password on a real account.
- Given ten failed attempts on `nadia_k` within an hour, When an eleventh
  arrives, Then it is refused by the ceiling regardless of the password.

### FR5 Existing accounts choose a username

- **FR5.1** Every authenticated response the clients use to route the person
  (`GET /v1/me` and the sign-in success response) carries a server-computed
  `username_required` flag, true while the account has no username. [U15]
  [TC-9]
- **FR5.2** When the flag is true, both clients show a choose-username screen
  after sign-in, before anything else, and the person cannot dismiss it without
  choosing one or signing out. [desc]
- **FR5.3** The server does not refuse other requests from an account without a
  username, so a client version that predates this change keeps working. The
  flag is the decision; the clients enforce the screen. [D-26] [assumption]
- **FR5.4** Choosing the first username follows FR1 and is not subject to the
  rename limit (FR7.2).

Acceptance criteria:

- Given an existing account without a username, When the person signs in by
  phone, Then the response says `username_required: true` and the client shows
  the choose-username screen.
- Given they choose `rahim_math`, When they continue, Then the flag is false on
  every later response and the screen does not return.

### FR6 Invitations by phone or email

- **FR6.1** When a teacher records or edits a student, they may enter a student
  email and a guardian email as well as, or instead of, the phone numbers. Both
  are optional, validated like sign-up emails, and stored lowercased. [desc]
  [U4]
- **FR6.2** A student email is unique among one teacher's students, the same
  way a student phone is unique per teacher today [D2]. [assumption]
- **FR6.3** Teacher-recorded email fields are named distinctly
  (`student_email`, `guardian_email`) and are teacher-written data visible to
  that teacher, like the recorded phone numbers. They are never the account's
  own email. [U8]
- **FR6.4** A coaching centre may invite a member teacher by phone or by email.
  [Q5]
- **FR6.5** Matching links an account to every seat and centre membership
  recorded with any phone or email the account has **verified**, at three
  moments: when the account is created, when a phone is added and verified, and
  when an email is added and verified. Today only the first two happen, for
  phone only. [desc] [U5]
- **FR6.6** Matching never accepts on the person's behalf: a newly linked seat
  is `pending` until its holder accepts or declines [BR5.1]. A seat already
  linked to another account is not re-linked.
- **FR6.7** The public already-added lookup used at sign-up accepts an email as
  well as a phone, with the same disclosure (that a teacher recorded the
  contact, never the name) and the same ceilings. [U4] [C-06]

Acceptance criteria:

- Given a teacher records `guardian_email = mother@example.com`, When an
  existing account adds and verifies `mother@example.com` in Settings, Then the
  seat appears in that account's invitations as pending.
- Given a teacher records a student with only an email, When that student signs
  up with the email, Then the student seat appears as pending.
- Given a teacher enters the same student email for two of their students, Then
  the second is refused as a duplicate.
- Given a centre invites `teacher@example.com`, When that address is verified on
  an account, Then the membership invitation appears for that account.

### FR7 Changing the username

- **FR7.1** A person may change their username in Settings, after confirming
  their password, subject to FR1. [desc] [assumption: password confirmation]
- **FR7.2** A username may be changed at most once every 30 days. Choosing the
  first username (FR5) does not count. [Q2]
- **FR7.3** When a username is released, by rename or by account deletion, it
  is held for 30 days. During the hold nobody else can take it; the person who
  released it by rename may take it back. After 30 days it is free. [Q1]
- **FR7.4** A hold left by a deleted account stores no username text: only a
  one-way digest of the lowercase form and the expiry, so no identifier of the
  deleted person is retained in readable form. [U14] [RC-4]
- **FR7.5** Changing the username does not sign the person out of any device;
  other signed-in devices show the new username on their next refresh.
  [assumption]

Acceptance criteria:

- Given `rahim_math` renamed to `rahim_m` today, When another person tries
  `rahim_math` within 30 days, Then it is refused as held; When `rahim_m`'s
  owner tries it, Then it is accepted.
- Given a rename today, When the same person tries another rename in 20 days,
  Then it is refused, naming when they can next change it.
- Given an account deleted today, When its old username is checked on day 31,
  Then it is available.

### FR8 Managing phone and email in Settings

- **FR8.1** A person may add a phone or an email in Settings by verifying a
  code sent to it, as today. [desc]
- **FR8.2** A person may replace or remove a phone or an email, after
  confirming their password, as long as at least one verified contact remains.
  Replacing means verifying the new one first, then the old one is removed.
  [Q3] [desc]
- **FR8.3** Removing a contact leaves every seat and membership already linked
  to the account linked. The removed contact becomes free for another account
  to use. [Q3]
- **FR8.4** Removing the last verified contact is refused with a message
  saying why, and the database's existing at-least-one-identifier constraint
  stays as the backstop. The stale "dormant account" prose is corrected in the
  same change. [desc] [U3] [U11]

Acceptance criteria:

- Given an account with a verified phone and a verified email, When the person
  removes the phone, Then it is removed and the account keeps its seats.
- Given an account with only a verified email, When the person tries to remove
  it, Then the removal is refused and the email stays.
- Given the person replaces their phone with a new number, When the new number
  is verified, Then the old number is gone and seats recorded against the new
  number are linked (FR6.5).

### FR9 Username is private to its owner

- **FR9.1** The username is visible only to the account that owns it. No
  teacher-lens, guardian-lens, student-lens, membership, class-teacher,
  examiner or platform-administrator response carries another account's
  username. [desc] [TC-13] [TC-14]
- **FR9.2** The username joins the hand-maintained owner-private field set in
  the schema-wide privacy gate, and the admin contract's forbidden-field list,
  and a test fails if the account username column exists without being in both.
  [U7]
- **FR9.3** No log line, audit row, notification, SMS or email contains a
  username. The authentication audit log records "username set" and "username
  changed" by account id only. [team: secrets leak through logs] [assumption]

Acceptance criteria:

- Given the generated OpenAPI schema, When the privacy gate walks every
  teacher-lens and admin response, Then no field named `username` appears.
- Given a guardian whose child has a username, When the guardian opens the
  child's dashboard, Then the child's username is not in the response.

### FR10 Deletion and recovery

- **FR10.1** "Forgot password" and both account-deletion paths keep asking for
  the phone or email the code is sent to; they do not accept a username. [Q6]
  [U16]
- **FR10.2** Deleting an account starts the 30-day hold on its username
  (FR7.3, FR7.4), and the deletion disposition and generated privacy policy
  name the hold, what it stores and when it is purged. [U14] [TC-19]

Acceptance criteria:

- Given an account deleted through the external route, When the deletion
  completes, Then the account row is gone and only a digest-and-expiry hold
  remains for its username.
- Given the hold's expiry has passed, When the scheduled purge runs, Then the
  hold row is gone.

### FR11 Both clients

- **FR11.1** Android and web each implement: the sign-up username field with
  the live availability check; the single sign-in field; the choose-username
  screen; Settings entries for viewing and changing the username and for
  adding, replacing and removing a phone or email; and the email fields on the
  teacher's student form and the centre invite form. [desc]
- **FR11.2** Every new user-facing string exists in Bangla and English, and
  each new or changed screen is entered in the Bangla layout check table
  (`docs/delivery/bangla-layout-check.md`) at the longest Bangla string. The
  verifier is that manual check; nothing automated discharges it.
  [TC-15] [D-43] [project: Corrections 2026-10-23]
- **FR11.3** Neither client decides whether a username is valid beyond format
  hints, whether one is required, or whether a contact may be removed; each
  shows what the server decided [TC-9]. Client-side format hints never refuse a
  value the server would accept.

## Non-functional requirements

- **NFR1 Anti-enumeration.** Sign-in by username, phone or email gives one
  refusal and indistinguishable responses for unknown, password-less and wrong
  credentials; the only endpoint that reveals username existence is the
  availability lookup (FR3), which reveals nothing else. Verified by tests that
  compare the full responses. [BR2.7]
- **NFR2 Rate limits.** Availability lookup: ceilings per IP, per /48 (IPv6) or
  equivalent prefix, and global, at values no looser than the existing
  already-added lookup. Username sign-in failures: 10 per username per hour
  plus the existing per-network ceilings. Rename: FR7.2. Each ceiling has a
  test that drives it to the limit and one past. [U13] [desc]
- **NFR3 Privacy boundary.** Username protection is structural, not per-query:
  the privacy gate (FR9.2) fails CI on any leak, and the privacy suite keeps
  running as the restricted non-superuser role. [TC-13] [project: Mandated]
- **NFR4 Test-first where the predicate holds.** Seat linking on a new email,
  lens and invitation effects of contact removal, and the last-contact refusal
  are authorization-adjacent with outputs knowable in advance, so their tests
  are written first. [team: Testing Posture]
- **NFR5 Coverage.** Backend line coverage stays at or above 80% with no
  decrease; any new backend package is added to the explicit `--cov` list;
  Android coverage does not decrease (the ratchet). [U17] [org: Testing Posture]
- **NFR6 Compatibility.** `/v1` stays additive: existing request shapes and
  response fields keep working, and both clients tolerate unknown fields.
  Installed clients that predate the change keep signing in. [D-26]
- **NFR7 Migration safety.** The schema change is forward-only and
  backward-compatible: the username column is nullable, no existing row is
  rewritten, and the migration runs as its own logged step before the new
  container serves traffic, rehearsed on staging first. [team: Deployment]
- **NFR8 Responsiveness.** The availability lookup answers within 300 ms at the
  95th percentile on staging under normal load, so the live check is usable
  while typing. [assumption]
- **NFR9 Committed contract.** Every API change is reflected in the committed
  `openapi.json`, enforced by the existing schema-diff gate. [team: Code Style]

## Constraints

- Children's data on a Play Families-track app: nothing a student or guardian
  writes reaches a teacher [TC-13]; administrators see no student or guardian
  data [TC-14]; data encrypted at rest. (`business-overview.md` § Constraints)
- The username cannot live on `profile`: that table's forced row-level security
  blocks the lookup sign-in has to do before authentication, so it lives on
  `account`, outside row-level security, protected by the response-schema gate.
  [U6] — recorded as a constraint for Domain Design, which owns the final
  schema.
- Business rules stay server-side; the clients render decisions [TC-9].
- Infrastructure spend stays under USD 50/month [OC-4]; this change adds no
  infrastructure.
- Solo build: important rules are mechanical (gates and tests), not review.

## Assumptions

- **A1** Seats and memberships linked through a contact stay linked after that
  contact is removed (Q3 answer). Reason: the link records what the teacher
  meant; the account still belongs to the person they meant.
- **A2** No invitation message is sent when a teacher records an email; "invited
  by email" means matched by email when the person verifies it, the same as
  phone today. Reason: the product sends no invitation SMS today.
- **A3** A username starting with a letter (FR1.2) satisfies "must not look like
  a phone number". Reason: every accepted phone spelling starts with a digit or
  `+`.
- **A4** Password confirmation is required for rename and for removing or
  replacing a contact. Reason: these change how the account is found and
  recovered; the existing account-security screens already confirm the
  password for comparable actions.
- **A5** Clients enforce the choose-username screen and the server does not
  block other routes (FR5.3). Reason: installed clients that predate the
  change must keep working.
- **A6** The rename limit and the hold are both 30 days, and the hold also
  applies on deletion. Reason: the shortest of the offered periods keeps the
  retained identifier minimal on a children's-data app.

## Out of scope

- Usernames for platform administrators (admin sign-in is unchanged).
- Showing usernames to anyone but their owner, including searching for people by
  username.
- Sending invitation emails or SMS when a teacher records a contact.
- Accepting a username in "forgot password" or in either deletion path (FR10.1).
- Bangla-script or other non-Latin usernames.
- Automated screenshot testing for the Bangla layout (the manual table is the
  verifier, per FR11.2).

## Open questions

- **OQ1** Where the hold lives and how its digest is computed (keyed or plain
  hash), and whether a renamed-away name held for its own account stores the
  name or a digest — Domain Design.
- **OQ2** Whether the case-insensitive uniqueness is a canonical lowercase
  column or a unique index on `lower(username)` — Domain Design. [U9]
- **OQ3** The exact ceiling values for the availability lookup — NFR
  Requirements, starting from the already-added lookup's values. [U13]
- **OQ4** Whether the single sign-in field is a new request type or a new
  optional field on the existing one — Contract Design. [U1] [U2]

## Sources

- Initial description: the change request recorded in
  `project-description.json` for this intent. [desc]
- Workflow-selected scope: custom plan `username-identity-cr` on `refactor`,
  Standard depth. [scope]
- Answers Q1–Q7 in `requirements-analysis-questions.md`, chosen as recommended
  on the person's instruction "Go with your recommendations". [Q1]–[Q7]
- Code knowledge base, 2026-11-13: `business-overview.md`, `architecture.md`,
  `code-structure.md`, `api-documentation.md`, `code-quality-assessment.md`
  (findings U1–U17).
- Project and team rules: `aidlc/spaces/default/memory/project.md`, `team.md`.
- Items marked [assumption] are listed under Assumptions with their reason.
