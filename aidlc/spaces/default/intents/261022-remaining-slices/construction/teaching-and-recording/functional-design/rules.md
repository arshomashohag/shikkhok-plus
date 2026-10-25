# Business Rules — D4 `teaching-and-recording`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **Two rules in this file will look like contradictions to the next reader,
> and both are resolved here rather than left to be rediscovered.**
>
> **BR3.1** builds a local write queue. `project.md` carries
> *"NEVER accept a write without connectivity in V1; there is no local write
> queue."* The next reader meets the NEVER before they meet the decision, so
> BR3.1 states what the queue guarantees that the forbidden one does not, and
> carries a `violation_behaviour` a test can assert.
>
> **BR7.4** records that PU-3.6 carries **no performance obligation in V1**.
> It was dropped as a requirement at Q14.3 in the prior record, and AC3.1.8
> exists so that a developer "neither invents a latency budget nor reads the
> gap as licence". This record's delivery planning resurrected it; that is
> stale and flagged. D4 requires no manual pilot check to be complete.
>
> Rule IDs are unit-scoped, as in every unit of this project: D1, D2 and D3
> each number from `BR1.1` and so does D4.
>
> **Every figure in a `logic` or `notes` field below was computed**, by
> running the case rather than reasoning about it. The banding example in
> BR6.3 was produced by executing the merge algorithm over a named mark list;
> team memory records a carry-forward figure that propagated to four files
> because nobody did this.

## Sources

- [upstream] this stage's `entities.md` — the tables these rules constrain
- [upstream] this stage's `functional-spec.md` — the workflows they sit in
- [upstream] `inception/units-generation/unit-of-work.md` — D4's scope and the
  manual pilot check
- [upstream] `inception/delivery-planning/bolt-plan.md` — Bolt 4's hypothesis
- [prior] `261016-.../inception/requirements-analysis/requirements.md` —
  FR3.1–FR3.9, FR4.1–FR4.7, FR9.2, FR11.4, FR11.5, **NFR5, NFR5.1**
- [prior] `261016-.../inception/user-stories/stories.md` — AC3.0.x–AC3.5.x,
  AC4.1.x–AC4.4.x
- [prior] `261016-.../inception/domain-design/decisions.md` — **ADR-006**
- [prior] `261016-.../inception/contract-design/contract-summary.md` —
  § B.1.1, § B.7, **§ B.8**
- [code] `app/db/models.py`, `app/errors/_classes.py`, `app/errors/codes.py`,
  `app/governance/dispositions.py`, `app/fees/verification.py`,
  `tests/db/test_governance.py`, `tests/contract/test_error_contract.py` —
  read 2026-10-24

---

