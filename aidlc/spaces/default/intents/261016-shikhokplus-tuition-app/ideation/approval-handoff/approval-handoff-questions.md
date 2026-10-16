# Approval & Handoff — Questions

**Stage**: approval-handoff (1.7)
**Phase**: Ideation
**Depth**: Comprehensive

## Sources

- [desc] Initial description.
- [scope] Workflow-selected scope: `classic`.
- [upstream] All Ideation artifacts: `intent-statement.md`, `stakeholder-map.md`,
  `feasibility-assessment.md`, `constraint-register.md`, `raid-log.md`,
  `architecture-proposal.md`, `scope-document.md`, `intent-backlog.md`.
- [firebase-privacy] https://firebase.google.com/support/privacy — Firebase Cloud Messaging data collection and Firebase installation IDs, retrieved 2026-10-17.

---

## Note on what is NOT asked here

This stage compiles rather than decides, and several of its reference questions
do not apply to this project:

- **Stakeholder agreement** — you are the sole decision-maker
  [intent: Q10]; there is no group to reach consensus.
- **Market research support** — market research was deliberately skipped,
  since the market, the competitor categories and the V1 exclusions were
  already named in the initial description.
- **Mob staffing and scheduling** — solo build with agent support
  [feasibility: Q1]; no teams to staff.
- **Rough mockups matching a shared vision** — rough mockups were folded into
  refined mockups, which has not run yet.
- **Budget commitment** — settled at feasibility: under USD 50/month
  infrastructure [feasibility: Q3].

What remains are the two things a phase boundary should actually test: whether
the risks are genuinely accepted, and whether the open questions are safe to
carry into Inception.

---

## Q1. Of the open questions carried into Inception, which must be answered before design work rather than during it?

Eight open items are carried forward. Four resolve naturally in early Inception
stages; four are external to the workflow and could block work if left. I would
rather know now which ones you consider blocking.

The four the workflow resolves on its own:

- The teacher-vs-teacher privacy boundary — Domain Design (2.6)
- The `FeeCycle` redesign to the anchor-plus-ledger model — Domain Design (2.6)
- Success-metric numeric targets — Requirements Analysis (2.3)
- The analytics dashboard's content — Requirements Analysis (2.3)

The four that are external:

- A. **SMS gateway selection** — blocks slice 1 (auth) implementation, not design
- B. **Play Console account type** — determines whether 12 testers for 14 days applies; affects the release plan, not the design
- C. **Teacher onboarding mechanism for closed testing** — no admin surface exists in V1, so teachers reach the platform by some manual route that is currently undefined
- D. **FCM permissibility under the no-device-identifier constraint** — if FCM is not permissible, push notifications as specified become impossible rather than merely costly
- E. None of these block Inception; carry all four and resolve them as implementation approaches
- X. Other (please specify)

(Select all that apply, or E.)

[Answer]: E. None of these block Inception; carry all four and resolve them as
implementation approaches.

Note added after the answer: option D (FCM permissibility) was researched
rather than carried, because an impermissible FCM would have made a Must Have
impossible rather than merely costly, and the check cost one lookup. Firebase
Cloud Messaging uses **Firebase installation IDs** to route messages
[firebase-privacy]. These are app-instance scoped, deletable through an API
call, with data removed from live and backup systems within 180 days of
deletion. The documented FCM data collection does not include AAID, IMEI, MAC
address or Android ID — the identifiers the Families policy prohibits
[TC-3]. **FCM is therefore permissible**, and push notifications remain
feasible as specified. The remaining three external open questions are carried
as answered.

---

## Q2. Is the risk register genuinely accepted as it stands?

Eleven risks are recorded in `raid-log.md`. Three are accepted rather than
mitigated, which means if they occur, the plan absorbs them rather than
preventing them. A phase boundary is the right place to confirm that is
deliberate.

The three accepted risks:

- **R-7**: attendance marking requires connectivity, so it will fail on patchy
  classroom data. This is the §11 abandonment scenario, accepted by your
  cached-reads-only decision [intent: Q18].
- **R-5**: homemade OTP auth may have a weakness Firebase would have prevented.
  Mitigated by seven named controls, but the residual risk is real
  [feasibility: Q5].
- **The no-buffer risk**: every V1 capability is Must Have, so schedule
  variance has nothing to absorb it [scope: Q7].

- A. Yes — all three are accepted deliberately; proceed to Inception
- B. Reconsider R-7 — add offline writes for the mid-class path after all
- C. Reconsider R-5 — revisit the Firebase decision
- D. Reconsider the no-buffer risk — designate something as Should Have
- X. Other (please specify)

[Answer]: A

---

## Q3. Go / no-go?

The formal phase gate. Ideation produced: an approved intent, a verified
feasibility assessment with a costed architecture, 35 constraints, an 11-risk
register, a fixed V1 scope and a dependency-ordered backlog of 8 proto-Units.

My recommendation is **go**, with the reservations stated in the initiative
brief: the timeline is unestimated beyond an 8–12 week range, one Must Have has
no defined content, and the client side is the thinnest-reviewed surface.

- A. Go — proceed to Inception
- B. Go, but with a change I will specify
- C. No-go — stop here
- X. Other (please specify)

[Answer]: A. Go — proceed to Inception.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Open questions: all four external ones are carried into Inception rather than
  treated as blockers on design work.
- One exception, researched rather than carried: FCM is permissible under the
  no-device-identifier constraint. It routes messages on app-instance-scoped
  Firebase installation IDs, deletable through an API call, and the documented
  collection does not include AAID, IMEI, MAC address or Android ID. Push
  notifications remain feasible as specified. The three remaining external open
  questions are SMS gateway selection, Play Console account type, and the
  teacher onboarding mechanism for closed testing.
- Risk register accepted as it stands. The three accepted-rather-than-mitigated
  risks are confirmed deliberate: attendance marking requires connectivity and
  will fail on patchy classroom data (R-7); homemade OTP auth carries residual
  risk that Firebase would have absorbed (R-5); and every V1 capability being
  Must Have leaves no buffer for schedule variance.
- Phase gate: **Go**. Proceed to Inception.
- Reservations recorded in the initiative brief rather than dropped: the
  timeline is an 8–12 week range rather than an estimate; the teacher analytics
  dashboard is a Must Have with no defined content and cannot be sized until
  Requirements Analysis defines it; and the Android client is the
  thinnest-reviewed surface given no declared Android experience.
- Four open questions have owning stages and are safe to carry: the
  teacher-vs-teacher privacy boundary and the `FeeCycle` redesign at Domain
  Design, and the success-metric targets and analytics dashboard content at
  Requirements Analysis.

[Answer]: Looks correct

---
