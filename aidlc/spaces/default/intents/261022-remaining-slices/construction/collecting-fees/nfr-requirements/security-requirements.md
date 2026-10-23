# Security Requirements — D3 `collecting-fees`

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: D3 `collecting-fees`
**Record**: 261022-remaining-slices

> **D3 introduces a privacy direction this product has never had.** Every
> control built so far protects student and guardian data *from* teachers.
> BR6.4 runs the other way: the teacher's payment-collection number flows
> **downward** to students and guardians. The built mechanisms do not cover
> that direction, and this file says so and names what must.
>
> D3 also adds **four tables**, all enrollment-scoped rather than
> profile-scoped, and the one place in the product where a wrong answer is a
> money error rather than a disclosure.

> **`NFRx.y` IDs are GLOBAL across units.** D3's start above the high-water
> mark each base had reached after D2: NFR14 from **.32**, NFR10 from **.15**,
> NFR23 from **.7**, NFR13 from **.5**, NFR11 from **.2**, and **NFR9 from
> `.34`**.
>
> **NFR9 is the one that nearly went wrong.** The high-water marks supplied to
> this stage covered eighteen bases and NFR9 was not among them; the money
> axis runs to **`.33`** in the prior record's `identity-and-access`
> artifacts, where NFR9.1 is "no secret in the repository or the image". A
> first draft of this file minted NFR9.1–9.5 and collided with five of them.
> Recomputed per base rather than taken, which is the only way this is
> findable — no sensor checks cross-unit collisions.
>
> D3 defines **no NFR12.x**: the abuse-control axis is D1's, and D3 adds no
> unauthenticated route. A bare `NFR14.15` or `NFR14.27` is a **citation** of
> a prior requirement, not an ID defined here.

## Sources

- [upstream] `construction/collecting-fees/functional-design/rules.md` — BR3.3,
  BR3.4, BR4.1, BR5.5, BR5.7, BR6.1, BR6.2, BR6.4, BR6.5
- [upstream] `construction/collecting-fees/functional-design/functional-spec.md`
  §§ 4.2, 5, 7, 8
- [upstream] `construction/collecting-fees/functional-design/entities.md` —
  `FeeCycle`, `LedgerEntry`, `PaymentClaim`, `ReminderEvent`
- [upstream] `inception/requirements-analysis/requirements.md` — NFR20–NFR23
- [prior] NFR9, NFR10, NFR11, NFR13, NFR14 of
  `261016-shikhokplus-tuition-app`; `inception/contract-design/contract-summary.md`
  § G (OQ-1, OQ-4)
- [code] `app/contract/privacy.py`, `app/authz/rls.py`,
  `migrations/versions/0001_initial_identity_schema.py`,
  `app/governance/dispositions.py`, read 2026-10-23

---

## 1. The new direction: a teacher-authored field flowing down

BR6.4 bounds the collection number well — visible only to a holder of a
student or guardian lens on an enrollment **in that batch**, absent from every
listing and search. What needs saying is that **the built invariant is silent
on it.**

`tests/privacy/` iterates the generated OpenAPI schema asserting that no
teacher-lens response carries a member of `OWNER_PRIVATE_FIELDS`
(`app/contract/privacy.py:71` — `self_name`, `photo_ref`, `address`). That is
a one-directional check. A teacher-authored field leaking into an over-broad
*student* response is its mirror image, and the test does not look that way.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.32 | The collection number is **mechanically bounded, not review-bounded** | A test asserting the field appears in **exactly one** response schema, and that the endpoint serving it resolves a student or guardian lens scoped to an enrollment in that batch | [BR6.4] [team: Way of Working] |
| NFR14.33 | The number appears in **no listing and no search response** | Batch listings, roster responses and fee-cycle collections carry it nowhere; it is fetched by the destination step alone | [BR6.4] [FR6.13] |
| NFR14.34 | Where the number is unset, the step is **omitted** rather than rendered empty | An empty field invites a client-side placeholder; the spec requires the person be told to ask the teacher [FR6.12] | [spec § 5.1] |
| NFR14.35 | The channel set is **server-supplied**, never a hardcoded client list | An installed Android app cannot be forced to update, so a client list is a permanent decision made by whoever shipped it | [BR6.5] |

