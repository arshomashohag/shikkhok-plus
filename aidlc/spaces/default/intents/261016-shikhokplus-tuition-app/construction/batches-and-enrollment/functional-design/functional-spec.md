# Functional Specification — `batches-and-enrollment` (U4)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U4 `batches-and-enrollment` — `service`, L
**Bolt**: B5 `b5-batches-and-enrollment`

> **The first Unit with two teachers in it.** U3 proved the lens
> mechanism against one account; this is the first Bolt where there are
> two teachers for data to leak between, and the human's stated top
> risk gets its first genuine test.
>
> It is also the first Unit to **write** the tables U3 created empty,
> and the first with a real money column — which turns B3's
> money-column assertion from a statement of intent into a check.

## Sources

- [stage] `functional-design-questions.md`
- [upstream] `functional-design/rules.md` — BR1.1–BR7.1
- [upstream] `functional-design/entities.md`
- [upstream] `inception/user-stories/stories.md` — US1.3, US2.1–US2.8
- [upstream] `inception/contract-design/contract-summary.md` — §B.4, §B.5, OQ-7
- [upstream] `construction/identity-and-access/functional-design/rules.md`
- [team] `## Testing Posture`, `## Code Style`
- [project] `## Forbidden` / `## Mandated`

---

## 1. What this Unit delivers

| # | Deliverable | Surface |
|---|---|---|
| 1 | Batch CRUD with subjects and schedule slots | Teacher lens |
| 2 | `Owner` row creation on first batch | Backend only |
| 3 | Add student, with dormant-account resolution and attach-to-existing | Teacher lens |
| 4 | Per-enrollment guardian, display name and fee override | Teacher lens |
| 5 | `inactive_from` semantics | Teacher lens |
| 6 | Edit and remove, with removal refused once history exists | Teacher lens |
| 7 | Student batch list and the hide-batch preference | Student lens |
| 8 | Guardian child selection and child-scoped routes | Guardian lens |
| 9 | Room read-cache pattern, established for every later Unit | Android |
| 10 | Governance manifest rows for every table created here | Backend |

**The teacher lens finally has something to scope.** U3 built
`TeacherLens` carrying `owner_id` and no route used it; every teacher
route here is scoped by it, which is the first real exercise of the
data-dependency design.

---

## 2. Operations

### 2.1 Create a batch — `POST /v1/batches`

1. Resolve the teacher lens. If the account has no `Owner` row, **create
   one** [BR1.1] — this is the only place an `Owner` is created.
2. Validate `fee_due_day` is 1–31. Values 29–31 are legal; the clamp is
   U7's arithmetic at generation time [AC2.1.2].
3. Insert `Batch`, then its `BatchSubject` rows (one or more) and
   `ScheduleSlot` rows, in one transaction.
4. Return the batch with its subjects and slots.

> **`default_fee` is the first real money column in the
> schema.** B3's type-and-precision assertion was vacuously true there;
> here it has something to check [BR3.2].

### 2.2 Add a student — `POST /v1/batches/{batch_id}/enrollments`

1. Scope the batch by the teacher's `owner_id`. A batch belonging to
   another owner returns **404**, not 403 — the uniform rule, so the
   response does not confirm the batch exists.
2. Resolve the student's number:
   - an `Account` exists → **attach to it** [AC2.2.4];
   - none exists → create a **dormant** `Account` (`activated_at` null).
3. Same for the guardian number, when supplied. The guardian is **per
   enrollment** — recording a guardian here does not make them a
   guardian of any other enrollment.
4. Insert the `Enrollment` with the teacher-typed `display_name`, the
   optional `fee_amount` (null means inherit [BR3.1]), and
   `claimed_at` null.
5. **Send nothing** [BR6.3]. No invitation, no notification.

> **Step 2 is where the permanent-account design pays off and where it
> can be broken.** Attaching to an existing account is what lets one
> person be a student of teacher A and a guardian for teacher B. Creating
> a second account for a known number would silently fork the person.

### 2.3 Edit an enrollment — `PATCH .../enrollments/{id}`

1. Scope by `owner_id`.
2. `display_name`, `fee_amount`, `guardian_account_id` and
   `inactive_from` are editable. **`Profile` is never read or written**
   [BR2.1].
