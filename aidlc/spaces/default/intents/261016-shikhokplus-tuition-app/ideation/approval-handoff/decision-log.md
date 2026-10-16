# Decision Log — Ideation Phase

**Stage**: approval-handoff (1.7)
**Date**: 2026-10-17

Every decision made during Ideation, with where it was made and what it binds.
Decisions marked **supersedes** changed something the initial description stated
as agreed; each was explicitly authorised.

---

## Identity and privacy

| # | Decision | Where | Binds |
|---|---|---|---|
| D-1 | The phone number is the account; one number is one account permanently. No role field. | [desc §3] | Schema, auth |
| D-2 | Role is a lens computed at read time from owned batches and enrollments — teacher, student, guardian. One account may hold all three. | [desc §3] [desc §12c] | Every endpoint's authorization |
| D-3 | Only teachers create student records. No self-registration, no join requests, no invite acceptance. A record stays dormant until first OTP login; a mistyped number stays dormant forever. | [desc §3] | Enrollment flow |
| D-4 | Where the teacher records both a student number and a guardian number, **both can log in, irrespective of the student's age**. | [intent: Q17] | Auth eligibility |
| D-5 | Nothing a student or guardian writes is ever visible to any teacher. Two name layers: teacher-owned `display_name` per enrollment, owner-private self-entered profile. No propagation or sync. | [desc §4] | Schema, API, authorization |
| D-6 | A platform administrator may see subscriber information only — teacher name, plan, payment status — never student or guardian data. | [intent: Q20] | Future admin surface |
| D-7 | The privacy boundary is enforced in three layers: separate tables by writer, PostgreSQL row-level security on `profile`, and teacher-facing response schemas with no profile fields. | [desc §12f] [architecture §8f] | Schema, API |

---

## Scope

| # | Decision | Where | Binds |
|---|---|---|---|
| D-8 | Attendance is **in** V1, per session and per enrollment, as a primary mid-class path. Resolves a contradiction in the brief, where §1 and §11 referenced attendance but §2 and §10 contained no attendance entity. | [intent: Q5] | Schema, mid-class UX |
| D-9 | Cached reads only. Rosters and schedules readable offline; every write, attendance included, requires connectivity and fails with an explicit retry prompt. | [intent: Q6] [intent: Q18] | Android data layer |
| D-10 | Teacher subscription is deferred — skipped for closed testing, needed later, so the data model and app design must absorb it without rework. | [intent: Q20] | Schema |
| D-11 | The platform administration surface is **out of V1 entirely** — no interface and no APIs. Teachers are onboarded manually. **Supersedes** the earlier APIs-only answer, on the reasoning that with subscription deferred there is nothing to activate programmatically. | [intent: Q16 → Q20] | V1 scope |
| D-12 | Out of V1 by decision: marksheet PDF export and sharing, teacher-to-single-student private messaging beyond batch announcements, multi-device session management and revocation. | [intent: Q12] | V1 scope |
| D-13 | Push notifications are **in** V1 and Must Have — fee reminders and new-marks alerts. | [intent: Q12] [scope: Q3] | V1 scope |
| D-14 | The teacher analytics dashboard is **in** V1 and Must Have. Content undefined. | [intent: Q12] [scope: Q4] | V1 scope, Requirements Analysis |
| D-15 | The first production release contains all seven slices across all three surfaces. Nothing reaches a tester until the complete product works. | [scope: Q1] [scope: Q2] | Release plan |
| D-16 | The cross-batch dues screen stays last in the slice order and is non-negotiable. | [scope: Q6] | Release completeness |
| D-17 | **Scope is fixed; the timeline is the variable.** Every V1 capability is Must Have; nothing moves to V2. The one-month closed-testing target is superseded. | [scope: Q7] | Planning |

---

## Money

