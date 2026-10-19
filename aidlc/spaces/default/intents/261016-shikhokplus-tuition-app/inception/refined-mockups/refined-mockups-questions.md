# Refined Mockups — Clarifying Questions

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [desc] Initial description, §5–§11.
- [scope] Workflow-selected scope: `classic`.
- [upstream] `inception/user-stories/stories.md` — 45 stories with Given/When/Then criteria.
- [upstream] `inception/user-stories/personas.md` — four personas.
- [upstream] `inception/requirements-analysis/requirements.md` — 85 FR, 17 NFR.
- [upstream] `inception/practices-discovery/team-practices.md` — affirmed practices, now governing rules.
- [design] `contributions/aidlc-design-agent.md` from User Stories — the UX findings already raised there.

---

## Two notes before the questions

**No rough mockups exist.** The plan folded that stage into this one, so these
mockups come directly from the stories and requirements. Nothing is being
refined from an earlier pass — there is no earlier pass, and I will not invent
one.

**The design knowledge in this framework is largely web-oriented** —
responsive breakpoints, hover states, ARIA roles. This is a native Android app
with Compose, so those map to different things: window size classes rather than
CSS breakpoints, pressed and focused states rather than hover, and Android
accessibility services rather than ARIA. I will produce the Android equivalents
and say where the mapping is not one to one.

---

## Q1. The guardian multi-number problem — which fix?

This is the worst unsolved UX problem in the specification, and the stories only
mitigated it. A guardian whose child has two teachers who recorded two different
numbers must log in with a different number to see each teacher's batch. The
stories added per-batch teacher attribution and a statement of which number the
view is keyed to [AC2.8.3–AC2.8.5], but a guardian seeing one batch where she
expects two still has to infer why.

- A. Mitigation only, as the stories have it — attribution plus a scope statement, and accept that she infers the rest
- B. Add an explicit in-app explanation: a dismissible note saying other teachers may have recorded a different number, with guidance to ask the teacher
- C. Let an account verify a second phone number and union the batches it reaches. The real fix, compatible with the lens model unchanged, but it is new scope and a new OTP flow
- D. Show a placeholder for batches reachable from another number — "1 other batch is linked to a different number" — without revealing whose
- X. Other (please specify)

[Answer]: C

---

## Q2. What does the teacher's home screen show first?

A teacher opens the app several times a day, usually mid-class or at month end.
The stories give four candidate landing surfaces and no decision between them.
Whichever is first is what the app is *for*, in the teacher's mind.

- A. Today's classes — the session list for today, because the most frequent action is recording a class
- B. The cross-batch dues view — your stated subscription justification, and the thing a teacher would pay for
- C. A batch list — neutral, requires one more tap for everything
- D. A summary: today's classes plus a dues total plus the next exam, each tappable
- X. Other (please specify)

[Answer]: A

---

## Q3. How does the mid-class attendance screen handle a large batch?

The stories settled the mechanics: everyone defaults to present, the teacher
marks exceptions, and the whole roster writes atomically [AC3.1.4, AC3.1.5].
What is unsettled is the layout at the sizes that matter — your scale ceiling is
a few thousand students across 100 teachers, so a batch might be 8 or 40.

- A. One scrolling list, every student visible, tap to toggle present/absent
- B. A compact grid of name chips, tap to toggle — more students per screen, less readable
- C. A list with a search or filter field, for batches above a threshold (specify the threshold)
- D. A list, plus a "mark all absent" action for the days almost nobody comes
- X. Other (please specify)

[Answer]: A + search and mark all absent options.

---

## Q4. Does the app have a bottom navigation bar, and what is in it?

This decides the information architecture for all three lenses. Android
convention is bottom navigation for three to five top-level destinations.

- A. Yes, three items for the teacher: Today, Batches, Dues — and two for student and guardian: Batches, Profile
- B. Yes, but four teacher items: Today, Batches, Dues, More
- C. No bottom bar; a navigation drawer instead, which scales to more destinations but hides them
- D. No bottom bar; a single home screen with everything reachable from it
- X. Other (please specify)

[Answer]: B

---

## Q5. How does the lens switcher present?

One account may hold teacher, student and guardian lenses simultaneously
[FR1.6], and switching must not require re-authentication [FR1.5]. The back
stack must also not leak across a switch [AC9.4.2].

