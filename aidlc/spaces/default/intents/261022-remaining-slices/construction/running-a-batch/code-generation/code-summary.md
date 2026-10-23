# Code Summary — D2 `running-a-batch`

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: D2 `running-a-batch`
**Record**: 261022-remaining-slices
**Date**: 2026-10-23

## Sources

- [upstream] `functional-design/` — functional-spec, rules.md (BR1.1–BR4.2),
  frontend-components
- [upstream] `nfr-requirements/`, `nfr-design/` — 17 NFRx.y
- [upstream] `infrastructure-design/` — no infrastructure, no migration
- [upstream] `inception/units-generation/unit-of-work.md` — D2's scope
- [code] `app/batches/`, `app/schemas/`, `app/api/`, `android/.../feature/`,
  read 2026-10-23 before any change

---

## What was built

D1 stored a per-link acceptance model and **no response exposed it**. A seat
the student accepted and the guardian declined reported plain `active`. D2
makes it visible and ships the four screens that model made necessary.

**No migration. No new route. No new backend capability.** Two response shapes
widen; every endpoint was already built and lens-resolved.

### Backend — four fields, one of them unplanned

| Response | Field | Why |
|---|---|---|
| `BatchResponse` | `accepted_count` | BR1.2. `enrollment_count` stays the denominator under its existing name |
| `RosterRowResponse` | `student_state` | BR2.1 |
| `RosterRowResponse` | `guardian_state` | BR2.2 — **four values**, `absent` among them |
| `RosterRowResponse` | `is_removable` | BR3.1 — **not in the plan's field list; see Deviations** |

`status` is unchanged and sits beside the new fields. Acceptance is a different
axis from activity: an inactive seat keeps whatever decisions its links carry,
because leaving a batch is not un-accepting it.

**The count is one conditional aggregate on the existing grouped statement**
[NFR20.7, NFR20.8]. `count(id) FILTER (WHERE student_decision = 'accepted' OR
guardian_decision = 'accepted')`, syntax-checked against the pinned SQLAlchemy
2.1.5 **before** it was written — the plan named a fourth grouped statement as
the fallback and it was not needed. The count therefore costs no extra statement
however many batches a teacher owns.

### Android — six screens, three mappers

`BatchesScreen` and `RosterScreen` were extended in place. `CreateBatchScreen`,
`AddStudentScreen`, `RemoveSeatConfirm` and the new `feature/guardian` package
are new. `BatchesStateMapper` moved out of `BatchesViewModel.kt` into its own
file, matching `RosterStateMapper` and `InvitationsStateMapper`.

---

## The three decisions worth reading

### 1. `absent` is keyed on the typed number, not the account id

BR2.2 says a seat with no guardian link reports `absent` rather than `pending`.
The obvious implementation reads `guardian_account_id IS NULL` — and it is
**wrong in the expensive direction**.

A guardian the teacher recorded who has not signed up yet carries
`guardian_phone` and a NULL `guardian_account_id`: `_LINK_GUARDIAN_SEATS` fills
the account id only at signup [BR5.1]. Those guardians *were* asked and have not
answered, so they are pending. Keying absence on the account id would report
every unregistered guardian as `absent` — dropping them out of the outstanding
figure, which is the exact inversion BR2.2 exists to prevent.

`_guardian_state` therefore returns `absent` only when **neither** the number
nor the account id is set. `test_a_recorded_guardian_who_has_not_answered_is_pending_not_absent`
is the test that would have caught the other reading.

### 2. `is_removable` had to become a server field

The plan's Step 6 said "the three new response fields" and Step 12 said the row
gains `isRemovable` **read from the server**. The response carried no such
field, and nothing in D2's scope added one — so the plan as written could only
have been satisfied by a client-side derivation, which BR3.1 and NFR14.31
forbid for a specific reason rather than a dogmatic one:

> `remove_enrollment` refuses on **two** independent conditions — no link
> accepted, and no erasure marker set. **The roster row carries the first and
> not the second.**

A client deriving removability from the two link states it displays would offer
removal on an **erased** seat, whose decisions both read `pending`. That is not
a style violation; it is a wrong answer the UI presents as an available action.

So `is_removable` was added to the service, the schema and the API. The test
that makes it load-bearing is
`test_removability_agrees_with_what_removal_actually_does`: three seats, one per
outcome, each row's answer compared against what `remove_enrollment` actually
does. The erased seat is the discriminating case.

### 3. One row builder, because the add response and the roster must agree

`add_enrollment` now returns a `RosterRow` rather than an ORM `Enrollment`, and
both it and `list_roster` build through `_roster_row`. The handler maps through
one `_roster_row_response`.

