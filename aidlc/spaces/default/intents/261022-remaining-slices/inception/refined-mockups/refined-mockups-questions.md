# Refined Mockups — Questions

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Record**: 261022-remaining-slices

## Sources

- [design] the ShikhokPlus canvas, 51 artboards, read 2026-10-23
- [upstream] `inception/user-stories/stories.md`, `requirements-analysis/requirements.md`
- [prior] `261016-shikhokplus-tuition-app/inception/refined-mockups/`

---

## Q1. Does the `O1 · Create account` artboard exist?

The replan describes O1 in detail and says it was read on 2026-10-22, but the
repository's design exports have not changed since 17 October, the prior
record lists the onboarding screens as undrawn, and no readable text could be
extracted from the HTML bundles. Several requirements cite O1 as their source.

[Answer]: Yes — it is in a tool outside this repository. The user supplied the
canvas link, and O1 was then read directly: it exists, on a page called "Sign
up and log in", with exactly the five states the replan describes, the
three-way role picker, and the locked-role invited state carrying the precise
Bangla copy the replan quotes.

**The doubt was wrong and the record says so.** The requirements that cite O1
stand unamended. What the episode establishes is narrower and still useful:
the exports under `claude_design/` are not the design, and a stage that needs
to know what a screen looks like reads the canvas.

## Q2. How should this stage treat O1 and the other existing artboards?

[Answer]: Read them, and do not redraw them. 48 artboards already existed and
cover the three in-app surfaces, the design system, and the store assets. This
stage adds only what acceptance needs and what the prior record recorded as
undrawn.

## Q3. Which screens should this stage draw?

[Answer]: Every undrawn screen, per the user's instruction — "Check the design
file. If it's not there then use the same design system to create one" and
"Cover every undrawn screen now". Four artboards were drawn:

- **`O4 · Invitations`** — accept, decline, un-decline, and the decline
  confirmation. Five states. Nothing covered this; it is the first thing a
  student or guardian does under the acceptance model.
- **`O5 · Profile and account deletion`** — profile edit [FR1.12] and the
  in-app deletion path [FR1.14], both undrawn since the first record, with a
  separate teacher variant because the consequences differ.
- **`O6 · Delete account from the web`** — the external route [FR1.15], drawn
  in a browser frame because it is the one non-app surface, including the
  unknown-number state that must not disclose whether an account exists.
- **`T7 · Single batch`, sixth column** — the acceptance states on the roster:
  the batch-level accepted count, a declined row with its remove action, and
  the split-decision row.

OTP sign-in was **not** redrawn: `O3-OTP` exists and the flow is built and
working.

## Q4. One component had to be invented. Is that acceptable?

[Answer]: Yes, and it is recorded rather than slipped in. `c-decl`, a declined
chip, is the only new component: no existing chip means "a person refused
this". It is grey and dashed rather than red, because a decline is not an error
and most often means a wrong number — red would read as a problem with the
student. Every other colour, type size, radius and spacing value on the four
artboards is an existing token.
