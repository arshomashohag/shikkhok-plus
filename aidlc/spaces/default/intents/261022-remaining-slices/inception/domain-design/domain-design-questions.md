# Domain Design — Questions

**Stage**: domain-design (2.6)
**Phase**: Inception
**Record**: 261022-remaining-slices

## Sources

- [upstream] `inception/requirements-analysis/requirements.md` — FR1a
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16
- [code] `app/db/models.py`, `app/governance/dispositions.py`,
  `migrations/versions/`
- [prior] `261016-shikhokplus-tuition-app/inception/domain-design/` — the
  component catalogue and ADR-001..008

---

## How this stage is scoped

The component model is settled and nothing here reopens it. Acceptance adds no
new component: it adds **state to an existing one**. `Enrollment` already
carries two per-link erasure markers for exactly the reason acceptance needs
two per-link acceptance markers, and the governance manifest already exists with
a test that fails on any live table lacking an entry.

So this stage's work is narrow and concrete: **where four new columns live, what
each one's disposition and retention class is, and whether the acceptance state
is derivable or stored.** Getting a column's placement wrong is the expensive
kind of error, because it is the one that needs a migration to undo after data
exists.

---

## Q1. How is a seat's acceptance state represented?

[FR1.9b] requires per-link markers. The seat already carries
`student_relink_blocked_at` and `guardian_relink_blocked_at`, both nullable
timestamps, for the erasure case.

- A. **Two nullable timestamps, mirroring the erasure markers**:
  `student_accepted_at`, `guardian_accepted_at`. Null means not yet accepted.
  Declined needs its own marker, so this is four columns in total.
- B. **Two enum columns**, each `pending | accepted | declined`, which makes the
  state explicit and the illegal combinations unrepresentable.
- C. A separate `seat_decision` table, one row per link per decision, which
  gives a full history of who decided what and when.
- X. Other (please specify)

[Answer]: B. Two enum columns, each `pending | accepted | declined`,
one per link: `student_decision` and `guardian_decision`. The state is explicit
and the illegal combinations are unrepresentable, which a pair of nullable
timestamps cannot give — with timestamps, "pending" is the absence of two
things, and a row with both `accepted_at` and `declined_at` set is expressible
and meaningless.

Chosen over mirroring the erasure markers deliberately. The erasure markers are
timestamps because *when* erasure happened is the fact that matters; for
acceptance the fact that matters is *which of three states* the link is in, and
the lens resolver reads that state on every request. A separate decision table
was rejected: it adds a join to the hottest query in the system [NFR6.1] to
record a history nothing in V1 reads.

## Q2. Where do the signup columns live — `account`, `profile`, or elsewhere?

[FR1.17] adds an **address** and a **display name** from signup. The placement
decides who can see them, because the privacy boundary is structural: `profile`
is under row-level security and owner-private; `account` is not.

The tension: a teacher-typed name already lives on `enrollment.display_name`,
and `profile.self_name` already holds a self-authored name that teachers never
see [BR3.1]. A third name is one too many unless its role is distinct.

- A. **Both on `profile`.** The self-authored name signup collects *is*
  `profile.self_name` — same field, now populated at signup rather than later
  — and the address joins it as owner-private data under the same policy.
- B. **Both on `account`.** They are supplied at account creation, so they
  belong to the account rather than to the private profile.
- C. **Name on `profile`, address on `account`.**
- X. Other (please specify)

[Answer]: A. Both on `profile`. The self-authored name signup
collects **is** `profile.self_name` — the same field, populated at signup
rather than later — so no third name is introduced, and the address joins it as
owner-private data under the row-level-security policy that already exists
there [BR3.2].

Placing either on `account` would put personal data outside the one table whose
policy enforces owner-privacy, which would mean inventing a second protection
mechanism for data the first one already covers.

## Q3. What is the address's disposition and retention?

Whatever Q2 decides, the address is new personal data and needs both. For
comparison, `profile` today is `HARD_DELETE` / `LIFE_OF_ACCOUNT`, with the
basis "everything here is self-authored and owner-private; nobody else has a
claim on it".

- A. **`HARD_DELETE` / `LIFE_OF_ACCOUNT`**, same as the rest of `profile`.
  Self-authored, nobody else has a claim, removed outright on deletion.
- B. `ANONYMIZE_IN_PLACE`, if any teacher-facing feature might later need a
  coarse location.
- C. `RETAIN_WITH_BASIS`, if an address is ever part of a teacher's record.
- X. Other (please specify)

[Answer]: A. `HARD_DELETE` / `LIFE_OF_ACCOUNT`, the same as the
rest of `profile`, and for the same recorded reason: everything there is
self-authored and owner-private, nobody else has a claim on it, so it is
removed outright. No teacher-facing feature reads an address and none is
planned; `ANONYMIZE_IN_PLACE` would retain data against a use case nobody has
named.

## Q4. Does a declined seat keep the teacher-typed name?

A teacher types a name when adding a seat. If that number declines — commonly
because the number was mistyped — the seat holds a name the declining person
never confirmed and may have nothing to do with.

[AC1.3.3a] already shows the bare number rather than the name on a declined
row, so the UI does not display it. The question is whether it is still stored.

- A. **Keep it.** It is teacher-authored data in the teacher's own record, the
  same basis `enrollment` already carries, and the teacher may need it to work
  out which student they meant.
- B. **Clear it on decline.** The name was typed about a person who has said
  this seat is not theirs, so retaining it keeps an assertion they disputed.
- X. Other (please specify)

[Answer]: A. Keep it. It is teacher-authored data in the
teacher's own record — the same basis `enrollment` already carries — and the
teacher may need it to work out which student they meant when correcting a
mistyped number.

[AC1.3.3a] already keeps it off the screen: a declined row shows the bare
number, not the name. So the name is retained without being asserted about the
declining person.

## Q5. Is the invitation lens a component, or a variation of the existing one?

[FR1.9d.1] requires a distinct invitation lens rather than a special case in
the resolver. `app/authz/lenses.py` defines `Lens`, `TeacherLens`,
`StudentLens` and `GuardianLens` as a type hierarchy.

- A. **A fourth type in the existing hierarchy**, `InvitationLens`, scoped to
  one enrollment, resolved by the same resolver from the same one-statement
  query. No new component.
- B. A separate component, because an invitation lens is granted on different
  evidence from the other three.
- X. Other (please specify)

[Answer]: A. A fourth type in the existing hierarchy,
`InvitationLens`, scoped to one enrollment and resolved by the same resolver
from the same one-statement query. No new component.

This satisfies [FR1.9d.1]'s "not a special case inside the resolver" in the way
that matters: it is a distinct TYPE, so the route-enumeration gate — which
matches on the return annotation being a `Lens` subtype — accepts it without
change, and a handler cannot compile a scoped query without one.

## Q6. How is the retained declined name recorded in the governance manifest?

Keeping the teacher-typed name on a declined seat [Q4] means the system holds a
name for a person who said the seat is not theirs. The privacy policy is
generated from the manifest, so a manifest silent about it produces a policy
silent about it.

[Answer]: Note it in `enrollment`'s existing basis rather than creating a
per-state entry. The manifest is per-table by design, and a per-state entry
would be the first exception to that; the basis text is what the policy
generator reads, so extending it is sufficient and keeps one entry per table.
