# Security Design — D4 `teaching-and-recording`

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: D4 `teaching-and-recording`
**Record**: 261022-remaining-slices

> **This is the unit where the product's children's data arrives.** Until now
> the privacy boundary has protected a self-chosen name, a photo reference, an
> address and a fee balance. D4 stores **attendance and marks**: a record of
> where a named child was on a given afternoon and how they performed. The
> Families declaration, the Data Safety form and RC-1 through RC-3 were
> written about exactly this data, and D4 is the first unit to hold it.
>
> Four designs carry the unit, and each is a mechanism rather than a rule:
> the **probe matrix** (§ 2), which copies the built four-route shape rather
> than inventing one; the **anonymised marksheet** (§ 4), which is a
> disclosure mechanism and not a view; the **refusal ordering** (§ 5), where
> a descriptive conflict code must be unreachable before authorization; and
> the **two obligations that attach to a new table** (§ 6), only one of which
> has a test.

## Sources

- [upstream] `nfr-requirements/security-requirements.md` — NFR14.48–NFR14.64,
  NFR10.18–NFR10.20
- [upstream] `nfr-requirements/reliability-requirements.md` — NFR19.33,
  NFR19.34, NFR19.35, NFR19.36, NFR19.38, NFR19.46, NFR19.47
- [upstream] `nfr-requirements/scalability-requirements.md` — NFR6.44,
  NFR6.50, whose concurrency guarantees the replay design depends on
- [upstream] `nfr-requirements/observability-requirements.md` — NFR24.13–
  NFR24.17, the prohibitions this document treats as security properties
- [upstream] `nfr-requirements/performance-requirements.md` — NFR20.26, the
  marksheet's single pass, whose shape § 4 constrains
- [upstream] `nfr-requirements/tech-stack-decisions.md` — NFR5.11, NFR5.12,
  NFR17.5
- [upstream] `functional-design/rules.md` — BR1.5, BR3.8, BR3.10, BR5.1–BR5.5,
  BR6.1–BR6.5, BR7.2
- [upstream] `functional-design/entities.md` — the six new tables and the three
  read-only existing ones
- [upstream] `functional-design/functional-spec.md` §§ 3.3, 4.2, 4.3, 5
- [prior] `261016-.../inception/contract-design/contract-summary.md` —
  **§ B.7**, § B.8
- [prior] `261016-.../inception/domain-design/decisions.md` — ADR-001, ADR-006
- [code] read 2026-10-24: `app/db/roles.py`, `app/governance/dispositions.py`,
  `app/contract/privacy.py`, `app/contract/routes.py`, `app/errors/_classes.py`,
  `app/errors/codes.py`, `app/authz/lenses.py`, `app/authz/resolve.py`,
  `tests/privacy/test_rls_meta.py`, `tests/privacy/test_profile_probes.py`,
  `tests/privacy/conftest.py`, `tests/db/test_governance.py`,
  `tests/contract/test_error_contract.py`,
  `migrations/versions/0001_initial_identity_schema.py`,
  `migrations/versions/0002_batches_and_enrollment.py`,
  `migrations/versions/0005_fee_system.py`

---

## 1. The database roles, and why D4 makes no decision here

**This section exists because it looked like a decision and is not.** The
question is whether D4's six tables are reachable by a test role that can
genuinely be held to the privacy boundary.

### 1.1 Ownership is inherited and already correct

PostgreSQL documents that **both a superuser and a table's owner bypass
row-level security entirely**, so a privacy suite connected as either passes
identically whether a policy is correct, broken or absent. The owner case is
the subtle one, because unlike superuser status it is acquired by accident:
the migration runs as the owner, and an application sharing those credentials
inherits the bypass.

**The built design already separates the two roles, and D4 inherits that
rather than deciding it.** Verified by reading
`migrations/versions/0001_initial_identity_schema.py:229-247`:

- the role is created `CREATE ROLE shikkhok_app NOINHERIT LOGIN` (line 231);
- it is **granted** `USAGE ON SCHEMA public` and DML on tables (lines 238-246);
- it is **never made owner of anything**.

`NOINHERIT` is what makes this load-bearing rather than incidental: the role
holds exactly what is granted to it and inherits no blanket privilege from
another role. `APP_ROLE` is defined once in `app/db/roles.py` and shared by
the migration, the request middleware and the meta-test, so no caller imports
a revision module by filename.

