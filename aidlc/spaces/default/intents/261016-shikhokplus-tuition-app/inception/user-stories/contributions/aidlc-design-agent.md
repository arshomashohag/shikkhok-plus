**Collaborator:** aidlc-design-agent

## Contribution

Reviewed `stories.md` and `personas.md` against `requirements.md` (84 FR, 17
NFR), `user-stories-questions.md` (including the Q6.2 device correction), and
the Screens-and-user-input section of the corner checklist. The draft is strong
on behavioural coverage and on deliberately asserting absences. My findings
concentrate where the specification is silent rather than wrong: the guardian
multi-number experience, missing loading/empty/error views, the anonymised
marksheet's actual shape, and Bangla rendering.

---

### 1. Persona fidelity: the Q6.2 correction propagated, with two residues

The correction is applied cleanly in the device rows — all three human personas
read "own phone, not shared" with the `[Q6.2]` tag, and `personas.md` records
the three consequences explicitly. That is the right handling. Two residues
remain:

**1a. P3's tech-comfort line still carries the deleted assumption.** Q5 option D
read "lower than the teacher's, **possibly sharing a device**, and primarily
motivated by fee transparency". Q6.2 killed the sharing clause, but the persona
now reads "Lower than the teacher's. Comfortable with messaging apps, less so
with anything requiring setup". The *sharing* trace is gone — good — but the
persona has silently dropped the confirmed half of D, the **fee-transparency
motivation over academic detail**. That is a behavioural claim the user affirmed
and it shapes guardian story priority: it says Shireen opens the app for money
and only secondarily for marks. Yet her Goals list academic improvement third
and the stories give her US4.4 (progress over time) equal weight with US5.4.
Propose adding to the P3 table or Goals section:

> Her primary motivation is fee transparency — knowing what is owed, what was
> paid, and that it was received — with academic detail valued but secondary
> [Q5.D]. US5.4 and US6.4 are therefore her load-bearing stories; US4.4 is the
> one that makes her feel the money was worth it.

