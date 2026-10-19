# Architecture Proposal — ShikhokPlus

**Stage**: feasibility (1.3)
**Status**: For approval as a whole [Q11]
**Date**: 2026-10-17

This is the consolidated architecture document: stack, database, API style,
Android architecture and auth, with §12a–f of the initial description each
answered explicitly, plus the strongest argument against the recommendation.
Approving it settles these choices; the later design stages elaborate within it
rather than re-deciding it. [Q11]

---

## 1. The constraints that actually decide this

Every recommendation below follows from four facts, not from preference.

| Constraint | Consequence |
|---|---|
| Strong Python and Node/TS, strong SQL, broad AWS. **No declared Kotlin or Android experience.** [Q2] | The backend can be ambitious; the Android app must be conventional. The client is where review will be thinnest, so it gets the most boring, best-documented choices available. |
| Under USD 50/month [Q3] | No Kubernetes, no always-on load balancer at launch, no multi-AZ database in V1. Managed services only where they fit the ceiling. |
| Closed testing in ~1 month [Q4] | Nothing that needs infrastructure learning time. Ship on the shortest path, design so the migration to a sturdier footing is a configuration change. |
| Mixed-audience-including-children Play declaration [intent: Q17] | No third-party SDK that transmits device or advertising identifiers. This disqualifies tools that would otherwise be obvious, and it is the reason several popular choices are absent below. |

---

## 2. Backend stack

**Recommendation: Python 3.12 with FastAPI, SQLModel/SQLAlchemy, Alembic
migrations, Pydantic v2 for schema validation.**

Reasoning, in the order that matters:

1. **It matches your strongest language.** [Q2] You will review every line I
   write. Review quality on an unfamiliar stack is the silent risk in
   agent-written code, and money logic is exactly where that risk is
   unacceptable.
2. **FastAPI generates an OpenAPI schema from the code itself.** That is not a
   convenience here, it is the §12a mechanism: the PWA consumes the same
   contract, generated rather than hand-maintained, so it cannot drift.
3. **Pydantic validation at the boundary** gives one place where the
   JSON-string money representation [Q8] is enforced, rather than per-endpoint
   discipline.
4. **Alembic gives real migrations** from the first commit, which matters
   because the fee model is already known to be changing [intent: Q19].

**Rejected: Node/TypeScript.** You know it too [Q2], and a single language
across backend and a future PWA is a genuine argument. But Python's edge in
decimal arithmetic handling is directly relevant to the money paths, and
FastAPI's schema generation is better than the Node equivalents at the thing
§12a needs most.

**Rejected: Kotlin/Ktor for backend.** Would unify the language across backend
and Android. Dismissed because it puts your weakest language on both sides of
the system.

---

## 3. Database

**Recommendation: PostgreSQL 16.**

Not a close call. The data is relational — accounts, batches, enrollments,
sessions, exams, fee cycles, payments — with integrity constraints that matter
financially. Postgres gives `NUMERIC` for the money representation [Q8], real
foreign keys, transactional DDL for safe migrations, partial and expression
indexes for the cross-batch dues query, and row-level security, which §12f
depends on (see §8 below).

**Rejected: DynamoDB.** Cheaper at rest and tempting on the free tier. Wrong
here: the cross-batch dues screen is an aggregate query across enrollments and
fee cycles, which is precisely what a document store makes hard and SQL makes
trivial. Access patterns are also not yet stable — the fee model is already
being revised — and DynamoDB punishes late access-pattern changes.

**Money columns**: `NUMERIC(12,2)`, BDT only, never `float` or `double`
anywhere in the stack. `BigDecimal` in Kotlin. Serialized across the API as a
JSON **string**, so no decimal is ever an IEEE double in transit. One rounding
mode, declared once, with all money arithmetic confined to a single module.
[Q8]

---

## 4. Hosting — a deliberate two-phase answer

The budget [Q3] and the timeline [Q4] pull in the same direction for closed
testing and a different one at launch, so this is phased rather than single.

### Phase 1 — closed testing (~USD 13/month)

| Component | Choice | Cost |
|---|---|---|
| Application | Lightsail instance, 2 GB RAM / 2 vCPU / 60 GB SSD, Docker Compose | USD 12/month [aws-lightsail] |
| Database | PostgreSQL 16 in a container on the same instance | included |
| Backups | Automated `pg_dump` to S3, lifecycle-managed | ~USD 1/month |
| TLS | Caddy or nginx with Let's Encrypt | free |

Stands up in hours, not days, which is what the one-month timeline needs.

