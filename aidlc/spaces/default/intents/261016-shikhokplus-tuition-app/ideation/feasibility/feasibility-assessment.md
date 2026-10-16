# Feasibility Assessment — ShikhokPlus

**Stage**: feasibility (1.3)
**Phase**: Ideation
**Date**: 2026-10-17

The architecture recommendation this assessment supports is in
`architecture-proposal.md`, approved as a whole at this stage's gate. [Q11]

---

## 1. Verdict

**Technically feasible. Schedule is the binding risk, not technology.**

Nothing in this product requires unsolved engineering. It is a relational CRUD
application with a strict authorization model, a money ledger, and a mobile
client — all well-trodden. Three things make it harder than it looks, and none
of them is the technology:

1. The one-month closed-testing target against a greenfield two-surface build
   across seven vertical slices. [Q4]
2. No declared Android experience on a product that is half Android client.
   [Q2]
3. A Play declaration that forbids device identifiers, which quietly rules out
   several otherwise-obvious third-party tools. [intent: Q17]

---

## 2. Technical viability by area

| Area | Verdict | Note |
|---|---|---|
| Backend | Low risk | Python/FastAPI matches the strongest declared skill [Q2]; the domain is relational and ordinary |
| Database | Low risk | PostgreSQL; the only non-trivial query is the cross-batch dues aggregate, which SQL handles directly |
| Identity (role-as-a-lens) | Low–medium risk | Computed per request rather than stored; conceptually clean but every endpoint must name its authorizing lens, so it needs discipline rather than cleverness |
| Privacy boundary | Low risk once structural | Separate tables plus row-level security plus distinct response schemas; see `architecture-proposal.md` §8f |
| Money ledger | Medium risk | Not technically hard, but the dispute surface makes correctness non-negotiable, which is why tests are mandatory on these paths [desc §13.6] |
| Fee-cycle generation | Low risk | Idempotency enforced by a unique constraint rather than application logic |
| OTP auth | Medium risk | Building our own rate limiting, replay protection and abuse controls [Q5] is the main self-inflicted risk in this proposal |
| Android client | **Medium–high risk** | Half the product, in the least familiar technology, reviewed by someone learning it [Q2] |
| Offline posture | Low risk | Cached-reads-only is simple to implement; the risk is product acceptance, not engineering [intent: Q18] |
| Play compliance | Medium risk | Not hard, but easy to get wrong late: Data Safety, Families declarations, two deletion paths, pre-launch report [intent: desc] |

---

## 3. OTP cost analysis

The §12e question, answered with current rates rather than training data.

### Local BTRC-approved gateways

| Provider | Rate (BDT/SMS) | Note |
|---|---|---|
| BulkSMSBD | from 0.25 | Claims market-lowest [sms-bulksmsbd] |
| BD Bulk SMS | from 0.30 | Operating since 2015 [sms-bdbulksms] |
| SMS.BD | 0.31 | BTRC approved, REST API [sms-smsbd] |
| MiMSMS | 0.35–0.40 tiered | BDT 2,000/5k SMS to BDT 7,000/20k SMS [sms-mimsms] |
| OnecodeSoft | 0.35 | No validity expiry [sms-onecodesoft] |
| Swift SMS Sender | 0.35 | BTRC approved [sms-swift] |

### Firebase Phone Auth

First 10 SMS/day free (~300/month), then billed per SMS by destination country.
Requires the Blaze plan; phone auth is unavailable on Spark. Google publishes
India at USD 0.07 and does not publish a Bangladesh rate. [firebase-pricing]

### The comparison

At roughly BDT 121/USD, USD 0.07 is about BDT 8.50 — some **25–30x** the local
rate.

| Monthly OTP volume | Local gateway (BDT 0.31) | Firebase (BDT ~8.50) |
|---|---|---|
| 2,000 (closed testing) | BDT 620 (USD 5) | BDT 17,000 (USD 140) |
| 20,000 (100 teachers, 20 students, monthly login) | BDT 6,200 (USD 51) | BDT 170,000 (USD 1,400) |

At the Q9 scale ceiling, Firebase alone would exceed the entire infrastructure
budget [Q3] by roughly 28x. **Decision: local gateway.** [Q5]

The cost structure also inverts a risk: with per-SMS billing on a cheap gateway,
OTP abuse becomes a direct financial attack, which is why
`architecture-proposal.md` §7 includes a global daily SMS ceiling with an alert.

---

## 4. Infrastructure cost analysis

Budget ceiling USD 50/month. [Q3] Scale target 100 teachers, a few thousand
students. [Q9]

| Option | Monthly | Verdict |
|---|---|---|
| Lightsail 2 GB instance, Postgres in Docker, pg_dump to S3 | ~USD 13 | **Phase 1 choice.** Fastest to stand up, fits the timeline |
| Lightsail instance + RDS `db.t4g.micro` | ~USD 12 (year 1, RDS free tier) rising to ~USD 27 | **Phase 2 choice.** Managed backups and point-in-time recovery |
| ECS Fargate + ALB + RDS | ~USD 30–35 | Rejected: the ALB alone is ~USD 16–18/month for load balancing 100 teachers do not need |
| Lambda + API Gateway + RDS Proxy + RDS | ~USD 11 | Rejected: RDS Proxy erases most of the saving, and cold starts fight §11's slow-network goal |
| Lightsail managed DB, entry tier | USD 15 | Rejected: entry standard tier lacks storage encryption [aws-lightsail] — unacceptable for children's data |