```yaml
rules:

  # ==================================================================
  # Group 1: sessions — what exists to record against.
  # ==================================================================

  - id: BR1.1
    statement: >
      A session exists for every occurrence the batch's weekly schedule
      slots imply, identified by its batch, date and start time.
    category: calculation
    applies_to: Session
    trigger: >
      The session-generation job, and any change to a batch's schedule
      slots.
    logic: >
      IF a batch has schedule slots
      THEN for each slot and each date in the generation horizon matching
      that slot's weekday
      INSERT a Session with origin `recurrence` for (batch_id, date,
      slot.start_time)
      AND take no action where such a row already exists.
    violation_behaviour: >
      A teacher opens a class to mark attendance and there is nothing to
      mark it against — US3.1 opens a session and nothing created one,
      which is the gap AC3.0.1 was added after review to close.
      Assertable: for a batch with a Monday 16:00 slot, after generation
      over a four-week horizon exactly four sessions exist with
      origin `recurrence`, one per Monday, each at 16:00.
    source: FR3.1, FR3.2, AC3.0.1

  - id: BR1.2
    statement: >
      Changing a batch's schedule slots never alters an existing session.
      Future occurrences follow the new slots.
    category: constraint
    applies_to: Session, ScheduleSlot
    trigger: A teacher edits the batch's schedule.
    logic: >
      IF schedule slots change
      THEN already-generated Session rows are left exactly as they are,
      including their date, start time, topic, status and attendance
      AND subsequent generation produces occurrences from the new slots
      only.
    violation_behaviour: >
      This is the reason sessions are rows rather than a view computed
      from the recurrence rule: a computed view re-derives history, so
      moving a Tuesday class to Wednesday silently moves every past
      Tuesday class and the attendance recorded against it. Assertable:
      generate four sessions, record attendance on the first, change the
      slot's weekday, generate again, then assert the first four sessions
      are byte-identical and their attendance rows are untouched.
    source: FR3.1, AC3.0.2
    notes: >
      This rule is why the materialised-row decision in `entities.md` is a
      requirement rather than a preference. It was the deciding argument.

  - id: BR1.3
    statement: >
      Session generation is idempotent by the database unique constraint
      on (batch_id, date, start_time), and a conflict is the success path.
    category: constraint
    applies_to: Session generation
    trigger: Inserting a generated session.
    logic: >
      IF a session already exists for (batch_id, date, start_time)
      THEN the insert conflicts and does nothing
      AND generation CONTINUES without raising
      AND no second session is created for that occurrence.
    violation_behaviour: >
      Two sessions for one class, each with its own roster, so attendance
      marked on one is invisible on the other and the student's record
      shows them absent from a class they attended. An application-level
      "has this run?" guard passes a sequential test and fails with two
      workers. Assertable, and ONLY assertable concurrently: N threads
      released together from a barrier against real PostgreSQL leave
      exactly one row per (batch_id, date, start_time).
    source: FR3.1, AC3.0.1, project MANDATED rule on constraint-based idempotency
    notes: >
      Same shape as D3's (enrollment_id, period) and as
      `RateLimitCounter`'s built UniqueConstraint. Deliberately not a new
      pattern.

  - id: BR1.4
    statement: >
      A teacher may create an ad-hoc session for a date with no scheduled
      slot, and generation never creates, modifies or deletes one.
    category: policy
    applies_to: Session
    trigger: The teacher creates a session manually; the generation job runs.
    logic: >
      IF a teacher creates a session for a date and time
      THEN it is stored with origin `ad_hoc`
      AND the generation job considers only rows with origin `recurrence`
      when deciding what is missing, and never deletes any row at all.
    violation_behaviour: >
      A generation job that reconciles rather than inserts would delete
      the extra class a teacher held on a Saturday, taking its attendance
      with it. Assertable: create an ad-hoc session on a non-slot date,
      run generation, assert the row and its attendance still exist and
      its origin is unchanged.
    source: FR3.2, AC3.0.3

  - id: BR1.5
    statement: >
      A session's roster is the batch's enrollments that were active on
      that session's date and whose student link is not declined.
    category: authorization
    applies_to: Session roster
    trigger: Reading a session's roster for marking or display.
    logic: >
      IF building the roster for a session on date D
      THEN include an enrollment WHERE its batch matches
      AND (inactive_from IS NULL OR inactive_from > D)
      AND student_decision <> `declined`
      AND (joined_on IS NULL OR joined_on <= D).
    violation_behaviour: >
      A student who left in March appears on an April roster and is
      marked absent every week, which then shows on a record nobody can
      explain. Or a seat someone declined — the mistyped-digit case —
      keeps appearing to be marked. Assertable per clause: four
      enrollments differing only in `inactive_from`, `student_decision`
      and `joined_on`, one roster read, one expected membership set.
    source: FR3.5, AC3.1.2, ADR-009
    notes: >
      Mirrors how D3 reads `inactive_from` for generation. The
      `joined_on` clause is the attendance counterpart of BR4.3's
      `joined_after` state, and both exist so a seat is never recorded
      against a class it could not have attended.

  - id: BR1.6
    statement: >
      A cancelled session accepts no attendance write and no topic write.
    category: validation
    applies_to: Session, Attendance
    trigger: Any write targeting a session.
    logic: >
      IF the session's status is `cancelled`
      THEN refuse the write with a ConflictError
      AND leave every existing attendance row for that session untouched.
    violation_behaviour: >
      A class that did not happen accumulates attendance, and a student
      is marked absent from it. Assertable: cancel a session, submit a
      roster, assert 409 and assert the attendance row count for that
      session is unchanged.
    source: FR3.3, FR3.4, AC3.2.2
    notes: >
      `ConflictError` rather than `ValidationError`, because the request
      is well-formed and the current state is what forbids it — which is
      the built class's own docstring: "Valid request; current state
      forbids it."

  - id: BR1.7
    statement: >
      Rescheduling a session changes its date and start time and
      preserves its identity, its topic and its attendance.
    category: policy
    applies_to: Session
    trigger: The teacher reschedules.
    logic: >
      IF a session is rescheduled to a new date or time
      THEN UPDATE that row's date and start_time
      AND do not create a new session and do not re-key attendance
      AND the new values must not collide with another session of the
      same batch, which the (batch_id, date, start_time) constraint
      enforces as a ConflictError.
    violation_behaviour: >
      Implemented as delete-and-recreate, a reschedule silently discards
      the topic and attendance already recorded against the class.
      Assertable: record a topic and a roster, reschedule, assert the
      session id is unchanged and both survive.
    source: FR3.4, AC3.2.1

  # ==================================================================
  # Group 2: the topic log.
  # ==================================================================

  - id: BR2.1
    statement: >
      A session's subject and topic are recorded by the teacher who owns
      the batch, and the topic is a queued path under BR3.1.
    category: policy
    applies_to: Session
    trigger: The teacher writes the topic, online or offline.
    logic: >
      IF the teacher submits a topic for a session
      THEN store it against that session
      AND treat the write as queued-path per BR3.1, carrying
      `base_topic_version` and a `client_mutation_id`
      AND apply the same refuse-on-conflict rule the roster uses, against
      `topic_version` rather than `attendance_version`.
    violation_behaviour: >
      NFR5 permits offline writes for the mid-class path, which FR3.6
      defines as attendance AND the topic log. Building the queue for
      attendance only leaves half the mid-class path failing with a
      retry prompt in the exact conditions the queue exists for.
      Assertable: with the network disabled, a topic write is accepted
      into the queue and shown as not-yet-sent, not as failed.
    source: FR3.2, FR3.6, AC3.1.1, NFR5

  - id: BR2.2
    statement: >
      An unwritten topic is distinguishable from a topic written as
      empty.
    category: constraint
    applies_to: Session
    trigger: Reading a session for display.
    logic: >
      IF a session's topic is NULL
      THEN it is rendered as not yet logged
      AND a topic the teacher deliberately saved as empty is stored as
      an empty string, which renders as logged-and-blank.
    violation_behaviour: >
      Collapsing the two makes it impossible to tell a class nobody
      logged from one logged as nothing, which is the whole content of
      AC3.4.2's "topics covered in each". Assertable: two sessions, one
      never written and one written empty, produce different
      `topic_logged` values in the response.
    source: FR3.2, AC3.4.2

  # ==================================================================
  # Group 3: the offline queue and the concurrency guarantee.
  # This is the unit's centre of gravity.
  # ==================================================================

  - id: BR3.1
    statement: >
      The two mid-class paths — attendance and the topic log — accept a
      write without connectivity into a device queue whose every state is
      shown to the teacher. No other write queues.
    category: policy
    applies_to: Attendance, Session.topic
    trigger: The teacher submits a roster or a topic with no connectivity.
    logic: >
      IF the write targets attendance or a session topic
      THEN accept it into the device queue in state `queued`, rendered as
      saved-on-phone-not-yet-sent and NEVER as confirmed
      AND sync it automatically when connectivity returns, with no action
      from the teacher
      ELSE refuse the write with an explicit retry prompt that preserves
      what was typed.
    violation_behaviour: >
      Two opposite failures, and the rule is assertable against both.
      (a) A queue that renders as saved: assert that while an item is
      `queued` the UI state is not the confirmed state and the server
      holds no row. (b) A third path queueing: assert that a write to any
      endpoint other than the two named fails with a retry prompt when
      offline, with nothing enqueued.
    source: FR3.6, NFR5, NFR5.1, AC3.1.3, ADR-006
    notes: >
      **This rule and `project.md`'s NEVER are about different things,
      and the difference is the word the NEVER drops.** The project rule
      reads "NEVER accept a write without connectivity in V1; there is no
      local write queue, and a failed write surfaces an explicit retry
      prompt rather than queueing SILENTLY" [TC-8, D-9]. Its own source
      is narrower than its restatement: **NFR5 reads "Permitted for the
      mid-class path only — the topic log and attendance queue locally
      and sync when connectivity returns. Every other write requires
      connectivity."** So the requirement was always scoped, and the
      `project.md` sentence lost the scope when it was written.
      .
      What the NEVER protects is a queue that LOOKS LIKE SUCCESS. This
      queue is its opposite, and the difference is mechanical rather
      than a matter of intent — four states, all distinct and all
      visible: `queued` (on the phone, not sent), `confirmed` (the server
      has it), `failed` (the send did not succeed; retry is right) and
      `conflicted` (the server refused it; retrying as-is is WRONG, look
      at what changed). A silent queue has one state and renders it as
      saved. **Nothing in this design ever renders an unsent write as
      confirmed, and BR3.1's violation_behaviour (a) is the test that
      proves it.**
      .
      **The `project.md` wording should be amended at a learnings gate**
      to say what it protects rather than to ban queues outright — it
      currently contradicts NFR5, which it cites. That is the gate's to
      do; this design does not edit memory. Recorded as an open item in
      `functional-spec.md`.

  - id: BR3.2
    statement: >
      The queue has exactly four states and survives app restart.
    category: constraint
    applies_to: The device queue
    trigger: Any queued write; app restart.
    logic: >
      IF a write is queued
      THEN it is persisted to device storage, not held in memory
      AND it is in exactly one of `queued`, `confirmed`, `failed`,
      `conflicted`
      AND after the process is killed and relaunched it is still present
      in the same state.
    violation_behaviour: >
      An in-memory queue loses the roster when Android kills the app in
      the background — mid-class, on a low-end device, which is when it
      is most likely. Assertable: enqueue, kill the process, relaunch,
      assert the item is present and still shows as not yet sent.
      Separately assertable: `failed` and `conflicted` are visually
      distinct, because AC3.1.10 requires three states and not two.
    source: NFR5.1, AC3.1.9, AC3.1.10

  - id: BR3.3
    statement: >
      A queued attendance write carries the `attendance_version` it was
      composed against, and the server applies it only if that version is
      still current.
    category: constraint
    applies_to: Attendance, Session.attendance_version
    trigger: An attendance roster arrives at the server.
    logic: >
      IF the submitted `base_attendance_version` equals the session's
      current `attendance_version`
      THEN apply the whole roster atomically, set
      `attendance_version` to base + 1, and return 200 with the new
      version
      ELSE refuse with 409 and return the CURRENT version and the
      CURRENT roster state, writing nothing.
    violation_behaviour: >
      A roster queued at 10:15, corrected from a tablet at 11:00, and the
      phone reconnecting at 11:40 to silently reinstate the stale mark —
      with the correction history then faithfully recording a change the
      teacher never made, which is worse than no history because it looks
      authoritative [ADR-006]. Assertable sequentially for the happy
      path; the refusal needs the concurrency test in BR3.4.
    source: FR11.4, FR11.5, ADR-006, contract-summary § B.8
    notes: >
      **The mechanism is a conditional update, not a lock.** The write is
      `UPDATE session SET attendance_version = :base + 1 WHERE id = :id
      AND attendance_version = :base`, and **zero rows affected means
      someone else won**. That single statement is both the check and the
      write, so no window exists between them. This is the product's
      FIRST optimistic path — verified by reading `app/db/models.py`
      (no version column on any table) and finding `SELECT ... FOR UPDATE`
      in three places instead: `app/auth/otp.py:170`,
      `app/auth/tokens.py:234`, and D3's `app/fees/verification.py:117`.
      A pessimistic lock is the wrong tool here for a reason specific to
      this path: the transaction would have to be held across a write
      composed hours earlier, and the contender is not a concurrent
      request but a stale one.
      .
      **Granularity is session-level and is inherited, not chosen.**
      ADR-006 and § B.8 both name `session.attendance_version`. The cost
      is stated rather than hidden: two devices marking DIFFERENT
      students in the SAME session do conflict, and the second is
      refused. Batch-level would conflict unrelated sessions;
      enrollment-level would destroy AC3.1.5's atomic roster, because
      per-seat versions are field granularity and a roster deliberately
      has none.

  - id: BR3.4
    statement: >
      Of N attendance writes racing against the same version, exactly one
      applies and N-1 are refused as conflicts. Never two applied, never
      a silent overwrite.
    category: constraint
    applies_to: Attendance, AttendanceSubmission
    trigger: Concurrent roster submissions for one session.
    logic: >
      IF N writes all carry `base_attendance_version` = V
      THEN the conditional update of BR3.3 succeeds for exactly one
      AND the other N-1 observe zero rows affected and are refused
      AND the UNIQUE (session_id, resulting_version) constraint on
      AttendanceSubmission is a second, independent guarantee of the
      same fact.
    violation_behaviour: >
      **A sequential test proves nothing here, and this is the rule that
      says so.** A roster write guarded by a version check passes every
      sequential test against an implementation with NO guard at all,
      because nothing ever contends. This is the exact shape of D3's
      double-crediting defect: a race on a path the constraint did not
      cover, with tests that never ran two writes at once. Assertable
      ONLY concurrently: N threads released together from a barrier,
      against real PostgreSQL, submitting rosters against version V;
      assert exactly one 200 and N-1 409s, assert
      `attendance_version` = V+1 and not V+N, and assert the stored
      roster is byte-identical to the one that won.
    source: ADR-006, § B.8, team Testing Posture on concurrency tests
    notes: >
      Two independent mechanisms pointing at one guarantee, which is the
      project's habit where a rule is important: the conditional update
      is the live control, and the unique constraint on
      (session_id, resulting_version) is what makes the guarantee survive
      somebody later rewriting the update into a read-then-write.

  - id: BR3.5
    statement: >
      A roster is written in one atomic operation covering every seat,
      never one write per student, and a re-submission replaces rather
      than appends.
    category: constraint
    applies_to: Attendance
    trigger: An accepted roster write.
    logic: >
      IF a roster write is applied
      THEN within ONE transaction: insert the AttendanceSubmission row,
      upsert one Attendance row per roster entry on
      (session_id, enrollment_id), increment the version
      AND if any part fails, none of it is applied.
    violation_behaviour: >
      A per-student write leaves attendance half-saved after a mid-roster
      connection drop, and a retry cannot reconcile that on screen
      [AC3.1.5]. Assertable: inject a failure on the k-th entry of a
      12-seat roster and assert the session has zero attendance rows and
      an unchanged version — not k-1 rows.
    source: FR3.5, FR3.6, AC3.1.5, AC3.1.7

  - id: BR3.6
    statement: >
      A refused queued write becomes `conflicted` — never `failed` — and
      the teacher's offline entry is preserved until they choose to
      re-apply or discard.
    category: policy
    applies_to: The device queue, the conflict-resolution screen
    trigger: The server returns 409 for a queued write.
    logic: >
      IF a queued write is refused for a version mismatch
      THEN the item moves to `conflicted`, not to `failed`
      AND the teacher is shown what they recorded offline against what
      the record now says
      AND the offline entry is retained until they explicitly re-apply or
      discard
      AND nothing is merged, nothing is silently applied, nothing is
      silently discarded.
    violation_behaviour: >
      `failed` means "try again" and would invite a retry that is
      guaranteed to be refused again, or worse, a retry wrapper that
      strips the version and overwrites. Merging would mean inventing a
      rule for a student the two rosters disagree about — a business
      decision a sync layer must not make. Assertable: force a conflict,
      assert the queue state is `conflicted` and not `failed`, assert the
      offline entries are still readable after a restart, and assert no
      automatic retry is scheduled.
    source: FR11.5, NFR5.1, ADR-006, AC3.1.10

  - id: BR3.7
    statement: >
      Re-applying a conflicted write is a NEW write carrying the current
      version and a FRESH `client_mutation_id`.
    category: constraint
    applies_to: The conflict-resolution screen, AttendanceSubmission
    trigger: The teacher chooses re-apply on a conflicted item.
    logic: >
      IF the teacher re-applies
      THEN compose a new queued write with the CURRENT
      `attendance_version` and a NEWLY generated `client_mutation_id`
      AND never reuse the id of the write that was refused.
    violation_behaviour: >
      **The obvious implementation reuses the old id, and it fails
      silently in the worst possible way.** The id carries a unique
      constraint and § B.7 makes a duplicate return the ORIGINAL stored
      result with 200 and write nothing — so re-apply would report
      success and change nothing, which is the exact opposite of what the
      teacher asked for. Re-apply is a new decision by the teacher, not a
      replay of the old one. Assertable: force a conflict, re-apply,
      assert the stored roster now matches the re-applied one and that
      the new AttendanceSubmission row has a different
      `client_mutation_id` and `base_version` from the refused attempt.
    source: ADR-006, § B.8, § B.7
    notes: >
      This is the hypothesis Bolt 4 is built to falsify, and this rule is
      the half of it that an implementation gets wrong by default.

  - id: BR3.8
    statement: >
      A replayed `client_mutation_id` returns the original stored result
      with 200 and writes nothing.
    category: constraint
    applies_to: AttendanceSubmission
    trigger: A roster write arrives whose mutation id is already stored.
    logic: >
      IF (submitted_by_account_id, client_mutation_id) already exists
      THEN return the original submission's result with 200 — not 201,
      not an error
      AND write no second Attendance row and do not increment the version
      AND leave the original's `created_at` unchanged, so a replay is
      observably a replay.
    violation_behaviour: >
      Without the constraint on AttendanceSubmission this cannot be
      enforced at the database at all, because a roster is many rows
      sharing one id — which is why the table exists. Assertable: submit
      the same roster body twice, assert both return 200, assert the
      version incremented ONCE and exactly one AttendanceSubmission row
      exists. Assertable concurrently too, which is the case that
      distinguishes a constraint from an application guard.
    source: § B.7, AC9.2.4
    notes: >
      Scoped per account per endpoint, so two clients cannot collide and
      a replay of someone else's id is an authorization refusal rather
      than a silent success.

  - id: BR3.9
    statement: >
      The four queue states are client-side vocabulary and appear in no
      response schema.
    category: constraint
    applies_to: The API contract
    trigger: Designing any response schema in this unit.
    logic: >
      IF a response schema is defined for a queued path
      THEN it carries the applied version or the conflict detail
      AND it carries NO `queue_state` field, because the server cannot
      know whether an item is queued on a device it has never heard from.
    violation_behaviour: >
      A `queue_state` field on the wire is a field the server must invent
      a value for, and whatever it invents is wrong for every device
      except the one that just called. Assertable: the generated OpenAPI
      schema contains no property named `queue_state` on any operation of
      this unit, checked by iterating the document rather than by
      remembering per endpoint.
    source: § B.8

  - id: BR3.10
    statement: >
      A conflict is reported with a descriptive code, and that is
      permitted because the refusal is post-authorization.
    category: validation
    applies_to: The error contract
    trigger: Refusing a queued write for a version mismatch.
    logic: >
      IF the caller's lens already reaches the session
      AND the version does not match
      THEN raise ConflictError with code `ATTENDANCE_VERSION_CONFLICT`,
      message_key `error.attendance_version_conflict`, and details
      carrying `expected_version`, `current_version` and `current_state`
      ELSE IF the lens does not reach the session, refuse FIRST with the
      shared `NOT_AVAILABLE`.
    violation_behaviour: >
      Order matters and is the assertable part. A descriptive conflict
      code returned BEFORE the authorization check is an existence
      oracle: a caller probes session ids and reads the difference
      between "not yours" and "yours but stale". Assertable: a teacher
      submitting against another teacher's session id receives
      `NOT_AVAILABLE`, byte-identical to the response for an invented id,
      and never `ATTENDANCE_VERSION_CONFLICT`.
    source: contract-summary § B.8, NFR14.3
    notes: >
      **No new error class.** `ConflictError` is built and its docstring
      already states this exact semantic: *"Valid request; current state
      forbids it. Refetch and decide. Retrying as-is is wrong."*
      `retryable` is false because retryability is a property of the
      class read in one place — a raise site cannot set it, and this one
      does not try. The descriptive code is permitted by the oracle rule
      in `app/errors/codes.py` because it is reached only after
      authorization; `tests/contract/test_error_contract.py` asserts
      there is no code pair distinguishing "does not exist" from "you may
      not reach this", and this code creates no such pair.

  - id: BR3.11
    statement: >
      Interactive writes carry no version and cannot conflict.
    category: policy
    applies_to: Every non-queued write in this unit
    trigger: An online write to a session, exam, mark or announcement.
    logic: >
      IF the write is interactive
      THEN apply last-write-wins per field, recording the actor and time
      in the correction history
      AND require no version, send no `If-Match`, and raise no conflict.
    violation_behaviour: >
      Stating this is what stops the queued-path rule from spreading.
      Applied everywhere, optimistic concurrency would make a teacher
      correcting a mark on their own phone refetch for no reason.
      Assertable: a mark write with no version field succeeds.
    source: FR11.4, § B.8

  # ==================================================================
  # Group 4: exams and marks.
  # ==================================================================

  - id: BR4.1
    statement: >
      An exam belongs to one batch and one of that batch's subjects, with
      a title, date and a total of at least one mark.
    category: validation
    applies_to: Exam
    trigger: Creating or editing an exam.
    logic: >
      IF an exam is created
      THEN require title, date, total_marks >= 1 and a batch_subject_id
      AND refuse with a ValidationError if the subject does not belong to
      the named batch.
    violation_behaviour: >
      A subject id from another teacher's batch attaches an exam across
      the ownership boundary. Assertable: creating an exam with teacher
      B's subject id under teacher A's batch is refused, and the refusal
      is `NOT_AVAILABLE` rather than a descriptive one, because the
      subject id is an unreachable resource and naming it as wrong is the
      oracle.
    source: FR4.1, AC4.1.1

  - id: BR4.2
    statement: >
      A recorded mark is an integer between zero and the exam's total,
      and a zero is a mark.
    category: validation
    applies_to: Mark
    trigger: Entering or correcting a mark.
    logic: >
      IF result_state is `marked`
      THEN marks must be non-null, >= 0 and <= the exam's total_marks
      AND marks must be NULL for every other result_state.
    violation_behaviour: >
      A zero stored as `absent` tells a guardian their child missed an
      exam they sat and failed, and the reverse tells them the child
      scored nothing when they were ill. Assertable both ways as a
      database CHECK on the state/marks biconditional, plus a write-path
      test for the upper bound, which spans a foreign key and so cannot
      be a single-table CHECK.
    source: FR4.2, FR4.3, AC4.1.2, AC4.1.3

  - id: BR4.3
    statement: >
      A result distinguishes four states, and `not_entered` and
      `joined_after` are derived from facts rather than typed by the
      teacher.
    category: calculation
    applies_to: Mark
    trigger: Reading an exam's results.
    logic: >
      IF a seat has a live Mark row THEN its state is that row's state
      ELSE IF the enrollment's joined_on is after the exam's date
      THEN the state is `joined_after`
      ELSE the state is `not_entered`.
    violation_behaviour: >
      Conflating "I have not marked this yet" with "they were absent"
      publishes an absence the teacher never recorded, on a shared
      marksheet, which makes it visible to the whole batch. And a student
      who joined in May showing as absent from an April exam reads as a
      record of truancy. Assertable: three seats differing only in
      `joined_on` and whether a Mark row exists produce three different
      states from one read.
    source: FR4.3, AC4.1.3, AC4.1.4, AC4.1.5

  - id: BR4.4
    statement: >
      Correcting a mark appends a new row and supersedes the old one; no
      mark is ever updated in place or deleted.
    category: constraint
    applies_to: Mark
    trigger: The teacher changes a mark already entered.
    logic: >
      IF a mark is corrected
      THEN insert a new Mark row with the new value
      AND set the previous live row's `superseded_by_id` to the new row's
      id, in the same transaction
      AND never UPDATE the value or state of an existing row.
    violation_behaviour: >
      An in-place update destroys the fact that a mark changed, which
      FR9.2 requires to be visible — and on a shared marksheet a silently
      changed mark is the one a student will dispute. Assertable: enter
      55, correct to 65, assert two rows exist, the first with a non-null
      `superseded_by_id`, and that the history read returns both with
      their actor and time.
    source: FR9.2, AC3.1.7
    notes: >
      The same shape as `LedgerEntry`'s supersession, deliberately,
      rather than a second correction mechanism.

  - id: BR4.5
    statement: >
      Exactly one live Mark exists per seat per exam, enforced by a
      partial unique index.
    category: constraint
    applies_to: Mark
    trigger: Any mark write.
    logic: >
      IF rows exist for (exam_id, enrollment_id)
      THEN at most one has superseded_by_id IS NULL
      AND that row is the result every read returns.
    violation_behaviour: >
      A correction that fails to set the old pointer leaves two live
      marks, and the marksheet counts one student twice — inflating the
      batch size, shifting every rank and skewing the average, with
      nothing on screen to indicate it. Assertable directly by attempting
      to insert a second live row for one seat and asserting the
      constraint rejects it, which a logic-only guard would not.
    source: FR4.2, FR9.2
    notes: >
      A partial unique index, the same shape as the built
      `uq_enrollment_batch_student`.

  # ==================================================================
  # Group 5: who may see what.
  # ==================================================================

  - id: BR5.1
    statement: >
      Every endpoint in this unit resolves a lens, and the lens carries
      the scoping value the handler queries with.
    category: authorization
    applies_to: Every route in this unit
    trigger: Any request.
    logic: >
      IF a route reads or writes a session, attendance, exam, mark or
      announcement
      THEN it declares a dependency whose return annotation is a Lens
      subtype
      AND it scopes its query by the value that lens carries, never by an
      id taken from the request body.
    violation_behaviour: >
      The built route-enumeration test walks `route.dependant` recursively
      and matches on the return annotation being a `Lens` subtype, with
      `PUBLIC_ROUTES` an explicit frozenset. A D4 route that resolves no
      lens fails `make check` rather than review. Assertable by that
      existing test, with no new mechanism.
    source: TC-11, D-2, project MANDATED rule on per-request lenses

  - id: BR5.2
    statement: >
      Every new read in this unit filters on the enrollment decision
      columns, named query by query.
    category: authorization
    applies_to: Session roster, attendance reads, mark reads, marksheet
    trigger: Adding any query that reaches an enrollment.
    logic: >
      IF a query returns attendance or marks under a student lens
      THEN it requires student_decision = `accepted`
      IF under a guardian lens
      THEN it requires guardian_decision = `accepted`
      IF under a teacher lens
      THEN it requires the batch's owner to match the lens's owner_id and
      applies BR1.5's roster predicate.
    violation_behaviour: >
      **This project recorded on 2026-10-22 that adding a column is not
      adding a behaviour, and that the queries which must start reading
      it have to be NAMED** — because the ones already granting access go
      on granting it on the old evidence. The six readers this unit adds
      are: the session roster, the session detail read, the student
      attendance history, the guardian attendance history, the batch
      marksheet, and the guardian progress-over-time read. Assertable as
      six IDOR probes, one per reader: a declined holder reaches none of
      them.
    source: ADR-009, ADR-014, TC-13, D-5

  - id: BR5.3
    statement: >
      No teacher-facing response in this unit carries an owner-private
      profile field or a global account identifier.
    category: authorization
    applies_to: Every teacher-lens response schema in this unit
    trigger: Defining a response schema.
    logic: >
      IF a schema is returned under a teacher lens
      THEN it exposes an enrollment id and never student_account_id
      AND it carries no field in the owner-private profile set.
    violation_behaviour: >
      A roster is the most natural place in the product to leak a
      student's self-authored name or photo to a teacher, because it is a
      list of people. The built gate in `app/contract/privacy.py`
      iterates the generated OpenAPI document and reads the lens from the
      route, so a D4 schema violating this fails `make check` without a
      per-endpoint test being remembered. Assertable by that existing
      invariant.
    source: TC-13, D-5, ADR-001

  - id: BR5.4
    statement: >
      The marksheet toggle is a single existing column, written through
      exactly one route, and when it is off no marksheet is returned at
      all.
    category: authorization
    applies_to: Batch.marksheet_visible
    trigger: A student or guardian requests a marksheet.
    logic: >
      IF the batch's marksheet_visible is false
      THEN return no marksheet to any student or guardian lens — not an
      empty one, not one with marks hidden
      AND the teacher's own view is unaffected, because the toggle
      controls what families see.
    violation_behaviour: >
      Returning an empty marksheet rather than none leaks that exams
      exist and how many. Assertable: with the toggle off, the
      student-lens response contains no marksheet object and no exam
      count. **Separately assertable, and this is the part an
      implementation forgets**: the column is already built and non-null
      [`app/db/models.py:589`], so D4 adds NO migration and NO default —
      a test asserts the migration set for this unit touches no column of
      `batch`.
    source: FR4.6, AC4.2.1, AC4.2.2

  - id: BR5.5
    statement: >
      An inactive batch is read-only; no write in this unit succeeds
      against one.
    category: validation
    applies_to: Every write in this unit
    trigger: A write whose batch is inactive.
    logic: >
      IF the target batch's `active` is false
      THEN refuse with a ConflictError
      AND continue to serve every read, because the batch collapses to
      read-only history rather than disappearing.
    violation_behaviour: >
      Attendance accruing on a closed batch, or a mark entered against a
      class that ended last year. Assertable: deactivate a batch, attempt
      a roster write, a topic write, an exam creation and a mark write,
      assert all four refuse and every read still succeeds.
    source: Batch.active, FR2.x

  # ==================================================================
  # Group 6: the marksheet, and governance.
  # ==================================================================

  - id: BR6.1
    statement: >
      Every table this unit creates carries both a disposition and a
      retention class in the governance manifests, with the values the
      prior catalogue already decided.
    category: policy
    applies_to: Session, Attendance, AttendanceSubmission, Exam, Mark, Announcement
    trigger: Any migration in this unit.
    logic: >
      IF this unit creates a table
      THEN add its disposition and its retention class to
      `app/governance/dispositions.py` in the same change as the
      migration
      AND use `RETAIN_WITH_BASIS` for attendance, exams and marks, which
      is the case that enum value was created for.
    violation_behaviour: >
      `tests/db/test_governance.py` iterates live `pg_tables` and asserts
      an entry in BOTH manifests, in both directions, so a missing entry
      turns `make check` red rather than shipping a privacy policy that
      does not describe the implementation. Six new tables, twelve
      entries. Assertable by that existing test with no new mechanism.
    source: ADR-003, ADR-004, prior components.md governance tables
    notes: >
      The disposition values are transcribed, not invented: the prior
      catalogue already wrote "Attendance stays for up to 3 years because
      it is the student's own record" and the matching rows for Exam, Mark
      and Announcement. `AttendanceSubmission` is the one table with no
      upstream row, because this design added it; it takes Attendance's
      disposition and retention, since it holds nothing Attendance does
      not and is meaningless without it.

  - id: BR6.2
    statement: >
      A student's marksheet shows their own named mark plus rank, batch
      average, highest mark and a banded distribution — never a list of
      other students' marks.
    category: calculation
    applies_to: The marksheet read
    trigger: A student requests an exam's marksheet.
    logic: >
      IF marksheet_visible is true AND BR6.4's thresholds are met
      THEN return the viewer's own mark named, their rank, the average of
      marked results, the highest marked result, and the merged bands
      AND return no row attributable to another student.
    violation_behaviour: >
      In a batch of 8 to 20 students who sit together and compare marks,
      twelve unattributed numbers are deanonymised by inference within a
      day — so a row list would over-claim "anonymised" for a product
      under a Families declaration. Assertable: the response contains no
      array whose length equals the number of marked results and no
      per-student object other than the viewer's own.
    source: FR4.4, FR4.5, AC4.3.1, AC4.3.2, AC4.3.7

  - id: BR6.3
    statement: >
      A distribution band holding fewer than three results merges with
      its neighbour.
    category: calculation
    applies_to: The marksheet read
    trigger: Computing the distribution.
    logic: >
      IF a band contains fewer than 3 marked results
      THEN merge it into the adjacent band and re-check, repeating until
      every published band holds at least 3
      AND never publish a band of one or two, which identifies its
      occupants.
    violation_behaviour: >
      A band of one IS a named mark, with the name supplied by anyone who
      knows who is in the batch. Assertable with the computed case below:
      the published band count and membership must match exactly.
    source: FR4.5, AC4.3.3
    notes: >
      **Worked example, computed by executing the merge over the mark
      list — not asserted.** Nine marked results out of 100:
      [92, 88, 81, 74, 71, 68, 55, 41, 12], five fixed bands of width 20.
      Raw counts, high to low: 80-100 holds 3, 60-79 holds 3, 40-59 holds
      2, 20-39 holds 0, 0-19 holds 1. Walking downward and merging any
      band under 3 into its neighbour, the bottom three collapse into a
      single 0-59 band holding 3. **Published: three bands — 80-100 with
      3, 60-79 with 3, 0-59 with 3 — totalling 9, which is every marked
      result.** For the same data the average is 64.67 and the highest is
      92; the rank of the 74 is 4th of 9.

  - id: BR6.4
    statement: >
      No comparison is shown below five marked results, and none is shown
      while marking is incomplete.
    category: calculation
    applies_to: The marksheet read
    trigger: Computing rank, average, highest and bands.
    logic: >
      IF fewer than 5 results are marked
      THEN return the viewer's own mark only, with no rank, average,
      highest or bands
      IF any seat on the roster is still `not_entered`
      THEN likewise return no rank and no average.
    violation_behaviour: >
      A rank that drifts from 2nd to 7th as marks arrive reads as the app
      changing the student's result. And below five results a rank plus a
      band identifies people directly. Assertable as two separate cases,
      because one can pass while the other fails: four marked and
      complete returns no comparison; eight marked with one
      `not_entered` also returns no comparison.
    source: FR4.3, FR4.5, AC4.3.4, AC4.3.5

  - id: BR6.5
    statement: >
      Absent results are excluded from the average, the rank and the
      distribution; marksheets never span batches.
    category: calculation
    applies_to: The marksheet read
    trigger: Computing any aggregate.
    logic: >
      IF a seat's result_state is not `marked`
      THEN exclude it from the average's numerator and denominator, from
      the rank ordering and from every band
      AND scope every aggregate to the one batch, never across a
      student's other batches.
    violation_behaviour: >
      Counting an absence as zero drags the average down and moves every
      rank — a quiet arithmetic error that looks like a real result.
      Assertable: identical marked results with and without two absent
      seats produce an identical average, rank and band set.
    source: FR4.3, FR4.4, AC4.3.6, AC4.3.7

  - id: BR6.6
    statement: >
      A guardian sees their child's results across exams in date order,
      with absences shown as absent rather than as zero.
    category: calculation
    applies_to: The guardian progress read
    trigger: A guardian opens progress over time.
    logic: >
      IF a guardian lens reaches the child's enrollment
      THEN return the live Mark per exam ordered by exam date ascending
      AND render an absent result as `absent`, contributing no value to
      any trend.
    violation_behaviour: >
      An absence plotted as zero shows a collapse in performance that did
      not happen, which is the single most alarming thing this screen can
      say wrongly. Assertable: a guardian's series over three exams with
      the middle one absent contains three entries, the middle carrying
      no numeric value, and any computed trend ignores it.
    source: FR4.7, AC4.4.1, AC4.4.2

  # ==================================================================
  # Group 7: announcements, student and guardian reads, and the
  # obligations this unit must discharge to be complete.
  # ==================================================================

  - id: BR7.1
    statement: >
      An announcement reaches every student and guardian of its batch,
      shows as edited when edited, disappears when deleted, and never
      expires.
    category: policy
    applies_to: Announcement
    trigger: Posting, editing, deleting or reading an announcement.
    logic: >
      IF an announcement exists with deleted_at IS NULL
      THEN it appears for every accepted student and guardian of that
      batch
      AND it renders as edited when edited_at IS NOT NULL
      AND no job and no column ever removes it on the passage of time.
    violation_behaviour: >
      Assertable in four parts, and the fourth is the one an
      implementation adds by habit: assert the schema has no expiry
      column and the unit ships no scheduled job that touches
      announcements. A silently expiring announcement is a message the
      teacher believes was delivered.
    source: FR3.8, FR3.9, AC3.3.1, AC3.3.2, AC3.3.3, AC3.3.4

  - id: BR7.2
    statement: >
      Students and guardians see the next class, the topics covered and
      attendance; a guardian sees their own child's and no other's.
    category: authorization
    applies_to: The student and guardian batch reads
    trigger: A student or guardian opens a batch.
    logic: >
      IF a student lens reaches the enrollment
      THEN return the next scheduled session's date and time, past
      sessions with their topics, and that student's own attendance
      IF a guardian lens reaches it
      THEN return the same scoped to the named child enrollment, which
      arrives as a path parameter and never from a client hint.
    violation_behaviour: >
      The guardian case is the IDOR shape this product cares most about.
      Assertable: a guardian requesting a non-child enrollment id
      receives `NOT_AVAILABLE`, byte-identical to the response for an
      invented id.
    source: FR3.7, AC3.4.1, AC3.4.2, AC3.5.1, AC3.5.2

  - id: BR7.3
    statement: >
      Every schedule and topic read carries the server time it was
      produced, so a client rendering it from cache can state its age.
    category: policy
    applies_to: The student and guardian batch reads
    trigger: Serving a cacheable read.
    logic: >
      IF a read returns schedule or topic data
      THEN include the server timestamp at which it was computed
      AND make no assumption about whether the client caches it.
    violation_behaviour: >
      AC3.4.3 requires a cached view to indicate its age, and a client
      cannot state an age the server never sent — it would have to use
      the device clock, which is the thing BR3.3's note rules out for
      decisions. Assertable server-side: the response carries the
      timestamp. **The caching itself is Android work with no server rule
      behind it**, so this rule states only the half the server owns.
    source: NFR4, AC3.4.3

  - id: BR7.4
    statement: >
      PU-3.6 carries NO performance obligation in V1. It was dropped as a
      requirement, and D4 neither measures mid-class speed nor invents a
      latency budget.
    category: policy
    applies_to: The attendance-marking path
    trigger: Any proposal to add a latency target, budget or timing check.
    logic: >
      IF a latency target, benchmark or timing assertion is proposed for
      the attendance path
      THEN it is refused as out of scope for V1
      AND the structural properties stand in its place: AC3.1.4's
      default-present and AC3.1.5's single atomic write.
    violation_behaviour: >
      A developer invents a latency budget nobody agreed, or reads the
      absence of a target as licence to let the path become slow.
      AC3.1.8 exists precisely to make both readings wrong, and it says
      so: it "records the absence so a developer neither invents a
      latency budget nor reads the gap as licence." Assertable as the
      absence of any timing assertion on this path, and as the presence
      of the two structural tests that replace it: a freshly opened
      roster has every seat present, and the roster commits as one write.
    source: Q14.3 (prior record, answer C), AC3.1.8, FR3.5
    notes: >
      **This rule was wrong in its first draft and the correction matters
      more than the rule.** It read "PU-3.6's latency obligation is
      discharged by a named manual pilot check", citing a human decision
      of 2026-10-23 that chose the manual verifier over a Macrobenchmark.
      That choice was real but it answered a question that had already
      been closed: **Q14.3 in the prior record, answer C — "The mid-class
      speed statement is dropped as a requirement... It carries no
      acceptance criterion, no numeric target and no verifier, and PU-3.6
      has no performance obligation in V1."** A recorded human answer.

      This record's delivery planning resurrected PU-3.6 as live and
      offered a two-way choice between verifiers; the orchestrator
      relayed that choice to the human without checking whether the
      obligation still existed. The honest position is not "manually
      verified" but "deliberately unverified, because deliberately
      dropped" — §11 accepts the risk that a slow path is found by pilot
      feedback rather than by a mechanism.

      **No manual pilot check is required by this unit's Definition of
      Done.** Timing a batch during the pilot remains welcome as
      feedback; it is not an obligation, and D4 is not incomplete without
      it. The delivery-planning artifacts that still describe it as a
      requirement are stale against Q14.3 and are flagged for the human.

  - id: BR7.5
    statement: >
      Every screen this unit ships has a row in the per-screen check
      table before the unit is complete.
    category: policy
    applies_to: Every screen in this unit
    trigger: Unit completion.
    logic: >
      IF this unit adds a screen
      THEN it gets a row in `docs/delivery/bangla-layout-check.md`
      covering the Bangla layout and the named artboard
      AND a screen with no row means an incomplete unit.
    violation_behaviour: >
      Assertable as a file check rather than as a judgement: the row
      exists or it does not. The screens this unit adds are the session
      list, the session detail with the roster, the conflict-resolution
      screen, the exam list, the mark-entry screen, the marksheet, and
      the guardian progress view.
    source: FR0.2, TC-15, D-43
    notes: >
      **The conflict-resolution screen is the one to check hardest**, for
      the reason the project recorded on 2026-10-22: a rule that differs
      by role, written once, serves one role and misleads the other. Here
      the risk is different and related — the screen shows two rosters
      side by side in Bangla, which is the densest text this unit renders
      and the layout most likely to break at the longest string.
```

