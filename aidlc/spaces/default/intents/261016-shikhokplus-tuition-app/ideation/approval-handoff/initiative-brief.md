# Initiative Brief — ShikhokPlus

**Stage**: approval-handoff (1.7) — closes Ideation
**Date**: 2026-10-17
**Recommendation**: **GO** — proceed to Inception, with three stated reservations

---

## 1. The initiative in one paragraph

In Bangladesh, private tuition teachers track batches, students, schedules,
topics, exams, marks and month-end fee collection in paper notebooks or Excel,
and communicate through ad-hoc messaging groups. Guardians fund this and see
none of it. ShikhokPlus replaces the whole workflow with one Android
application plus a backend: teachers get full read and write, students and
guardians get read-only visibility plus the ability to submit a payment, and the
teacher's cross-batch dues screen shows everyone who owes money across every
batch at once. Guardian satisfaction is the stated driver of subscription
renewal, which makes the guardian commercially decisive even though the teacher
pays. [desc]

---

## 2. Problem and customer

| | |
|---|---|
| **Problem** | An entirely manual, widespread workflow with a funding party who receives no information at all. [desc] |
| **Primary customer** | The private tuition teacher — the paying subscriber and sole author of teaching records. [desc] |
| **Commercially decisive customer** | The guardian — funds the tuition, currently sees nothing, and whose satisfaction renews the subscription. [desc] |
| **Also served** | The student, including under-13s who hold their own account. [desc] [intent: Q17] |
| **Operator** | The platform owner — no surface at all in V1; teachers are onboarded manually. [intent: Q20] |

---

## 3. Feasibility and risk highlights

**Verdict: technically feasible. Schedule is the binding constraint, not
technology.** [feasibility]

Nothing here requires unsolved engineering. The three things that make it harder
than it looks are not technical:

1. The scope is fixed at full V1 with every capability Must Have, so schedule
   variance has nothing to absorb it. [scope: Q7]
2. Half the product is a Jetpack Compose Android client, in a technology with no
   declared experience, reviewed by someone learning it. [feasibility: Q2]
3. A mixed-audience-including-children Play declaration forbids device and
   advertising identifiers, which rules out several otherwise-obvious tools.
   [intent: Q17]

**Costs, verified against current rates rather than assumed:**

| | |
|---|---|
| OTP SMS | BDT 0.25–0.40 per message via local BTRC-approved gateways, against Firebase's India-adjacent USD 0.07 (~BDT 8.50) — roughly 25–30x. At the scale ceiling, Firebase alone would exceed the whole infrastructure budget by ~28x. [feasibility] |
| Infrastructure | ~USD 13/month for closed testing, ~USD 12–30/month at launch. Budget ceiling is USD 50/month. [feasibility: Q3] |

**Three risks accepted rather than mitigated**, confirmed deliberate at this
gate [Q2]:

- **R-7** — attendance marking requires connectivity, so it will fail on patchy
  classroom data. This is the abandonment scenario §11 warns about, accepted as
  a consequence of the cached-reads-only decision. [intent: Q18]
- **R-5** — homemade OTP auth carries residual risk Firebase would have
  absorbed. Mitigated by seven named controls, not eliminated. [feasibility: Q5]
- **No-buffer schedule** — every capability is Must Have, so any slip moves the
  date directly. [scope: Q7]

Full register: 11 risks, 10 assumptions, 8 open issues, 6 dependencies in
`../feasibility/raid-log.md`.

---

## 4. Scope boundary

**In V1**: all seven slices across all three surfaces — auth and identity;
batches and enrollment; schedule, sessions and attendance; exams and marksheets;
fee cycles; payment submission and verification; the cross-batch dues screen.
Plus push notifications, a teacher analytics dashboard, Bangla and English, both
account-deletion paths, and the Play compliance deliverables. Every item is Must
Have. [scope]

**Out of V1, with an architectural obligation to absorb later without rework**:
coaching centres (org-owned batches), the tutor marketplace, batch messaging, a
PWA, teacher subscription state, and the platform administration surface.
[desc §2] [intent: Q20]

**Out of V1 by decision**: marksheet PDF export, teacher-to-student private
messaging, multi-device session management. [intent: Q12]

**Minimum viable scope equals full V1 scope.** The conventional MVP cut was
offered and declined: nothing reaches a tester until the complete product works.
[scope: Q1]

---

## 5. Architecture, approved as a whole

[feasibility: Q11] — full document at `../feasibility/architecture-proposal.md`.

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel/SQLAlchemy, Alembic, Pydantic v2 |
| Database | PostgreSQL 16; money as `NUMERIC(12,2)` / `BigDecimal`, JSON-string transport, never float |
| API | REST over HTTPS, versioned `/v1/`, OpenAPI 3.1 generated from code |
| Android | Compose, Material 3, MVVM, coroutines/Flow, Hilt, Retrofit/OkHttp, Room, Navigation Compose, single activity |
| Auth | Phone OTP via local SMS gateway behind our own endpoints; 15-minute access tokens, rotating 30-day refresh tokens |
| Hosting | Lightsail with containerized Postgres for closed testing, then RDS `db.t4g.micro` at launch; `ap-southeast-1` or `ap-south-1` |

**The four structural decisions that make the deferred capabilities absorbable:**

