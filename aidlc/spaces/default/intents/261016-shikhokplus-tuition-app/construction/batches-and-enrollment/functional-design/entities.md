# Entity Model — `batches-and-enrollment` (U4)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **U4 takes ownership of the two tables U3 created empty.** `Owner` and
> `Enrollment` exist as shells with a shape and no behaviour; this Unit
> extends their columns and becomes the only thing that writes them.
>
> Three entities carry a property in their shape rather than in the code
> that touches them, following B3's pattern: an `Owner` indirection that
> makes a subscription transferable, a `display_name` whose *table*
> answers the privacy question, and a `fee_amount` that is nullable so
> absence means inherit rather than zero.

## Sources

- [stage] `functional-design-questions.md`
- [upstream] `inception/units-generation/unit-of-work.md` — U4
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.3,
  US2.1–US2.8
- [upstream] `inception/user-stories/stories.md` — AC1.3.x, AC2.1.x–AC2.8.x
- [upstream] `inception/domain-design/components.md` — the entity catalogue
- [upstream] `inception/contract-design/contract-summary.md` — §B.4, §B.5, OQ-7
- [upstream] `construction/identity-and-access/functional-design/entities.md`
  — the shells this Unit extends
- [team] `## Code Style`, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
entities:

  # ---- Extended from U3's empty shells ----

  - name: Owner
    identifier: id
    attributes: [id, kind, account_id, state, plan, plan_valid_to, deleted_at]
    ownership: U4 owns behaviour; U3 created the table
    description: >
      A teacher's ownership of batches, and the anchor a subscription
      attaches to. Read by lens resolution since U3; written here first.
    constraints:
      - "THE INDIRECTION IS THE POINT [AC2.1.3]. A batch belongs to an Owner, never directly to an Account. Ownership can then transfer, and a subscription has something to attach to that is not a person's identity."
      - "ATTRIBUTES ARE THE UPSTREAM CATALOGUE'S [components.md]. An earlier draft invented `subscription_plan`, `subscription_status` and `created_at`; the real columns are `kind`, `state`, `plan` and `plan_valid_to`. Note Owner DOES carry a `deleted_at` -- it is Enrollment that does not."
      - "`state`, `plan` and `plan_valid_to` are the ONLY fields a platform administrator may ever read [TC-14, D-6]. Nothing here identifies a student, a guardian or a child."
      - One Owner per Account in V1. The column is not unique-constrained, because a second Owner is how a future handover would work and a constraint would have to be dropped under data.

  - name: Enrollment
    identifier: id
    attributes: [id, batch_id, student_account_id, guardian_account_id, display_name, guardian_phone, fee_amount, joined_on, inactive_from, relink_blocked_at, created_at]
    ownership: U4 owns behaviour; U3 created the table
    description: >
      A student's place in a batch, the teacher-typed display name and
      guardian contact, and the per-enrollment fee the fee cycle
      charges against.
    constraints:
      - "THE ATTRIBUTE LIST IS THE UPSTREAM CATALOGUE'S, VERBATIM [components.md]. An earlier draft of this document invented `account_id`, `fee_override`, `role` and `deleted_at`, and omitted `guardian_phone`, `joined_on` and `relink_blocked_at`. The Governance disposition manifest is written against the catalogue's column NAMES, so a divergence here makes U11's per-column dispositions unmappable onto the real schema."
      - "relink_blocked_at IS A PRIVACY MECHANISM, NOT BOOKKEEPING, and it is checked on U4's OWN add-student path. A phone number resolves to an account on first authentication, so without it an erased student whose number returns is silently reattached to their own erased history -- defeating the erasure invisibly. Dormant-enrollment resolution SKIPS any row carrying it; the teacher may enroll that number again, which creates a NEW enrollment with no link to the old."
      - "display_name and guardian_phone are TEACHER-typed and belong to the ENROLLMENT, not the account [AC2.2.2, ADR-003, FR2.6]. Both SURVIVE deletion of the person's account, because the teacher wrote them and they are the teacher's own contact record. The same person in two batches has two display names, and editing one does not touch the other or their Profile [AC2.3.2]."
      - "fee_amount is NULLABLE, and null means INHERIT the batch default [AC2.2.5]. Zero is a real fee of zero, which is a waiver and not an absence. A non-nullable column defaulting to 0 would make those indistinguishable and silently charge nothing."
      - "inactive_from is a DATE, not a timestamp, and its semantics are the subtlest thing in this Unit [AC2.4.1]: no cycle generates for a period beginning STRICTLY AFTER it, while the period CONTAINING it still generates in full."
      - "THERE IS NO deleted_at AND NO TOMBSTONE. Deletion is anonymize-in-place: student_account_id or guardian_account_id is set to NULL and the enrollment reverts to DORMANT [FR11.1]. `student_account_id IS NULL` therefore means dormant, and relink_blocked_at distinguishes NEVER-CLAIMED (null) from CLAIMED-THEN-ERASED (set) [AC1.3.6]."
      - guardian_account_id is PER ENROLLMENT [FR2.3]. One child may have different guardians recorded by different teachers, and a guardian of one enrollment is not thereby a guardian of another.
      - "The teacher-facing key is enrollment_id, NEVER a student account id [ADR-001]. Asserted schema-wide by U2's privacy gate, which already runs."
      - "U3's shell declared `account_id` and `role`. Reconciling those to `student_account_id` plus `guardian_account_id` is part of this Unit's migration, alongside BR5.0's lens-query correction -- the two are the same change."

  # ---- Owned by this Unit ----

  - name: Batch
    identifier: id
    attributes: [id, owner_id, name, teacher_display_name, collection_number, collection_channel, default_fee, fee_due_day, marksheet_visible, active, created_at]
    description: >
      A teacher's class. Carries the fee defaults every enrollment
      inherits unless it overrides them.
    constraints:
      - "owner_id, never account_id. The indirection AC2.1.3 requires."
      - "ATTRIBUTES ARE THE UPSTREAM CATALOGUE'S [components.md]. An earlier draft said `is_active` and dropped five real columns: `teacher_display_name`, `collection_number`, `collection_channel` and `marksheet_visible`. The last is U6's toggle and the two collection fields are U8's payment destination -- U4 creates the columns, later Units give them behaviour, exactly as U3 did for this table's shells."
      - "default_fee is a Money value: NUMERIC(12,2), never a float and never a bare Numeric [TC-7, D-20]. The money-column assertion B3 armed will now have something real to check — it was vacuous on U3."
      - "`collection_number` is a TEACHER-TYPED PAYMENT DESTINATION, NOT MONEY [components.md]. It must not acquire a money type, and `collection_channel` names which service it belongs to."
      - "fee_due_day is an INTEGER 1-31 with a CHECK constraint. 29, 30 and 31 are legal and clamp to the month's last day at generation time [AC2.1.2]; the clamp is U7's arithmetic, but the column must admit the value or the clamp never gets to run. BR3.3 allowlists it against the money gate, whose name tokens it matches."
      - "`active` drives the read-only collapsed state [AC2.6.2]. History stays reachable; nothing is deleted.

  - name: BatchSubject
    identifier: id
    attributes: [id, batch_id, name]
    description: >
      One subject taught in a batch. A row rather than a column because
      a batch has one or more [AC2.1.1].
    constraints:
      - A separate table rather than an array column, because U6 attaches exams to a subject and needs a key to reference.
      - "No created_at, matching the catalogue. It carries one on Batch and Enrollment and deliberately omits it here, so adding one would be invention rather than completeness."

  - name: ScheduleSlot
    identifier: id
    attributes: [id, batch_id, weekday, start_time, end_time]
    description: >
      One weekly recurring slot. U5 generates session instances from
      these; this Unit only records them.
    constraints:
      - "weekday is an INTEGER 0-6 with a CHECK constraint, not a string. A string admits 'Monday', 'monday' and 'Mon' as three different Mondays."
      - "start_time and end_time are TIME, not timestamps. A weekly recurrence has no date; the date arrives when U5 instantiates it."
      - "No timezone column. Bangladesh is a single zone and a column nobody sets is a column that eventually holds something wrong."

  - name: HiddenBatchPreference
    identifier: id
    attributes: [id, account_id, batch_id, hidden_at]
    description: >
      One person's choice to hide one inactive batch from their own
      list. Deliberately a separate table.
    constraints:
      - "A SEPARATE TABLE, not a column on Enrollment [AC2.6.3]. Hiding is PER VIEWER: a student hiding a batch must not hide it from the guardian or the teacher. A column on Enrollment would be shared by every lens that reads it, which is the bug this shape prevents."
      - "Keyed on account_id because the preference follows the PERSON across lenses, not the enrollment."