3. An edit changes **exactly one row** [BR4.3].

### 2.4 Mark inactive — the three properties

Setting `inactive_from` must satisfy all three independently [BR4.1–BR4.3]:

| Property | Named test |
|---|---|
| No cycle for a period starting **strictly after** the date | `test_no_cycle_generates_for_a_period_beginning_after` |
| The period **containing** the date generates **in full** | `test_the_containing_period_charges_in_full` |
| Other enrollments of the same account are untouched | `test_other_enrollments_are_unaffected` |
| The comparison uses the period **start**, never the due date | `test_the_comparison_is_against_the_period_start` |

> **The fourth test exists because the third property has a plausible
> wrong reading.** Worked: `fee_due_day` 31, `inactive_from` 2026-02-15.
> February starts 2026-02-01 and generates — correct. Its clamped due
> date is 2026-02-28, which is *after* the inactive date, so a rule read
> against the due date silently waives a month the teacher taught.
>
> That misreading is reachable rather than careless: AC2.1.2's clamp
> rule is about due dates, and `fee_due_day` sits on the same entity.

> **The middle one looks wrong and is right.** Marking a student
> inactive on the 10th does not prorate that month. An implementer who
> "fixes" it to prorate writes a money bug no test outside this Unit
> would catch [AC2.4.5].
>
> U4 **records** `inactive_from`; U7 **reads** it when generating. The
> tests here assert the predicate U7 will apply, against a stub, so the
> semantics are pinned before the consumer exists.

### 2.5 Remove an enrollment — `DELETE .../enrollments/{id}`

1. Refuse unless `claimed_at` is null **and** no history references it
   [BR6.1].
2. On refusal, return a `ConflictError` naming the inactive path.

> **The history check is incomplete at B5 and that is recorded rather
> than hidden.** Attendance, marks and fee rows belong to U5, U6 and
> U7, whose tables do not exist yet. The check covers what exists, and
> each later Unit carries an obligation to extend it — written into
> that Unit's rules, not left as a comment here.

### 2.6 Student batch list — `GET /v1/me/batches`

1. Resolve the student lens; reachable batches are those with an
   `Enrollment` where this account is the **student**.
2. Apply the viewer's `HiddenBatchPreference` — hiding affects
   **this viewer only** [BR2.1 of entities, AC2.6.3].
3. Inactive batches are returned but flagged read-only and collapsed
   [AC2.6.2]; history stays reachable.

### 2.7 Guardian child selection — `GET /v1/guardian/children`

1. Reachable enrollments are those whose `guardian_account_id` is
   **this authenticated account** [BR5.3].
2. **Collapse to DISTINCT CHILDREN** before counting [BR5.2]. The
   acceptance criteria say "children"; the query returns enrollments;
   and `AC2.2.3` permits the same student in two batches of one
   teacher. Counting enrollments would show that child twice and skip
   the straight-through case entirely.
3. Zero, one and many are three distinct outcomes [BR5.2]:
   - zero → an empty state saying a teacher must record this number;
   - one → straight through, **still naming the teacher and the masked
     number**;
   - many → the selection list, **one entry per child**, each showing
     display name and teacher.

> **A child is not an enrollment** [BR5.4]. One selection-list entry may
> cover several enrollments — the same child in two of one teacher's
> batches — while each child-scoped route still names exactly one
> `enrollment_id`. Treating "the selected child" as a single enrollment
> silently drops the rest.

### 2.8 Child-scoped routes — `/v1/guardian/children/{enrollment_id}/...`

**The child is a path parameter. This settles OQ-7** [BR5.1].

1. The server validates the enrollment is reachable from the
   authenticated account on **every** request.
2. Unreachable → **404**, never 403.

> **Why not the lens hint.** The hint is non-authoritative by
> construction [D-2] — the server is required to distrust it. Putting a
> privacy-relevant selection in a field whose contract is "this decides
> nothing" means either trusting what must not be trusted, or
> re-validating anyway, in which case the path parameter is the same
> work made visible to the route-enumeration gate.
>
> It also makes back-stack correctness enforceable: a URL naming the
> child lets the server refuse a stale entry, where a header silently
> serves the newly selected child under the old screen [AC9.4.2].
>
> **The cost is real**: every guardian route carries a segment and the
> client threads the id.