The built meta-test asserts all three conditions before any probe runs
[`tests/privacy/test_rls_meta.py`]: `current_user` is not a superuser, the
suite connects as `APP_ROLE`, and **the suite does not own the table** —
checked against `pg_tables.tableowner`. A fourth test asserts RLS is both
`ENABLE`d and `FORCE`d on `profile`, because without `FORCE` the policy does
not apply to the owner and would look present in `pg_policies` while doing
nothing.

**Design statement [NFR14.41, project NEVER-rule]: D4's six tables are created
by the same migration path, as the same owning role, and are read in tests by
the same granted non-owner `APP_ROLE`. D4 introduces no new role, changes no
ownership, and makes no decision here.** Verifier: the built meta-test, which
is a package-level gate rather than a sibling test — `tests/privacy/conftest.py`
reorders it first by node id *and* re-checks the three conditions in an autouse
fixture that fails the package, because a probe suite running against a missing
policy reports a **pass**, which is the worst available outcome.

### 1.2 The grant is per-table, and it is the obligation that can be forgotten

**There is no `ALTER DEFAULT PRIVILEGES` anywhere in the migration history.**
I searched all of `migrations/versions/` and all of `app/`, and found none.
`0001`'s `GRANT ... ON ALL TABLES IN SCHEMA public` covered only the tables
that existed at that moment, so every later migration grants its own:

| Migration | How it grants |
|---|---|
| `0001` | `GRANT ... ON ALL TABLES IN SCHEMA public` — covers only what existed then |
| `0002` | a per-table loop over its four new tables (`_grant_new_tables`) |
| `0003` | an explicit grant for `staging_sms_outbox` |
| `0005` | a per-table loop over `NEW_TABLES`, D3's five |

**Design statement [NFR19.46, NFR19.47]: D4's migration grants its six tables
explicitly to `APP_ROLE`, looping over a declared `NEW_TABLES` list rather
than writing six statements**, which is `0005`'s shape and is chosen because a
table added to the list cannot then be granted by accident, and a table created
without being added to it fails loudly.

**Why a missing grant is worse than a permission error.** `0002`'s own
docstring records the discovery, and it is the reason this section is in the
security document rather than the reliability one: an ungranted table is
**invisible to the restricted role in `information_schema`**, so the governance
gates — which read as that role — silently stop covering it. The money-column
assertion reported `enrollment.fee_amount` and skipped `batch.default_fee`
entirely until the grant existed. *A control that quietly narrows is worse than
one that fails.*

### 1.3 The reachability verifier already exists — this is not new work

The natural proposal at this point is a test asserting the restricted role can
`SELECT` from every live table, to catch a missing grant at `make check` rather
than in staging.

**That test is already built.** Verified by reading `tests/db/test_governance.py`:

| Built test | What it asserts |
|---|---|
| `test_the_restricted_role_can_read_every_live_table` | every live table answers `SELECT 1 ... LIMIT 1` as `APP_ROLE` |
| `test_every_owned_table_is_visible_to_the_restricted_role` | the owner's table list minus the restricted role's is empty |

Both iterate `_live_tables()`, which applies
`INFRASTRUCTURE_TABLES = frozenset({"alembic_version"})` — the same exclusion
set, reached through the same helper, so there is **no second copy of the list
to drift**. The second test is the stronger half: it compares what the owner
sees against what the restricted role sees, catching a table that has
disappeared from every gate without saying so.

**Design statement: D4 specifies no new reachability test, because specifying
one would be duplicating a built control.** D4's obligation is to add its six
tables to the granted list so the existing assertions continue to pass. This
entry is recorded rather than omitted, because an absent section reads to the
next person as an unconsidered gap.

> **Honest limit on this claim.** I verified these tests by **reading** the
> file. I could not **execute** them: Docker is unavailable in this session and
> `python3 -m pytest tests/db/test_governance.py -q` reported `sss.sssss`, the
> module-level skip `tests/conftest.py` applies when no daemon is reachable.
> That skip is itself the gap `team.md` assigns a CI precondition assertion to.
> No claim in this document rests on a measured green run.

---

## 2. The probe matrix: four routes at one boundary

### 2.1 The shape is copied, not invented [NFR14.48]

The built suite `tests/privacy/test_profile_probes.py` attacks **one boundary
by four separate routes**, because an implementation can block one and leave
another open:

| Route | Why it is distinct |
|---|---|
| A direct query | The obvious one |
| A **join** | The shape a real teacher-facing roster query actually has |
| An **ORM traversal** | Reaches rows a hand-written query would not |
| An unscoped `SELECT *` | The query someone runs while debugging — exactly when a leak gets copied somewhere it should not go |

