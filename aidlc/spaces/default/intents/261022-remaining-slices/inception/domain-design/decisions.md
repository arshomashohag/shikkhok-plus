# Architecture Decision Records — acceptance

**Stage**: domain-design (2.6)
**Phase**: Inception
**Record**: 261022-remaining-slices

> ADR-001..008 are in the prior record and none is superseded. These six
> continue that numbering.

---

## ADR-009: Per-link acceptance is an enum, not a timestamp pair

### Status
Accepted · 2026-10-23

### Context

[FR1.9b] requires acceptance to be recorded **per link** rather than per row,
because a seat's student and guardian are independent facts and one person's
decision must not speak for the other.

`Enrollment` already carries two per-link markers for the erasure case,
`student_relink_blocked_at` and `guardian_relink_blocked_at`, both nullable
timestamps. Mirroring them is the obvious move and the one the first draft of
the requirements implied.

Three forces pull against it:

- The lens resolver reads this state on **every request**, in the system's
  hottest query [NFR6.1], on a 2 GB instance.
- A link has **three** states — pending, accepted, declined — not two.
- A row with both `accepted_at` and `declined_at` set is meaningless, and a
  timestamp pair makes it expressible.

### Decision

Two enum columns, `student_decision` and `guardian_decision`, each
`pending | accepted | declined` and `NOT NULL`.

**No column-level default, and the backfill is conditional** — see [ADR-013].
The first draft of this ADR said "defaulting to `pending`", which would have
withdrawn a working lens from every student already signed in.

### Consequences

**Positive.** The illegal combinations are unrepresentable rather than merely
undocumented. "Pending" is a value rather than the absence of two values, so a
reader never infers a state from which nulls are set. The resolver reads one
column per link.

**Negative.** It diverges from the erasure markers beside it, so a reader
asking "why are these two pairs shaped differently" needs this ADR to answer
them. Adding a fourth state later requires a migration, where a timestamp
scheme would have absorbed it.

**Neutral.** When a decision was made is not recorded. Nothing in V1 reads it,
and the auth audit log carries the events if a dispute needs reconstructing.

### How the decision columns compose with the erasure markers

The two pairs are **independent and both are read**, which the first draft left
unsaid and the review caught. A link therefore carries two facts:

| `*_decision` | `*_relink_blocked_at` | Means |
|---|---|---|
| `pending` | null | Created, not yet answered |
| `accepted` | null | Accepted and in use |
| `declined` | null | Refused. [FR1.9c.1] lets the person un-decline |
| `declined` | set | Refused **and** erased. The account was deleted after declining |
| `accepted` | set | Accepted, then the account was erased |

The fourth row is the one [FR11.1a] turns on: deletion must not clear a
decline, so the decision column survives the erasure marker being set, and the
two together say "this person declined, then left" rather than either alone.

**`accepted` plus an erasure marker does not grant a lens**, because the
account it named no longer exists. The decision column is not an
authorization input on its own; [ADR-014] states the predicate that is.

### Alternatives rejected

- **Two nullable timestamps**, mirroring the erasure markers. Rejected above:
  three states do not fit two nullable timestamps without a third column or an
  inference.
- **A `seat_decision` table**, one row per decision, giving full history.
  Rejected because it adds a join to the hottest query in the system to record
  a history nothing in V1 reads. The audit log already covers the dispute case.

---

## ADR-010: Signup's personal data lives on `Profile`

### Status
Accepted · 2026-10-23

### Context

[FR1.17] adds an address and a display name, both collected at signup. Where
they live decides who can see them, because this project's privacy boundary is
**structural**: `Profile` carries a row-level-security policy keyed on the
session's account id [BR3.2]; `Account` carries none.

A third name is also in tension with two that exist:
`enrollment.display_name` is teacher-authored and is what teachers see;
`profile.self_name` is self-authored and is what teachers never see [BR3.1].

### Decision

The address is a nullable `text` column on **`Profile`**. Signup's "full name"
is **`profile.self_name`** — no new column; the existing field is populated at
signup rather than later.

### Consequences

**Positive.** The address inherits an enforced policy instead of needing a new
one. No third name exists, so "which name does a teacher see" stays answered by
*which table the query reads* rather than by a filter. `profile`'s governance
entry already covers the address without amendment.

**Negative.** A person has a `Profile` row from signup rather than from first
edit, so `Profile` is no longer optional. **Checked rather than assumed:**
nothing constructs or reads `Profile` today — it is defined in `models.py`,
carries the row-level-security policy, and has no reader — so no existing code
changes. The cost is forward-looking: every future reader may assume the row
exists, and a signup path that fails between creating the `Account` and the
`Profile` would leave an account that violates that assumption. Signup creates
both in one transaction for this reason.

**Neutral.** The address is nullable, because O1's already-added path lets a
teacher-created account reach signup with the name filled and the address not.

### Alternatives rejected