---

## Rules summary

| ID | Category | What it settles |
|---|---|---|
| BR1.1 | calculation | Sessions exist for every scheduled occurrence |
| BR1.2 | constraint | A schedule change never rewrites history |
| BR1.3 | constraint | Generation idempotency is a unique constraint |
| BR1.4 | policy | Ad-hoc sessions are never touched by generation |
| BR1.5 | authorization | Who is on a session's roster |
| BR1.6 | validation | A cancelled session takes no attendance |
| BR1.7 | policy | Rescheduling preserves identity and attendance |
| BR2.1 | policy | The topic log is the second queued path |
| BR2.2 | constraint | Unlogged differs from logged-empty |
| BR3.1 | policy | **The queue, and why it is not the forbidden one** |
| BR3.2 | constraint | Four states, surviving restart |
| BR3.3 | constraint | **The conditional update; version granularity** |
| BR3.4 | constraint | **One applies, N-1 conflict; sequential proves nothing** |
| BR3.5 | constraint | One atomic roster write |
| BR3.6 | policy | Conflicted is not failed; the entry is preserved |
| BR3.7 | constraint | **Re-apply carries a fresh mutation id** |
| BR3.8 | constraint | A replay returns the original and writes nothing |
| BR3.9 | constraint | Queue states never reach the wire |
| BR3.10 | validation | A descriptive code, after authorization |
| BR3.11 | policy | Interactive writes cannot conflict |
| BR4.1 | validation | Exam shape and subject ownership |
| BR4.2 | validation | A mark's range; a zero is a mark |
| BR4.3 | calculation | The four result states, two of them derived |
| BR4.4 | constraint | Corrections append and supersede |
| BR4.5 | constraint | One live mark per seat, by partial index |
| BR5.1 | authorization | Every route names its lens |
| BR5.2 | authorization | **The six readers that must filter on decisions** |
| BR5.3 | authorization | No profile field reaches a teacher |
| BR5.4 | authorization | The toggle, on an existing column |
| BR5.5 | validation | An inactive batch is read-only |
| BR6.1 | policy | Governance rows for six new tables |
| BR6.2 | calculation | Rank and bands, never a row list |
| BR6.3 | calculation | Band merging, with the computed example |
| BR6.4 | calculation | Thresholds: five results, and completeness |
| BR6.5 | calculation | Absences excluded; never across batches |
| BR6.6 | calculation | Guardian progress; absent is not zero |
| BR7.1 | policy | Announcements, including no expiry |
| BR7.2 | authorization | Student and guardian reads |
| BR7.3 | policy | A server timestamp so a cache can state its age |
| BR7.4 | policy | **PU-3.6: no obligation in V1; it was dropped** |
| BR7.5 | policy | A per-screen row per screen |

