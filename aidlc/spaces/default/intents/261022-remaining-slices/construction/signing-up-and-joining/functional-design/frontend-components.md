# Frontend Components — D1 `signing-up-and-joining`

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: D1 `signing-up-and-joining`
**Record**: 261022-remaining-slices

> **Technology-agnostic by stage contract**, but not convention-agnostic: the
> affirmed practice is conventional, well-documented Google choices, feature
> packages with a layer split inside each, and a ViewModel that maps a server
> response to a UI state class. The shapes below are stated in those terms
> because departing from them would itself be a design decision.

## Sources

- [upstream] `inception/refined-mockups/mockups.md` — O1, O4, O5 and states
- [upstream] `inception/refined-mockups/interaction-spec.md`
- [upstream] `inception/refined-mockups/accessibility-checklist.md`
- [upstream] `inception/units-generation/unit-of-work.md` — D1's screens
- [this stage] `functional-spec.md` §2 and §7, `rules.md`

---

## The one rule that governs every component here

**A composable receives a UI state and renders it, with no conditional that
depends on a domain value** [team: Code Style]. The checkable form is: *if the
client is comparing a domain value, the server should have sent a decision.*

This unit has a live instance of that trap. The invitation card must show a
state — waiting, declined-but-reclaimable — and the wrong design is a
composable reading `decision == "declined"`. The server sends the **state the
card is in**, and the card renders it. The decision enum is the server's input
to that choice, not the client's.

A second instance: the guardian decline sheet differs from the student one
[AC1.14.1a]. The client does not decide which to show by inspecting which
link it holds; the invitation's UI state names which confirmation applies.

---

## Feature packages

```
feature/signup/        O1 — create account
feature/invitations/   O4 — accept or decline
feature/profile/       O5 profile half (the deletion half is D6's)
core/model/            shared types; Money lives here already
core/network/          the API client
core/designsystem/     tokens and shared composables
```

