# Stage Memory — Feasibility & Constraints

Observation diary for this stage. Hand-maintained narrative.

## Interpretation

- 2026-10-17 — The stage file's reference questions assume an enterprise context
  (existing systems to integrate with, AWS accounts in use, organisational
  change freezes). This is a solo greenfield build with no existing systems, so
  I reframed around what actually constrains it: who builds it and with what
  skills, the infrastructure budget, the OTP provider economics, scale ceiling,
  and money representation.
- 2026-10-17 — The user delegated the stack and auth decisions to me (§12) while
  asking for justification and the strongest counter-argument. So Q5 is
  presented as a recommendation with its arithmetic and its strongest rebuttal,
  not as an open question — asking "which OTP provider?" without the cost
  research would have pushed the work back to them.

## Deviation

- 2026-10-17 — Did the OTP cost research before writing the questions rather
  than during artifact generation. The provider choice cannot be put to the user
  meaningfully without real rates, and §12e explicitly asked what SMS costs look
  like at Bangladesh volumes. Research notes kept in the session scratchpad;
  sources cited inline in the questions file and to be carried into the
  feasibility assessment.
- 2026-10-17 — Added Q11 asking whether the user wants staged architecture
  decisions or one consolidated proposal. Their §13 asked for an architecture
  proposal approved before code, which does not map cleanly onto this
  workflow's stage-by-stage gating. Rather than silently pick one reading, asked.

## Tradeoff

- 2026-10-17 — Firebase Phone Auth versus a local BTRC-approved gateway is a
  ~25-30x cost difference per OTP (about BDT 8.50 vs BDT 0.31), which at 20,000
  OTPs/month is roughly BDT 164,000/month. Recommended the local gateway, but
  recorded the genuine counter-argument: Firebase supplies rate limiting, replay
  protection, OTP expiry and abuse detection that we would otherwise build
  ourselves, and auth is the worst place for homemade code. The user decides.
- 2026-10-17 — Recommended Jetpack Compose native Android despite the user
  declaring no Android experience [Q2]. The honest alternative is React Native
  or Flutter: one language across both clients, their existing JS/TS knowledge
  applied, and a near-free PWA story. Rejected because §11's constraints are
  specifically hostile to it (small APK, low-end devices, and no third-party SDK
  transmitting device identifiers under the Families declaration). Recorded as
  the strongest counter-argument in the proposal rather than buried, because it
  is a real trade-off and the user may reasonably prefer familiarity over APK
  size.
- 2026-10-17 — Argued against the user's fixed-point decimal choice for money
  [Q8] and they kept it. Rather than silently accept the latent risk,
  specified the version that does not drift: NUMERIC(12,2), BigDecimal only,
  and JSON-string serialization so no decimal crosses the API as an IEEE
  double. The user's choice stands; the failure mode I was worried about is
  closed by the serialization rule.
- 2026-10-17 — Firebase's Android SDK uses Play Integrity and device signals.
  Under the mixed-audience-including-children declaration (no device
  identifiers transmitted), this needs verification before Firebase could be
  chosen safely. Noted as a constraint rather than treated as disqualifying,
  since I have not confirmed exactly what the SDK transmits.

## Open question

- 2026-10-17 — Verified Play's closed-testing requirement during artifact
  generation: 12 testers opted in continuously for 14 days before production
  access, for personal developer accounts created after 13 Nov 2023;
  organization accounts exempt. This is material to the user's one-month target
  (R-1) and to the pilot group size, since "a small group" [intent: Q10] may be
  under 12. Recorded as I-8 because the account type is unknown. Found by
  checking a dependency I had written down as unverified rather than leaving it
  as an assumption — worth repeating as a habit.
- 2026-10-17 — No Bangladesh-specific Firebase Phone Auth rate is published.
  Used India (USD 0.07) as the nearest published comparator and labelled it as
  such. The real BD rate could differ; the order-of-magnitude conclusion holds
  either way, but the precise figure is an assumption.
- 2026-10-17 — Carried forward from intent-capture and still open: numeric
  success-metric targets, the teacher-vs-teacher privacy boundary, and the
  credibility of "absorb without rework" across six deferred capabilities.
