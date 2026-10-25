# Business Rules — D6 `releasing-safely`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D6 `releasing-safely`
**Record**: 261022-remaining-slices

> **This unit's defects are the ones nobody tests, because they are
> absences.** Deletion features ship broken more reliably than any other kind
> for a single reason `team.md` states outright: *nobody tests the absence of
> data.* A deletion that leaves a row behind passes every test anyone thinks
> to write, because every test asserts what is there.
>
> **Three rules carry the unit**, and each exists because the obvious
> implementation is wrong:
>
> - **BR1.3** — a test must assert the row is **gone**, enumerated from the
>   manifest rather than listed by hand, or the one table someone forgets is
>   the one that keeps a child's data.
> - **BR2.1** — the policy is **generated**, because `docs/legal/README.md`
>   already claims it is and no generator exists.
> - **BR4.1** — the purge is **idempotent and chunked**, because the honest
>   failure of a retention job is not deleting too much but dying halfway and
>   being re-run.
>
> Rule IDs are unit-scoped: D6 numbers from `BR1.1` like D1 through D5.

## Sources

- [upstream] this stage's `entities.md` — the cascade defect, the deletion table
- [upstream] `inception/units-generation/unit-of-work.md` — D6's scope
- [prior] `261016-.../inception/user-stories/stories.md` — AC1.6.1–AC1.6.3,
  AC1.7.1–AC1.7.2, AC10.1.1–AC10.1.7
- [prior] ADR-012 — a declined seat keeps the teacher-typed name
- [human] 2026-10-25 — hard-delete the account; `0007` makes **three** links
  `SET NULL`; **a teacher owning any batch cannot delete their account**
- [team] `team.md` — *"Deletion features are the ones most reliably shipped
  broken, because nobody tests the absence of data"*
- [code] read 2026-10-25: `app/db/models.py`, `app/governance/dispositions.py`,
  `app/contract/routes.py`, `docs/legal/PRIVACY.md`, `docs/legal/README.md`

---

