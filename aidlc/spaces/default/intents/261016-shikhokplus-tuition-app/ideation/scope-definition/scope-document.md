# Scope Document — ShikhokPlus V1

**Stage**: scope-definition (1.4)
**Phase**: Ideation
**Date**: 2026-10-17

---

## 1. Scope posture

**Scope is fixed. The timeline is the variable.** [Q7]

Every capability below is Must Have. Nothing is designated Should Have or Could
Have, and nothing moved to V2 at this stage. The one-month closed-testing target
recorded at feasibility is superseded: planning proceeds against a realistic
build estimate plus Play's mandatory 14-day closed-testing period. [Q7]

This is a legitimate posture when every feature genuinely matters, and it is the
user's explicit decision. Its consequence is recorded as a risk in §6: with no
lower-priority tier, schedule variance has nothing to absorb it.

---

## 2. In scope for V1

### Teacher surface — full read and write

| Capability | Detail | Source |
|---|---|---|
| Batch creation | Name, subjects taught, default monthly fee, fee due day, weekly schedule slots | [desc §6] |
| Student enrollment | By phone number plus optional guardian phone number plus display name | [desc §6] |
| Per-student fee override | Teachers let some students pay less | [desc §6] |
| Multiple enrollment | A student taking two batches is enrolled twice; everything is batch-level | [desc §6] |
| Mark inactive from a date | Not a boolean. Stops future fee cycles, leaves existing dues standing; the student may remain active in other batches | [desc §6] [Q5] |
| Edit student details | The "my name is spelled wrong on the marksheet" case | [desc §6] |
| Session logging | Record subject and topic covered per session; reschedule or cancel | [desc §6] |
| Attendance | Per session and per enrollment; a primary mid-class path | [intent: Q5] [intent: Q18] |
| Exams | Create per batch and subject with date and total marks; enter marks | [desc §6] |
| Announcements | Per batch | [desc §6] |
| Payment verification | Per batch: approve in full, approve a smaller amount than claimed, or reject. Logs who approved and when | [desc §6] |
| Partial-payment disposition | On approving a partial payment, choose to carry the remainder forward or waive it | [desc §6] |
| Cross-batch dues screen | Everyone who owes money right now across all batches, with amounts. Driven by outstanding balance, not active status: students who left owing money still appear. First-class feature, not a report | [desc §6] [Q6] |
| Analytics dashboard | Must Have | [intent: Q12] [Q4] |

### Student surface — read-only plus three writes

| Capability | Detail | Source |
|---|---|---|
| Batch list | Their batches; everything about a batch lives inside that batch | [desc §7] |
| Per batch | Next class date and time, topics covered, exam dates, announcements | [desc §7] |
| Marksheet | The full marksheet of all students in that batch for each past exam, scoped to that batch only, never across batches. Subject to the per-batch `marksheet_visible` toggle, default on | [desc §7] [desc §10] |
| Own fee status | Status and history | [desc §7] |
| Write: submit a payment | Select batch, enter transaction ID, enter amount | [desc §9] |
| Write: hide an inactive batch | From their own list only | [desc §5] |
| Write: edit own profile | Self-entered name and photo, visible only to the owner | [desc §4] [desc §5] |

### Guardian surface — identical to student, plus child selection

| Capability | Detail | Source |
|---|---|---|
| Child selection | Begins here; a guardian may have multiple children, each in multiple batches | [desc §8] |
| Per child | That child's batches with the same contents as the student view | [desc §8] |
| Progress over time | The child's progress across exams | [desc §8] |
| Payment outlook | Next payment date and amount, and the payment status of every past fee cycle | [desc §8] |
| The same three writes | Submit a payment, hide an inactive batch, edit own profile | [desc §5] [desc §9] |

### Cross-cutting

