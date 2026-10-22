# Accessibility Checklist — the added screens

**Stage**: refined-mockups (2.5)
**Record**: 261022-remaining-slices

> WCAG 2.1 AA, checked against `O4`, `O5`, `O6` and `T7`'s added column as
> drawn. The prior record covers the other 47 artboards.

## Sources

- [design] the four added artboards on the ShikhokPlus canvas
- [upstream] `inception/user-stories/stories.md` — AC9.4.1, AC9.4.2
- [team] the standing per-Unit obligation: accessibility and back-stack

---

## Contrast

**Computed, not estimated — and the first version of this table was
estimated.** Every figure below is calculated from the WCAG relative-luminance
formula against the exact token values. The first draft of this file carried a
table headed "Measured against the tokens, not estimated" above numbers that
had been guessed; the review caught it. Every verdict happened to be right and
every number was wrong, which is precisely the failure
`project.md`'s rule about a stated number being a claim exists to prevent.

| Pair | Ratio | Verdict |
|---|---|---|
| Ink `#15191F` on white | 17.64:1 | pass |
| Ink muted `#434A55` on white | 8.94:1 | pass, including at 13px |
| Ink muted on surface `#F4F6F9` | 8.26:1 | pass |
| White on primary `#1D4F91` | 8.14:1 | pass |
| `#0B2447` on tint `#D8E3F7` | 11.97:1 | pass |
| White on danger `#A3201A` | 7.56:1 | pass |
| `#6A110C` on danger tint `#FCE3E1` | 10.14:1 | pass |
| `#0F5427` on success tint `#DCF1E2` | 7.65:1 | pass |
| `#2B3440` on `#E4E8EE` — declined chip | 10.24:1 | pass |
| `#5B2E9E` on `#EFE6FB` — verifying chip | 7.46:1 | pass |
| `#663C00` on `#FCE8C3` — the guardian fee warning | 7.90:1 | pass |
| `#0B2447` on `#EEF3FC` — the count strip | 13.89:1 | pass |

No failures. The declined chip was checked specifically because it is the one
new component, and grey-on-grey is where a new chip usually fails.

## Never colour alone — AC9.4.1

| Distinction | Carried by |
|---|---|
| Waiting vs declined, **on T7** | Different text, different icon (clock / cross), different border (solid / dashed). **Not lightness**: the two chip backgrounds `#EFE6FB` and `#E4E8EE` differ by a luminance ratio of 1.018, which is nothing. An earlier version of this row claimed they differed in lightness; they do not, and the distinction rests entirely on text, icon and border. |
| Waiting vs declined, **on O4** | Different cards, not different chips. O4's waiting chip is `c-inv` — solid `#D8E3F7`, no border, no icon — while a declined card carries `c-dec` plus a different action. The row above describes T7's chips and does not apply here. |
| Deleted vs kept, on the deletion screens | A cross icon vs a tick icon, and two separately headed lists — not two colours in one list |
| Accept vs *Not me* | Fill vs outline, and different labels. Not two coloured buttons of the same weight |
| The split-decision row | Stated in words ("Student accepted · guardian declined"), not encoded in a chip |

## Touch targets

| Element | Size |
|---|---|
| Accept / *Not me* | 48dp tall, half-width each |
| *Accept after all* | 48dp |
| Save, Delete, Send code | 56dp |
| Remove, on a declined row | 40dp tall, 14px horizontal padding — **the one element below 44dp** |

**The Remove button is 40dp, which fails WCAG 2.5.5, and that is a finding
rather than an oversight.** It matches the existing `.bt` component used on
`T7`'s Exams tab — verified, it is genuinely 40dp there — so raising it here
alone would make one row inconsistent with the artboard it sits in.

**Owner and unit, because a deferral that names neither is the shape
`project.md` forbids as of 2026-10-22:** `.bt` rises to 44dp across the design
system, and the change lands in **D1**, with D1's Functional Design choosing
between raising the shared component and giving this row a different one.
Raising `.bt` is the likelier answer and affects `T7`'s Exams tab, which is D4
— so doing it in D1 means D4 inherits a corrected component rather than
re-opening the question.

## Labels and semantics

- Every input on `O5` and `O6` has a visible `<label>`, not a placeholder
  standing in for one.
- The role picker on `O1` (existing) uses `role="radiogroup"` with
  `aria-checked`; the invited state marks the two unavailable roles `disabled`
  rather than hiding them, so the lock is perceivable rather than implied by
  absence.
- Icon-only controls carry `aria-label`. Decorative SVG is `aria-hidden`.
- The read-only number field on `O5` is rendered as text with its explanation,
  not as a disabled input — a disabled input is skipped by Tab and the
  explanation would be unreachable.
- The declined row's phone number is the row's accessible name. A screen reader
  announces the number, not a name nobody confirmed.

## Back stack — AC9.4.2

This is a **privacy** case wearing navigation clothing, and acceptance adds a
new way to get it wrong.

| Path | Required behaviour |
|---|---|
| Accept a seat → the new lens becomes available | Back returns to the invitation list, **not** into the newly available lens's stack |
| Decline → sheet → confirmed | Back from the list does not reopen the sheet |
| Lens switch while an invitation is open | The invitation list resolves the **invitation lens** [FR1.9d.1], which is scoped to a seat rather than to the teacher, student or guardian lenses. Switching between those three must not tear it down into the destination lens's history |
| Profile → delete → done | Back from Done never returns to the deleted account's profile |

The third row is the new one, and an earlier version of this file got its
reasoning wrong: it said an invitation is "the only screen in the product that
is not inside a lens". That contradicts [FR1.9d.1], which specifies a distinct
**invitation lens** precisely because every read path is lens-parameterised and
the route-enumeration gate rejects an unlensed route. A pending read does
resolve a lens; it is simply not one of the three the switcher offers.

The navigation requirement is unchanged and is the point: the invitation lens
is scoped to a seat, so hanging the screen off whichever of the three lenses
happens to be active would put it in that lens's back stack and make Back from
it land in another lens's data.

## Bangla

Both bundles must carry every string on these four screens before D1
completes, and each screen needs its row in
`docs/delivery/bangla-layout-check.md` [FR0.2]. Two places were laid out
against their longest Bangla forms during drawing:

- the invitation card's batch name and subject, which wrap rather than
  truncate;
- the deletion screens' two lists, where the Bangla for "attendance, marks and
  fee records your teachers wrote" runs roughly 1.6× the English.

The web route `O6` additionally needs `lang` declared on the page, which an
app screen gets from its framework.

## Open

- **The 40dp Remove button**, above. A design-system decision, not a
  one-screen one.
- **Screen-reader order on the split-decision row.** Two states in one row
  read correctly as a sentence but may need an explicit grouping label; no
  testing has been done and none is claimed.
