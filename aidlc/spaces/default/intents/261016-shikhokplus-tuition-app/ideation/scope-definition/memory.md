# Stage Memory — Scope Definition & Prioritization

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — The stage file's reference questions (minimum viable scope,
  must-have vs nice-to-have, dependencies, sequencing preference, deadlines) are
  almost entirely answered already: the in/out boundary was settled at intent
  capture, the seven-slice order is stated in the initial description §13.4 and
  is already dependency-first, and budget/timeline/scale came from feasibility.
  The protocol forbids re-asking an answered question, so I asked only what is
  genuinely open.
- 2026-10-17 — What IS open changed because of the Play finding: 12 testers for
  14 continuous days means the first release is a scope decision with a
  deadline attached, not just a priority ordering. Reframed the stage around
  "where does the first testable release cut?" rather than generic MoSCoW.
- 2026-10-17 — Read "attendance" as belonging to slice 3 (schedule and
  sessions) rather than as its own slice. It is per-session and per-enrollment,
  so it attaches to the session entity the slice already creates. The user's
  stated seven-slice order did not mention attendance because it was added
  later at intent capture Q5.

## Deviation

- 2026-10-17 — Asked 6 questions rather than the Comprehensive 8-12 guideline.
  Padding to reach the range would have meant re-asking settled questions, which
  the protocol explicitly forbids and which the user would rightly resent after
  answering 20 at intent capture and 12 at feasibility. Coverage, not count, is
  the bar.
- 2026-10-17 — Q3 and Q4 revisit two items the user explicitly kept IN V1 at
  intent capture (push notifications, teacher analytics dashboard). This is not
  re-asking an answered question: the earlier answer settled in-or-out, and
  these ask for priority within V1, which is this stage's own subject. Both are
  flagged because I think their cost is underestimated relative to how small
  they sound.

## Tradeoff

- 2026-10-17 — Considered proposing a reordering of the seven slices (moving the
  dues screen earlier, since it is the stated subscription justification yet
  sits last and is therefore the most likely casualty of a slip). Did not impose
  it; offered it as Q6 option B instead. The stated order is dependency-correct
  — dues needs fee cycles to exist — so moving it earlier means moving fee
  cycles earlier too, which has knock-on effects the user should weigh rather
  than have decided for them.

## Deviation

- 2026-10-17 — The user answered all six questions at maximum scope: all seven
  slices before testing, all three surfaces, push and analytics both Must Have,
  dues screen non-negotiable. Together these contradicted the one-month target
  recorded at feasibility. Rather than silently plan an impossible schedule or
  quietly narrow scope, named the conflict explicitly and asked which constraint
  gives. The user chose to extend the timeline and keep every feature. Recorded
  as Q7.
- 2026-10-17 — Produced a single-tier MoSCoW backlog, which the prioritization
  guidance explicitly warns against ("if everything is a Must Have, you have not
  prioritized"). This is the user's decision, so the backlog is ordered by
  dependency instead and the absence of a buffer is recorded as an accepted
  risk. Did not use WSJF or RICE: both rank items to decide what to drop, and
  with nothing droppable they would produce scores that change no decision.
- 2026-10-17 — Q1 = D (nothing to testers until complete) makes Play's
  14-day/12-tester clock additive rather than parallel, costing roughly two
  weeks of calendar time for no scope gain. Pointed this out at the conflict
  question; the user chose to extend the timeline rather than ship
  incrementally. Recorded as an accepted scope risk, not re-litigated.

## Open question

- 2026-10-17 — Carried forward and still open: success-metric numeric targets
  (due at Requirements Analysis), the teacher-vs-teacher privacy boundary (due
  at Domain Design), the FeeCycle redesign (Domain Design), the
  "absorb without rework" confidence question (Domain Design), teacher
  onboarding mechanism for closed testing, SMS vendor selection, region
  measurement, and Play account type.
- 2026-10-17 — New and important: the analytics dashboard (PU-8.2) is Must Have
  with no defined content. A Must Have that specifies nothing cannot be
  estimated, built or tested, and it is the single largest unknown in the V1
  scope. Excluded from the 8-12 week range for that reason. Requirements
  Analysis must define it, and it should be the first thing asked there.
- 2026-10-17 — Push notification event set (PU-8.1) is similarly underspecified:
  two event types named, four or five more plausible. Also for Requirements
  Analysis.
- 2026-10-17 — FCM's registration token is app-instance-scoped rather than a
  device identifier, so it should be permissible under the Families
  no-device-identifier constraint. Not verified against policy text. Must be
  confirmed before the notification work starts, because if FCM is
  impermissible, push notifications as specified become impossible rather than
  merely expensive.