- A. A persistent control in the top app bar, showing the current lens
- B. In the profile or settings screen only — switching is rare, so it need not occupy the main surface
- C. A full-screen chooser on launch when more than one lens exists, remembered thereafter
- D. Both A and C — chooser on first launch, then a top-bar control
- X. Other (please specify)

[Answer]: D

---

## Q6. What is the visual treatment for fee status?

Your affirmed practices require status never to be carried by colour alone
[AC9.4.1], and the server already sends a status enum. The question is what the
status looks like.

- A. A text label with an icon — "Paid", "Partial", "Unpaid" — with colour as reinforcement only
- B. A coloured chip containing the text, so colour and text travel together
- C. Text plus an amount, with no icon or colour at all — the amount carries the meaning
- X. Other (please specify)

[Answer]: A

---

## Q7. Which Material 3 posture — default, or a custom theme?

Compose with Material 3 is already decided [D-27]. What is open is whether this
looks like a stock Material app or carries its own identity.

- A. Stock Material 3 with dynamic colour, following the system wallpaper. Cheapest, most familiar, zero design debt
- B. A fixed brand colour scheme, Material 3 components otherwise. Recognisable, slightly more work
- C. A considered custom theme — typography, shape and colour tuned for Bangla text and for a teaching context
- X. Other (please specify)

[Answer]: X - I have a design file made using claude design - https://claude.ai/code/artifact/14c6b628-4a29-4601-adaa-64711995bf29.

---

## Q8. What accessibility level are we committing to?

Your NFR15 says "accessibility basics", which the requirements stage flagged as
unverifiable. Play's pre-launch report checks a subset automatically. A stated
level makes the obligation testable.

- A. WCAG 2.2 Level AA, as the stated target, verified per screen
- B. Play's pre-launch report findings plus the three story-level cases already specified, with no formal WCAG commitment
- C. WCAG 2.2 Level AA for the teacher surface only, since students and guardians are read-mostly
- X. Other (please specify)

[Answer]: C

---

## Q9. Does the design need to work in landscape, and on a tablet?

Android's window size classes are the modern equivalent of breakpoints. A
teacher might use a tablet; a student almost certainly will not.

- A. Portrait phone only. Landscape is permitted but unoptimised; no tablet layout
- B. Portrait and landscape phone; no tablet-specific layout
- C. Phone portrait and landscape, plus a tablet layout for the teacher surface where the dues and marksheet views benefit from width
- X. Other (please specify)

[Answer]: C

---

## Q10. How is the marksheet presented, now that it is rank and bands?

The stories replaced anonymised rows with the viewer's own mark, a rank, the
batch average, the highest mark, and a banded distribution [AC4.3.2]. That is
specified as content, not as a design, and bands are easy to render badly.

- A. A horizontal bar per band, with the viewer's band highlighted — compact and readable at a glance
- B. A number line with band boundaries and a marker for the viewer's position
- C. Plain text: "Your mark: 72. Rank 4 of 18. Average 61. Highest 89." plus a simple band table
- D. A, plus the plain-text summary beneath it, so the figures are available to a screen reader as text
- X. Other (please specify)

[Answer]: D

---

## Q11. Reconciling the design file with the approved artifacts

The design canvas was read after Q1–Q10 were answered. Three of its decisions
conflicted with artifacts already approved; these are the resolutions.

**Q11.1 — The marksheet**

The design shows a fully named marksheet: 19 students ranked by mark, the
viewer's row tinted `#D8E3F7`, absent students listed but unranked. That is
§10 as originally written. The stories had replaced it with anonymised
rank-and-bands after the User Stories design review argued that unattributed
marks are deanonymised by inference in a batch whose members sit together.

- A. The design — named marksheet
- B. Keep anonymised rank-and-bands
- C. Named, behind a third state on the existing per-batch toggle
- X. Other (please specify)

[Answer]: B. The anonymised rank-and-bands treatment stands [AC4.3.2–AC4.3.6].
The design's `Marksheet light` and `Marksheet dark` artboards are **superseded
on this screen only**; every other artboard stands. The named layout is a
better-looking screen and a worse privacy posture under the mixed-audience
Families declaration, and the deanonymisation-by-inference argument is not
answered by presentation.

