# Intent Backlog — ShikhokPlus V1

**Stage**: scope-definition (1.4)
**Phase**: Ideation
**Date**: 2026-10-17

Proto-Units, in dependency order. Units Generation (2.7) converts these into the
formal Unit DAG; Delivery Planning (2.9) chooses the economic path through it.

---

## Prioritization method

**MoSCoW, with a single tier.** Every item is **Must Have** by the user's
explicit decision [Q7]. Nothing is Should Have, Could Have or Won't Have at this
stage.

A single-tier MoSCoW carries no ranking information, so **the backlog is ordered
by dependency instead**, following the slice order stated in the initial
description §13.4. Where an item could sit in more than one slice, it is placed
at the earliest slice that can deliver it completely.

WSJF and RICE were considered and are not used: both rank items against each
other to decide what to drop or defer, and with nothing droppable they would
produce scores that change no decision.

---

## PU-1 — Authentication and identity

**Slice 1.** Foundation; everything depends on it.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-1.1 | Phone-number account creation; one number is one account permanently | Must | [desc §3] |
| PU-1.2 | OTP issue endpoint with the seven abuse controls (per-number and per-IP rate limits, 5-minute single-use OTP, 5 verify attempts, hashed storage, enumeration resistance, global daily SMS ceiling) | Must | [feasibility: Q5] [architecture §7] |
| PU-1.3 | OTP verify endpoint issuing a 15-minute access token and a rotating 30-day refresh token | Must | [architecture §7] |
| PU-1.4 | Local SMS gateway integration, abstracted behind an interface so the vendor is swappable | Must | [feasibility: Q5] [feasibility: R-9] |
| PU-1.5 | Android OTP entry with SMS Retriever autofill; no SMS permission, no `TelephonyManager` read | Must | [desc §11] [TC-4] [TC-5] |
| PU-1.6 | Role resolution at read time — teacher, student and guardian lenses computed per request from owned batches and enrollments | Must | [desc §3] [desc §12c] |
| PU-1.7 | Login offers only the roles that have data | Must | [desc §3] |
| PU-1.8 | In-app role switcher; no logout required | Must | [desc §3] |
| PU-1.9 | Owner-private profile: self-entered name and photo, visible only to the owner, with helper text stating it does not change what teachers see | Must | [desc §4] |
| PU-1.10 | Privacy boundary enforcement: separate tables by writer, row-level security on `profile`, teacher-facing response schemas with no profile fields | Must | [desc §4] [desc §12f] [architecture §8f] |
| PU-1.11 | Account deletion — in-app path | Must | [desc §11] |
| PU-1.12 | Account deletion — externally accessible web route, usable without reinstalling the app | Must | [desc §11] [TC-19] |
| PU-1.13 | Bangla and English string resources, device-locale-driven falling back to English | Must | [desc §11] [intent: Q13] |

**Proves**: the identity model works, including one account holding several
lenses, and the privacy boundary holds structurally.

---

## PU-2 — Batches and enrollment

**Slice 2.** Depends on PU-1.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-2.1 | `Owner` indirection: `Batch.owner_id → Owner(kind: teacher \| organisation)` from day one | Must | [desc §12b] [architecture §8b] |
| PU-2.2 | Batch creation: name, subjects, default monthly fee, fee due day, weekly schedule slots | Must | [desc §6] |
| PU-2.3 | Add a student by phone plus optional guardian phone plus teacher-typed display name | Must | [desc §6] |
| PU-2.4 | Dormant account creation — a record exists until that person first logs in by OTP; a mistyped number stays dormant forever | Must | [desc §3] |
| PU-2.5 | Attaching to an existing account when another teacher already entered that number | Must | [desc §3] |
| PU-2.6 | Per-enrollment guardian capture — two teachers may hold different guardian numbers for the same student and neither is wrong | Must | [desc §10] |
| PU-2.7 | Per-student fee override, falling back to the batch default when null | Must | [desc §6] [desc §10] |
| PU-2.8 | Multiple enrollment — a student in two batches is enrolled twice | Must | [desc §6] |
| PU-2.9 | **Mark inactive from a date**, not a boolean: stops future fee cycles, leaves existing dues standing, student may stay active in other batches | Must | [desc §6] [Q5] |
| PU-2.10 | Edit student details, including the teacher-owned display name | Must | [desc §6] |
| PU-2.11 | Student and guardian batch lists | Must | [desc §7] [desc §8] |
| PU-2.12 | Guardian child selection, for guardians with multiple children | Must | [desc §8] |
| PU-2.13 | Hide an inactive batch from the student's or guardian's own list | Must | [desc §5] |
| PU-2.14 | Cached reads of rosters and batch lists via Room, with staleness shown | Must | [intent: Q18] [architecture §6] |

