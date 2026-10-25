# Entities — D4 `teaching-and-recording`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **D4 creates six tables and inherits one column it must not re-create.**
> `Batch.marksheet_visible` already exists in `app/db/models.py:589`, as a
> non-null boolean, and its own docstring says so: *"U6's toggle; U4 only
> creates the column"* — prior-record unit numbering, where U6 maps forward
> to this unit. **D4 is the unit that makes the existing column mean
> something.** It adds no column for it and writes no migration for it.
>
> The concurrency mechanism is likewise **inherited, not invented**. ADR-006
> decided refuse-on-conflict and rejected three alternatives;
> `contract-summary.md` § B.8 fixed the wire shape down to the field name
> `base_attendance_version` and the reason it travels in the body. This unit
> implements that contract and re-opens none of it.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D4's scope, the
  manual pilot check, and what the unit does not own
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — the
  US3.x and US4.x rows mapping here
- [upstream] `inception/requirements-analysis/requirements.md` — FR0.1, FR0.2
- [upstream] `inception/domain-design/components.md` — the decision columns on
  `Enrollment`, which D4 reads and never writes
- [upstream] `inception/delivery-planning/bolt-plan.md` — Bolt 4's confidence
  hypothesis
- [prior] `261016-.../inception/domain-design/components.md` — the `Teaching`
  component, its five entities, and both governance manifest rows
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
  (queued writes refuse on conflict), ADR-008 (Teaching is one component)
- [prior] `261016-.../inception/contract-design/contract-summary.md` — § B.7
  idempotency, **§ B.8 the queued-write contract**
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  FR3.1–FR3.9, FR4.1–FR4.7, FR11.4, FR11.5, NFR5, NFR5.1
- [prior] `261016-.../inception/user-stories/stories.md` — AC3.0.x–AC3.5.x,
  AC4.1.x–AC4.4.x
- [code] `app/db/models.py`, `app/governance/dispositions.py`,
  `app/contract/privacy.py`, `app/errors/_classes.py`, `app/errors/codes.py`,
  `app/authz/lenses.py`, `app/fees/verification.py`, `tests/db/test_governance.py`
  — all read 2026-10-24

---