```yaml
rules:

  # ==================================================================
  # Group 1: deletion, and proving the absence.
  # ==================================================================

  - id: BR1.1
    statement: >
      Deleting an account hard-deletes the account and profile rows,
      and every credential row belonging to them.
    category: policy
    applies_to: account, profile, otp_request, refresh_token, verify_attempt
    trigger: A confirmed deletion request.
    logic: >
      IF a deletion is confirmed for an account
      THEN DELETE the account row, which cascades its profile and
      credential rows
      AND the phone number is thereby released.
    violation_behaviour: >
      The published policy promises "Deleted permanently, within 30
      days: Your phone number" and a regulator reads it. Assertable:
      after deletion, a query for the account by its id returns
      nothing and a query by phone returns nothing.
    source: AC1.6.1, FR1.14, FR11.1, human 2026-10-25
    notes: >
      **This reverses the manifest's recorded disposition**, which read
      `ANONYMIZE_IN_PLACE` with a basis rejecting hard delete. The
      human chose the policy over the code [2026-10-25], and
      `dispositions.py` is updated to match rather than left to
      disagree. The basis named a real hazard and BR1.2 is what closes
      it.

  - id: BR1.2
    statement: >
      A deleted account's enrollments survive with their links cleared,
      and the clearing is done by the database constraint rather than
      by the deletion code.
    category: constraint
    applies_to: Enrollment
    trigger: Any delete of an account row, from any path.
    logic: >
      IF an account row is deleted
      THEN `student_account_id` and `guardian_account_id` referencing
      it are set to NULL
      AND the enrollment row, its attendance, marks, fee cycles and
      ledger entries all remain.
    violation_behaviour: >
      **Today `student_account_id` is `ondelete="CASCADE"` while
      `guardian_account_id` is `ondelete="SET NULL"`**, so a STUDENT
      deleting their account removes the enrollment row -- and six
      tables cascade from it, taking the teacher's attendance, marks
      and settled fee ledger for that seat. A guardian doing the same
      thing loses nothing. Assertable, and it must be asserted FOR
      BOTH ROLES: a test using only a guardian passes against the
      defect.
    source: AC1.6.2, FR11.1, human 2026-10-25
    notes: >
      **Migration `0007` alters THREE columns to `SET NULL`**, found
      by ENUMERATING every `account.id` reference against its table's
      disposition rather than by reading pairs. The rule falls out of
      that table: **a `CASCADE` to `account.id` is wrong exactly when
      its table's disposition is `RETAIN_WITH_BASIS`**, because the
      manifest already says the row must survive account deletion.
      .
      The three are `enrollment.student_account_id`,
      `payment_claim.submitted_by_account_id` and
      `queued_submission.submitted_by_account_id`. **Two of them are
      `NOT NULL`**, so `0007` makes them nullable as well as altering
      the constraint -- not a one-line `ondelete` flip. Fifteen
      references in all: eight `CASCADE`, seven `SET NULL`; the five
      remaining cascades are correct because their tables are
      `HARD_DELETE`.
      .
      **The first two were found by reading pairs and the third only by
      enumerating**, which is the argument for BR1.3 deriving its table
      from the manifest rather than from a list someone wrote.
      The alternative -- nulling it in the deletion path before
      deleting the account -- works and was declined: a rule enforced
      by remembering is enforced once, and any other path that deletes
      an account row would still cascade. The constraint also closes
      the reuse hazard BR1.1's basis named, because a new account with
      the same number inherits no link to the old one. **Two
      obligations, one constraint**, stated so a later reader does not
      weaken it believing it serves only AC1.6.2.

  - id: BR1.6
    statement: >
      A teacher who owns any batch cannot delete their account, and the
      refusal names what is blocking it.
    category: policy
    applies_to: Both deletion paths
    trigger: A deletion request from an account owning batches.
    logic: >
      IF the account owns an `owner` row with any batch
      THEN refuse the deletion
      AND name the batches, so the teacher can deactivate or hand them
      over
      AND delete nothing.
    violation_behaviour: >
      **This is the largest cascade in the product**:
      `account -> owner -> batch -> enrollment -> six tables`, every
      link `NOT NULL` and `CASCADE`. Without this rule a teacher
      deleting their own account **erases every student's attendance,
      marks and settled fee ledger across every batch they ever ran** --
      records belonging to children who never consented to that
      deletion -- and BR3.2's unauthenticated route takes only a phone
      number, so it is reachable today. Assertable: a teacher with one
      batch is refused, the refusal names the batch, and every row on
      the chain still exists afterwards.
    source: AC1.6.2, FR11.1, human 2026-10-25
    notes: >
      **Each link in the chain is individually defensible**, which is
      why nothing caught it: an `owner` row exists only for its
      account, a `batch` only for its owner. The chain is what is
      wrong, and no single `ondelete` is the culprit.
      .
      **The cascade becomes UNREACHABLE rather than correct**, which is
      the stronger property: it does not depend on six constraints all
      staying right as later units add tables.
      .
      **This makes the published policy wrong**, and `0007` does not
      fix that. `PRIVACY.md` says a teacher's deletion means "their
      students' records are deleted with the class"; under this rule
      that never happens. **BR2.1's generator is what corrects it** --
      the second time in this unit that generating the policy would
      have caught a statement the code contradicts.

  - id: BR1.3
    statement: >
      A deletion test asserts the absence of rows, enumerated from the
      governance manifest rather than listed by hand.
    category: constraint
    applies_to: The deletion test suite
    trigger: Writing or changing a deletion test.
    logic: >
      IF a deletion test runs
      THEN for every table whose disposition is HARD_DELETE it asserts
      ZERO rows remain for that account
      AND for every table whose disposition is RETAIN_WITH_BASIS it
      asserts the rows DO remain
      AND the table list comes from `DISPOSITIONS`, not from a literal
      in the test.
    violation_behaviour: >
      **`team.md`: deletion features are the ones most reliably shipped
      broken, because nobody tests the absence of data.** A hand-listed
      test covers the tables its author thought of; the table added two
      units later keeps a child's personal data and nothing fails.
      Assertable: add a table to `DISPOSITIONS` with HARD_DELETE and no
      deletion handling, and the test must fail WITHOUT being edited.
    source: AC1.6.1, TC-19, RC-4, RC-5, team Testing Posture
    notes: >
      This is the same mechanism the built privacy gate uses -- iterate
      the generated artifact rather than remember per case -- applied
      to deletion. It is what makes D6's suite survive D7.

  - id: BR1.4
    statement: >
      A second deletion request succeeds and changes nothing further.
    category: policy
    applies_to: Both deletion paths
    trigger: A deletion request for an account already deleted.
    logic: >
      IF the account does not exist
      THEN respond as success
      AND write nothing.
    violation_behaviour: >
      A user who clicks twice, or whose network retried, sees an error
      for an action that already succeeded -- and on a deletion screen
      an error reads as "it did not work". Assertable: delete, delete
      again, assert the second returns success and the row counts are
      unchanged.
    source: AC1.6.3, FR11.3
    notes: >
      **This must not be implemented as "look up, then delete if
      found"**, which is a race between two requests. The DELETE is
      idempotent by nature -- deleting zero rows is success -- so the
      rule is to report that honestly rather than to check first.

  - id: BR1.5
    statement: >
      Deletion does not clear a decline.
    category: constraint
    applies_to: Enrollment decision columns
    trigger: An account with declined links is deleted.
    logic: >
      IF a deleted account held an enrollment link whose decision is
      `declined`
      THEN the decision column keeps its value
      AND the seat is not re-prompted to anyone.
    violation_behaviour: >
      A decline is the record of someone saying "this seat is not
      mine" -- often the mistyped-digit case. Resetting it on deletion
      re-exposes a stranger's child to the next person who signs up
      with that number, which is the exposure the acceptance model
      exists to close. Assertable: decline a seat, delete the account,
      assert the decision column still reads `declined`.
    source: US1.6 (amended), ADR-009

  # ==================================================================
  # Group 2: the generated policy.
  # ==================================================================

  - id: BR2.1
    statement: >
      The privacy policy's factual content is GENERATED from the
      governance manifest, not written beside it.
    category: policy
    applies_to: docs/legal/PRIVACY.md
    trigger: Any change to a disposition, retention class or basis.
    logic: >
      IF the policy is produced
      THEN its per-table claims derive from `DISPOSITIONS` and
      `RETENTION`
      AND a test asserts the committed text matches the generated one.
    violation_behaviour: >
      **`docs/legal/README.md` is already headed "The policy is
      generated from the schema, not written beside it", and NO
      GENERATOR EXISTS** -- checked across `app/`, `scripts/`,
      `tests/` and the `Makefile`. The current text was hand-written
      against the schema and verified by a five-row manual table, so
      the heading is a claim nothing checks, on the document a
      regulator reads. Assertable the same way the schema-diff gate
      works: regenerate, compare, fail on drift.
    source: unit-of-work, team Deployment, project.md on unverifiable claims
    notes: >
      **The markers bound what is CHECKED, not what may be claimed,
      and that is the loophole to close.** Nothing stops a factual
      claim being written outside them -- and this is not
      hypothetical: **`docs/legal/README.md` already carries a rival
      per-table disposition list** saying `account` is "hard delete"
      while `dispositions.py` said `ANONYMIZE_IN_PLACE`, which is the
      three-documents-three-answers problem BR2.3 claims to close,
      surviving in a second file. **The generator therefore owns the
      README's table too**, or the table comes out and the README
      points at the policy.
      .
      **Not every sentence is generated and the rule must not pretend
      otherwise.** The policy carries prose a person wrote -- the
      contact address, the reasoning about a teacher's business record,
      the plain-language summary. What is generated is the FACTUAL
      table: which data is deleted, which is kept, and for how long.
      The design obligation is that the generated region is marked and
      the test compares only that region, so a human may still improve
      the surrounding words.

  - id: BR2.2
    statement: >
      The generated text states that a teacher-typed name survives
      deletion.
    category: policy
    applies_to: docs/legal/PRIVACY.md
    trigger: Generating the policy.
    logic: >
      IF the enrollment disposition keeps `display_name`
      THEN the policy says so in words a parent can read
      AND a test asserts the generated text contains that disclosure.
    violation_behaviour: >
      [ADR-012] decided a declined seat keeps the teacher-typed name,
      which is the sharpest edge of this product's privacy model: a
      person who never consented, and who declined, still appears in a
      teacher's record under a name the teacher typed. **A policy that
      omits it is a false statement to a regulator about children's
      data.** Assertable: the generated text contains the disclosure,
      asserted against the generated output rather than the committed
      file, so the test fails if the generator stops emitting it.
    source: ADR-012, unit-of-work, RC-4, RC-5

  - id: BR2.3
    statement: >
      The policy and the manifest cannot disagree, and the test is what
      makes that true.
    category: constraint
    applies_to: docs/legal/PRIVACY.md, app/governance/dispositions.py
    trigger: Any disposition change.
    logic: >
      IF a disposition changes and the policy is not regenerated
      THEN `make check` fails
      AND the failure names the table whose text drifted.
    violation_behaviour: >
      **This conflict already happened and is what this unit found.**
      The manifest said `account` was `ANONYMIZE_IN_PLACE`; the policy
      promised the phone number is "deleted permanently"; the legal
      README's table said "hard delete". Three documents, three
      answers, nothing failing. Assertable by the gate itself.
    source: team.md on generated policy, this unit's own finding
    notes: >
      The same shape as the built OpenAPI schema-diff gate, and for
      the same reason: a committed artifact derived from code must be
      regenerated in the change that alters its source, or it becomes
      a claim about an older version.

  # ==================================================================
  # Group 3: the two paths.
  # ==================================================================

  - id: BR3.1
    statement: >
      Both deletion paths reach the same code and produce the same
      result.
    category: constraint
    applies_to: The in-app path, the external route
    trigger: Either deletion path.
    logic: >
      IF deletion proceeds by either route
      THEN both call one deletion function
      AND the outcome is identical row for row.
    violation_behaviour: >
      Two implementations drift, and the one that drifts is the
      external route -- used less, tested less, and the one Play
      requires. Assertable: run both paths against identical fixtures
      and compare the surviving row sets, rather than asserting each
      against a hand-written expectation.
    source: AC1.7.1, TC-19

  - id: BR3.2
    statement: >
      The external route is reachable without the app and verifies
      ownership of the number before deleting.
    category: authorization
    applies_to: GET and POST /account-deletion
    trigger: A request to the external route.
    logic: >
      IF the external route is requested
      THEN it requires no app session
      AND it proves ownership by the same OTP mechanism the app uses
      AND it names the app and the developer.
    violation_behaviour: >
      Without ownership proof the route deletes anyone's account given
      their number, which is a denial-of-service against every user.
      With an app session required it fails Play's requirement that
      deletion work without reinstalling. Assertable: the route answers
      unauthenticated, and a POST without a verified code deletes
      nothing.
    source: AC1.7.1, AC1.7.2, FR1.15, RC-4
    notes: >
      **Both routes are already in `PUBLIC_ROUTES`**, declared in D1
      with the comment "pre-declared D6 scope". D6 lands handlers
      against entries that exist, so the asserted count of eight does
      not change.

  - id: BR3.3
    statement: >
      The OTP ceilings apply to the deletion route exactly as they
      apply to sign-in.
    category: validation
    applies_to: The external route
    trigger: An OTP issued for deletion.
    logic: >
      IF the deletion route issues a code
      THEN it consumes the same per-number, per-IP and global ceilings
      AND a ceiling breach refuses with the same ConflictError.
    violation_behaviour: >
      An unauthenticated public endpoint that issues SMS without
      ceilings is a way to spend the project's entire messaging budget
      from a script -- the exact attack the ceilings exist for, through
      a door added later. Assertable: the deletion route's issue path
      increments the same counters, asserted by the built ceiling
      tests extended to it.
    source: NFR12, NFR12.1, D-33

  # ==================================================================
  # Group 4: retention, enforced for the first time.
  # ==================================================================

  - id: BR4.1
    statement: >
      The purge is idempotent and chunked, and deletes only what a
      finite retention class names.
    category: constraint
    applies_to: The retention purge
    trigger: The scheduled run.
    logic: >
      IF the purge runs
      THEN for each table with a finite RetentionClass it deletes rows
      older than that window, in bounded batches
      AND re-running it immediately deletes nothing more
      AND a run interrupted halfway leaves a consistent state.
    violation_behaviour: >
      **The honest failure of a retention job is not deleting too much
      -- it is dying halfway and being re-run.** An unchunked DELETE
      over a year of `otp_request` rows locks the table on the single
      small instance this product runs on. Assertable in three parts:
      a second immediate run deletes zero; an interrupted run leaves no
      partial state; and a batch size is bounded rather than "all
      matching rows".
    source: unit-of-work, team Deployment on retention
    notes: >
      **Nothing deletes anything on a retention window today.** The
      precise claim, corrected after review: the `RetentionClass` ENUM
      is used only in its own module, and `RETENTION` is imported by
      `tests/db/test_governance.py:17` -- which asserts every table
      HAS a class, never that any window is honoured. Seven tables
      carry finite windows and no code acts on one, so the purge is
      NEW behaviour rather than a scheduled version of something
      existing. That is why BR4.2 exists.
      .
      **The batch size is 1,000 rows and the commit boundary is per
      chunk**, stated as numbers rather than as "bounded" because an
      unstated bound is not a bound. Each chunk commits before the
      next begins, which is what makes an interrupted run leave a
      consistent state -- "leaves a consistent state" is trivially
      true of any single DELETE and says nothing on its own. **The
      number is a starting point, not a measurement**: nothing has
      been run against production volumes, and the figure is small
      enough to be safe on the single small instance this product
      runs on.

  - id: BR4.2
    statement: >
      The purge deletes nothing whose retention class is
      LIFE_OF_ACCOUNT.
    category: constraint
    applies_to: The retention purge
    trigger: Every purge run.
    logic: >
      IF a table's retention is LIFE_OF_ACCOUNT
      THEN the purge does not touch it, at any age.
    violation_behaviour: >
      Eighteen of the twenty-five tables are LIFE_OF_ACCOUNT,
      including every attendance, mark and ledger row. A purge that
      treated "no window" as "any age" would delete the product's
      entire history on its first run. Assertable, and it must be
      asserted with aged fixtures: a row dated two years back in a
      LIFE_OF_ACCOUNT table survives a purge.
    source: dispositions.py, AC1.6.2
    notes: >
      Stated as its own rule because the dangerous implementation is
      the natural one -- iterating all tables and applying a default
      window to those without an explicit one.

  - id: BR4.3
    statement: >
      The purge's deletions obey the same foreign keys as a deletion
      does.
    category: constraint
    applies_to: The retention purge
    trigger: Purging a table other rows reference.
    logic: >
      IF a purged row is referenced
      THEN the reference is cleared or cascaded per the constraint
      AND the purge never leaves a dangling reference.
    violation_behaviour: >
      A purge that deletes around a foreign key fails loudly, which is
      fine. One that deletes WITH a cascade nobody expected is the
      BR1.2 defect by another route. Assertable: purge with referenced
      rows present and assert the referencing rows' state explicitly.
    source: BR1.2, this unit's cascade finding

  # ==================================================================
  # Group 5: the invariants this unit asserts rather than builds.
  # ==================================================================

  - id: BR5.1
    statement: >
      Every refusal in the application is an AuthorizationError that
      does not disclose whether the resource exists.
    category: authorization
    applies_to: The whole application
    trigger: Unit completion.
    logic: >
      IF a caller requests a resource their lens does not reach
      THEN the refusal is identical to the refusal for a resource that
      does not exist
      AND it carries retryable false.
    violation_behaviour: >
      Assertable by the BUILT error-contract test, which already
      asserts exactly one resource-refusal code exists. **D6 builds
      nothing here**; its obligation is to run the invariant against
      the FINAL schema, after six units of routes.
    source: AC10.1.1-AC10.1.4, NFR14

  - id: BR5.2
    statement: >
      No teacher-lens response schema contains an owner-private profile
      field, and every route resolves a lens.
    category: authorization
    applies_to: The generated OpenAPI document
    trigger: Unit completion.
    logic: >
      IF the final schema is generated
      THEN the built privacy gate and route-enumeration test pass over
      ALL routes
      AND `PUBLIC_ROUTES` holds exactly eight.
    violation_behaviour: >
      Both gates are built and schema-wide by construction, so the
      obligation is to run them against the completed product rather
      than to add a mechanism. Assertable: `make check`, unchanged.
    source: AC10.1.5, AC10.1.7, TC-13
    notes: >
      **D6 is a `spec` unit and this is what that means**: most of
      Group 5 is already enforced. Stating these as rules rather than
      omitting them is what makes "the invariants hold against the
      final schema" a checked claim rather than an assumption.

  - id: BR5.3
    statement: >
      A client-supplied lens hint is never trusted for authorization.
    category: authorization
    applies_to: Lens resolution
    trigger: Any request carrying a hint.
    logic: >
      IF a request carries a lens hint
      THEN it affects navigation only
      AND the lens is resolved from owned batches and enrollments.
    violation_behaviour: >
      Assertable: a request claiming a teacher lens from an account
      owning no batch resolves no teacher lens. Built in D1; D6
      asserts it survives.
    source: AC10.1.6, TC-11, D-2

  - id: BR5.4
    statement: >
      Every table in the final schema carries a disposition and a
      retention class.
    category: policy
    applies_to: app/governance/dispositions.py
    trigger: Unit completion.
    logic: >
      IF the final schema is live
      THEN the built governance test passes in BOTH directions
      AND the count is 25.
    violation_behaviour: >
      The second direction is the one that matters at the end of a
      project: a disposition naming a table that no longer exists is
      what a long sequence of units produces, and a one-directional
      check misses it.
    source: ADR-003, ADR-004, TC-19
```