- **Both on `Account`.** Rejected: it places personal data outside the only
  table whose policy enforces owner-privacy, and the second mechanism would be
  a filter someone remembers to apply.
- **Name on `Profile`, address on `Account`.** Rejected: it makes the address
  *less* protected than the name with no reason that survives stating.

---

## ADR-011: `InvitationLens` is a fourth type, not a fourth component

### Status
Accepted · 2026-10-23

### Context

A pending person must read three fields of a seat they have not accepted
[FR1.9d]. Every read path in this system is lens-parameterised, and the
route-enumeration gate rejects a route that resolves no lens — but a pending
person by construction holds none of the three existing lenses for that seat.

[FR1.9d.1] requires a distinct lens rather than a special case inside the
resolver, on the grounds that a special case inside the thing that decides
authorization is where an authorization defect hides.

### Decision

`InvitationLens(Lens)`, carrying `enrollment_id`, granted when a link on that
enrollment names this account and its decision is `pending` or `declined`.

**It is resolved by a second statement, not a fourth branch of `_LENS_QUERY`.**
The first draft of this ADR claimed "a fourth branch of the same one-statement
query, no round trip", and that was wrong about the query it named.
`_LENS_QUERY` returns three **scalars** for one account — an owner id, a
student `EXISTS`, and one guardian enrollment id via `ORDER BY created_at, id
LIMIT 1`. An invitation grant is per-enrollment and a person may hold several
pending seats, so the answer is a **set**. A fourth scalar subquery would have
silently returned only the first one, and the bug would have presented as "my
other invitation never appeared".

The invitation read is therefore its own statement, issued only on the
invitation route rather than on every request. That is the right trade: the
three role lenses resolve on every request and must stay one statement
[NFR6.1]; invitations are read on one screen.

### Consequences

**Positive.** The route-enumeration gate accepts it unmodified, because it
matches on the return annotation being a `Lens` subtype. A handler cannot
compile a scoped query without it, so the pending read is bound to one
enrollment by construction.

**Negative.** A fourth lens widens the surface the three-layer privacy boundary
has to hold. Every response schema reachable through it must be checked against
the owner-private field set, like any other.

**Neutral.** It is not offered by the lens switcher. It is scoped to a seat,
not to a role, so it is not one of the three a person chooses between.

### Alternatives rejected

- **A conditional inside the existing resolver.** Rejected by [FR1.9d.1] and
  for the reason it gives.
- **A separate component.** Rejected: it shares the resolver, the query and the
  type hierarchy with the three existing lenses, and a component boundary with
  no enforced rule behind it describes nothing [contract-design learning,
  2026-10-18].

---

## ADR-012: A declined seat keeps the teacher-typed name, and the manifest says so

### Status
Accepted · 2026-10-23

### Context

A teacher types a name when creating a seat. If the number declines — most
often because it was mistyped — the seat holds a name belonging to someone who
has said the seat is not theirs, possibly a person with no connection to the
teacher at all.

The privacy policy is **generated from the governance manifest** [ADR-004], so
whatever the manifest says is what the policy says, and whatever it omits the
policy omits.

### Decision

Keep the name. Extend `enrollment`'s existing basis text to state that the
display name is retained on a declined seat and why, rather than adding a
per-state manifest entry.

### Consequences

**Positive.** The teacher retains their own record of who they meant to add,
which is what lets them correct a mistyped number. [AC1.3.3a] already keeps the
name off the screen — a declined row shows the bare number — so it is retained
without being asserted about the declining person. The generated policy now
discloses it.

**Negative.** The system holds personal data about someone who refused a
relationship with it. That is a real cost and the disclosure is what makes it
honest rather than hidden.

**Neutral.** The manifest stays one entry per table, so the schema-iterating
test's "every live table has an entry" check keeps its meaning.

### The verifier, because a basis string nothing reads is a comment

**Checked rather than assumed:** nothing reads `basis` today. Its only
reference outside `dispositions.py` is `tests/db/test_governance.py`, which
asserts the string is at least 20 characters — a length check, not a content
one. No policy generator exists.

So on its own this disclosure is a comment, and both `project.md`'s "NEVER let
a comment state a count, a version or a scope that nothing checks" and
`team.md`'s named-verifier rule bite.

**The verifier is the policy generator, and its installing unit is D6**, which
already owns generating the privacy policy from the manifests [ADR-004] and
both deletion paths. The obligation this ADR adds to D6 is specific: the
generated text must mention the retained name on a declined seat, and a test
asserts that it does. Until D6 ships, this basis string is a decision recorded
for the unit that will enforce it — which is the shape `team.md` requires, a
control named together with the unit that installs it.

### Alternatives rejected

- **Clear the name on decline.** Defensible, and rejected because it destroys
  the teacher's record of their own action at the moment they most need it —
  when working out which student a wrong number was meant to be.
- **A per-state manifest entry.** Rejected: it would be the manifest's first
  departure from one-entry-per-table, for a disclosure the basis text can
  carry.

---

## ADR-013: The acceptance backfill is conditional, not a default