`O2` (OTP entry) and `O3` (role landing) are built and are not re-opened by
this unit [BR2.2 requires `O2`'s behaviour unchanged].

**One Gradle module**, packages inside it, as the affirmed practice sets.

> **A note the practice file earns:** `BatchesViewModel` currently imports
> `AuthResult` from `feature.auth` — a cross-feature import of a result type
> that belongs in `core`. D1 adds three features that all need a shared
> result shape. The type belongs in `core/model` before it is imported a
> fourth time; moving it is in scope for this unit's first commit.

---

## O1 · Signup

### UI state

```yaml
SignupUiState:
  variant: Empty | PreFilled | Submitting | NumberTaken | Error
  phone_field: { value, enabled, error_key }
  name_field: { value, enabled, correctable, error_key }
  role_field: { value, locked, options }
  address_field: { value, error_key }
  already_added_notice: string_key | null
  submit: { enabled, label_key, destination_number }
  error_key: string_key | null
```

**`role_field.locked` and `name_field.correctable` are server-derived.** They
come from the already-added lookup, not from the client noticing that a name
arrived [BR4.5].

**`already_added_notice`** is a message key, never a server-sent sentence. It
says a teacher has added this number and names neither teacher nor batch
[BR2.3] — the component could not name them if it wanted to, because the
response does not carry them.

**`submit.destination_number`** exists because [BR4.3] requires the control to
name the number the code will go to. A label assembled client-side from the
field would drift from what the server will actually text.

### Components

| Component | Receives | Notes |
|---|---|---|
| `SignupScreen` | `SignupUiState`, callbacks | Owns no logic; routes on `variant` |
| `PhoneField` | value, enabled, error key | Format-only client validation [team: Code Style] |
| `NameField` | value, correctable flag | Disabled-looking but editable when pre-filled |
| `RoleSelector` | value, locked, options | When locked, renders the role as a fact, not a disabled picker — a disabled control invites tapping |
| `AddressField` | value, error key | Optional; nullable on the server |
| `AlreadyAddedNotice` | message key | Rendered only when present |
| `SubmitButton` | enabled, label key, number | Label includes the destination number |

### Validation

Client-side validation is **format-only, never policy** [team: Code Style].
The client may check that a number looks like a number. It does **not** check
whether the number already has an account — that is [BR4.4], a server
uniqueness answer, and duplicating it client-side is how the two diverge.

### Interaction flow

1. Number typed → debounce → lookup call.
2. Lookup returns → state becomes `Empty` or `PreFilled`.
3. Submit → `Submitting`; the button is disabled and the form is locked.
4. Success → navigate to `O2`, which is unchanged.
5. Number taken → `NumberTaken`, with the log-in route offered.
6. Any failure → `Error`, with the server's `message_key` and its
   server-provided `retryable` flag. The client never decides retryability.

---

## O4 · Invitations

The screen that did not exist, for the decision that did not exist. Seven
states, and the state list is load-bearing: *nothing waiting* and *could not
load* must never be confusable, because one means decide nothing and the other
means you may have a decision you cannot see.

### UI state

```yaml
InvitationsUiState:
  variant: Loading | Empty | Error | Loaded
  items: [InvitationCardState]      # when Loaded
  error_key: string_key | null

InvitationCardState:
  enrollment_id: id
  batch_name: string                # teacher-authored, rendered as data
  subject: string
  fee: Money                        # decoded from a JSON string, always
  role_label_key: string_key        # which link this is
  card_state: Waiting | Declined
  primary_action: Accept | AcceptAfterAll
  secondary_action: NotMe | null
  decline_confirmation: Student | Guardian | null
```

**`card_state` is sent, not computed.** This is the rule at the top of the
file, applied to the place it would most easily be broken.

**`decline_confirmation`** names which sheet applies. A guardian's decline
does not stop the student's fee, so the guardian sheet carries that warning
and the student sheet does not [AC1.14.1a]. One confirmation for both was the
defect review caught in the mockups; the component contract is where it stays
fixed.

**`fee` is `Money`** — the value class whose serializer reads only a JSON
string and rejects a JSON number. The fee is shown because a guardian is being
asked to take on a financial obligation and hiding the amount would make the
decision uninformed [FR1.9d].

**Three fields and no more.** The card holds batch name, subject and fee
[BR1.4]. There is no field for attendance, marks, the teacher or any other
enrollment, so there is nothing for a future edit to accidentally render.

### Components

| Component | Receives | Notes |
|---|---|---|
| `InvitationsScreen` | `InvitationsUiState` | Routes on `variant`; four distinct bodies |
| `InvitationCard` | `InvitationCardState` | Renders `card_state`; no domain comparison |
| `InvitationEmptyState` | — | "Nothing waiting", and where accepted batches live |
| `InvitationErrorState` | error key, retry | Says explicitly this is not the same as having none |
| `InvitationSkeleton` | — | Matches the card shape |
| `DeclineSheet` | variant, batch name | Two variants; the guardian one carries the fee-unchanged callout |

### Actions

- **Accept** → optimistic nothing. The write goes to the server, the list
  reloads, and the lens picker's counts change with it [BR1.2]. There is **no
  offline write queue** in V1 [TC-8]: a failed write surfaces an explicit
  retry prompt rather than queueing silently.
- **Not me** → opens `DeclineSheet`. The label is deliberate: the commonest
  cause of a pending seat is a mistyped number, and the commonest person
  seeing this screen wrongly is a stranger. "Not me" is what that person
  means.
- **Accept after all** → the same accept call on a declined card [BR5.4].

---

## O5 · Profile (the edit half)

**Deletion is D6's.** D1 ships the profile-edit states; the two deletion
confirmations and the done screen land with the deletion paths.

### UI state

```yaml
ProfileUiState:
  variant: Viewing | Editing | Saving | Saved | Error
  self_name: { value, error_key }
  phone: string            # read-only, marked as the login
  address: { value, error_key }
  helper_text_key: string_key
  error_key: string_key | null
```

**`helper_text_key`** carries [FR1.12]'s line: your teachers keep seeing the
name they typed. It is the only place a person learns that the two names are
different things, and [AC1.5.3] makes it required rather than advisory.

### Components

| Component | Receives | Notes |
|---|---|---|
| `ProfileScreen` | `ProfileUiState` | |
| `ReadOnlyPhoneRow` | phone | Marked as the login; not editable here |
| `ProfileHelperText` | message key | Required by AC1.5.3 |

---

## Cross-cutting obligations

**Strings.** No hard-coded user-facing string. Bangla and English present from
the first screen, both bundles complete [TC-15]. Three new screens' worth of
keys land in both.

**Bangla layout.** Every screen D1 ships needs a row in
`docs/delivery/bangla-layout-check.md` before the unit completes — a screen
with no row means an incomplete unit [FR0.2]. The verifier is the named manual
per-screen check; the practice is explicit that an unverifiable obligation is
a wish.

**Money.** Any money-carrying model class ships a serialization test proving
decode from a JSON string and **loud failure** on a JSON number. The
invitation card carries a fee, so `InvitationCardState` is in scope for that
test.

**ViewModel tests.** Each of the three features ships tests for its state
machine — loading, success, error, and the explicit retry path for a failed
write [TC-8, D-9] — targeting the response-to-UiState **mapping function**
rather than an untargeted ViewModel.

**Colour independence.** A card's state is never carried by colour alone
[AC9.4.1]: the waiting and declined cards differ in text, icon and border, not
in a fill whose luminance ratio is 1.018.

**Forbidden identifiers.** Nothing added here reads a device or advertising
identifier, and nothing reads the phone number from the device — the number is
always typed [TC-4]. The manifest allowlist and DEX scan enforce it at release;
the commit-time half is the toolchain work landing before this unit.

---

## Assumptions & Open Questions

- **Assumed**: the invitations list is its own route rather than a section of
  the home screen, matching the mockups. Either satisfies the rules.
- **Open**: whether `O4` is reachable from the lens switcher. The mockups
  record it as open. The invitation lens is **not** one of the three a person
  chooses between [ADR-011], so the switcher is the wrong home for it; the
  mockups' own answer is a home-screen entry point. Recorded rather than
  settled, because it is a navigation choice with no rule behind it.
- **Assumed**: `AuthResult` moves from `feature/auth` to `core/model` in this
  unit's first commit. It is the smallest moment the move is still trivial.
