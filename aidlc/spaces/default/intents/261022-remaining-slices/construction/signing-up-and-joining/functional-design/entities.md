# Entities — D1 `signing-up-and-joining`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **D1 creates no table.** It adds two columns to `Enrollment`, one to
> `Profile`, and nothing else. The four entities are stated in full anyway,
> because the design is about what the new columns mean *beside* the ones
> already on those rows — and that cannot be read from a diff.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D1's schema scope
- [upstream] `inception/domain-design/components.md` — the component catalogue
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.7a,
  FR1.9a–FR1.9i, FR1.16, FR1.17
- [upstream] `inception/user-stories/stories.md` — US1.10 through US1.16
- [prior] `inception/domain-design/decisions.md` — ADR-009, ADR-010, ADR-013
- [code] `app/db/models.py`, read 2026-10-23

---

```yaml
entities:

  - name: Account
    description: >
      A person's identity, keyed by mobile number. Carries no name and no
      personal data: those live on Profile, the only table whose
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
          - One account per number. This uniqueness is what makes AC1.12.4 a
            constraint reporting itself rather than a lookup someone writes.
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
        description: >
          D6 owns both deletion paths. D1's only obligation here is negative:
          nothing it does may clear a decision column [BR6.1].

  - name: Profile
    description: >
      The private, self-authored side of a person, behind a row-level-security
      policy keyed on the session account id. Signup's personal data lands
      here and not on Account for exactly that reason [ADR-010].
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
          Self-authored, and a teacher never sees it [BR3.1]. Signup's full
          name populates THIS field; no third name column is added [ADR-010].
      - name: photo_ref
        type: text
        required: false
      - name: address
        type: text
        required: false
        added_by_this_unit: true
        description: >
          Collected at signup [FR1.17]. Nullable because the already-added
          path can reach signup with the name pre-filled and no address yet.
          A single free-text field, as O1 draws it: Bangladesh addresses do
          not decompose cleanly into line/city/postcode.

          Adding the column does NOT enrol it in the privacy gate: the
          owner-private field set is matched by NAME and maintained by hand,
          so `address` joins it in this same unit [BR3.4].
    constraints:
      - >
        A Profile row now exists from signup rather than from a first edit,
        so Profile stops being optional. Signup creates Account and Profile
        in ONE transaction, because a failure between them would leave an
        account violating the assumption every later reader will make
        [BR3.3, ADR-010].

  - name: Owner
    description: >
      Marks an account as a teacher. The row's EXISTENCE is the teacher
      claim; there is no role column anywhere in this product [BR1.1 of
      identity-and-access].
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
      - Created at signup ONLY when the person chose Teacher [BR4.1].
      - Nothing verifies the claim [BR4.2].

  - name: Enrollment
    description: >
      A seat in a batch. ONE row carries BOTH links — student and guardian —
      because the seat IS the relationship. After D1 it carries two
      independent per-link pairs: a decision and an erasure marker.
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
          NULL while nobody has signed up on that number. After D1 this is
          NOT an acceptance signal and NOT a claimed signal: a named account
          may still be pending [BR5.1]. Four merged readers treat it as one
          or the other; see the sweep in rules.md.
      - name: guardian_account_id
        type: uuid
        required: false
        references: Account.id
      - name: display_name
        type: text
        required: true
        description: >
          Teacher-typed. What teachers see, and what survives a decline
          [ADR-012]. Never written by a profile edit [BR3.1].
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
          the seat's initial state, because a default lets a future insert
          skip the decision silently [ADR-013].
      - name: guardian_decision
        type: enum
        required: true
        added_by_this_unit: true
        allowed_values: [pending, accepted, declined]
        default: none
      - name: student_relink_blocked_at
        type: timestamp
        required: false
        description: >
          Set when the student erased. A SEPARATE axis from the decision,
          and both are read [BR6.2].
      - name: guardian_relink_blocked_at
        type: timestamp
        required: false
      - name: created_at
        type: timestamp
        required: true
    constraints:
      - >
        The decision columns and the erasure markers are two INDEPENDENT
        facts per link, and lens resolution reads both [BR6.2]. `accepted`
        beside a set erasure marker grants nothing, because the account that
        link named no longer exists.
      - >
        A decision is per LINK, never per row. One person's decision never
        speaks for the other [BR5.2] — except where both links name the SAME
        account, in which case one action moves both columns [BR5.3].
      - >
        Backfill is CONDITIONAL, not a column default: `accepted` where the
        link already names an account, `pending` otherwise. A plain default
        would withdraw a working lens from every student already signed in
        [ADR-013]; see functional-spec.md § 5.

relationships:
  - from: Account
    to: Profile
    cardinality: one-to-one
    direction: Profile.account_id -> Account.id
    note: Created together at signup, in one transaction [BR3.3].
  - from: Account
    to: Owner
    cardinality: one-to-zero-or-one
    direction: Owner.account_id -> Account.id
    note: Present only for a teacher [BR4.1].
  - from: Account
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.student_account_id -> Account.id
    note: >
      The student link. A row here does NOT imply a lens; the decision
      column does [BR1.1, ADR-014].
  - from: Account
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.guardian_account_id -> Account.id
    note: The guardian link, independent of the student link.
  - from: Batch
    to: Enrollment
    cardinality: one-to-many
    direction: Enrollment.batch_id -> Batch.id
    note: >
      Batch is owned by a merged unit and is unchanged here. D1 READS a
      batch's name, subject and fee to render an invitation [BR1.4] and
      writes nothing to it.
```

