# Business Rules — `batches-and-enrollment` (U4)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

## Sources

- [stage] `functional-design-questions.md`
- [upstream] `inception/user-stories/stories.md` — AC1.3.x, AC2.1.x–AC2.8.x
- [upstream] `inception/units-generation/unit-of-work.md` — U4
- [upstream] `inception/contract-design/contract-summary.md` — §B.4, OQ-7
- [upstream] `construction/identity-and-access/functional-design/rules.md`
  — BR1.1, BR3.1, BR6.1, the rules this Unit inherits
- [upstream] `inception/domain-design/decisions.md` — ADR-001, D-2
- [team] `## Testing Posture`, `## Code Style`
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
rules:

  # ---- BR1.x - Ownership and the indirection ----

  - id: BR1.1
    statement: >
      A batch belongs to an Owner, never directly to an Account. U4 is
      the first and only writer of the Owner table.
    category: constraint
    applies_to: Batch creation
    trigger: A teacher creates their first batch
    logic: >
      IF a teacher creates a batch AND no Owner row exists for them
      THEN create one
      AND record the batch against that Owner id.
    violation_behaviour: >
      batch.account_id. It works, it is simpler, and it makes a
      subscription anchor to a person who can then never hand the batch
      over. Caught by a schema assertion that Batch has no account_id
      column at all.
    rationale: >
      The indirection exists for two reasons that are easy to forget
      once the code works: a subscription needs something to attach to
      that is not an identity, and ownership must be transferable
      without rewriting every batch row.

      U3 created this table EMPTY and a test asserted it never wrote it
      [U3 BR6.1]. That test must now be **narrowed to U3's own modules**
      rather than deleted, or U4's legitimate writes will fail it.
    source: [AC2.1.3, FR2.2]

  - id: BR1.2
    statement: >
      Only the Owner's subscription fields are visible to a platform
      administrator. No student, guardian or child data is.
    category: authorization
    applies_to: Any administrative surface
    trigger: Any read on behalf of a platform administrator
    logic: >
      IF a platform administrator reads anything
      THEN it is drawn from Owner.subscription_* and Account.phone of
      the TEACHER only
      ELSE it is refused.
    violation_behaviour: >
      An admin endpoint joining to Enrollment "to show how many
      students" leaks the roster's existence and size.
    rationale: >
      There is no admin surface in V1, so this rule has nothing to
      guard yet. It is recorded now because the Owner table is being
      written for the first time and the temptation arrives with it.
    source: [TC-14, D-6, project.md NEVER]

  # ---- BR2.x - The display name and the privacy boundary ----

  - id: BR2.1
    statement: >
      display_name belongs to the Enrollment. Editing it changes every
      teacher-facing view and never touches the person's Profile.
    category: authorization
    applies_to: Enrollment edit
    trigger: A teacher edits a display name
    logic: >
      IF a teacher edits display_name
      THEN the Enrollment row changes
      AND Profile is not read and not written.
    violation_behaviour: >
      An UPDATE touching Profile, or a read that falls back to
      Profile.self_name when display_name is empty. The fallback is the
      more likely one and it is a privacy breach wearing a convenience.
    rationale: >
      U3 made this structural by splitting the tables [BR3.1]. U4 is
      the first Unit that actually WRITES display_name, so it is the
      first place the split can be violated by a well-meant fallback.

      A test asserts no U4 module references Profile at all.
    source: [AC2.2.2, AC2.3.1, AC2.3.2, FR2.4, FR2.5]

  - id: BR2.2
    statement: >
      The same person enrolled in two batches has two independent
      enrollments, each with its own display name and fee.
    category: constraint
    applies_to: Enrollment
    trigger: A second enrollment for an existing account
    logic: >
      IF a number already has an Account
      THEN attach the new Enrollment to that Account
      AND do not copy, merge or reconcile the other enrollment's
      display_name or fee.
    violation_behaviour: >
      A unique constraint on (batch-less) account_id, or an "update the
      student's name" path that writes both rows.
    rationale: >
      Attach-to-existing is what makes one permanent account work
      across teachers [AC2.2.4]. The independence is what stops
      teacher A's naming from reaching teacher B's roster.
    source: [AC2.2.3, AC2.2.4, FR2.9, FR1.10]

  # ---- BR3.x - The fee anchor ----

  - id: BR3.1
    statement: >
      fee_override is nullable. NULL means inherit the batch default;
      zero means a fee of zero.
    category: constraint
    applies_to: Enrollment
    trigger: Fee resolution for any period
    logic: >
      IF enrollment.fee_override IS NULL
      THEN charge batch.default_monthly_fee
      ELSE charge enrollment.fee_override, including when it is zero.
    violation_behaviour: >
      A NOT NULL column defaulting to 0, which makes "inherit" and
      "waived" the same value and silently charges nothing.
    rationale: >
      U7 charges against this anchor and cannot distinguish the two
      cases after the fact. The distinction has to exist in the column.
    source: [AC2.2.5, FR2.8]

  - id: BR3.2
    statement: >
      Every money column this Unit creates is NUMERIC(12,2) through
      U1's TypeDecorator, never a float and never an unconstrained
      numeric.
    category: constraint
    applies_to: The migration
    trigger: Any money column
    logic: >
      IF a column carries money
      THEN it is declared through app.money's TypeDecorator.
    violation_behaviour: >
      A hand-written migration declaring `numeric` without precision.
    rationale: >
      **B3 armed this assertion and it was VACUOUS there**, because U3
      carries no money. U4 is the first Unit with a real money column,
      so the test stops being a statement of intent and starts
      checking something. That transition is worth naming: a gate
      nobody has seen fail is a gate nobody has seen work.
    source: [NFR9.32, TC-7, D-20, project.md NEVER]

  # ---- BR4.x - inactive_from, which fails quietly ----

  - id: BR4.1
    statement: >
      No fee cycle generates for a period beginning STRICTLY AFTER
      inactive_from. The period CONTAINING the date generates in full.
    category: calculation
    applies_to: Enrollment
    trigger: Fee generation, and any read that reports future liability
    logic: >
      IF period.START_DATE > enrollment.inactive_from
      THEN no cycle
      ELSE a cycle at the full resolved fee, with no proration.

      The comparison is against the period's START DATE — the first of
      the calendar month — and NEVER against its due date.
    violation_behaviour: >
      Two, and the second was found by working the dates rather than by
      reading the rule:

      1. Prorating the containing period. It LOOKS fairer and it is a
         money bug: the teacher taught that month and the requirement
         says it charges in full unless they adjust it.
      2. **Comparing against the DUE DATE instead of the period start.**
         Worked: `fee_due_day` 31, `inactive_from` 2026-02-15. February's
         period starts 2026-02-01 (≤ the date, so it generates — correct
         per AC2.4.4) but its clamped due date is 2026-02-28 (> the date,
         so it would NOT generate — silently waiving a month the teacher
         taught).

         The misreading is plausible rather than careless: AC2.1.2's
         clamp rule is *about* due dates, and `fee_due_day` sits on the
         same entity as everything else here.
    
    rationale: >
      **Three separate named tests, not one with three assertions**, so
      a failure reports which property broke. The three are: nothing
      after, the containing period in full, and other enrollments
      untouched.

      Test-first by `team.md`'s predicate: the correct output is
      knowable from the requirement and a wrong answer is a money
      error.
    source: [AC2.4.1, AC2.4.4, AC2.4.5, FR2.11, FR5.6, Q7.1]

  - id: BR4.2
    statement: >
      Existing unpaid cycles stand unchanged when an enrollment is
      marked inactive.
    category: constraint
    applies_to: Enrollment
    trigger: Marking inactive
    logic: >
      IF an enrollment is marked inactive
      THEN no existing FeeCycle or LedgerEntry is modified or deleted.
    violation_behaviour: >
      A cascade that cancels outstanding dues, which erases money a
      student actually owes.
    rationale: >
      Marking inactive is a statement about the FUTURE. U7 owns the
      ledger and this Unit must not reach into it.
    source: [AC2.4.2, FR2.11]

  - id: BR4.3
    statement: >
      Marking an enrollment inactive in one batch does not affect the
      same account's enrollments in any other batch.
    category: constraint
    applies_to: Enrollment
    trigger: Marking inactive
    logic: >
      IF an enrollment is marked inactive
      THEN exactly one row changes.
    violation_behaviour: >
      An UPDATE keyed on account_id rather than enrollment id. Plausible
      because "mark this student inactive" reads as being about the
      student.
    rationale: >
      The phrase in the requirement is about a STUDENT; the operation
      is about an ENROLLMENT. That gap is where the bug lives.
    source: [AC2.4.3, FR2.11]

  # ---- BR5.x - The guardian route shape, settling OQ-7 ----

  - id: BR5.1
    statement: >
      The guardian's selected child travels as a PATH PARAMETER
      (`/v1/guardian/children/{enrollment_id}/...`), never in the lens
      hint. The server validates it against reachable enrollments on
      every request.
    category: authorization
    applies_to: Every guardian-facing route
    trigger: Any guardian request
    logic: >
      IF a guardian requests a child-scoped resource
      THEN the child is named in the path
      AND the server verifies that enrollment is reachable from the
      authenticated account
      ELSE 404, never 403.
    violation_behaviour: >
      Carrying the child in X-Lens-Hint. The hint is explicitly
      non-authoritative [D-2] and the server is REQUIRED to distrust
      it — so a privacy-relevant selection would ride a field whose
      whole contract is that it does not decide anything.
    rationale: >
      **This settles OQ-7**, which the contract stage left open for
      this Unit with the guardian screens in view.

      Three reasons the path parameter wins, and the cost is real:

      1. **It is loggable and testable per request.** A header that
         selects a child is invisible in a route table, so the
         route-enumeration gate cannot see which routes are
         child-scoped.
      2. **The hint is non-authoritative by construction.** Putting a
         privacy decision in it would require trusting a field D-2
         forbids trusting, or re-validating it anyway — in which case
         the path parameter is the same work, visible.
      3. **Back-stack correctness is a privacy case** [AC9.4.2]. A URL
         that names the child makes a stale back-stack entry wrong in a
         way the server can refuse; a header makes it silently serve
         the newly selected child's data under the old screen.

      **The cost**: every guardian route carries an extra segment, and
      the client must thread the id. That is accepted.

      **404 rather than 403**, per the contract's uniform rule: a 403
      on an unreachable enrollment confirms it exists.
    source: [OQ-7, FR2.14, FR2.17, AC9.4.2, D-2]

  - id: BR5.2
    statement: >
      Zero reachable children, one, and more than one are three
      distinct outcomes, and the single-child case still shows
      attribution. The count is of DISTINCT CHILDREN, never of
      enrollments.
    category: policy
    applies_to: Guardian sign-in
    trigger: A guardian's first authenticated request
    logic: >
      LET children = DISTINCT student_account_id over the reachable
      enrollments
      IF len(children) == 0 THEN an empty state explaining a teacher
      must record the number
      ELSE IF len(children) == 1 THEN go straight to that child, still
      naming the teacher and the masked number
      ELSE present the selection list, one entry per CHILD.
    violation_behaviour: >
      Two failures, and the second was found by working the cases
      rather than by reading the rule:

      1. Skipping attribution in the single-child case. AC2.8.5 names
         this as the case the explanation is MOST needed in, because
         the selection list is where attribution would otherwise have
         been shown.
      2. **Counting ENROLLMENTS rather than children.** AC2.2.3
         explicitly permits the same student in two batches of the
         SAME teacher, each a separate enrollment. With one guardian
         number on both, an enrollment count returns 2 for one child —
         so the guardian is shown a selection list naming the same
         child twice, violating AC2.8.2, and never reaches the
         straight-through path AC2.7.2 requires.
    rationale: >
      An empty list and "no children" are different states and a blank
      screen explains neither.

      **The cardinality is the subtle part.** The acceptance criteria
      say "children"; the reachability query returns ENROLLMENTS; and
      BR5.1 keys the route on `enrollment_id`. Three different
      granularities, and the naive implementation conflates the first
      two. The selection list is keyed on the child and each entry
      carries that child's enrollments, which is also what lets one
      entry name more than one batch.
    source: [AC2.7.1, AC2.7.2, AC2.8.2, AC2.8.5, AC2.8.6, AC2.2.3, FR2.14, FR2.15]

  - id: BR5.4
    statement: >
      A child-scoped route names an ENROLLMENT; the selection list
      names a CHILD. When a child has several reachable enrollments,
      selecting that child resolves to all of them, not to one.
    category: constraint
    applies_to: Guardian routes and the selection list
    trigger: A guardian selects a child
    logic: >
      IF a child has N reachable enrollments
      THEN the selection list shows ONE entry
      AND that entry's batch view covers all N
      AND each child-scoped route still names exactly one
      enrollment_id, validated for reachability.
    violation_behaviour: >
      Treating "the selected child" as a single enrollment id, which
      silently drops the child's other batches under the same teacher.
    rationale: >
      BR5.1 chose `enrollment_id` as the path key for good reasons —
      it is the teacher-facing identifier and never an account id
      [ADR-001]. But a child is not an enrollment, and this rule is
      what stops that choice from quietly redefining what "child"
      means in the UI.

      Recorded as its own rule rather than a clause of BR5.1, because
      the two decisions can be changed independently.
    source: [AC2.2.3, AC2.7.1, AC2.8.2, ADR-001]

  - id: BR5.3
    statement: >
      A guardian signing in with one number sees only the enrollments
      recorded against that number, and each child appears once.
    category: authorization
    applies_to: The guardian batch list
    trigger: Any guardian read
    logic: >
      IF a guardian is authenticated as PN1
      THEN reachable enrollments are those whose guardian_account_id is
      PN1's account
      AND the same child recorded by another teacher under PN2 does not
      appear.
    violation_behaviour: >
      Resolving reachability through the CHILD rather than through the
      recorded guardian number, which merges two teachers' records and
      shows each teacher data the other's guardian recorded.
    rationale: >
      **This is the human's stated top risk at its first genuinely
      multi-party test.** B3 could only demonstrate the lens mechanism
      against one account; B5 is the first Bolt with two teachers to
      leak between.
    source: [AC2.8.1, AC2.8.2, FR2.7, FR2.18]

  # ---- BR6.x - Removal, and what it must refuse ----

  - id: BR6.1
    statement: >
      An enrollment may be deleted only while dormant AND free of
      attendance, marks and fee history. Otherwise removal is refused
      and marking inactive is offered.
    category: constraint
    applies_to: Enrollment removal
    trigger: A delete request
    logic: >
      IF claimed_at IS NULL AND no attendance, mark or fee row
      references this enrollment
      THEN delete
      ELSE refuse with a ConflictError naming the inactive path.
    violation_behaviour: >
      A cascade delete. It would remove the teacher's own attendance
      and marks records, which are the teacher's business record as
      well as the child's data.
    rationale: >
      The check must consult tables U5, U6 and U7 own and this Unit
      does not. At B5 those tables do not exist yet, so the check is
      written against the tables that DO exist and extended as each
      arrives — with the extension recorded as an obligation on each
      later Unit rather than left to be remembered.
    source: [AC2.5.1, AC2.5.2, FR2.12]

  - id: BR6.2
    statement: >
      Never-claimed is distinguishable from claimed-and-then-deleted.
    category: constraint
    applies_to: Enrollment
    trigger: Any roster or detail read
    logic: >
      IF claimed_at IS NULL AND deleted_at IS NULL THEN never claimed
      ELSE IF claimed_at IS NOT NULL AND deleted_at IS NOT NULL THEN
      claimed and later deleted.
    violation_behaviour: >
      One nullable timestamp carrying both meanings.
    rationale: >
      The first is probably a mistyped number the teacher should fix;
      the second is a person who left. The remedies are opposite.
    source: [AC1.3.6, FR1.8]

  - id: BR6.3
    statement: >
      A dormant enrollment is never notified, never invited, and never
      marked on the roster.
    category: policy
    applies_to: Dormant enrollments
    trigger: Any notification dispatch or roster render
    logic: >
      IF an enrollment has claimed_at IS NULL
      THEN send nothing to its number
      AND render no per-row marker.
    violation_behaviour: >
      An invitation SMS. It would spend money on the control U3 built
      ceilings for, and contact a person who never asked to be
      contacted.
    rationale: >
      Dormant is the NORMAL state early in a batch's life [AC1.3.3].
      Decorating most rows flags normality as exceptional, and the
      count at batch level carries the same information without the
      clutter [AC1.3.5].
    source: [AC1.3.1, AC1.3.2, AC1.3.3, AC1.3.5, FR1.7]

  # ---- BR7.x - The Room cache pattern this Unit establishes ----

  - id: BR7.1
    statement: >
      Room entities mirror the API DTO one-to-one, carry only an added
      fetched_at, and hold no derived field.
    category: constraint
    applies_to: The Android read cache
    trigger: Any cached read
    logic: >
      IF a Room entity is defined
      THEN its fields are the DTO's fields plus fetched_at
      ELSE it is a shadow model.
    violation_behaviour: >
      A computed column — a formatted fee, a status, a count. Each one
      is a business rule on the client and a second place for it to
      diverge.
    rationale: >
      **U4 establishes the pattern every later Unit copies**, so a
      defect here propagates by imitation rather than by import. A test
      asserts each Room entity's field set equals its DTO's plus
      exactly one.

      Room is a READ cache [TC-8, D-9]. V1 accepts no write without
      connectivity, so there is no write queue to reconcile.
    source: [TC-8, TC-9, D-9, D-31, unit-of-work U4 implementation notes]
