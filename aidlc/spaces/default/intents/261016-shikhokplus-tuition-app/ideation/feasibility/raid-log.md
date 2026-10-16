# RAID Log — ShikhokPlus

**Stage**: feasibility (1.3)
**Phase**: Ideation
**Date**: 2026-10-17

Risks, Assumptions, Issues, Dependencies. Live document — later stages update
it rather than replacing it.

---

## Risks

Scored likelihood × impact. Treatment per the org rule that risks are
mitigated, transferred, accepted or avoided — explicitly, never implicitly.

| ID | Risk | Likelihood | Impact | Treatment | Owner |
|---|---|---|---|---|---|
| R-1 | The one-month closed-testing target is missed. Seven vertical slices across two greenfield surfaces, plus Play closed-testing setup, Data Safety declarations and review lead time. **If the Play account is personal, production access additionally needs 12 testers opted in continuously for 14 days** [play-closed-testing], so the earliest possible production release is roughly two weeks after a working build reaches testers, independent of development speed. | High | Medium | **Mitigate by narrowing, not extending.** Sequence so auth, batches, enrollment and attendance form a demonstrable first release; defer later slices rather than half-finishing all seven. Start the closed test as early as a usable build exists, so the 14-day clock runs in parallel with the remaining slices rather than after them. | User |
| R-2 | Android code quality suffers from the review gap — half the product in the least familiar technology. [Q2] | Medium | High | **Mitigate**: conventional patterns only (Compose, MVVM, Hilt, Retrofit, Room); no clever abstractions; heavier client test coverage than typical; explain Android idioms in review rather than assuming them. | Agent |
| R-3 | A money-arithmetic defect produces a real financial dispute between a teacher and a guardian. | Medium | **High** | **Mitigate**: mandatory tests on fee-cycle arithmetic, carry-forward, partial approval and waiver [desc §13.6]; money confined to one module; fixed-point decimal with JSON-string transport [Q8]; approval actions logged with actor and timestamp [desc §6]. | Agent |
| R-4 | OTP abuse drives SMS spend. With per-SMS billing, abuse is a direct financial attack rather than merely a nuisance. | Medium | Medium | **Mitigate**: per-number limits (3/hour, 5/day), per-IP limit (10/hour), 5-minute single-use OTPs, 5 verify attempts, plus a global daily SMS ceiling with alerting. | Agent |
| R-5 | Homemade auth has a weakness Firebase would have prevented. This is the accepted cost of the Q5 decision. | Medium | High | **Accept with mitigation**: seven named controls in `architecture-proposal.md` §7; security review before the auth slice ships; enumeration-resistant responses; hashed OTP and refresh-token storage. | Agent |
| R-6 | Play rejects or delays the release on children's-data grounds. | Low–medium | High | **Mitigate**: declaration settled at intent capture [intent: Q17]; no device identifiers anywhere (TC-3); no ads SDK (TC-6); no `TelephonyManager` read (TC-4); both deletion paths built (TC-19); verified against current policy text. | Agent |
| R-7 | Attendance proves unusable mid-class on patchy data, which is the abandonment scenario §11 warns about. | Medium | Medium | **Accepted** — the user's explicit decision to keep cached-reads-only [intent: Q18]. Revisit if pilot teachers encounter it; the mitigation if so is a write queue for the mid-class path only. | User |
| R-8 | One or more of the six deferred capabilities proves not absorbable without rework. | Medium | Medium | **Partially mitigate**: ownership indirection (TC-10) is built now because org-owned batches is the hardest. The other five are reassessed at Domain Design rather than claimed as handled. | Agent |
| R-9 | The selected SMS gateway proves unreliable — poor delivery rates, slow delivery, or no masked sender — after integration. | Medium | Medium | **Mitigate**: abstract the gateway behind an interface so swapping vendors is a configuration change; test delivery from a real Bangladeshi number before committing. | Agent |
| R-10 | AWS free-tier ineligibility (account older than the 15 July 2025 change) raises Phase 2 hosting cost. | Medium | Low | **Accept**: worst case is about USD 27–30/month, still inside the USD 50 ceiling [Q3]. | User |
| R-11 | Success without measurable targets — the three success metrics have no numbers, so V1 cannot be judged against them. [intent: Q4] | Medium | Low | **Mitigate**: resolve at Requirements Analysis, which needs thresholds to write testable requirements against. | User |

---

## Assumptions

Each is recorded rather than treated as fact. Accepting an assumption does not
make it true.

