# Architecture Decision Records — Domain Design

**Stage**: domain-design (2.6)
**Phase**: Inception
**Date**: 2026-10-18

Six decisions deferred since Intent Capture and Requirements Analysis, plus two
decomposition choices made here. Decided by a dispatched architect under the
user's delegation.

---

## ADR-001: The teacher-vs-teacher privacy boundary is a keying rule

**Context.** The privacy boundary is specified between teachers and
students/guardians [desc §4], and between admins and students/guardians
[intent: Q20]. It was never specified between two teachers. One phone number is
one permanent account, a student may be enrolled with several teachers at once
[desc §3], and roles are lenses computed per request [TC-11]. Carried as an open
question since Requirements Analysis.

**Decision.** A teacher's lens is scoped to the batches their Owner owns, and
nothing else. Stated as one mechanically checkable invariant:

> **Every teacher-lens query is rooted at `owner_id`, and every teacher-facing
> response schema exposes `enrollment_id` and never `student_account_id`.**

Teacher A must not see, for a shared student: teacher B's batches, sessions,
attendance, exams, marks, fee cycles, payments or reminders; **the fact that
teacher B exists at all**; or any aggregate crossing the owner boundary. The
cross-batch dues view [FR7.1] is cross-*batch*, never cross-*owner*.

FR2.19 is **the general rule, not a special case**: the phone number is a global
identifier but never a global query key for a teacher lens. A teacher types a
number to create an enrollment; a teacher never reads by number.

**Consequences.**

*Positive.* The leak has no address to travel to, rather than being filtered out
at each site. Row-level security on the enrollment-rooted tables, keyed on a
request-scoped setting the lens sets, survives a forgotten `WHERE`. The existing
schema-wide invariant test gains one more forbidden field set rather than a new
mechanism. The enumeration oracle closes with the same structural assertion
FR2.19 already uses.

*Negative.* Every teacher-facing endpoint must be keyed on `enrollment_id`, which
is slightly more awkward than an account id in a handful of places. Three more
tables carry row-level security. An unscoped `find_account_by_phone` must be
contained by an import rule, which is a boundary someone could route around if
they did not know why it exists — hence the behaviour note on the Identity
component.

**Alternatives rejected.**

- *A fourth RLS policy on `profile`.* Would not have worked. The existing
  three-layer boundary separates **writers** — profile versus enrollment — and
  here both teachers write enrollment-shaped data in the same tables, so the
  boundary cannot see this leak at all.
- *Filtering by owner at each query site.* The forgotten-`WHERE` failure mode,
  which the project's practices reject generally for exactly this reason.
- *Treating FR2.19 as a one-off.* It is the only place the requirements happened
  to notice the problem, because the add-student lookup is the one teacher read
  whose natural implementation is a global phone lookup. Leaving it as a special
  case would leave the general rule unstated.

---

## ADR-002: The fee ledger is append-only entries with a derived balance

**Context.** The original model had `FeeCycle(enrollment, period, due_date,
amount_due, carry_in, adjustment, amount_paid, status)` with a stated balance
formula. It was superseded at Intent Capture [intent: Q19] by a teacher-adjustable
anchor plus a ledger, and again at User Stories [Q7.2] when overpayment forced a
fifth quantity — credit. FR5.1 now names five quantities; FR5.9 adds the credit
rule. Carried as an open question since Requirements Analysis.

**Decision.** Append-only `LedgerEntry` rows with every quantity derived, plus a
thin mutable `FeeCycle` row that exists **only** to carry the idempotency
constraint and the period's identity. No money columns on `FeeCycle` at all.

Entry kinds: `charge · receipt · carry_forward · carried_out · forgiveness ·
credit_grant · credit_apply`. **Amounts are always non-negative; the sign lives
in the kind.**

