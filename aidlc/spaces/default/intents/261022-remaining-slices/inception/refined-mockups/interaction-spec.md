# Interaction Specification — acceptance and deletion

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Record**: 261022-remaining-slices

> Covers only the screens this stage added. The interaction specification for
> `T1`–`T8`, `S1`–`S3`, `G1`–`G3` and `O1`–`O3` is in the prior record and is
> unchanged.

## Sources

- [design] the ShikhokPlus canvas — `O4-Invitations`, `O5-Profile`,
  `O6-WebDelete`, `T7-BatchDetail`
- [upstream] `inception/user-stories/stories.md` — US1.10, US1.13, US1.14,
  US1.15
- [team] the error taxonomy and the layer-boundary rule in `team.md`

---

## O4 · Invitations

| Field | Value |
|---|---|
| Component | Invitation list |
| Description | Where a person accepts or declines a seat a teacher created for their number |
| Category | navigation + feedback |

### States

| State | Description | Trigger |
|---|---|---|
| default | One or more seats awaiting a decision | at least one pending link for this account |
| mixed | Pending seats above previously declined ones | a declined link exists |
| empty | Nothing waiting | no pending and no declined link |
| confirming, student | Decline confirmation sheet open | *Not me* tapped on a student seat |
| confirming, guardian | A different sheet | *Not me* tapped on a guardian seat — see below |
| loading | Fetching the list | screen opened |
| error | List could not load | request failed |

### Interactions

- **Accept** → the seat's matching lens becomes available immediately, the card
  leaves the list, and the batch appears under *My batches* [AC1.10.3]. The
  person is **not** navigated away: a second pending seat must still be
  answerable without finding this screen again.
- **Not me** → opens the confirmation sheet. The sheet is a stop, not a
  formality: declining stops a fee and tells a teacher something, and
  [AC1.14.2]'s ledger reversal is not undone by the un-decline path.
- **Accept after all** (on a declined card) → identical to Accept
  [AC1.13.2]. No extra confirmation; the person is correcting a mistake and a
  second barrier would be the defect this path exists to fix.
- **No decline action on a declined card.** Declining twice is meaningless and
  offering it invites a mis-tap in the recovery flow.

### The decline sheet differs by role, and must

**This is the finding the review caught, and it was a money error rather than
a wording one.** The first version showed one confirmation sheet saying "the
fee stops". That is true for a student and **false for a guardian**:
[AC1.14.1a] states that a guardian's decline leaves fee generation untouched,
because the student owes the fee and a guardian's refusal to oversee the
enrollment does not cancel the student's obligation.

A single sheet therefore told a guardian that declining cancelled a debt it
does not cancel.

| Declining as | What the sheet says about money |
|---|---|
| **Student** | No fee is charged to you. Generation stops and what accrued is voided [AC1.14.1, AC1.14.2]. |
| **Guardian** | **The student's fee is unchanged.** Declining removes your access, not their enrollment [AC1.14.1a]. Shown as a warning callout, not a footnote. |

Both sheets still say the teacher will see the decline, that nothing about the
person is shared, and that the decision is reversible.

### What the server decides

Per [TC-9, D-31], the client renders and does not compute. The server supplies
the seat's state as an enum (`pending` / `declined`), the role label, and the
fee as a **formatted string** [TC-7]. The client never compares an amount or
derives "is this waiting" from the absence of a marker.

### Error behaviour

| Failure | Shown as |
|---|---|
| List request fails | The list is replaced by a retry, never by an empty state. "Nothing waiting" and "could not load" must never be confusable: one means decide nothing, the other means you may have a decision you cannot see. |
| Accept or decline fails | The card stays, with an explicit retry [TC-8, D-9]. No optimistic removal: a card that vanishes and reappears reads as the action having worked and then undone itself. |
| Accept succeeds, lens does not refresh | Treated as success. The lens arrives on the next resolve; nothing is re-submitted. |

---

## O5 · Profile and account deletion

| Field | Value |
|---|---|
| Component | Profile and deletion |
| Description | Edit the private profile; delete the account |
| Category | input + feedback |

### Interactions

