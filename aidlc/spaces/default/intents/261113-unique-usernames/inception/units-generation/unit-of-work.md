# Units of Work — Unique usernames

Intent `261113-unique-usernames`. Four units, grouped from the fifteen
components in `inception/domain-design/components.md` (ADR-001 to ADR-012 in
`decisions.md`) and covering FR1–FR11 of `requirements.md`. The decomposition
was approved as a plan before these files were written (units-generation
questions Q1–Q4). The walking skeleton does not apply: the plan runs with the
skeleton off, and the skeleton built in B3 does not recur (team.md).

Topology only: which unit can depend on which is in
`unit-of-work-dependency.md`. This file does not choose a build order.

## Unit table

| Unit ID | Directory | Name | Kind | Size | Deploys as |
|---|---|---|---|---|---|
| U1 | `u1-usernames-backend` | usernames-backend | service | L | Embedded in the existing backend container (modular monolith) |
| U2 | `u2-contacts-and-invites-backend` | contacts-and-invites-backend | service | L | Embedded in the existing backend container (modular monolith) |
| U3 | `u3-android-identity` | android-identity | ui | L | The Android app, on its own release cadence |
| U4 | `u4-web-identity` | web-identity | ui | M | The web app, on its own release cadence |

## U1 — usernames-backend

**Description.** Everything that makes a username exist, sign someone in, and
stay private, on the backend.

**Components.** Usernames (new), and the username halves of AccountDirectory,
Registration, SignIn, AccountSettings (rename), RateCeilings, AuthAudit,
AccountDeletion, IdentityApi and PrivacyGate.

**Owns and delivers.**

- Migration: `account.username`, `account.username_key` (UNIQUE, CHECK equals
  `lower(username)`), `account.username_changed_at`, `pending_signup.username`
  and its replacement counter, and the `username_hold` ledger created after the
  account columns (ADR-001, ADR-002).
- The Usernames module: format rules and refusal keys, canonical key, reserved
  list, the hold ledger with its keyed digest, upsert and purge (FR1, FR7.3,
  FR7.4).
- Sign-up with a username, the rollback-and-retry on a username taken during
  verification (ADR-011), and the username-set audit event (FR2.1–FR2.4).
- One-field sign-in, uniform refusal, and the username failure ceilings
  (ADR-003, ADR-007; FR4).
- The availability lookup, public and authenticated, with its ceilings and the
  public-route allowlist update (FR3; ADR-007 amends FR3.1).
- `username_required` on `GET /v1/me` and the sign-in success response (FR5,
  ADR-008).
- Rename and reclaim with the rename limit (FR7.1, FR7.2, FR7.5; ADR-012).
- The deletion hold, its disposition entry and the regenerated privacy policy
  (FR10.2).
- The privacy gate entries and the membership test (FR9; ADR-010); the
  OTP-key rotation runbook line (ADR-002).
- Correcting the stale "dormant account" prose (FR8.4's second sentence).

**Implementation notes and constraints.**

- Test-first where the authorization or money predicate holds (team.md,
  Testing Posture): uniform refusal across unknown, password-less and wrong;
  the per-network failure ceiling cannot lock out another network; reclaim
  allowed once, rename limit otherwise; the privacy gate catches a leak.
- Two review findings accepted at the Domain Design gate are settled in this
  unit's Functional Design: the replacement cap at sign-up must be counted
  where a rollback cannot undo it (R-09), and repeated reclaims must not
  bypass the rename limit (R-10).
- `app.auth` is outside the mypy strict islands; any new username module lands
  in a strict package. New packages join the `make test` coverage list.

## U2 — contacts-and-invites-backend

**Description.** Recording people by email as well as phone, matching accounts
to those records when a contact is verified, and letting an owner replace or
remove a contact.

**Components.** ContactMatching (new), StudentRoster, CentreMembership, and the
contact halves of AccountDirectory, Registration (matching at creation),
AccountSettings, RateCeilings, AuthAudit and IdentityApi.

**Owns and delivers.**

- Migration: `student.student_email`, `student.guardian_email`,
  `enrollment.student_email`, `enrollment.guardian_email`,
  `owner_member.invited_email`, `owner_member.invited_phone` made nullable with
  an at-least-one CHECK, and the uniqueness rules of ADR-009.
- Teacher and centre request and response fields for those emails (FR6.1–FR6.4).
- ContactMatching and the owners' link statements with the one precedence rule
  of ADR-005 (FR6.5, FR6.6), called at account creation, phone add and email
  add.
- The already-added lookup by email (FR6.7).
- Contact replace and remove with password confirmation, the at-least-one
  rule, the removed-contact notice and the change ceiling (FR8; ADR-006).

**Implementation notes and constraints.**

- Test-first (the authorization predicate holds): an email never links a
  record that records a phone; the phone's owner signing up after the email's
  owner still takes the seat; a recycled contact links only unlinked records;
  links are pending, never accepted; removing the last contact is refused.
- Existing relink rules for phone (`_apply_identity`, `_refuse_relink`) extend
  to email unchanged.
- `email` is already a staff-private field name (U8): teacher-recorded emails
  are named `student_email` and `guardian_email`.

## U3 — android-identity

**Description.** The Android screens for everything U1 and U2 expose.

**Components.** AndroidIdentityScreens.

**Owns and delivers.** Sign-up username field with the live availability
check; the single sign-in field; the choose-username screen driven by
`username_required`; Settings entries for the username (view, rename, reclaim)
and for contacts (add, replace, remove); the email fields on the teacher's
student form and the centre invite form (FR11.1). Bangla and English strings,
and each new or changed screen entered in the manual Bangla layout table
(FR11.2). Format hints never refuse what the server accepts (FR11.3).

**Implementation notes and constraints.** ViewModel state-machine tests for
each new screen, including the retry path for a failed write (team.md). No
client-side business rule [TC-9]. The Kotlin coverage ratchet must not
decrease. No new third-party dependency is expected; any that appears needs an
SDK admission note against the forbidden-identifier set.

## U4 — web-identity

**Description.** The web app's equivalents of U3.

**Components.** WebIdentityScreens.

**Owns and delivers.** The same screens and behaviour as U3 on the web client
(FR11.1–FR11.3).

**Implementation notes and constraints.** Same rules as U3. Smaller than U3:
the web client has no store release or Bangla layout table of its own beyond
the same manual check for each new screen.
