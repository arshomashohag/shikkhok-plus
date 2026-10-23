# Entities — D1 `signing-up-and-joining`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **Three of these four entities already exist.** D1 adds two columns to
> `Enrollment` and one to `Profile`, and creates no table. They are stated in
> full because the design is about what those columns mean beside the ones
> already there, which cannot be read from a diff.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D1's schema scope
- [upstream] `inception/domain-design/components.md` — the component catalogue
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.7, FR1.9,
  FR1.17
- [upstream] `inception/user-stories/stories.md` — US1.10 through US1.16
- [prior] `inception/domain-design/decisions.md` — ADR-009, ADR-010, ADR-013

---

```yaml
entities:

  - name: Account
    description: >
      A person's identity, keyed by mobile number. Carries no name and no
      personal data: those live on Profile, which is the only table whose
      row-level-security policy enforces owner-privacy.
    status: exists
    changed_by_this_unit: false
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: phone
        type: string
        required: true
        unique: true
        max_length: 20
        constraints:
          - One account per number. This is what makes AC1.12.4 a uniqueness
            answer rather than a lookup.
      - name: created_at
        type: timestamp
        required: true
      - name: activated_at
        type: timestamp
        required: false
        description: Set on first successful OTP verification.
      - name: deleted_at
        type: timestamp
        required: false
        description: D6 owns deletion; D1 only must not clear a decision.

  - name: Profile
    description: >
      The private, self-authored side of a person. Protected by a row-level
      security policy keyed on the session account id, which is why signup's
      personal data lands here and not on Account [ADR-010].
    status: exists
    changed_by_this_unit: true
    attributes:
      - name: account_id
        type: uuid
        required: true
        unique: true
        references: Account.id
      - name: self_name
        type: text
        required: false
        description: >
          Self-authored. A teacher never sees it [BR3.1]. Signup's full name
          populates THIS field rather than adding a third name [ADR-010].
      - name: photo_ref
        type: text
        required: false
      - name: address
        type: text
        required: false
        added_by_this_unit: true
        description: >
          Collected at signup [FR1.17]. Nullable because the already-added
          path can reach signup with the name filled and the address not.
    constraints:
      - A Profile row now exists from signup rather than from first edit, so
        Profile is no longer optional. Signup creates Account and Profile in
        one transaction, because a failure between them would leave an account
        violating that assumption [ADR-010].

  - name: Owner
    description: >
      Marks an account as a teacher. Its presence IS the teacher claim; there
      is no role column anywhere [BR1.1].
    status: exists
    changed_by_this_unit: false
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: account_id
        type: uuid
        required: true
        unique: true
        references: Account.id
      - name: created_at
        type: timestamp
        required: true
    constraints:
      - Created at signup ONLY when the person chose Teacher [AC1.11.1].
        Nothing verifies the claim [AC1.11.5].

  - name: Enrollment
    description: >
      A seat in a batch. One row carries BOTH links — the student and the
      guardian — because the seat IS the relationship. There is no role
      column [BR1.1].
    status: exists
    changed_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: batch_id
        type: uuid
        required: true
        references: Batch.id
      - name: student_account_id
        type: uuid
        required: false
        references: Account.id
        description: >
          NULL while nobody has signed up on that number. NOT an acceptance
          signal: a named account may still be pending [AC1.12.3].
      - name: guardian_account_id
        type: uuid
        required: false
        references: Account.id
      - name: display_name
        type: text
        required: true
        description: >
          Teacher-typed. What teachers see, and what survives a decline
          [ADR-012].
      - name: guardian_phone
        type: string
        required: false
        max_length: 20
      - name: fee_amount
        type: money
        required: false
      - name: joined_on
        type: date
        required: false
      - name: inactive_from
        type: date
        required: false
      - name: student_decision
        type: enum
        required: true
        added_by_this_unit: true
        allowed_values: [pending, accepted, declined]
        default: none
        description: >
          NO column-level default, deliberately: every insert path must state
          the seat's initial state, because a default would let a future
          insert skip the decision silently [ADR-013].
      - name: guardian_decision
        type: enum
        required: true
        added_by_this_unit: true
        allowed_values: [pending, accepted, declined]
        default: none
      - name: student_relink_blocked_at
        type: timestamp
        required: false
        description: Set when the student erased. Independent of the decision.
      - name: guardian_relink_blocked_at
        type: timestamp
        required: false
      - name: created_at
        type: timestamp
        required: true
    constraints:
      - >
        The decision columns and the erasure markers are two INDEPENDENT facts
        per link, and both are read [ADR-009]. `accepted` plus a set erasure
        marker does not grant a lens, because the account it named no longer
        exists.
      - >
        A decision is per LINK, not per row. One person's decision never
        speaks for the other [AC1.10.6], even when both links name the same
        account — in which case both columns move together on one action
        [AC1.10.5].
      - >
        Backfill is CONDITIONAL, not a default: `accepted` where the link
        already names an account, `pending` otherwise. A plain default would
        withdraw a working lens from every student already signed in
        [ADR-013].

relationships:
  - from: Account
    to: Profile
    cardinality: one-to-one
    direction: Profile.account_id -> Account.id
    note: Created together at signup, in one transaction.
  - from: Account
    to: Owner
    cardinality: one-to-zero-or-one
    direction: Owner.account_id -> Account.id
    note: Present only for a teacher.
  - from: Account
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.student_account_id -> Account.id
    note: >
      The student link. A row here does NOT imply a lens; the decision column
      does [ADR-014].
  - from: Account
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.guardian_account_id -> Account.id
    note: The guardian link, independent of the student link.
  - from: Batch
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.batch_id -> Batch.id
    note: Batch is owned by a merged unit and is unchanged here.
```

---

## The entity set, in a sentence each

**`Account`** is a phone number with an id. It holds no name, which is the
structural half of the privacy boundary: there is no personal field on it to
leak.

**`Profile`** is everything personal a person writes about themselves, behind
a row-level-security policy. D1 adds `address` here rather than on `Account`
because that policy already exists and a second mechanism would be a filter
someone remembers to apply.

**`Owner`** is the teacher claim, expressed as a row's existence rather than a
value. Signup creates it only for Teacher.

**`Enrollment`** is where the unit's real change lands. It already carried two
per-link erasure markers; D1 adds two per-link decision columns beside them.
A reader seeing four per-link fields on one row should know that the two pairs
answer different questions — *did this person refuse the seat* and *did this
person erase themselves* — and that both are read.

## What D1 does not add

No new table. No `role` column, here or anywhere [BR1.1]. No third name: the
signup name is `profile.self_name`, and the teacher-typed
`enrollment.display_name` is untouched by it [ADR-010]. No timestamp recording
*when* a decision was made — nothing in V1 reads it, and the auth audit log
carries the events if a dispute needs reconstructing [ADR-009].

## Assumptions & Open Questions

- **Assumed**: `Batch` is unchanged by this unit. D1 reads a batch's name,
  subject and fee to render an invitation and writes nothing to it.
- **Assumed**: the enum is a database enum type rather than a check-constrained
  string. Either satisfies the design; the choice is Code Generation's, and the
  constraint that matters is that the three values are the only representable
  ones.
