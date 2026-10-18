# Accessibility Checklist — ShikhokPlus

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Date**: 2026-10-17

**Commitment**: WCAG 2.2 Level AA, **teacher surface**, verified per screen
[Q8]. Student and guardian surfaces are read-mostly and carry the Play
pre-launch report plus the three story-level cases.

**What the design actually delivers**: AAA (7:1) text contrast on **all three**
surfaces, in both themes. That exceeds the commitment. It is recorded as
delivered rather than promoted to an obligation, so the commitment does not
silently inflate.

---

## 1. Contrast — delivered by the design

The design measured every token in both themes. Reproduced, not re-verified.

| Token | Light | Dark | Status |
|---|---|---|---|
| `onSurface` | 17.6:1 | 14.5:1 | AAA |
| `onSurfaceVariant` | 8.9:1 | 9.2:1 | AAA |
| `primary` | 8.1:1 | 10.3:1 | AAA |
| `outline` | 4.6:1 | 5.6:1 | **Non-text only** |
| Payment states (5) | 7.5–12.8:1 | 7.8–12.8:1 | AAA |

**`outline` never carries text.** It is for borders and icons. Enforcing that
is a review item, not an automated one.

- [ ] Verify the implemented `ColorScheme` preserves these pairings — a Compose
      theme can apply a token in a role the design did not intend
- [ ] Confirm no text uses `outline`

---

## 2. Colour independence

Status is **never carried by colour alone** [AC9.4.1]. The design satisfies
this with four cues per payment state, and includes a greyscale test artboard.

- [ ] All five payment states distinguishable in greyscale
- [ ] Attendance present/absent distinguishable without colour
- [ ] Partial always shows the remainder; Due always shows the date; Overdue
      always shows the day count
- [ ] No red/green pairing carries meaning on its own

---

## 3. Touch targets

- [ ] Every interactive target ≥ 48dp (WCAG 2.2 Target Size, Minimum is 24×24
      CSS px; 48dp is the stricter Android floor and the design's rule)
- [ ] Every money action 56dp tall, full width
- [ ] 32dp of separation above a money decision

---

## 4. Text and scaling

- [ ] All text in `sp`, so system font scaling applies
- [ ] Layouts hold at 200% font scale (WCAG 1.4.4 Resize Text)
- [ ] `caption` (13sp) is the floor — nothing smaller
- [ ] **Bangla line height**: `fallbackLineSpacing` on, explicit `lineHeight`
      per style, `LineHeightStyle(Center, Trim.None)`, no fixed-height text box
      that can clip
- [ ] Verify at the longest Bangla string per screen: roster, marksheet, dues,
      OTP entry, and **every empty and error state** — explanatory strings are
      the longest in the product and the least likely to be screenshotted
      [AC9.3.3]

---

## 5. Screen reader (TalkBack)

| Requirement | Implementation |
|---|---|
| Icon-only buttons | `contentDescription` on every one |
| Decorative icons | `contentDescription = null` where a word is already present |
| Status chips | `stateDescription` carries the state word |
| Money values | Read as money, not as a digit sequence |
| The marksheet | The plain-text summary [AC-Q10 option D] is the accessible path to the band chart |
| G2's progress chart | The table beneath it is the accessible alternative; the plain-language summary precedes both |

- [ ] Every screen traversable by TalkBack in a sensible order
- [ ] No control reachable only by gesture

---

## 6. Navigation and focus

- [ ] **Back after a lens switch does not reach the other lens's data**
      [AC9.4.2] — a privacy requirement, not only a usability one
- [ ] **Back after a child switch does not reach the other child's data**
- [ ] Correct back-stack behaviour throughout — Play's pre-launch report checks
      this [NFR15]
- [ ] Focus visible for keyboard and switch-access navigation
- [ ] Focus does not escape a bottom sheet or dialog while open

---

## 7. Forms and errors

- [ ] Every field has a visible label, not a placeholder standing in for one
      (WCAG 3.3.2)
- [ ] Errors name the field and the fix in plain words — the design's *"Bangladeshi
      mobile numbers have 11 digits. This one has 10."* is the standard
- [ ] Errors are announced, not only shown
- [ ] Input is preserved on failure [AC9.2.1]
- [ ] **The deletion confirmation names what is deleted and what the teacher's
      records retain** [AC9.4.3] — an [RC-5] compliance exposure, since the
      privacy policy must state post-deletion retention

---

## 8. The three distinct states

- [ ] Loading, empty and error are visually and semantically distinct on every
      list and form
- [ ] **An error never renders as the empty state** [AC9.2.5]
- [ ] Loading skeletons match real row heights

---

## 9. What is deferred, and to where

| Item | Owner |
|---|---|
| Per-screen AA verification | Refined visual design at implementation |
| Play pre-launch report findings | Deployment Execution (4.3) |
| Formal contrast re-measurement against the built theme | Build and Test (3.6) |
| Tablet and landscape layouts, unverified for accessibility | Deferred — no artboards exist [Q9] |

---

## Assumptions & Open Questions

- The commitment is AA on the teacher surface [Q8] while the design delivers
  AAA everywhere. **Regression guard**: the delivered figures are the baseline
  for every surface, and a change that drops any token below its recorded ratio
  is a reviewable regression even where no commitment is breached. The
  contrast check at Build and Test asserts against the recorded values, not
  against the AA floor — so the floor is what we promised and the recorded
  values are what we keep. [assumption]
- WCAG is authored for the web. Applying it to Compose means substituting
  TalkBack for screen readers, `sp` scaling for browser zoom, and `semantics`
  for ARIA. The substitution is standard but not exact. [assumption]
- Tablet and landscape have no artboards [Q9], so their accessibility is
  unverifiable until the layouts exist. [assumption]
- The design's contrast figures are reproduced from its own annotations and
  have not been independently re-measured. [assumption]
- No motion specification survived the export, so reduced-motion handling
  (WCAG 2.3.3) has no design reference. [assumption]

## Sources

- [design] The user's design canvas, `Colour tokens` and `Type scale` artboards.
- [Q8], [Q9], [Q10] `refined-mockups-questions.md`.
- [AC9.2.*], [AC9.3.*], [AC9.4.*] `inception/user-stories/stories.md`.
- [NFR15], [RC-5] `inception/requirements-analysis/requirements.md` and
  `ideation/feasibility/constraint-register.md`.