---

## Rules summary

| ID | Category | What it settles |
|---|---|---|
| BR1.1 | policy | Hard-delete the account; the number is released |
| BR1.2 | constraint | **The cascade defect, fixed by `0007` rather than by code** |
| BR1.3 | constraint | **Assert the ABSENCE, enumerated from the manifest** |
| BR1.4 | policy | A second deletion succeeds and changes nothing |
| BR1.5 | constraint | Deletion does not clear a decline |
| BR2.1 | policy | **The policy is generated — the README already claims it is** |
| BR2.2 | policy | The generated text discloses the surviving teacher-typed name |
| BR2.3 | constraint | Policy and manifest cannot drift |
| BR3.1 | constraint | Both paths reach one implementation |
| BR3.2 | authorization | The external route proves ownership without a session |
| BR3.3 | validation | The deletion route consumes the OTP ceilings |
| BR4.1 | constraint | **Idempotent and chunked — the failure is being re-run** |
| BR4.2 | constraint | `LIFE_OF_ACCOUNT` is never purged |
| BR4.3 | constraint | The purge obeys the same foreign keys |
| BR5.1 | authorization | Refusals disclose nothing — asserted, not built |
| BR5.2 | authorization | The schema-wide gates, run against the final schema |
| BR5.3 | authorization | No trusted lens hint |
| BR5.4 | policy | Governance complete in both directions |

## Assumptions & Open Questions

- **The generated region of the policy is marked and the test compares only
  that region** [BR2.1]. The alternative — generating the whole document —
  would discard reviewed human prose, including the reasoning a parent
  actually reads. **Where the markers go is implementation; that there are
  markers is the rule.**
- **`Account.deleted_at` becomes unused** under a hard delete. This design
  does not drop it, because an unused column is the smaller change and
  dropping it is irreversible. **Its docstring says "Reserved for U11's
  deletion paths" and that is now wrong** — the docstring is corrected in
  `0007`'s change even though the column stays.
- **The 30-day promise is satisfied by a synchronous delete**, which this
  design builds. If deletion ever becomes queued, the promise acquires a
  mechanism it does not have today.
- **`guardian_phone` on the enrollment survives deletion** and is a phone
  number the teacher typed. ADR-012 covers it and the policy discloses it;
  **this is the sharpest edge of the disclosure** and BR2.2's test is what
  keeps it stated.
- **No figure in this document was measured.** D6's code does not exist. The
  counts quoted — 25 dispositions, eight public routes, six tables cascading
  from `enrollment`, seven finite retention windows — were each read from the
  code on 2026-10-25.