**Carry-forward is two-sided.** A carry appends *both* a `carry_forward` on the
receiving cycle and a `carried_out` on the originating one. A one-sided
`carry_forward` double-counts the debt: it appears in the old cycle's
outstanding and again in the new cycle's carried-in, so an enrollment carrying
1000 into a second 1000 charge reads 2500 owed instead of 1500. At the
enrollment level the two kinds are equal and cancel, which is what makes
carry-forward an internal transfer rather than a new charge.
A correction appends a compensating entry and marks the original superseded —
which satisfies FR9.1's "overwrite" (a statement about what the teacher *sees*)
and gives FR9.2's previous-value-and-actor for free.

Credit belongs to the **enrollment**, not to a cycle. An overpayment appends a
`receipt` for the applied part and a `credit_grant` for the excess; the next
generation appends a `credit_apply` of `min(available_credit, charge)`.

**The invariant, corrected.** The team's affirmed practice records
`charged − received − forgiven == outstanding`, which **omits carry-forward** —
in the same sentence that lists carry-forwards among the operations it covers —
and predates credit entirely. It would fail on its first carry-forward.

A first correction attempt was itself wrong and is recorded here because the
error is instructive. It read
`total_charged + total_carried − total_received − total_forgiven ==
total_outstanding − available_credit`, and it fails on the very overpayment case
that motivated it: charge 1000, approved payment 1200 gives
`1000 + 0 − 1000 − 0 = 0` on the left but `0 − 200 = −200` on the right. The
cause is that `receipt` records only the *applied* part of a payment, so the
200 that physically arrived as `credit_grant` never reaches the received side.
**Cash in is `receipt + credit_grant`, not `receipt`.** The per-cycle form was
also missing a `credit_apply` term, so a 1000 charge with 200 credit applied
computed 1000 outstanding rather than 800.

The correct form, which this design satisfies by construction:

```
per cycle:       outstanding == max(0, charged + carried_in
                                       − received − forgiven
                                       − credit_applied − carried_out)
                 outstanding >= 0

per enrollment:  total_charged − total_forgiven − total_cash_in
                   == total_outstanding − available_credit

                 where total_cash_in     = total_receipt + total_credit_grant
                       available_credit  = total_credit_grant − total_credit_apply
                       available_credit >= 0
                       total_outstanding >= 0
                       sum(carry_forward) == sum(carried_out)
```

In English: *every taka charged and not forgiven is either still owed or has
been received — and anything received beyond what was owed is held as credit.*
Outstanding and credit are the two non-negative halves of one signed quantity,
which is what makes the never-negative rule expressible. Carry-forward does not
appear in the enrollment-level identity at all, which is the correct result:
moving a debt between periods is not an economic event.

**Verified, not asserted.** The form above was checked against twelve worked
cases covering the plain, partial, waiver, full-waiver, carry-forward,
multi-period carry, overpayment, credit-applied, credit-exceeding-charge,
pure-advance and overpayment-with-carry paths, and then against 20,000
randomized enrollment histories composed of those operations in arbitrary
order. Zero failures. This matters because the team's practice mandates 100%
branch coverage on the money module with this identity as the property-based
test — an unverified invariant there would certify the arithmetic it was
supposed to check.

**Consequences.**

*Positive.* A sixth quantity becomes a new `kind` value rather than a migration —
which matters, because this model is already on its second revision. Correction
history stops needing a parallel mechanism that could drift. The analytics
filters FR8.3 requires (`carry_forward` excluded both sides, `forgiveness`
excluded from the denominator) become expressible, which they were not against a
mutable row. FR5.6, AC6.3.3 and FR7.2 all fall out without special cases.

*Negative.* Every balance is a query rather than a column read. On a 2 GB
instance at the stated scale this is fine; if it ever is not, the fix is a
materialized rollup, which append-only makes safe.

