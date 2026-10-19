# Stage Memory — Practices Discovery

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — Greenfield, so there is nothing to discover from evidence: no
  application code, no CI config, no git history beyond the scaffold commit, and
  `team.md` is entirely placeholder comments. The stage therefore runs as
  "choose practices from org.md defaults plus the approved architecture" rather
  than "infer practices from what the team already does". Said so explicitly in
  the lead's brief so the evidence artifact does not present inference as
  observation.
- 2026-10-17 — The approved architecture and constraint register narrow the
  practice choices considerably: the stack is settled, the money-path test
  requirement is stated, the coverage floor comes from the scope, and the
  compliance constraints are non-negotiable. So the genuinely open practice
  questions are fewer than a greenfield run would normally have — mainly the
  testing methodology and the walking-skeleton stance.
- 2026-10-17 — Flagged the testing-methodology tension in the lead's brief
  rather than pre-deciding it: the money paths are arithmetic over a ledger and
  favour test-first, while Compose UI work by a developer unfamiliar with
  Compose is exploratory and does not. A `custom` methodology that is honest
  about the split may beat a uniform one, but asked the lead to argue its own
  position rather than ratify mine.

## Deviation

- 2026-10-17 — Independently verified the quality reviewer's RLS-superuser
  finding against the PostgreSQL 16 documentation rather than accepting it on
  authority, because it either inverts the project's strongest privacy control
  or is wrong, and the check cost one lookup. Confirmed verbatim: "Superusers
  and roles with the BYPASSRLS attribute always bypass the row security system
  when accessing a table. Table owners normally bypass row security as well,
  though a table owner can choose to be subject to row security with ALTER
  TABLE ... FORCE ROW LEVEL SECURITY."
  Consequence: a privacy-boundary test suite connecting as the default
  `postgres` container user passes identically whether the RLS policy is
  correct, wrong, or entirely absent. The draft's strongest test obligation
  certified nothing as written. This is a genuine save — the defect is
  invisible when present, because the symptom is a passing suite.

- 2026-10-17 — Verified the security reviewer's TC-19 claim: grep finds zero
  occurrences of deletion in either `team-practices.md` or
  `discovered-rules.md`, while RC-4 (Data Safety) and RC-5 (privacy policy) are
  both present and mandated as release-blocking. Those three constraints come
  from the same Play policy page. Confirmed omission.
  **This is the second time account deletion has been dropped in this
  workflow** — the product-lead reviewer caught the same omission in the intent
  statement at stage 1.1, and it was restored there. Twice is a pattern, not
  bad luck: account deletion is a release requirement that no stage's reference
  questions ask about, it has no natural home in a feature list because it is
  not a feature anyone requests, and it is easy to feel covered by the adjacent
  compliance items that do get named. Carrying it as an explicit Mandated rule
  with a test obligation is what stops it recurring a third time.

## Tradeoff

- 2026-10-17 — Told the lead explicitly not to promote its own preferences into
  `discovered-rules.md`, only hard constraints the human actually stated. That
  file gets promoted into the project's permanent memory (`project.md`
  `## Mandated` / `## Forbidden`), so an invented rule there would silently bind
  every future stage and every future intent in this space. The constraint
  register and decision log are the legitimate sources.

- 2026-10-17 — All three blind reviews returned with substance, which validated
  running them blind: each found a different class of defect and none could have
  found the others'. Quality found the RLS-superuser flaw (a control that
  certifies nothing). Security found the TC-19 omission (a release blocker) and
  that review cannot enforce a transitive-dependency constraint. Developer found
  that several rules were stated as conventions where they could be made
  mechanical — the `Money` value class being the best example, turning the float
  prohibition from a lint rule that must know which classes carry money into a
  property the compiler enforces.
- 2026-10-17 — A theme across all three: the draft's substance was sound and its
  *enforcement mechanisms* were weak. Most objections were "right but
  unenforceable as written" rather than disagreement. That is the useful shape
  for a practices stage, because an unenforceable practice decays silently while
  appearing to be in force.

- 2026-10-17 — The user's first answer pass contained a three-way tension worth
  recording because the shape recurs: Q2 (80% line floor on Kotlin) and Q6
  (Critical/High block every merge) each defensible alone, together producing
  three hard gates on the least-familiar surface with no triage path; while Q7
  declined the DEX scan, leaving enforcement hardest where risk is visible
  (published, fixable CVEs) and absent where it is invisible (a transitive SDK
  reading a prohibited identifier). Named the tension rather than implementing
  it, and the user revised both to the reviewers' positions. The general
  lesson: answers given one at a time can each be reasonable while their
  combination is not, so a consolidated read-back before integration is where
  that gets caught.
- 2026-10-17 — The user chose 88-character lines over their own stated global
  79-character Python standard. Asked the lead to record it explicitly as a
  deliberate project-level departure, so a later stage or reviewer does not
  "fix" it back to 79 and reformat every file.

- 2026-10-17 — The lead flagged, honestly and against its own integration, that
  the docstring narrowing had weaker affirmation than the line-length departure:
  it came from inside a reviewer contribution and rode on Q12's "nothing else
  changes" rather than being asked. Raised it as an explicit question; the user
  chose their global standard, so the narrowing was reverted in
  `team-practices.md` and the resolution recorded in `evidence.md`. Worth noting
  the mechanism that caught this: the lead was asked to report what the human
  should see at the gate, and it used that to surface its own weakest decision.
  A report that only defends its work would not have found this.

## Open question

- 2026-10-17 — Carried into this stage: whether the walking-skeleton stance
  should be on. The scope's `skeleton:` field supplies a default, but the user's
  decision that nothing reaches a tester until all seven slices work
  [scope: Q1] sits awkwardly with a skeleton ceremony whose purpose is to prove
  an end-to-end slice early. Worth asking in the interview rather than resolving
  from the scope field alone.
- 2026-10-17 — Still open from Ideation, with owners: teacher-vs-teacher privacy
  boundary and FeeCycle redesign and subscription absorb-mechanism (Domain
  Design); analytics dashboard content and success-metric targets (Requirements
  Analysis). Not this stage's business, tracked so they are not lost.