It also asserts **two positive cases** — an owner reads their own profile, and
a teacher successfully reads the teacher-typed name — so the suite proves the
boundary is in the *right place* rather than merely that something is blocked.
Without them the whole suite passes against a policy that denies
unconditionally, which is not the requirement. A fifth test asserts that a
session with **no account context sees nothing**, so an unset context fails
closed and a missing middleware call does not open the table.

**Design statement: D4's probes follow this shape for marks and attendance.**

### 2.2 The six readers, each with its routes [NFR14.48, NFR14.49]

BR5.2 names six readers that must filter on the enrollment decision columns.
Per the project's 2026-10-22 correction — *adding a column is not adding a
behaviour* — each is designed individually rather than covered by one general
sentence.

| Reader | Lens | Predicate | Adversarial probe | Positive probe |
|---|---|---|---|---|
| Session roster | Teacher | BR1.5's four clauses | A declined seat is absent | An accepted seat is present |
| Session detail | Teacher | batch owner = `owner_id` | Teacher A cannot read B's session | The owner reads it |
| Student attendance history | Student | `student_decision = accepted` | A pending seat reads nothing | An accepted student reads their own |
| Guardian attendance history | Guardian | `guardian_decision = accepted` | A declined guardian reads nothing | An accepted guardian reads their child's |
| Batch marksheet | Student, Guardian | the respective column | Each lens refused on its own column | Each lens reads its own marksheet |
| Guardian progress | Guardian | `guardian_decision = accepted` | A non-child enrollment id is refused | The child's progress returns |

**Each adversarial row is probed by at least the direct and the join route**,
because the join is the shape the real query has. The marks and attendance
reads additionally carry the ORM traversal, since the ViewModel-facing reads
are ORM-shaped.

**The positive column is not decoration.** It is what distinguishes a correct
boundary from a blanket denial, and it is the half the built suite was careful
to include.

### 2.3 The IDOR equality probe [NFR14.49]

A guardian requesting a **non-child** enrollment id receives `NOT_AVAILABLE`
**byte-identical** to the response for an invented id — same status, same code,
same body [BR7.2].

**Design statement: this is verified by an EQUALITY assertion over the two
responses, not by two independent assertions that each is a refusal.** Two
separate assertions both pass while the bodies differ, and the difference is
the leak.

**The timing half is designed as out of scope and said so plainly.** NFR14.49
also asks for no timing difference. A timing-equality assertion on a single
shared host is flaky in both directions and would be the kind of test that gets
muted. **The design relies on the two paths being the same code path — one
shared refusal raised before any resource-specific work — which makes a timing
difference structurally unlikely rather than asserted. Nothing automated
verifies the timing property, and that sentence is the honest half.**

### 2.4 Three tables, three attack directions

Collected so no reader is left to infer which probe covers which table:

| Table | Attacker | Target |
|---|---|---|
| `attendance` | Teacher A | Teacher B's session roster |
| `attendance` | A guardian | A non-child's attendance |
| `mark` | A student | Another student's mark in the same exam |
| `mark` | A guardian | A non-child's marks |
| `exam`, `announcement` | Teacher A | Teacher B's batch |

**The exam's own integrity constraint is an authorization boundary** [BR4.1]:
an exam belongs to one batch **and one of that batch's subjects**, so a
`batch_subject_id` from another teacher's batch would attach an exam **across
the ownership boundary** [BR5.1]. `entities.md` states this as an entity
constraint; it is repeated here because it is enforced in the write path
rather than by a foreign key, which means it is a check somebody can omit.
**Verifier: a probe creating an exam with a subject id from a batch the
teacher does not own, asserting refusal.**

---

## 3. Row-level security: the decision and its trigger

### 3.1 Why no RLS policy on D4's six tables [NFR14.52, NFR14.54]

**Design statement: D4's six tables are protected by lens-scoped queries plus
the adversarial probes of § 2, and no RLS policy is added for them.** This
follows D3's NFR14.36 decision, re-checked against D4's schema rather than
inherited on faith.

The reason is mechanical. **RLS exists on `profile` alone because `profile`
has a column naming its reader** — `account_id` — which is what a policy needs
to compare against a session variable (`app.account_id`, defined once in
`app/db/roles.py`). **None of D4's six tables has such a column.** `attendance`
is keyed by `(session_id, enrollment_id)`; reaching the reader from a row
requires joining enrollment to account and branching on which of three lenses
is asking. That branch is the lens resolver's job and not a policy predicate's.

**`attendance_submission.submitted_by_account_id` is not a counter-example**
[NFR14.54]. It names the **writer**, not a permitted reader, and no read is
ever scoped by it. It is stated explicitly because it is the one column in D4
that looks like one.

