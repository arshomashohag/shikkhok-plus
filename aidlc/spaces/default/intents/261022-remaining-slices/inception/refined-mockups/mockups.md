# Refined Mockups — the screens acceptance adds

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **The design is a canvas, not a file in this repository.** It lives at
> `https://claude.ai/code/artifact/08870a1d-3766-4531-ae6f-93e52d9a7158`
> and now holds **51 artboards** across twelve pages. The HTML bundles under
> `claude_design/` are exports, and their text cannot be read; the canvas is
> the source.
>
> This stage did not redraw what exists. It drew the four screens acceptance
> needs and that nothing covered.

## Sources

- [design] the ShikhokPlus canvas, read 2026-10-23 — `project/canvas.json`,
  `O1-Signup`, `S1-Batches`, `T7-BatchDetail`
- [upstream] `inception/user-stories/stories.md` — US1.10–US1.16 and the
  amendments
- [upstream] `inception/requirements-analysis/requirements.md` — FR1a
- [prior] `261016-shikhokplus-tuition-app/inception/refined-mockups/mockups.md`

---

## A correction worth recording

The prior record's mockups artifact states that **OTP sign-in, profile edit
and both deletion screens have no artboard**, and this stage opened expecting
to find the same. It also doubted whether `O1 · Create account` existed at all,
because the replan describes it in detail while the repository's exported HTML
contains no readable trace of it.

**That doubt was wrong.** `O1-Signup`, `O2-Login` and `O3-OTP` all exist on the
canvas, on a page called "Sign up and log in", and O1 matches the replan's
description exactly: five states, a three-way role picker, the locked-role
invited state carrying the precise Bangla copy the replan quotes. The prior
record's "no artboard for OTP sign-in" was either written before that page
existed or written from the same unreadable exports.

The lesson is narrow and practical: **the repository's design exports are not
the design.** A future stage that needs to know what a screen looks like reads
the canvas, not `claude_design/`.

---

## What existed before this stage

51 artboards, of which the 48 pre-existing ones cover:

| Page | Artboards |
|---|---|
| Design system | type pairing, type scale, numerals, colour, components, marksheet light and dark |
| Onboarding | `O1` create account, `O2` log in, `O3` OTP |
| Teacher | `T1`–`T8` |
| Student | `S1`–`S3` |
| Guardian | `G1`–`G3` |
| Store, screenshots, tablet, desktop, video | listing graphics and promotional renders |

Every one carries its states as columns — default, empty, loading, error — which
is the convention this stage follows.

---

## What this stage added

### `O4 · Invitations` — accept or decline

**The screen that did not exist, for the decision that did not exist.** Under
the superseded model a student or guardian signed in and their records were
simply there; under acceptance, the first thing either of them does is answer a
question.

Seven states:

| State | What it shows |
|---|---|
| **Default, one waiting** | Batch name, the role they were added as, subject and monthly fee, with Accept and *Not me*. Nothing else about the batch. |
| **Two seats, one declined** | A waiting invitation above a declined one that still offers *Accept after all* — the un-decline path [AC1.13.1]. |
| **Empty** | Nothing waiting, and where accepted batches live instead. |
| **Confirm declining, student** | The teacher sees it, nothing about them is shared, no fee is charged to them, and it is reversible. |
| **Confirm declining, guardian** | The same, except a warning callout saying **the student's fee is unchanged** [AC1.14.1a]. |
| **Error** | "Couldn't check for invitations. This is not the same as having none." |
| **Loading** | Skeleton matching the card shape. |

The last three were added after review. The guardian sheet is the important
one: a single confirmation saying "the fee stops" was true for a student and
false for a guardian, telling them that declining cancelled an obligation it
does not cancel. The error state matters for a related reason — "nothing
waiting" and "could not load" must never be confusable, because one means
decide nothing and the other means you may have a decision you cannot see.

Three decisions inside it worth naming:

- **The decline action reads "Not me", not "Decline".** The commonest cause of
  a pending seat is a mistyped number, and the commonest person seeing this
  screen wrongly is a stranger. "Not me" is what that person means; "Decline"
  sounds like refusing a teacher, which is the rarer case and the one more
  likely to be mis-tapped out of confusion.
- **The pending card shows the fee.** [FR1.9d] permits batch, subject and fee,
  and the fee is the reason: a guardian is being asked to take on a financial
  obligation, and hiding the amount would make the decision uninformed.
- **The confirmation sheet says declining is reversible.** It is the one place
  the un-decline rule reaches the person it protects, and without it a cautious
  reader treats the choice as final.

### `O5 · Profile and account deletion`

Profile edit and in-app deletion, both undrawn since the first record and both
release-blocking for deletion [TC-19].

| State | What it shows |
|---|---|
| **Profile** | Name, a read-only number marked as the login, address. Carries [FR1.12]'s helper text: your teachers keep seeing the name they typed. |
| **Delete, confirm** | Two lists — what is deleted, what the teachers keep — with the number typed to confirm. |
| **Delete, teacher variant** | Its own deleted/retained pair [AC9.4.3], phrased in terms of access to 31 students' records rather than of a profile, with the batch count and the outstanding total. Added after review, which found the teacher screen had neither list. |
| **Done** | What was removed, and what remains. |

The two confirmation screens differ because the consequences differ. A student
deleting removes their own login; a teacher deleting takes their access to 31
students' records with them, and the screen says so with the numbers filled in.