1. **Ownership indirection** — `Batch.owner_id → Owner(kind: teacher | organisation)` from day one. Coaching centres insert rows; no existing row changes and no `Batch` migration runs. [desc §12b]
2. **Role as a computed lens** — no role field, no cached role; each request re-derives the teacher, student and guardian relationships per resource. One account holding all three lenses needs no special handling. [desc §12c]
3. **Idempotency by constraint** — a unique constraint on `(enrollment_id, period)` with `ON CONFLICT DO NOTHING`, deliberately not an application-level "did I run this month?" check, which fails under concurrency. [desc §12d]
4. **Privacy boundary in three layers** — separate tables by writer, PostgreSQL row-level security on `profile`, and teacher-facing response schemas with no profile fields to populate. Enforced by table design, the database, and the type system rather than by remembering to filter. [desc §12f]

---

## 6. Delivery plan

Solo build; the agent writes most code, the user reviews. [feasibility: Q1] No
mobs to staff. [feasibility: Q1]

**Dependency order** (8 proto-Units, ~70 capabilities in
`../scope-definition/intent-backlog.md`):

```
PU-1 auth & identity
 └─> PU-2 batches & enrollment
      ├─> PU-3 schedule, sessions, attendance  ─┐ mutually
      ├─> PU-4 exams & marksheets               │ independent
      └─> PU-5 fee cycles                      ─┘
           └─> PU-6 payment submission & verification
                └─> PU-7 cross-batch dues screen
PU-8 cross-cutting spans all of the above
```

Critical path: PU-1 → PU-2 → PU-5 → PU-6 → PU-7. PU-3, PU-4 and PU-5 are the
only parallelisation opportunity.

**Timeline: 8–12 weeks of build, then Play's 14-day closed-testing window.** The
one-month target recorded at feasibility is superseded. [scope: Q7] This is a
range, not an estimate — see reservations below.

---

## 7. Go/no-go recommendation

**GO.** [Q3]

Ideation produced an approved intent, a costed and verified architecture, 35
constraints, an 11-risk register, a fixed scope and a dependency-ordered
backlog. The architecture answers all six of the §12 questions explicitly, and
the four deferred-capability obligations have concrete structural mechanisms
rather than assurances.

**Three reservations, stated rather than buried:**

1. **The timeline is a range, not an estimate.** 8–12 weeks is judgement, not
   measured velocity on a codebase that does not exist. It firms up as slices
   complete.
2. **One Must Have specifies nothing.** The teacher analytics dashboard is
   mandatory with no defined content, so it cannot be sized, built or tested as
   it stands, and it is excluded from the 8–12 week range. Requirements Analysis
   must define it first. [scope: Q4]
3. **The Android client is the thinnest-reviewed surface.** Conventional choices
   reduce this risk; they do not remove it. The honest alternative — React
   Native or Flutter, applying existing JS/TS knowledge — was assessed and
   rejected on APK-size and SDK-audit grounds, but it remains a defensible
   trade-off if client-side review quality proves to be the binding problem.
   [feasibility: Q2] [architecture §9]

---

## 8. Open questions entering Inception

**Four with owning stages** — safe to carry:

| Question | Owner |
|---|---|
| The teacher-vs-teacher privacy boundary. One permanent account can be enrolled with several teachers, and read-time role resolution could leak across that edge. | Domain Design (2.6) |
| `FeeCycle` redesign to the anchor-plus-ledger model, superseding §10. | Domain Design (2.6) |
| Success-metric numeric targets — three measures confirmed, no thresholds. | Requirements Analysis (2.3) |
| The analytics dashboard's content. | Requirements Analysis (2.3) |

**Three carried without an owning stage** [Q1]:

| Question | Blocks |
|---|---|
| SMS gateway vendor selection, with delivery reliability and masked-sender support verified rather than priced. | PU-1 implementation |
| Play Console account type — a personal account created after 13 Nov 2023 needs 12 testers opted in continuously for 14 days before production access. The pilot group was described as smaller than that. | The release plan |
| Teacher onboarding mechanism for closed testing — no admin surface exists in V1. | Closed testing |

**One resolved during this stage**: FCM is permissible under the
no-device-identifier constraint. It routes on app-instance-scoped Firebase
installation IDs, deletable by API, and the documented collection excludes AAID,
IMEI, MAC and Android ID. [firebase-privacy]

---

## Assumptions & Open Questions

- The 8–12 week build range is the agent's judgement, not measured velocity.
  [assumption]
- The analytics dashboard's cost is unknown because its content is undefined,
  and it is therefore excluded from that range. [assumption]
- A-7 from the RAID log remains the largest untested product assumption: that
  read-only visibility is genuinely what students and guardians want, and
  sufficient to drive renewal. No stage in the current plan validates it, since
  market research was skipped; pilot teacher feedback is the only mechanism.
  [assumption]
- Play's 12-tester/14-day requirement is verified, but which account type will
  be used is not, so whether it applies is unknown. [assumption]
- FCM's permissibility is inferred from Firebase's own privacy documentation
  listing installation IDs as the identifier used, and from the absence of
  prohibited identifiers in that documentation. It is not a statement from
  Google about Families-policy compliance specifically. [assumption]
- Local SMS gateway rates are advertised prices, not negotiated quotes, and may
  carry minimum commitments. [assumption]

## Sources

- [desc] Initial description, including §2, §12.
- [Q1]–[Q3] Confirmed answers in `approval-handoff-questions.md`.
- [intent: Q12], [intent: Q17], [intent: Q18], [intent: Q20] — from
  `../intent-capture/`.
- [feasibility: Q1], [feasibility: Q2], [feasibility: Q3], [feasibility: Q5],
  [feasibility: Q11], [architecture §9] — from `../feasibility/`.
- [scope: Q1], [scope: Q4], [scope: Q7] — from `../scope-definition/`.
- [firebase-privacy] https://firebase.google.com/support/privacy — retrieved
  2026-10-17.
