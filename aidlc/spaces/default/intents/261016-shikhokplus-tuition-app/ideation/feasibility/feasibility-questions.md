# Feasibility & Constraints — Clarifying Questions

**Stage**: feasibility (1.3)
**Phase**: Ideation
**Depth**: Comprehensive

## Sources

- [desc] Initial description: the authoritative project description recorded at workflow creation.
- [scope] Workflow-selected scope: `classic`.
- [upstream] `ideation/intent-capture/intent-statement.md` — approved intent statement, including the ten architecture-constraining decisions.

---

## Q1. Who builds this, and what is the skill profile?

Feasibility depends more on who is building than on what is being built. A
stack that is objectively excellent and unfamiliar to the team ships later than
a merely good familiar one. I also need to know whether "native Android" means
you write Kotlin yourself or are directing me to.

- A. You alone, and you write the code with me
- B. You alone, and I write most of it while you review
- C. You plus one or more other developers (specify how many and their strengths)
- D. You plus contractors or an agency
- X. Other (please specify)

[Answer]: B

---

## Q2. What is your actual experience with the Android and backend sides?

This decides how much of my stack recommendation should optimise for
familiarity versus fit. Be blunt; an honest answer here saves weeks.

(Select all that apply.)

- A. Strong Kotlin / Android — Compose, coroutines, Room all familiar
- B. Some Android, rusty or older-style (Java, XML layouts, no Compose)
- C. Strong backend in a specific language — specify which (Python, Node/TS, Go, Java/Kotlin, PHP, other)
- D. Strong with relational databases and SQL
- E. Comfortable with cloud infrastructure and deployment (specify which cloud)
- X. Other (please specify)

[Answer]: C - Python, Node/TS, D. E - I know many things in AWS

---

## Q3. What is the infrastructure budget per month for V1 and closed testing?

This is the single biggest constraint on the backend recommendation. Managed
services cost money and save time; self-hosting on a cheap VPS costs time and
saves money. Note that OTP SMS is a separate running cost on top of this — see
Q5.

- A. Effectively zero — free tiers only, I will not pay for infrastructure during closed testing
- B. Under USD 25/month
- C. USD 25–100/month
- D. USD 100–500/month
- E. Not a constraint — optimise for correctness and speed of delivery
- X. Other (please specify)

[Answer]: C - under 50

---

## Q4. What is the timeline, and is there a fixed external date?

Feasibility assessment needs to know whether we are optimising for earliest
usable release or for architectural completeness.

- A. No fixed date — correctness over speed
- B. Closed testing with pilot teachers within about 1 month
- C. Closed testing within about 3 months
- D. Tied to the academic calendar — a specific term or year start (specify the date)
- X. Other (please specify)

[Answer]: B - You will build, so should be quick

---

## Q5. OTP provider: local SMS gateway or Firebase Phone Auth?

Your §12e asked for the provider decision with SMS costs at Bangladesh volumes.
I researched current rates rather than relying on training data.

**Local BTRC-approved gateways**: BDT 0.25–0.40 per SMS. BulkSMSBD from BDT
0.25, SMS.BD at BDT 0.31, BD Bulk SMS from BDT 0.30, MiMSMS BDT 0.35–0.40
tiered, OnecodeSoft and Swift SMS Sender at BDT 0.35. All provide REST APIs and
delivery reports.

**Firebase Phone Auth**: first 10 SMS/day free, then billed per SMS by
destination country. Google publishes India at USD 0.07; South Asia bands
together, and no Bangladesh-specific rate is published. Requires the Blaze plan;
phone auth is unavailable on the free Spark plan.

**The arithmetic.** At roughly BDT 121/USD, USD 0.07 is about BDT 8.50 — some
25–30x the local rate. At a modest 20,000 OTPs/month (1,000 teachers, 20
students each, one login per month):

| Provider | Monthly cost |
|---|---|
| Local gateway at BDT 0.31 | about BDT 6,200 (USD 51) |
| Firebase at India-adjacent rate | about BDT 170,000 (USD 1,400) |

**My recommendation: a local gateway**, behind our own OTP issue and verify
endpoints. Two reasons beyond cost. It keeps auth logic server-side, which your
§12a requires anyway so a future PWA consumes the same API. And Firebase's
Android SDK uses Play Integrity and device signals, which needs checking against
the mixed-audience-including-children declaration that bars device identifiers.

**The strongest argument against me**: Firebase gives you rate limiting, replay
protection, OTP expiry, abuse detection and reCAPTCHA for free. Rolling our own
means building all of that, and auth is where homemade code hurts most. That is
a genuine risk, not a formality.

- A. Local gateway, build our own OTP endpoints — accept the security work (my recommendation)
- B. Firebase Phone Auth — accept the cost, inherit the hardening
- C. Local gateway for production, Firebase during closed testing to move fast, migrate later
- D. Pick a specific local provider now — name which one, if you already have a relationship or preference
- X. Other (please specify)

[Answer]: A

---

## Q6. Do you already have accounts, infrastructure or vendor relationships?

Existing accounts and credits change the recommendation materially, and an
existing SMS vendor relationship can settle Q5 by itself.

(Select all that apply.)

- A. None — starting from nothing
- B. An AWS account (note any credits)
- C. A Google Cloud or Firebase account (note any credits)
- D. A VPS or hosting provider already paid for (specify)
- E. A relationship with a Bangladeshi SMS gateway (specify which)
- X. Other (please specify)

[Answer]: B

---

## Q7. Where must the data live?