**Proves**: students carry batches across teachers, and the two name layers
stay separate.

---

## PU-3 — Schedule, sessions and attendance

**Slice 3.** Depends on PU-2. **First slice at which the guardian gains
anything.**

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-3.1 | Weekly schedule slots per batch | Must | [desc §6] [desc §10] |
| PU-3.2 | Session records with subject and topic covered | Must | [desc §6] |
| PU-3.3 | Session status: scheduled, held, cancelled | Must | [desc §10] |
| PU-3.4 | Reschedule or cancel a session | Must | [desc §6] [Q5] |
| PU-3.5 | **Attendance per session per enrollment** — a primary mid-class path; requires connectivity and fails with an explicit retry prompt | Must | [intent: Q5] [intent: Q18] |
| PU-3.6 | Mid-class attendance UX fast enough to use in a real class | Must | [desc §11] |
| PU-3.7 | Next class date and time, student and guardian view | Must | [desc §7] |
| PU-3.8 | Topics covered, student and guardian view | Must | [desc §7] |
| PU-3.9 | Per-batch announcements | Must | [desc §6] |
| PU-3.10 | Attendance visible to student and guardian | Must | [desc §1] |

**Proves**: the mid-class path is usable on a real classroom network — the
accepted risk R-7, and the thing pilot feedback is most needed on.

---

## PU-4 — Exams and marksheets

**Slice 4.** Depends on PU-2; independent of PU-3.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-4.1 | Exam creation per batch and subject, with date and total marks | Must | [desc §6] [desc §10] |
| PU-4.2 | Mark entry per enrollment | Must | [desc §6] |
| PU-4.3 | Full batch marksheet visible to students and guardians — all students in that batch, for each past exam | Must | [desc §7] |
| PU-4.4 | Marksheet scoped to the batch only, never across batches | Must | [desc §7] |
| PU-4.5 | Per-batch `marksheet_visible` toggle, default on | Must | [desc §10] |
| PU-4.6 | Exam dates, student and guardian view | Must | [desc §7] |
| PU-4.7 | Guardian view of a child's progress across exams over time | Must | [desc §8] |

**Proves**: batch-scoped visibility holds, and the marksheet toggle works per
batch.

---

## PU-5 — Fee cycles

**Slice 5.** Depends on PU-2. **Money begins here; tests are mandatory.**

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-5.1 | Fee model: amount as a teacher-adjustable anchor, with a ledger of what was charged, received, carried forward or forgiven | Must | [intent: Q19] |
| PU-5.2 | Calendar-month periods with a due day, clamped for short months | Must | [intent: Q19] |
| PU-5.3 | Monthly generation where `inactive_from IS NULL OR inactive_from > period` | Must | [desc §10] |
| PU-5.4 | **Idempotent generation** — unique constraint on `(enrollment_id, period)` with `ON CONFLICT DO NOTHING`; running twice equals running once | Must | [desc §12d] [architecture §8d] |
| PU-5.5 | Scheduled generation job, running daily so a missed day self-heals | Must | [architecture §8d] |
| PU-5.6 | Money as `NUMERIC(12,2)` / `BigDecimal`, JSON-string transport, never float; arithmetic confined to one module | Must | [feasibility: Q8] [TC-7] |
| PU-5.7 | **Mandatory tests**: fee-cycle arithmetic, carry-forward, partial approval, waiver | Must | [desc §13.6] [TC-20] |
| PU-5.8 | Student view of own fee status and history | Must | [desc §7] |
| PU-5.9 | Guardian view of next payment date and amount, and every past cycle's status | Must | [desc §8] |

**Proves**: the money arithmetic is correct and generation cannot double-charge.

---

## PU-6 — Payment submission and verification

**Slice 6.** Depends on PU-5.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-6.1 | One identical submission form in both student and guardian views: select batch, enter transaction ID, enter amount | Must | [desc §9] |
| PU-6.2 | Batch resolves to enrollment resolves to the open fee cycle | Must | [desc §9] |
| PU-6.3 | Partial amounts allowed | Must | [desc §9] |
| PU-6.4 | Pending verification list per batch | Must | [desc §6] |
| PU-6.5 | Approve in full | Must | [desc §6] |
| PU-6.6 | Approve a smaller amount than claimed | Must | [desc §6] |
| PU-6.7 | Reject | Must | [desc §6] |
| PU-6.8 | **Log who approved and when** — the dispute surface | Must | [desc §6] |
| PU-6.9 | On partial approval, choose carry-forward or waive | Must | [desc §6] |
| PU-6.10 | Guardian and student view of payment history | Must | [desc §8] |

**Proves**: the verification path produces a defensible audit trail when a
dispute arrives.

---

## PU-7 — Cross-batch dues screen