| ID | Assumption | If wrong |
|---|---|---|
| A-1 | Firebase's Bangladesh SMS rate is near India's published USD 0.07. | The order-of-magnitude conclusion holds at any plausible rate; the Q5 decision does not change. |
| A-2 | USD/BDT is roughly 121. | All BDT cost figures move proportionally; relative comparisons unaffected. |
| A-3 | OTP volume approximates one login per student per month, implied by a 30-day refresh token. | Higher volume raises SMS cost linearly; the cost circuit-breaker (R-4) caps the damage. |
| A-4 | The existing AWS account [Q6] is free-tier eligible. | See R-10; cost rises to about USD 27–30/month. |
| A-5 | Local gateway advertised rates are achievable without large minimum commitments. | Effective per-SMS cost rises; local still beats Firebase by an order of magnitude. |
| A-6 | Encryption at rest satisfies the Families policy's children's-data protection expectation. | Additional controls may be needed; no policy text names encryption explicitly (RC-8). |
| A-7 | Students and guardians genuinely want read-only visibility, and read-only is sufficient to drive renewal. | The product's core premise would need revisiting; this is the largest untested product assumption. |
| A-8 | Teachers will accept connectivity-required attendance marking. | See R-7. |
| A-9 | A guardian may have children under more than one teacher simultaneously. Implied by per-enrollment guardian capture but never confirmed. [intent] | Guardian child-selection UX and the enrollment model need revisiting. |
| A-10 | Mumbai versus Singapore latency from Dhaka is decided by routing, not distance, so it must be measured. | Wrong region choice costs user-visible latency on slow networks. |

---

## Issues

Open items requiring a decision or action now, as distinct from risks.

| ID | Issue | Status | Needed by |
|---|---|---|---|
| I-1 | No SMS gateway vendor selected. [Q6] | Open | Before the auth slice |
| I-2 | Hosting region unmeasured — `ap-southeast-1` versus `ap-south-1` from Dhaka. | Open | Before provisioning |
| I-3 | The teacher-vs-teacher privacy boundary is unspecified. One permanent account can be enrolled with several teachers, and read-time role resolution could leak across that edge. Carried from intent capture. | Open | Domain Design |
| I-4 | Success-metric numeric targets are unset. Carried from intent capture. [intent: Q4] | Open | Requirements Analysis |
| I-5 | The fee model supersedes the `FeeCycle` entity in the initial description's §10; that entity needs redesigning. [intent: Q19] | Open | Domain Design |
| I-6 | Teacher onboarding mechanism during closed testing is undefined — no admin surface exists, so it is a manual operation of unspecified shape. [intent: Q20] | Open | Before closed testing |
| I-7 | "Absorb without rework" is claimed for six deferred capabilities without a stated confidence level. Raised by the reviewer at intent capture and still unaddressed. | Open | Domain Design |
| I-8 | **Play account type is unknown, and it changes the release timeline.** A personal developer account created after 13 Nov 2023 requires 12 testers opted in continuously for 14 days before production access [play-closed-testing]. An organization account has no such requirement. If personal, the pilot group must reach 12 teachers — above the "small group" described [intent: Q10] — and the 14-day clock runs after a working build is in testers' hands. | Open | Before the release plan is fixed |

---

## Dependencies

| ID | Dependency | Type | Note |
|---|---|---|---|
| D-1 | A Bangladeshi SMS gateway account with API credentials | External vendor | Blocks the auth slice; see I-1 |
| D-2 | A Google Play Console developer account | External | Needed before closed testing; has its own setup and verification lead time |
| D-3 | An AWS account | External | Exists [Q6]; free-tier eligibility unconfirmed (A-4) |
| D-4 | A domain name for the API and the account-deletion web route (TC-19) | External | The deletion route must be externally reachable without the app |
| D-5 | Pilot teachers available for closed testing | Human | Group size unquantified [intent: Q10] |
| D-6 | A Play Console closed-testing track with **at least 12 testers opted in continuously for 14 days** before production access can be applied for | External | **Verified** [play-closed-testing]. Applies to personal developer accounts created after 13 November 2023; organization accounts are not subject to it. Testers who opt in for fewer than 14 days and opt out do not count. Directly constrains R-1 — see I-8 |

---

## Assumptions & Open Questions

- D-6 was verified against Google's official documentation on 2026-10-17: 12
  testers opted in continuously for 14 days, for personal accounts created after
  13 November 2023. What remains unknown is which account type will be used,
  which is why it is recorded as issue I-8 rather than a settled constraint.
  [assumption]
- The likelihood and impact scores above are the agent's judgement, not derived
  from historical project data. They are intended to rank attention, not to
  quantify probability. [assumption]
- A-7 is the largest untested assumption in the project and no stage in the
  current plan validates it, because market research was skipped as already
  answered. Pilot teacher feedback is the only validation mechanism. [assumption]

## Sources

- [desc] Initial description, including §6, §11, §12 and §13.6.
- [Q1]–[Q12] Confirmed answers in `feasibility-questions.md`.
- [intent: Q4], [intent: Q10], [intent: Q17], [intent: Q18], [intent: Q19],
  [intent: Q20] — confirmed answers carried from `ideation/intent-capture/`.
- [play-closed-testing] https://support.google.com/googleplay/android-developer/answer/14151465
  — closed-testing requirements for production access, retrieved 2026-10-17.
- Cost and policy sources are cited in `feasibility-assessment.md` and
  `constraint-register.md`.
