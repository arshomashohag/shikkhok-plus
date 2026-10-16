# Intent Statement — ShikhokPlus

**Stage**: intent-capture (1.1)
**Phase**: Ideation
**Date**: 2026-10-17

---

## Problem Statement

In Bangladesh, teachers and graduate students earn income through private
tuition: teaching one student or a batch of students, often several subjects per
batch. They currently track batches, students, class schedules, topics covered,
exam dates, marks and month-end fee collection in paper notebooks or Excel, and
communicate through ad-hoc WhatsApp and Messenger groups. ShikhokPlus replaces
all of that with one application. [desc]

Guardians fund this tuition and currently have no visibility into it — no
attendance, no syllabus progress, no marks, no fee history. Serving the guardian
well is what makes the teacher's subscription renew. [desc]

A second, structural problem sits underneath the first: the records a teacher
keeps and the records a guardian needs are the same records, but the two parties
must never see each other's private information. Paper notebooks solve this
accidentally, by being inaccessible. A shared application has to solve it
deliberately. [desc]

---

## Target Customer

**Primary: the private tuition teacher.** The paying customer, and the only
party with write access to teaching records. They manage batches, students,
schedules, topics, exams, marks and fee collection. They carry the cost of the
current paper-based process and the reputational cost of disputes with
guardians. [desc]

**Secondary: the guardian.** Funds the tuition and currently sees nothing.
Receives read-only visibility into their child's batches, attendance, topics
covered, exam results, next payment date and amount, and the payment status of
every past fee cycle. Guardian satisfaction is the stated renewal driver, which
makes the guardian the commercially decisive user even though they are not the
payer of the subscription. [desc]

**Secondary: the student.** Read-only visibility into their own batches,
schedules, topics, exam marksheets and fee status. A student may be under 13 and
still hold an account. [desc] [Q17]

**Operator: the platform owner.** Administers the platform — onboarding
teachers and overseeing subscriptions and their payment status. This persona has
**no surface in V1**: with subscription deferred, there is nothing to activate
programmatically during closed testing, so neither an interface nor
administration APIs ship. Teachers are onboarded manually. [Q1] [Q20]

When the administration surface does arrive, its visibility is already bounded:
an administrator may see subscriber information only — the teacher's name,
subscription plan and payment status — and never any student's or guardian's
data. [Q20]

A single phone number may legitimately be both student and guardian at once;
role is resolved at read time rather than stored, so one account carries
whichever lenses have data. [desc]

---

## Success Metrics

Three measures were selected. [Q4]

| Metric | Measure | Target |
|---|---|---|
| Teacher retention | Teachers still active 3 months after onboarding | Unknown (open question) [assumption] |
| Guardian engagement | Guardians who open the app at least monthly | Unknown (open question) [assumption] |
| Fee collection improvement | Reduction in overdue balances versus the paper baseline | Unknown (open question) [assumption] |

The three measures are confirmed; their numeric targets are not yet set. [Q4]
Without numbers these are directions rather than verifiable criteria, so each
target is carried as an open question into Requirements Analysis, where
requirements will need concrete thresholds to trace to. [assumption]

---

## Initiative Trigger

The trigger is an unserved market need rather than external pressure: an
existing, widespread, entirely manual workflow (paper notebooks, Excel, ad-hoc
messaging groups) with a funding party who currently receives no information at
all. [desc] The opportunity is to serve the guardian, because guardian
satisfaction is what renews the teacher's subscription. [desc]

Commercially, teachers pay a recurring subscription. Collection is manual and
out-of-band for V1: no in-app purchase, no billing integration, and no
subscription state in the V1 data model. [Q1] Subscription is deferred rather
than abandoned — it is skipped for the closed testing period but will be needed,
so the data model and application design must accommodate it from the start
without later rework. [Q20]

---

## Initial Scope Signal

### Workflow-selected scope

`classic`, at comprehensive depth, running a custom 24-stage plan.
[scope] *(workflow-selected — this describes how much process the build runs
through, not the product boundary.)*

