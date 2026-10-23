# Components — what acceptance adds

**Stage**: domain-design (2.6)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **No new component.** The catalogue of 24 entities and their owning
> components is settled in
> `261016-shikhokplus-tuition-app/inception/domain-design/components.md` and
> nothing here reopens it. Acceptance adds **state to an existing entity** and
> one type to an existing hierarchy.
>
> This file records the schema changes, their governance, and why each sits
> where it does.

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — FR1a, FR1.17
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16
- [code] `app/db/models.py`, `app/governance/dispositions.py`,
  `app/authz/lenses.py`, `migrations/versions/`
- [prior] the component catalogue and ADR-001..008

---

## The change, in one sentence

`Enrollment` gains two enum columns for per-link acceptance, `Profile` gains an
address, and the lens hierarchy gains a fourth type. Everything else is
unchanged.

---

## Entity changes

### `Enrollment` — two decision columns

```yaml
entity: Enrollment
owning_component: batches-and-enrollment
change: additive
new_columns:
  - name: student_decision
    type: enum(pending, accepted, declined)
    nullable: false
    column_default: none
    backfill: accepted where student_account_id IS NOT NULL, else pending
    note: NULL is not a state. A seat with no student link carries pending
          and is never read, because the link's absence is carried by
          student_account_id being NULL.
  - name: guardian_decision
    type: enum(pending, accepted, declined)
    nullable: false
    column_default: none
    backfill: accepted where guardian_account_id IS NOT NULL, else pending
```

**Why enums rather than timestamps** [Q1]. The seat already carries
`student_relink_blocked_at` and `guardian_relink_blocked_at` as nullable
timestamps, and mirroring them was the obvious move. It is wrong here. Those
markers are timestamps because *when* erasure happened is the fact that
matters. For acceptance the fact that matters is *which of three states* a link
is in, and the lens resolver reads it on every request.

Two timestamps would make `pending` the absence of two things, and would make a
row with both `accepted_at` and `declined_at` set both expressible and
meaningless. An enum makes the illegal combinations unrepresentable, which is
the property worth paying a migration for.

**Why `NOT NULL`, and why the backfill is conditional rather than a plain
default.** The first draft of this file said "every existing row is pending by
construction: no seat created before this change has been accepted, because
acceptance did not exist", and gave the column a plain `DEFAULT 'pending'`.

**That would have retroactively un-accepted every student already using the
app.** `is_dormant` is computed as `student_account_id is None`
(`app/batches/service.py:172`), so a seat whose student has signed in is not
dormant — that person holds a working student lens today. Defaulting their row
to `pending` would withdraw it, and since four Units are merged with live
staging data, the migration would have taken away access that already works.

The backfill is therefore conditional, and the migration states it explicitly:

```sql
-- student_decision
UPDATE enrollment SET student_decision =
  CASE WHEN student_account_id IS NOT NULL THEN 'accepted' ELSE 'pending' END;
-- guardian_decision
UPDATE enrollment SET guardian_decision =
  CASE WHEN guardian_account_id IS NOT NULL THEN 'accepted' ELSE 'pending' END;
```

A link that already names an account was accepted under the old model, where
signing in *was* acceptance [the superseded AC1.2.1]. A link naming no account
is genuinely unclaimed and becomes `pending`. The column is `NOT NULL` after
the backfill runs, with no column-level default: a default would let a future
insert skip the decision silently, and every insert path should state the
seat's initial state.

### `Profile` — the address

```yaml
entity: Profile
owning_component: identity-and-access
change: additive
new_columns:
  - name: address
    type: text
    nullable: true
    note: Nullable because O1 permits an account to exist before an address
          is supplied in the already-added path, where the teacher filled the
          name and the person adds the address.
```

**Why `Profile` and not `Account`** [Q2]. This is the decision with the
longest shadow, because it decides who can see the data.

`Profile` is the one table under row-level security [BR3.2], with a policy
keyed on the session's account id, and its whole purpose is owner-private
self-authored data. `Account` has no such policy. Putting an address on
`Account` would mean inventing a second protection mechanism for data the first
one already covers — and the second mechanism would be a filter someone
remembers to apply, which is precisely what the three-layer privacy boundary
exists to avoid.

