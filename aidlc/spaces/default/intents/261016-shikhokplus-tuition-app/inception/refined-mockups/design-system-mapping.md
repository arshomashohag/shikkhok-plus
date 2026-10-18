# Design System Mapping — ShikhokPlus

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Date**: 2026-10-17
**Source**: the user's design canvas, exported to `claude_design/` and extracted
from its bundled artboards. Every token below is **read from that file**, not
invented here.

Maps the design to Jetpack Compose Material 3. Where the framework's design
knowledge assumes the web (breakpoints, hover, ARIA), the Android equivalent is
given and the difference stated.

---

## 1. Colour

The design's stated principle: *"One blue for actions. Everything else is ink,
until money is involved."* Contrast ratios below are the design's own measured
values, light · dark.

### Material 3 colour roles

| M3 role | Light | Dark | Contrast | Note |
|---|---|---|---|---|
| `primary` | `#1D4F91` | `#A9C7FF` | 8.1 · 10.3 | The only action colour |
| `primaryContainer` | `#D8E3F7` | `#1E3F6E` | — | |
| `onPrimaryContainer` | `#0B2447` | `#D8E3F7` | — | |
| `secondary` | `#4A5668` | `#B9C4D6` | — | Neutral slate, never decorative |
| `error` | `#A3201A` | `#FFB4AB` | — | Form errors only |
| `background` | `#F4F6F9` | `#0F1215` | — | |
| `surface` | `#FFFFFF` | `#15191E` | — | |
| `surfaceContainer` | `#EEF1F5` | `#1C2128` | — | |
| `surfaceContainerHigh` | `#E4E8EE` | `#252B33` | — | |
| `onSurface` | `#15191F` | `#E6E9EE` | 17.6 · 14.5 | |
| `onSurfaceVariant` | `#434A55` | `#B5BCC7` | 8.9 · 9.2 | |
| `outline` | `#6E7682` | `#8A929E` | 4.6 · 5.6 | **Borders and icons only, never text** |
| `outlineVariant` | `#C9CED6` | `#343B45` | — | Dividers only |

These map to a Compose `ColorScheme` directly — `lightColorScheme(...)` and
`darkColorScheme(...)` with these values. **Dynamic colour is off**: the
palette is fixed, so `dynamicColor = false`.

**Dark theme is in scope.** No upstream requirement mentions it; the design
specifies both themes throughout, so the app ships both.

### Contrast policy

The design states: *"every text token here is 7:1 or higher (AAA) in both
themes, including all five state labels"*, with `outline` at 4.6:1 reserved for
borders and icons and never carrying text.

That **exceeds the WCAG 2.2 AA commitment** made at Q8, and exceeds it on all
three surfaces rather than only the teacher's. Recorded as an upgrade the
design delivers for free, not a new obligation.

### Payment states — four redundant cues each

This is how the design satisfies the colour-independence rule [AC9.4.1], and it
goes well past "add an icon".

| State | Cues besides colour | Contrast L · D |
|---|---|---|
| Paid | Tonal fill · tick in a circle | 7.6 · 8.7 |
| Partially paid | Tonal fill · half-filled circle · **always shows the remainder** ("৳400 left") | 7.9 · 8.4 |
| Due | No fill, solid outline · empty circle · **always shows the due date** | 12.6 · 12.8 |
| Overdue | **The only solid fill in the app** · triangle · bold · **day count** | 7.6 · 7.8 |
| Pending verification | Dashed outline (not yet confirmed) · clock | 7.5 · 9.0 |

Each state carries fill style, icon shape, words, and for three of them a number
or date. The design includes a greyscale test artboard proving the states remain
distinguishable with colour removed entirely.

**Loud colour is used for exactly two things**: the overdue chip, and a solid
banner when a class is cancelled or moved.

---

## 2. Typography

### The scale

sp, size / line height / weight. Compose `Typography` slots in brackets.