The escalation needs a trigger rather than a feeling, because the cross-batch
dues view [FR7.2] is the most expensive read in the system — driven by
outstanding balance rather than active status, so it evaluates every enrollment
an owner has ever created, including long-inactive ones carrying years of
ledger history, on every open with no generate step [FR7.3] — and it degrades
silently as the ledger grows. **Build the rollup when either holds: the dues
view's p95 exceeds 800 ms in staging at NFR6 scale, or any single owner
exceeds 20,000 ledger entries.** The first is the user-visible symptom; the
second is the leading indicator that reaches us before a teacher complains.
Index and query shape are Functional Design's to settle — what belongs here is
the decision rule, so that stage inherits a threshold rather than an
open-ended "fine for now". Concurrent generation needs a
`SELECT ... FOR UPDATE` on the enrollment row so two cycles cannot double-spend
one credit — a bounded lock on a row generation already touches, and not the
application-level idempotency guard the project rule forbids.

**Alternatives rejected.**

- *Mutable row per cycle with more columns.* The shape that produced the current
  revision. It stores the **answer**, so every new quantity is a column and every
  correction is lossy.
- *Idempotency constraint on `LedgerEntry`.* Wrong: legitimate second charges
  (an adjustment) exist on the same cycle. The constraint needs a row to sit on,
  which is the whole reason `FeeCycle` is retained.
- *Credit as a column on `FeeCycle`.* A credit granted in March does not belong
  to March; it belongs to the enrollment. Cycle-level credit would make
  AC6.3.8 a search rather than a lookup.

---

## ADR-003: A teacher's deletion removes their identity, not their students' records

**Context.** FR11.1 settles the student and guardian case. FR11.2 deliberately
did not settle the teacher case, because a teacher deleting their account would
destroy attendance, marks and fee history belonging to students who were never
asked. The affirmed practice requires a written disposition per table, from which
the privacy policy is generated [RC-5].

**Decision.** A teacher's deletion hard-deletes their account, profile, phone
number, authentication records and collection number, and ends their ability to
sign in. It deletes **no** batch, enrollment, attendance, mark or fee record. The
`Owner` row is retained in a terminal `deleted` state: batches become permanently
read-only, no new teacher may attach, no new data may be written, and students and
guardians keep read access to their own history. The per-record retention clocks
[ADR-004] then run normally.

The teacher's **display name on the batch is retained**, as a denormalized
teacher-typed copy — because a student's history saying "Chemistry, 2026, Rahman
sir" is the student's record of their own past, and removing it destroys the
record's meaning.

Full disposition table in `components.md` **Appendix A**, which is the data the Governance manifest holds — one row per entity per deleting actor, with the privacy-policy clause each disposition generates. Two rows
deserve attention:

- **`PaymentClaim` is anonymized, not deleted** — the one table where a student
  or guardian writes something a teacher legitimately needs. Hard-deleting it
  would leave an approved `receipt` in the ledger with no originating claim,
  breaking the audit trail on money. Severing authorship leaves the financial
  fact.
- **`Enrollment.guardian_phone` survives the guardian's deletion** — it was typed
  by the teacher and is the teacher's own contact record [FR2.6], the same
  category as the display name. Uncomfortable, deliberate, and the privacy policy
  must say so plainly.

**Consequences.**

*Positive.* Symmetric with FR11.1: teacher-authored records survive the subject's
deletion, so they equally survive the author's. Disclosable in one sentence a
person can act on, which is the actual test — and the teacher is told at the
confirmation [AC9.4.3] before confirming. Retention is bounded rather than
indefinite.

*Negative.* **A teacher cannot make their students' records go away.** That is
the right answer and it will surprise someone. It is surfaced at the approval
gate rather than buried in a table, and it is stated in the deletion
confirmation.

**Alternatives rejected.**

- *Cascade the delete.* One person's routine account action silently destroying
  dozens of children's records, with no notice and no consent. Cannot be
  disclosed truthfully in a Data Safety form, and fails COPPA and GDPR-K
  [RC-2, RC-3].
- *Anonymize the teacher-authored records in place.* Removes the teacher's name
  from a student's history, which destroys the record's meaning for the person it
  belongs to.
- *Refuse teacher deletion entirely.* Denies a real erasure right over the
  teacher's own personal data, which is the part they are actually entitled to.

---

## ADR-004: Retention is per data class, split academic from financial

