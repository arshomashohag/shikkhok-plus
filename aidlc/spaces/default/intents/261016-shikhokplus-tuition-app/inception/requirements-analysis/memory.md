# Stage Memory — Requirements Analysis

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — The specification is unusually complete, so this stage's value is
  not in asking what to build. It is in the Step 5 corner sweep: crossing each
  component against the conditions it touches. Most corners I can settle with a
  stated default, which becomes a requirement or an assumption the user can
  correct; the corner checklist is explicit that a corner the agent can settle
  should not become a question. So the 13 questions are only the ones that
  depend on a fact about the user's world — market behaviour, compliance
  appetite, dispute tolerance — plus the two items this stage owes from
  earlier (analytics content, metric targets).
- 2026-10-17 — Read the practices as governing rules now, not proposals. They
  arrived as five load-steering parts, which is itself the signal: `team.md` is
  no longer a placeholder file. Several requirements will be shaped by them
  rather than by the brief — the deletion dispositions per table, the retention
  periods, the `Money` type's behaviour at its edges.

## Deviation

- 2026-10-17 — Asked 13 questions where Comprehensive guidance suggests 8-12.
  The corner sweep legitimately surfaced more world-dependent unknowns than a
  feature-driven pass would. Four of the thirteen (Q3, Q4, Q9, Q10) are places
  where I judged no default was safe to assume because the answer depends on
  market norms or compliance appetite rather than on engineering.

## Tradeoff

- 2026-10-17 — Q9 (absent vs not-yet-entered vs joined-later vs zero) is the
  clearest example of the sweep finding something a feature-level reading
  misses. §10's `ExamResult(exam, enrollment, marks)` is a single nullable
  number, which cannot distinguish four states that are visibly different on a
  marksheet the whole batch sees. Raised it as a question rather than assuming,
  because the display wording is market-facing.
- 2026-10-17 — Q10 (named marks on a shared marksheet) sits at the intersection
  of a product norm the brief explicitly endorses and a compliance posture the
  Families declaration imposes. Did not pre-empt it: the brief says named marks
  are normal and motivating in this market, and that is the user's call to make
  with the compliance consequence stated.

## Open question

- 2026-10-17 — Carried in and owned by later stages: teacher-vs-teacher privacy
  boundary, FeeCycle redesign, subscription absorb-mechanism (all Domain
  Design); deletion dispositions per table (Domain Design, blocks the privacy
  policy); academic-record retention; the Construction Verification Command;
  SMS vendor selection and whether its API logs the OTP; PU-3.6's measurement
  instrument; sub-ceiling thresholds; whether CI minutes count against the
  budget; region; production support access; and the external deletion route's
  uncosted web surface.
