# Mockups — ShikhokPlus

**Stage**: refined-mockups (2.5)
**Phase**: Inception
**Date**: 2026-10-17

21 artboards from the user's design canvas, exported to `claude_design/` and
extracted from their bundled form. Screens are described here with their states
and the stories they satisfy; the canvas is the visual source of truth, this
file is the specification derived from it.

No rough-mockups pass preceded this — that stage was folded into this one when
the plan was composed, so there is no earlier fidelity to compare against.

---

## Information architecture

**Bottom navigation, four teacher items** [Q4]: Today · Batches · Dues · More.
Student and guardian surfaces are narrower and do not carry the same bar.

**Lens switcher** [Q5]: a full-screen chooser on first launch when an account
holds more than one lens, then a control in the top app bar. Switching never
re-authenticates [FR1.5], and the back stack must not carry a previous lens's
screen across the switch [AC9.4.2].

**Teacher landing is Today** [Q2] — the session list, because recording a class
is the most frequent action. Dues is one tap away on the bar.

---

## Teacher surface — 8 screens

### T1 · Teacher home (Today)

Satisfies US3.0, US3.1 entry, US7.1 summary, US8.1–US8.4 summary.

| Element | Content |
|---|---|
| Date header | "Today · Saturday, 17 Oct" |
| Outstanding card | "৳48,600 · 7 batches · ৳31,200 overdue · 12 students" — taps through to Dues |
| Change banner | "Batch C moved to 7:30 pm today. Students and guardians were notified." |
| Classes today | Time, subject · batch, topic, with a **Record** action; "Next · in 35 min" on the imminent one |
| Exam marker | Inline in the class list where a class is an exam, with a **Marks** action |
| To verify | Count, oldest-first, each showing student, channel, age, amount and whether it matches the fee |

**States**: Default · Empty (first run). The empty state is a numbered
three-step setup rather than a blank: *"1 Name the batch and pick its class
days, time and monthly fee. 2 Add students by phone number. They sign in with
it."*

### T2 · Record a class

Satisfies US3.1 (AC3.1.1–AC3.1.10).

Subject chips where a batch has more than one paper; a free-text topic field
accepting **Bangla or English**; previous topic offered as a continuation.