**NFR14.32 exists because of the project rule that where a rule is important,
it is mechanical.** BR6.4 states a `violation_behaviour` that is assertable;
leaving it to review would make the one new disclosure direction in the
product the only one with no mechanism behind it.

---

## 2. Row-level security on D3's four tables — decided, with the reason

**The existing policy does not cover them, and claiming otherwise would be
false.** Row-level security in this product exists on **`profile` alone**:
migration `0001_initial_identity_schema.py:261-266` runs `ENABLE` and then
`FORCE ROW LEVEL SECURITY`, and the `FORCE` is deliberate — without it the
policy does not apply to the table owner and looks present in `pg_policies`
while doing nothing for the connection most likely to be used by mistake.

`FeeCycle`, `LedgerEntry`, `PaymentClaim` and `ReminderEvent` are
**enrollment-scoped**, not account-scoped. The decision:

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.36 | D3's four tables are protected by **lens-scoped queries plus adversarial probes**, not by their own RLS policies | Stated as a decision with its reasoning below, so the next reader does not have to guess | [BR6.1] [entities] |
| NFR14.37 | The decision is **revisited if any D3 table gains an account-scoped column** that identifies a reader directly | `profile` has RLS because `account_id` *is* the subject; these tables reach a reader through a join | [code: `0001:261-266`] |

**Why lens-scoping rather than a policy.** `profile`'s policy is expressible
because the row carries the account it belongs to: `account_id = current_setting(...)`
is a predicate on a column of the row. A fee cycle has no such column. Its
authorization is a *path* — this account holds a student link on this
enrollment, or a guardian link on it, or owns the batch the enrollment is in —
and encoding a three-branch join into a `USING` clause duplicates
`app/authz/resolve.py` in SQL, outside its branch-coverage measurement and
outside the strict mypy island. Two implementations of one authorization rule
is the failure mode, not the protection.

**What makes that safe is that the probes are not optional.** The adversarial
suite is the mechanism here, which is why NFR14.38–NFR14.40 below are
requirements and not suggestions.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.38 | **Teacher A requesting teacher B's batch fees** is refused | IDOR probe, per the affirmed adversarial posture | [spec § 7] [team: Testing Posture] |
| NFR14.39 | **A guardian requesting a non-child's enrollment** is refused | Guardians reach children through their own link only, never by finding the child first | [NFR14.29] [BR4.1] |
| NFR14.40 | **A student requesting a fee cycle not their own** is refused | Named explicitly in the team practice and **lands here for the first time**, because fee cycles did not exist before | [team: Testing Posture] |

**NFR14.40 is the one the practice has been waiting for.** The probe set was
written naming three shapes; two were exercisable at D1 and the third was not,
because the table it probes is created by this unit.

---

## 3. The test role — the standing rule, restated because D3 is where it bites

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.41 | D3's privacy suite connects as the **restricted non-superuser role** `shikkhok_app`, with the existing meta-test asserting `current_user` is not a superuser **before** it runs | A superuser bypasses row-level security entirely, so a privacy suite run as `postgres` passes against a policy that is broken, or absent | [project: NEVER-rule] [pg-rls] |

**This binds even though D3 adds no RLS policy** [NFR14.36]. The meta-test
guards the *suite*, not a particular table: if a future reader adds a policy
to `LedgerEntry` and the suite is running as owner, it certifies nothing. The
built guard is a collection reorder plus an autouse re-check and D3's new
tests fall under it with no new mechanism.

---

## 4. Money as a security property

