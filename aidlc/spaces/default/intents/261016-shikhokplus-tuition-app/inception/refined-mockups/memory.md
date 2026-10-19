# Stage Memory — Refined Mockups

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — The two declared inputs (wireframes, user-flow) are absent and
  the directive marks both `expected: true` — rough-mockups was folded into
  this stage when the plan was composed. The stage file explicitly covers this:
  design directly from stories and requirements, and never invent the content of
  a missing artifact. Said so in the questions file so the user is not misled
  into thinking something is being "refined" from an earlier pass.
- 2026-10-17 — The design knowledge in this framework is largely web-oriented:
  responsive breakpoints, hover states, ARIA roles, a component spec template
  with `prop` tables. This is native Android with Compose, so I will translate
  rather than transcribe — window size classes for breakpoints, pressed and
  focused for hover, Android accessibility services for ARIA — and say where the
  mapping is not one to one rather than producing a web spec with Android words
  pasted over it.

## Deviation

- 2026-10-17 — Asked 10 questions, within the Comprehensive range but unusually
  front-loaded for a design stage. Reason: with no rough-mockups pass, the
  structural decisions a low-fidelity round would normally settle (landing
  screen, navigation shape, lens switcher placement) are all still open, and
  guessing them would mean producing mockups whose information architecture the
  user has never seen.

## Tradeoff

- 2026-10-17 — Q1 re-opens the guardian multi-number problem, which the stories
  only mitigated. The design review at User Stories argued the real fix is
  letting an account verify a second number and union the batches. That is new
  scope, so it belongs to the user rather than to me — but the mitigation is
  weak enough that presenting it as settled would be dishonest.
- 2026-10-17 — Q2 (teacher landing screen) looks like a small question and is
  not: whichever surface is first defines what the app is for. The dues view is
  the stated subscription justification; today's classes is the most frequent
  action. Did not pre-empt it.

- 2026-10-17 — The design canvas could not be read through the artifact tool:
  it lives in a different organization from the one this session is signed in
  to, which is an org-identity check that runs before any sharing logic, so
  making it public did not help. The user exported it instead. The exports are
  self-contained bundler pages — authored markup sits in a
  `<script type="__bundler/template">` block, with fonts and runtime in a
  gzipped base64 manifest — so extracting it meant unwrapping two layers.
  Worth recording because the first export (`first_draft.html`) was the Logo
  artboard alone and I nearly concluded the whole export was unusable.
- 2026-10-17 — The design is substantially more worked than anything I would
  have produced, and it **overrides two of my decisions**. (1) The marksheet is
  fully named — 19 students, ranked, viewer's row tinted, absent students listed
  but unranked — which is the brief's §10 as originally written, not the
  anonymised rank-and-bands I substituted after the User Stories design review.
  (2) The numeral rule is the inverse of mine: the app's own numbers render
  **Latin always** (money, marks, dates, IDs, phone), while *user-typed text* is
  stored and shown exactly as typed, and Bengali digits are accepted on input.
  My AC9.3.1 said only OTP, phone and transaction IDs force Latin; theirs is
  broader and better reasoned.
- 2026-10-17 — Things the design settles that no upstream artifact had: dark
  theme throughout (nothing in the requirements mentions it); payment states
  carrying four redundant cues each (fill style, icon shape, words, and a count
  or date) with measured contrast ratios at AAA rather than the AA we committed
  to at Q8; IBM Plex Mono 500 scoped to transaction IDs only, because bKash and
  Nagad codes mix 0/O and 1/I/l; a 1.67x line-height step for Bangla because the
  Latin 1.2x default clips the matra and the descender; and an explicit offline
  state ("saved on this phone, will send when you are back online") that
  contradicts NFR5's no-offline-writes rule.

- 2026-10-18 — The user switched the workflow to autonomous for the rest of
  Inception: decide rather than ask, dispatching a specialist per decision. The
  one thing that still reached them was the summary-confirmation checkpoint,
  which is structural and cannot be self-answered; said so plainly rather than
  letting it look like a lapse back into asking.
- 2026-10-18 — Dispatched a product specialist for the three design-introduced
  capabilities rather than deciding them myself, because each had a real
  either-way. Its reasoning on the reminder SMS was better than mine: I had
  framed the cost as "another SMS consumer", it framed it as **the ceiling
  changing meaning** — a global ceiling that must arbitrate between an abuse
  burst and a legitimate bulk action on the 5th of the month is no longer an
  abuse control. That reframing is what makes NFR12.1 (per-purpose budget) worth
  adding now rather than later.
- 2026-10-18 — It also caught something I had missed entirely: FR10.1 already
  commits to **push** notifications for fee reminders. Paid SMS reminders would
  duplicate a free channel already in scope, before the pilot has shown push is
  insufficient. That turned a "defer on cost" into a "defer on redundancy",
  which is a stronger argument.
- 2026-10-18 — The enumeration-oracle risk in the cross-batch lookup was the
  specialist's find, not mine. I had assessed it as safe because the data is
  teacher-authored, which is true but incomplete: the lookup is **keyed on a
  phone number the requester supplies**, so unscoped it reveals whether any
  number exists on the platform. FR2.19 now requires the no-match response to be
  identical whether the number is enrolled with another teacher or nowhere.

- 2026-10-18 — Reviewer returned NOT-READY with seven findings, all verified
  before acting. **The sharpest was a fourth design addition neither I nor the
  Q12 specialist caught**: S3 displays the teacher's own bKash or Nagad number
  to every guardian, with a Copy action. No requirement defined it. It is the
  one teacher-authored field the product must deliberately expose — the payment
  flow cannot work without it, since money moves out of band — and it was
  sitting in a mockup unexamined. FR6.12 and FR6.13 now define it as a separate
  optional field, bounded in who sees it, with the teacher told at entry.
  Pattern worth noting: both Q12 and I were scanning for *features*, and this
  was a *data field* hiding inside a feature we had already accepted.
- 2026-10-18 — Second real catch: a stale constraint note still read "no
  offline writes, which makes FR3.6's retry prompt the entire failure story",
  two rows below the amended FR3.6 describing a write queue. Same file, direct
  contradiction. Reconciliation leftovers hide in prose rather than in the
  tables being amended.
- 2026-10-18 — Third: FR2.19's enumeration resistance was written as
  "byte-identical", which is the exact form the team's own Walking Skeleton
  practice **explicitly rejects** for OTP ("we assert the structural property …
  and not a wall-clock bound, because a millisecond assertion is flaky and will
  be deleted the third time CI fails on it"). I had written a new requirement in
  a shape the project already decided against. Restated structurally.
- 2026-10-18 — Fourth: the walking-skeleton screen has no artboard and was not
  flagged. The mockups file listed six lesser gaps in Assumptions and omitted
  the one that matters most — the OTP sign-in flow, where a design mistake is a
  security mistake. Now a dedicated section rather than an assumption bullet.

## Open question

- 2026-10-17 — Carried in, owned by Domain Design: teacher-vs-teacher privacy
  boundary, FeeCycle redesign (now with a credit field), deletion dispositions
  per table, academic-record retention, subscription absorb mechanism, teacher
  deletion cascade.
- 2026-10-17 — Three things in the stories are the agent's design rather than
  the user's specification and remain open to correction: the rank-and-bands
  marksheet, default-present attendance, and how a credit counts toward the
  collection rate.
- 2026-10-17 — NFR2's device floor (minSdk 24, 2 GB RAM, 15 MB) is still flagged
  for NFR Requirements, possibly conservative after the device-reality
  correction.