**The display name needs no column.** Signup's "full name" **is**
`profile.self_name`, populated at signup rather than later. A third name would
be one too many: `enrollment.display_name` is teacher-authored and what
teachers see, `profile.self_name` is self-authored and what teachers never see
[BR3.1], and the name a person types about themselves at signup is the second
of those by definition.

### Nothing else changes

No new entity, no entity moves component, no relationship changes. The four
built Units' schemas are untouched beyond the two columns above.

---

## The lens hierarchy — a fourth type

```yaml
component: identity-and-access
file: app/authz/lenses.py
change: additive
new_type:
  name: InvitationLens
  extends: Lens
  carries: enrollment_id
  granted_when: a link on that enrollment names this account and its
                decision is pending or declined
```

**Why a type and not a component** [Q5]. [FR1.9d.1] requires a distinct
invitation lens rather than a special case inside the resolver, and a fourth
type satisfies that in the way that matters:

- the **route-enumeration gate** matches on a dependency's return annotation
  being a `Lens` subtype, so it accepts `InvitationLens` without modification —
  a special case inside the resolver would have been invisible to it;
- a handler **cannot compile a scoped query** without the lens object, because
  the scoping value lives inside it, which is the property that makes
  authorization a data dependency rather than a precondition [TC-11];
- it is granted on **stored state** rather than on a conditional somewhere
  above the query, so a future reader cannot reach the data by writing a query
  that forgets the check.

**What it may read.** One enrollment's batch name, subject and fee amount
[FR1.9d] — all three teacher-authored, so the pending read crosses no privacy
boundary. It reads no attendance, no marks, no other enrollment, and no
`Profile` row but the holder's own.

**Resolved by its own statement, not by a branch of `_LENS_QUERY`.** That
query returns three scalars for one account, including exactly one guardian
enrollment id via `LIMIT 1`. An invitation grant is per-enrollment and a person
may hold several pending seats, so a fourth scalar would have returned only the
first — presenting as "my other invitation never appeared". The three role
lenses stay one statement on the per-request path [NFR6.1]; invitations are
read on one screen and pay for their own query there.

### The two queries that grant lenses must both change

Adding the columns changes nothing on its own. **Two** built queries grant
access on the old evidence, and both need the decision predicate — see
[ADR-014]:

| Query | File | What it grants |
|---|---|---|
| `_LENS_QUERY` | `app/authz/resolve.py` | The student and guardian lenses |
| `_SUMMARY_QUERY` | `app/authz/summary.py` | The counts `GET /v1/me` renders the picker from |

They are **separate statements**, and `GET /v1/me` reads the second. Changing
one alone is a silent half-fix: either the lenses are right and the picker
offers lenses for seats nobody accepted, or the reverse. This is a condition of
D1 being complete, with an adversarial test as its verifier.

---

## Governance

Both manifests are mechanical: a test iterates the migrated schema and fails on
any live table without an entry, so neither column can arrive undeclared.

### The address

| Field | Value |
|---|---|
| Table | `profile` (existing entry, unchanged) |
| Disposition | `HARD_DELETE` |
| Retention | `LIFE_OF_ACCOUNT` |

No manifest change is needed: the address inherits `profile`'s existing entry,
whose basis already reads "everything here is self-authored and owner-private;
nobody else has a claim on it, so it is removed outright" [Q3]. That sentence
is true of an address and is why it belongs on this table.

### The decision columns, and the declined name

`enrollment`'s entry stays `RETAIN_WITH_BASIS` / `LIFE_OF_ACCOUNT`, and its
**basis text is extended** [Q6]:

> `display_name` is TEACHER-authored and part of the teacher's own record. This
> is the direct tension between a guardian's erasure right and a teacher's
> business record, and U11 resolves it against the full schema.
>
> **Added 2026-10-23:** the display name is retained **even on a declined
> seat**, where it names a person who has said the seat is not theirs. Retained
> on the same basis — it is the teacher's own record of who they meant to add,
> and the commonest cause of a decline is a mistyped number they need to
> correct. It is never shown: [AC1.3.3a] puts the bare number on the roster
> row, not the name. The privacy policy generated from this manifest must
> therefore say that a declined enrollment keeps the name the teacher typed.