**States**: Default (typing, keyboard up) · Empty (first class in a batch —
*"Write in any language. From the next class we'll suggest where you left
off."*) · Loading (suggestions on slow network) · **Error: "Saved on phone ·
not sent — Couldn't send. Will retry on its own."** with a **Retry now**
action.

That error state is the offline queue [Q11.2]. It is the design's, and it
reversed NFR5.

### T3 · Marks entry

Satisfies US4.1 (AC4.1.1–AC4.1.5).

Continuous entry down the roster with a progress counter ("6/20"), row index,
name, a numeric field and the denominator ("/25"). **Absent** is a distinct row
state, not a blank or a zero [FR4.3]. Row height 64dp.

### T4 · Payment verification

Satisfies US6.3 (AC6.3.1–AC6.3.8).

Queue with "4 waiting · oldest 2 days". Each entry shows the student, batch,
age, amount, **whether it matches the fee** ("Matches Oct fee" / "৳400 short of
৳1,200"), the channel and transaction ID in mono, and the sending number —
noting when it is the guardian's rather than the student's.

Three actions: **Reject · Partial · Approve**. Partial opens the
carry-forward-or-waive choice [AC6.3.3].

### T5 · Cross-batch dues

Satisfies US7.1 (AC7.1.1–AC7.1.5).

Header totals "Owed to you ৳48,600 · 34 students", then **three lateness
bands**: 30+ days (৳18,000 · 7), 1–30 days (৳13,200 · 5), due-not-yet-late
(৳17,400 · 22). Filters: All batches · Late only · **Not reminded**.

Each row: student, **which batches** ("2 batches · পদার্থবিজ্ঞান A, রসায়ন C"),
period, reminder state, amount, day count.

Bulk action: *"Remind 12 late guardians — SMS in Bangla and English · you
approve the text first."*

> **⚠ V2 — DO NOT BUILD FROM THIS ARTBOARD.** The bulk SMS action is deferred
> [Q12.1]. Building it from the mockup by default is the specific risk this
> note exists to prevent. The **"Not reminded" filter and the per-row reminder
> state stay in V1** — both are satisfiable from the V1 push-notification
> events alone [FR10.3, FR10.4].

### T6 · Batch list · T7 · Single batch · T8 · Add student

T6 satisfies US2.1 entry. T7 satisfies US2.2–US2.5 with tabs **Students ·
Classes · Exams · Notices**, each student row showing the guardian number or
"No guardian added", and the fee state.

T8 satisfies US2.2 and US1.4, and is the most considered form in the design:

- Phone with a fixed `+88` prefix
- **Live lookup**: "Checking if this number is on ShikhokPlus…" → "Found on
  ShikhokPlus · তাসনিম জাহান · Also in your রসায়ন · Batch C · guardian
  01611-477203 · Filled from Batch C"
- Name field labelled *"Any language, as the family writes it"*
- Guardian phone marked optional, explained: *"Lets a parent see marks and pay
  fees from their own phone."*
- Fee defaults to the batch fee with a toggle for a per-student override
- **Save & add next** alongside Save
- Validation in plain words: *"Bangladeshi mobile numbers have 11 digits. This
  one has 10."*

The cross-batch lookup pre-filling a guardian number is **not in any story**.
See §Conflicts.

---

## Student surface — 3 screens

### S1 · Student batches

Satisfies US2.6, US2.7-equivalent for students.

Header shows the student's own name **and number** — which is the design's
answer to "how does a student tell their teacher how to add them". Next class
banner, then one card per batch with teacher name, schedule, last test mark and
rank, and fee state.

**Empty**: *"You're not in a batch yet. Your teacher adds you using your phone
number. Give them this number: 01611-477203."* That is the dormant-record case
[US1.3] from the student's side, which no story covered.

### S2 · Student batch · S3 · Submit payment

S2 satisfies US3.4, US4.3, US5.3 — next class with the following two dates,
fee state, results with rank, upcoming exams with chapters, latest notice, and
a topics-covered section.

S3 satisfies US6.1–US6.2 as a **numbered three-step flow**: 1 Send money to
[teacher name] [number] · Copy · 2 Which app (bKash / Nagad / **Rocket**) · 3
Transaction ID from the SMS, and the amount.

**States**: Default · Empty ("Which fee are you paying?", listing payable fees
and explaining exclusions: *"রসায়ন · Batch C isn't listed: your October payment
is being checked."*) · Loading ("Sending…").

**Rocket is a third payment channel** not named anywhere upstream — the brief
says bKash and Nagad. See §Conflicts.

---

## Guardian surface — 3 screens

### G1 · Guardian home

Satisfies US2.7 (AC2.7.1–AC2.7.4), US4.4, US5.4.

Child switcher as avatar chips at the top. The selected child's name is
**repeated in every card title below it** — "তাসনিম's next payment", "তাসনিম's
latest results", "তাসনিম's batches" — which is the design's answer to
wrong-child risk [AC6.1.2/AC6.1.3], applied as a layout principle rather than
one confirmation dialog.

Switching children shows "Now showing [name]'s marks and fees" and the late
state carries forward ("37 days late").

### G2 · Guardian progress

Satisfies US4.4 (AC4.4.1–AC4.4.2).

A **plain-language summary first**: *"Marks went up in each of the last 4
tests, from 31 to 44 out of 50. Now above the batch average."* Then a line
chart of the child against the batch average, then a table of test, marks and
rank.

### G3 · Guardian payments

Satisfies US5.4, US6.4.

Year total, then months, each entry showing state with its date and channel:
Due · **Verifying** ("You sent it 15 Oct · Nagad") · Paid ("Approved 8 Oct ·
bKash").

---

## Screens with no artboard

The design covers the three in-app surfaces thoroughly and leaves four screens
undrawn. Two of those matter more than the "no tablet layout" gaps listed in
Assumptions, so they are stated here rather than buried.

| Missing screen | Stories | Why it matters |
|---|---|---|
| **OTP sign-in** | US1.1, US1.2, US1.8 | **This is the walking skeleton.** PU-1 is the first thing built, it carries all seven abuse controls as skeleton-time obligations, and it is the one flow where a design mistake is a security mistake. The design has no artboard for it, so the OTP entry screen, the resend-after-cooldown state, the delivery-failure message and the degraded-mode message when the SMS ceiling trips are all unspecified visually. `interaction-spec.md` §7 covers the phone field; nothing covers the code-entry step |
| **Account deletion, in-app** | US1.6 | Release-blocking [TC-19]. AC9.4.3 requires the confirmation to name what is deleted and what the teacher's records retain — that is a screen with specific content and it is not drawn |
| **Account deletion, external web route** | US1.7 | Release-blocking, and it is a **web surface** the architecture does not include [feasibility open item]. Not drawn, not costed |
| **Profile edit** | US1.5 | Including the helper text stating the profile does not change what teachers see [FR1.12] |

All four are specified well enough in the stories to build from, and the
design system supplies their visual language. They are recorded as gaps rather
than invented here.

---

## Foundations — 7 artboards

`Colour tokens` · `Type scale` · `Type pairing` · `Numeral rule` · `Spacing and
components` · `Marksheet light` · `Marksheet dark`. All specified in
`design-system-mapping.md`.

---

## Cross-cutting states

The design specifies these once, in `Spacing and components`, rather than
per-screen:

| State | Treatment |
|---|---|
| Offline | Banner: *"Offline · last updated 10:42 am. Your entries are saved on this phone and will send when you're back online."* |
| Queued write | "Class recorded · তাপগতিবিদ্যা — **Not sent yet**" |
| Loading | **Static skeleton with the same row heights as the real list**, so nothing jumps on load |
| Empty | Per screen, each explaining the next action rather than stating absence |

---

## Conflicts and additions

### Resolved at Q11

| Conflict | Resolution |
|---|---|
| Marksheet named vs anonymised | **Stories stand.** `Marksheet light` and `Marksheet dark` are superseded on that screen only [Q11.1] |
| Offline writes | **Design stands.** NFR5 and FR3.6 amended; mid-class path queues [Q11.2] |
| Numerals | **Design stands.** AC9.3.1 widened, AC9.3.4–AC9.3.6 added [Q11.3] |

### New scope the design introduces

Three capabilities appear in the design that exist in no requirement or story.
Recorded here rather than absorbed silently; each needs a decision.

All three were decided at Q12 and are now recorded as requirements.

| Addition | Decision | Recorded as |
|---|---|---|
| **Reminder SMS to late guardians** (T5) | **Deferred to V2.** It is a second cost-bearing consumer on the gateway that carries OTP, where SMS cost is the project's one direct financial-attack surface. A shared ceiling would arbitrate between an abuse burst and a legitimate bulk action. FR10.1's push reminders are free, already in scope, and serve the same guardian — paying per SMS before the pilot shows push is insufficient is premature. | **FR10.3** reminders as events not a flag · **FR10.4** V1 push writes those events · **NFR12.1** per-purpose SMS budget. All three exercised in V1 by capabilities already in scope, so V2 is an addition rather than a migration |
| **Cross-batch student lookup** (T8) | **Accepted, narrowed** to the requesting teacher's own batches, teacher-authored fields only, copied as editable defaults. Unscoped it would be a phone-number enumeration oracle, so the no-match response must be identical for "enrolled with another teacher" and "enrolled nowhere" | **FR2.19** |
| **Rocket as a payment channel** (S3) | **Accepted**, with `cash` added alongside since §9 names it. No gateway integration means the channel is a label on a claim — no integration surface, credential, cost or compliance consequence | **FR6.11**, with the channel set server-supplied so adding one later is a data change, not an app release |
| **The teacher's collection number** (S3) — *found at review, not at Q12* | **Accepted.** S3's step 1 reads "Send money to নাজমা আক্তার · 01712-345678 · bKash or Nagad · personal", with a Copy action. The payment flow cannot work without it: money moves out of band [FR6.10], so a guardian needs somewhere to send it. But no requirement defined it — not how it is captured, not whether it differs from the login number, not what happens when it is unset | **FR6.12** (a separate, optional collection number — a teacher may collect on a different account from the one they sign in with) and **FR6.13** (its disclosure to students and guardians is deliberate and bounded, and the teacher is told at entry that it will be visible) |

### The anonymised marksheet has no artboard

Because `Marksheet light`/`dark` are superseded [Q11.1], the rank-and-bands
treatment specified in AC4.3.2–AC4.3.6 is the **only screen in the product with
no visual design**. Its content is specified; its layout is not.

---

## Assumptions & Open Questions

- The artboards are a point-in-time export. The canvas could not be read
  directly — it is in a different organization from this session — so there is
  no mechanism to notice if it changes. [assumption]
- The `More` bottom-nav item has no artboard; its contents are unspecified.
  [Q4] [assumption]
- Tablet layouts [Q9] are not drawn. The design is at 360×760dp throughout, so
  the Expanded window size class has no visual reference and will be derived at
  implementation. [assumption]
- Landscape is not drawn either, for the same reason. [Q9] [assumption]
- G2's line chart is the only data visualisation in the product and has no
  accessible-alternative specified beyond the table beneath it, which may be
  sufficient. [NFR15] [assumption]
- ~~The design shows reminder state per guardian which implies persistence the
  data model does not have.~~ **Resolved**: FR10.3 records reminders as events
  and FR10.4 has the V1 push write them, so the state is derived from real V1
  data with no SMS capability. [Q12.1]

## Sources

- [design] The user's design canvas, 21 artboards, exported to `claude_design/`.
- [Q1]–[Q11] `refined-mockups-questions.md`.
- [US*], [AC*] `inception/user-stories/stories.md`.
- [FR*], [NFR*] `inception/requirements-analysis/requirements.md`.
