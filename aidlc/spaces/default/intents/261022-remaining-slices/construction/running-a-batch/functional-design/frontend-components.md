# Frontend Components — D2 `running-a-batch`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices

> **Technology-agnostic by stage contract, not convention-agnostic.** The
> affirmed practice is conventional Google choices, feature packages with a
> layer split inside each, and a ViewModel mapping a server response to a UI
> state class. The shapes below are stated in those terms because departing
> from them would itself be a design decision.
>
> D2 is the unit where the layer boundary is under most pressure, because
> every screen renders a list and a count.

## Sources

- [upstream] this stage's `functional-spec.md` — the workflows and the
  response-shape change
- [upstream] `inception/units-generation/unit-of-work.md` — D2's six screens
- [upstream] `inception/refined-mockups/` — `T6`, `T7`, `T8`, `G1`
- [upstream] `construction/signing-up-and-joining/functional-design/rules.md`
  — BR1.1, BR5.2, BR7.1, which D2 renders
- [code] `android/.../feature/batches`, `feature/roster`, `feature/auth`,
  read 2026-10-23

---

## The one rule that governs every component here

**A composable receives a UI state and renders it, with no conditional that
depends on a domain value** [TC-9, D-31]. The checkable form: *if the client
is comparing a domain value, the server should have sent a decision.*

D2 has three live instances of that trap, and they are the reason this file
exists rather than being a list of screens:

| Tempting | Why it is wrong | Instead |
|---|---|---|
| `if (acceptedCount > 0)` to choose an empty state | The client deciding what an empty batch is | `EmptyRoster` and `Loaded` are separate states |
| `if (state == DECLINED)` to show the declined mark | Comparing a domain enum to choose a control | The row carries `isDeclined`, decided by the mapper |
| Counting accepted rows client-side | The client deciding what counts as accepted, and wrong once the roster paginates | `accepted_count` from the server [TC-9] |

**The second is the slip D1 made and corrected.** `InvitationCard` branched on
`row.state == AcceptanceState.PENDING` to decide whether to show a decline
button; it became a `canDecline` field the mapper owns. D2 renders four times
as many states, so the same shape will present four times as often.

---

## Component hierarchy

Feature packages with a layer split inside each, as packages in one Gradle
module.

```
feature/batches/          BatchesUiState, BatchesStateMapper
  ui/                     BatchesScreen (exists), CreateBatchScreen (new)
feature/roster/           RosterUiState, RosterStateMapper
  ui/                     RosterScreen (exists), AddStudentScreen (new),
                          RemoveSeatConfirm (new)
feature/guardian/         GuardianUiState, GuardianStateMapper      (new)
  ui/                     GuardianHomeScreen (new)
core/model/               BatchSummary, RosterRow, LinkState         (extended)
core/network/             BatchDto, RosterRowDto, GuardianChildDto   (extended)
```

---

## State shapes

### `BatchesUiState`

| State | Carries | Renders |
|---|---|---|
| `Loading` | — | progress |
| `Empty` | — | "no batches yet" plus create |
| `Loaded` | `List<BatchSummary>` | the list |
| `Failed` | `messageKey`, `retryable` | the message, retry if permitted |

`BatchSummary` carries `acceptedCount` and `seatCount` **as the server sent
them**, plus `acceptedLabel` — the formatted "9 of 12 accepted" string key and
its arguments. Formatting is the screen's; the numbers are not.

### `RosterUiState`

| State | Carries |
|---|---|
| `Loading` | — |
| `EmptyRoster` | the batch, so the screen can still offer "add student" |
| `Loaded` | the batch summary plus `List<RosterRow>` |
| `Failed` | `messageKey`, `retryable` |
| `ConfirmingRemoval` | the row being removed |
| `RemovalRefused` | `messageKey` **and** which remedy applies |

**`EmptyRoster` is a distinct state, not a `Loaded` with no rows.** A blank
list explains nothing, and the screen needs the batch in hand to offer the one
action that helps.

**`RemovalRefused` carries the remedy, not just the message** [BR7.1]. Claimed
and erased refuse for different reasons with different remedies — mark
inactive, versus the seat cannot be reused at all — and a screen showing one
message for both leaves a teacher trying the wrong one.

### `RosterRow`

