# User Stories — Story Plan and Questions

**Stage**: user-stories (2.4)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [desc] Initial description, §3–§10.
- [scope] Workflow-selected scope: `classic`.
- [upstream] `inception/requirements-analysis/requirements.md` — 84 FR, 17 NFR, approved.
- [upstream] `inception/practices-discovery/team-practices.md` — affirmed practices, now governing rules.
- [upstream] `ideation/scope-definition/intent-backlog.md` — 8 proto-Units in dependency order.

---

## The plan

**Personas**: four. Teacher, student, guardian, plus the platform owner recorded
for completeness with no V1 stories [intent: Q20].

**Format**: "As a [persona], I want [goal], so that [benefit]", with
Given/When/Then acceptance criteria as the inception phase rules require. Stable
`US{group}.{seq}` IDs and three-segment `AC{group}.{seq}.{n}` criterion IDs.

**Breakdown**: by **proto-Unit**, matching the eight-slice dependency order from
the backlog rather than by persona or by screen. Reasoning: the slices are
already the delivery sequence, each is independently testable, and the Unit DAG
that Units Generation produces will consume this grouping directly. Grouping by
persona would scatter each slice across three places and break the
Independent part of INVEST.

**Priority**: MoSCoW, but see Q1 — every V1 capability is already Must Have, so
priorities describe sequencing value rather than a cut line.

**Expected volume**: roughly 45–60 stories. The 84 requirements do not map one
to one: several collapse into a single story (FR2.10 and FR2.11 are one
behaviour from the teacher's side), and a few expand into several (FR9's
correction history behaves differently for marks, fees and verifications).

---

## Q1. Should stories carry MoSCoW priorities at all, given everything is Must Have?

Scope Definition fixed every V1 capability as Must Have with no Should or Could
tier [scope: Q7], and Delivery Planning owns the real sequencing decision. So
MoSCoW here would mark 55 stories "Must Have" and tell you nothing.

Two alternatives are more useful: rank by what the slice order already implies,
or mark the handful of stories that could be dropped without breaking a slice.

- A. Mark everything Must Have, as Scope Definition decided — consistent, uninformative
- B. No priority field; the slice order carries the sequencing and Delivery Planning owns the rest
- C. Priority within each slice — which stories must work for the slice to be demonstrable, versus which complete it
- D. Flag the small number of stories that could be dropped without breaking their slice, as a reserve if the timeline bites
- X. Other (please specify)

[Answer]: A

---

## Q2. How granular should a story be where one requirement has several actors?

Example: a teacher corrects an exam mark. The requirement is FR9.1–FR9.3. But
three parties experience it — the teacher making the correction, the student
seeing their mark change, and the guardian seeing it change. One story with
criteria covering all three, or three stories?

This decision sets the shape of roughly a third of the backlog, because the
privacy boundary means most teacher actions have a student-side and
guardian-side consequence.

- A. One story per actor — "As a teacher I correct a mark", "As a student I see my corrected mark". More stories, each independently testable, each with one clear actor
- B. One story per behaviour, with acceptance criteria covering every actor's view. Fewer stories, criteria carry the asymmetry
- C. One story per actor only where the experience differs meaningfully; otherwise one story with multi-actor criteria
- X. Other (please specify)

[Answer]: A

---

## Q3. Should the dormant-account lifecycle get its own stories?

FR1.7–FR1.11 describe a record that exists for the teacher but is not yet
claimed by the person. It is unusual enough that it behaves differently for
every persona, and the mistyped-number case is specified as *correct* behaviour
rather than an error [FR1.9].

I can fold this into the enrollment stories as acceptance criteria, or give it
its own group — it is arguably the most mis-implementable part of the identity
model.

- A. Its own story group, because the behaviour is unusual and spans personas
- B. Acceptance criteria inside the enrollment stories, since it is a state of an enrollment rather than a feature
- C. Both — criteria in the enrollment stories, plus one story covering the first-login claim moment
- X. Other (please specify)

[Answer]: A

---

## Q4. Do the 17 non-functional requirements get stories?

NFRs are not user stories in the usual sense — "As a teacher I want the app
under 15 MB" is not a goal anyone has. But several have user-visible behaviour
that needs acceptance criteria: offline cached reads [NFR4], the connectivity
retry prompt [NFR5], Bangla layout [NFR3].

The later NFR Requirements stage (3.2) exists specifically for these, so there
is a real question of whether to cover them here at all.