- **Both confirmation screens carry the deleted/retained lists** [AC9.4.3].
  An earlier version of this file claimed they appeared on "both artboards"
  while the teacher variant had neither; the review caught it and the artboard
  now carries its own pair, with the teacher's phrased in terms of access to
  31 students' records rather than of their own profile.
- **Name and address** are editable; **the number is not**, and is shown
  read-only with the reason ("this is your login").
- **Delete my account** → the confirmation screen, never a dialog. Two lists
  that a person must be able to read without the surrounding screen competing
  for attention.
- **Confirm by typing the number.** Not a checkbox: the action is irreversible
  and the typed number proves the person is on their own account.
- **Delete** stays disabled until the typed number matches.

### The teacher variant

A teacher's confirmation differs in content, not in shape. It names the batch
count, the student count and the outstanding total, because a teacher deleting
removes their access to other people's records and the numbers are what make
that concrete. The underlying rule is unchanged — [ADR-003] keeps the students'
records — and the screen says which side of that line each thing falls on.

### What the copy must carry

[AC9.4.3] requires the confirmation to name what is deleted and what is
retained. Both artboards show them as **two separate lists with opposite
icons**, not as a paragraph: a person scanning before an irreversible action
reads lists and skips prose.

---

## O6 · Delete account from the web

| Field | Value |
|---|---|
| Component | External deletion route |
| Description | Deletion without the app installed [FR1.15, TC-19] |
| Category | input + feedback |

### Interactions

- **Two steps, always.** Number, then a code. A single-step form on a public
  URL would let anyone delete an account by typing a number.
- **The code step looks identical whether or not the number has an account**,
  and says so: "If this number has an account, a code is on its way." This is
  the same non-disclosure rule the OTP path follows [BR2.7], and it is the
  reason this screen needed drawing rather than describing.
- **Rate limited per number and per IP**, as signup is [FR1.7d]. A public
  deletion endpoint is an abuse surface in its own right.

### Accessibility note specific to this surface

It is a web page, not a Compose screen, so it carries the obligations the app
gets from its framework for free: a declared page language, a visible focus
indicator, labels on both inputs, and a form that works without JavaScript for
the submit step.

---

## T7 · Single batch — the acceptance column

### Interactions added

- **The count strip** is not interactive. It replaces per-row pending marks
  [AC1.3.3a] and tapping it would imply a filtered view that does not exist.
- **A declined row** shows the number, the date, and a **Remove** action
  [AC2.5.1a]. Remove is permitted here precisely because nobody accepted the
  seat, so nothing is destroyed.
- **Remove asks for confirmation**, naming the number. The commonest reason to
  remove is a mistyped digit, and the commonest error in fixing it is removing
  the wrong row.
- **A split-decision row** states both links plainly ("Student accepted ·
  guardian declined"). No icon for it: two independent states on one row cannot
  be carried by a single chip without inventing a vocabulary for every
  combination.

### What the teacher cannot do

- **Clear or reverse a decline** [AC1.13.3]. No action offers it, and the
  explanation beside a declined row says what the remedy is: check the number,
  remove the seat, add the right one.
- **See why** a seat was declined. The roster shows the fact, not a reason;
  nothing in V1 collects one.

---

## Cross-cutting

### Touch targets and spacing

Every action on these screens is at least 44×44dp **except one**: the Remove
button on T7's declined row is 40dp, matching the existing `.bt` component.
That is a WCAG 2.5.5 failure, it is owned by D1, and
`accessibility-checklist.md` carries the decision. An earlier version of this
file flatly asserted the 44dp minimum held everywhere, which contradicted the
checklist — and whoever builds T7 reads one file, not both.

The Accept and *Not me* buttons are 48dp tall and split the width evenly,
which keeps both reachable one-handed and avoids making the destructive one
smaller: a smaller decline would bias a decision that must not be biased.

### Bangla

Every string on all four artboards is externalised, and both the invitation
card and the deletion lists were laid out against their longest Bangla forms.
The card's fee row and the batch name are the two places where a long Bangla
subject name pushes the layout, and both wrap rather than truncate. Each screen
needs its row in `docs/delivery/bangla-layout-check.md` before D1 completes
[FR0.2].

### Motion

None specified. The product has no motion language and inventing one here,
three units before the screens are built, would be a decision made in the
wrong place.