| Property | Why it is a decision, not a value |
|---|---|
| `displayLabel` | The **number** for a declined seat, the name otherwise [ADR-012]. The mapper chooses; the screen renders |
| `studentState` | `pending \| accepted \| declined` |
| `guardianState` | the same, plus **`absent`** when no guardian link exists |
| `isDeclined` | Whether to mark this row. Declined per row, pending not [AC1.3.3a] |
| `isRemovable` | Server decision [BR7.1] — never inferred from the states above |
| `statusLabel` | The existing resource key for `dormant/active/inactive` |

**`isRemovable` is separate from the two link states on purpose.** It could be
derived from them today, and deriving it would move the removability rule into
the client — where D1 just finished moving it out of, for merged code that had
the same shape.

### `GuardianUiState`

| State | Carries |
|---|---|
| `Loading` | — |
| `OneChild` | that child's seat; the switcher is not drawn |
| `SeveralChildren` | the list, with the selected child named |
| `Failed` | `messageKey`, `retryable` |

**`OneChild` and `SeveralChildren` are separate states** rather than a list
whose length the screen checks — the same rule as `EmptyRoster`, and the
single-child case is the common one.

---

## Interaction flows

### Removing a seat

```
roster row -> remove -> ConfirmingRemoval
                          |-- confirm --> removing -> Loaded (seat gone)
                          |                      \-> RemovalRefused(remedy)
                          \-- cancel  --> Loaded
```

The confirmation names what is being removed. The refusal names the remedy.

### Switching children

```
GuardianHome(OneChild)        -> no switcher
GuardianHome(SeveralChildren) -> switcher -> child named as a PATH PARAMETER
```

**Back must not land on the previous child's data** [AC9.4.2]. A switch
replaces rather than stacks; this is a privacy case in navigation's clothing
and it is the one back-stack obligation in D2 worth testing rather than
assuming.

---

## Form validation

**Format only, never policy** [team: Layer boundaries].

| Form | Client checks | Server decides |
|---|---|---|
| Create batch | name non-empty, at least one subject | whether the teacher may create it |
| Add student | name non-empty, phone shape if given | whether the number is already on this batch |
| Remove seat | — | whether the seat is removable [BR7.1] |

A duplicate seat is **not** a client-side check: whether a number is already
on a batch is a server decision and arrives as a failure state.

---

## API integration points

| Screen | Route | Exists? |
|---|---|---|
| `T6` | `GET /v1/batches` | yes — gains the count |
| create batch | `POST /v1/batches` | yes |
| `T7` | `GET /v1/batches/{id}/roster` | yes — gains per-link states |
| `T8` | `POST /v1/batches/{id}/enrollments` | yes |
| mark inactive | `PATCH /v1/enrollments/{id}` | yes |
| remove seat | `DELETE /v1/enrollments/{id}` | yes |
| `G1` | `GET /v1/guardian/children` | yes |

**No new route.** Two response shapes widen; every route is built and
lens-resolved.

---

## Test obligations

Per the affirmed Android posture: mapping functions, not untargeted
ViewModels.

| Target | Tests |
|---|---|
| `RosterStateMapper` | `isDeclined` set for declined only; `displayLabel` is the number for declined and the name otherwise; `absent` guardian state; `isRemovable` read from the server |
| `BatchesStateMapper` | the count comes from the response; `Empty` versus `Loaded` |
| `GuardianStateMapper` | `OneChild` versus `SeveralChildren` |
| Screens (Robolectric) | declined marked per row and pending not; a split seat rendered once with both states; the two refusals showing different remedies; Back after a child switch |

**Every new user-facing string lands in both bundles** and each of the six
screens needs a row in `docs/delivery/bangla-layout-check.md` before this unit
completes [FR0.2].

---

## Assumptions & Open Questions

- **Assumed**: `BatchesScreen.kt` and `RosterScreen.kt` are extended in place
  rather than replaced. Both already render a server-chosen `statusLabel`, so
  the pattern is established and the change is additive.
- **Assumed**: the switcher is a selection control rather than a navigation
  stack, which is what makes the Back obligation satisfiable.
- **Open, and D3's**: whether the roster shows a fee column per row. The
  roster response already carries `fee_amount`; what a declined seat shows for
  it is a money question and there is no ledger until D3.
