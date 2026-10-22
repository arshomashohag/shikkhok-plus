# Requirements — the six remaining deliverable units

**Stage**: requirements-analysis (2.3)
**Phase**: Inception
**Depth**: Standard
**Record**: 261022-remaining-slices

> **This document does not restate the product's requirements.** They are
> written, traced and gated in
> `261016-shikhokplus-tuition-app/inception/requirements-analysis/requirements.md`
> — 102 entries, no gaps — and their `FR{n}.{m}` IDs are permanent
> traceability keys that four built Units already reference. Renumbering them
> would break that chain.
>
> What is here is what changed: the requirements that decisions taken after
> 2026-10-17 have contradicted, the new requirements acceptance introduces, and
> the delivery standard the re-cut adds.

## Sources

- [desc] the authoritative project description for this record — D1–D6
- [upstream] `codekb/shikkhok-plus/` — the scan of the built code, 2026-10-22
- [upstream] `inception/practices-discovery/team-practices.md`
- [prior] the product requirements, 2026-10-17, and the approved re-cut,
  2026-10-22, both in `261016-shikhokplus-tuition-app/`
- [Q1]–[Q6] in `requirements-analysis-questions.md`

---

## Intent analysis

**The goal is not six more features.** Every capability D1–D6 builds was
already specified in 2026-10-17, and four Units of it are merged and working.
The goal is that a person can **use** what was built.

That distinction is the whole reason this record exists. B3 and B5 both shipped
and both met their stated Definition of Done; what reached the phone was two
unstyled forms against nine working endpoints. The capability requirements were
satisfied and the product was unusable. So the re-cut changed the unit boundary
from a backend layer to one user-visible capability — API, screens and tests
together — and the standard from "the endpoints work" to "the thing can be done
on a phone".

Three consequences shape what follows:

1. **The requirements were right and the delivery boundary was wrong.** This
   stage does not re-derive requirements that were never the problem.
2. **One gap was real.** Account creation existed in no requirement and no
   Bolt; a teacher could only exist by hand-inserting a database row. Reading
   the O1 artboard also surfaced that a teacher typing a phone number grants a
   stranger a guardian lens over a child, with no consent and no notification.
3. **Four requirements now say the opposite of what was decided.** Left
   standing, the next reader follows whichever file they opened first.

---

## FR0 — The delivery standard

New, and applying to all six units rather than to any one of them.

| ID | Requirement | Source |
|---|---|---|
| FR0.1 | A deliverable unit is one user-visible capability, delivered as API, screens and tests together. A unit whose endpoints work but whose screens do not exist is **not done**. | [re-cut 2026-10-22] |
| FR0.2 | Each unit's screens are checked before the unit completes, by the per-screen check recorded at `docs/delivery/bangla-layout-check.md`. A screen with no row in that table is an incomplete unit. The check covers both the Bangla layout and, where the plan names one, the design artboard the screen must match. | [TC-15] [D-43] [practices 2026-10-22] [Q6, amended] |

**A separate artboard requirement was drafted and removed.** It said each unit's
named artboards "are verified per screen" and named no artifact, no recorded
result and no actor — the exact shape `project.md` forbids as of 2026-10-22,
where an obligation without a named verifier is a wish. It was also vacuous for
D5, which the plan gives no artboard at all. Rather than ship an unverifiable
requirement, the artboard check folds into the per-screen table that already
exists, already has a failure taxonomy, and already treats a missing row as an
incomplete unit [Q6, amended after review].

The plan's artboards per unit are therefore an input to that table rather than a
requirement of their own: D1 `O1` (five states), `O2`, `O3`; D2 `T6`, `T7`,
`T8`, create-batch, remove-student, `G1`; D3 `T5`, `S2`, `T4`, `S3`, `G3`;
D4 `T1`, `T2`, `T3`, marksheet; D5 none; D6 the deletion confirmation copy.

---

## FR1a — Identity: account creation and seat acceptance

### Superseded requirements

Both supersessions are recorded rather than applied by edit: the prior record is
a gated artifact, and overwriting it would destroy the evidence of what changed
[Q1].