**Verifier: the decision is recorded here; what is verified is the probe suite
of § 2, which is what actually enforces the boundary.** Recording this as
"verified by a recorded decision" rather than claiming a test would be the
empty-promise shape; the probes are the real control and the design says so.

### 3.2 The trigger that re-opens it [NFR14.53]

**This decision is revisited if any D4 table gains a column identifying a
reader directly.** Stated so the decision has a trigger rather than being
permanent by default — which is the failure mode `team.md` records for the
`app.authz` strict island: a deferral with a stated trigger and nothing
watching for the trigger.

**The watch is the probe suite plus this sentence**, and there is no automated
trigger. That is a genuine limit and it is written rather than implied.

### 3.3 One built assertion worth copying

`test_row_level_security_is_not_enabled_on_enrollment` exists because enabling
RLS there would be a plausible "more security" change that **silently breaks
the teacher's legitimate roster read**. The equivalent for D4 is the positive
probe column of § 2.2: the teacher's own roster read must keep working, and a
test asserts it.

---

## 4. The anonymised marksheet is a disclosure mechanism

Treating it as a feature rather than a disclosure is how it ships wrong.

### 4.1 What the response may contain [NFR14.55]

**Design statement: a marksheet carries the viewer's own mark named, plus
rank, average, highest and a banded distribution, and carries no row
attributable to another student.**

The mechanism is **schema shape, not filtering**: the response type has **no
per-student collection at all**, so there is no array a future change can
populate. A filtered list is one forgotten predicate from a leak; an absent
field is not.

**Verifier: a schema-level assertion that the marksheet response carries no
per-student collection, plus a probe asserting a second student's mark is not
derivable from the response body.**

### 4.2 The band-merge rule [NFR14.56, BR6.3]

**No published band holds fewer than three results; a band under three merges
into its neighbour, and the merge repeats until every published band holds at
least three.** BR6.3 states the single merge; **the repetition is this
design's addition**, and it is the part an implementation drops — one merge
pass can produce a neighbour that is itself still under three.

Worked through, at the band width of 20 the functional design chose, over a
marked set of 8 — computed here rather than quoted:

```
raw bands:  [0-20]:1  [21-40]:1  [41-60]:4  [61-80]:1  [81-100]:1
pass 1:     merge [0-20] into [21-40]      -> [0-40]:2  [41-60]:4  [61-80]:1  [81-100]:1
            [0-40] is STILL under three    -> this is why the rule repeats
pass 2:     merge [0-40] into [41-60]      -> [0-60]:6  [61-80]:1  [81-100]:1
pass 3:     merge [61-80] into [81-100]    -> [0-60]:6  [61-100]:2
pass 4:     [61-100] under three           -> [0-100]:8   one band, 8 results
```

The terminal case is one band holding every result, which discloses nothing
beyond the count — and the count is already disclosed by NFR14.57's threshold.

**A band of one IS a named mark.** In a batch of 8 to 20 students who sit
together and compare marks, the name is supplied by anyone in the room within
a day. That is why the threshold is a security requirement and not a
presentation nicety.

**Verifier: the computed case above, plus a property-style test over generated
mark lists asserting `min(published band counts) >= 3` or zero bands
published.** The property form is what catches the single-pass bug; the worked
case above is the regression that names it.

### 4.3 The two independent suppression conditions [NFR14.57]

**No comparison of any kind is published below five marked results, and none
is published while any roster seat is still `not_entered`** [BR6.4]. The two
conditions are independent and **both** must hold.

**Verifier: a test per condition, each holding the other condition satisfied.**
A single test varying both at once passes while only one check is implemented —
which is the defect shape, not a stylistic preference.

### 4.4 One batch, never across batches [NFR14.58]

Every aggregate is scoped to **one batch**. A cross-batch aggregate would
disclose the existence and shape of a batch the viewer is not enrolled in.

**Verifier: a probe seeding two batches with disjoint marks and asserting the
average matches the single-batch computation.** The disjoint seeding is what
makes a wrong answer visible; equal marks in both batches would pass either
way.

### 4.5 The toggle is an authorization control [NFR14.59, NFR14.60]

When `Batch.marksheet_visible` is false, **no marksheet is returned at all** to
any student or guardian lens — not an empty one, not one with the comparison
fields nulled [BR5.4].

**An empty marksheet still discloses that exams exist and how many.** That is
the precise failure mode, and it is the one an implementation reaches by habit,
because returning an empty collection is the kinder-looking code.