This replaced a hand-written `status="dormant"` in the add handler. Two mappings
of the same columns is how an add response reporting `pending` and a roster
computing `absent` for the same seat start disagreeing —
`test_a_newly_added_seat_with_no_guardian_reports_absent` asserts they do not.

It also kept `test_every_public_function_takes_a_lens` green. An earlier attempt
exported the guardian-state predicate publicly and **failed that gate**, which
was the gate working correctly: a public function in that module that takes no
lens cannot be scoped by one. The predicate stayed private and the data crossed
the boundary as a row instead.

---

## The layer boundary, which is what D2 was most at risk on

Every decision the screens need is a **field the mapper owns**, never a
comparison a composable makes:

| Field | The comparison it replaces |
|---|---|
| `isDeclined` | `if (studentState == DECLINED)` |
| `displayLabel` | `if (declined) phone else name`, null when a declined seat has no number; the screen shows a placeholder [BR2.3] |
| `isRemovable` | any derivation from the two link states |
| `RemovalRemedy` | `if (code == "ENROLLMENT_CLAIMED")` |
| `OneChild` / `SeveralChildren` | `if (children.size > 1)` |
| `Empty` / `Loaded` | `if (rows.isEmpty())` |

This is the slip D1 made on `InvitationCard` and corrected. D2 renders four
times as many states, so the same shape would have presented four times as
often. **No `@Composable` in this unit compares a domain value**; the only
conditionals on the screens are `state.retryable`, which the server set, and
exhaustive `when` expressions over sealed types and enums.

The link states **are** rendered, and rendering an enum is not comparing one:
`linkStateLabel` is exhaustive over `LinkState`, so a fifth value fails to
compile rather than rendering under whichever branch was the fallback. The
mapper applies the same rule to the wire tokens — `LinkState.fromWire` returns
null for an unknown value and the mapper turns that into an explicit failure,
matching the convention `STATUS_KEYS` already set.

---

## Testing

Cadence per the affirmed contract: **test-first where the output is knowable
from the requirement and a wrong answer is a money or authorization error**,
test-after elsewhere, written from the acceptance criterion.

### Test-first, and confirmed RED before Phase B

| File | Tests | RED evidence |
|---|---|---|
| `tests/batches/test_accepted_count.py` | 5 | All 5 failed: `'BatchSummary' object has no attribute 'accepted_count'` |
| `tests/batches/test_removal_refusals.py` | 4 | 4 passed against built code — as the plan predicted, since `remove_enrollment` already returns both codes |

**The refusals test was verified load-bearing rather than assumed.** Its point
is not that removal refuses but that the **pair is distinguishable**. Converging
the two message keys in the service failed 2 of its 4 tests. A pair agreeing on
either the code or the key would collapse two remedies into one screen.

### Test-after

| File | Tests |
|---|---|
| `tests/batches/test_roster_states.py` | 9 |
| `RosterStateMapperTest` (extended) | 23 |
| `RosterScreenTest` (extended) | 16 |
| `BatchesStateMapperTest` (new) | 7 |
| `GuardianStateMapperTest` (new) | 8 |
| `GuardianHomeScreenTest` (new) | 4 |
| `AddStudentScreenTest` (new) | 5 |
| `CreateBatchScreenTest` (new) | 5 |
| `RosterViewModelTest`, `BatchesViewModelTest` (updated) | 21 |

### NFR23.6 — the obligation with no other verifier

`BACK AFTER A CHILD SWITCH does not reach the previous child` is the only
mechanism that can observe BR4.2. No server-side control can: both requests are
legitimately authorized, the lens is correct in both, and neither response is
anomalous.

It asserts in **two halves**, and both are needed. After switching, the previous
child is not the one displayed — the switch replaced rather than stacked. After
a real `onBackPressedDispatcher.onBackPressed()`, it still is not — there was no
destination to pop back to. Half 2 alone would pass against a screen that never
switched; half 1 alone would pass against a push, because the pushed screen
covers the old one until Back is pressed.

**Verified non-vacuous**: making `afterChildSelected` stop replacing fails it.

It reads the displayed name through its own test tag rather than by text,
because every child's name is also on its own switcher chip — the first version
of this test failed on that ambiguity, and a differently-written version could
have *passed* on it.

It is named in `tests/named_tests.toml`, which required teaching the manifest
parser to read Kotlin. The parser was Python-AST-only; a manifest that could
only hold Python entries would have quietly dropped the one obligation most at
risk of becoming a review note. The Kotlin reader is a regex over
`@Test fun \`...\``, and a miss fails the check loudly rather than passing it.

### Results

