# Interaction Specification — ShikhokPlus

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Date**: 2026-10-17

Component-level specification for the Android surfaces. The framework's
component template assumes the web (props, breakpoints, hover, ARIA); the
Android equivalents are used and the substitution is stated in
`design-system-mapping.md` §4.

---

## 1. Payment status chip

| Field | Value |
|---|---|
| Component | `PaymentStatusChip` |
| Description | Conveys a fee cycle's state with four redundant cues |
| Category | display |

### States

Five, from the design's `Colour tokens` artboard. **Colour is never the only
differentiator** [AC9.4.1].

| State | Fill | Icon | Words | Number or date |
|---|---|---|---|---|
| `Paid` | Tonal | Tick in a circle | "Paid" | — |
| `Partial` | Tonal | Half-filled circle | "Partial" | **Always** the remainder: "৳400 left" |
| `Due` | None, solid outline | Empty circle | "Due" | **Always** the date: "Due 10 Nov" |
| `Overdue` | **Solid — the only solid fill in the app** | Triangle | "Overdue", bold | **Always** the day count: "Overdue 23 days" |
| `Verifying` | Dashed outline | Clock | "Verifying" | — |

### Inputs

| Input | Type | Required | Notes |
|---|---|---|---|
| `status` | enum of the five above | yes | **Server-supplied** — the client never derives it from a balance comparison [TC-9] |
| `remainder` | `Money?` | when Partial | |
| `dueDate` | `LocalDate?` | when Due | |
| `daysLate` | `Int?` | when Overdue | |

### Accessibility

`stateDescription` carries the state word. `contentDescription` on the icon is
null — the icon is decorative because the word is present. Contrast 7.5:1
minimum in both themes per the design's measurements.

---

## 2. Money text

| Field | Value |
|---|---|
| Component | `MoneyText` |
| Description | The only way a money value reaches the screen |
| Category | display |

- Always **Latin numerals**, regardless of locale [AC9.3.1]
- `৳` prefix; the glyph requires the Bangla font, so the composable must not
  fall back to a Latin-only face
- Decoded from a JSON **string**, never a number [NFR9]
- Thousands grouping follows the **South Asian convention** — ৳1,25,400, not
  ৳125,400 — which the design shows explicitly
- `display` type slot (34/52/700) for totals; `body` inline

---

## 3. Attendance roster

| Field | Value |
|---|---|
| Component | `AttendanceRoster` |
| Description | The mid-class path. Its speed is structural, not measured |
| Category | input |

### Behaviour

- **Every student defaults to present** [AC3.1.4]; the teacher marks exceptions
- Tap a row to toggle present/absent
- **Search field** for large batches [Q3]
- **Mark all absent** action [Q3]
- Submit writes the **whole roster in one atomic operation** [AC3.1.5] — never
  one write per student
- Confirmation names present and absent counts before committing [AC3.1.6]
- Reopening a recorded session allows correction [AC3.1.7]

### States

| State | Treatment |
|---|---|
| `default` | Rows at 56dp, all present |
| `submitting` | Action disabled, progress inline |
| `queued` | **"Saved on phone · not sent"** — distinct from both confirmed and failed [AC3.1.10] |
| `synced` | Confirmed |
| `failed` | Non-modal prompt, marks stay on screen [AC3.1.3] |

**No elapsed-time criterion applies** [AC3.1.8]. The speed requirement was
dropped; default-present and the single atomic write stand in its place.

---

## 4. Money action button

| Field | Value |
|---|---|
| Component | `MoneyActionButton` |
| Description | Any action that moves or commits money |
| Category | action |

- **56dp tall, full width** — above the 48dp touch floor, deliberately
- **32dp of space above it** — the design's "above a money decision" spacing step
- Used by: Approve, Partial, Reject [T4]; Send for checking [S3]; Pay [G1, G3]
- Disabled until the form is valid; never disabled *during* submission without
  a visible progress state

---

## 5. Child switcher

| Field | Value |
|---|---|
| Component | `ChildSwitcher` |
| Description | Guardian's child selection |
| Category | navigation |

- Avatar chips at the top of the guardian surface
- **Skipped entirely when one child is reachable** [AC2.7.2]
- Each entry shows the child's name **and the recording teacher** [AC2.7.3]
- **The selected child's name is repeated in every card title below it** — the
  design's structural answer to wrong-child risk
- Switching does not re-authenticate [AC2.7.4], and the back stack must not
  carry the previous child's screens [AC9.4.2]

---

## 6. Transaction ID field

| Field | Value |
|---|---|
| Component | `TransactionIdField` |
| Description | bKash, Nagad or Rocket reference entry |
| Category | input |

- **IBM Plex Mono 500** — the only mono in the app, because these codes mix
  0/O and 1/I/l and Plex Mono's zero carries an inner mark
- **Upper-cased, spaces removed on entry** [AC9.3.6]
- Bengali digits accepted and normalised [AC9.3.5]
- Helper text: *"Paste it from the bKash or Nagad SMS"*

---

## 7. Phone number field

- Fixed `+88` prefix, 11 digits
- Bengali digits accepted and normalised [AC9.3.5]
- **Never read from the SIM** [NFR11] — always typed
- Live lookup on the add-student form, with three outcomes: not found ("New
  number. They'll get an SMS invite."), found, or invalid with a plain-words
  message naming the actual problem

---

## 8. Empty, loading and error — the three distinct states

Required of every list and form [AC9.2.5]. The design's treatments:

| State | Rule |
|---|---|
| `loading` | **Static skeleton at the real row heights** so nothing jumps |
| `empty` | Explains the next action, never just "no data". Teacher: a numbered setup. Student: "Give them this number: …" |
| `error` | **Never rendered as empty** [AC9.2.5] — an empty dues view would tell a teacher nobody owes him money |

---

## 9. Write failure and queue behaviour

| Path | Behaviour |
|---|---|
| Mid-class (topic, attendance) | **Queues locally**, syncs on reconnect, survives app restart, shown as not-yet-sent [NFR5, NFR5.1] |
| Every other write | Requires connectivity; fails with input preserved on screen [AC9.2.1] |
| All writes | `retryable` comes **from the server**, never inferred from an HTTP status [AC9.2.3] |
| All writes | Double submission creates one record [AC9.2.4] |

---

## 10. Navigation and back stack

- Bottom bar, four teacher items: Today · Batches · Dues · More [Q4]
- Lens chooser full-screen on first launch; top-bar control thereafter [Q5]
- **Back after a lens or child switch must not reach the other lens's or
  child's data** [AC9.4.2] — a privacy rule wearing navigation clothing
- Single-activity Navigation Compose, per the approved architecture

---

## Assumptions & Open Questions

- The design draws no pressed, focused or disabled variants for most
  components; they are inferred from Material 3 defaults. [assumption]
- `MoneyText`'s South Asian grouping (৳1,25,400) is read from the design's
  examples, not from a stated rule, and the requirements say only "fixed-point
  decimal in BDT". Worth confirming at implementation. [assumption]
- The reminder-SMS flow [T5] has no interaction spec here because it is
  recommended for deferral. [assumption]
- No motion or transition specification exists in the design beyond a `Motion`
  heading in `Spacing and components` whose content did not survive export.
  [assumption]

## Sources

- [design] The user's design canvas, 21 artboards.
- [Q1]–[Q11] `refined-mockups-questions.md`.
- [AC*], [US*] `inception/user-stories/stories.md`.
- [FR*], [NFR*], [TC-9] `inception/requirements-analysis/requirements.md` and
  `ideation/feasibility/constraint-register.md`.
