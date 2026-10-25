# Functional Design — Questions

**Stage**: functional-design (3.1)
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

## How this stage was answered

D2 is typed `ui`: **screens over endpoints that already work**, with no new
backend capability beyond the roster's acceptance state. Seven batch and
roster endpoints are built and routed, two of the six screens exist, and D1
has just stored the two per-link decision columns.

So the design question is not what to build but **where the seam falls**: what
the existing responses already carry, what they do not, and which of the gaps
is a server decision the client must not make for itself. Each answer is
settled from an upstream criterion or a direct read of the built code, and the
source is named.

---

## Q1. What does the roster response carry today, and is it enough?

[Answer]: **Not enough, and this is D2's one real backend change.**
`RosterRowResponse` carries `status`, a server-computed enum of exactly
`dormant | inactive | active` decided by `_roster_status`
(`app/api/batches.py:71`). That shape is correct in kind — the client switches
on a decision rather than comparing a date — and it is now too narrow.

D1 made `is_dormant` mean *no link has accepted* [BR7.2]. So after D1 a seat
whose student accepted and whose guardian declined is not dormant, has no
`inactive_from`, and reports plain `active` — losing exactly the distinction
[AC1.10.7] requires the roster to show.

[code: `app/api/batches.py:71`, `app/schemas/batches.py:155-172`] [AC1.10.7]

## Q2. Per-row or batch-level: what does the roster show for each state?

[Answer]: **Declined per row; pending as a batch-level count.** The criteria
are explicit and they disagree deliberately:

| State | Where | Why [AC1.3.3a, AC1.3.5a] |
|---|---|---|
| **declined** | per row | It is abnormal and actionable — most likely a mistyped number |
| **pending** | batch-level count ("9 of 12 accepted") | It is the **normal** state of a new seat; decorating most rows would flag normality as a problem |
| **accepted** | the count's numerator | Scale without per-row clutter |

The superseded AC1.3.3 said dormant "is not marked there" for that reason, and
the amendment keeps the reasoning while changing which state is normal.

[AC1.3.3a] [AC1.3.5a]

## Q3. Does the client compute the "9 of 12" count?

[Answer]: **No — it is a server decision** [TC-9, D-31]. A client counting
accepted rows is the client deciding what counts as accepted, which is the
erosion path this project's layer boundary names: *if the client is comparing
a domain value, the server should have sent a decision*.

The count also cannot be derived correctly from the rows a client holds once
the roster paginates, and D2 is the unit that would establish the wrong habit
for D3's fee status and D5's dues list.

[TC-9] [D-31] [team: Layer boundaries]

## Q4. One seat, two people, two states — how is that one row?

[Answer]: The row carries **both link states separately** and the screen shows
the seat once [AC1.10.7]. D1's data model is already per-link [BR5.2]; what is
missing is the response exposing both rather than collapsing them.

The case that makes this concrete: a student accepts and their guardian
declines. The student is enrolled and owes a fee; the guardian simply does not
watch. Collapsing that into one seat state would have to pick one, and either
pick is wrong.

[AC1.10.7] [BR5.2] [FR1.9b] [FR1.9h]

## Q5. What does the teacher see for a declined seat — the name or the number?

[Answer]: **The bare number, not the teacher-typed name** [AC1.3.3a's
companion]. The name is retained — it is the teacher's own record of who they
meant to add, and the commonest cause of a decline is a mistyped number they
need to correct — but it names a person who has said the seat is not theirs,
so it is not displayed.

[ADR-012] [governance: the declined name]

## Q6. Can a teacher still remove a seat after someone signs up?

[Answer]: Yes, and D1 already built it. `remove_enrollment` reads
`_nobody_accepted()` rather than `student_account_id`, so a seat stays
removable while nobody has accepted it — which is the mistyped-number recovery
path [BR7.1, AC2.5.1a].

D2 owns the **screen** for it: the remove action and its two distinct
refusals, claimed and erased, which carry different remedies.

[BR7.1] [AC2.5.1a] [code: `app/batches/service.py`]

## Q7. What is the guardian child route's shape? (OQ-7)

[Answer]: **The child arrives as a path parameter, never as a client-supplied
hint**, and `GET /v1/guardian/children` is already built and routed. The
guardian lens carries `child_enrollment_id` filled with the first reachable
enrollment so a single-child guardian goes straight through, but **no
authorization decision reads it without the route having named it**.

That is what OQ-7 was open on and the built code settles it; D2 records the
settlement rather than re-deciding it.

[OQ-7] [code: `app/authz/lenses.py`, `app/api/batches.py:277`] [US2.6]

## Q8. Does a guardian see a child whose seat they declined?

[Answer]: No. A declined guardian link grants no `GuardianLens` [BR1.1], so
`list_guardian_children` returns nothing for that seat — it is safe **only
because the lens stops being granted**, not because the query filters
[rules.md sweep]. The seat remains in that guardian's **invitations**, where
they may still accept it [BR5.4].

[BR1.1] [BR5.4] [D1 rules.md]

## Q9. Does D2 add any endpoint?

[Answer]: **No new route. One response shape widens.** The roster response
gains the per-link states and the batch response gains the accepted count,
both as server-computed decisions. Every route D2 needs exists and is
lens-resolved.

[D2 scope: "no new backend capability beyond the roster's acceptance state"]

## Q10. Which screens are new?

[Answer]: Four new, two extended.

| Screen | State |
|---|---|
| `T6` batch list | **exists** — `BatchesScreen.kt`; gains the accepted count |
| `T7` single batch + roster | **exists** — `RosterScreen.kt`; gains per-link state and the declined row |
| `T8` add student | new |
| create-batch | new |
| remove-student | new (confirmation + its two refusals) |
| `G1` guardian child home | new |

[D2 scope] [refined-mockups]

## Assumptions & Open Questions

- **Assumed**: the accepted count is `accepted / total` where total is every
  seat on the batch including declined ones. A declined seat is still a seat
  the teacher created, and excluding it would make the denominator drift
  silently as people decline.
- **Assumed**: a seat with no guardian link reports its guardian state as
  absent rather than `pending`. `pending` on a link that does not exist would
  make the batch count wrong by counting a decision nobody was asked for.
- **Open, and D3's**: what a declined seat shows for its fee. D2 renders the
  roster; the money consequence of a decline is US1.14 and there is no ledger
  until D3.