### `O6 · Delete account from the web`

The externally accessible route [FR1.15, TC-19] — release-blocking, and the
only non-app surface in the product. Drawn in a browser frame rather than a
phone frame, because that is what it is.

Four states: ask for a code, confirm with the code, done, and **unknown
number**. That last one is the reason this screen needed drawing rather than
describing: the page must not reveal whether a number has an account, so the
code step looks identical either way and says so in as many words.

### `T7 · Single batch` — a sixth column

The roster gains an acceptance view rather than a redrawn one. It shows:

- the **batch-level count** ("5 of 7 accepted") that [AC1.3.3a] and [AC1.3.5a]
  put in place of per-row pending marks;
- a **declined row** showing the bare number rather than a name, because a
  declined seat is often a wrong number and there may be no real person behind
  it, with the remove action [AC2.5.1a] beside the explanation;
- a **split-decision row** — "Student accepted · guardian declined" — which is
  the case [AC1.10.6] adds and which no existing artboard could express.

The five original columns are untouched.

---

## Why pending is counted and declined is marked

The superseded [AC1.3.3] refused to mark the roster at all, reasoning that
"dormant is the normal state early in a batch's life and decorating most rows
would flag normality as a problem". That argument survives the collapse of
dormant into pending and is honoured rather than discarded.

Pending is now the common early state, so marking every pending row would
reproduce exactly the clutter the original reasoning guarded against. Declined
is not normality — it is the signal that a number may be wrong — so it earns a
row. The count carries the rest.

---

## Screens still with no artboard

| Screen | Where it lands | Why it is not drawn here |
|---|---|---|
| Fee cycle and ledger screens beyond `T5`/`S2` | D3 | The existing artboards cover the capability; D3's functional design will say whether they suffice. |
| Attendance conflict resolution [FR11.5] | D4 | A genuinely novel surface with no artboard, flagged in the prior record and still open. The four-state queue and the re-apply path need drawing before D4 builds them. |
| Insights | D5 | The plan gives D5 no artboard and the prior record notes the same. |

The attendance conflict screen is the one real remaining gap. It is recorded
here rather than drawn, because it belongs to D4 and drawing it now would
specify a surface three units ahead of the unit that builds it.

## Assumptions & Open Questions

- **Assumed**: the invitation list is its own destination rather than a banner
  on the batch list. A banner would have to coexist with the empty state that
  already tells a student how to be added, and two competing explanations on
  one screen is worse than one screen each.
- **Assumed**: a declined row shows the phone number rather than the
  teacher-typed name. The teacher typed that name against a number that turned
  out to be wrong, so showing it would assert an identity the decline disputes.
- **Open**: whether `O4` should be reachable from the lens switcher or sit
  above the batch list. The artboard shows it as its own screen; where it is
  entered from is a navigation decision for Functional Design.

---

## What the review changed

Ten findings, two Critical. Each was verified against the artboards or by
computation before being acted on; all are closed.

| Finding | What was wrong | Closed by |
|---|---|---|
| **The decline sheet told a guardian the fee stops** | [AC1.14.1a] says a guardian's decline leaves the student's obligation intact. One sheet for both roles told a guardian that declining cancelled a debt it does not cancel. A money error, not a wording one. | A separate guardian sheet with a warning callout; the student copy narrowed to "no fee is charged to you" |
| **O4 had no error state** | `interaction-spec.md` declared one and made it load-bearing — "nothing waiting" and "could not load" must never be confusable — and the artboard had five columns. The two artifacts disagreed about what was drawn. | Drawn, saying exactly that |
| **The teacher deletion screen had neither list** | [AC9.4.3] requires naming what is deleted and what is retained, and `interaction-spec.md` claimed both artboards carried them. The teacher variant carried neither. | Its own pair, phrased in terms of access to 31 students' records |
| **Every contrast figure was wrong** | The table was headed "Measured against the tokens, not estimated" above estimated numbers. Ink on white was 17.64 not 16.8; white on primary 8.14 not 8.6. No verdict changed, which is what makes it the exact failure `project.md`'s stated-number rule names. | Recomputed from the luminance formula, with the episode recorded |
| **The two chips do not differ in lightness** | The checklist claimed hue *and* lightness. `#EFE6FB` and `#E4E8EE` differ by a luminance ratio of 1.018 — nothing. [AC9.4.1] holds on text, icon and border alone. | Corrected, and the O4 row separated from the T7 row it actually described |
| **The lens claim contradicted the requirement** | "The only screen in the product that is not inside a lens" contradicts [FR1.9d.1], which specifies a distinct invitation lens. | Restated over the invitation lens; the navigation requirement is unchanged and was always the point |
| **Two files disagreed about 44dp** | `interaction-spec.md` asserted the minimum held everywhere; the checklist recorded a 40dp failure. Whoever builds T7 reads one file. | The spec now names the exception and points at the checklist |
| **The 40dp deferral named no owner** | Which `project.md` forbids as of 2026-10-22. | Assigned to D1, with the reasoning for fixing the shared component rather than one screen |

Two findings were accepted without change: the dual student-and-guardian seat
[AC1.10.5] is not separately drawn, and nothing shows the invitee side of a
split decision — correctly, since each party sees only their own decision and
the split is invisible to each half by construction.

**What the review did not fault** is worth recording, because it was the part
most at risk: T7's sixth column, O6's non-disclosing unknown-number state, the
design-system reuse, and the honesty of the O1 episode.