```yaml
entities:

  # ======================================================================
  # Created by this unit.
  # ======================================================================

  - name: Session
    description: >
      One instance of a class: a date and start time a batch actually met
      or is due to meet. **Materialised rows, not a computed view of the
      recurrence rule.** ScheduleSlot holds the weekly recurrence and its
      docstring already says sessions are generated from it; the reason
      the instances are rows is that attendance, the topic log and a
      reschedule all attach to a specific occurrence, and AC3.0.2
      requires a schedule change to leave past sessions untouched — which
      a computed view cannot do, because recomputing it moves history.
      This row also carries the concurrency version the whole offline
      queue turns on.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: batch_id
        type: uuid
        required: true
        references: Batch.id
        on_delete: cascade
      - name: batch_subject_id
        type: uuid
        required: false
        references: BatchSubject.id
        on_delete: set_null
        description: >
          Which subject this session taught. Nullable because an ad-hoc
          session [AC3.0.3] may be held before the teacher decides, and
          because a subject removed from the batch must not delete the
          history of the classes that taught it.
      - name: date
        type: date
        required: true
      - name: start_time
        type: time
        required: true
      - name: end_time
        type: time
        required: false
      - name: topic
        type: string
        required: false
        max_length: 2000
        description: >
          What was covered [FR3.2]. Null until the teacher writes it; an
          empty topic is a session nobody has logged, which is a
          different fact from a session logged as blank.
      - name: status
        type: enum
        required: true
        allowed_values: [scheduled, held, cancelled]
        default: scheduled
        description: >
          FR3.3's three states. `cancelled` forbids attendance [AC3.2.2]
          and is the only transition that does.
      - name: origin
        type: enum
        required: true
        allowed_values: [recurrence, ad_hoc]
        description: >
          Whether generation produced this row or a teacher created it
          [AC3.0.3]. **No default, on ADR-013's reasoning applied to a
          second column**: a later insert path that does not state the
          origin is a path that forgot to think about it, and generation
          must never re-create or delete an ad-hoc session.
      - name: attendance_version
        type: integer
        required: true
        default: 0
        min: 0
        description: >
          The optimistic-concurrency version for the attendance roster
          [ADR-006, § B.8]. Incremented by exactly one on every applied
          roster write. **Session-level, not batch-level and not
          enrollment-level** — see the note under BR3.3 for what that
          chooses and what it costs.
      - name: topic_version
        type: integer
        required: true
        default: 0
        min: 0
        description: >
          The same mechanism for the other queued path, the topic log
          [FR3.6]. A separate counter rather than one shared with
          attendance, because a teacher logging a topic must not conflict
          with a roster submitted from another device: sharing one counter
          would manufacture conflicts between two writes that touch
          disjoint columns.
      - name: created_at
        type: timestamp
        required: true
    entity_constraints:
      - 'UNIQUE (batch_id, date, start_time). AC3.0.1 identifies a session
        by its date and start time, so two rows for one occurrence is the
        duplicate this prevents. It is also what makes recurrence
        generation re-runnable: generation inserts with ON CONFLICT DO
        NOTHING and a conflict is the success path [BR1.3], the same shape
        D3 used for (enrollment_id, period) and `RateLimitCounter` used
        before it.'
      - 'A session whose status is `cancelled` accepts no attendance write
        [BR1.6]. Enforced in the write path rather than by a database
        constraint, because the forbidden thing is a row in another table.'
    relationships:
      - 'Batch 1 — 0..* Session'
      - 'BatchSubject 0..1 — 0..* Session'
      - 'Session 1 — 0..* Attendance'

  - name: Attendance
    description: >
      One enrollment's presence at one session. The whole roster is
      written in a single atomic operation and never one row per student
      [AC3.1.5] — a per-student write leaves attendance half-saved after a
      mid-roster connection drop, and nothing on screen can reconcile
      that. A correction rewrites the roster and increments the version;
      the correction history is the audit trail, not a supersession
      chain, because attendance is a boolean per seat rather than a value
      with a history of its own.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: session_id
        type: uuid
        required: true
        references: Session.id
        on_delete: cascade
      - name: enrollment_id
        type: uuid
        required: true
        references: Enrollment.id
        on_delete: cascade
      - name: present
        type: boolean
        required: true
        description: >
          No third value. AC3.1.4 defaults every seat to present and the
          teacher marks only exceptions, so an unsubmitted roster is an
          absent Attendance row rather than a null column.
      - name: recorded_at
        type: timestamp
        required: true
      - name: recorded_by_account_id
        type: uuid
        required: true
        references: Account.id
        on_delete: set_null
        description: >
          Who marked it. Required by FR9.2's correction history and by the
          governance manifest's anonymize-on-teacher-deletion row.
      - name: submission_id
        type: uuid
        required: true
        references: AttendanceSubmission.id
        on_delete: cascade
        description: >
          Which accepted roster write produced this row. The replay key
          lives on that row rather than here, because all rows of one
          atomic write share one `client_mutation_id` — see
          AttendanceSubmission for why that forces a separate table.
    entity_constraints:
      - 'UNIQUE (session_id, enrollment_id). One row per seat per session.
        A roster re-submission replaces rather than appends [BR3.5].'
    relationships:
      - 'Session 1 — 0..* Attendance'
      - 'Enrollment 1 — 0..* Attendance'
      - 'AttendanceSubmission 1 — 1..* Attendance'

  - name: AttendanceSubmission
    description: >
      One accepted roster write. **A table rather than a column, and it is
      the piece the contract implies without naming.** § B.7 requires that
      a replayed `client_mutation_id` return the ORIGINAL stored result
      with 200 and never write a second time; the roster is many
      Attendance rows sharing one id, so the id cannot carry a unique
      constraint on Attendance without being unique per row, which is the
      opposite of what is wanted. This row is the single thing the
      constraint lives on, and the thing a replay reads back.
      **This is the shape D3's double-crediting defect had**: a write with
      no natural key to conflict on, guarded only by application logic.
      Here the key exists and is the constraint.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: session_id
        type: uuid
        required: true
        references: Session.id
        on_delete: cascade
      - name: submitted_by_account_id
        type: uuid
        required: true
        references: Account.id
        on_delete: cascade
      - name: client_mutation_id
        type: uuid
        required: true
      - name: base_version
        type: integer
        required: true
        min: 0
        description: >
          The `attendance_version` this roster was composed against
          [§ B.8]. Stored rather than discarded so a replay can be proved
          to be a replay of the same decision, and so the conflict rate is
          answerable from data during the pilot.
      - name: resulting_version
        type: integer
        required: true
        min: 1
        description: 'The version after this write applied. Always base_version + 1.'
      - name: composed_at
        type: timestamp
        required: false
        description: >
          Client-reported, from § B.8's example body. **Never used in any
          decision** — it is a device clock, and a device clock in a
          conflict rule would let a wrong phone time silently reorder two
          teachers' writes. Recorded for the pilot's queue-latency
          question only.
      - name: created_at
        type: timestamp
        required: true
    entity_constraints:
      - 'UNIQUE (submitted_by_account_id, client_mutation_id). The
        idempotency constraint § B.7 specifies, on the one row per write
        that can carry it.'
      - 'UNIQUE (session_id, resulting_version). Belt and braces on the
        version increment: two writes cannot both produce version N+1.
        This is the constraint that makes the guarantee survive a
        conditional update somebody later rewrites [BR3.4].'
    relationships:
      - 'Session 1 — 0..* AttendanceSubmission'
      - 'Account 1 — 0..* AttendanceSubmission'
      - 'AttendanceSubmission 1 — 1..* Attendance'

  - name: Exam
    description: >
      One assessment in one batch and subject [AC4.1.1]. Holds no result;
      results are Mark rows. `total_marks` is an integer count of marks
      and **not a money value** — it must never acquire a money type, for
      the same reason `Batch.collection_number` must not.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: batch_id
        type: uuid
        required: true
        references: Batch.id
        on_delete: cascade
      - name: batch_subject_id
        type: uuid
        required: true
        references: BatchSubject.id
        on_delete: restrict
        description: >
          `restrict` rather than `cascade` or `set_null`: deleting a
          subject must not silently destroy the exams and marks recorded
          under it, and an exam with no subject cannot satisfy AC4.1.1.
      - name: title
        type: string
        required: true
        max_length: 200
      - name: date
        type: date
        required: true
        description: >
          The exam date. Load-bearing beyond display: AC4.1.5 compares it
          against the enrollment's `joined_on` to distinguish "joined
          after the exam" from "absent" [BR4.3].
      - name: total_marks
        type: integer
        required: true
        min: 1
        description: >
          The denominator. At least 1, because a total of zero makes every
          percentage undefined and every band degenerate.
      - name: created_at
        type: timestamp
        required: true
    entity_constraints:
      - 'The batch_subject_id must belong to batch_id. A subject from
        another teacher''s batch would attach an exam across the
        ownership boundary [BR5.1].'
    relationships:
      - 'Batch 1 — 0..* Exam'
      - 'BatchSubject 1 — 0..* Exam'
      - 'Exam 1 — 0..* Mark'

  - name: Mark
    description: >
      One enrollment's result in one exam. **Append-only with a
      supersession chain**, the same shape `LedgerEntry` uses and for the
      same reason: AC3.1.7 and FR9.2 require a correction to be visible,
      and an UPDATE destroys the fact that a mark changed. A correction
      appends a new row and sets the old row's `superseded_by_id`.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: exam_id
        type: uuid
        required: true
        references: Exam.id
        on_delete: cascade
      - name: enrollment_id
        type: uuid
        required: true
        references: Enrollment.id
        on_delete: cascade
      - name: result_state
        type: enum
        required: true
        allowed_values: [marked, absent, not_entered, joined_after]
        description: >
          FR4.3's four states, and the enum is the point: a zero is a
          `marked` result with `marks` 0 and is never conflated with
          `absent`. `not_entered` is the state of a seat the teacher has
          not reached yet [AC4.1.4] and `joined_after` is a seat that
          could not have sat the exam [AC4.1.5]. **A client switches on
          this enum**, so adding a value is a breaking change under the
          contract's § B.1.1 rule.
      - name: marks
        type: integer
        required: false
        min: 0
        description: >
          Non-null if and only if `result_state` is `marked`. Nullable
          because the other three states have no number, and storing zero
          for them is exactly the conflation FR4.3 forbids.
      - name: recorded_at
        type: timestamp
        required: true
      - name: recorded_by_account_id
        type: uuid
        required: true
        references: Account.id
        on_delete: set_null
      - name: superseded_by_id
        type: uuid
        required: false
        references: Mark.id
        on_delete: set_null
        description: >
          Null on the live row. Set on an older row when a correction
          replaces it. The live result for a seat is the one row with a
          null `superseded_by_id` [BR4.5].
      - name: created_at
        type: timestamp
        required: true
    entity_constraints:
      - 'CHECK: (result_state = `marked`) = (marks IS NOT NULL). A
        database constraint rather than a validator, because this is the
        invariant the four-state requirement reduces to and a validator is
        bypassed by every write path that forgets it.'
      - 'CHECK: marks <= the exam''s total_marks. Cannot be a single-table
        CHECK in PostgreSQL since it spans a foreign key, so it is
        enforced in the write path and asserted by a test [BR4.2].'
      - 'At most one row per (exam_id, enrollment_id) with
        superseded_by_id IS NULL. A partial unique index — the same shape
        as `uq_enrollment_batch_student`, which is already built and
        already partial. Without it a correction that fails to set the
        old row''s pointer leaves two live marks and the marksheet
        silently counts one student twice.'
    relationships:
      - 'Exam 1 — 0..* Mark'
      - 'Enrollment 1 — 0..* Mark'
      - 'Mark 0..1 — 0..1 Mark (supersession, self-referential)'

  - name: Announcement
    description: >
      One note a teacher posted to a batch [FR3.8]. Soft-deleted rather
      than removed, because AC3.3.3 requires it to disappear from student
      and guardian views while FR9.2's correction history and the
      governance manifest's "stays with the batch's history" basis both
      require the fact of it to survive.
    status: new
    owned_by_this_unit: true
    attributes:
      - name: id
        type: uuid
        required: true
        unique: true
      - name: batch_id
        type: uuid
        required: true
        references: Batch.id
        on_delete: cascade
      - name: body
        type: string
        required: true
        max_length: 4000
      - name: created_at
        type: timestamp
        required: true
      - name: edited_at
        type: timestamp
        required: false
        description: >
          Null until edited. Its non-null-ness IS the "shows as edited"
          flag [AC3.3.2] — a separate boolean would be a second source of
          truth that can disagree with the timestamp.
      - name: deleted_at
        type: timestamp
        required: false
        description: 'Null while visible. Non-null hides it from every lens [AC3.3.3].'
      - name: posted_by_account_id
        type: uuid
        required: true
        references: Account.id
        on_delete: set_null
    entity_constraints:
      - 'No expiry column and no expiry job [AC3.3.4]. Stated as an
        absence because the obvious implementation of "announcements"
        adds one.'
    relationships:
      - 'Batch 1 — 0..* Announcement'

  # ======================================================================
  # Read and never written by this unit.
  # ======================================================================

  - name: Batch
    description: >
      Built, in `app/db/models.py:575`. D4 reads `marksheet_visible` and
      **writes it through exactly one route** [BR5.4] — the column exists
      and has always been non-null with no reader; this unit is the one
      that gives it an effect. Every other Batch column is read-only here.
    status: existing
    owned_by_this_unit: false
    attributes:
      - name: marksheet_visible
        type: boolean
        required: true
        description: >
          **No schema change.** The column is already non-null in the
          built model. AC4.2.1's "defaults to on" is satisfied by the
          existing batch-creation path stating `true`, which D2 owns; D4
          adds no default and no migration for it. Verified by reading
          the model rather than assumed.
      - name: active
        type: boolean
        required: true
        description: 'False collapses the batch to read-only history, which D4 honours for every write [BR5.5].'

  - name: Enrollment
    description: >
      Built, in `app/db/models.py:499`. D4 writes nothing here. It reads
      `student_decision` and `guardian_decision` to decide which seats
      appear on a roster and which lenses may read a result, and
      `joined_on` to distinguish `joined_after` from `absent`.
      **Adding a column is not adding a behaviour** — this project
      recorded that correction on 2026-10-22 — so the readers D4 adds are
      named individually in BR5.2 rather than left to inference.
    status: existing
    owned_by_this_unit: false
    attributes:
      - name: student_decision
        type: enum
        required: true
        description: 'Read by the roster query and by lens-scoped result reads.'
      - name: guardian_decision
        type: enum
        required: true
        description: 'Read by the guardian-facing attendance and progress reads.'
      - name: joined_on
        type: date
        required: false
        description: 'Compared against Exam.date for the `joined_after` state [BR4.3].'
      - name: inactive_from
        type: date
        required: false
        description: >
          Read by the roster query. An enrollment inactive before a
          session's date does not appear on that session's roster
          [BR1.5], which mirrors how D3 reads the same column for
          generation.

  - name: ScheduleSlot
    description: >
      Built, in `app/db/models.py:638`, and its docstring already names
      this unit's job: *"One weekly recurring slot. U5 generates sessions
      from these."* D4 reads the slots and writes none.
    status: existing
    owned_by_this_unit: false

  - name: BatchSubject
    description: >
      Built, in `app/db/models.py:610`. Its docstring already anticipates
      this unit: *"a separate table rather than an array because U6
      attaches exams to a subject and needs a key to reference."* D4 is
      the unit that attaches them.
    status: existing
    owned_by_this_unit: false

entity_constraints_global:
  - 'Every table this unit creates carries BOTH a disposition and a
    retention class in `app/governance/dispositions.py`, or
    `tests/db/test_governance.py` fails `make check` in both directions —
    it walks live `pg_tables` for undeclared tables and walks the manifest
    for declared tables that do not exist. Six new tables, twelve entries.
    The values are not invented here: the prior components catalogue
    already decided them [BR6.1].'
  - 'No column on any of these tables carries a money type. `total_marks`
    and `marks` are integer counts, and the built money-name gate in
    `app/contract/money_names.py` is what would catch a name that drifts.'

relationships_summary:
  - 'Batch 1 — 0..* Session — 1 — 0..* Attendance — 0..* — 1 Enrollment'
  - 'Session 1 — 0..* AttendanceSubmission (one row per accepted roster write)'
  - 'Batch 1 — 0..* Exam — 1 — 0..* Mark — 0..* — 1 Enrollment'
  - 'Mark 0..1 — 0..1 Mark (supersession)'
  - 'Batch 1 — 0..* Announcement'
```

