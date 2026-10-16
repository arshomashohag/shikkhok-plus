# Stage Memory — Intent Capture & Framing

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — The brief is unusually complete for an intent-capture stage: it
  already carries a data model, explicit V1 exclusions, and a stated build
  order. So the clarifying questions deliberately avoid re-asking what the
  brief settles, and target only the places where a wrong assumption would be
  expensive to reverse: commercial model, Play audience declaration, the
  permanent package name, money-rule corners, and the offline boundary.
- 2026-10-17 — Treated "role is a lens resolved at read time" and the privacy
  boundary as settled requirements from the brief, not open questions. They are
  design inputs for domain-design, not things to re-litigate here.

## Deviation

- 2026-10-17 — Asked 15 questions, above the Comprehensive 8-12 guideline. The
  user explicitly requested "every question where a wrong assumption would be
  expensive to reverse. One batch of questions, not a drip." The money-rule
  corners (Q7-Q9) and the Play audience declaration (Q2) each independently
  justify their place; padding was not the issue, coverage was.

## Tradeoff

- 2026-10-17 — Verified the Play target-API and children's-data policy via web
  fetch during the composer's run rather than deferring to nfr-requirements.
  Reason: Q2's answer depends on the policy text, and asking the user to decide
  the audience declaration without the TelephonyManager prohibition in front of
  them would have produced an uninformed answer. The sourced claim still belongs
  in nfr-requirements as an attributed requirement.

## Open question

- 2026-10-17 — Reviewer (advisory, iteration 1) returned NOT-READY with 1
  critical, 2 major, 2 minor. Two were acted on immediately as omissions rather
  than judgment calls: the §11 release-readiness deliverables (account deletion,
  Data Safety form, privacy policy, Families declarations, accessibility) had
  been silently dropped from the scope section despite being named V1 scope in
  the initial description; and the teacher-vs-teacher privacy boundary was
  unaddressed, which matters because one permanent account can be enrolled with
  several teachers and read-time role resolution could leak across that edge.
  The critical finding (no numeric success targets) is a decision for the human,
  already carried as an open question — advisory class means it goes to the gate
  rather than into a fix loop.
- 2026-10-17 — Attendance (Q5) is a genuine internal contradiction in the brief:
  §1 and §11 both reference attendance, but §2's IN list and the §10 data model
  contain no attendance entity. Flagged rather than silently resolved either way.
  RESOLVED at Q18: attendance is in V1, cached-reads-only stands, marking
  requires connectivity.
- 2026-10-17 — Spelling/package-name conflict (Q3): the brief says never invent
  variant spellings, yet `shikhokplus` (§11) and the repo's `shikkhok-plus`
  are already two spellings. Permanent-once-published, so surfaced now.
  RESOLVED at Q3: `com.shikkhokplus.app`, matching the existing repo spelling.
  NOTE: user-facing strings still say "ShikhokPlus" per the brief, so the Latin
  product name and the package namespace differ by one k. Deliberate, recorded.
- 2026-10-17 — Four contradictions surfaced after the first answer pass; all
  four resolved via Q16-Q19 before artifact generation.

## Deviation

- 2026-10-17 — Q1's answer expanded scope: a platform-owner admin persona with
  write access, not present in the brief's three personas, and §4's privacy
  boundary says nothing about what an admin may see. Resolved at Q16 as
  APIs-only for V1. The authorization model must therefore admit a fourth
  principal from the start, and the privacy boundary needs an explicit
  admin clause at domain-design — flagged as an open design question, not
  settled here.
- 2026-10-17 — Q19 accepted a departure from the §10 data model the brief
  called agreed: fee becomes a teacher-adjustable anchor with a ledger of
  charged/received/carried/forgiven amounts, replacing a fixed `amount_due`
  with the stated balance formula as the sole truth. Calendar-month periods and
  `fee_due_day` are retained. The user authorised this explicitly; §10's
  FeeCycle shape will need revision at domain-design.
- 2026-10-17 — Q18 accepted a known risk rather than designing it away: §11
  warns that slow mid-class attendance marking causes abandonment, and
  cached-reads-only means attendance marking fails on patchy data. I
  recommended offline writes for the mid-class path; the user chose
  connectivity-required. Recorded as an accepted V1 risk to revisit if
  pilot teachers hit it.

## Tradeoff

- 2026-10-17 — At the assumption confirmation gate the user neither accepted nor
  converted: they resolved three assumptions directly and removed scope. Treated
  their reply as the instruction it was rather than forcing it into A or B —
  recorded the resolutions as Q20, revised both artifacts, then recorded
  acceptance for what genuinely remained. Scope shrank at an assumption gate,
  which is the opposite of the usual direction and worth noting: the admin APIs
  were added by Q1 and removed by Q20 within the same stage, so no design work
  was built on them.
- 2026-10-17 — Q2/Q17: the user's login mechanism (teacher enters both numbers,
  both can log in regardless of age) decides the Play declaration rather than
  the reverse. Rather than write down the 13+ answer they first selected, I
  named the consequence — under-13s logging in makes 13+ a misdeclaration — and
  they confirmed mixed-audience. Families obligations are now hard constraints
  for NFR and design: no device/advertising identifiers anywhere, no ads SDK,
  no TelephonyManager number read, COPPA/GDPR-K.
- 2026-10-17 — Q14: the user withdrew the DECISIONS.md / DEFERRED.md
  requirement from §13.5 of the brief ("Ignore these"). Their later instruction
  overrides the earlier brief, so neither file is a deliverable. The equivalent
  record lives in the per-stage artifacts and these diaries.