| ID | Supersedes | Why |
|---|---|---|
| **FR1.7a** | **FR1.7** — "Only a teacher creates a student record. There is no self-registration, no join request and no invite acceptance." | D1 adds account creation and seat acceptance. Every clause of FR1.7 is now false. It was a correct description of the 2026-10-17 design; the design changed on 2026-10-22. |
| **FR1.9a** | **FR1.9** — "A mistyped number produces a permanently dormant record. This is correct behaviour, not an error state, and the system never attempts recovery." | FR1.9 treated the mistyped number as harmless. It is not: under the lens model a mistyped number silently grants a stranger a guardian lens over a child's records. That is the exposure acceptance exists to close. |
| **FR11.1a** | **FR11.1** — a student's or guardian's account deletion leaves the teacher's records intact and "**the enrollment reverts to dormant**". | Found at review, and a behavioural bug rather than a wording nit. Under the new state machine, reverting to dormant silently erases a decline: a person who declined and then deleted their account is re-prompted the next time the teacher re-adds them, which is exactly what [FR1.9c] promises cannot happen. Deletion must not be a way to clear a decline. |

### Requirements

| ID | Requirement | Source |
|---|---|---|
| FR1.7a | A person may create their own account, choosing teacher, student or guardian, and supplying name, mobile number and address. The choice decides **what is created**, not what is stored: picking Teacher creates an `Owner` row, picking Student or Guardian creates none. No role is recorded on the account [BR1.1]. | [desc] [re-cut] |
| FR1.7b | Nothing verifies a self-declared role. A person who signs up as a teacher is a teacher, and the system does not monitor the claim. | [human, 2026-10-22] |
| FR1.7c | Signup happens **before** OTP verification, not after: the form is submitted, the account is created, then the code is sent. | [O1 artboard] |
| FR1.7d | Signup carries its own per-number and per-IP rate ceilings, separate from the OTP ceilings. Its response is deliberately informative — it tells an existing number to log in instead — so it is an existence oracle by construction and needs its own abuse control. | [O1 state 5] [D-33] |
| FR1.7e | `POST /v1/auth/otp` remains byte-identical for known and unknown numbers. Signup's informative response does not weaken it; the existing adversarial test re-runs to prove it. | [BR2.7] |
| FR1.7f | The lookup that renders the already-added case confirms only that the number has been added, and returns what the form needs to pre-fill the name and lock the role. It names **neither the teacher nor the batch**. | [Q9, 2026-10-22] |
| FR1.9a | A seat a teacher creates grants **no student or guardian lens** until the person named accepts it. A mistyped number therefore exposes nothing. | [Q10, 2026-10-22] |
| FR1.9b | Acceptance is recorded per **link**, not per row: a seat carries a separate acceptance marker for its student link and its guardian link, because the two are independent facts about one seat. This mirrors the two erasure markers already on the enrollment [BR6.2]. | [Q10] [BR6.2] |
| FR1.9c | Declining is durable **against the teacher**: re-adding the same number does not re-prompt a person who declined. | [Q10] |
| FR1.9c.1 | Declining is **reversible by the person who declined it**. A declined seat stays visible to them with an accept action, and accepting it works exactly as accepting a pending seat would. | [review R-C3] |
| FR1.9c.2 | The teacher has no action that clears or reverses a decline. The durability in [FR1.9c] exists to protect the declining person from a teacher who keeps re-adding them, so the remedy belongs to the person and not to the teacher. | [review R-C3] |
| FR1.9d | A pending person sees the invitation plus **what they would be accepting**: batch name, subject and fee amount, read-only. They do not see attendance, marks, other enrollments, or any write action. | [Q2] |
| FR1.9d.1 | Every value in [FR1.9d] is teacher-authored, so the pending view crosses no student or guardian privacy boundary and needs no new table. What it does need is a **lens**: every read path is lens-parameterised and the route-enumeration gate rejects an unlensed route, while a pending person by construction holds no lens for that seat. The pending read resolves a distinct **invitation lens**, scoped to one enrollment and carrying read access to exactly those three fields. It is not a special case inside the existing resolver, because a special case inside the thing that decides authorization is where an authorization defect hides. | [review R-M1] [TC-11] [BR1.4] |
| FR11.1a | A student's or guardian's account deletion leaves the teacher's records intact, as [FR11.1] says, **but the seat does not revert to dormant if it was declined**. A declined seat stays declined through the account's deletion and recreation. Deletion is not a path to clear a decline. | [review R-C1] [FR1.9c] |
| FR1.9e | A seat that is never accepted stays pending indefinitely. There is no expiry and no automatic deactivation. | [Q3] |
| FR1.9f | Fee cycles generate against a **pending** seat from its creation. The teacher's side never blocks on acceptance, and the debt is real whether or not anyone has opened the app. | [Q3] [FR5] |
| FR1.9f.1 | A **decline stops generation**: no further fee cycle is generated against a declined seat. | [review R-C2] |
| FR1.9f.2 | A decline **voids the cycles already accrued** against that seat. Nobody incurred them: the person being billed is the person who has just said this enrollment is not theirs, and the commonest cause of a declined seat is a mistyped number. Voiding is recorded in the ledger as a reversal with its reason, never by deleting rows — the ledger stays append-only [ADR-002]. | [review R-C2] |
| FR1.9f.3 | An un-decline under [FR1.9c.1] does **not** resurrect the voided cycles. Generation resumes from the acceptance date. A person who declined in error and corrects it owes from when they joined, not from when a teacher typed their number. | [review R-C2] |
| FR1.9g | On acceptance, the person sees the full history of their seat from creation, including dues accrued before they accepted. The teacher's roster and the student's own view never show different totals for one seat. | [Q13, 2026-10-22] |
| FR1.9h | The roster shows **pending** and **declined** as distinct states, alongside the existing dormant, active and inactive. No notification is sent on either. | [Q4] [Q14] |
| FR1.9i | Removal remains as [FR2.12]: a seat may be removed only while unclaimed. Once accepted, the teacher marks the enrollment inactive and the record stands [ADR-003]. Acceptance introduces no new removal rule. | [Q15] [FR2.12] [ADR-003] |
| FR1.4a | Amends **FR1.4** rather than superseding it: at login only the lenses that have data are offered, **and a lens is offered only once its seat is accepted**. Implemented as `GET /v1/me`, which returns every available lens with a count. A single-lens account skips the picker. | [FR1.4] [re-cut] |
| FR1.8a | Amends **FR1.8**: a seat is dormant → pending → accepted (or declined). Authenticating is no longer sufficient to grant a lens; acceptance is. | [FR1.8] [Q10] |
| FR1.16 | One account may hold both the student and guardian links on a single seat — an adult student with no guardian, or a teacher enrolling their own child. No special case is written for it. | [Q12] |
| FR1.17 | Two new personal-data columns are stored: an address and a display name. Each carries a disposition per deleting actor and a retention class before it is stored. | [O1] [RC-5] |