## Assumptions & Open Questions

- **The `project.md` NEVER on local write queues needs amending at a
  learnings gate.** Its own cited source, NFR5, reads "Permitted for the
  mid-class path only"; the restatement dropped that scope and now forbids
  what the requirement permits. BR3.1 records the reconciliation and this
  design does not edit memory.
- **The band width of 20 is this design's choice and no upstream artifact
  fixes it.** I searched FR4.5, AC4.3.2–AC4.3.6 and § B of the prior
  `contract-summary.md`; all four say "banded distribution" and none gives a
  width or a count. Five bands of 20 over a percentage is the common form and
  the merge rule in BR6.3 makes the width mostly immaterial — the published
  bands are whatever survives merging. Flagged because it is visible to
  students.
- **The generation horizon for BR1.1 is not specified upstream.** I searched
  FR3.1, FR3.2, AC3.0.1–AC3.0.3 and the prior contract-summary's § B and found
  no horizon. The working assumption in force is **the current calendar month
  plus the next**, generated by the same daily job that D3 built for fee
  cycles, since a horizon that is too long creates sessions for schedule slots
  the teacher is about to change (BR1.2 then freezes them) and one that is too
  short leaves a teacher unable to open tomorrow's class. Stated as the
  assumption in force rather than left open, per the project's recorded
  correction that an open question carrying a proposed default is a decision
  wearing a question's clothes.
