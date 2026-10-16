# Scope Definition & Prioritization — Clarifying Questions

**Stage**: scope-definition (1.4)
**Phase**: Ideation
**Depth**: Comprehensive

## Sources

- [desc] Initial description, including §2 (scope), §6–§9 (per-persona features) and §13.4 (stated slice order).
- [scope] Workflow-selected scope: `classic`.
- [upstream] `ideation/intent-capture/intent-statement.md` — approved V1 boundary and the ten architecture-constraining decisions.
- [upstream] `ideation/feasibility/feasibility-assessment.md` — risk analysis, including R-1 (timeline) and the verified Play closed-testing requirement.
- [upstream] `ideation/feasibility/constraint-register.md` — 20 technical, 7 organisational and 8 regulatory constraints.

---

## Note on what is NOT asked here

The following are already settled and are not re-opened:

- The in/out boundary [intent: Initial Scope Signal] — coaching centres, tutor
  marketplace, batch messaging, PWA, PDF export, private messaging and
  multi-device session management are out; attendance, push notifications and a
  teacher analytics dashboard are in.
- The slice order [desc §13.4] — auth and identity → batches and enrollment →
  schedule and sessions → exams and marksheets → fee cycles → payment
  submission and verification → dues screen.
- Sequencing preference — the stated order is already dependency-first, and the
  feasibility assessment recommends narrowing rather than extending (R-1).
- Scale ceiling, budget and timeline [feasibility: Q3, Q4, Q9].

What remains genuinely open is where the **first testable release** cuts, now
that Play's closed-testing requirement is known.

---

## Q1. Where does the first closed-testing release cut?

Play requires 12 testers opted in continuously for 14 days before a personal
developer account can apply for production access [feasibility: D-6]. The clock
starts when a working build reaches testers, so the earliest sensible strategy
is to ship something usable early and let the 14 days run while later slices are
built.

That makes "what is the smallest build a pilot teacher would actually use for a
real batch?" the decisive scope question. A build that cannot run a real class
produces no useful feedback and wastes the 14-day window.

- A. Slices 1–3 (auth, batches and enrollment, schedule and sessions including attendance) — a teacher can set up a batch, add students, and run and record real classes. No money, no exams
- B. Slices 1–4 (adds exams and marksheets) — teaching is fully covered; money is not
- C. Slices 1–5 (adds fee cycles) — teachers see dues but cannot record payments
- D. All seven slices — nothing reaches testers until the product is complete
- X. Other (please specify)

[Answer]: D

---

## Q2. Which of the three app surfaces must be in the first testing release?

The teacher app is obviously required. The student and guardian views are
read-only and depend on teacher-entered data existing, so they could follow.
But the guardian is the party whose satisfaction drives renewal
[intent: Target Customer], which argues for exposing them early.

- A. Teacher app only — students and guardians come in a later test release
- B. Teacher app plus guardian view — the guardian is the renewal driver, so their experience needs real-world validation earliest
- C. Teacher app plus both student and guardian views — all three from the first release
- X. Other (please specify)

[Answer]: C

---

## Q3. Push notifications were kept in V1 — where do they sit in priority?

You kept push notifications in scope [intent: Q12] while excluding PDF export
and messaging. They carry server-side delivery infrastructure (FCM integration,
token lifecycle, per-event triggering) that the excluded features do not, and
FCM needs checking against the no-device-identifier constraint [TC-3].

This is the one in-scope item whose cost I think is underestimated relative to
its adjacency to "small features".

- A. Must Have in V1 — fee reminders and new-marks alerts are core to the guardian value proposition
- B. Should Have — build if the timeline allows, after the seven slices work
- C. Could Have — defer to V2; guardians open the app rather than being pushed to
- D. Keep in V1 but narrow it to one event type only (specify which: fee due, payment approved, new marks, class cancelled)
- X. Other (please specify)

[Answer]: A

---

## Q4. The teacher analytics dashboard was kept in V1 — same question.

You kept this in scope too [intent: Q12]. Your §6 already includes the
cross-batch dues screen, which is the highest-value analytical view and is
separately mandated as a first-class feature. A broader analytics dashboard
(income over time, student performance trends) is additional.