### User-confirmed product boundary

**In V1:** individual teachers; student app view; guardian app view; batch
management; schedules; topic log; exams and marksheets; fee cycles; payment
submission and teacher approval. [desc] Plus attendance, recorded per session
and per enrollment, as a primary mid-class path. [Q5] [Q18] Push notifications
and a teacher analytics dashboard remain in scope. [Q12]

**Excluded from V1, by the initial description:** coaching centres
(multi-teacher organisations, org-owned batches, teacher hiring records,
org-level scheduling); a public tutor discovery marketplace; batch messaging or
group chat between batch members; and a Progressive Web App giving the same
experience on desktop. The architecture must absorb all four without rework.
[desc]

**Also deferred, and subject to the same absorb-without-rework requirement:**
teacher subscription state, and the platform administration surface that
depends on it. Both are skipped for the closed testing period and both are
expected later, so the data model and application design must accommodate them
now. [Q20]

**Also excluded from V1, confirmed by the user:** marksheet or report-card PDF
export and sharing; teacher-to-single-student private messaging beyond the batch
announcement already in the model; and multi-device session management or
session revocation for a logged-in account. [Q12]

**Geography and language:** Bangladesh only. The interface follows the device
locale, falling back to English, with Bangla and English both supported from the
start. [Q13] [desc]

**Release-readiness deliverables, in V1:** the initial description names these as
V1 scope alongside the product features, and they are release preconditions
rather than optional extras. [desc]