**Context.** No retention period was set for marks, attendance or fee history,
and the requirements noted this needed the teacher's-record-versus-child's-data
tension resolved first. ADR-003 resolves it: the records are **both**, which makes
retention the only lever that bounds the child's exposure without destroying the
teacher's record.

**Decision.**

| Data class | Retention | Clock |
|---|---|---|
| Auth ephemera (OTP, verify attempts, rate-limit counters) | **7 days** | row creation |
| Refresh tokens | **30 days past expiry** | token expiry |
| Auth audit log | **13 months** | event time |
| Academic records (sessions, attendance, exams, marks, announcements) | **3 years** | the record's own date; `Announcement` runs from `created_at` |
| Financial records (cycles, ledger, claims, reminders) | **6 years** | entry `occurred_at` |
| Dormant enrollments with no activity | **18 months** | enrollment creation |
| Enrollment carrying history | follows its longest-surviving child record | — |

**Consequences.**

*Positive.* The academic-versus-financial split follows the data rather than
convention: an attendance mark has no use once the student has moved on and the
next reference is written, whereas a disputed payment has a longer conventional
life. One number for both would either keep children's attendance six years for
no reason (failing storage limitation) or discard financial evidence at three
(failing the teacher). The 18-month dormant rule is the one that earns its keep
daily — FR1.9 guarantees a steady accumulation of rows holding real phone numbers
that will never authenticate, and nothing else removes them.

*Negative.* These are **defensible defaults, not numbers derived from a
Bangladeshi statute** — RC-7 records that no general retention statute applies, so
the basis is GDPR-K storage limitation plus proportionality. A stated number is
enormously better than silence, but it is a judgement. The purge must also be
visible: a guardian opening the app in 2031 for a 2027 marksheet should see
"records older than three years are not kept", not an empty state — the same
error AC9.2.5 already forbids for the dues view.

**Alternatives rejected.**

- *One period for everything.* Fails one side or the other, as above.
- *No stated retention.* Leaves RC-5's privacy-policy requirement ungeneratable
  and the storage-limitation principle unaddressed.

---

## ADR-005: Subscription absorbs through three accommodations, none of them subscription logic

**Context.** Subscription state is deferred to V2 but carries the standing
"absorb without rework" obligation [intent: Q20]. Unlike org-owned batches (the
Owner indirection) and the PWA (server-side rules plus generated OpenAPI), it had
an obligation recorded and **no mechanism**. Flagged at the Ideation phase check
as the gap most easily overlooked, because nothing in V1 exercises it.

**Decision.** Three accommodations, all V1:

1. **`Owner` carries the subscription anchor** — `plan` and `plan_valid_to`
   columns, written once as `'pilot'` and `NULL`, read nowhere. Subscription is a
   property of the entity that owns batches, which is what makes it survive the
   arrival of organisations.
2. **`TeacherLens` carries one entitlement value**, always `FULL` in V1, resolved
   at one named call site on the path every teacher-lens request already takes.
   Roughly fifteen lines.
3. **The client renders an unknown error `code` as a generic localized message** —
   stated as a client obligation with a test, so a V2 subscription refusal needs
   no app release.

**Consequences.**

*Positive.* Each removes one thing a new table cannot fix: an attachment point
that does not exist, an enforcement point that does not exist, and a client that
cannot render a new refusal. The route-enumeration test already asserts every
teacher route resolves a lens, so it now transitively guarantees every teacher
route passes the entitlement point.

*Negative.* Two columns and an enum that do nothing in V1, which will look like
dead code to a reader who does not know why. Mitigated by the behaviour note on
the Ownership component.

**Alternatives rejected.**

- *Nothing now; add a subscription table in V2.* The table is the cheap part. The
  expensive parts are re-keying off `account` after organisations arrive, and
  auditing forty endpoints for where the check belongs — which is exactly the
  rework the obligation forbids.
- *Build subscription state in V1.* Reverses a settled scope decision and encodes
  product decisions nobody has made. `'pilot'` and `FULL` deliberately commit to
  nothing.

---

## ADR-006: Queued writes refuse on conflict rather than merging or overwriting