**Q11.2 — The offline write queue**

The design's `Record a class` artboard shows a "Saved on phone · not sent —
Couldn't send. Will retry on its own." state, and `Spacing and components`
shows an offline banner reading "Your entries are saved on this phone and will
send when you're back online." That is an offline write queue, which NFR5
forbids ("no local write queue, and a failed write surfaces an explicit retry
prompt rather than queueing silently") following the cached-reads-only decision
at intent capture [intent: Q6, Q18].

- A. The design — allow the queue for mid-class writes
- B. NFR5 stands; the design's offline state is corrected
- C. Queue the topic text only, not attendance
- X. Other (please specify)

[Answer]: A. **Allow a local write queue for the mid-class path** — the topic
log and attendance. This reverses the cached-reads-only decision for those two
writes and is the most consequential change in this stage.

What it costs, recorded so it is not discovered later: a local write queue, a
sync mechanism, and conflict handling, none of which the approved architecture
includes. It also partly restores the protection that was lost when the
mid-class speed requirement was dropped [requirements: Q14.3] — a queued write
cannot fail mid-class, which is the abandonment scenario §11 warns about.

Scope of the reversal: **mid-class writes only**. Payment submission, marks
entry, enrollment, batch creation and profile edits all still require
connectivity. Every other write keeps the US9.2 failure behaviour.

Upstream amendments this requires:
- `NFR5` — no longer an absolute prohibition; it now excepts the mid-class path.
- `FR3.6` — attendance no longer requires connectivity.
- `US3.1` (AC3.1.3) — the retry prompt becomes a queued-and-will-retry state.
- `AC9.2.2` — "an unconfirmed write never renders as confirmed" needs a third
  state: queued, which is neither confirmed nor failed.
- The architecture gains a sync surface; Domain Design must decide what happens
  when a queued attendance write arrives after the teacher has edited the same
  session from another device [FR11.4].

**Q11.3 — The numeral rule**

The design's rule is broader than AC9.3.1 and better reasoned: the app's own
numbers render Latin **always** (money, marks, dates, transaction IDs, phone),
user-typed text is stored and shown exactly as typed, and Bengali digits are
accepted on input and normalised. AC9.3.1 forced Latin only for OTP, phone and
transaction IDs.

[Answer]: The design's rule is adopted and supersedes AC9.3.1. No question was
needed — it is strictly broader, it covers cases AC9.3.1 missed (money and
marks), and it adds an input-normalisation rule the stories had no equivalent
of.

---

## Q12. Three capabilities the design introduces that no requirement covers

The user delegated these decisions ("decide the best possible options... so
that I don't need to check"), so a product specialist was dispatched with the
scope posture, the SMS cost analysis and the privacy rules, and asked to decide
rather than recommend. Its decisions are recorded here as answered.

**Q12.1 — Reminder SMS to late guardians (T5)**

The dues screen shows "Remind 12 late guardians — SMS in Bangla and English ·
you approve the text first", plus a "Not reminded" filter and per-row reminder
state.

[Answer]: **Defer the send path to V2; make two accommodations now.**

Reasoning: this is five things, not one — two-language templating, a teacher
approval step, per-guardian-per-cycle state, a bulk job with partial-failure
semantics, and **a second cost-bearing consumer on the gateway that currently
carries only OTP**. That last one decides it. Per-SMS billing is the project's
one direct financial-attack surface [R-4], answered by a global ceiling
[NFR12]. A second, teacher-triggered, *bulk* consumer makes that ceiling
arbitrate between an abuse burst and a legitimate teacher pressing "Remind 12"
on the 5th — when every teacher presses it on the same few days. Shared, it
either lets reminders exhaust the OTP budget and lock teachers out of login, or
throttles reminders unpredictably.

There is also a product reason to wait: **FR10.1 already commits to push
notifications for fee reminders.** Push is free, already in scope, and targets
the same guardian for the same purpose. Shipping paid SMS before the pilot shows
whether push reaches guardians is paying for an unproven channel.

Accommodations made now, both exercised in V1 by capabilities already in scope:
- **FR10.3** — reminders are events, not a flag. A boolean or `last_reminded_at`
  cannot express channel, a failed send, or a second reminder, so it would force
  a migration.
- **FR10.4** — the V1 push writes a reminder event, so the table is exercised and
  the "Not reminded" filter works in V1 with no SMS capability at all.
- **NFR12.1** — the gateway adapter takes a `purpose` and each purpose carries its
  own ceiling. V1 has one purpose. Retrofitting this means re-reasoning about the
  one control protecting the wallet, after a second consumer is live.

The T5 bulk-SMS action is **marked V2 in `mockups.md`** so it is not built from
the artboard by default. The filter and per-row state stay — both are satisfiable
from push events alone.

**Q12.2 — Cross-batch student lookup on enrollment (T8)**

[Answer]: **Accept, narrowed.** Recorded as **FR2.19**. Three narrowings: the
lookup resolves only over enrollments owned by the requesting teacher's own
owner entity; it returns only teacher-authored fields (the display name and
guardian number *that teacher* typed elsewhere), never self-authored profile
data; and values are copied as editable defaults, never linked.

Within that narrowing this is a teacher reading their own business record, which
FR2.4 and FR2.6 already establish as teacher-authored. Unscoped, it is exactly
the leak the open teacher-vs-teacher question anticipates — and worse, because
the lookup is keyed on a phone number the requester supplies, it would become a
**phone-number enumeration oracle** over the whole user base, against the
standing rule never to reveal whether a number exists. FR2.19 therefore requires
the no-match response to be byte-identical for "enrolled only with another
teacher" and "enrolled nowhere".

Implementation notes carried to Domain Design: the lookup is a lensed endpoint
whose lens carries the resolved `owner_id` and scopes the query — not a global
query filtered afterwards, which is the forgotten-lens failure the
route-enumeration test exists to catch. Its response schema is a teacher-lens
schema, so the schema-wide no-profile-fields invariant covers it automatically.
An adversarial probe is added: teacher A looks up a number enrolled only with
teacher B and must get the no-match response.

**Q12.3 — Rocket as a payment channel (S3)**

[Answer]: **Accept.** Recorded as **FR6.11**, with `cash` added alongside, since
§9 names cash and a claim with no representable channel is the same gap.

With no gateway integration [FR6.10] the channel is a label on a claim: no
integration surface, no credential, no cost, no compliance consequence. Omitting
it pushes students to pick a wrong label, degrading the one thing the field is
for — helping a teacher match a claimed transaction against what they received.

The channel set is **server-supplied data, not a client-side list**, so adding
Upay later is a data change rather than an app release. An installed Android app
cannot be forced to update [NFR16].

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Teacher lands on Today (the session list); four-item bottom navigation —
  Today, Batches, Dues, More; lens chooser on first launch then a top-bar
  control; attendance as a scrolling list with search and mark-all-absent; fee
  status as text plus icon with colour only reinforcing.
- WCAG 2.2 Level AA committed on the teacher surface; the design in fact
  delivers AAA text contrast on all three surfaces in both themes, recorded as
  delivered rather than promoted to an obligation.
- Phone portrait and landscape plus a teacher tablet layout; neither landscape
  nor tablet is drawn in the design, so both are derived at implementation.
- The design system is taken from the user's own canvas: `primary #1D4F91` light
  and `#A9C7FF` dark with full Material 3 roles, Noto Sans with Noto Sans
  Bengali, IBM Plex Mono for transaction IDs only, a 7-step type scale with a
  1.67x line-height step for Bangla, and a 4/8/12/16/24/32 spacing scale with
  56dp full-width buttons for anything that moves money.
- Three conflicts between the design and the approved artifacts were resolved:
  the anonymised marksheet stands and the design's two marksheet artboards are
  superseded on that screen only; the design's offline write queue is adopted
  for the mid-class path, amending NFR5 and FR3.6; and the design's numeral rule
  supersedes AC9.3.1, being strictly broader.
- Three capabilities the design introduced were decided rather than absorbed:
  reminder SMS deferred to V2 with three schema accommodations made now
  (FR10.3, FR10.4, NFR12.1), the cross-batch lookup accepted narrowed to the
  teacher's own batches (FR2.19), and Rocket accepted with cash alongside
  (FR6.11).
- The anonymised marksheet is consequently the only screen in the product with
  no visual design.

[Answer]: Looks correct

---
