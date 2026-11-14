# Entities — contacts-and-invites-backend (U2)

Intent `261113-unique-usernames`, unit U2. Source of truth for the data shape
this unit adds or changes. Grounded in the built model (`app/db/models.py`:
`Account` 451, `OwnerMember` 943, `Student` 1014, `Enrollment` 1079), in
ADR-005, ADR-006 and ADR-009, and in the C3 schema split. Only attributes this
unit adds, changes or relies on are listed; every other column is unchanged.
The username columns on `Account` and the `UsernameHold` ledger are U1's and are
not described here.

```yaml
entities:
  - name: ContactValue
    kind: value-object
    description: >
      A verified or recorded phone number or email address, tagged with its
      kind. The existing Identifier type is this value. Equality is on the
      canonical form, so two spellings of one contact are one contact.
    attributes:
      - name: kind
        type: enum
        required: true
        allowed_values: [phone, email]
      - name: value
        type: string
        required: true
        constraints:
          - "phone: canonical +8801XXXXXXXXX, from any accepted spelling"
          - "email: trimmed, lowercased, one @, no whitespace, a dot in the domain"
        max: 254
      - name: rate_key
        type: string (derived)
        required: true
        constraints:
          - "phone: the canonical number, as counters have always been keyed"
          - "email: 'e:' followed by 62 hex characters of SHA-256 over the lowercased address"
        max: 64

  - name: Account
    kind: entity (owned by AccountDirectory; contact half written by this unit)
    description: >
      An identity. This unit adds no column to it. It changes the contact
      columns' lifecycle: a phone or an email may now be replaced or removed,
      and a removed one is free for another account.
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: phone
        type: string
        required: false
        unique: true
        max: 20
        constraints: ["canonical form; present only after its code was verified"]
      - name: email
        type: string
        required: false
        unique: true
        max: 254
        constraints: ["lowercased; present only after its code was verified"]
      - name: password_hash
        type: string
        required: false
        constraints: ["read to confirm a replacement or removal; never written by this unit"]
    constraints:
      - "ck_account_has_identifier: phone or email is present (existing; the backstop for BR5.5)"
      - "Every stored contact is verified: nothing writes a contact column without a spent code, so 'stored' and 'verified' are the same set"
    relationships:
      - {to: Enrollment, cardinality: "0..1 to 0..*", direction: "Enrollment.student_account_id -> Account (SET NULL)"}
      - {to: Enrollment, cardinality: "0..1 to 0..*", direction: "Enrollment.guardian_account_id -> Account (SET NULL)"}
      - {to: OwnerMember, cardinality: "0..1 to 0..*", direction: "OwnerMember.account_id -> Account (SET NULL)"}
      - {to: OtpRequest, cardinality: "0..1 to 0..*", direction: "OtpRequest.requested_by_account_id -> Account (SET NULL)"}

  - name: Student
    kind: entity (owned by StudentRoster)
    description: >
      A teacher's record of one student. Gains the two teacher-recorded
      emails. Teacher-written data, visible to that teacher only.
    attributes:
      - name: owner_id
        type: uuid
        required: true
        references: Owner.id
      - name: student_phone
        type: string
        required: false
        max: 20
        constraints: ["canonical; unique per owner (existing uq_student_owner_phone)"]
      - name: guardian_phone
        type: string
        required: false
        max: 20
      - name: student_email
        type: string
        required: false
        max: 254
        default: null
        constraints:
          - "NEW. Canonical lowercased email (same rule as ContactValue email)"
          - "Unique per owner among that owner's students, archived included, where present (mirrors uq_student_owner_phone)"
      - name: guardian_email
        type: string
        required: false
        max: 254
        default: null
        constraints:
          - "NEW. Canonical lowercased email"
          - "Not unique: one guardian is recorded on many children, as guardian_phone is"
      - name: archived_at
        type: timestamp
        required: false
    constraints:
      - "student_email and student_phone may both be absent (a record with a name only), as today for the phone"
    relationships:
      - {to: Enrollment, cardinality: "1 to 0..*", direction: "Enrollment.student_id -> Student"}

  - name: Enrollment
    kind: entity (owned by StudentRoster)
    description: >
      A seat: one student in one batch, carrying two links (student and
      guardian) and a synchronized copy of the student's recorded contacts.
      The copy is what linking matches against.
    attributes:
      - name: student_phone
        type: string
        required: false
        max: 20
        constraints: ["copy of Student.student_phone, written in the same transaction"]
      - name: guardian_phone
        type: string
        required: false
        max: 20
        constraints: ["copy of Student.guardian_phone"]
      - name: student_email
        type: string
        required: false
        max: 254
        default: null
        constraints: ["NEW. Copy of Student.student_email, written in the same transaction"]
      - name: guardian_email
        type: string
        required: false
        max: 254
        default: null
        constraints: ["NEW. Copy of Student.guardian_email, written in the same transaction"]
      - name: student_account_id
        type: uuid
        required: false
        references: Account.id
        constraints: ["at most one seat per (batch_id, student_account_id) (existing uq_enrollment_batch_student)"]
      - name: guardian_account_id
        type: uuid
        required: false
        references: Account.id
      - name: student_decision
        type: enum
        required: true
        allowed_values: [pending, accepted, declined]
        constraints: ["never written by linking (BR3.4); stated on every insert, no default (ADR-013)"]
      - name: guardian_decision
        type: enum
        required: true
        allowed_values: [pending, accepted, declined]
      - name: student_relink_blocked_at
        type: timestamp
        required: false
        constraints: ["set at erasure; a blocked link is never linked again (BR3.6)"]
      - name: guardian_relink_blocked_at
        type: timestamp
        required: false
    constraints:
      - "A link's recorded phone is <role>_phone and its recorded email is <role>_email, for role in {student, guardian}"
      - "A teacher contact edit or seat creation locks the student's seat rows (ascending id) before reading decisions or blocked markers; decision, erasure and match writes change a row only under a condition on its current link (BR2.6)"
      - "The roster row and its response carry student_email and guardian_email beside guardian_phone (BR1.11)"
      - "Guardian link is 'absent' only when guardian_phone, guardian_email and guardian_account_id are all absent (BR1.6)"
    relationships:
      - {to: Student, cardinality: "0..* to 1", direction: "Enrollment.student_id -> Student"}
      - {to: Account, cardinality: "0..* to 0..1", direction: "student link"}
      - {to: Account, cardinality: "0..* to 0..1", direction: "guardian link"}

  - name: OwnerMember
    kind: entity (owned by CentreMembership)
    description: >
      A centre's invitation to a member, now by phone, by email or both.
    attributes:
      - name: owner_id
        type: uuid
        required: true
        references: Owner.id
      - name: account_id
        type: uuid
        required: false
        references: Account.id
      - name: invited_phone
        type: string
        required: false
        max: 20
        constraints:
          - "CHANGED: was NOT NULL, becomes nullable (ADR-009)"
          - "Live phone unique per centre (existing uq_owner_member_live_phone)"
          - "Legacy manager rows may hold '' (empty); read as absent, never written by new code (Q3)"
      - name: invited_email
        type: string
        required: false
        max: 254
        default: null
        constraints:
          - "NEW. Canonical lowercased email"
          - "Live email unique per centre: unique on (owner_id, invited_email) where revoked_at is absent and invited_email is present"
      - name: decision
        type: enum
        required: true
        allowed_values: [pending, accepted, declined]
        constraints: ["never written by linking"]
      - name: revoked_at
        type: timestamp
        required: false
        constraints: ["a revoked invitation is never linked"]
    constraints:
      - "NEW CHECK: invited_phone or invited_email is present"
    relationships:
      - {to: Account, cardinality: "0..* to 0..1", direction: "OwnerMember.account_id -> Account (SET NULL)"}

  - name: OtpRequest
    kind: entity (owned by the existing OTP module; one column added by this unit)
    description: >
      An issued code. Gains the account that requested a replacement code
      after confirming its password, so the verify can only be completed by
      that account (Q1).
    attributes:
      - name: phone
        type: string
        required: false
      - name: email
        type: string
        required: false
      - name: purpose
        type: string
        required: true
        allowed_values: [otp, deletion, contact, contact_replace]
        max: 32
        constraints: ["contact_replace is NEW (15 characters)"]
      - name: requested_by_account_id
        type: uuid
        required: false
        references: Account.id
        default: null
        constraints:
          - "NEW. Set only for purpose contact_replace; absent for every other purpose"
          - "On account deletion set to absent; an absent binding never matches a verifying account"
    constraints:
      - "purpose = contact_replace implies requested_by_account_id was present when issued"
      - "A replacement verify selects by (destination, purpose contact_replace, requested_by_account_id = verifying account), latest unexpired first; another account's rows are never selected or attempted (BR5.3)"

  - name: RateLimitCounter
    kind: entity (owned by RateCeilings)
    description: >
      Existing counter table. This unit adds one scope and reuses the four
      already-added lookup scopes for email.
    attributes:
      - name: scope_kind
        type: string
        required: true
        max: 16
        allowed_values_added: [contact_chg_day]
      - name: scope_value
        type: string
        required: true
        max: 64
        constraints:
          - "contact_chg_day: the account id (36 characters)"
          - "lk_number_day for an email: ContactValue.rate_key ('e:' form)"
          - "contact_chg_day is incremented only inside the contact change's own transaction (no intermediate commit), so it commits or rolls back with the change (BR5.6)"
      - name: window_start
        type: timestamp
        required: true
      - name: count
        type: integer
        required: true
        min: 0

  - name: AuthAuditEvent
    kind: enumeration (owned by AuthAudit)
    description: Closed set of audit events; this unit adds two.
    attributes:
      - name: event
        type: enum
        required: true
        allowed_values_added: [CONTACT_REPLACED, CONTACT_REMOVED]
        constraints: ["rows carry the account id and correlation id only; never a phone, email, code, token or username"]

  - name: RemovedContactNotice
    kind: transient message (not persisted)
    description: >
      The best-effort notice sent after commit to a contact that was replaced
      or removed.
    attributes:
      - name: destination
        type: ContactValue
        required: true
        constraints: ["the removed contact; never logged"]
      - name: text
        type: fixed server template
        required: true
        constraints:
          - "says a contact was removed from a ShikkhokPlus account and to contact support if that was not them"
          - "never contains a username, the new contact, the account id or a code"
          - "SMS: one segment"
```

## Summary

U2 adds no new table. It adds two teacher-recorded email columns to `student`
and copies of them to `enrollment`, adds `invited_email` to `owner_member` and
relaxes `invited_phone` to nullable under an at-least-one CHECK, and adds one
nullable account binding to `otp_request` for replacement codes (Question 1;
an addition to C3's `u2_adds`, see `functional-spec.md` § Issues). Uniqueness
follows the phone everywhere it already exists: student email per teacher,
invited email per centre among live invitations, guardian email nowhere.

`Account` gains nothing, but its contact columns gain a lifecycle: replace and
remove, under the at-least-one rule whose backstop is the existing
`ck_account_has_identifier`. `ContactValue` is the existing `Identifier` type,
reused unchanged; its `rate_key` is what keys the email already-added lookup
counter. `RateLimitCounter` gains one scope, `contact_chg_day`.

Decisions on seats (`student_decision`, `guardian_decision`) and invitations
(`decision`) appear here because the most important property of this unit is
that nothing in it ever writes them.