### Phase 2 — launch (~USD 30/month in year 1)

| Component | Choice | Cost |
|---|---|---|
| Database | RDS PostgreSQL `db.t4g.micro`, Single-AZ, encrypted at rest | free for 12 months, 750 hrs/month covers one instance continuously [aws-rds-free] |
| Application | Same container on Lightsail or a small EC2 instance | USD 12/month |
| Backups | RDS automated backups and point-in-time recovery | included |

Because the application is containerized from day one, Phase 1 to Phase 2 is a
connection-string change plus a data migration, not a re-architecture.

**Rejected: ECS Fargate behind an Application Load Balancer.** The correct
answer at a larger scale. An ALB alone is roughly USD 16–18/month, which
consumes a third of the budget before any compute, for load balancing that
100 teachers do not need. [Q3] [Q9]

**Rejected: Lambda plus API Gateway.** Genuinely cheapest at this volume, and I
considered it seriously. Two problems: RDS Proxy is effectively required
(Lambda connection churn exhausts a `t4g.micro`'s connection limit) at about
USD 11/month, erasing much of the saving; and cold starts work against §11's
slow-network responsiveness requirement, where a cold start and a bad network
compound.

**Rejected: Lightsail managed database at the entry tier.** USD 15/month and
convenient, but the entry standard plan does not encrypt storage
[aws-lightsail] — unacceptable for children's names, attendance and marks under
the Families declaration [intent: Q17].

**Region**: `ap-southeast-1` (Singapore) or `ap-south-1` (Mumbai) [Q7]. Mumbai
is geographically closer to Dhaka; Singapore has broader service availability
and is typically better peered. Recommend measuring both from Dhaka before
committing — it is a one-off test and the difference is user-visible on slow
networks.

---

## 5. API style

**Recommendation: REST over HTTPS, JSON, versioned at `/v1/`, with
OpenAPI 3.1 generated from the code.**

**Rejected: GraphQL.** The read-heavy student and guardian clients are the
textbook GraphQL case, and I weighed it properly. Against it: it moves query
shaping to the client, which is exactly wrong when §12f requires the privacy
boundary enforced structurally on the server; every new client query is a new
authorization surface to audit. It also adds a dependency and a learning curve
against a one-month timeline [Q4]. REST with purpose-built read endpoints gives
the same payload efficiency with a fixed, auditable surface.

---

## 6. Android architecture

Deliberately conventional, because you have not declared Android experience
[Q2] and this is where review will be thinnest.

| Concern | Choice | Why |
|---|---|---|
| UI | Jetpack Compose, Material 3 | Current Google default; the best-documented path, which matters most where your review is thinnest |
| Pattern | MVVM — ViewModel plus UI state data classes | The pattern every Android tutorial and Google sample uses |
| Async | Kotlin coroutines and `Flow` | Standard |
| DI | Hilt | Google's own, heavily documented |
| Networking | Retrofit plus OkHttp, kotlinx.serialization | Standard, and money decodes from JSON strings to `BigDecimal` |
| Local cache | Room | Backs the cached-reads-only posture [intent: Q6/Q18] |
| Navigation | Navigation Compose, single activity | Gives correct back-stack behaviour, which Play's pre-launch report checks [intent: desc] |
| Build | Gradle Kotlin DSL, version catalog, R8 minification, AAB output | Per §11 |

**Caching, precisely.** Room holds the last successful read of rosters,
schedules, topics, exams and fee status, so a teacher opening the app mid-class
sees data offline. Every write — attendance included — requires connectivity
and fails with an explicit retry prompt [intent: Q18]. Stale reads show their
age. There is no write queue in V1; that is the accepted risk below.

**No ads SDK. No analytics SDK that transmits a device or advertising
identifier.** The Families declaration forbids it [intent: Q17]. If product
analytics are wanted later, they must be first-party, server-side, and keyed on
the account rather than the device.

---

## 7. Authentication

**Recommendation: phone number plus OTP via a local BTRC-approved SMS gateway,
behind our own issue and verify endpoints. Short-lived JWT access tokens with
rotating refresh tokens.** [Q5]

The cost case is in `feasibility-assessment.md` §3 — roughly 25–30x against
Firebase. Three reasons beyond cost:

1. **Auth logic stays server-side**, which §12a requires so the PWA consumes
   the same API with no backend rewrite.
2. **Firebase's Android SDK uses Play Integrity and device signals**, which
   needs verification against the no-device-identifiers constraint
   [intent: Q17]. I have not confirmed exactly what it transmits; that
   uncertainty is itself a reason to avoid it here.
3. **No `TelephonyManager` read, ever.** The number is always typed. SMS
   Retriever API supplies autofill with no permission at all.

**Token design**: access token 15 minutes, refresh token 30 days and rotating
(each use issues a new one and invalidates its predecessor, so theft is
detectable). Refresh tokens are stored hashed server-side. V1 has no
multi-device session management [intent: Q12], so a refresh token is not
individually revocable by the user — recorded as a known gap.

**Abuse controls, which are ours to build** [Q5]:

| Control | Rule |
|---|---|
| Per-number rate limit | 3 OTP requests per number per hour, 5 per day |
| Per-IP rate limit | 10 OTP requests per IP per hour |
| OTP lifetime | 5 minutes, single use, invalidated on success or expiry |
| Verify attempt limit | 5 attempts per OTP, then invalidate and require a fresh request |
| OTP storage | Hashed, never stored or logged in plaintext |
| Enumeration resistance | Identical response and timing whether or not the number exists |
| Cost circuit-breaker | A global daily SMS ceiling with an alert, so an abuse spike cannot produce an unbounded bill |

That last one exists because the cost model inverts the usual risk: with a local
gateway, SMS abuse is a direct financial attack.

---

## 8. §12 answered explicitly

### a. How a PWA later consumes the same API with no backend rewrite

Every rule lives server-side. The API is the only way in, and the Android app
holds no business logic — it renders what the server computes. Fee balances,
role resolution and authorization decisions are all server-side. The OpenAPI
3.1 schema is generated from the code, so a future PWA generates a typed client
from the same contract. Authentication is bearer tokens over HTTPS, with no
Android-specific mechanism. The one PWA-specific work item is CORS
configuration, which is a setting rather than a rewrite.

### b. How batches become organisation-owned without a painful migration

**Ownership indirection from day one.** `Batch` does not reference a teacher
directly. Instead:

```
Batch.owner_id        -> Owner.id
Owner(id, kind: 'teacher' | 'organisation', ...)
```

In V1 every `Owner` row has `kind = 'teacher'` and a one-to-one relationship
with an `Account`. When coaching centres arrive, organisation rows are inserted
with `kind = 'organisation'`, and a teacher-to-organisation membership table is
added. No existing row changes, no column moves, and no `Batch` migration runs.
The cost today is one join and one extra table — cheap insurance, and the
cheapest point at which to buy it.

### c. How role-as-a-lens is enforced in authorization

Roles are computed, never stored. On each request the token identifies an
account; authorization then asks a question per resource:

- **teacher lens** — does an `Owner` the account controls own this batch?
- **student lens** — is there an enrollment where `student_account_id` is this
  account?
- **guardian lens** — is there an enrollment where `guardian_account_id` is this
  account?

A single account hitting all three lenses in one session is normal and needs no
special handling, because nothing is cached as "the user's role". The client may
send a lens hint to shape the UI, but the server never trusts it for
authorization — it re-derives the relationship every time. Any endpoint that
cannot name which lens authorizes it is a design error.

### d. Where fee-cycle generation runs, and how it stays idempotent

A scheduled job on the application host (systemd timer in Phase 1, EventBridge
Scheduler if we move to Fargate), running daily rather than monthly so a missed
day self-heals.

Idempotency is structural, not procedural: a **unique constraint on
`(enrollment_id, period)`**. Generation inserts with `ON CONFLICT DO NOTHING`.
Running twice, or ten times, produces exactly the same rows. This is deliberately
not an application-level "have I run this month?" check, because that is the
kind of guard that fails under concurrency. The database refuses the duplicate.

Generation covers enrollments where `inactive_from IS NULL OR inactive_from >
period_start`, per the initial description.

### e. OTP provider, SMS costs, rate limiting and abuse

Covered in §7 above and costed in `feasibility-assessment.md` §3. Summary: local
BTRC-approved gateway at BDT 0.25–0.40 per SMS against Firebase's
India-adjacent USD 0.07 (~BDT 8.50); seven named abuse controls including a
global cost circuit-breaker; no specific vendor chosen yet, which is an open
item.

### f. How "nothing a student writes is visible to a teacher" is enforced structurally

Three layers, so that forgetting one does not breach the boundary:

1. **Separate tables by ownership.** Self-entered profile data lives in
   `profile`, keyed to the account and written only by its owner.
   Teacher-authored data lives on the enrollment (`display_name`). They are
   different tables with different writers — a teacher-facing query cannot
   accidentally include profile data, because it would have to join to a table
   no teacher-facing endpoint joins to.
2. **PostgreSQL row-level security.** The `profile` table carries an RLS policy
   restricting rows to the owning account. Even a query that mistakenly joins to
   it returns nothing for a different account. This is the layer that survives a
   coding mistake.
3. **Separate response schemas.** Teacher-facing Pydantic response models have
   no profile fields to populate. A leak would require adding a field to a
   schema, which is a visible, reviewable change rather than a silent one.

The boundary is therefore enforced by table design, by the database, and by the
type system — not by remembering to filter in each query.

---

## 9. The strongest argument against this proposal

Stated properly, because §12 asked for it.

**The Android app is the risk, and this proposal does not remove it.** The
backend choices are safe: your strongest language, a database you know, a
hosting shape you can reason about. But roughly half this product is a Jetpack
Compose application in a language you have not declared experience in [Q2],
reviewed by someone learning it, against a one-month timeline [Q4]. Conventional
choices reduce that risk; they do not eliminate it. A reasonable person would
argue for React Native or Flutter instead — one language across both clients,
your existing JS/TS knowledge applied [Q2], and a PWA story that nearly comes
free.

My counter is that §11's requirements are specifically hostile to that:
small APK, low-end devices, and no third-party SDK transmitting device
identifiers. Cross-platform frameworks add runtime weight and an SDK
surface to audit against the Families declaration. But this is a genuine
trade-off, not a settled question, and if you would rather trade APK size for
your own familiarity, that is a defensible call I would implement.

**The second-strongest: the one-month timeline is unlikely to hold.** Seven
vertical slices across two surfaces, plus Play closed-testing setup, Data Safety
declarations and review lead time. The architecture does not fix a schedule
problem. Expect either a longer first release or a narrower one, and prefer
narrowing: auth, batches, enrollment and attendance is a demonstrable product;
all seven slices half-finished is not.

---

## 10. Open items

| Item | Needs | When |
|---|---|---|
| SMS gateway vendor | Choose among BulkSMSBD, SMS.BD, BD Bulk SMS, MiMSMS and others; verify delivery reliability and masked-sender support, not just price | Before the auth slice |
| Region choice | Measure latency from Dhaka to `ap-southeast-1` and `ap-south-1` | Before provisioning |
| Firebase SDK device signals | Only if Firebase is reconsidered; confirm exactly what Play Integrity transmits | Not needed under this proposal |
| Teacher-vs-teacher privacy boundary | Carried from intent capture, still open | Domain Design |
| Success-metric targets | Carried from intent capture, still open | Requirements Analysis |

---

## Assumptions & Open Questions

- Firebase Phone Auth has no published Bangladesh rate. India's USD 0.07 is the
  nearest published comparator and South Asia generally bands together. The
  order-of-magnitude conclusion is robust; the precise figure is an assumption.
  [assumption]
- Aurora Serverless v2 regional pricing for `ap-southeast-1` and `ap-south-1` is
  not published on the public pricing page, so Aurora was assessed on its
  us-east-1 rate and not recommended at this scale. [assumption]
- AWS free-tier eligibility depends on when the account was created: the
  structure changed on 15 July 2025, and credits are valid up to 12 months.
  Phase 2's "free for 12 months" assumes an eligible account; if the existing
  AWS account [Q6] is older, RDS adds roughly USD 13–15/month and the total is
  about USD 27–30/month, still within budget. [assumption]
- Lightsail's entry managed-database tier is documented as lacking storage
  encryption; higher tiers encrypt. This was taken from the pricing page rather
  than verified in the console. [assumption]
- Mumbai being geographically closer than Singapore does not reliably mean lower
  latency from Dhaka; routing and peering decide it. Hence the recommendation to
  measure rather than assume. [assumption]

## Sources

- [desc] Initial description, including §10–§12.
- [Q1]–[Q12] Confirmed answers in `feasibility-questions.md`.
- [intent: Q6], [intent: Q12], [intent: Q17], [intent: Q18], [intent: Q19] —
  confirmed answers carried from `ideation/intent-capture/`.
- [aws-lightsail] https://aws.amazon.com/lightsail/pricing/ — instance and
  managed-database plans, retrieved 2026-10-17.
- [aws-rds-free] https://aws.amazon.com/rds/free/ and
  https://aws.amazon.com/rds/postgresql/pricing/ — free-tier terms, retrieved
  2026-10-17.
- [aws-aurora] https://aws.amazon.com/rds/aurora/pricing/ — Aurora Serverless v2
  capacity and rates, retrieved 2026-10-17.