Bangladesh has no general data-residency statute comparable to GDPR, but the
app holds children's names, attendance and marks, and the Play Families
declaration brings COPPA and GDPR-K into play regardless of where servers sit.
Latency from Dhaka also differs substantially between regions.

- A. No residency constraint — choose the nearest region for latency (likely Singapore or Mumbai)
- B. Prefer in-country hosting if a credible provider exists
- C. Must be in-country — a stated requirement
- D. Not yet decided — flag as an open constraint
- X. Other (please specify)

[Answer]: A

---

## Q8. How should the fee ledger handle money, and in what currency only?

Your fee model is now an anchor plus a ledger of what was charged, received,
carried forward or forgiven. Money bugs come from representation as much as from
logic, and this is a decision that is painful to change once data exists.

- A. Integer minor units (poisha) in BDT only, no floating point anywhere
- B. Fixed-point decimal in BDT only
- C. Integer minor units, with a currency field for future non-BDT use
- D. Whole taka only — fractional amounts cannot occur in practice
- X. Other (please specify)

[Answer]: B. Fixed-point decimal in BDT only. Confirmed after I argued for integer
minor units; the user kept their choice. Mitigation agreed: `NUMERIC(12,2)` in
Postgres, `BigDecimal` in Kotlin (never `Double` or `Float` anywhere), and
serialized as a JSON **string** rather than a number so no decimal crosses the
API as an IEEE double. Rounding mode stated once, centrally, and money
arithmetic confined to one module.

---

## Q9. What is the realistic upper bound on scale for V1?

This sizes the database and hosting decisions. Under-sizing wastes a migration;
over-sizing wastes money now. I would rather design for a known ceiling than an
imagined one.

- A. Closed testing only — under 20 teachers, a few hundred students
- B. Small launch — up to 100 teachers, a few thousand students
- C. Up to 1,000 teachers, around 20,000 students
- D. Design for 10,000+ teachers from the start
- X. Other (please specify)

[Answer]: B

---

## Q10. Are there organisational or personal blockers I should plan around?

Feasibility includes the things that stall projects for non-technical reasons.

- A. None
- B. This is evenings-and-weekends work alongside a job — expect irregular availability
- C. A hard constraint on when I can work or review (specify)
- D. Dependency on someone else's availability (specify)
- X. Other (please specify)

[Answer]: A

---

## Q11. Do you want one consolidated architecture proposal, or staged decisions?

Your §13 asked for architecture and stack proposal before any code, with
approval. This workflow would otherwise deliver that in pieces — constraints
here, then domain design, then the API contract — each separately approved.
Both work; they suit different review styles.

- A. Staged, as the workflow does it — smaller decisions, each separately approvable, less to review at once
- B. One consolidated architecture document covering stack, database, API style, Android architecture and auth, approved as a whole before design stages proceed
- C. Staged, but with a short written stack recommendation up front so the big choices are settled early
- X. Other (please specify)

[Answer]: B. One consolidated architecture document, approved as a whole.
Placement confirmed in follow-up: written now as an output of this feasibility
stage, covering stack, database, API style, Android architecture and auth, with
each of §12a–f answered explicitly. Approved at this stage's gate. The later
design stages (Domain Design, Contract Design, Infrastructure Design) then
elaborate within that approved architecture rather than re-deciding it.

---

## Q12. How much pushback do you want on the data model in §10?

You asked me to flag anything I would change, and I have already flagged the
fee model, which you accepted. There are other things I would change. I want to
know whether to raise them as they arise or hold them for domain design.

- A. Raise every concern as it arises, even small ones
- B. Raise structural concerns only; let conventions and naming go
- C. Hold them all for domain design and present them together
- D. Implement §10 as written unless something is actually broken
- X. Other (please specify)

[Answer]: B

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Build team: the user alone, with the agent writing most of the code and the
  user reviewing.
- Skills: strong Python and Node/TS backend, strong relational databases and
  SQL, broad AWS knowledge. No Kotlin or Android strength declared — treated as
  a real constraint on the client-side choices.
- Infrastructure budget: under USD 50 per month.
- Timeline: closed testing with pilot teachers in about 1 month.
- OTP provider: a local BTRC-approved SMS gateway, with our own OTP issue and
  verify endpoints; the rate limiting, replay protection and abuse controls are
  ours to build.
- Existing accounts: an AWS account. No SMS vendor relationship yet.
- Data residency: no constraint; nearest region for latency (Singapore or
  Mumbai).
- Money representation: fixed-point decimal, BDT only. `NUMERIC(12,2)` in
  Postgres, `BigDecimal` in Kotlin, never float or double, serialized as a JSON
  string so no decimal crosses the API as an IEEE double. Rounding mode stated
  centrally; money arithmetic confined to one module.
- Scale ceiling for V1: up to 100 teachers and a few thousand students.
- Organisational blockers: none.
- Architecture delivery: one consolidated architecture document, written now as
  an output of this stage, covering stack, database, API style, Android
  architecture and auth, with §12a–f each answered explicitly. Approved as a
  whole at this stage's gate; later design stages elaborate within it.
- Pushback level: structural concerns raised as they arise; conventions and
  naming left alone.
- Recorded risks: the 1-month closed-testing timeline is the dominant schedule
  risk given a greenfield two-surface build across seven vertical slices plus
  Play closed-testing setup and review lead times; and the absence of declared
  Android experience makes the client side the thinnest review surface, which
  argues for conventional Android choices over clever ones.

[Answer]: Looks correct

---