**1b. P1's "what makes him abandon the app" is now the only place a data/device
constraint survives, and it is correctly re-grounded.** No objection. But the
Q6.2 consequence 2 reasoning ("cached reads stay, on narrower grounds —
connectivity not bytes") has **not** propagated into the stories. AC3.4.3 still
justifies cached reads with `[NFR4]` and says nothing about why. That is fine at
this stage, but AC3.1.3 and AC3.4.3 together are now the entire mid-class
connectivity story and they should read as one coherent position. See §6.

**Plausibility for Bangladeshi private tuition**: the personas are plausible. Two
notes.

- **P3 as "the mother"** — the assumption note already covers that a guardian may
  be any adult. Good, and worth keeping, because in this market an **older
  sibling** is a common de facto guardian and may be under 18 themselves. That
  has a compliance edge: a guardian account can itself belong to a minor, and the
  Families declaration reasoning currently treats "under-13 present" as a
  student-side fact only [P2]. Worth one line in P3's assumptions: *a guardian
  account may belong to a minor (an older sibling), so no guardian-only surface
  may assume an adult user*. This is a structural concern, raised per [OC-6].
- **P2's "Frequency: weekly or less — spikes after an exam"** understates the
  Bangladeshi tuition pattern. Students in private batches typically attend 3–6
  sessions a week and the brief's own value proposition for the student is "know
  when the next class is and what was covered" — that is a near-daily check, not
  weekly. If the frequency figure is load-bearing anywhere downstream (caching
  policy, notification volume), it is wrong in the conservative direction. The
  assumption note already flags frequency as inferred; I would additionally
  change P2's frequency to **"Several times a week during term; spikes after an
  exam."**

---

### 2. The guardian multi-number model — this is the worst UX defect in the spec

I agree with the brief's framing. US2.8 states the *behaviour* correctly and is
untestable-free; what is missing is any **explanation surface**, and the failure
mode is precise and predictable:

Shireen's child has two teachers. Teacher A recorded PN1; teacher B recorded PN2
(her husband's number, or an older number she gave eighteen months ago, or a
digit mistyped). She signs in with PN1. She sees one child, one batch. She knows
the child has two teachers. **The app has silently told her it has half her
data.** Her inference is not "my other number reaches the other teacher" —
nobody has ever told her the app is keyed to a phone number per teacher. Her
inference is that the app is broken, or that teacher B is not using it. She
either stops trusting the app (the commercially decisive persona abandoning) or
phones teacher B to complain about a product teacher B did not break. In a
closed-testing pilot of ~100 teachers, this generates support load on a solo
operator who has no admin surface to investigate with [team: Deployment].

Note the near-miss in the current design: FR2.16 shows the recording teacher
against each child in the **selection list**, but FR2.15 sends a guardian with
exactly one reachable child **straight past that list**. So the one piece of
explanatory information the spec does provide is invisible in precisely the case
where confusion is worst — one child, two teachers, one visible batch.

**What the experience should be.** Three layers, cheapest first. All three are
within V1 reach and none requires exposing data across the privacy boundary.

**Layer 1 (necessary, cheap): a persistent, non-modal statement of the scoping
rule, on the guardian's batch list.** Not a one-time onboarding tooltip — she
will not read it, and the confusion arrives weeks later when a second teacher
starts using the app. A permanent footer line on the guardian batch list:

> *Showing what teachers recorded for this number (+880 1X XX XX 45). A teacher
> who recorded a different number for your child appears when you sign in with
> that number.*

The number must be **partially masked** and must be **the number she signed in
with** — which she knows, because she just typed it — so this is self-explanatory
rather than a data disclosure. The phrasing says *what happened* ("showing what
was recorded for this number") and *what to do next* ("sign in with that
number"), which is the error-message standard applied to a non-error state.

**Layer 2 (strongly recommended): make the recording teacher visible always, not
only in the multi-child selection list.** Each batch row on the guardian's list
carries the recording teacher's name. This is already the FR2.16 datum, just
shown in the place she actually lands. It converts "one batch" from an absence
into a positive statement: *this is teacher A's record*. A guardian who sees
"Rafiq Sir — Class 9 Maths" and knows her child also studies with Nasrin Madam
can form the correct hypothesis unprompted.

**Layer 3 (the real fix, and I recommend specifying it in V1): let the guardian
add a second number to her own account, and union the batches.** The privacy
model does not forbid this and the lens model already supports it — the lens is
computed per request from enrollments reachable by the account, and an account
that has **proved ownership of two numbers via two OTP verifications** reaches
the union of both numbers' enrollments. Nothing about the teacher's view changes;
no teacher learns anything new; no row-level-security policy weakens; the
teacher-authored enrollment still names exactly the number the teacher typed.

This is the design that makes the model *correct* rather than explained. The
alternative — explaining a limitation forever — asks every guardian in the
product's life to understand an implementation detail of how teachers type
numbers. Cost: one OTP flow reused, one join widened, and the already-mandated
per-teacher attribution to disambiguate the result.

I recognise this may exceed V1 scope, and it is the mob's call, not mine. So I
propose **Layer 1 and Layer 2 as V1 acceptance criteria** (they close the
"guardian concludes the app lost her data" failure outright) and **Layer 3 as an
explicitly recorded deferral with its design already settled**, so it is not
re-litigated from scratch later. Concretely, replacing the current US2.8:

> ### US2.8 — Guardian understands why she sees the batches she sees
>
> As **a guardian**, I want to see which teacher recorded each batch and that my
> view is keyed to the number I signed in with, so that a missing teacher's batch
> reads as "recorded against another number" rather than as lost data.
>
> - **AC2.8.1** — Given teacher A recorded my number PN1 and teacher B recorded PN2 for the same child, When I sign in with PN1, Then I see teacher A's batch only. [FR2.7] [FR2.18]
> - **AC2.8.2** — Given that situation, When I sign in with PN1, Then the child appears once, not twice. [FR2.18]
> - **AC2.8.3** — Given my batch list, Then each batch names the teacher who recorded it, whether or not a child-selection step occurred. [FR2.16]
> - **AC2.8.4** — Given my batch list, Then a persistent, dismissible-never statement says the view shows what teachers recorded for the number I signed in with, shows that number partially masked, and says that a teacher who recorded a different number appears on signing in with that number. [FR2.7] [A3]
> - **AC2.8.5** — Given exactly one child is reachable and FR2.15 skips the selection step, Then AC2.8.3 and AC2.8.4 still apply, because this is the case in which the absence is least explicable. [FR2.15] [FR2.16]
> - **AC2.8.6** — Given the guardian's own profile, Then no V1 path adds a second verified number to one account; the union-of-numbers design is recorded as deferred. [A3]

AC2.8.5 is the criterion I would least like to see dropped. AC2.8.6 asserts an
absence in the style the draft already uses for AC1.3.3 / AC3.1.4 / AC5.1.5, and
it stops a developer from inventing a half-version of Layer 3.

Assumption A3 should then be **downgraded from unresolved to partly addressed in
the story layer** — AC2.8.3–5 are the mechanism; what stays open is only the
union design.

---

### 3. Missing UX states

The checklist standard is that **loading, empty and error are three different
views, each saying what happened and what to do next**. The draft has two empty
states (AC7.1.5, AC8.1.6) and one error state (AC3.1.3). That is three states
across 30 stories, and the gaps are not uniform — they cluster on exactly the
screens a brand-new pilot user hits first.

**Empty states a real user will hit on day one, with no criterion:**

| Story | Empty case a user actually hits | Why it matters |
|---|---|---|
| US2.6 (student batches) | A student whose only enrollment was deleted, or a claimed number with no live enrollment | Lands on a blank list with no explanation; cannot tell "nothing recorded yet" from "app broken" |
| US2.7 / US2.8 (guardian) | **Zero children reachable** — the mistyped-number case, from the guardian's side | FR2.15 covers one child and two-or-more. **Zero is unhandled.** This is the single most likely first-run state for a guardian whose number a teacher typed wrong, and it is the exact moment a wrong-number sign-in must NOT look like a broken app |
| US3.4 (next class, topics) | New batch: no sessions held, no topics | First screen a student sees after claiming |
| US4.3 (student marksheet) | No exams yet, or exams exist but marksheet toggle off | Distinct cases: "no exams yet" vs. "your teacher does not share marks" [FR4.6]. AC4.2.2 says "no marksheet is shown at all", which is a *removal*, not a stated empty state — a student who saw it last month and not this month needs to know why |
| US5.3 / US5.4 (fee status) | First month before any cycle generates; inactive enrollment with nothing owed | A guardian seeing no fee row before the 1st will assume the fee is zero |
| US6.3 (teacher verifies) | No pending submissions — the **normal** state most days | Teacher opens the verification queue daily and sees blank |
| US6.4 (guardian payment history) | Never submitted a payment | Blank screen next to a visible due amount reads as a failed submission |
| US9.1 (notifications) | No notifications yet | Minor; include for consistency |

The one I would treat as a defect rather than a gap is **zero reachable children**
on the guardian path. Proposed criterion, to go in US2.7:

> - **AC2.7.5** — Given no child is reachable from the number I signed in with, Then I see a defined empty state saying no teacher has recorded this number, naming the number partially masked, and advising me to check the number with my child's teacher — not a blank list and not an error. [FR2.15] [FR2.7]

That single criterion closes the mistyped-number loop from the guardian's side,
which US1.3 currently closes only from the teacher's side.

**Error states missing.** AC3.1.3 is the only failure criterion in the document,
and it is the only one that was *required* by a requirement (FR3.6). But [NFR5]
forbids offline writes **universally**, so every write in the product has the same
failure shape and only one story says so. The writes are: enrollment creation
(US2.2), display-name edit (US2.3), inactive marking (US2.4), enrollment removal
(US2.5), session reschedule/cancel (US3.2), announcement post/edit/delete (US3.3),
exam creation and mark entry (US4.1), visibility toggle (US4.2), charge adjustment
(US5.2), payment submission (US6.1, US6.2), verification approve/reject/correct
(US6.3), profile edit (US1.5), account deletion (US1.6, US1.7). Fourteen stories,
one documented failure path.

Rather than add a near-identical criterion fourteen times, I propose a **single
cross-cutting story** in the US9 cross-cutting group, which the per-story criteria
then reference:

> ### US9.2 — Any user is told when a write failed, and nothing is lost
>
> As **any signed-in user**, I want a failed write to tell me it failed and let me
> retry without re-typing, so that I never believe something was saved when it was
> not.
>
> - **AC9.2.1** — Given any write in the app, When it fails for lack of connectivity, Then a prompt names it a connectivity failure and offers a retry of the same write; nothing is queued silently. [NFR5] [FR3.6]
> - **AC9.2.2** — Given a failed write, Then everything I typed is preserved and the retry re-submits it without my re-entering it. [NFR5] [checklist: unsaved input]
> - **AC9.2.3** — Given a failed write, Then no part of it is shown as saved; the screen does not display the value I attempted until the server confirms it. [TC-9] [NFR5]
> - **AC9.2.4** — Given a write that the server rejected rather than failed to reach, Then the message distinguishes the two: a rejection names the field and the fix and is not retryable as-is; a connectivity failure is retryable. [team: error taxonomy] [NFR5]
> - **AC9.2.5** — Given I submit twice — tapping once, then once again before a response — Then exactly one record results. [FR5.4] [checklist: double submit]
>
> *Note*: AC9.2.3 matters for optimistic-UI drift. A client that paints the value
> before confirmation has, in effect, built the local write queue [TC-8, D-9]
> forbid. AC9.2.4 maps the error envelope's server-provided `retryable` boolean
> [team: error handling] to a user-visible distinction; without it the client
> infers retryability, which [TC-9] forbids.

**AC9.2.5 (double submit) deserves separate emphasis**: payment submission
(US6.1) has a transaction ID and an amount and **no uniqueness criterion**. A
guardian on a slow connection who taps Submit twice can plausibly create two
payment claims for one transaction, which the teacher then approves twice. The
money paths carry mandatory tests [TC-20, D-23] and this is a money path with no
stated constraint. I would add specifically to US6.1:

> - **AC6.1.6** — Given I submit the same transaction ID for the same enrollment twice, Then exactly one pending submission exists and the second attempt tells me the first was already received. [FR6.1] [FR6.2]

**Loading states.** No story mentions one, and I accept that per-story loading
criteria would be noise. But two screens have loading characteristics worth
naming because they are not uniform:

- **AC7.1.4** requires the dues view to render "current data on open with no
  generate step" — that is a *performance posture* with no loading view
  specified. On a 2 GB Lightsail instance aggregating across all batches, this is
  the slowest read in the product. It needs a stated loading view, and it needs
  to be distinguishable from the empty state in AC7.1.5 — a spinner that resolves
  to blank is the classic confusion.
- **AC3.4.3** shows cached schedule "with their age indicated" — that is a stale
  view, the fourth state, and the only one in the document. The checklist asks
  for staleness **and** for *when a refresh failed*; AC3.4.3 covers age but not
  refresh failure. Proposed addition:

> - **AC3.4.4** — Given cached content is shown and a refresh attempt failed, Then the screen says the refresh failed as well as how old the content is, and offers a retry. [NFR4] [checklist: stale data]

I propose the lead add one cross-cutting criterion rather than per-story loading
criteria, plus the AC7.1 pair:

> - **AC7.1.6** — Given the dues view is loading, Then a loading view is shown that is visually distinct from the empty state in AC7.1.5, and a failure to load says so rather than rendering as "nobody owes anything". [FR7.3] [checklist: loading/empty/error]

That last clause is the important one: **a failed load that renders as an empty
state tells a teacher nobody owes him money.** That is a money-adjacent silent
failure in the product's highest-value screen.

---

### 4. AC1.3.3 — the lead is wrong, and the mistyped-number case is why

The reasoning given ("its state does not affect my work") is true of *recording*
and false of *expectation*. Rafiq's second stated goal is "keep the guardian
informed without answering the same question by phone twenty times a month"
[P1]. If he mistyped Shireen's number, he is marking attendance and entering
marks in the belief that she is seeing them. She is not. Nobody will tell him:
AC1.3.2 guarantees no notification ever goes to that number, and US2.8/AC2.7.5
mean Shireen either sees nothing or never signs in at all. **The failure is
mutually invisible to both parties who care about it** — the single worst
property a defect can have.

The counterargument I take seriously is: a dormant enrollment is also the
*normal* state for a legitimately enrolled student who simply has not bothered
to sign in yet, so a "nobody claimed this" marker would decorate most of the
roster during the pilot and become noise. That is real. But it argues for
**where and how** the information appears, not for suppressing it.

The concrete difference: a claim state has two distinguishable reads —

- **Never claimed** (ambiguous: typo, or has not got round to it)
- **Claimed once, then the account was deleted** (AC1.6.2 reverts the enrollment
  to dormant — so "dormant" conflates "never reached anyone" with "reached
  someone who left")

A per-row badge cannot carry that nuance without clutter. My proposal, which I
think is cheaper and more useful than either the lead's position or a per-row
badge:

Replace AC1.3.3 with:

> - **AC1.3.3** — Given a dormant enrollment, When I view the roster, Then the row is not decorated with a status badge, because an unclaimed row is the normal state of a newly enrolled student. [FR1.8]
> - **AC1.3.4** — Given an enrollment whose number has never been signed in with, When I open that enrollment's detail, Then it states that nobody has signed in with that number yet and offers me a path to correct the number. [FR1.8] [FR1.9]
> - **AC1.3.5** — Given an enrollment where a number was claimed and that account was later deleted, When I open the enrollment's detail, Then it is distinguishable from one never claimed, because the correct action differs — re-check the number versus nothing to do. [FR1.8] [FR11.1]

This keeps the roster clean (the lead's legitimate concern), puts the fact where
a teacher goes when he *does* ask "is she seeing this?", and makes the ambiguity
explicit rather than hiding it. The detail screen is already the place the
display name is edited [AC2.3.1], so the number-correction path is adjacent to
where he already is.

**I also think the roster needs one aggregate signal**, not per-row: a batch-level
line such as "9 of 12 numbers have signed in". That is one string, it is noise-free,
it answers the teacher's real question ("is this working?"), and it gives him a
reason to look at the detail screen. I propose it as a criterion but flag it as
the one of these I hold least firmly:

> - **AC1.3.6** — Given a batch roster, Then one line states how many of its recorded numbers have ever been signed in with, without identifying which. [FR1.8]

(The "without identifying which" clause keeps AC1.3.3's clean roster intact and
sidesteps the privacy question of whether a claim event is the student's
information — a count discloses nothing about an individual.)

---

### 5. The anonymised marksheet — "anonymised rows" is not a design

FR4.5 gives two facts: own row named, others' results shown without identity.
AC4.3.1–2 restate them. Nothing says what the viewer actually *sees*, and the
options differ enormously in both usefulness and re-identification risk.

**The re-identification problem is real and is being under-weighted.** A private
tuition batch is 8–20 students who **sit in the same room and know each other's
names**. A list of 12 unattributed marks tells Tanvir almost everything: he knows
who was absent that day (he was there), he knows roughly who is strong, and after
two exams the sort order is stable enough to deanonymise most of the list by
inference. For an under-13-present, Families-declared product [RC-1], shipping
something labelled "anonymised" that is trivially deanonymised by its own
audience is worse than shipping something honestly labelled. The requirements
document itself flags this trade as a pilot judgment; the story layer should at
minimum not overclaim.

Four candidate presentations, with my assessment:

| Option | What Tanvir sees | Value to him | Re-identification | Verdict |
|---|---|---|---|---|
| **A. Unattributed row list** (the literal reading) | 12 rows of marks, his named | "Where do I stand" answered by counting | High, as above | Reject. Maximum disclosure for minimal added insight over C |
| **B. Rank only** | "You placed 4th of 12" | Directly answers the question | Low — one number, no per-student data | Strong |
| **C. Distribution** | His mark on a band histogram (e.g. 0–40 / 41–60 / 61–80 / 81–100, with counts) plus batch high and average | Answers "where do I stand" *and* "was this exam hard" | Low — bands of 3+ only | Strongest |
| **D. Own mark vs. average only** | "You: 72. Batch average: 64." | Thin; an average hides whether he is mid-pack or near the top | Minimal | Insufficient alone |

**My recommendation: C plus B** — own mark named, batch average, batch high, rank,
and a banded distribution. It answers the student's actual question better than
an unattributed list does, it is a better-looking screen, it survives Bangla
text expansion (no name column to overflow), and it discloses materially less.
It also fits [TC-9] naturally: bands, rank and average are all **server-computed
decisions**, where an unattributed row list is raw data the client would be
tempted to sort — which [team: layer boundaries] rule 2 forbids.

One necessary guard: in a very small batch, bands and rank themselves leak. With
4 students, "you placed 2nd of 4" plus the high mark narrows the rest sharply.
Proposed story text replacing US4.3's criteria:

> - **AC4.3.1** — Given a past exam with visibility on, Then I see my own result named, my rank in the batch, the batch average and the batch high mark. [FR4.5]
> - **AC4.3.2** — Given the same exam, Then the rest of the batch is shown only as a banded distribution — counts per mark band — and never as a list of individual unattributed results, so a reader who knows the batch cannot attribute marks by inference. [FR4.5] [RC-1]
> - **AC4.3.3** — Given a band that would contain fewer than three results, Then it is merged with an adjacent band rather than shown alone. [FR4.5] [RC-1]
> - **AC4.3.4** — Given a batch with fewer than five marked results, Then I see my own result and the batch average only — no rank, no high mark, no distribution. [FR4.5] [RC-1]
> - **AC4.3.5** — Given absent and not-yet-entered results, Then they are excluded from the average, the high mark, the rank denominator and the distribution, and the count they were excluded from is stated. [FR4.3] [FR4.5]
> - **AC4.3.6** — Given I am in two batches, Then each exam's comparison covers only that batch's students, never across batches. [FR4.4]
> - **AC4.3.7** — Given rank, average, high mark and distribution, Then all are computed server-side and the client renders them without computing or re-sorting anything. [TC-9] [D-31]

AC4.3.5 is not pedantry: including a not-yet-entered result as a zero in an
average is the exact defect class the draft already guards against in AC4.1.4
and AC4.4.2, and the marksheet is the third place it can occur. It is also the
first place a half-marked exam becomes visible to a student — which raises a
question for the mob: **should a partially-marked exam be visible to students at
all?** AC4.1.4 gives the teacher a "not yet entered" state; nothing says whether
Tanvir sees the marksheet mid-marking and computes a rank from half the batch.
I believe he should not, and propose:

> - **AC4.3.8** — Given an exam where not every enrollment's result is entered or marked absent, Then no comparison is shown to students or guardians; my own result is shown if entered, with a statement that the batch comparison appears when marking is complete. [FR4.3] [FR4.5]

This also fixes a trust problem: a rank that changes from 2nd to 7th as the
teacher finishes marking looks like the app changing the child's result.

If the mob prefers to hold the literal FR4.5 reading, then at minimum AC4.3.2
should state that the unattributed list is **unsorted and in a stable
batch-independent order**, because sorting it by mark converts it directly into a
rank table of the whole batch. But I would record my position as OBJECT in that
case — see Positions.

---

### 6. Mid-class attendance: fast with nothing enforcing it, and a likely mid-roster drop

The situation: P1's defining abandonment risk is attendance being slower than
paper [desc §11]; the speed requirement was deliberately dropped [Q14.3]; AC3.1.4
records the absence; offline writes are forbidden [NFR5]; AC3.1.3 specifies a
retry prompt. The team practice already names this honestly — a Compose
correctness test does not discharge a latency requirement, and the alternative is
a Macrobenchmark or an explicit manual pilot check [team: Testing Posture].

So the UX has to carry what the requirement does not. What matters is not raw
latency but **how many interactions a full roster costs and what a mid-roster
failure costs**. Two design properties do almost all the work:

**6a. Default-present, mark the exceptions.** In a tuition batch of 12, typically
1–2 are absent. If the roster opens with every student unmarked, Rafiq makes 12
decisions and 12 taps. If it opens default-present, he makes 1–2 taps. That is a
6× interaction reduction with no requirement and no performance work, and it is
the single highest-leverage decision available here. The risk is a teacher who
submits without looking, recording a full house — mitigated by the submit
confirmation naming the counts (6b).

**6b. One write for the whole roster, not one per student.** This is the decisive
property for the connectivity failure. Per-student writes mean a mid-roster drop
leaves attendance **half-recorded**, and a retry that re-submits only the failed
tail — so Rafiq cannot tell from the screen which students are saved. A single
batched write for the session is atomic: either the session's attendance is
recorded or none of it is, and AC3.1.3's retry re-sends the whole thing. It also
turns N round-trips into one, which is the latency win nobody has to measure.

**6c. The retry prompt must not be modal and must not lose the roster.** A modal
error dialog mid-class, in front of twenty students, with the marks gone behind
it, is the abandonment moment. A non-blocking banner with the roster still on
screen and still editable, plus a retry button, is the same information with none
of the cost.

Proposed criteria for US3.1:

> - **AC3.1.2** — Given the session roster, When I open it, Then every enrolled student is pre-marked present and I change only the exceptions; attendance is recorded per enrollment on submission. [FR3.5]
> - **AC3.1.5** — Given a marked roster, When I submit it, Then the whole session's attendance is written in one operation — either all of it is recorded or none of it is — so no roster is ever half-saved. [FR3.5] [NFR5]
> - **AC3.1.6** — Given I submit and the write fails, Then the roster stays on screen with my marks intact and editable, the failure is shown as a non-blocking message rather than a dialog that hides the roster, and retry re-submits the whole roster. [FR3.6] [NFR5]
> - **AC3.1.7** — Given I submit, Then a confirmation states how many are recorded present and how many absent, so a roster submitted without being read is visible as such. [FR3.5]
> - **AC3.1.8** — Given attendance already recorded for a session, When I reopen it, Then I see what was recorded and may correct it, and the correction is itself one atomic write. [FR3.5] [FR9.1]

AC3.1.8 matters because a teacher who hits a failure, retries, is unsure whether
it went through, and reopens the session needs to see the truth. Without it he
re-marks the whole roster, which under a non-idempotent write is a duplicate-data
path.

I would also keep AC3.1.4's deliberate absence — it is correct and valuable — but
**sharpen it**, because as written it reads as licence:

> - **AC3.1.4** — Given no speed requirement applies [Q14.3], Then no criterion here asserts a latency bound; the interaction cost is instead bounded structurally by AC3.1.2 (one tap per exception, not per student) and AC3.1.5 (one write per roster). [FR3.5] [Q14.3]

That converts "we dropped the requirement" into "here is what stands in its
place", which is the honest position and the one a developer can implement
against.

---

### 7. Bangla-first reality

NFR3 says Bangla and English from the first screen, device-locale driven with
English fallback; the personas imply Bangla is the real primary. Nothing in
`stories.md` assumes English-first in so many words — no story names an English
label — but **four things in the criteria will break or mislead in Bangla**, and
none is currently stated.

**7a. Numerals.** Bangla locale conventionally renders digits as Bengali numerals
(১২৩). The product is full of numbers that must be *typed and read back
exactly*: the phone number (AC1.1.1), the OTP (AC1.1.2), the transaction ID
(AC6.1.1), and every money amount. A transaction ID or a bKash number shown in
Bengali numerals that the guardian must compare against her SMS receipt in Latin
digits is a transcription error generator. And money is already locked to a
server-side `Money.format(locale)` [team: Code Style], so this is a decision the
server makes once and no story currently constrains. Proposed:

> - **AC-i18n.1** — Given Bangla locale, Then phone numbers, OTP codes and transaction identifiers are rendered in Latin digits, because the user must compare them character-for-character against an SMS. [NFR3]
> - **AC-i18n.2** — Given Bangla locale, Then money amounts render with the locale's digits, separators and currency presentation as the server formats them, and the same amount renders identically on every screen it appears on. [NFR3] [TC-7] [checklist: same fact in two places]

**7b. Dates.** Due dates, exam dates, session dates and "whole days remaining"
(AC8.1.5) all appear. Bangla date formatting differs in order and in month names,
and the fee due-day clamp (AC2.1.2) is month-length arithmetic the user must be
able to verify by eye. Also worth stating: the calendar is Gregorian, not Bangla
Sôn — a teacher who sets "due day 29" means the Gregorian 29th, and showing a
Bangla-calendar date beside it would be a genuine money-adjacent ambiguity.

> - **AC-i18n.3** — Given either locale, Then all dates are Gregorian and rendered in the locale's conventional format; no Bangla-calendar date is shown anywhere a fee period, due date or exam date appears. [NFR3] [FR5.2]

**7c. Name ordering and the display-name field.** The teacher types the display
name [AC2.2.1], so the app imposes no ordering — good, and it means Bangla names
work by construction. But the **private profile name** (AC1.5.1) and the typed
display name can be in different scripts, and AC1.5.2 guarantees the teacher
still sees the typed one. That is correct. The gap is **sorting**: AC7.1.1 lists
everyone who owes money, AC2.6.1 lists batches, AC2.7.3 lists children. Nothing
says what order, and Bangla collation is not Latin collation. Per [team: layer
boundaries] rule 2 the server decides order anyway, so:

> - **AC-i18n.4** — Given any list of people or batches, Then the server decides the order and applies locale-appropriate collation for Bangla and English; the client never re-sorts a domain list. [NFR3] [TC-9]

**7d. Text expansion, and the one place it is genuinely dangerous.** Bangla runs
roughly 15–30% longer than English and needs more vertical space for conjuncts
and matras. The team practice already requires a verifier (screenshot tests at
the longest Bangla string, or a per-screen manual check), so the mechanism exists.
What the stories should name is **which screens are at risk**, because that is
the per-screen checklist the verifier needs:

1. The **attendance roster** (US3.1) — the densest screen, with a name plus two
   controls per row, and the one where a wrapped row costs mid-class seconds.
2. The **marksheet** (US4.3) — a table; tables are where expansion breaks worst.
   This is a further argument for §5's distribution design over a row list.
3. The **cross-batch dues view** (US7.1) — name, batch name, amount on one row.
4. The **OTP screen** (US1.1) — the skeleton screen, and the team practice
   already requires both bundles present there [team: Walking Skeleton].
5. The **error and empty strings** proposed in §3 — the longest strings in the
   product are explanatory, and they are the ones nobody screenshots.

> - **AC-i18n.5** — Given Bangla locale, Then the attendance roster, the marksheet, the cross-batch dues view, the OTP screen and every empty, loading and error view render the longest Bangla string for each element without truncation, overlap or loss of a tappable control. [NFR3] [TC-15] [D-43]

I would group AC-i18n.1–5 as a single cross-cutting story in US9 rather than
scattering them, consistent with the lead's US9 treatment:

> ### US9.3 — Any user uses the app in their own language
>
> As **any user**, I want the app in Bangla or English according to my phone, so
> that I am not reading a second language to find out what my child owes.
>
> (criteria AC-i18n.1–5 above, renumbered AC9.3.1–5)

I note this cuts against Q4's answer A (no NFR stories). I do not think it
violates it: Q4 asked whether the *17 NFRs get stories*, and the lead already and
correctly made exceptions where an NFR has user-visible behaviour inside a
criterion (NFR4 in AC3.4.3, NFR5 in AC3.1.3, NFR13 in AC1.1.2). NFR3's
user-visible behaviour is larger than one criterion's worth, which is why I
propose a story rather than another inline tag. If the mob holds Q4-A strictly,
these belong as criteria distributed across US1.1, US3.1, US4.3, US6.1 and US7.1
instead, and I would accept that — the content matters, the packaging does not.

---

### 8. Accessibility

NFR15 says "accessibility basics and correct back-stack behaviour", which is
the vaguest requirement in the document, and the stories mention neither.

**On whether that is correct for this stage**: mostly yes. Contrast ratios, touch
target sizes, focus indicators and ARIA/content-description specifics belong in
Refined Mockups (2.5) and NFR Requirements (3.2), not in acceptance criteria.
Putting "4.5:1 contrast" in a user story would be exactly the implementation
detail the INVEST table says these stories correctly avoid.

**But three accessibility concerns are story-level, not design-level**, because
they are about *what information exists*, not how it is styled — and if they are
not in the story, there is nothing for a mockup to style:

**8a. Status is conveyed by colour alone — a real risk in this product, not a
generic one.** The fee status "paid / partly paid / unpaid" (AC5.3.1, AC5.4.2,
AC6.4.1) is the archetypal green/amber/red badge, and attendance present/absent
is the archetypal green tick / red cross. Roughly 8% of men have a red-green
colour vision deficiency; Rafiq and Tanvir are both plausibly in that group, and
the guardian is reading **money status**. The checklist states it plainly:
*status is never shown by colour alone*. This is also already half-solved
server-side: [team: layer boundaries] rule 1 requires the server to send
`status: "due" | "paid" | "partial"` as an enum rather than letting the client
compare a balance. So the text is already arriving; the story just has to require
that it be shown.

> - **AC9.4.1** — Given any status shown in the app — fee paid/partly paid/unpaid, attendance present/absent, payment pending/approved/rejected — Then it is conveyed by text or by an icon with a text label, never by colour alone. [NFR15] [checklist: contrast]

**8b. Back-stack behaviour is named in NFR15 and has two genuinely ambiguous
cases in these stories**, both of which are "user control and freedom" rather
than styling:

- **Lens switching** (AC1.2.4) and **child switching** (AC2.7.4) change the whole
  view without re-authenticating. What does Back do afterwards? If it returns to
  the previous lens's screen, the user is looking at another child's data having
  pressed Back once, which in a product whose entire point is a privacy boundary
  is a bad surprise. If it exits the app, she loses her place.
- **Account deletion** (US1.6) is irreversible and the draft says "I request
  deletion and confirm" with no statement of what the confirmation says.

> - **AC9.4.2** — Given I switched lens or switched child, When I press Back, Then I return within the currently selected lens or child, never into the previous lens's or child's data. [NFR15] [FR1.5] [FR2.17]
> - **AC1.6.4** — Given I request account deletion, Then the confirmation names in my own language what will be removed and what the teacher's records retain, and deletion requires a distinct confirming action rather than a single tap. [FR1.14] [RC-5] [checklist: destructive action]

AC1.6.4 is not only accessibility: [RC-5] already requires the privacy policy to
state what is retained, and AC1.6.2 already specifies that teacher-authored
records survive. A user who deletes expecting everything to go and later learns
her child's marks remain has been misled by a confirmation dialog, which is a
compliance exposure and not merely a UX one.

**8c. One thing worth recording as explicitly deferred**, so Refined Mockups
knows to pick it up rather than assuming it was considered: the OTP screen
(US1.1) is the only screen every user must pass, it is time-bounded at five
minutes, and it involves transcribing digits from an SMS. It is the highest-risk
accessibility screen in the product (TalkBack announcement of a per-digit code
field, auto-advance behaviour, the SMS Retriever autofill path, and the
five-minute limit against a slow typist). Proposed as an open question rather than
a criterion:

> - OTP entry accessibility — per-digit field announcement, autofill interaction,
>   and whether a five-minute window is sufficient for a screen-reader user — is
>   deferred to Refined Mockups (2.5) and NFR Requirements (3.2). Recorded so it
>   is picked up rather than assumed. [NFR15] [NFR12] [assumption]

I propose AC9.4.1–2 as a short US9.4 ("Any user can use the app without relying
on colour, and Back behaves predictably"), or as criteria folded wherever the lead
prefers.

---

### Summary of proposed changes

| # | Change | Strength |
|---|---|---|
| 1 | P3 gains the confirmed fee-transparency-primary motivation; P2 frequency raised; one line that a guardian may be a minor | Should |
| 2 | US2.8 rewritten: per-batch teacher attribution always, persistent scoping statement, applies in the single-child case; union-of-numbers recorded as deferred-with-design | **Must** |
| 3 | US2.7 gains the zero-reachable-children empty state; new US9.2 cross-cutting write-failure story; AC6.1.6 double-submit; AC7.1.6 loading-vs-empty; AC3.4.4 refresh-failed | **Must** (AC2.7.5, US9.2, AC7.1.6, AC6.1.6) |
| 4 | AC1.3.3 kept for the roster but AC1.3.4–5 added on the enrollment detail; AC1.3.6 aggregate count | **Must** (1.3.4–5); AC1.3.6 Should |
| 5 | US4.3 rewritten as rank + average + high + banded distribution with small-batch guards, excluded absents, and no comparison until marking completes | **Must** |
| 6 | US3.1 gains default-present, atomic roster write, non-modal retry preserving marks, submit confirmation with counts, reopen-and-correct; AC3.1.4 sharpened | **Must** (3.1.5, 3.1.6); others Should |
| 7 | New US9.3: Latin digits for phone/OTP/transaction ID, Gregorian dates only, server-side locale collation, named text-expansion screens | **Must** (Latin digits, Gregorian) |
| 8 | AC9.4.1 status never colour-alone; AC9.4.2 Back after lens/child switch; AC1.6.4 deletion confirmation names what is retained; OTP accessibility deferred explicitly | **Must** (9.4.1, 9.4.2, 1.6.4) |

## Positions

- AGREE: Grouping by proto-Unit rather than by persona — it matches the delivery sequence and keeps each group independently demonstrable, which grouping by persona would destroy.
- AGREE: One story per actor [Q2-A] — the privacy asymmetry is the product, and a single multi-actor story would bury it in criteria.
- AGREE: Deliberately asserting absences (AC3.1.4, AC5.1.5) — an unstated absence does get implemented as its opposite; this is the right technique and I extend it in AC2.8.6 and a sharpened AC3.1.4.
- AGREE: The persona set, including P4 with no stories, and the Q6.2 device correction's propagation into the device rows.
- AGREE: No stories for the 17 NFRs as a general rule [Q4-A], with the lead's existing practice of tagging user-visible NFR behaviour inside criteria.
- AGREE: US8.1 is too large and should split — four distinct views behind six criteria is not estimable, and the dashboard-is-one-screen argument is a UI fact, not a story boundary.
- OBJECT: AC1.3.3 as the whole treatment of dormant state — the mistyped-number case leaves a teacher believing a guardian is informed when nobody is, invisibly to both; the fact belongs on the enrollment detail even if the roster row stays undecorated.
- OBJECT: US2.8 as written — it states the behaviour and leaves the guardian with no way to interpret a missing batch; per-batch teacher attribution and a persistent scoping statement must apply in the single-child case, which is exactly where FR2.15 currently removes the only explanatory datum.
- OBJECT: AC4.3.2's unattributed row list — in an 8–20 student batch whose members know each other, it is deanonymised by inference while adding little over a rank and a distribution, and it is the weakest choice for a Families-declared product. Rank plus banded distribution answers the student's question better and discloses less.
- OBJECT: One documented failure path (AC3.1.3) for fourteen write stories under a universal no-offline-writes rule — the failure shape is uniform, so it needs one cross-cutting story, not silence.
- OBJECT: No empty state for zero reachable children — this is the guardian-side face of the mistyped number and the most likely first-run state for an affected guardian; a blank list there reads as a broken app.
- OBJECT: Silence on a failed load of the dues view — rendering a load failure as the AC7.1.5 empty state tells a teacher nobody owes him money, which is a silent failure in the highest-value screen.
- OBJECT: No story-level constraint on Bangla numerals — rendering an OTP or a bKash transaction ID in Bengali numerals, which the user must compare character-for-character against an SMS, is a transcription-error generator and a one-line decision to get right now.
- OBJECT: Complete silence on accessibility — contrast and ARIA belong downstream, but colour-only status, Back behaviour after a lens or child switch, and what a deletion confirmation discloses are story-level facts, and the last is a compliance exposure under [RC-5].
