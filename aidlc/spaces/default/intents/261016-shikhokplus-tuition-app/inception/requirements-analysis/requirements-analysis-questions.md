# Requirements Analysis — Clarifying Questions

**Stage**: requirements-analysis (2.3)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [desc] Initial description, including §3–§10.
- [scope] Workflow-selected scope: `classic`.
- [upstream] `ideation/intent-capture/intent-statement.md` — approved intent and the ten architecture-constraining decisions.
- [upstream] `ideation/scope-definition/scope-document.md` — the fixed V1 boundary.
- [upstream] `ideation/scope-definition/intent-backlog.md` — 8 proto-Units, ~70 capabilities.
- [upstream] `inception/practices-discovery/team-practices.md` — affirmed practices, now governing rules.
- [corner] `.claude/knowledge/aidlc-product-agent/corner-checklist.md` — the condition sweep required at Comprehensive depth.

---

## What this stage is for, and what it is not re-asking

Your specification is unusually complete, so this stage is **not** asking what
to build. It is doing the thing that finds the defects which survive a careful
specification: sweeping each component against the conditions it touches —
empty lists, boundary dates, a value containing the format's own delimiter, two
spellings of one thing, a store that is briefly unreachable.

Most corners below I can settle myself with a stated default, and those become
requirements or assumptions you can correct rather than questions. **These are
the ones that depend on a fact about your world that I cannot know**, plus the
two items this stage owes you from earlier.

---

## Q1. What does the teacher analytics dashboard show?

This is the last undefined Must Have, and it is the only V1 item I cannot size.
It was kept in scope at intent capture and confirmed Must Have at scope
definition, but nothing specifies its content. Your §6 already includes the
cross-batch dues screen, which is the highest-value analytical view and is
separately mandated.

(Select all that apply.)

- A. Monthly earnings total, derived from the fee ledger — what was actually received this month across all batches
- B. Earnings over time — a trend across months
- C. Collection rate — proportion of what was charged that was actually received, per month or per batch
- D. Per-batch comparison — which batches earn most, which have the worst collection
- E. Student performance trends — exam marks over time, per batch or per student
- X. Other (please specify — or "A only", the smallest useful version)

[Answer]:

---

## Q2. What are the numeric targets for the three success metrics?

Carried from intent capture, where the measures were confirmed but the
thresholds were not. Requirements must be verifiable, and these three currently
cannot be: "reduce overdue balances" has no pass or fail. Each needs a number
and a timeframe, or an explicit decision that it stays directional for now.

- A. Teacher retention: ___ teachers still active 3 months after onboarding (give a number)
- B. Guardian engagement: ___% of guardians open the app at least monthly (give a percentage)
- C. Collection improvement: ___% reduction in overdue balances versus the paper baseline (give a percentage)
- D. All three stay directional for V1 — closed testing with 12 teachers is too small a sample for a percentage to mean anything, so judge by qualitative feedback and set targets after launch
- X. Other (please specify — give whichever numbers you have and mark the rest directional)

[Answer]:

---

## Q3. When a student's enrollment ends mid-period, what happens to that period's fee?

`inactive_from` is a date, not a boolean, and your §6 says marking a student
inactive stops future fee cycles while leaving existing dues standing. What is
unspecified is the period the date falls inside. A student marked inactive from
the 10th, in a month whose cycle was already generated on the 1st, has a full
month's fee sitting against ten days of teaching.

This is the single most likely source of a real fee dispute in the product, and
no answer is obviously right — it depends on how teachers in your market
actually behave.

- A. The generated cycle stands in full — the teacher adjusts it manually if they want to, using the ledger's existing charge-adjustment path
- B. The cycle is automatically prorated by days taught when the student goes inactive mid-period
- C. The cycle is voided entirely if the student goes inactive before a stated day of the period (specify the day)
- D. The teacher is prompted to choose at the moment they mark the student inactive, per student
- X. Other (please specify)

[Answer]:

---

## Q4. Can a teacher edit or delete a fee cycle, a payment approval, or a recorded mark after the fact?

Your §6 requires logging who approved a payment and when, because that screen
generates disputes. That implies the record is durable. But teachers make
mistakes — approving the wrong amount, entering a mark against the wrong
student — and a system with no correction path gets worked around.

The tension is between an audit trail that means something and a teacher who
can fix their own error.

- A. Corrections are new entries, never edits — an approval can be reversed by a compensating entry, and the original stays visible in the history
- B. Edits are allowed and overwrite the record, with the previous value kept in an audit log the teacher cannot see
- C. Edits are allowed within a time window (specify how long), after which only compensating entries are possible
- D. Marks and fee cycles are freely editable; payment approvals are append-only because they are the dispute surface
- X. Other (please specify)

[Answer]:

---

## Q5. Can a teacher remove a student from a batch entirely, as distinct from marking them inactive?

Marking inactive is specified. Removal is not, and the two differ in what
happens to history: an inactive student keeps their attendance, marks and fee
record; a removed one raises the question of whether those disappear. It also
matters for the mistyped-number case — a teacher who typed a wrong number
creates an enrollment that will never activate.

- A. No removal at all — inactive is the only exit, and a mistyped enrollment stays dormant forever as the correct failure mode
- B. Removal allowed only while the enrollment is dormant and has no attendance, marks or fee history; otherwise inactive is the only option
- C. Removal always allowed, and it hides the enrollment from the teacher while retaining all records for the student and guardian
- D. Removal always allowed and it hard-deletes everything
- X. Other (please specify)

[Answer]:

---

## Q6. Two teachers record different guardian numbers for the same student. Which guardian sees what?