```

---

## Part B — Rules summary

| Rule | Category | What it fixes |
|---|---|---|
| **BR1.1** | constraint | Batches belong to an Owner, not an account |
| **BR1.2** | authorization | An administrator sees subscription data and nothing else |
| **BR2.1** | authorization | A teacher's edit never reaches the student's profile |
| **BR2.2** | constraint | Two enrollments of one person stay independent |
| **BR3.1** | constraint | Null fee means inherit; zero means waived |
| **BR3.2** | constraint | Every money column is NUMERIC(12,2) — first real test |
| **BR4.1** | calculation | `inactive_from`: nothing after, containing period in full |
| **BR4.2** | constraint | Existing dues stand |
| **BR4.3** | constraint | One enrollment changes, not the student's others |
| **BR5.1** | authorization | The child is a path parameter — **settles OQ-7** |
| **BR5.2** | policy | Zero, one and many **children** — counted as children, not enrollments |
| **BR5.4** | constraint | A route names an enrollment; the list names a child |
| **BR5.3** | authorization | Two teachers' guardian records never merge |
| **BR6.1** | constraint | Removal refused once history exists |
| **BR6.2** | constraint | Never-claimed ≠ claimed-then-deleted |
| **BR6.3** | policy | A dormant enrollment is never contacted |
| **BR7.1** | constraint | Room mirrors the DTO and derives nothing |

---

## Assumptions & Open Questions

**None open.** [assumption] OQ-7 is settled by BR5.1 rather than
carried forward, because the contract stage named this Unit as the
place to decide it and the guardian screens are in view here.

[assumption] BR6.1's history check cannot be complete at B5, because
the attendance, mark and fee tables belong to U5, U6 and U7 and do not
exist yet. It is written against what exists and **each later Unit
carries an obligation to extend it** — recorded in that Unit's rules
rather than left as a comment here, since a comment in this file is not
somewhere a later Bolt's author will look.