- A. Must Have in V1 — specify what it must show
- B. Should Have — after the seven slices
- C. Could Have — the cross-batch dues screen already covers the essential analytical need; defer the rest
- D. Narrow it to monthly earnings totals only, derived from the fee ledger
- X. Other (please specify)

[Answer]: A

---

## Q5. Is there any capability whose absence would make a pilot teacher abandon the app?

The feasibility assessment records R-7: attendance marking requires
connectivity, which may fail mid-class. Beyond that, I want to know whether
anything else is a hard floor from the teacher's point of view — something
where a workaround is unacceptable rather than merely annoying.

(Select all that apply.)

- A. Nothing beyond what slices 1–3 provide
- B. Editing a student's display name — the "my name is spelled wrong on the marksheet" case [desc §6]
- C. Marking a student inactive from a date, so fee cycles stop
- D. Per-student fee override
- E. Cancelling or rescheduling a session
- X. Other (please specify)

[Answer]:C

---

## Q6. How should the dues screen's scope be bounded for V1?

Your §6 calls the cross-batch dues screen the strongest justification for the
subscription and insists it is a first-class feature, not a report. It is also
the last slice in the stated order, which means it is the most likely casualty
if the timeline slips.

- A. Keep it last but treat it as non-negotiable — the release is not complete without it
- B. Move it earlier, right after fee cycles, since it is the subscription justification
- C. Keep it last, and accept a simpler first version (list of who owes what, no filtering or sorting) with refinement later
- X. Other (please specify)

[Answer]: A

---

## Q7. Resolving the scope-versus-timeline conflict (follow-up to Q1–Q6)

The six answers above together contradict the one-month closed-testing target
recorded at feasibility [feasibility: Q4]. Every item is Must Have, nothing
moved to V2, all three surfaces are in the first release, and nothing reaches a
tester until the complete product works (Q1 = D). Against a solo build with
agent-written code, Bangla and English throughout, the Play compliance
deliverables, and no declared Android experience, that scope does not fit one
month. Q1 = D additionally means Play's 14-day/12-tester clock starts only after
the full build is finished, making it additive to the schedule rather than
overlapping it.

Asked which constraint gives: the one-month target, or the
everything-before-testing rule.

- A. Keep full scope, extend the timeline
- B. Keep full scope, ship to testers incrementally so the 14-day clock overlaps
- C. Keep one month, defer push notifications and the analytics dashboard to V2
- D. Keep one month, narrow the first production release to slices 1–5
- X. Other (please specify)

[Answer]: A. Keep full scope, extend the timeline. No feature is cut and nothing
moves to V2; every item in Q1–Q6 remains Must Have. The one-month target
recorded at feasibility is superseded: planning proceeds against a realistic
estimate for a complete build, plus Play's 14-day closed-testing period before
production access. The timeline is the variable; scope is fixed.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- First production release contains all seven slices. Nothing reaches testers
  until the complete product works.
- All three surfaces — teacher, student and guardian — are in that first
  release.
- Push notifications are Must Have: fee reminders and new-marks alerts are core
  to the guardian value proposition.
- The teacher analytics dashboard is Must Have.
- Marking a student inactive from a date is the capability whose absence would
  make a pilot teacher abandon the app, beyond what slices 1–3 provide.
- The cross-batch dues screen stays last in the slice order and is
  non-negotiable: the release is not complete without it.
- Scope is fixed and the timeline is the variable. The one-month closed-testing
  target recorded at feasibility is superseded. No feature moves to V2.
- Consequence recorded as a risk: with every item Must Have and no Should or
  Could tier, there is no prioritization buffer, so any slip hits the date
  directly rather than being absorbed by dropping lower-priority work.
- Consequence recorded as an estimate, not a commitment: a realistic range is
  8–12 weeks of build before the 14-day Play testing window opens. Narrowing
  that range further would be false precision given the client-side
  unfamiliarity. Delivery Planning sequences the slices.

[Answer]: Looks correct

---