---

## NFR additions

The product's NFRs stand. These are additions arising from this record's
decisions.

| ID | Requirement | Source |
|---|---|---|
| NFR20 | Lens resolution returns every available lens in one statement. Measured before adoption at 50,000 accounts and 200,000 enrollments — 500× the target — at 0.20 ms with index-only scans. The property required is that cost tracks the data belonging to the requesting account, never the total data in the system. | [measured 2026-10-22] |
| NFR21 | No cached summary table and no denormalised counts. They cost more to maintain than the indexes cost to read, and reintroduce the staleness [BR1.1] exists to prevent. | [2026-10-22] |
| NFR22 | No eager per-lens data at login. The summary carries counts; a lens's rows arrive when that lens is chosen. | [2026-10-22] |
| NFR23 | Acceptance state transitions are tested test-first, because a wrong answer grants or withholds a lens and is therefore an authorization error under the affirmed testing predicate. | [team: Testing Posture, 2026-10-22] |

---

## Constraints

Unchanged from the product requirements, with three preconditions now
**satisfied** rather than outstanding.

### Satisfied preconditions

Completed 2026-10-22, ahead of D1, with all gates passing. Recorded here as
context rather than as requirements of this work: a completed control stated as
a future requirement would misdescribe the state [Q5].

| Precondition | Delivered |
|---|---|
| Dependency lockfiles on both surfaces | `requirements.txt` with 1,865 hashes, installed under `--require-hashes`; Gradle dependency locking (352 deps) and checksum verification (523 components). |
| CVE scanning, per-push half | pip-audit annotating per push; Dependabot weekly and grouped; `.security-exceptions.md` present. First audit: no known vulnerabilities. |
| Android quality toolchain | detekt, Android Lint with `HardwareIds` fatal, Kotlin coverage ratchet live at 30.95% with no decrease permitted. |

**ktlint does not run over Kotlin source**, by decision: it cannot parse the
`[AC1.1.6]` traceability tags inside KDoc, which appear 52 times across 21 of
32 files. detekt, Lint and the release DEX scan carry the Kotlin checks.

### Standing constraints

Every `NEVER` and `ALWAYS` in `project.md` applies unchanged — money never
float, no device or advertising identifier, no role column, the privacy
boundary enforced in three layers, both deletion paths release-blocking, the
USD 50/month ceiling. This document adds none and relaxes none.