- A. No NFR stories; traceability marks all 17 Deferred to nfr-requirements
- B. Stories only for the NFRs with user-visible behaviour (offline reads, retry prompt, localization), the rest Deferred
- C. A story for every NFR, however awkward the phrasing
- X. Other (please specify)

[Answer]: A

---

## Q5. Is there a persona detail I have wrong?

I will write four personas from the brief and the approved artifacts. Before I
do — these are the things I would be guessing at, and a wrong guess shapes every
story's "so that" clause.

(Select all that need correcting, or A if the guesses are fine.)

- A. The guesses below are close enough
- B. Teacher tech comfort — I assume moderate: uses WhatsApp and Messenger daily, but has never used a purpose-built app for this, and abandons tools that are slower than paper
- C. Student age range — I assume 11–18, secondary school, with under-13s present and logging in [intent: Q17]
- D. Guardian tech comfort — I assume lower than the teacher's, possibly sharing a device, and primarily motivated by fee transparency rather than academic detail
- E. Device reality — I assume a shared or low-end Android phone, mobile data rather than wifi, and data cost being a real consideration
- X. Other (please specify what I have wrong)

[Answer]: A, B, C, D — clarified at Q6 below. The answer was ambiguous as given
(A says the guesses are fine; B, C and D were the individual guesses), and the
question was badly built: it listed the guesses as selectable corrections rather
than stating them and asking only what was wrong. Resolved at Q6: B, C and D
stand as written; E is wrong.

---

## Q6. Device and connectivity reality (clarifying Q5)

**Q6.1 — what Q5's answer meant**

- A. All four guesses right, including device reality
- B. B, C and D right; E needs changing
- C. B, C and D are the ones needing correction
- X. Other (please specify)

[Answer]: B. The teacher, student and guardian assumptions stand as written. The
device-reality assumption is wrong.

**Q6.2 — the actual device and connectivity picture**

- A. Not shared — own phones, decent data
- B. Own phones, but data cost still matters
- C. Shared, but wifi is common
- D. Mid-range phones, not low-end
- X. Other (please specify)

[Answer]: A. Teachers, students and guardians each have their own phone, and
mobile data is cheap and plentiful enough not to be a design constraint.

**Consequences, recorded rather than silently applied:**

1. **No shared-device privacy concern.** I was about to write personas and
   stories around a guardian and child sharing a handset, which would have
   raised a question the §4 privacy boundary does not address — the boundary
   governs what each *account* sees, not what a second person looking at the
   same screen sees. That question does not arise. One fewer thing to design
   around.
2. **The caching rationale weakens but does not disappear.** [NFR4]'s cached
   reads were justified partly by data cost. With data cheap, the remaining
   justification is patchy *connectivity* rather than expensive bytes — a
   classroom with poor signal is still a classroom with poor signal, and
   [NFR5] still forbids offline writes. So cached reads stay, on narrower
   grounds.
3. **[NFR2]'s device floor may now be too conservative, and it is not changed
   here.** `minSdk` 24 with a 2 GB RAM floor was chosen for low-end devices
   [A8]. "Own phones with decent data" does not by itself say the phones are
   newer — a personal phone can still be an entry-level Android — so the floor
   is left as approved rather than loosened on an inference. Flagged for NFR
   Requirements (3.2), which owns device targets, with the note that raising
   `minSdk` would reduce test surface and allow newer APIs. Raising it is a
   one-line change now and a compatibility break after release.

---

## Q7. Mob triage — three judgment calls

The three specialists raised these; each has two legitimate positions, so the
stage protocol routes them to you rather than letting me pick. Everything else
from the mob was either a mechanical fix (applied) or a knowledge dispute I
resolved in the artifact.

**Q7.1 — A requirements-level contradiction I introduced**

A student marked inactive from **10 March**:

- **FR5.3** generates cycles where `inactive_from` "falls after the period".
  10 March falls *inside* March, not after it — so March generates **no cycle**.
- **FR5.6** says an already-generated March cycle **stands in full**.

Both describe the same calendar situation. Which applies depends only on
whether the daily generation job happened to run before the 10th. So the same
departing student owes either a full month or nothing, decided by job timing —
and the inception rules forbid carrying an unresolved contradiction forward.

