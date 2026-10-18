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

- 2026-10-17 — Contradiction analysis found three conflicts, all raised rather
  than implemented. Q4 (hidden audit log) contradicted §6's stated purpose for
  logging approvals — dispute resolution — and the affirmed append-only
  practice; resolved to overwrite-with-visible-history. Q10 (anonymised marks)
  reversed §10's named-marks decision; confirmed as a deliberate override.
  Q11 (no numeric target) left §11's clearest performance statement with no
  verifier at all; the user chose to drop the requirement entirely rather than
  carry it unverifiable, which is the more honest of the two.
- 2026-10-17 — An Edit landed on the wrong question's answer (Q12 rather than
  Q11) because the anchor text was not unique enough. Caught by verifying
  placement immediately after, restored Q12, then re-applied to Q11 with a
  longer anchor. Worth noting because the failure was silent: the edit
  succeeded, just in the wrong place, and only the verification found it.

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

- 2026-10-17 — Reviewer (advisory, iteration 1) returned NOT-READY with 2
  critical, 3 major, 2 minor. The critical one was a real miss on my part:
  **guardian child selection (PU-2.12) is a Must Have and had no requirement at
  all.** I dropped it because Q6's answer changed the guardian model to
  phone-number scoping, and I never re-derived what child selection means under
  the new model — the capability simply fell out between an answer that changed
  a premise and an artifact built on the new premise. Verified by grep before
  acting: no occurrences outside two incidental mentions. This is the failure
  mode to watch for whenever an answer changes a model rather than filling a
  blank: the artifact gets rebuilt coherently around the new model and silently
  loses whatever the old model carried.
- 2026-10-17 — Second critical finding also sound: FR9.3's "alike" was unbounded,
  so nothing fenced the correction-history mechanism against being applied to
  student- or guardian-authored content, which would breach the affirmed
  `NEVER expose anything a student or guardian writes to any teacher` rule.
  Added FR9.4 as an explicit negative boundary rather than relying on the
  enumeration being read as exhaustive.
- 2026-10-17 — The reviewer was right that A6 was not an assumption. "Collection
  rate" was a formula I invented, labelled as an assumption, which hides a
  decision rather than recording it. Promoted to FR8.3 with the denominator,
  carried-forward handling, waiver handling and the no-charge case stated.
  Kept the A6 entry as a struck-through note explaining the promotion, because
  the reasoning is more useful than a clean deletion.
- 2026-10-17 — NFR2 had the same defect as the mid-class speed statement: no
  pass/fail criterion. Rather than drop it as the user chose for speed, I gave
  it numbers (minSdk 24, 2 GB RAM, 15 MB download) and flagged them as A8 — my
  choice, not the user's, and the right kind of thing to correct at the gate.

## Open question

- 2026-10-17 — Carried in and owned by later stages: teacher-vs-teacher privacy
  boundary, FeeCycle redesign, subscription absorb-mechanism (all Domain
  Design); deletion dispositions per table (Domain Design, blocks the privacy
  policy); academic-record retention; the Construction Verification Command;
  SMS vendor selection and whether its API logs the OTP; PU-3.6's measurement
  instrument; sub-ceiling thresholds; whether CI minutes count against the
  budget; region; production support access; and the external deletion route's
  uncosted web surface.