---

## The entity set in prose

**Six new tables, and one of them is not in the upstream catalogue.** The
prior record's `Teaching` component names `Session`, `Attendance`, `Exam`,
`Mark` and `Announcement`. This design adds **`AttendanceSubmission`**, and
the reason is the one defect D3 shipped that is most likely to recur here.

§ B.7 requires a replayed `client_mutation_id` to return the original stored
result and never write twice. The upstream catalogue puts `client_mutation_id`
on `Attendance`. But a roster is *many* Attendance rows sharing *one* mutation
id, so a unique constraint on that column would either be per-row — which
makes it not unique for the write it is meant to protect — or absent, which
leaves idempotency to application logic. **That is precisely the shape of D3's
double-crediting race: a write with no natural key to conflict on.** The
submission row is the natural key. It costs one table and converts both
guarantees — replay-safety and the version increment — into database
constraints.

**The version is session-level, and that choice has a stated cost.** ADR-006
and § B.8 both name `session.attendance_version`, so this is implemented
rather than chosen. What follows from it is worth stating plainly: two
teachers marking *different students in the same session* from two devices
**do** conflict, and the second one is refused. The alternative granularities
are worse in ways that matter more — a batch-level version conflicts two
teachers working on unrelated sessions, and an enrollment-level version
destroys AC3.1.5's atomic roster, because per-seat versions are field
granularity and the roster deliberately has none. A co-teaching feature does
not exist in V1 (the batch has one `owner_id`), so the conflicting case is one
teacher on two devices, which is the case ADR-006 was written about.