- A. The period containing `inactive_from` always generates and the cycle stands in full. The teacher adjusts if they choose. Consistent with the Q3 answer; a student leaving on the 1st still owes the full month.
- B. The period containing `inactive_from` never generates. Nothing is owed for a partial month, and FR5.6 then only covers a cycle generated before the teacher marked them inactive.
- C. Generation depends on a day threshold within the period — specify the day.
- X. Other (please specify)

[Answer]: A

**Q7.2 — An approved payment exceeding what was charged**

Nothing in the requirements covers it, and the ledger records charged,
received, carried forward and forgiven [FR5.1] — with no credit field. The
affirmed Hypothesis invariant says outstanding never goes negative, so an
overpayment has nowhere to go. AC6.3.7 was written as a credit carried forward
because it is the only option consistent with that invariant, but it introduces
a concept the model does not have.

- A. Credit carried forward — add a credit concept to the ledger, applied automatically against the next cycle
- B. Refuse at verification — a teacher cannot approve more than was charged, so an overpayment is handled by the teacher adjusting the charge upward first
- C. Allow it and let outstanding go negative, dropping the never-negative invariant
- X. Other (please specify)

[Answer]: A

**Q7.3 — The mistyped number is invisible to everyone**

AC1.3.2 guarantees no notification is ever sent to a dormant number, and
AC1.3.3 says a dormant enrollment is not marked on the roster. Together, a
teacher who mistyped a guardian's number believes that guardian is receiving
updates, and the guardian never knows they were enrolled. The failure is
mutually invisible — and the design reviewer argued that this, not roster
clutter, is the real problem.

The counter-argument, which I accept: dormant is the *normal* state early on,
so decorating the roster would flag most of it as a problem.

- A. Keep the roster undecorated, but show claim status on the enrollment detail with a path to correct the number
- B. As A, plus a batch-level count ("9 of 12 have signed in") so a teacher can see the scale without per-row clutter
- C. Mark unclaimed enrollments on the roster after all — the information matters more than the clutter
- D. Leave it entirely as drafted; a teacher who mistypes finds out when the guardian complains
- X. Other (please specify)

[Answer]: B

---

## Consolidated Summary Confirmation

Does this all look correct?

- Stories are grouped by proto-Unit in dependency order, with one story per
  actor, and every story marked Must Have per the Scope Definition decision.
- Four personas: teacher, student, guardian, plus the platform owner recorded
  with no V1 stories. Teacher, student and guardian assumptions stand as
  drafted; the device picture is corrected to own phones with cheap, plentiful
  data, which removes the shared-device privacy question entirely.
- The dormant-account lifecycle has its own story group, and the 17
  non-functional requirements get no stories of their own — all are Deferred to
  their owning stages in traceability, except three whose user-visible
  behaviour is testable now (localization, offline reads, the retry prompt).
- The period containing `inactive_from` always generates a fee cycle and that
  cycle stands in full, whether it was generated before or after the teacher
  marked the student inactive. A student leaving on the 1st still owes the full
  month unless the teacher adjusts it. This amends FR5.3 in
  `requirements.md`, because the contradiction was in the requirement itself.
- An approved payment exceeding what was charged is accepted, and the excess is
  recorded as a **credit** carried to the next cycle. The ledger therefore
  records five quantities rather than four — charged, received, carried forward,
  forgiven and credited — which amends FR5.1 and adds FR5.9.
- A dormant enrollment is not marked on the roster, because dormant is the
  normal early state. Claim status appears on the enrollment detail with a
  path to correct the phone number, plus a batch-level count of how many
  enrollments have been claimed.
- Five stories were added after the specialist round: the OTP abuse controls as
  their own story, per-request role resolution, a cross-cutting write-failure
  story, a Bangla-behaviour story, and an adversarial privacy-boundary story
  covering requests for data that is not the requester's.
- The shared marksheet shows the viewer's own mark named, plus rank, batch
  average, highest mark and a banded distribution — not a list of other
  students' individual marks, because a dozen unattributed marks in a batch
  that sits together are deanonymised by inference within a day. This changes
  how FR4.5 is satisfied, not FR4.5 itself.
- Mid-class attendance defaults every student to present so only exceptions are
  marked, and writes the whole roster in one atomic operation. These are the
  structural properties standing in for the speed requirement that was dropped;
  nothing in V1 measures elapsed time.
- Traceability covers all 102 requirements: 88 OK, 13 Deferred to named stages,
  1 not applicable with justification, and no gaps.

[Answer]: Looks correct