**Verifier: a probe asserting the response is a refusal or an absence, and
specifically that it carries no exam count, no exam list and no empty marks
array.** Asserting the three absences individually is the point; asserting only
"not a 200" passes against a 200 carrying an empty list.

The toggle is written through **exactly one route**, under a teacher lens
scoped to the batch's owner. The teacher's own view is unaffected by its value.
**Verifier: the route-enumeration test for the lens, plus a probe asserting a
non-owner teacher cannot write it.**

**No schema change** — the column is already non-null in
`app/db/models.py:589`, and D4 ships no migration for it [entities.md].

---

## 5. Replay, conflict, and the refusal ordering

### 5.1 The three mechanisms, kept distinct [NFR14.61]

D4 carries all three, each correct for its own case. A design that blurs them
invites the wrong one being reached for:

| Mechanism | Protects against | Where | Enforced by |
|---|---|---|---|
| `client_mutation_id` | **replay** — the same decision arriving twice | attendance, topic log (+ D3's two money writes) | `UNIQUE (submitted_by_account_id, client_mutation_id)` on `AttendanceSubmission` |
| `attendance_version` / `topic_version` | **conflict** — a stale decision arriving late | the two queued paths only | the conditional `UPDATE`, zero rows meaning someone else won |
| insert-conflict | **duplicate generation** | sessions (D3: fee cycles) | `ON CONFLICT DO NOTHING` on a natural key |

**`client_mutation_id` is required on exactly the writes § B.7 names**, two of
which are D4's: `POST /v1/sessions/{id}/attendance` and
`PUT /v1/sessions/{id}/topic`. It is **not** added to any other D4 write —
§ B.7 says "stating the four explicitly is what makes the rule reviewable", so
generalising it would contradict a deliberate decision rather than extend it.

**Verifier: a schema-level assertion over the generated OpenAPI document that
exactly these two D4 request bodies carry the field** — iterating the document
rather than remembering per endpoint, which is the shape `app/contract/privacy.py`
already establishes for the field-level invariant.

### 5.2 A cross-account replay is an authorization failure [NFR14.62]

**Design statement: a replay of another account's `client_mutation_id` is an
`AuthorizationError`, never a silent success.**

The uniqueness is scoped **per account per endpoint** [§ B.7], so account B
presenting account A's id is **not a duplicate at all** and must not be treated
as one. The constraint is on the pair `(submitted_by_account_id,
client_mutation_id)`, so B's submission does not collide with A's row — the
lookup must be scoped by the authenticated account, and a lookup on
`client_mutation_id` alone would find A's row and return it.

**This is the requirement that ships as a silent success if nobody writes it
down.** The natural implementation looks up the id, finds a row, and returns it.

**Verifier: a probe submitting account A's id under account B's token,
asserting a refusal and specifically asserting it is not a `200` carrying A's
stored result.** The negative half is load-bearing: asserting only "not 200"
passes against a 500.

### 5.3 A replay is observably a replay [NFR14.63, NFR19.34]

A replayed `(submitted_by_account_id, client_mutation_id)` returns the original
stored result with `200` — not `201`, not an error — writes no second
`attendance` row, does not increment the version, and leaves the original's
**`created_at` unchanged**.

**Design statement: the `created_at` assertion is the load-bearing one.** A
row-count assertion passes against an implementation that **overwrites the
original in place** — same row count, same version, wrong behaviour, and the
original decision's timestamp destroyed.

**Verifier: submit the same body twice; assert one submission row, one
increment, and that `created_at` did not move.**

### 5.4 Authorization precedes the version check [NFR14.64, BR3.10]

**Design statement: a version conflict is refused AFTER authorization, never
before.** If the caller's lens does not reach the session, the request is
refused with the shared `NOT_AVAILABLE` before any version is compared.

**The ordering is the security property, and the reason is concrete.**
`ATTENDANCE_VERSION_CONFLICT` carries `current_version` and `current_state` in
`error.details` — and `current_state` **is the roster**. Emitting it before the
authorization check would hand a stranger the class's attendance **in an error
body**.

The design is a sequence, not a convention:

```
resolve lens -> if it does not reach the session: raise AuthorizationError(NOT_AVAILABLE)
             -> only then: compare base_attendance_version
             -> on mismatch: raise ConflictError(ATTENDANCE_VERSION_CONFLICT, details=...)
```

**Verifier: a probe asserting that a caller with no lens on the session
receives `NOT_AVAILABLE` and never `ATTENDANCE_VERSION_CONFLICT`, run for both
a matching and a non-matching version.** Running both is the point: a probe
using only a non-matching version cannot distinguish correct ordering from an
implementation that happens to check authorization first by accident of
control flow.

### 5.5 Why the descriptive code does not trip the built oracle test

Checked against the code rather than asserted. `tests/contract/test_error_contract.py`
carries `test_exactly_one_resource_refusal_code_is_registered`, which asserts
`AUTH_403_CODES - ALLOWED_NON_RESOURCE == {NOT_AVAILABLE}`.

**`ATTENDANCE_VERSION_CONFLICT` is a `ConflictError` carrying 409, not an
`AuthorizationError` carrying 403**, so it never enters `AUTH_403_CODES` and
the test is untouched by it. That is precisely why the ordering requirement of
§ 5.4 is the real control here: **the built registry test cannot catch an
individually-disclosing 409**, and nothing else will either. The code is
permitted because it is unreachable without authorization, and § 5.4's probe is
what makes that true rather than intended.

**No new exception class** [NFR19.35]. `ConflictError`'s built docstring
already states this semantic exactly: *"Valid request; current state forbids
it. Refetch and decide. Retrying as-is is wrong."* `retryable: false` follows
from the class and is read in one place — a raise site cannot set it
[`app/errors/_classes.py`].

### 5.6 Two state-based refusals [NFR19.38]

A write to a `cancelled` session [BR1.6] and any write to an `inactive` batch
[BR5.5] are refused as `ConflictError`, not `ValidationError`: the request is
well-formed and the **current state** is what forbids it.

**Verifier: a test per case asserting the class and that existing rows are
untouched.** The second half matters — a refusal that has already written is a
refusal in name only.

---

## 6. Governance: the two obligations that attach to a new table

### 6.1 One entry per table, not two [NFR10.18]

Each of D4's six new tables carries a **`TableGovernance` entry** in
`app/governance/dispositions.py`, written in the **same change** as the
migration that creates it [BR6.1].

**One entry, not two.** Verified by reading `dispositions.py:279-281`:
`RETENTION` is **derived** from `DISPOSITIONS` by a dict comprehension, so the
two cannot fall out of step and there is no second map to maintain. The entry
carries `disposition`, `retention` and `basis`, and **the `basis` is the
sentence the generated privacy policy is written from** — prose a parent could
read, not a code comment. `test_every_disposition_states_a_basis` enforces a
20-character floor.

Counted from the file: **19 entries today, six added, 25 after D4.**

### 6.2 The dispositions are transcribed, not invented [NFR10.19]

`attendance`, `exam` and `mark` take `RETAIN_WITH_BASIS`, which is the case
that enum value was created for — the built `Disposition` docstring names
attendance and marks explicitly: rows written by the **teacher**, which are the
teacher's business record and simultaneously the child's personal data.

**`attendance_submission` is the one table with no upstream row**, because this
design added it. It takes `attendance`'s disposition and retention, since it
holds nothing `attendance` does not and is meaningless without it.

**Verifier: `tests/db/test_governance.py`, which asserts in BOTH directions** —
and the second direction is the one D4 specifically needs. Six tables arrive in
one migration, and a typo in a table name produces a **stale entry naming a
table that does not exist** rather than a missing entry, which a one-directional
check misses entirely. `test_no_disposition_names_a_table_that_does_not_exist`
is that direction.

### 6.3 The migration's definition of done

**Design statement: a new table in this project carries TWO obligations, and
only one of them has a dedicated test.**

| Obligation | Verifier | Fails where |
|---|---|---|
| A `TableGovernance` entry | `tests/db/test_governance.py`, both directions | `make check` |
| An explicit `GRANT` to `APP_ROLE` | `test_the_restricted_role_can_read_every_live_table` (§ 1.3) | `make check` |

Both are covered today — the grant by the built reachability pair rather than
by its own named test. **Stating them together is the design contribution**,
because the failure mode of the second is silent narrowing (§ 1.2) rather than
a loud error, and a developer who knows only the first will write a migration
that passes governance and cannot be read.

### 6.4 Encryption at rest [NFR10.20]

D4 adds no hosting or database tier and therefore does not disturb the
encryption-at-rest requirement for children's data [RC-8, D-29]. It is
restated because **D4 is the unit that first makes "children's data" literal**.

**Verifier: no infrastructure change in this unit; the existing tier's storage
encryption stands.**

---

## 7. The device: what the queue holds and what protects it

### 7.1 No identifier, checked against the built gates [NFR5.11]

The queue file holds **enrollment ids, booleans, a version number and two
UUIDs**. No device or advertising identifier, no name, no phone number.

**Verifier: the existing DEX scan and merged-manifest permission allowlist,
which are unaffected by this unit, plus review of the serialized shape.** The
built gates are the strongest work in the repository and D4 adds no dependency
that would challenge them.

### 7.2 The queue is not encrypted at rest, as a recorded decision [NFR5.12]

**Design statement: the queue file is not encrypted, and this is a decision
rather than an omission.**

The reasoning, stated so it can be disagreed with: it holds a roster of
enrollment ids and presence booleans for one batch — **no name, no phone
number, no profile field, no token**. `EncryptedSharedPreferences` is used for
the refresh token because that is a 30-day credential readable via adb on a
rooted phone; a queued roster is neither a credential nor readable as
identifying data without the server's enrollment mapping.

**Verifier: none — this is a recorded acceptance.**

**Flagged for the human.** If the preference is to encrypt it anyway, the cost
is small and I verified why: `androidx.security:security-crypto` is **already a
declared dependency** (`gradle/libs.versions.toml:46`) and
`EncryptedTokenStore.create()` in
`android/src/main/kotlin/com/shikkhokplus/app/core/network/TokenStore.kt`
already demonstrates the `MasterKey` + `EncryptedSharedPreferences` pattern.
**One caveat if that route is taken**: `EncryptedSharedPreferences` is a
key-value store, so a roster list would have to be encoded into a string value
— which lands back on the serialized-shape design with an encryption wrapper,
not on a different storage model. The queue's atomic-rename property
[NFR5.10] would need re-deriving, because `apply()`/`commit()` is the
durability mechanism there rather than a rename.

---

## 8. Logging prohibitions, as security properties [NFR24.13–NFR24.17]

Designed in full in `observability-design.md` § 1, where the whole logging rule
set lives. Named here because they are **security properties first**:

- **a child's name never reaches a log line**;
- **a mark never reaches a log line**;
- **an attendance roster never reaches a log line** — and in particular the
  `ATTENDANCE_VERSION_CONFLICT` path must not log `current_state`, which *is*
  the roster, when it logs the conflict.

The last is the specific hazard in this unit: the conflict is interesting, so
it will be logged; the error body already carries the roster; and the obvious
implementation logs the error body.

**Nothing automated checks the first two. That sentence is the requirement's
honest half** [NFR24.13, NFR24.14], and the conflict-log shape is the one of
the three that does get a test [NFR24.15].

---

## 9. What D4 does not change

Stated so a reader does not look for a decision made elsewhere:

- **Authentication, tokens and OTP abuse controls** [NFR12, NFR13] — untouched.
  D4 adds no credential, no session and no token.
- **Device identifiers** [NFR11] — untouched. D4 adds no SDK.
- **The route-enumeration gate** [NFR14.50] — every D4 route resolves a lens,
  enforced by the built test in `app/contract/routes.py` that walks
  `route.dependant` recursively and matches on the dependency's **return
  annotation being a `Lens` subtype**. **D4 adds no entry to `PUBLIC_ROUTES`**;
  every route in this unit is authenticated. Verified by reading
  `app/contract/routes.py`: the frozenset holds **eight** entries and
  `tests/contract/test_route_lenses.py:76,104` asserts that count in two
  places — so **D4 adding one would fail `make check` rather than passing
  silently**. (The drift `team.md` records here, a comment reading "exactly
  five" over a six-entry set, has been **closed**: the comment now states
  eight and the assertion makes the number a claim that is checked.)
- **The field-level privacy gate** [NFR14.51] — no teacher-facing schema in
  this unit carries an owner-private profile field or a global account
  identifier; a roster exposes an **enrollment id** and never
  `student_account_id`. Enforced by the built `app/contract/privacy.py`, which
  iterates the generated OpenAPI document and reads the lens from the route.
  **No new mechanism.**
- **The restricted test role** [NFR14.41] — binds exactly as before, although
  D4 adds no RLS policy, because the guard protects the *suite* (§ 1.1).
- **The teacher/platform-administrator boundary** [TC-14, D-6] — D4 adds no
  administrator surface.
- **`app.authz.*` strictness** [NFR17.5] — D4's six lens-scoped readers land
  under a **configured** strict island. Verified at `pyproject.toml:222-225`;
  `team.md`'s note that this island was never configured is **stale**, and D1
  additionally added a fourth on `app.accounts.*`.

### A roster is literally a list of people

Worth stating plainly because it is the design pressure this unit is under.
A roster is the most natural place in the whole product to render a student's
self-authored name or photo beside the checkbox a teacher is tapping. **The
gate catches the schema; nothing catches a designer deciding the roster should
show photos.** That decision was already made against — the roster shows what
the teacher recorded [ADR-001] — and § 9's field-level gate is the mechanical
half of it.

---

## 10. Verification obligations, collected

| Obligation | Verifier | Automated |
|---|---|---|
| Six readers filter on decisions [NFR14.48] | One adversarial probe each, direct + join | yes |
| Positive reads still work [NFR14.48] | The positive probe column, § 2.2 | yes |
| Guardian IDOR is byte-identical [NFR14.49] | Equality over two responses | yes |
| …and shows no timing difference [NFR14.49] | Shared code path, § 2.3 | **no — structural, not asserted** |
| Every route names a lens [NFR14.50] | Built route-enumeration test | yes |
| No profile field to a teacher [NFR14.51] | Built `app/contract/privacy.py` | yes |
| Marksheet carries no per-student rows [NFR14.55] | Schema assertion + derivation probe | yes |
| No band under three [NFR14.56] | Worked case + property test | yes |
| No comparison below five, or while incomplete [NFR14.57] | A test per condition | yes |
| One batch only [NFR14.58] | Disjoint two-batch probe | yes |
| Toggle off returns nothing at all [NFR14.59] | Probe on three absences | yes |
| Toggle written through one owner-scoped route [NFR14.60] | Route test + non-owner probe | yes |
| `client_mutation_id` on exactly two D4 writes [NFR14.61] | OpenAPI document assertion | yes |
| Cross-account replay refused [NFR14.62] | Probe under a second token | yes |
| Replay leaves `created_at` unmoved [NFR14.63] | Equality on the timestamp | yes |
| Authorization precedes the version check [NFR14.64] | Probe, both version cases | yes |
| Six governance entries [NFR10.18] | Built `tests/db/test_governance.py`, both directions | yes |
| Six tables granted to `APP_ROLE` [§ 1.2] | Built reachability pair, § 1.3 | yes |
| Suite is non-superuser, non-owner [NFR14.41] | Built `tests/privacy/test_rls_meta.py` | yes |
| RLS decision for D4's tables [NFR14.52] | Recorded; the probes enforce it | **no — a recorded decision** |
| The RLS re-open trigger [NFR14.53] | This document plus review | **no — nothing watches the trigger** |
| Queue unencrypted [NFR5.12] | Recorded acceptance | **no — a recorded decision** |
| No child name or mark in a log [NFR24.13, NFR24.14] | Review | **no — nothing automated checks it** |
| No latency assertion on the attendance path [NFR2.6] | Review | **no — the deliberate position** |

---

## Assumptions & Open Questions

- **`project.md`'s NEVER on local write queues contradicts its own cited
  source**, and this unit designs the queue it appears to forbid. The rule
  reads "NEVER accept a write without connectivity in V1; there is no local
  write queue"; NFR5, which it cites, reads **"Permitted for the mid-class
  path only"**. BR3.1 reconciles them: what the NEVER protects is a queue that
  *looks like success*, and the four-state design is its mechanical negation.
  **This document does not edit memory. For the human, at a learnings gate.**
- **I searched for an existing RLS policy on any table other than `profile`** —
  `migrations/versions/0001_initial_identity_schema.py`, every other file under
  `migrations/versions/`, and `app/authz/rls.py` — and found none. NFR14.52's
  claim that `profile` is the only policy is from that search, and it agrees
  with D3's independently-made NFR14.36.
- **I searched for `ALTER DEFAULT PRIVILEGES`** across all of
  `migrations/versions/` and all of `app/`, and found none. § 1.2's per-table
  grant obligation follows from that absence rather than from the convention
  being observed in three migrations.
- **I could not execute any test suite.** Docker is unavailable in this
  session; `python3 -m pytest tests/db/test_governance.py -q` returned
  `sss.sssss`. Every claim about a built test is from reading the file, and
  each is cited by path and symbol. **No claim here rests on a measured run**,
  and the skip itself is the gap `team.md` assigns a CI precondition assertion
  to.
- **The band width of 20 is the functional design's choice**, not an upstream
  decision. § 4.2's worked example is computed at that width; the merge rule
  makes the width largely immaterial to the disclosure property, since what is
  published is whatever survives merging.
- **No threat model document exists for this product.** I searched both
  records' `inception/` trees and `docs/`. The design above is derived from the
  stated constraints and the built gates rather than from an enumerated threat
  set, which is the same basis D1 through D3 used.