| Capability | Detail | Source |
|---|---|---|
| Phone-OTP authentication | Local BTRC-approved SMS gateway behind our own endpoints; rotating JWTs | [feasibility: Q5] |
| Role switching | In-app switcher; at login, offer only the roles that have data | [desc §3] |
| Push notifications | Must Have. Fee reminders and new-marks alerts | [intent: Q12] [Q3] |
| Bangla and English | From the start, device-locale-driven falling back to English; no hardcoded strings | [desc §11] [intent: Q13] |
| Account deletion | In-app path plus an externally accessible route usable without reinstalling | [desc §11] |
| Data Safety declaration | Documented content for the Play form | [desc §11] |
| Privacy policy | Drafted content | [desc §11] |
| Accessibility and back-stack | Basics, checked by Play's pre-launch report | [desc §11] |

---

## 3. Out of scope for V1

### Excluded by the initial description, with an architectural obligation

These four must be absorbable without rework. [desc §2]

| Excluded | Architectural obligation |
|---|---|
| Coaching centres — multi-teacher organisations, org-owned batches, teacher hiring records, org-level scheduling | `Batch` ownership indirected through an `Owner` entity from day one, so organisation rows insert without a `Batch` migration [architecture §8b] |
| Public tutor discovery marketplace | No obligation beyond not coupling batch visibility to teacher identity |
| Batch messaging / group chat between batch members | Must land as a new write path, not a reshaping of the read-optimised student and guardian clients [desc §5] |
| Progressive Web App | Every rule server-side; the Android app is one client among future clients. OpenAPI 3.1 generated from code [desc §12a] [architecture §8a] |

### Excluded by user decision at intent capture

| Excluded | Source |
|---|---|
| Marksheet or report-card PDF export and sharing | [intent: Q12] |
| Teacher-to-single-student private messaging beyond the batch announcement | [intent: Q12] |
| Multi-device session management or session revocation | [intent: Q12] |

### Deferred, with the same absorb-without-rework obligation

| Deferred | Obligation | Source |
|---|---|---|
| Teacher subscription state | The data model and app design must accommodate it without rework; skipped for closed testing | [intent: Q20] |
| Platform administration surface | No interface and no APIs in V1. When built, visibility is bounded to subscriber information only — teacher name, plan, payment status — never student or guardian data | [intent: Q20] |

### Excluded by consequence of other decisions

| Excluded | Why |
|---|---|
| Offline write capability | Cached reads only; every write needs connectivity [intent: Q18] |
| Payment gateway integration | Money moves out-of-band via bKash, Nagad or cash; the app records claims and verifications only [desc §9] |
| Any ads SDK | Forbidden under the mixed-audience-including-children declaration [intent: Q17] |
| Any analytics SDK transmitting a device or advertising identifier | Same [intent: Q17]. Product analytics, if wanted, must be first-party and account-keyed |
| High availability / multi-AZ database | Not justified at 100 teachers inside the budget ceiling [feasibility: Q3] [feasibility: Q9] |

---

## 4. Minimum viable scope

The user's decision makes this section unusual: **the minimum viable scope and
the full V1 scope are the same thing.** [Q1] [Q7]

Nothing reaches a tester until all seven slices work across all three surfaces.
The conventional MVP cut — ship the smallest useful thing, learn, then extend —
was offered and declined.

For the record, the cut that was offered and not taken: slices 1–3 (auth,
batches and enrollment, schedule and sessions with attendance) would let a pilot
teacher set up a batch, add students, and run and record real classes. That was
assessed as the smallest build a teacher would use for a real batch.

---

## 5. Value stream

How a capability becomes a customer outcome, and why the slice order is what it
is.

```
Teacher onboards (manual, no admin surface in V1)
  └─> Authenticates by phone OTP                          [slice 1]
       └─> Creates a batch, adds students                 [slice 2]
            ├─> Students and guardians gain an account they can log into
            │    (dormant until first OTP login)
            └─> Runs classes, records topic and attendance [slice 3]
                 ├─> Guardian sees attendance and syllabus progress
                 │    ── first point at which the guardian gains anything
                 └─> Creates exams, enters marks           [slice 4]
                      ├─> Student and guardian see marksheets and progress
                      └─> Fee cycles generate monthly      [slice 5]
                           ├─> Guardian sees next payment date and amount
                           └─> Payment submitted and verified [slice 6]
                                ├─> Guardian sees payment history
                                └─> Cross-batch dues screen  [slice 7]
                                     └─> Teacher sees everyone who owes,
                                          across all batches
                                          ── the subscription justification
```

