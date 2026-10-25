# Design System Mapping — the added screens

**Stage**: refined-mockups (2.5)
**Record**: 261022-remaining-slices

> The design system is unchanged. This records which existing tokens and
> components the four added artboards use, and the one new chip they need.

## Sources

- [design] the canvas — `Colour`, `Components`, `Main` (type pairing),
  `TypeScale`, `Numerals`
- [code] `android/src/main/kotlin/com/shikkhokplus/app/core/designsystem/`

---

## Nothing new was invented

Every colour, type size, radius and spacing value on `O4`, `O5`, `O6` and
`T7`'s added column is taken from the existing system. The artboards were
written against the tokens already in `Colour.dc.html` and already built in
Kotlin under `core/designsystem/`.

| Token | Value | Used for |
|---|---|---|
| Primary | `#1D4F91` | Accept, Save, the count strip's icon and border |
| Primary tint | `#D8E3F7` / `#EEF3FC` | The waiting chip, the count strip, the invited callout |
| Primary dark | `#0B2447` | Text on primary tint |
| Danger | `#A3201A` | Delete, the decline confirmation's primary action |
| Danger tint | `#FCE3E1` | The number-taken error, the web route's warning |
| Success | `#0F5427` / `#DCF1E2` | Paid chip, the kept-records tick, the done state |
| Ink | `#15191F` | Body text |
| Ink muted | `#434A55` | Secondary text, help text |
| Hairline | `#E4E8EE` / `#C9CED6` | Row dividers, input borders |
| Surface | `#FFFFFF` on `#F4F6F9` | Cards on screen |

Type is the existing pairing — Noto Sans with Noto Sans Bengali — at the
existing scale: 21/34 screen title, 16/26 row title, 14/22 body, 13/20
secondary.

## One addition: the declined chip

| Chip | Existing? | Style |
|---|---|---|
| `c-paid` | yes | solid green |
| `c-part` | yes | solid amber |
| `c-due` | yes | outlined |
| `c-over` | yes | solid red |
| `c-pend` | yes | dashed purple — **payment** verifying |
| **`c-decl`** | **new** | dashed grey |

`c-decl` is new because no existing chip means "a person refused this".
Deliberately **grey and dashed**, not red: a decline is not an error and most
often means a wrong number. Red would read as a problem with the student.

It is dashed to match `c-pend`'s "not settled yet" sense while differing in
hue and lightness, so the two are distinguishable without colour alone
[AC9.4.1]. `c-pend` means a payment is being checked; `c-decl` means a seat
was refused. They never appear in the same column.

## Components reused unchanged

| Component | From | Used on |
|---|---|---|
| Phone frame, 360×760 | every screen artboard | O4, O5 |
| Browser frame | **new**, O6 only | O6 — the one non-app surface |
| App bar with title and subtitle | `S1`, `T7` | O4, O5 |
| Card, 12px radius on `#FFFFFF` | `S1` | O4, O5 |
| Two-column key/value under a hairline | `S1` | O4's subject and fee |
| Full-width primary button, 56dp, 28px radius | `S1`, `O1` | O5, O6 |
| Outlined button, 48dp | `S1` | the un-decline action |
| Bottom sheet over a dimmed list | `T2` | O4's decline confirmation |
| Skeleton blocks | `S1`, `T7` | O4 loading |

The browser frame is the only new container, and it exists because the
external deletion route is a web page. Drawing it in a phone frame would
misrepresent what it is.

## What the Kotlin side already has

`Color.kt`, `Spacing.kt`, `Type.kt`, `Theme.kt`, `Surfaces.kt`, `OtpField.kt`,
`PaymentStateChip.kt` and `PaymentStateIcon.kt` are built. D1 adds:

- a **seat-state chip** alongside `PaymentStateChip` — same shape, different
  vocabulary (pending / accepted / declined rather than paid / due / partial).
  A separate component, not a widened enum: the two are different domains and
  conflating them is how a payment state ends up rendered on an invitation.
- an **invitation card**, which is the existing card plus the two-column
  key/value and an action row.

Neither needs a new token.