**`topic_version` is separate from `attendance_version`** because the two
queued paths touch disjoint columns. One shared counter would refuse a topic
log because a roster arrived, which is a conflict the teacher cannot act on —
there is nothing to compare and nothing to re-apply differently.

**Three existing tables are read and one existing column is written.**
`Batch.marksheet_visible` is already built and already non-null; its docstring
says D4 only creates the column and a later unit uses it, using the prior
record's numbering where that later unit is this one. D4 therefore ships **no
migration** for the toggle and **one route** that writes it. This was verified
by reading `app/db/models.py:589` — the project's recorded correction is that
a claim about how a change fits built code is checked against the code.

**Deletion and retention are inherited, not decided here.** The prior
components catalogue already wrote both manifest rows for its five tables, and
`Disposition.RETAIN_WITH_BASIS` exists in the built enum with a docstring that
names attendance and marks as the case it was created for. D4 transcribes
those decisions into `dispositions.py`; it does not re-litigate them. Twelve
entries, six tables, and `tests/db/test_governance.py` turns a forgotten one
into a red `make check` rather than a privacy policy that describes a table
nobody has.

## Assumptions & Open Questions

- **`Session.end_time` is nullable and is not required by any criterion.**
  I searched FR3.1–FR3.9, AC3.0.x–AC3.5.x and § B.8 and found an end time
  required of `ScheduleSlot` (built, non-null) and of no session. It is
  carried so a rescheduled session can state one, and nothing reads it.
- **Announcement delivery is a notification question this unit inherits from
  D3.** AC3.3.1 says every student and guardian "sees" an announcement, which
  the batch feed satisfies. Whether it also pushes is governed by the FCM
  adapter, whose ownership § G of the prior `contract-summary.md` assigns to
  *both* this unit and D3 — the finding D3's review raised. **D3 built it**, so
  D4 reuses that adapter and builds no second one. V1's named triggers are the
  fee reminder and entered marks; an announcement push is in neither list, so
  this design does not add one.
- **`AC3.4.3`'s cached read-with-age is a client obligation**, not a server
  one. It is listed in this unit's traceability as `OK` against BR7.3, which
  states the server contract that makes it possible — a fetch timestamp the
  client can render — because the caching itself is Android work with no
  server rule behind it.