### Status
Accepted · 2026-10-23

### Context

Adding `student_decision` and `guardian_decision` to `Enrollment` requires
deciding what every existing row becomes. Four Units are merged and staging
holds live data, so this is a migration against real seats rather than an
empty-table change.

The obvious move — `NOT NULL DEFAULT 'pending'` — was in the first draft of
[ADR-009], on the reasoning that no seat can have been accepted because
acceptance did not exist.

**That reasoning is wrong**, and the code says so. `is_dormant` is computed as
`student_account_id is None` (`app/batches/service.py:172`). A seat whose
student has signed in is not dormant: that person holds a working student lens
right now. Under the superseded [AC1.2.1], signing in *was* the act that
granted it.

So a plain default would withdraw a lens from every student already using the
app — a migration that takes away working access, on a children's-data product,
discovered only when someone opened the app and found their batches gone.

### Decision

Backfill conditionally on whether the link names an account:

```sql
UPDATE enrollment SET student_decision =
  CASE WHEN student_account_id IS NOT NULL THEN 'accepted' ELSE 'pending' END;
UPDATE enrollment SET guardian_decision =
  CASE WHEN guardian_account_id IS NOT NULL THEN 'accepted' ELSE 'pending' END;
```

The column is `NOT NULL` after the backfill and carries **no column-level
default**.

### Consequences

**Positive.** Nobody loses access they already have. The mapping is faithful to
the superseded model rather than to a convenient uniform value: a link naming
an account was accepted under the old rules, and a link naming none was never
claimed.

**Negative.** It grants `accepted` to people who never consented, because under
the old model nobody was asked. That is the honest consequence of changing the
consent model after launch, and the alternative — asking every existing user to
re-accept — would log them out of their own records to fix a problem they do
not have.

**Neutral.** No column default means every insert path must state the seat's
initial state. Deliberate: a default would let a future insert skip the
decision silently, and the state is the thing this stage exists to make
explicit.

### Alternatives rejected

- **`NOT NULL DEFAULT 'pending'` for every row.** Rejected above. It is the
  version that reached the first draft, and it would have been a live-data
  incident.
- **Nullable, meaning "decided under the old model".** Rejected: it adds a
  fourth state that means "unknown", which is exactly what [ADR-009] chose
  enums to avoid.

---

## ADR-014: Both existing lens queries must filter on the decision columns

### Status
Accepted · 2026-10-23

### Context

**This ADR exists because the review found it missing, and its absence would
have left open the exact exposure the whole re-cut was created to close.**

[ADR-009] adds the decision columns. `traceability.json` claimed [FR1.9a] was
covered by "a lens is granted only on `accepted`" — but no artifact said so,
and the two built queries that grant lenses would have gone on granting them
on the old evidence.

There are **two** such queries, not one, and the artifacts named neither:

| Query | Where | What it does today |
|---|---|---|
| `_LENS_QUERY` | `app/authz/resolve.py` | Grants the student and guardian lenses on `student_account_id` / `guardian_account_id` naming the account |
| `_SUMMARY_QUERY` | `app/authz/summary.py` | Counts `student_enrollments` and `guardian_children` on the same columns, for `GET /v1/me` |

`GET /v1/me` renders from the **second**, which is a separate statement from
the first. Adding decision columns while changing neither leaves a mistyped
number granting a stranger a guardian lens — unchanged from before acceptance
existed.

### Decision

Both queries gain a decision predicate, and this is a **condition of D1 being
complete** rather than an implementation detail:

- `_LENS_QUERY`'s student branch: `student_account_id = :account_id AND
  student_decision = 'accepted'`
- `_LENS_QUERY`'s guardian branch: the same on `guardian_account_id` and
  `guardian_decision`
- `_SUMMARY_QUERY`'s two counts: the same predicates, so [FR1.4a]'s "only the
  lenses that have data are offered" counts accepted seats rather than all
  seats

### Consequences

**Positive.** The exposure closes where it is created — in the queries that
grant access — rather than in a check somewhere above them. A pending seat
grants nothing because the grant cannot see it.

**Negative.** Two queries must change together, and they live in different
modules. A change to one alone is a silent half-fix: lenses correct, picker
counts wrong, or the reverse.

**Neutral.** Both predicates are on columns of rows the query already reads,
so neither adds a join or a round trip.

### How this is kept true

An adversarial test, not a reviewer's memory: **an account named only on
`pending` or `declined` links resolves no student or guardian lens, and
`GET /v1/me` reports zero for both counts.** That test fails against today's
code, which is what makes it worth writing — it is the regression guard for
the defect this ADR exists to prevent.

### Alternatives rejected

- **Filter above the query, in the resolver's Python.** Rejected: it puts the
  authorization decision somewhere a future query can bypass, which is what
  [TC-11]'s data-dependency design exists to prevent.
- **A database view presenting only accepted links.** Rejected as premature: it
  helps when many queries need the same filter, and there are two.