**Context.** FR11.4 records last-write-wins per field with correction history and
no locking. The offline write queue was added later, at Refined Mockups
[mockups: Q11.2], for the mid-class path. A queued roster can now arrive hours
after the same session was edited from another device.

**Decision.** Split the rule.

- **Interactive writes** (two devices, both online): last-write-wins per field
  with correction history. Unchanged.
- **Queued writes** (the mid-class path): optimistic concurrency on
  `session.attendance_version`. A queued write whose base version no longer
  matches is **refused with a `ConflictError`, reported to the teacher with the
  current state and an explicit re-apply action** — never merged, never silently
  applied, never silently discarded.

`client_mutation_id` with a unique constraint satisfies AC9.2.4's double-submit
rule for the queue as well as the double-tap.

**Consequences.**

*Positive.* Prevents a failure that is almost invisible: a roster queued at
10:15, a correction from a tablet at 11:00, and the phone reconnecting at 11:40
to silently reinstate the stale mark — with correction history then faithfully
recording a change the teacher never made, **which is worse than no history
because it looks authoritative**. Consistent with NFR5.1's promise that queued is
a third state whose outcome is reported.

*Negative.* The teacher sees a conflict screen in the rare case. Requires a fourth
queue state, `conflicted`, distinct from `failed` — because failed implies "try
again" and this one means "look at what changed".

**Requires amending:** FR11.4 (records a general rule the queue contradicts for
the one path where it matters) and NFR5.1 (needs the fourth state). Both flagged
at the gate.

**Alternatives rejected.**

- *Per-field last-write-wins for queued writes too.* Cannot work: AC3.1.5
  requires the roster to be written in **one atomic operation**, so the whole
  roster is one write and field granularity does not exist.
- *Merge the two rosters.* Would mean inventing a rule for a student the rosters
  disagree about — a business decision made by a sync layer, which TC-9/D-31
  forbid the client from holding and nothing authorizes the server to invent.
- *Arrival-time last-write-wins.* The failure above. Arrival time is an artifact
  of when the teacher walked back into signal.

---

## ADR-007: Fees and Payments are separate components

**Context.** Both touch money and a verification immediately produces ledger
entries, so one component is the obvious shape.

**Decision.** Separate. Payments appends to the ledger through Fees' API and never
inserts a `LedgerEntry` directly.

**Consequences.** *Positive:* the writer differs, and that difference **is** the
privacy boundary — students and guardians write claims, teachers write
verifications. A boundary in the code where the boundary exists in the domain.
*Negative:* one cross-component call on the verification path, and the atomicity
of "approve and append" spans a component boundary.

**Alternatives rejected.** *A single Billing component:* would put both sides of
the privacy boundary in one module and make "never write a ledger row directly" a
convention rather than a boundary. Reversible — merging later is easy; splitting
after entanglement is not.

---

## ADR-008: Teaching is one component, not three

**Context.** Sessions/attendance, exams/marks and announcements are three
distinguishable concerns.

**Decision.** One Teaching component.

**Consequences.** *Positive:* they share the batch shape, the same change rate,
and **the same optimistic-concurrency mechanism** — and a rule implemented twice
is a rule that drifts. *Negative:* the coarsest component in the catalogue, and
announcements genuinely have little to do with marks.

**Alternatives rejected.** *Three components:* would duplicate the ADR-006
concurrency rule across two of them. Reversible — the entities are already
distinct, so splitting later is mechanical.

---

## Flags for the approval gate

Four things a human should see rather than discover later.

1. **A teacher cannot make their students' records go away** [ADR-003]. The right
   answer, and the kind that should be said out loud.
2. **The team's affirmed Hypothesis invariant is wrong** [ADR-002] — it omits
   carry-forward and predates credit. Changing an affirmed practice goes through
   the learnings gate, not a direct edit.
3. **FR11.4 needs amending and NFR5.1 needs a fourth queue state** [ADR-006].
4. **The privacy policy is now generatable** [ADR-003, ADR-004], which unblocks
   the release-blocking RC-4 and RC-5 deliverables.