| Deliverable | Requirement | Source |
|---|---|---|
| Account deletion | An in-app path to delete the account and its associated data, plus an externally accessible route that works without reinstalling the app. Both are required by Google Play for any app allowing account creation. | [desc] |
| Data Safety declaration | Documented content for the Play Data Safety form: exactly what personal data is collected (phone numbers, children's names, attendance, marks), why, whether it is shared, and how it is deleted. | [desc] |
| Privacy policy | Drafted policy content, including any data retained after deletion for security, fraud-prevention or regulatory reasons. | [desc] |
| Children's-data declarations | The Play Console target-audience and Families data-practices declarations implied by the mixed-audience-including-children decision. | [Q17] [desc] |
| Accessibility and back-stack correctness | Accessibility basics and correct back-stack behaviour, both of which Play's pre-launch report checks. | [desc] |

### Decisions that constrain the architecture

These were settled during intent capture and bind later design stages.

| Decision | Detail | Source |
|---|---|---|
| Identity | The phone number is the account; one number is one account permanently. No role field — teacher, student and guardian are lenses resolved at read time from owned batches and enrollments. | [desc] |
| Privacy boundary | Nothing a student or guardian writes is ever visible to any teacher. Two name layers: a teacher-owned `display_name` per enrollment, and an owner-private self-entered profile. No propagation or sync between them. | [desc] |
| Privacy boundary, admin side | A platform administrator may see subscriber information only — the teacher's name, subscription plan and payment status — and never any student's or guardian's data. Binds the administration surface whenever it arrives. | [Q20] |
| Joining | Only teachers create student records, by phone number plus an optional guardian number. No self-registration, no join requests, no invite acceptance. A record stays dormant until that person logs in by OTP; a mistyped number stays dormant forever, which is the correct failure mode. | [desc] |
| Write surface | Teachers have full read/write. Students and guardians are read-only except three writes: submit a payment, hide an inactive batch from their own list, and edit their own profile. | [desc] |
| Login eligibility | Where the teacher records both a student number and a guardian number, both can log in, irrespective of the student's age. | [Q17] |
| Play target audience | Mixed audience including children. Consequently: no advertising or device identifiers (AAID, SIM serial, build serial, BSSID, MAC, SSID, IMEI, IMSI) transmitted anywhere; no ads SDK; no device phone-number read via `TelephonyManager`, so numbers are always typed and never auto-filled from the SIM; COPPA and GDPR-K compliance; Families data-practices declarations in Play Console. | [Q17] |
| Package namespace | `com.shikkhokplus.app`, matching the existing repository spelling. User-facing strings remain "ShikhokPlus", so the product name and the namespace differ by one letter. Deliberate, and permanent once published. | [Q3] [desc] |
| Offline behaviour | Cached reads only. Rosters and schedules are readable offline; every write, attendance included, requires a live connection and fails with a clear retry prompt. | [Q6] [Q18] |
| Fee model | The fee amount is a teacher-adjustable anchor, not a fixed amount due. The teacher decides what is actually charged, received, carried forward or forgiven, and the ledger records it for earnings reporting. Calendar-month periods with a due day are retained. | [Q7] [Q19] |

---

## Assumptions & Open Questions

- Numeric targets for all three success metrics are unset; the measures are
  confirmed but the thresholds are not. Requirements Analysis needs concrete
  numbers for these to be verifiable. [assumption]
- The §11 risk that slow mid-class attendance marking causes teachers to abandon
  the app is accepted rather than mitigated in V1: attendance marking requires
  connectivity, so it will fail on patchy classroom data. Recommended offline
  writes for the mid-class path; the user chose connectivity-required. To be
  revisited if pilot teachers encounter it. [Q18] [assumption]
- Subscription state and the platform administration surface are deferred but
  expected, so both must be absorbable without rework. This is a design
  obligation carried into Domain Design alongside the four exclusions named in
  the initial description, and it is the obligation most easily overlooked
  because nothing in V1 exercises it. [Q20] [assumption]
- The agreed data model in the initial description defines `FeeCycle` with a
  fixed `amount_due` and a stated balance formula. The confirmed fee model
  supersedes that with a teacher-adjustable anchor plus a ledger, so the
  `FeeCycle` shape will be revised at Domain Design. The initial description
  invited exactly this kind of flagged change. [Q19] [desc] [assumption]
- Push notifications remain in V1 scope while messaging and PDF export are
  excluded. Notifications carry server-side delivery infrastructure that the
  excluded features do not, so their cost is larger than their adjacency to
  "small features" suggests. Flagged for scope definition. [Q12] [assumption]
- Pilot teacher group size was not quantified beyond "a small group". [Q10]
  [assumption]
- Subscription state is absent from the V1 data model, so the application cannot
  distinguish an active teacher from a lapsed one, and no feature gating on
  subscription status is possible in V1. This is accepted deliberately for the
  closed testing period. [Q1] [Q20] [assumption]
- With no administration surface in V1, teacher onboarding is a manual
  operation. The mechanism — direct database insertion, a one-off script, or
  something else — is not established, and it is the only way a teacher can
  reach the platform during closed testing. [Q20] [assumption]
- Whether a guardian may have children under more than one teacher
  simultaneously is implied by the per-enrollment guardian capture in the
  initial description but not explicitly confirmed. [assumption]
- The privacy boundary governs teacher-vs-student/guardian and
  admin-vs-student/guardian, but not **teacher-vs-teacher**. Because one phone
  number is one permanent account and students carry their batches across
  teachers, a single account may be enrolled with several teachers at once. What
  Teacher A may learn about Teacher B's batches, fees or marks through that
  shared account is unspecified. The per-enrollment `display_name` and
  per-enrollment guardian capture suggest the intended answer is full isolation
  per teacher, but it is nowhere stated. Domain Design must settle this
  explicitly; it is the one boundary a read-time role resolution could leak
  across by accident. [Q20] [desc] [assumption]

---

## Sources

- [desc] Initial description: the authoritative project description recorded at
  workflow creation.
- [scope] Workflow-selected scope: `classic`.
- [Q1], [Q3], [Q4], [Q5], [Q6], [Q7], [Q10], [Q12], [Q13], [Q17], [Q18],
  [Q19], [Q20] — confirmed answers in
  `intent-capture-questions.md`. (Q16's answer was superseded by Q20.)