---

## Assumptions

| ID | Assumption | Reason it needs no requirement |
|---|---|---|
| A10 | A teacher's display name is all signup needs. A subscription plan, an institution name and a photo are all plausible and none is required to reach a batch list. | Additive later under the `/v1/` policy. |
| A11 | Acceptance needs no expiry. | Inventing a window now would guess at a problem nobody has reported; [FR1.9e] records the indefinite behaviour explicitly rather than leaving it unstated. |
| A12 | A declined seat needs no notification to the teacher. | The roster state [FR1.9h] is where the teacher already looks, and a decline is not urgent. |
| A13 | The platform subscription is gone and nothing replaces it: the app charges nobody. The fee system is untouched — teachers collect tuition from their own students. | Confirmed explicitly on 2026-10-23 after an ambiguous phrasing; the distinction is recorded because mis-reading it would delete a quarter of the product. |

---

## Out of scope

- **Re-deriving the product's capability requirements.** They are complete and
  gated; this record amends four and adds to them.
- **Expiry or automatic deactivation of a pending seat** [Q3].
- **Notifying a teacher of a decline** [Q4].
- **Verifying a self-declared role** [FR1.7b].
- **Naming the teacher or batch in the already-added lookup**, which the O1
  artboard shows and this record declines [FR1.7f].
- Everything the product requirements already exclude: offline writes, payment
  gateway integration, PDF export, private messaging, multi-device session
  management, the admin surface, coaching centres, the tutor marketplace, batch
  messaging and the PWA.

---

## Open questions

| Question | Owner | Note |
|---|---|---|
| Where the Macrobenchmark harness is built | D4's start, or D5 as planned | D4's mid-class latency obligation is dischargeable only by a harness D5 carries. The one genuine sequencing defect in the plan; three options recorded in `risk-and-sequencing-rationale.md`. |
| The Play Console account type | The human | If it is the post-2023 personal type and twelve testers cannot be found, the fallback is a longer organisation verification path. Now the most schedule-dangerous open item, because the mitigation of starting the Play clock early did not happen. |
| OQ-1 — does `PaymentClaim.transaction_id` survive the claimant's deletion? | The human | Must close before D6; ideally before D3, so the payment-history schema is not revisited. |
| OQ-5 — the external deletion route's web surface | The human | Release-blocking at D6; confirmable in minutes against Play's current requirements. |
| OQ-2 — FR8.3's collection-rate definition | The human | D5 ships without the `collection_rate` field rather than with provisional arithmetic. |
| Is "Require branches to be up to date before merging" enabled? | The human | A thirty-second settings check. If off, the green-`main` obligation has no verifier. |

---

## Assumptions & Open Questions

None beyond those tabled above.

---

## What the review changed

An advisory review ran on the first draft and returned eight findings. The
three Critical ones were real gaps in the draft rather than reviewer noise, and
each was verified against the prior record or this one before being acted on.
All are now closed, by the human's decision at each:

| Finding | What the draft got wrong | Closed by |
|---|---|---|
| A mis-tapped decline was permanent and unfixable | Decline was written as durable with no way back. Durability protects a stranger from a persistent teacher; it should never have barred a real student from their own records. | [FR1.9c.1], [FR1.9c.2] — reversible by the person who declined, never by the teacher |
| A declined seat accrued debt forever | [FR1.9e] made pending indefinite and [FR1.9f] accrued from creation, and nothing said what decline did to the ledger. The mistyped-digit failure, relocated from the lens to the money. | [FR1.9f.1]–[FR1.9f.3] — decline stops generation and voids what accrued, as an append-only reversal |
| A fifth contradiction, unfound | Prior [FR11.1] reverts an enrollment to dormant on account deletion, which silently erases a decline. Verified in the prior record. | [FR11.1a] |
| [FR0.2] was a wish by the project's own rule | "Verified per screen" named no artifact, no recorded result and no actor, and was vacuous for D5, which has no artboard. | Removed; the artboard check folds into the per-screen table that already has a verifier |
| [FR1.9d] needed a lens it did not name | The data crosses no privacy boundary, but every read path is lens-parameterised and a pending person holds none. | [FR1.9d.1] — a distinct invitation lens rather than a special case in the resolver |

What the review did **not** fault is worth recording too, because it was the
part most at risk of being wrong: the scope boundary. Not restating 102 traced
requirements, declining to log completed toolchain work as future requirements,
and re-confirming the no-subscription reading were each tested and held.
