# Entities — usernames-backend (U1)

Intent `261113-unique-usernames`, unit U1. Source of truth for the data shape
this unit adds or changes. Grounded in the built model (`app/db/models.py`:
`Account` 451, `RateLimitCounter` 709, `AuthAuditLog` ~754, `PendingSignup`
797), in ADR-001, ADR-002, ADR-007, ADR-011 and ADR-012, in the C3 schema split
(`u1_adds`), and in the answers to Q1–Q5 of `functional-design-questions.md`.
Only attributes this unit adds, changes or relies on are listed; every other
column is unchanged. The contact columns' lifecycle (replace, remove) is U2's
and is not repeated here.

Two changes to C3's `u1_adds` follow from the answers: `pending_signup`
loses the planned `username_replacements` column (Q1: the bound is the
availability lookup's committed ceilings, not a counter inside the rolled-back
transaction), and `account` gains `username_reclaimed_at` (Q2: a second
reclaim in one rename window must count). U1 owns both tables' new columns, so
neither change touches U2.

```yaml
entities:
  - name: UsernameCandidate
    kind: value-object
    description: >
      What a person typed as a username, before it is accepted. Produced by the
      Usernames module from raw input; either valid (and then carries its key)
      or invalid (and then carries exactly one refusal key). Never stored.
    attributes:
      - name: text
        type: string
        required: true
        constraints:
          - "the raw input with leading and trailing whitespace removed (FR1.4)"
          - "kept exactly as typed otherwise: this is the display form (FR1.3)"
        max: 64
      - name: key
        type: string (derived)
        required: true
        constraints:
          - "the lowercase form of text; used for uniqueness, sign-in, holds and the reserved list"
        min: 3
        max: 20
      - name: refusal
        type: enum
        required: false
        allowed_values:
          - account.username.invalid_character
          - account.username.too_short
          - account.username.too_long
          - account.username.must_start_with_letter
          - account.username.bad_dot
          - account.username.reserved
        constraints:
          - "absent when the candidate is valid; exactly one value otherwise, chosen by the precedence in BR1.6"

  - name: LoginSubject
    kind: value-object
    description: >
      What the single sign-in field was classified as, on the server (ADR-003).
      A closed union of three shapes; the existing Identifier type is the
      first two and is not widened (ADR-003 alternatives rejected).
    attributes:
      - name: kind
        type: enum
        required: true
        allowed_values: [email, phone, username]
      - name: value
        type: string
        required: true
        constraints:
          - "email: the canonical address (trimmed, lowercased)"
          - "phone: the canonical +8801XXXXXXXXX"
          - "username: the trimmed, lowercased text; NOT validated against FR1 (BR4.2)"
        max: 254

  - name: Account
    kind: entity (owned by AccountDirectory; username half written by this unit)
    description: >
      An identity. This unit adds four nullable columns. AccountDirectory is
      their only writer. No existing row is rewritten by the migration (NFR7).
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: username
        type: string
        required: false
        max: 20
        min: 3
        constraints:
          - "the display form, as the person typed it after trimming (FR1.3)"
          - "owner-private: served only on MeResponse.username and UsernameChangeResponse.username (BR8.1)"
          - "null while the account has not chosen one; username_required is then true (FR5.1)"
      - name: username_key
        type: string
        required: false
        unique: true
        max: 20
        min: 3
        constraints:
          - "equals the lowercase form of username"
          - "plain uniqueness on this column is the case-insensitive uniqueness guarantee (ADR-001)"
          - "owner-private, like username, and never served at all"
      - name: username_changed_at
        type: timestamp with time zone
        required: false
        constraints:
          - "when the last ORDINARY rename happened; the rename window is [username_changed_at, username_changed_at + 30 days)"
          - "null until the first ordinary rename: neither sign-up nor the first choice sets it (FR5.4)"
          - "not moved by a reclaim (ADR-012) or by a case-only change (Q3)"
      - name: username_reclaimed_at
        type: timestamp with time zone
        required: false
        constraints:
          - "NEW (Q2). When the account last used its reclaim exemption"
          - "the exemption is unused in the current window while this is null or earlier than username_changed_at"
      - name: password_hash
        type: string
        required: false
        constraints: ["existing; read by sign-in and by rename's password confirmation, never written by this unit except the existing transparent rehash"]
      - name: phone
        type: string
        required: false
        constraints: ["existing, unchanged; one of the three sign-in subjects"]
      - name: email
        type: string
        required: false
        constraints: ["existing, unchanged; one of the three sign-in subjects"]
      - name: activated_at
        type: timestamp with time zone
        required: false
        constraints: ["existing; its docstring is corrected: set on the first successful verify, and no account is ever 'dormant' (FR8.4 second half)"]
    constraints:
      - "BOTH-OR-NEITHER: username and username_key are both null or both set, and when set username_key equals lower(username). A check of equality alone passes when either side is null, so the null case is written out (BR1.9)"
      - "username_key has the FR1 shape: 3 to 20 characters from a-z, 0-9, underscore and dot, starting with a letter, not ending with a dot, no two dots in a row. A backstop for a writer that bypassed the Usernames module; the reserved list is not in the database"
      - "existing: at least one of phone and email is present"
    relationships:
      - target: UsernameHold
        cardinality: "one account to zero or more holds"
        direction: "UsernameHold.releasing_account_id references Account.id; set to null when the account is erased"

  - name: UsernameHold
    kind: entity (owned by Usernames)
    description: >
      A released username that nobody else may take until held_until. Created
      in the same migration as, and after, the new account columns (ADR-002).
      Stores no username text, ever: only a keyed digest of the key.
    attributes:
      - name: key_digest
        type: string
        required: true
        unique: true
        min: 64
        max: 64
        constraints:
          - "identifier: lowercase hex of HMAC-SHA256 under SHIKKHOKPLUS_OTP_HMAC_KEY over the bytes of 'username-hold:v1:' followed by the username key (ADR-002, BR7.1)"
          - "the purpose prefix makes a hold digest unequal to any OTP digest, which is computed over 'phone:code'"
      - name: held_until
        type: timestamp with time zone
        required: true
        constraints:
          - "the moment of the latest release plus exactly 30 days (30 x 24 hours, UTC instants)"
          - "the hold is live while now is strictly earlier than held_until (BR7.2)"
          - "the purge's age column (BR7.7)"
      - name: releasing_account_id
        type: uuid
        required: false
        references: Account.id
        constraints:
          - "set by a rename or a reclaim to the account that gave the name up: that account alone may take it back while the hold is live"
          - "null for a hold placed by account deletion"
          - "set to null by the database when the referenced account is erased (foreign key with set-null)"
      - name: created_at
        type: timestamp with time zone
        required: true
        constraints: ["when this digest's row was first written; not changed by a later release of the same name"]
    constraints:
      - "one row per digest; a later release of the same name replaces held_until and releasing_account_id (latest release wins, ADR-002)"
    relationships:
      - target: Account
        cardinality: "zero or more holds to zero or one account"
        direction: "hold to the releasing account, optional"

  - name: PendingSignup
    kind: entity (owned by Registration)
    description: >
      The sign-up draft (existing). This unit adds the username. A draft never
      reserves its username (FR2.3).
    attributes:
      - name: username
        type: string
        required: false
        max: 20
        min: 3
        constraints:
          - "the candidate's text (trimmed, as typed), validated against FR1 and found available when the draft was saved"
          - "null only for a draft saved before this change was deployed; such a draft creates an account with no username (C1 direction, 2026-11-14)"
          - "replaced inside the verify transaction by a replacement username (ADR-011); the replacement is undone with everything else if that transaction rolls back"
          - "owner-private like the rest of the row, and read by no route"
      - name: otp_request_id
        type: uuid
        required: false
        constraints: ["existing; the verify that consumes this code completes this draft"]
    constraints:
      - "no username_replacements column (removed by Q1; see BR2.6)"
      - "existing: exactly one of phone and email"

  - name: RateLimitCounter
    kind: entity (owned by RateCeilings; existing table, new scope values)
    description: >
      The shared counter table. This unit adds five scope kinds. No column or
      constraint changes.
    attributes:
      - name: scope_kind
        type: enum (string, max 16)
        required: true
        allowed_values:
          - "un_fail_net_hour (16): failed username sign-ins per username and /64, window one hour, limit 10"
          - "un_fail_hour (12): failed username sign-ins per username across networks, window one hour, limit 30"
          - "un_lk_ip_hour (13): availability lookups and sign-up replacement attempts per /64 (IPv4 /24), window one hour"
          - "un_lk_ip48_hour (15): the same per /48 (IPv4 /24), window one hour"
          - "un_lk_global_hr (15): the same product-wide, window one hour, alert-only, never refuses"
        constraints:
          - "exact limits for the three un_lk_* scopes are NFR Requirements' (OQ3), no looser than lk_ip_hour 30, lk_ip48_hour 100 and lk_global_hour 1000"
      - name: scope_value
        type: string
        required: true
        max: 64
        constraints:
          - "un_fail_hour: 'u:' followed by the first 62 hex characters of SHA-256 over the username key"
          - "un_fail_net_hour: 'u:' followed by the first 62 hex characters of SHA-256 over the key, '|', and the /64 prefix"
          - "un_lk_ip_hour, un_lk_ip48_hour: the prefix, as the existing lookup scopes"
          - "un_lk_global_hr: the existing 'global' value"
          - "a 'u:' value can never equal a phone value ('+880...'), an email value ('e:...'), an account value ('acct:...') or a prefix"

  - name: AuthAuditLog
    kind: entity (owned by AuthAudit; existing table, new events)
    description: >
      The append-only authentication audit log. This unit adds two events.
      Rows carry the account id and never a username, contact, code or token.
    attributes:
      - name: event
        type: enum (string, max 32)
        required: true
        allowed_values:
          - "USERNAME_SET: the first username was set, at sign-up completion or by the first choice"
          - "USERNAME_CHANGED: an ordinary rename, a reclaim, or a case-only change"
      - name: account_id
        type: uuid
        required: true
        constraints: ["always present for the two new events"]
```

## Summary

U1 adds four nullable columns to `account` (`username`, `username_key`,
`username_changed_at`, `username_reclaimed_at`), one nullable column to
`pending_signup` (`username`), and one table, `username_hold`, whose identifier
is a keyed digest so that no released name is ever stored as text. Two value
objects exist only in memory: `UsernameCandidate`, the validated (or refused)
form of what was typed, and `LoginSubject`, the server's classification of the
single sign-in field. The shared `rate_limit_counter` gains five scope kinds,
all within its 16-character name and 64-character value columns, and the audit
log gains two events that carry only an account id.

Three shape decisions are worth reading before the rules. The account's
both-or-neither constraint is spelt out because an equality check alone passes
when either side is null. `username_changed_at` records only ordinary renames,
and the new `username_reclaimed_at` records the one reclaim each window allows.
And a hold names its releasing account only while that account exists: the
database clears the link at erasure, which turns a rename hold into a
nobody-may-take-it hold for the rest of its 30 days.