| Suite | Result |
|---|---|
| D2 backend command | **18 passed** |
| D2 Kotlin command | **89 tests, all passed** across 9 classes |
| Full backend suite | **730 passed** (615 at D1's baseline) |
| Full Kotlin suite | **246 passed** (194 before D2) |
| Backend coverage | **91.68%** against the 80% floor |
| Kotlin ratchet | **48.52%**, up from 45.84 |
| `make check` | **All gates passed** |

**Docker was reachable for every run.** D2's backend tests are all integration
tests against a real PostgreSQL container; without Docker the whole suite skips
and still exits zero, so a green run would have meant nothing was checked.
`docker info` was confirmed before the first RED run and the suite reports
passes rather than skips.

**The coverage ratchet rose rather than dropped**, so no glob narrowing was
needed. The floor was raised to 48.52 in the same commit, deliberately — the
ratchet prints the new figure and refuses to raise itself.

---

## Deviations from the approved plan

| Step | Deviation | Why |
|---|---|---|
| 6 | **A fourth response field, `is_removable`** | The plan named three fields while Step 12 required `isRemovable` to be read from the server. Nothing carried it. Deriving it client-side would offer removal on an erased seat [BR3.1, NFR14.31]. Recorded as a deviation because the field count changed, not the intent |
| 11 | `BatchesStateMapper` was **moved, not created** | The dispatch brief said no such object existed. It existed as an `object` inside `BatchesViewModel.kt` — already pure and already the tests' target. It moved to its own file; nothing was rewritten |
| 13 | `EmptyRoster` was **not added** | `RosterUiState.Empty(batchName)` already exists, as the brief's correction noted. Only `ConfirmingRemoval` and `RemovalRefused` were added |
| 23 | The **manifest parser was extended** | `tests/test_named_test_manifest.py` parsed Python only, so the Kotlin Back test could not be named in it. Extending the parser was the smallest change that let the obligation be carried |
| 18 | `RemoveSeatConfirm` holds **two** composables | The plan named one component for the confirmation and its refusals. It is `RemoveSeatConfirm` plus `RemoveSeatRefused` in one file, because a single composable switching on "confirming or refused" would be the state machine the sealed type already expresses |
| 4 | **No fallback needed** | `count(...) FILTER` was syntax-checked against SQLAlchemy 2.1.5 and holds. The named fourth-statement fallback was not used |

---

## Gaps, named rather than hidden

| Item | Status | Where it goes |
|---|---|---|
| The persistent masked-number statement on `G1` (US2.6) | **Not built** | `GuardianHomeScreen` has no access to the signed-in number, which lives in the auth feature. Recorded against US2.6 in `traceability.json`; the record defines no enumerated AC id for it |
| **AC1.3.4a** — a seat detail screen with a number-correction path | Deferred | Not among D2's six screens. The per-link states are on the roster row |
| **AC2.3.1, AC2.3.2** — correcting a display name | Deferred | Needs the same seat-detail screen |
| **AC2.4.2–AC2.4.5** — `inactive_from`'s fee consequence, batch schedule | Deferred | The money half needs a ledger (**D3**); the schedule half is not in D2's screens |
| **AC2.1.3** — schedule fields on the create form | Deferred | Same as AC2.4.4 |
| The six Bangla layout rows | **Open, as rows** | `docs/delivery/bangla-layout-check.md`. Nothing automated discharges this; it is a manual check on a device in Bangla locale |

**`roster_remove_claimed_remedy` at 145 characters is now the longest string in
the whole bundle**, displacing `decline_guardian_body` (125). Re-derived at the
time of writing. It is the first D2 row to check.

### One thing noticed and deliberately not changed

`BatchesScreen`'s header computes `state.rows.sumOf { it.enrollmentCount }` for
its subtitle. That is a client-side tally — of **server-sent numbers**, so it
decides no rule and is not the erosion path BR1.3 names, but it is the shape.
It is pre-existing D1 code and outside D2's steps; changing it would have been
unapproved scope. Recorded here so it is a noticed thing rather than an
overlooked one.

---

## Assumptions

- The guardian switcher is a selection control rather than a navigation stack.
  This is what makes NFR23.6 satisfiable: the screen takes no `NavController`
  and owns no back stack, so there is nothing that *could* push.
- `accepted_count` is carried on `BatchResponse` only. The roster endpoint
  returns rows and no summary, so `HttpRosterRepository` passes null counts
  rather than tallying the rows it holds — a tally there is exactly the
  derivation BR1.3 forbids. `RosterUiState.Loaded.accepted` is therefore
  nullable and the screen renders no count rather than an invented "0 of 0".
- The three new roster fields are **required** on the wire, matching D1's
  precedent (`InvitationDto.decision`). A missing field is a contract failure
  the decoder reports rather than a seat rendered as pending.