**Why extend the basis rather than add a per-state entry** [Q6]. The manifest
is per-table by design, and a per-state entry would be its first exception. The
basis text is what the policy generator reads, so extending it is sufficient —
and it keeps the invariant that one table has one entry, which is what makes
the schema-iterating test's "every live table has an entry" check meaningful.

**This is the finding that mattered most in this stage.** Keeping the declined
name was the right call, but it holds personal data about someone who disputed
the relationship. If the manifest had stayed silent, the generated policy would
have been silent, and a policy that omits data the system holds is worse than a
vague one.

---

## What is deliberately NOT stored

| Not stored | Why |
|---|---|
| **When a decision was made** | Nothing in V1 reads it. [AC1.3.3a] shows the declined state, not its date; the artboard's "Declined 14 Oct" is a display affordance that can be met by the audit log if it is ever wanted. Adding a timestamp nobody reads is a column to migrate later for no gain. |
| **Why a seat was declined** | No requirement collects it, [AC1.15.4] sends the teacher no notification, and asking a stranger to explain themselves is worse than letting them refuse. |
| **A decision history** | Rejected at [Q1]: it adds a join to the hottest query in the system to record what nothing reads. The auth audit log already carries the events if a dispute ever needs reconstructing. |

---

## Assumptions & Open Questions

- **Assumed**: the enum is a PostgreSQL native enum rather than a check
  constraint on text. Consistent with nothing else in the schema — there is no
  existing enum column — so this is a first, and a check constraint would be
  the equally defensible choice. Flagged for the migration rather than treated
  as settled, because the two differ in how a fourth value is later added.
- **Assumed**: the address is a single free-text field, as O1 draws it, rather
  than structured lines. Bangladesh addresses do not decompose cleanly into the
  Western line/city/postcode shape, and O1's single textarea is the right call.
- **Open**: whether `InvitationLens` should also be granted on an *accepted*
  seat, so the invitation screen can show a recently accepted one before it
  moves to the batch list. Drawn as moving immediately; if Functional Design
  wants a brief confirmation state, the grant condition widens by one value.

---

## What the review changed

Eight findings, two Critical, each verified against the code before being
acted on. All closed.

| Finding | What was wrong | Closed by |
|---|---|---|
| **Nothing said the lens queries must read the new columns** | `traceability.json` claimed FR1.9a was covered by "a lens is granted only on `accepted`", and no artifact said so. Adding the columns without changing the queries leaves the mistyped-number exposure exactly as it was. | **ADR-014**, naming both queries and an adversarial test as the verifier |
| **`InvitationLens` could not be a branch of `_LENS_QUERY`** | That query returns three scalars, including one guardian enrollment via `LIMIT 1`. An invitation grant is per-enrollment and a person may hold several, so a fourth scalar would have returned only the first — presenting as "my other invitation never appeared". | Its own statement, on the invitation route only |
| **`GET /v1/me` reads a second query nobody named** | `_SUMMARY_QUERY` in `app/authz/summary.py` is separate from `_LENS_QUERY` and carries no decision predicate, so the picker would count unaccepted seats. [FR1.4a] unmet by a read path no artifact mentioned. | Named in ADR-014 alongside the first |
| **ADR-009 still said "defaulting to `pending`"** | The design `components.md` had already rejected. A developer reading the ADR alone implements the live-data incident. | Corrected, pointing at ADR-013 |
| **The erasure markers and decision columns were never reconciled** | `declined` plus an erasure marker is a different fact from a plain decline, and FR11.1a turns on exactly that. | A composition table in ADR-009 |
| **The basis string has no reader** | Nothing reads `basis`; the only test asserts length ≥ 20 characters. The disclosure was a comment, which `project.md` forbids. | D6 named as the installing unit, with the generated-text assertion as its obligation |

Two findings were already fixed before the review returned: the conditional
backfill (ADR-013) and the `Profile` optionality check, both found by reading
the code during the wait.

**What the review did not fault:** no circular dependency, no broken entity
reference, no component-boundary violation, and the scoping discipline — not
reopening the 24-entity catalogue — held throughout.