Two observations from this map:

**The guardian gains nothing until slice 3.** Guardian satisfaction is the
stated renewal driver, so the product's commercial value does not begin until
classes are being recorded. This supports the slice order as stated.

**The subscription justification arrives last.** The cross-batch dues screen is
both the strongest reason to pay and the final slice, which is why Q6 marks it
non-negotiable rather than letting it be the casualty of a slip.

---

## 6. Scope risks

| Risk | Detail | Treatment |
|---|---|---|
| **No prioritization buffer** | Every capability is Must Have [Q1–Q6]. With no Should or Could tier, schedule variance has nothing to absorb it, so any slip moves the date directly. The prioritization guidance warns that if everything is a Must Have, prioritization has not happened. | **Accepted** — the user's explicit decision [Q7]. Mitigation: the slice order is itself a de facto priority sequence, so if a cut becomes necessary later, the last slices are the natural candidates and the dependency graph already permits stopping after any slice. |
| **Play testing clock is additive, not parallel** | Q1 = D means the 14-day/12-tester period starts only after the complete build is finished [feasibility: D-6]. Shipping to testers incrementally would have overlapped it. | **Accepted** — the user's decision. Adds roughly two weeks to the earliest possible production date. |
| **Pilot group may be too small** | Play requires 12 testers for personal developer accounts; the pilot group was described as "a small group" [intent: Q10]. | **Open** — recorded as feasibility I-8. Needs resolving before the release plan is fixed. |
| **Two Must Haves carry hidden cost** | Push notifications bring FCM integration, token lifecycle and per-event triggering, and FCM needs checking against the no-device-identifier constraint [TC-3]. The analytics dashboard has no defined content beyond "Must Have". | **Flagged** — both were raised and confirmed as Must Have [Q3] [Q4]. The analytics dashboard's content is an open question for Requirements Analysis, since "Must Have" without a defined scope cannot be estimated or tested. |
| **No confident delivery date** | A realistic range is 8–12 weeks of build before the testing window, but narrowing it further would be false precision given the client-side unfamiliarity [feasibility: Q2]. | **Accepted** — Delivery Planning sequences the slices; the estimate firms up as slices complete. |

---

## Assumptions & Open Questions

- The analytics dashboard is Must Have [Q4] but its content is undefined. "Must
  Have" without defined content cannot be estimated, built or tested, so
  Requirements Analysis must establish what it shows. Until then its cost is
  unknown and the 8–12 week range excludes it. [assumption]
- Push notifications are Must Have [Q3] but which events trigger them is not
  specified beyond "fee reminders and new-marks alerts". The full event set is an
  open question for Requirements Analysis. [assumption]
- FCM is assumed to be usable under the no-device-identifier constraint, since
  its registration token is app-instance-scoped rather than a device identifier.
  This was not verified against the Families policy text and must be before the
  notifications work begins. [assumption]
- The 8–12 week build estimate is the agent's judgement, not derived from
  measured velocity on this codebase, which does not yet exist. [assumption]
- The slice order is assumed to remain dependency-valid as designed. Units
  Generation and Delivery Planning will confirm the dependency graph; if a
  dependency inverts, the order may need revisiting. [assumption]
- Whether a guardian may have children under more than one teacher
  simultaneously remains unconfirmed, carried from intent capture. It affects
  the guardian child-selection surface. [assumption]
- The teacher onboarding mechanism for closed testing is undefined, since no
  admin surface exists in V1. Carried from feasibility I-6. [assumption]

## Sources

- [desc] Initial description, including §2, §4–§11 and §13.4.
- [Q1]–[Q7] Confirmed answers in `scope-definition-questions.md`.
- [intent: Q5], [intent: Q10], [intent: Q12], [intent: Q13], [intent: Q17],
  [intent: Q18], [intent: Q20] — confirmed answers carried from
  `ideation/intent-capture/`.
- [feasibility: Q2], [feasibility: Q3], [feasibility: Q5], [feasibility: Q9],
  [feasibility: D-6], [feasibility: I-6], [feasibility: I-8],
  [architecture §8a], [architecture §8b], [TC-3] — from `ideation/feasibility/`.