Both phases sit comfortably inside the ceiling. Full reasoning in
`architecture-proposal.md` §4.

---

## 5. Risk analysis

| Risk | Likelihood | Impact | Treatment |
|---|---|---|---|
| One-month timeline slips | High | Medium | Narrow the first release rather than extend it: auth, batches, enrollment and attendance is demonstrable; seven half-finished slices is not |
| Android quality gap from unfamiliarity | Medium | High | Conventional choices only (Compose, MVVM, Hilt, Retrofit, Room); no clever patterns; heavier test coverage on the client than usual |
| Money arithmetic defect | Medium | **High** | Mandatory tests on fee-cycle arithmetic, carry-forward, partial approval and waiver [desc §13.6]; money confined to one module; fixed-point decimal with JSON-string transport [Q8] |
| OTP abuse driving SMS cost | Medium | Medium | Per-number and per-IP rate limits plus a global daily ceiling with alerting |
| Homemade auth weakness | Medium | High | Seven named controls in `architecture-proposal.md` §7; security review before the auth slice ships |
| Play rejection on children's-data grounds | Low–medium | High | Declarations settled at intent capture; no device identifiers anywhere; no ads SDK; verified against current policy |
| Attendance unusable on patchy data | Medium | Medium | Accepted risk, user's explicit decision [intent: Q18]; revisit if pilot teachers hit it |
| Six deferred capabilities prove not absorbable | Medium | Medium | Ownership indirection built now for org-owned batches (the hardest one); the rest reassessed at Domain Design rather than claimed |

---

## 6. What makes this feasible that might not have been

Three things in the brief that reduce rather than add risk, worth naming because
they were deliberate choices:

- **Cached-reads-only** instead of offline-first [intent: Q18] removes sync and
  conflict resolution entirely — the single largest piece of engineering this
  product could have required.
- **No payment gateway in V1** [desc §9] removes PCI scope, settlement
  reconciliation and refund flows. The app records claims and verifications
  only.
- **Teacher-created records with no self-registration** [desc §3] removes
  invitation flows, join requests and acceptance states, and makes a mistyped
  number a dormant row rather than an error path.

---

## Assumptions & Open Questions

- Firebase's Bangladesh rate is unpublished; India's USD 0.07 is used as the
  nearest comparator. The conclusion holds at any plausible rate, but the figure
  is an assumption. [assumption]
- The USD/BDT rate is taken as roughly 121. Cost figures move with it.
  [assumption]
- The OTP volume model (one login per student per month) is an estimate, not
  measured behaviour. Real volume depends on session length and token lifetime;
  a 30-day refresh token implies roughly monthly re-authentication.
  [assumption]
- AWS free-tier eligibility depends on account age; the structure changed on
  15 July 2025. If the existing account [Q6] predates eligibility, Phase 2 costs
  about USD 27–30/month instead of USD 12 — still within budget. [assumption]
- Local gateway rates are advertised prices from vendor sites, not negotiated
  quotes, and may carry minimum purchase commitments. Delivery reliability and
  masked-sender support are unverified. [assumption]
- No SMS vendor has been selected. [Q6] [assumption]
- Latency from Dhaka to `ap-southeast-1` versus `ap-south-1` is unmeasured.
  [assumption]

## Sources

- [desc] Initial description, including §9, §10–§12 and §13.6.
- [Q1]–[Q12] Confirmed answers in `feasibility-questions.md`.
- [intent: Q17], [intent: Q18] — confirmed answers carried from
  `ideation/intent-capture/`.
- [sms-bulksmsbd] https://bulksmsbd.com/ — retrieved 2026-10-17.
- [sms-smsbd] https://sms.bd/ — retrieved 2026-10-17.
- [sms-bdbulksms] https://bdbulksms.com/ — retrieved 2026-10-17.
- [sms-mimsms] https://www.mimsms.com/otp-sms-bangladesh and
  https://www.mimsms.com/bulk-sms-price-in-bangladesh-2026 — retrieved
  2026-10-17.
- [sms-onecodesoft] https://onecodesoft.com/blogs/best-otp-sms-service-provider-in-bd-fast-and-affordable
  — retrieved 2026-10-17.
- [sms-swift] https://astgd.com/swift-sms-sender — retrieved 2026-10-17.
- [firebase-pricing] https://firebase.google.com/pricing and
  https://cloud.google.com/identity-platform/pricing — retrieved 2026-10-17.
- [aws-lightsail] https://aws.amazon.com/lightsail/pricing/ — retrieved
  2026-10-17.
- [aws-rds-free] https://aws.amazon.com/rds/free/ — retrieved 2026-10-17.