| # | Decision | Where | Binds |
|---|---|---|---|
| D-18 | The fee amount is a **teacher-adjustable anchor**, not a fixed amount due. The teacher decides what is actually charged, received, carried forward or forgiven, recorded in a ledger for earnings reporting. **Supersedes** the `FeeCycle` shape in §10, which defined a fixed `amount_due` with a stated balance formula as the sole truth. | [intent: Q19] | Schema, Domain Design |
| D-19 | Calendar-month periods with a due day, clamped for short months, are retained. The elapsed-day cycle (30 days from batch start) discussed at intent capture is **not** adopted for V1. | [intent: Q19] | Schema |
| D-20 | Money is fixed-point decimal, BDT only: `NUMERIC(12,2)` server-side, `BigDecimal` in Kotlin, never float or double, serialized across the API as a JSON **string** so no decimal crosses as an IEEE double. Rounding mode stated once, centrally; arithmetic confined to one module. The agent argued for integer minor units; the user kept fixed-point decimal, and the serialization rule closes the drift risk that argument was about. | [feasibility: Q8] | Schema, API, client models |
| D-21 | Fee-cycle generation is idempotent **by database constraint** — unique on `(enrollment_id, period)` with `ON CONFLICT DO NOTHING` — not by an application-level guard, which fails under concurrency. Runs daily so a missed day self-heals. | [desc §12d] [architecture §8d] | Schema, scheduled job |
| D-22 | No payment gateway in V1. Money moves out-of-band via bKash, Nagad or cash; the app records the claim and the teacher's verification. | [desc §9] | Removes PCI scope |
| D-23 | Mandatory tests on the money paths: fee-cycle arithmetic, carry-forward, partial approval, waiver. | [desc §13.6] | Test suite, CI |

---

## Architecture

| # | Decision | Where | Binds |
|---|---|---|---|
| D-24 | Backend: Python 3.12, FastAPI, SQLModel/SQLAlchemy, Alembic, Pydantic v2. Chosen for the user's strongest declared language and for schema generation that keeps a future PWA's contract from drifting. Node/TS and Kotlin/Ktor were assessed and rejected. | [feasibility: Q11] [architecture §2] | Implementation |
| D-25 | Database: PostgreSQL 16. DynamoDB rejected — the cross-batch dues screen is an aggregate query, and access patterns are not yet stable. | [architecture §3] | Implementation |
| D-26 | API: REST over HTTPS, versioned `/v1/`, OpenAPI 3.1 generated from code. GraphQL rejected: it moves query shaping to the client, which is wrong when the privacy boundary must be enforced server-side. | [architecture §5] | Contract Design |
| D-27 | Android: Compose, Material 3, MVVM, coroutines/Flow, Hilt, Retrofit/OkHttp, Room, Navigation Compose, single activity. Deliberately conventional because review depth is limited there. | [architecture §6] | Implementation |
| D-28 | `Batch` ownership is indirected through an `Owner` entity from day one, so organisation-owned batches insert rows rather than requiring a `Batch` migration. | [desc §12b] [architecture §8b] | Schema |
| D-29 | Hosting is phased: Lightsail with containerized Postgres for closed testing (~USD 13/month), then RDS `db.t4g.micro` at launch (~USD 12–30/month). ECS Fargate with an ALB, Lambda with API Gateway, and the Lightsail entry managed database were each assessed and rejected — the last because it lacks storage encryption. | [architecture §4] | Infrastructure Design |
| D-30 | Region: `ap-southeast-1` or `ap-south-1`, to be chosen by measuring latency from Dhaka rather than assuming proximity. | [feasibility: Q7] [architecture §4] | Provisioning |
| D-31 | Every rule lives server-side. The Android app holds no business logic; it renders what the server computes. | [desc §12a] | Both surfaces |

---

## Authentication

| # | Decision | Where | Binds |
|---|---|---|---|
| D-32 | OTP via a **local BTRC-approved SMS gateway** behind our own issue and verify endpoints, not Firebase Phone Auth. Cost is ~25–30x in Firebase's favour against us (BDT ~8.50 vs BDT 0.31 per SMS); at the scale ceiling Firebase alone would exceed the whole infrastructure budget by ~28x. Also keeps auth server-side per §12a and avoids Firebase's Play Integrity device signals. | [feasibility: Q5] [architecture §7] | Implementation |
| D-33 | The rate limiting, replay protection, OTP expiry and abuse detection Firebase would have supplied are **ours to build**. Seven named controls, including a global daily SMS ceiling, because per-SMS billing makes abuse a direct financial attack. | [feasibility: Q5] [architecture §7] | Implementation, security review |
| D-34 | Tokens: 15-minute access, 30-day rotating refresh, stored hashed server-side. No individually revocable sessions in V1, since multi-device session management is out of scope. | [architecture §7] | Implementation |
| D-35 | No `TelephonyManager` phone-number read, ever. Numbers are always typed. OTP autofill via SMS Retriever API, which needs no permission. | [intent: Q17] [desc §11] | Auth UI |

---

## Play Store and compliance