Your §10 states guardian capture is per enrollment, and that two teachers
holding different guardian numbers for one student is legitimate — neither is
wrong. The consequence needs stating: guardian A, recorded by teacher A, and
guardian B, recorded by teacher B, are two different accounts both claiming the
same child.

- A. Each guardian sees only the batches of the teacher who recorded them — strict per-enrollment scoping, so neither sees the other's batches
- B. Each guardian sees all of that child's batches, across all teachers
- C. Each guardian sees only their own teacher's batches, but the child's name and the existence of other batches is visible
- X. Other (please specify)

[Answer]:

---

## Q7. What happens when a teacher enters a phone number that is already a teacher's account?

One number is one account forever, and role is a lens. So a teacher can enter a
number that already owns batches — perhaps a colleague, perhaps their own
number by mistake. The lens model handles it technically: that account simply
gains a student lens. Whether it should is a product question.

- A. Allowed with no special handling — the account gains a student lens, and the role switcher shows both
- B. Allowed, but warn the teacher that this number already belongs to a teacher before confirming
- C. Blocked — a number that owns batches cannot be enrolled as a student
- D. Allowed, except a teacher cannot enroll their own number in their own batch
- X. Other (please specify)

[Answer]:

---

## Q8. What does a student or guardian see about a batch they were removed from, or a teacher who stopped teaching?

Your §5 lets a student hide an inactive batch from their own list. What is
unspecified is what happens to data when the teacher's side changes: a batch
marked inactive by the teacher, a teacher who stops using the app, or a teacher
whose subscription lapses (deferred, but the data question is now).

- A. Everything stays visible and read-only forever — history is the student's and guardian's record too
- B. Visible until the student hides it; the teacher cannot remove it from their view
- C. An inactive batch becomes read-only and is collapsed by default, but all history remains reachable
- D. Marks and attendance stay; fee history stays; announcements and schedules disappear once the batch is inactive
- X. Other (please specify)

[Answer]:

---

## Q9. Exam marks: what can be absent, and how is absence shown?

Your §10 has `ExamResult(exam, enrollment, marks)` with a marksheet showing all
students in the batch. The corners: a student who did not sit the exam, a
student who joined after the exam, a mark not yet entered, and a zero.

"Absent", "not yet entered", "joined later" and "scored 0" are four different
things that a single nullable number cannot distinguish — and on a marksheet
visible to the whole batch, confusing them is visible to everyone.

(Select all that should be distinguishable.)

- A. Absent — sat no exam, shown as "Absent" rather than a mark
- B. Not yet entered — the teacher has not finished marking, shown as "—" or similar
- C. Joined after the exam — not applicable for this student, shown as blank
- D. Exempted or excused by the teacher
- E. Only a mark or nothing is needed; a blank is sufficient for every case
- X. Other (please specify)

[Answer]:

---

## Q10. Does the batch marksheet show every student's name, or only ranks and marks?

Your §7 says students see the full marksheet of all students in that batch, and
§10 makes it a per-batch toggle defaulting on, noting that showing everyone's
marks is normal and motivating in this market. The remaining question is
whether names are attached.

This matters because it is children's data visible to other children's
guardians, and because the Families declaration makes children's-data exposure
a compliance question as well as a product one.

- A. Names and marks, as the teacher typed the display names — normal in this market and what makes it motivating
- B. Marks with the viewer's own row named and others anonymised — shows standing without exposing named marks
- C. Teacher chooses per batch, alongside the existing visibility toggle
- X. Other (please specify)

[Answer]:

---

## Q11. Is there any requirement on how fast the teacher's mid-class path must be?

§11 says a teacher needing more than a few seconds per class to mark attendance
will abandon the app, which is the clearest performance statement in the brief
but not yet a number. The practices already note that a Compose UI test asserts
behaviour rather than latency, so this needs a measurable target to be
verifiable at all.

- A. Marking a full batch's attendance completes in under 10 seconds on a low-end device over a 3G connection (specify a different number if you prefer)
- B. Each individual attendance tap acknowledges within 500ms locally, with the network write confirmed asynchronously
- C. No numeric target — "feels fast" judged by pilot teachers is sufficient for V1
- D. A target, but set it after the first Android slice exists and can be measured
- X. Other (please specify)

[Answer]:

---

## Q12. What should happen when the SMS gateway is down or an OTP never arrives?

The gateway is a third-party dependency with no fallback in the architecture,
and it sits in front of the only way into the app. A teacher who cannot receive
an OTP cannot use the product at all.

- A. Retry the same OTP request after a cooldown, with the rate limit still applying — and show the user that delivery failed rather than that the code was wrong
- B. As A, plus a "resend" that the user can trigger once the cooldown expires
- C. As B, plus a documented manual path for the closed-testing group — you can activate a known tester out-of-band if delivery fails
- D. Nothing specific — a failed send is a generic error and the user tries again later
- X. Other (please specify)

[Answer]:

---

## Q13. Is a guardian allowed to submit a payment for a batch they are not recorded against?

The payment form resolves batch to enrollment to open fee cycle. A guardian
sees only their own children's batches, so the normal path is safe. The corner
is a guardian with two children in the same teacher's different batches, who
selects the wrong child's batch — the payment lands against the wrong
enrollment and the wrong fee cycle.

- A. The form requires selecting the child first, then that child's batch, so a wrong-child payment is not reachable
- B. Batch selection shows the child's name alongside the batch name, and submission shows a confirmation naming both
- C. Both A and B
- D. No special handling — the teacher catches it at verification and rejects it
- X. Other (please specify)

[Answer]:

---