```

---

## Part B — `inactive_from`, which is where this Unit fails quietly

**Three separate assertions, because an implementation can satisfy any
two and miss the third** [AC2.4.1–AC2.4.5]:

| Assertion | What it prevents |
|---|---|
| No cycle for a period starting **strictly after** the date | Charging a student who left |
| The period **containing** the date still generates **in full** | Silently waiving a month the teacher taught |
| Other enrollments of the same student are **unaffected** | One batch's decision leaking into another |

> **The second is the one that looks wrong and is right.** Marking a
> student inactive on the 10th does not prorate that month: the period
> charges in full unless the teacher adjusts it [AC2.4.5]. An
> implementer who "fixes" this to prorate has written a money bug that
> no test outside this Unit would catch, which is why `team.md`'s
> predicate puts `inactive_from` under test-first.

It is **money-adjacent and fails quietly**, so all three are named
tests rather than one test with three assertions — a single test
reports one failure and stops.

---

## Part C — What the shapes buy

| Entity | The shape | What it prevents |
|---|---|---|
| `Owner` | An indirection, not an account id | A subscription anchored to a person who cannot hand the batch over |
| `Enrollment.fee_amount` | Nullable | Zero (a waiver) reading as absent (inherit) |
| `Enrollment.display_name` | On the enrollment | A teacher's edit reaching the student's own profile |
| `HiddenBatchPreference` | A table, not a column | One viewer's hide affecting every other viewer |
| `ScheduleSlot.weekday` | Integer + CHECK | Three spellings of Monday |

And one in an **absence**: there is still **no role column** anywhere.
A student in one batch and a guardian in another is two `Enrollment`
rows with different `role` values — which is a property of the
enrollment, not of the account [BR1.1 of U3].

---

## Assumptions & Open Questions

**One, and it is settled here rather than carried.** [assumption] OQ-7
asks whether a guardian's selected child travels in the lens hint or as
a route parameter. It is settled in `rules.md` BR5.1 as a **path
parameter**, because the hint is explicitly non-authoritative [D-2] and
a privacy-relevant selection must not ride a field the server is
required to distrust.