---

## 3. The Android surface

- **Rosters cached in Room**, establishing the pattern [BR7.1]: entities
  mirror the DTO one-to-one, carry only `fetched_at`, derive nothing.
- **Staleness is shown, not hidden.** A cached roster displays when it
  was fetched. V1 accepts no write without connectivity, so a stale read
  is the only offline state and the user should be able to see it.
- **The child switcher** changes the path parameter; it decides nothing.
- **Both language bundles** for every new string [TC-15].

---

## 4. Boundary cases

| Case | Behaviour | Why |
|---|---|---|
| Teacher's first batch | An `Owner` row is created | [BR1.1] |
| Number already has an account | Enrollment attaches to it | [AC2.2.4] |
| Same student, two batches | Two enrollments, independent names and fees | [BR2.2] |
| `fee_amount` set to 0 | Charges zero — a waiver, not an inherit | [BR3.1] |
| `fee_amount` null | Inherits the batch default | [BR3.1] |
| `fee_due_day` 31 in February | Clamps at generation — U7's arithmetic | [AC2.1.2] |
| Inactive from the 10th | That month charges **in full** | [AC2.4.5] |
| Inactive, with unpaid dues | Dues stand unchanged | [BR4.2] |
| Remove a claimed enrollment | Refused; inactive offered instead | [BR6.1] |
| Remove a dormant, history-free enrollment | Deleted | [AC2.5.1] |
| Guardian with zero children | Empty state explaining why | [BR5.2] |
| Guardian with one child | Straight through, attribution still shown | [AC2.8.5] |
| Same child, two teachers, two numbers | Only the signed-in number's batches | [BR5.3] |
| Student hides an inactive batch | Hidden for them only | [AC2.6.3] |

---

## 5. What this Unit does not build

- **No sessions or attendance** — U5's.
- **No exams or marks** — U6's.
- **No fee cycles or ledger** — U7's. This Unit records the **anchor**
  (`fee_amount`, `default_fee`, `fee_due_day`, `inactive_from`)
  that U7 charges against; it computes nothing.
- **No deletion of accounts** — U11's.
- **No admin surface** — there is none at this budget.

---

## 6. Obligations this Unit hands forward

| Obligation | Owing Unit | How it is enforced |
|---|---|---|
| Extend BR6.1's history check to attendance | U5 | **Mechanically** — see below |
| Extend it to marks | U6 | Mechanically |
| Extend it to fee cycles | U7 | Mechanically |
| Apply `inactive_from` in generation | U7 | U4's four named tests pin the semantics against a stub |
| **Delete `app/db/seed_skeleton.py`** | U4 (here) | U4 can create a batch for real, so the B3 throwaway is obsolete |

> **The first three are enforced, not remembered** [BR6.1]. A test
> queries the migrated schema for every table **referencing an
> enrollment** — the UNION of "has a foreign key to `enrollment`" and
> "has a column named `enrollment_id`" — and asserts each appears in
> the `HISTORY_TABLES` registry.
>
> Verified against a real container, including the evasions: a table
> with the column but **no** foreign key (an author omitting the
> constraint on a hot insert path) is missed by the FK predicate, and
> a table whose column is called `subject_enrollment` is missed by the
> name predicate. Each alone has a plausible gap; the union caught all
> three shapes. Adding an `attendance` table makes **U4's** test fail
> on the commit that adds it, naming the table.
>
> That inversion is the point. An obligation written in prose across
> three future Bolts is the kind that gets forgotten; this one fires
> without anyone reading this file.
>
> It passes **vacuously** at B5 — the same shape as B3's money-column
> assertion — and that is recorded so the first real failure reads as
> the gate working rather than breaking.

> The last one is this Bolt's own: B3's seed script existed only
> because U3 could not create an `Owner` or `Enrollment` row. U4 can,
> so the script and its tests go.

---

## Assumptions & Open Questions

**None open.** [assumption] OQ-7 is settled here as a path parameter
[BR5.1], which is what the contract stage asked this Unit to decide.

[assumption] BR6.1's history check is partial at B5 by necessity, and
the gap is carried as a named obligation on three later Units rather
than as a comment — a comment in this file is not somewhere a later
Bolt's author would look.