A wrong number here is not a disclosure; it is a person charged money they do
not owe, or a payment that vanishes.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR9.34 | Money crosses the API as a **JSON string**, asserted on both sides | The Kotlin serializer reads only a string and **fails loudly** on a JSON number; a lenient decoder that quietly converts is the actual failure mode | [BR6.2] [TC-7] [D-20] |
| NFR9.35 | `NUMERIC(12,2)` in storage; no float anywhere in the stack, in any language, in storage, in transit or in memory | The import boundary is already enforced two ways — Ruff banned-api on raw `decimal` outside `app/money/**`, and a pytest AST walk | [project: NEVER-rule] |
| NFR9.36 | Ledger amounts are **non-negative**, refused at the value type and constrained in the table | The sign lives in the kind. A negative amount inverts a term of the identity silently, and a row inserted by a migration or a repair script never passes through the value type | [BR3.4] |
| NFR9.37 | The ledger is **append-only**: no `UPDATE` and no `DELETE` on `amount`, `kind`, `period` or `enrollment_id` | Only `superseded_by_id` is ever written after insert. A correction appends a compensating entry [BR3.3] | [entities: `LedgerEntry`] |
| NFR9.38 | A carry is written as a **pair in one transaction** | `sum(carry_forward) == sum(carried_out)` holds structurally rather than by convention, which is what makes the one-sided 3000 case unreachable | [BR3.1] [spec § 2.3] |

**NFR9.36 and NFR9.37 are stated as table constraints, not as value-type
behaviour.** The value type already refuses both. What the table constraint
adds is protection against the writer that does not go through it — and on a
single-host deployment with manual production access, a repair script is a
realistic writer.

---

## 5. Verification is an authorization decision

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.42 | A claim is verifiable **only** by a teacher owning the batch the claim's enrollment sits in | `AuthorizationError`, non-retryable. The lens is a dependency whose return annotation is a `Lens` subtype, so the route-enumeration test covers D3's new routes with no new mechanism | [spec § 8] [TC-11] |
| NFR14.43 | Every verification records **who and when**, and the decision and its ledger entries commit in **one transaction** | A verification whose entries did not commit is a teacher believing they approved a payment that was never received | [BR5.5] [FR6.7] |
| NFR14.44 | A correction **retains the prior decision** with its actor and timestamp, and is visible to the teacher **and** to that student and guardian | Never hidden from either party. An amendable money record visible to only one side is the shape a dispute cannot be settled from | [BR5.7] [FR9.2] |
| NFR14.45 | Concurrent re-verification of a decided claim is a `ConflictError`, not a second decision | Correction is a distinct path with its own audit trail | [spec § 8] [BR5.7] |

---

## 6. The decline asymmetry, as a disclosure rule

A declined **student** link stops generation and reverses the accrued balance
[BR1.6]. A declined **guardian** link changes nothing about the money
[BR1.7] — only that guardian's lens is withdrawn.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR14.46 | A declined guardian link withdraws the guardian's **read access** and leaves the student's obligation intact | Two different outcomes behind one word, and the product has already shipped one defect from conflating them | [BR1.7] [AC1.14.1a] |
| NFR14.47 | Every surface rendering a decline is checked against **both** roles before the unit is complete | A role-dependent rule is checked against every screen it reaches, not only the screen it was written for | [team: Corrections 2026-10-22] |

**NFR14.47 is a correction this project has already paid for once.** A decline
confirmation reading "the fee stops" was shown to guardians as well as
students, telling a guardian a debt was cancelled when it was not. D3 is where
that sentence becomes true or false in the ledger rather than only on a screen.

---

## 7. Governance rows for four new tables

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR10.15 | Each of the **four new tables** carries a disposition and a retention class in `app/governance/dispositions.py` before the unit is complete | The schema-iterating test fails on a live table with no governance row, so this is mechanical already | [code: `dispositions.py`] [spec § 12] |
| NFR10.16 | Children's fee data is encrypted at rest, as every other table is | Storage encryption is a hosting property, not a per-table one; D3 adds no tier that lacks it | [RC-8] [D-29] |

**The dispositions are genuinely D3's to choose and are not chosen here**,
because the disposition is a domain decision and this stage records the
obligation rather than the answer. What is worth flagging is that
`LedgerEntry` is the first table where `HARD_DELETE` and `RETAIN_WITH_BASIS`
pull hard in opposite directions: it is a child's financial record **and** a
teacher's business record, and OQ-1 is the open form of exactly that tension
for one of its columns.