---

## The entity set, in a sentence each

**`Account`** is a phone number with an id. It holds no name, which is the
structural half of the privacy boundary: there is no personal field on it to
leak.

**`Profile`** is everything personal a person writes about themselves, behind
a row-level-security policy. D1 puts `address` here rather than on `Account`
because that policy already exists, and a second mechanism would be a filter
someone has to remember to apply.

**`Owner`** is the teacher claim, expressed as a row's existence rather than a
value. Signup creates it for Teacher and for nobody else.

**`Enrollment`** is where the unit's real change lands. It already carried two
per-link erasure markers; D1 adds two per-link decision columns beside them. A
reader who finds four per-link fields on one row should know the two pairs
answer different questions — *did this person refuse the seat* and *did this
person erase themselves* — and that both are read on every grant.

## The column whose meaning changes

`student_account_id` is unchanged in shape and changed in meaning, and that is
the riskiest thing in this unit's schema.

Before D1 it answered **"has this seat been claimed?"**, because under the
superseded model signing in *was* acceptance. After D1 it answers only **"has
someone signed up on this number?"** — a weaker fact — and *claimed* moves to
`student_decision = 'accepted'`.

Nothing in a migration makes the merged readers notice. `rules.md` carries the
sweep of all seven readers of the two link columns, with what each must do;
two of them are write paths D1 must fix in the same unit that changes the
meaning [BR7.1, BR7.2].

## What D1 does not add

No new table. No `role` column, here or anywhere. No third name: the signup
name **is** `profile.self_name`, and the teacher-typed
`enrollment.display_name` is untouched by it [ADR-010]. No timestamp recording
*when* a decision was made — nothing in V1 reads it, and the auth audit log
carries the events if a dispute ever needs reconstructing [ADR-009]. No reason
for a decline, and no decision history.

## Assumptions & Open Questions

- **Assumed**: `Batch` is unchanged by this unit, which the read-only use
  above states explicitly.
- **Assumed**: the decision columns are a database enum type rather than a
  check-constrained string. Either satisfies this design and the choice is
  Code Generation's; what the design fixes is that the three values are the
  only representable ones. Noted because this would be the schema's first
  enum, and the two forms differ in how a fourth value is later added
  [components.md].
