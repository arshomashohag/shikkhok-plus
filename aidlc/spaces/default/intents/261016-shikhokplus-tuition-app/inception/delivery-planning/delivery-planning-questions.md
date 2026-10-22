# Delivery Planning — Questions

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` and `unit-of-work-dependency.md`
- [upstream] `inception/contract-design/contract-summary.md` — open contract questions
- [upstream] `ideation/approval-handoff/initiative-brief.md` §6
- [team] the affirmed Way of Working, Walking Skeleton and Deployment practices

---

## How this stage was answered

Several of the stage's strategic questions were already settled by affirmed
practice or recorded state — solo build (so no team to allocate and no parallel
Bolts), serial execution, unit-major iteration, checkpoints enabled, and the
walking skeleton. Those were not re-asked. Three genuinely open economic
judgements went to the human; the rest went to a dispatched delivery lead with
those answers as settled input.

## Q1. Where should the gated-to-autonomous switch fall?

[Answer]: After B7 `payment-claims-and-verification` (U8). This is the direct
translation of the affirmed "gated through the payment slice, then autonomous"
onto the current unit list — the practice was written when the payment slice was
PU-6, and the unit list has since changed shape. The money and privacy write
surfaces stay gated; analytics, packaging and governance follow automatically.

## Q2. What worries you most about this build?

[Answer]: The privacy boundary — nothing a student or guardian writes reaching
any teacher, row-level security genuinely in force, no cross-teacher leak. This
shaped what the early Bolts are asked to prove: B2, B3, B5, B7 and B9 each carry
a falsifiable privacy hypothesis rather than a feature one.

## Q3. How big should one Bolt be?

[Answer]: One Unit per Bolt — eleven Bolts matching the Unit list exactly.
Construction is already unit-major with per-unit checkpoints, so this keeps the
plan and the runtime in step and makes each checkpoint a demonstration of one
coherent thing.

## Q4. Should a formal scoring model rank the work?

[Answer]: No, and the rationale artifact says so explicitly rather than silently
omitting it. Seven of eleven positions are DAG-forced; every V1 capability is
Must Have, so cost of delay is identical across all Bolts and the value axis is
constant; job sizes span one step. Scoring would dress up a decision the
geometry already made. The one genuinely free choice turned on a hard constraint
no score would have surfaced.

## Q5. Can Bolts run concurrently?

[Answer]: No. Serial, because this is a solo build and there is no second worker
— not because the DAG forbids it. The parallelisable sets recorded at Units
Generation describe reorderability, which is useful when an external dependency
slips, not simultaneity.

## Q6. What external work could hold this up?

[Answer]: Seven dependencies mapped with owner, lead time, blocked Bolt and
fallback. Three want resolving before Construction starts rather than when their
Bolt arrives: the SMS vendor, the Play account type, and OQ-5. Lead times are
recorded as unknown where they genuinely are.

---

## Consolidated Summary Confirmation — first run 2026-10-18 (settled)

Asked and answered on the first run of this stage. Kept for the record; the
live confirmation for this re-run is at the end of this file.

- **Eleven Bolts, one Unit each, serial.** Validated as a topological order
  against the DAG: no violations, and exactly three positions where the DAG left
  genuine freedom. The other seven are forced.
- **B3 `identity-and-access` is the walking skeleton**, with its own human
  checkpoint before later Bolts start.
- **`release-packaging` moves early, to position 4**, on a dependency the DAG
  does not carry: U5's latency obligation is dischargeable only by a
  Macrobenchmark, and that harness belongs to U10. The Play-clock argument is
  secondary.
- **`privacy-and-governance` stays terminal, but its mechanism moves to B3** —
  the manifest pair and the schema-iterating test, so every table-creating Bolt
  must carry its dispositions or CI reddens. This grows B3, already the largest.
- **No WSJF scoring**, with the reasoning recorded rather than the omission
  being silent.
- **No team to allocate**; the allocation artifact says so plainly instead of
  inventing roles.
- **Schedule: 10–16 weeks of build**, against the Ideation range of 8–12 —
  which sits on the optimistic side of a straightforward sum and excluded the
  analytics dashboard now in the plan. Best re-stated after B2, when the first
  real velocity data exists.
- **Three items flagged for the human, not decided**: re-gating B11 against the
  settled gating decision, starting SMS vendor selection now, and resolving the
  Play account type before Construction.

Answered: Looks correct

---

# Re-run 2026-10-22 — follow-up questions

Delivery Planning was re-entered at the user's request: *"there are some bolts
that are still remaining. We've made some decision changes as well. Refine the
outstanding bolts and group related works (1 or more bolts) as a deliverable
units."*

Four Units are built (U1 `money-core`, U2 `api-contract`, U3
`identity-and-access`, U4 `batches-and-enrollment`). The prior answers above
stand except where a decision change has moved the ground. Only those were
re-asked, each naming the prior answer it revisits.

## Q7. The Bolt boundary — revisits Q3

Q3 set one Unit per Bolt, eleven Bolts matching the Unit list exactly, because
Construction is unit-major and that kept the plan and the runtime in step. The
re-plan at `docs/delivery/vertical-slices.md` changes the boundary to one
user-visible capability — API, screens and tests together — which cuts V1 and
V2 across the `batches-and-enrollment` Unit and pulls account creation in as
work no Bolt covered.

[Answer]: Vertical slices, as the re-plan says. Each remaining Bolt is one
user-visible capability with its screens, and names the design artboard its
Definition of Done must match. This replaces the one-Unit-per-Bolt rule for
everything still outstanding. A Bolt is no longer done when its endpoints work;
it is done when the thing can be done on a phone.

## Q8. Where the gated-to-autonomous switch falls — revisits Q1

Q1 put the switch after B7 `payment-claims-and-verification` (U8), translating
the affirmed "gated through the payment slice, then autonomous" onto the unit
list of the time. Four Units are now built and the remaining work is re-cut, so
the slice that answer named sits at a different position.

[Answer]: Autonomous from here. The user's words: *"we don't have payment slice
now. That is dropped. go with autonomous"* — confirmed on a follow-up as
meaning the **platform subscription** only (ShikhokPlus charging teachers,
students or guardians), not the fee system. Teachers still record and collect
tuition from their own students: fee cycles and payment claims/verification both
remain in the plan. The gating practice was anchored to a slice that no longer
marks a boundary worth gating on, so Construction continues automatically from
here. Plan Approval, summary confirmation, verification command selection and
any failure remain human stops regardless.

## Q9. The already-added lookup's disclosure — settles the re-plan's open question

`docs/delivery/vertical-slices.md` left open whether the lookup that renders
O1 state 3 may name the teacher and the batch to an **unauthenticated** caller,
as the artboard shows ("মাহফুজুর রহমান added this number as a student in
পদার্থবিজ্ঞান · Batch A"). Anyone who typed a phone number would learn who
teaches that person and in which batch.

[Answer]: Settle it now — show less. The lookup confirms that the number has
already been added and returns what the form needs to pre-fill and lock the
role, but names neither the teacher nor the batch to an unauthenticated caller.
The screen loses some reassurance; it does not become an oracle for who teaches
whom. This is now a decided constraint on V1 rather than an open question.

---

## Consolidated Summary Confirmation — superseded 2026-10-22

Does this all look correct before I generate the artifact?

- **Nine remaining Bolts become six deliverable units**, each one or more Bolts
  grouped by what a person can do when it ships, cut as vertical slices: API,
  screens and tests together, with the artboard named in the Definition of Done.
- **Four Units are built and frozen** — `money-core`, `api-contract`,
  `identity-and-access`, `batches-and-enrollment`. The plan covers only what
  remains.
- **Account creation enters the plan as its own slice.** No Bolt covered it; a
  teacher could only exist by hand-inserting a database row.
- **Construction runs autonomously from here.** The payment-slice gate is
  retired because the platform subscription it anchored to is gone.
- **The already-added lookup names neither teacher nor batch**, settling the one
  question the re-plan left open.
- **`release-packaging` is partly done**: both release gates exist, the
  Macrobenchmark harness does not — and the attendance latency obligation is
  dischargeable only by that harness.
- **Governance stays last and stays release-blocking.** Neither account-deletion
  path exists, and both are V1 deliverables, so no public Play track until it
  lands.
- **The money boundary, the lens-per-request rule, the privacy boundary, the
  test-first predicate and both coverage floors are unchanged.** This re-cut
  changes when work is cut, not what is required of it.

Answered: Request changes

---

# Lens management — decided 2026-10-22

The user asked to settle lens management before the plan was written:
*"Every user is teacher, student, and guardian. In teacher's lens user can
create batches, add student and guardians and do all other operations to manage
a batch. In guardian's lense user can check every account he is added as
guardian and he accepted it. Same goes for student. Let's discuss about this
lens management first."*

Most of that description is already the built model and is confirmed rather than
changed: one account holds all three lenses simultaneously, computed per request
from `Owner` and `Enrollment` with no role column [BR1.1], proven by
`tests/authz/test_dual_role_cost.py`. The teacher lens comes from owning an
`Owner` row; the student lens from `enrollment.student_account_id`; the guardian
lens from `enrollment.guardian_account_id`.

**One clause had no implementation: "and he accepted it".** There is no
acceptance anywhere in the schema. A teacher typing a phone number today makes
that account a student or guardian immediately, with no consent, no
notification and no way to decline — so a mistyped digit exposes a child's
records to whoever owns that number.

## Q10. Should a seat require acceptance before it grants a lens?

[Answer]: Accept before the lens works. A seat a teacher creates is **pending**:
visible to the account it names, so they can act on it, but granting no student
or guardian lens until accepted. Declining is durable and survives the teacher
re-adding the same number, so a declined person is not prompted forever.

Two consequences recorded with the decision:

- **The teacher's side never blocks on acceptance.** The roster, the batch and
  fee-cycle generation all work against a pending seat from the moment it is
  created. The debt is real whether or not anyone has opened the app. Acceptance
  gates only the student and guardian lenses.
- **The markers are per LINK, not per row**, for the same reason the two erasure
  markers already are [BR6.2]: the student's claim and the guardian's claim are
  independent facts about one seat, and a single flag cannot express the states
  that result.

## Q11. How does a person move between lenses?

[Answer]: Pick at login, switch anywhere — confirming the decision already
recorded in `docs/delivery/vertical-slices.md` and already built as
`GET /v1/me`. The account's lenses are returned at sign-in with a count each, a
single-lens account skips the picker entirely rather than being shown a list of
one, and every screen offers a switcher. Measured before adoption at 50,000
accounts and 200,000 enrollments: 0.20 ms, index-only.

## Q12. Can one account hold both links on one enrollment?

[Answer]: Allow it, with no special case. Both `student_account_id` and
`guardian_account_id` may hold the same account id — an adult student who needs
no guardian, or a teacher enrolling their own child. The schema already permits
it; nothing special-cases it, and the person simply sees that seat in both
lenses.

## Q13. What does a person see when they accept a seat that already owes money?

[Answer]: Everything since the seat was created, including dues accrued before
acceptance. The decisive argument is agreement rather than kindness: the teacher
has been looking at those dues on the roster since the day they added the seat,
so a student view that started at the acceptance date would show a different
total for the same seat and neither number would be wrong. One history, two
lenses onto it.

## Q14. What does a teacher see for a seat nobody has accepted?

[Answer]: A pending state on the roster row — added, not yet accepted. This is
the mechanism that catches a mistyped digit: without it, a wrong number is
indistinguishable from a student who simply has not opened the app yet, and the
error is discovered only when someone complains. No automatic nudge in V1; the
visible state is the control.

## Q15. Can a teacher remove or edit a seat after it is accepted?

[Answer]: Edit yes; remove only while the seat is unclaimed. This preserves
FR2.12 exactly as recorded rather than reopening it, and it preserves ADR-003's
"a teacher cannot make their students' records go away" — once a real person is
attached with real dues, the teacher marks them inactive (`inactive_from`) and
the record stands. Acceptance does not create a new removal rule; it gives the
existing dormant-vs-claimed distinction a precise meaning.

## Q16. Where is acceptance built?

[Answer]: With account creation, in the first remaining slice. Acceptance is the
other half of signup — the O1 state-3 path where a student whose teacher already
added them signs up and claims that seat is one continuous flow, not two
features. Building them together also means the pending state is never shipped
without a way to resolve it, which is the failure the re-plan exists to prevent.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

**Lens management, settled first at the user's request:**

- **All three lenses per account, computed per request** — confirmed as built,
  not changed. No role column; the `Owner` row and the two enrollment links are
  the facts the lens reads [BR1.1].
- **A seat requires acceptance before it grants a student or guardian lens.**
  This is the one clause of the user's description with no implementation today.
  Pending seats are visible to the person named; declining is durable.
- **The teacher's side never blocks on acceptance** — roster, batch and fee
  generation all work against a pending seat, with a pending state shown on the
  roster row so a mistyped number is caught rather than discovered later.
- **Acceptance markers are per link, not per row**, matching the existing
  erasure markers [BR6.2].
- **Dues predate acceptance** and are shown in full, so the teacher's roster and
  the student's own view never disagree.
- **Removal stays as FR2.12 and ADR-003 already have it**: edit any time, remove
  only while unclaimed, otherwise mark inactive.
- **One account may hold both links on one seat**, with no special case.
- **Pick a lens at login, switch anywhere** — confirming what is already built.

**The re-cut plan:**

- **Nine remaining Bolts become six deliverable units**, grouped by what a
  person can do when it ships, each cut as a vertical slice: API, screens and
  tests together, with the design artboard named in its Definition of Done.
- **Four Units are built and frozen**; the plan covers only what remains.
- **Account creation and seat acceptance form the first slice** — neither
  exists today, and a teacher can currently only exist by hand-inserting a
  database row.
- **Construction runs autonomously from here**; the payment-slice gate retires
  with the platform subscription it was anchored to. The fee system stays.
- **The already-added lookup names neither teacher nor batch.**
- **`release-packaging` is partly done**: both release gates exist, the
  Macrobenchmark harness does not — and the attendance latency obligation is
  dischargeable only by that harness.
- **Governance stays last and release-blocking**: neither account-deletion path
  exists and both are V1 deliverables, so no public Play track until it lands.
- **Unchanged**: the money boundary, the lens-per-request rule, the privacy
  boundary, the test-first predicate, both coverage floors and both release
  gates. This re-cut changes when work is cut, not what is required of it.

[Answer]: Looks correct