| Design name | Spec | Used for | M3 slot |
|---|---|---|---|
| display | 34 / 52 · 700 | Money totals | `displaySmall` |
| headline | 26 / 40 · 700 | Screen title, guardian | `headlineSmall` |
| title | 21 / 34 · 600 | Card and section titles | `titleLarge` |
| **reading** | 18 / 30 · 400–600 | **Guardian body, list primary** | `bodyLarge` |
| body | 16 / 26 · 400–600 | Teacher and student body | `bodyMedium` |
| label | 14 / 22 · 600 | Chips, buttons, headers | `labelLarge` |
| caption | 13 / 20 · 500 | **Floor. Nothing smaller.** | `labelSmall` |

**The guardian step** is a deliberate design decision worth preserving: the
guardian surface uses `reading` (18sp) where the teacher surface uses `body`
(16sp), in the same row layout, with no user setting involved. It follows from
the persona — the guardian has lower tech comfort and reads less often.

### Fonts

**Noto Sans + Noto Sans Bengali**, bundled as woff2 rather than Google-hosted.
The design compared three pairings and recorded why: *"Matra sits just above
Latin x-height; stroke weight matches at every step. Same family spec across
scripts."* Hind Siliguri and Anek Bangla were the rejected candidates.

**IBM Plex Mono 500 for transaction IDs only.** The design's reason: bKash and
Nagad IDs mix 0/O and 1/I/l, and Plex Mono's zero carries an inner mark.
*Nothing else in the app uses mono.*

### The Bangla line-height problem, and its fix

The design demonstrates it: at 18sp with the Latin default 1.2× line height,
Bangla text **clips** — the matra above and the descender below are cut. Four
sample names are shown clipped. At the design's 1.67× step they render cleanly.

Compose specifics the design names, which carry straight into implementation:

- `includeFontPadding = false` is **not** enough on its own
- set `fallbackLineSpacing` on
- set an explicit `lineHeight` per style, not a multiplier
- use `LineHeightStyle(alignment = Center, trim = Trim.None)`
- **never** put Bangla text in a fixed-height box that can clip

This is the concrete verifier the stories asked for and did not have [AC9.3.3].

---

## 3. Spacing, shape and reach

| Scale | Value | Used for |
|---|---|---|
| 4dp | icon to label | |
| 8dp | inside chips, between lines | |
| 12dp | between list items in a card | |
| 16dp | screen margin, card padding | |
| 24dp | between sections | |
| 32dp | **above a money decision** | deliberate separation before an irreversible action |

**Touch targets**: 48dp minimum. **Every button that moves money is 56dp tall
and full width** — above the 48dp floor, deliberately.

**Row heights**: single line 56 · two lines 72 · marks entry 64 · read-only
marksheet 48.

**Corner radius**: fields 8 · cards 12 · chips and sheets 16 · FAB 16. Maps to
Compose `Shapes(small = 8.dp, medium = 12.dp, large = 16.dp)`.

---

## 4. Web-to-Android translation

Where the framework's design knowledge assumes a browser:

| Web concept | Android equivalent here | Note |
|---|---|---|
| CSS breakpoints | `WindowSizeClass` — Compact, Medium, Expanded | Q9: phone portrait and landscape, plus a teacher tablet layout |
| `:hover` | pressed, focused, dragged via `InteractionSource` | No hover on touch; hover states are not designed |
| ARIA roles | `Modifier.semantics` with `role`, `contentDescription`, `stateDescription` | TalkBack, not a screen-reader-on-DOM model |
| `aria-label` on icon buttons | `contentDescription` | Required on every icon-only control |
| Focus ring | Compose focus indication | Keyboard and switch-access navigation |
| `prefers-color-scheme` | `isSystemInDarkTheme()` | Both themes exist in the design |
| Responsive units (rem, %) | `dp` and `sp` | `sp` for text so system font scaling works |

The design is drawn at **360 × 760dp** — the stated thumb-zone reference — which
is a small phone, so layouts derived from it scale up rather than needing to
compress.

---

## 5. Component inventory

Drawn from the `Spacing and components` artboard and the 14 screen artboards.