| # | Decision | Where | Binds |
|---|---|---|---|
| D-36 | Play target audience: **mixed, including children**. Follows from D-4. Declaring 13+ while under-13s log in would be a misdeclaration, and Play verifies independently. | [intent: Q17] | Play Console, SDK set |
| D-37 | No advertising or device identifier transmitted anywhere — AAID, SIM serial, build serial, BSSID, MAC, SSID, IMEI, IMSI. No ads SDK. No analytics SDK carrying a device identifier. | [intent: Q17] | Every dependency choice |
| D-38 | Package namespace `com.shikkhokplus.app`, matching the existing repository spelling. User-facing strings remain "ShikhokPlus", so the product name and namespace differ by one letter — deliberate, and permanent once published. | [intent: Q3] | Android module, Play Console |
| D-39 | `compileSdk` and `targetSdk` 36 (Android 16). Verified against Google's documentation: API 36+ is already required for all new submissions, with no grace period for a new app. | [play-target-sdk] | Build config |
| D-40 | Both account-deletion paths: in-app, plus an externally accessible route usable without reinstalling. Verified as a Play requirement for any app allowing account creation. | [play-deletion] [desc §11] | Backend, Android, web |
| D-41 | Data Safety form content, privacy policy content, and the Families data-practices declarations are V1 deliverables, not follow-ups. | [desc §11] | Release |
| D-42 | FCM is permissible under D-37. It routes on app-instance-scoped Firebase installation IDs, deletable by API, and the documented collection excludes the prohibited identifiers. | [firebase-privacy] | Push notifications |
| D-43 | Bangladesh only; the interface follows the device locale, falling back to English, with Bangla and English both supported from the start. | [intent: Q13] | Localization |

---

## Process

| # | Decision | Where | Binds |
|---|---|---|---|
| D-44 | One consolidated architecture document, approved as a whole at the feasibility gate, rather than architecture decided piecemeal across three later stages. Later design stages elaborate within it. | [feasibility: Q11] | Workflow shape |
| D-45 | Structural concerns are raised as they arise; naming and conventions are not. | [feasibility: Q12] | How the agent reports |
| D-46 | DECISIONS.md and DEFERRED.md are **not** deliverables — withdrawn from §13.5 of the brief at the user's instruction. This log and the per-stage artifacts carry the equivalent record. | [intent: Q14] | Deliverables |
| D-47 | Three risks are accepted rather than mitigated, confirmed deliberate at the phase gate: connectivity-dependent attendance (R-7), homemade auth residual risk (R-5), and the no-buffer schedule. | [Q2] | Risk posture |
| D-48 | Phase gate: **Go**. Proceed to Inception with three stated reservations. | [Q3] | Workflow |

---

## Decisions that superseded the initial description

Recorded separately because the brief described §10 as agreed and asked for
changes to be flagged.

| # | What changed | Authorised at |
|---|---|---|
| D-11 | Platform admin APIs: added by one answer, then removed entirely by a later one in the same stage. No design work was built on them. | [intent: Q20] |
| D-18 | `FeeCycle`: fixed `amount_due` plus balance formula → teacher-adjustable anchor plus ledger. | [intent: Q19] |
| D-17 | The one-month closed-testing target → timeline as the variable, scope fixed. | [scope: Q7] |
| D-46 | DECISIONS.md and DEFERRED.md withdrawn as deliverables. | [intent: Q14] |
| D-8 | Attendance added, resolving an internal contradiction rather than changing a stated decision. | [intent: Q5] |

---

## Assumptions & Open Questions

- This log records decisions, not their outcomes. Several decisions rest on
  assumptions recorded in `../feasibility/raid-log.md` — notably the SMS cost
  comparison (A-1), the OTP volume model (A-3) and AWS free-tier eligibility
  (A-4). [assumption]
- D-42's FCM permissibility is inferred from Firebase's privacy documentation
  rather than from a Google statement about Families-policy compliance
  specifically. [assumption]
- D-30 names two candidate regions without choosing between them; the choice
  depends on a measurement not yet taken. [assumption]
- D-14's analytics dashboard is a decision to include something whose content is
  undefined, so it is a scope decision without a corresponding design decision.
  [assumption]
- Eight open questions enter Inception, four with owning stages and three
  without, one having been resolved during this stage. They are listed in
  `initiative-brief.md` §8. [assumption]

## Sources

- [desc] Initial description, including §3, §4, §9, §11, §12 and §13.
- [Q1]–[Q3] Confirmed answers in `approval-handoff-questions.md`.
- [intent: Q3]–[intent: Q20] — from `../intent-capture/intent-capture-questions.md`.
- [feasibility: Q5]–[feasibility: Q12], [architecture §2]–[architecture §8f] —
  from `../feasibility/`.
- [scope: Q1]–[scope: Q7] — from `../scope-definition/scope-definition-questions.md`.
- [play-target-sdk] https://developer.android.com/google/play/requirements/target-sdk
- [play-deletion] https://support.google.com/googleplay/android-developer/answer/13327111
- [firebase-privacy] https://firebase.google.com/support/privacy