**Slice 7.** Depends on PU-6. **Non-negotiable** [Q6]. The subscription
justification.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-7.1 | Everyone who owes money right now, across all of a teacher's batches, with amounts | Must | [desc §6] |
| PU-7.2 | Driven by outstanding balance, **not** by active status — students who left owing money still appear | Must | [desc §6] |
| PU-7.3 | Treated as a first-class feature, not a report | Must | [desc §6] [Q6] |

**Proves**: the thing a teacher would pay for.

---

## PU-8 — Cross-cutting, spanning slices

Not a slice. These are built alongside the slices they touch, and completed
before release.

| # | Capability | Priority | Source |
|---|---|---|---|
| PU-8.1 | Push notifications — FCM integration, token lifecycle, per-event triggering | Must | [intent: Q12] [Q3] |
| PU-8.2 | Teacher analytics dashboard — **content undefined; see open questions** | Must | [intent: Q12] [Q4] |
| PU-8.3 | Bangla text that does not break layouts, on every screen | Must | [desc §11] |
| PU-8.4 | Accessibility basics and correct back-stack behaviour | Must | [desc §11] [TC-18] |
| PU-8.5 | Small APK, low-end device performance | Must | [desc §11] [TC-17] |
| PU-8.6 | AAB output, signing config, release and debug flavours, R8 rules surviving minification | Must | [desc §11] [TC-16] |
| PU-8.7 | Data Safety form content | Must | [desc §11] [RC-4] |
| PU-8.8 | Privacy policy content, including post-deletion retention disclosure | Must | [desc §11] [RC-5] |
| PU-8.9 | Play Console children's-data and target-audience declarations | Must | [intent: Q17] [RC-1] |
| PU-8.10 | `compileSdk` and `targetSdk` 36 | Must | [TC-1] |

---

## Dependency summary

```
PU-1 (auth & identity)
 └─> PU-2 (batches & enrollment)
      ├─> PU-3 (schedule, sessions, attendance)   ─┐
      ├─> PU-4 (exams & marksheets)                │ PU-3 and PU-4 are
      └─> PU-5 (fee cycles)                        │ independent of each
           └─> PU-6 (payment submission & verify)  │ other and of PU-5
                └─> PU-7 (cross-batch dues)       ─┘

PU-8 (cross-cutting) spans all of the above.
```

PU-3, PU-4 and PU-5 are mutually independent once PU-2 exists, so they are the
only parallelisation opportunity in the graph. PU-1 → PU-2 → PU-5 → PU-6 → PU-7
is the critical path.

---

## Assumptions & Open Questions

- **PU-8.2 has no defined content.** The analytics dashboard is Must Have [Q4]
  but nothing specifies what it shows. A Must Have without defined content
  cannot be estimated, built or tested, and it is excluded from the 8–12 week
  range in `scope-document.md` for that reason. Requirements Analysis must
  define it. [assumption]
- **PU-8.1's event set is incomplete.** "Fee reminders and new-marks alerts" are
  named; whether class cancellation, payment approval, announcements or exam
  scheduling also notify is unspecified. [assumption]
- FCM is assumed usable under the no-device-identifier constraint, since its
  registration token is app-instance-scoped rather than a device identifier.
  Unverified against the Families policy text. [assumption]
- Slice placement of each capability is the agent's judgement about the earliest
  slice that can deliver it completely. Units Generation may regroup them.
  [assumption]
- PU-1.6's read-time role resolution is specified but the **teacher-vs-teacher**
  boundary it must respect is still unspecified, carried from intent capture. A
  single account enrolled with several teachers could leak across that edge.
  Domain Design must settle it before PU-1 is built. [assumption]
- PU-5.1's ledger shape supersedes the `FeeCycle` entity in the initial
  description §10, which Domain Design must redesign. [intent: Q19]
  [assumption]
- No estimates are attached to any proto-Unit. With everything Must Have and
  nothing droppable, relative sizing changes no decision at this stage;
  Delivery Planning sizes them when sequencing. [assumption]

## Sources

- [desc] Initial description, including §1, §3–§13.
- [Q1]–[Q7] Confirmed answers in `scope-definition-questions.md`.
- [intent: Q5], [intent: Q12], [intent: Q13], [intent: Q17], [intent: Q18],
  [intent: Q19] — confirmed answers carried from `ideation/intent-capture/`.
- [feasibility: Q5], [feasibility: Q8], [feasibility: R-9], [architecture §6],
  [architecture §7], [architecture §8b], [architecture §8d],
  [architecture §8f], [TC-1], [TC-4], [TC-5], [TC-7], [TC-16], [TC-17],
  [TC-18], [TC-19], [TC-20], [RC-1], [RC-4], [RC-5] — from
  `ideation/feasibility/`.