| Component | States shown | Notes |
|---|---|---|
| Payment status chip | 5 (paid, partial, due, overdue, verifying) | Four cues each; see §1 |
| Money amount | default, large (display) | Latin numerals always; ৳ needs the Bangla font |
| Student row | single, two-line, with avatar initial | 56 / 72dp |
| Marks entry row | default, focused, filled | 64dp |
| Marksheet row | default, own-row | 48dp, read-only |
| Batch card | default, inactive | |
| Child switcher | collapsed, expanded | Selected child's name repeated in every card title below |
| Bottom navigation | 4 teacher items (Today, Batches, Dues, More) | Q4 |
| FAB | default | 16dp radius |
| Money button | default, pressed, disabled | 56dp, full width |
| Offline banner | — | *See the note below* |
| Empty state | per screen | "No batches yet — Create a batch, then add students by phone number. They sign in with that number." |
| Loading skeleton | — | **Same row heights as the real list**, so nothing jumps |
| Error state | "saved, but not sent" | |

---

## 6. Where the design and the approved artifacts disagreed

Three conflicts, all resolved at Q11 and recorded here so the design file is not
silently treated as authoritative.

| Conflict | Resolution |
|---|---|
| **Marksheet.** The design shows a fully named, ranked marksheet (19 students, own row tinted `#D8E3F7`, absent listed but unranked). The stories specify anonymised rank-and-bands. | **The stories stand** [Q11.1]. The design's `Marksheet light` and `Marksheet dark` artboards are superseded **on this screen only**. Every other artboard stands. |
| **Offline writes.** The design shows "Saved on phone · not sent — will retry on its own" and an offline banner. NFR5 forbade any write queue. | **The design stands** [Q11.2]. NFR5 and FR3.6 were amended: the mid-class path (topic log, attendance) queues locally and syncs. Every other write still requires connectivity. |
| **Numerals.** The design's rule is broader than AC9.3.1. | **The design stands** [Q11.3]. AC9.3.1 was widened and AC9.3.4–AC9.3.6 added. |

---

## Assumptions & Open Questions

- The exported artboards are a **point-in-time copy**. If the canvas is edited,
  this mapping goes stale with no mechanism to notice. The canvas could not be
  read directly — it is in a different organization from this session — so
  re-export is the only refresh path. [assumption]
- Contrast ratios are **the design's own measured figures**, reproduced not
  re-verified. They should be re-checked against the implemented theme, since a
  Compose `ColorScheme` can apply a token in a role the design did not intend.
  [assumption]
- The design states AAA (7:1) for text while Q8 committed to AA. The AAA figures
  are recorded as delivered; **the commitment remains AA on the teacher surface**
  so the obligation does not silently inflate. [Q8] [assumption]
- `MarksheetLight` and `MarksheetDark` are superseded, so the anonymised
  rank-and-bands treatment **has no artboard**. It is specified in
  `mockups.md` from the stories instead, and is the one screen in the product
  with no visual design. [Q11.1] [assumption]
- The offline queue reverses a decision held since Intent Capture, and the
  approved architecture has no sync surface. Domain Design inherits the
  conflict question: what happens when a queued attendance write arrives after
  the same session was edited elsewhere [FR11.4]. [Q11.2] [assumption]
- Bundled fonts carry an APK cost against NFR2's 15 MB budget. Noto Sans
  Bengali is the largest single asset in the design's manifest (143 KB woff2,
  larger as TTF). Not yet measured against the budget. [NFR2] [assumption]
- The design shows a `More` bottom-nav item whose contents are not specified in
  any artboard. [Q4] [assumption]

## Sources

- [design] The user's design canvas, exported to `claude_design/design_system.html`,
  `teachers_screen.html`, `students.html`, `guardians.html`, `first_draft.html`
  and extracted from their bundled artboards. 21 artboards total.
- [Q1]–[Q11] Confirmed answers in `refined-mockups-questions.md`.
- [FR*], [NFR*] `inception/requirements-analysis/requirements.md`.
- [AC*], [US*] `inception/user-stories/stories.md`.
- [team: *] `aidlc/spaces/default/memory/team.md`.
