# Functional Specification — D2 `running-a-batch`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **D2 is typed `ui`, which settles `entities.md` and not `rules.md`.** This
> unit adds no entity, so `produces_kinds` makes `entities.md` inapplicable.
> It does carry rules — what the roster marks, counts, shows and permits are
> each decisions somebody could implement two ways — and they live in
> `rules.md` beside this file.
>
> This file owns the **interaction workflows and screen-state transitions**,
> and the one response-shape change those workflows require.
>
> D2 is **screens over endpoints that already work**. Seven batch and roster
> routes are built and lens-resolved; two of the six screens exist. The design
> work is where the seam falls between what the server already decides and
> what the screens render.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` — D2's scope and
  its Done-when
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.3,
  US1.15, US2.1–US2.6
- [upstream] `inception/requirements-analysis/requirements.md` — FR1.9b,
  FR1.9h, FR1.9i
- [upstream] `construction/signing-up-and-joining/functional-design/rules.md`
  — BR1.1, BR5.2, BR5.4, BR7.1, BR7.2, which D1 built and D2 renders
- [upstream] `inception/refined-mockups/` — `T6`, `T7`, `T8`, `G1`
- [code] `app/api/batches.py`, `app/schemas/batches.py`,
  `app/batches/service.py`, `android/.../feature/batches`, `feature/roster`,
  read 2026-10-23

---

## 1. The one thing D2 changes on the server

**D1 stored the per-link decisions; no response exposes them.** That is the
whole backend change in this unit, and it is a response-shape widening rather
than a new capability.

### What the roster returns today

`RosterRowResponse` carries `status`, a server-computed enum of exactly
`dormant | inactive | active`, decided by `_roster_status`
(`app/api/batches.py:71`):

```
if row.is_dormant:              return "dormant"
if row.inactive_from is not None: return "inactive"
return "active"
```

The *shape* is right and this unit keeps it: the client switches on a decision
and never compares a date of its own [TC-9]. Returning `inactive_from` alone
and letting the client decide is the erosion path that function exists to
close.

### Why it is now too narrow

D1 redefined `is_dormant` as **no link has accepted** [BR7.2]. So a seat whose
student accepted and whose guardian declined is not dormant, carries no
`inactive_from`, and reports plain `active` — losing exactly the distinction
[AC1.10.7] requires the roster to show.

| Seat | Student link | Guardian link | Reports today | Should show |
|---|---|---|---|---|
| Nobody answered | pending | pending | `dormant` | pending, in the batch count |
| Both accepted | accepted | accepted | `active` | accepted |
| Student in, guardian out | accepted | **declined** | `active` | accepted **+ guardian declined** |
| Mistyped number, refused | **declined** | — | `dormant` | **declined**, per row |
| Left the batch | accepted | accepted | `inactive` | inactive |

Rows three and four are the ones the current shape cannot express.

### The change

| Response | Gains | Kind |
|---|---|---|
| `RosterRowResponse` | `student_state`, `guardian_state` — each `pending \| accepted \| declined \| absent` | server-computed decision |
| `BatchResponse` | `accepted_count` **only** | server-computed decision |

**The denominator already exists and is not renamed.** `BatchResponse`
carries `enrollment_count` today (`app/schemas/batches.py:114`, computed
server-side in `app/batches/service.py:391`), which is exactly BR1.4's "every
seat the teacher created". So D2 adds **one** field, not two: `accepted_count`
is the numerator and `enrollment_count` stays the denominator under its
existing name.

Stated explicitly because a draft of this file proposed `seat_count` as a new
field, which would have left Code Generation with two names for one number and
no rule about which to trust. Renaming `enrollment_count` was the other
option and is worse: it is already in the committed OpenAPI schema and the
built `BatchesScreen`, so a rename is a contract change bought for a tidier
word.

`status` stays as it is. The two new fields sit beside it rather than
replacing it, because `inactive` is a different axis from acceptance and
collapsing the two is what produced the gap above.

**`absent` is a fourth value and not a null**, for the guardian link only. A
seat with no guardian recorded has no decision to report, and reporting
`pending` there would count a decision nobody was asked for — making the batch
count wrong by exactly the number of guardian-less seats.

---

## 2. Workflows

### W1 — Creating a batch

Covers US2.1.

1. The teacher opens the batch list (`T6`) and chooses to create.
2. The create form takes name, subjects, and optionally a default fee, a fee
   due day and collection details.
3. On submit the server creates the batch owned by this teacher's `Owner` row.
4. The list returns with the new batch showing `0 of 0 accepted`.

**The count renders from the first moment**, so a teacher sees the shape of
the number before any seat exists rather than meeting it later.

### W2 — Adding a student

Covers US2.2 and `T8`.

1. From a batch, the teacher adds a student: a display name, optionally a
   guardian phone number, optionally a fee for this seat.
2. The server creates the `Enrollment` with **both decisions `pending`** —
   stated explicitly because there is no column default and every insert path
   must say so [ADR-013].
3. The roster returns with the seat present, counted in the denominator, and
   **not marked per row**: pending is the normal state of a new seat
   [AC1.3.3a].

**Nothing is sent to the person named.** A seat is created; the person
discovers it when they sign up, and the teacher is told nothing further
[AC1.15.4].

### W3 — Reading the roster

Covers US1.3 (amended), US2.3, and `T7`.

1. The teacher opens a batch.
2. The server returns the batch with `accepted_count` of `enrollment_count`, and one
   row per seat carrying `status`, `student_state` and `guardian_state`.
3. The screen renders:
   - the **count** at batch level — "9 of 12 accepted" [AC1.3.5a];
   - **declined** marked per row [AC1.3.3a];
   - **pending** not marked per row, because it is normal;
   - a split seat showing **both link states separately**, once [AC1.10.7].
4. A declined row shows the **bare number, not the teacher-typed name**
   [ADR-012]. The name is retained as the teacher's record of who they meant
   to add — the commonest cause of a decline is a mistyped number they need to
   correct — and it names a person who has said the seat is not theirs.

**The count is the server's** [TC-9]. A client counting accepted rows is a
client deciding what counts as accepted, and it would also be wrong the moment
the roster paginates.

### W4 — Removing a seat

Covers US2.5 (amended) and US1.15.

1. The teacher removes a seat from the roster.
2. The screen confirms, naming what is being removed.
3. The server removes it **if no link has accepted and no erasure marker is
   set** [BR7.1] — D1 built this predicate; D2 renders it.
4. Two refusals, each with its own remedy:

| Refusal | Means | The teacher's remedy |
|---|---|---|
| `ENROLLMENT_CLAIMED` | Somebody accepted | Mark the seat inactive; the record stands [FR1.9i, ADR-003] |
| `ENROLLMENT_ERASED` | The account was erased | The seat cannot be reused at all |

**The distinct codes exist because the remedies differ**, and a screen showing
one message for both would leave a teacher trying the wrong one.

**This is the mistyped-number recovery path** [AC2.5.1a]. Before D1 it closed
the moment a stranger signed up; D1 reopened it and D2 is where a teacher can
reach it.

### W5 — Marking a seat inactive

Covers US2.4's lifecycle half and FR1.9i.

1. For an accepted seat, removal is refused; the teacher marks it inactive
   instead, with a date.
2. `inactive_from` is recorded and `status` becomes `inactive`.
3. The seat **stays on the roster** and its history stands [ADR-003].

The acceptance axis is untouched: an inactive seat keeps whatever decisions
its links carry, because leaving a batch is not un-accepting it.

### W6 — The guardian's children (`G1`)

Covers US2.6 and settles OQ-7.

1. A guardian signs in and resolves a `GuardianLens`.
2. `GET /v1/guardian/children` returns the seats **reachable through
   `guardian_account_id`**, never through the child [BR5.3 of
   identity-and-access, NFR14.15].
3. A guardian with one child goes straight through; several children get a
   switcher.
4. Every subsequent request names the child as a **path parameter**, never a
   client-supplied hint.

**OQ-7 is settled by the built code rather than re-decided here.** The lens
carries `child_enrollment_id` filled with the first reachable enrollment so a
single-child guardian goes straight through, and no authorization decision
reads it without the route having named it.

**A declined guardian link reaches nothing**, and the reason is worth stating:
`list_guardian_children` has no decision predicate of its own. It is safe
because `GuardianLens` stops being granted [BR1.1] — defended by the lens, not
by itself. The seat stays in that guardian's **invitations**, where they may
still accept it [BR5.4].

---

## 3. Screen states

| Screen | States | New? |
|---|---|---|
| `T6` batch list | loading, empty, loaded, failed | **exists**; gains the count |
| `T7` batch + roster | loading, empty roster, loaded, failed | **exists**; gains per-link state and the declined row |
| `T8` add student | form, submitting, failed, added | new |
| create batch | form, submitting, failed, created | new |
| remove seat | confirm, removing, refused-claimed, refused-erased | new |
| `G1` guardian home | loading, one child, several children, failed | new |

Every state is a sealed UI state the mapper produces; a composable receives
one and renders it with **no conditional depending on a domain value**
[TC-9, D-31]. The two erosion paths D2 is most likely to take:

- **`if (count > 0)` for an empty-roster state.** That is the client deciding
  what an empty batch is. The state is `EmptyRoster` or `Loaded`, decided by
  the mapper.
- **`if (state == DECLINED)` to show the declined mark.** Same shape as the
  slip D1 made and corrected: the row carries the decision the screen renders.

---

## 4. Per-screen obligations

| Obligation | Applies | Verifier |
|---|---|---|
| Bangla layout check | all six screens | a row in `docs/delivery/bangla-layout-check.md` [FR0.2] |
| Accessibility and back-stack | all six | Back must never land in another lens's data [AC9.4.2] |
| Both string bundles | every new string | `values/` and `values-bn/` together |

**`G1` is the back-stack case worth naming.** A guardian switching children
moves between two scopes of the same lens; Back must not land on the previous
child's data after a switch, which is a privacy case wearing navigation's
clothes.

---

## 5. Verification obligations

Test-after by the affirmed predicate: D2's work is rendering and response
shape, not an authorization decision. **The one exception is the count**,
which is a server decision whose wrong answer misreports who has agreed — so
it is tested from the criterion before the endpoint is written.

| Obligation | Covers |
|---|---|
| `accepted_count` counts accepted links, not signed-up accounts | AC1.3.5a |
| The denominator includes declined seats | assumption, stated below |
| A split seat returns both link states, and the screen shows it once | AC1.10.7 |
| A guardian-less seat reports `absent`, not `pending` | § 1 |
| Declined is marked per row; pending is not | AC1.3.3a |
| A declined row shows the number, not the name | ADR-012 |
| Removal is refused with the **right** code for claimed versus erased | BR7.1 |
| A guardian reaches children only through `guardian_account_id` | NFR14.15 |
| Back from a switched child does not reach the previous child | AC9.4.2 |

---

## Assumptions & Open Questions

- **Assumed**: `accepted_count / enrollment_count` counts every seat the teacher
  created, declined ones included. A declined seat is still a seat; excluding
  it would make the denominator shrink silently as people decline, so "9 of
  12" would become "9 of 11" without anything having been removed.
- **Assumed**: a seat with no guardian link reports `absent` rather than
  `pending`, per § 1.
- **Assumed**: `status` keeps its three values and the new fields sit beside
  it. Folding acceptance into `status` would produce a product of two axes and
  a value set nobody can switch on exhaustively.
- **Open, and D3's**: what a declined seat shows for its fee. D2 renders the
  roster; the money consequence of a decline is US1.14 and no ledger exists
  until D3 creates one.