---

## 8. OQ-1, stated accurately

**OQ-1 is genuinely open.** It is at
`261016-shikhokplus-tuition-app/inception/contract-design/contract-summary.md`
§ G: *does `PaymentClaim.transaction_id` survive the claimant's deletion?* It
is student- or guardian-authored (so FR11.1 says remove) and simultaneously
the teacher's only evidence of a verified payment (so the business-record
argument says retain). The question is assigned to U11 — **D6** — and is a
product and legal judgement the contract can express either way.

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR10.17 | `PaymentClaim.transaction_id` ships **nullable**, which is answer-agnostic | If the answer is "remove", D6 nulls it in place rather than migrating a column that cannot hold the absence | [spec: Assumptions] [OQ-1] |

---

## 9. What D3 does not change

| Control | State |
|---|---|
| Signup and OTP ceilings | D1's, untouched |
| Row-level security on `profile` | Unchanged; D3 adds no policy and says why [NFR14.36] |
| The owner-private field set | Unchanged; D3 adds no `Profile` column |
| The auth audit vocabulary | Unchanged; D3 adds no authentication event |
| Unauthenticated surface | **None added** |
| Device identifiers | None; D3's FCM adapter uses app-instance-scoped installation ids only [NFR11.2] |

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR11.2 | The FCM adapter transmits **no device or advertising identifier** | App-instance-scoped installation ids only. D3 owns the adapter and **D4 consumes the same one**, so this property is established once | [TC-3] [D-42] [OQ-4] |
| NFR13.5 | D3 adds no token, no session and no credential of its own | Its routes authenticate through the built session; no new secret enters the repository or the image | [project: NEVER-rule] |

---

## 10. Verification obligations

| ID | Requirement | Target | Source |
|---|---|---|---|
| NFR23.7 | **Nearly every rule in this unit is test-first**, under the affirmed predicate | The correct output is knowable from the requirement without the code, and a wrong answer is a money error or an authorization error. That is unusual for a unit and is the point of this one | [team: Testing Posture] |
| NFR23.8 | The money module stays at **100% branch coverage** with `fail_under = 100`, and the floor is never weakened to make a step pass | Measured at 100.00% on 2026-10-22; D3 adds persistence around the module, not arithmetic inside it | [project: NEVER-rule] [NFR17] |
| NFR23.9 | Partial approval is tested with a claim that **differs** from the charge | The two formulas are indistinguishable when claim equals charge. The boundary case is charge 1000, claim 1500, approved 600: **400.00** correct against 900.00 wrong | [BR5.3] [spec § 5.3] |
| NFR23.10 | A named test exists **per fee-cycle and payment state transition**, and a documented boundary case per money input | Period boundaries, rounding at the half, zero, negative, and an approved amount exceeding the claimed amount | [team: Testing Posture] |

**NFR23.9 names the figures because the separating case is the whole test.**
A suite that uses a claim equal to the charge passes against the wrong formula.

---

## Assumptions & Open Questions

- **Assumed**: `ReminderEvent` carries no message body, only
  `(enrollment, period, channel, sent_at, sent_by, outcome)`. A stored body
  would be a free-form string beside a child's record — the shape
  `audit/log.py` deliberately avoids by having no field but `correlation_id`.
- **Assumed**: the four new tables need no new strict mypy island. Their
  authorization lives in `app.authz`, which is already strict, and their money
  lives in `app.money`, which is already strict.
- **Open, and the human's — OQ-1**: whether `transaction_id` survives
  deletion. D3 ships it nullable so the answer is not foreclosed, but the
  answer belongs in D6's disposition manifest and the privacy-policy text
  generated from it.
- **Open, and the human's**: the four governance dispositions. Mechanically
  forced by the schema-iterating test, so this cannot ship unanswered — but
  `LedgerEntry`'s is a genuine judgement between a child's financial record and
  a teacher's business record.
