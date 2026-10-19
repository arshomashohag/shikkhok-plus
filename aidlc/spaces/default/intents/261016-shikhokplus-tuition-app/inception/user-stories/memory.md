# Stage Memory — User Stories

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — Step 2's execute-or-skip assessment is genuinely open on paper
  but not in practice here: three personas with asymmetric rights over the same
  records is the textbook case for stories. Wrote the assessment properly rather
  than treating it as a formality, and recorded the one factor that does NOT
  apply — cross-team coordination, since a solo build has no team boundary for
  stories to span. Their value here is specification and testability.
- 2026-10-17 — Chose to group stories by proto-Unit rather than by persona.
  The slices are already the delivery sequence, each is independently testable,
  and Units Generation will consume the grouping directly. Grouping by persona
  would scatter each slice across three places, which breaks the Independent
  part of INVEST — the thing that makes a story deliverable on its own.

## Deviation

- 2026-10-17 — Asked 5 questions where Comprehensive suggests 8-12. By this
  stage the requirements are approved and 84 FRs are settled, so most of what a
  story plan would normally ask is already answered. The five are the ones that
  shape the artifact's structure rather than its content: priority scheme, actor
  granularity, dormant-account placement, NFR coverage, and persona accuracy.
  Padding would mean re-asking settled requirements.

## Tradeoff

- 2026-10-17 — Q1 questions whether MoSCoW priorities are worth carrying at all.
  Scope Definition fixed everything as Must Have, so a priority column would
  mark 55 stories identically and inform nothing. Raised it rather than
  mechanically filling the field, because a field that carries no information is
  worse than an absent one — it looks like a decision was made.
- 2026-10-17 — Q2 is the highest-leverage structural question: whether a
  teacher action and its student-side consequence are one story or two. The
  privacy boundary means most teacher actions have a student and guardian
  consequence, so this decision shapes roughly a third of the backlog. Did not
  pre-empt it.

- 2026-10-17 — The mob found two defects where my draft contradicted rules the
  user had already affirmed, which is the clearest evidence the round was worth
  its cost. **AC5.1.2 specified a sequential idempotency test** when the
  permanent project rule says concurrent, never sequential — and the rule exists
  precisely because an application-level "has this already run" guard passes
  sequentially and fails with two workers, which Phase 1 has. **And US10 did
  not exist**: every authorization criterion I wrote tested the actor's own
  view, so zero coverage of the IDOR shape the practices mandate probing. Both
  verified against the rule text before fixing.
- 2026-10-17 — The design review caught a near-miss none of us would have found
  from the requirements alone: FR2.16 puts the recording teacher in the
  child-selection list, and FR2.15 skips that list when one child is reachable.
  So the single explanatory signal in the whole specification was invisible in
  exactly the worst case — one child, two teachers, one visible batch. That is
  an interaction between two requirements written at different moments, which is
  the class of defect a per-requirement review cannot see.
- 2026-10-17 — Three findings went to the user as judgment calls rather than
  being decided here, per the mob triage rule. All three were genuine
  either-ways: the inactive_from contradiction (my error, two defensible
  resolutions), overpayment handling (no answer consistent with both the ledger
  shape and the never-negative invariant without adding a concept), and
  dormant-enrollment visibility (clutter versus mutual invisibility).
- 2026-10-17 — Q7.1's resolution required amending `requirements.md`, not just
  the stories: FR5.3's predicate was itself wrong, so fixing only the story
  would have left the contradiction in the approved requirement. FR5.1 also
  gained a fifth ledger quantity from Q7.2. Editing an approved upstream
  artifact is the right call when the contradiction is in it, but it is worth
  noting that it happened — the requirements gate approved a contradiction and
  this stage caught it.

- 2026-10-17 — Reviewer (advisory, iteration 1) returned NOT-READY with seven
  findings. **Two were wrong and I verified before acting**: it reported the
  money boundaries (zero/negative amount, approved-exceeds-claimed) as still
  absent when AC6.1.6, AC6.1.7 and AC6.3.7 cover them, and reported US1.8's
  degraded-mode messaging as missing when AC1.8.5 states it. Most likely it read
  the file before those edits landed. Checking cost two greps and avoided
  re-adding criteria that already existed, which would have left duplicates.
- 2026-10-17 — **Five findings were correct and all concerned my integration of
  the mob, not the draft itself.** I had dropped the developer's US8 four-way
  split and its corrected dependency edges, dropped the quality agent's
  `AuthorizationError` taxonomy tagging on US10, left FR3.1 uncovered after the
  developer specifically flagged that nothing creates the sessions US3.1 opens,
  omitted the design agent's three story-level accessibility cases, and let two
  persona details drift. That is a pattern worth naming: the hard findings got
  integrated and the *reasoned-but-undramatic* ones got lost. The US8 split in
  particular was argued and settled in the contribution, and I left the
  Assumptions section reading as though it were still an open question.
- 2026-10-17 — The dependency edge was factually wrong, not just imprecise: I
  wrote that US8 depends on US5, but earnings, collection rate and waived
  amounts all need *verified* payments from US6, and the next-exam view needs
  only US4. A wrong dependency edge in an artifact Units Generation consumes
  would have propagated into the build order.
- 2026-10-17 — Ran the summary confirmation checkpoint AFTER writing the
  artifacts rather than before. The engine refused the review request until it
  existed, which is how I noticed. The content was unaffected, but the
  checkpoint is designed as a pre-generation stop so the user can redirect
  before work is done; running it afterwards turned it into a formality. Told
  the user plainly rather than letting it pass as a normal confirmation.

## Open question

- 2026-10-17 — Carried in, owned by Domain Design: teacher-vs-teacher privacy
  boundary, FeeCycle redesign, deletion disposition per table, academic-record
  retention, subscription absorb mechanism, and the teacher-deletion cascade.
  Owned by Functional Design: the notification event set. Unowned and external:
  SMS vendor, Play account type, teacher onboarding during closed testing, and
  the uncosted web surface for the external deletion route.
- 2026-10-17 — Two figures in the requirements are mine rather than the user's
  and remain open to correction: NFR2's device floor and APK budget (A8), and
  FR8.3's collection-rate denominator. Both were surfaced at the requirements
  gate and approved without change, so they stand, but they are the two most
  likely to be wrong.
