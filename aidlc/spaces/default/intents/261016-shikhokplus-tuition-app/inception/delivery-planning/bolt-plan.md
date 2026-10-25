# Bolt Plan

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive
**Revision**: re-run 2026-10-22. Supersedes the 2026-10-18 plan of eleven
service-shaped Bolts, four of which have shipped.

> A **Bolt** is one build pass over a piece of the work, ending in something
> that runs. A **deliverable unit** groups one or more Bolts by what a person
> can do when it ships.
>
> This plan covers only what remains. Four Bolts are built and frozen; the nine
> that were outstanding are re-cut as six deliverable units.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` and
  `unit-of-work-dependency.md` — the Unit catalogue and the dependency DAG
- [upstream] `inception/contract-design/contract-summary.md`
- [upstream] `inception/domain-design/components.md` — ADR-001..008 and the
  Appendix A dispositions
- [decision] `docs/delivery/vertical-slices.md`, committed 2026-10-22 — the
  re-cut this stage brings into the record
- [human] Q7–Q16 in `delivery-planning-questions.md`
- [team] the affirmed Way of Working, Walking Skeleton, Deployment and Testing
  Posture
- [code] the built state on disk, read 2026-10-22

## What changed, and why this plan exists

The 2026-10-18 plan typed every Bolt `service`, `spec`, `library` or
`packaging`, and carried the Android work as a trailing clause of the
Definition of Done — B3 ended with "Android: OTP entry via SMS Retriever, the
lens switcher, both language bundles on screen one."

That boundary let a Bolt be **technically done and practically unusable**. B3
and B5 both shipped and both met their stated Definition of Done. What reached
the phone was a phone-number field, an OTP field, a batch list and two unstyled
forms, against nine working endpoints. Nothing flagged it, because nothing was
in breach.

**From here a Bolt is one user-visible capability: API, screens and tests
together.** Its Definition of Done names the design artboard it must match, and
it is not done until the thing can be done on a phone. [Q7]

Three decision changes arrived with that re-cut and are recorded here:

1. **Account creation did not exist in any Bolt.** A student or guardian is
   created by their teacher; a teacher had no path at all and could only exist
   by hand-inserting a database row.
2. **The app charges nobody.** The platform subscription is gone. The fee
   system is untouched — teachers still record and collect tuition from their
   own students, which is the product's core. [Q8]
3. **Every lens is returned at login** and the person picks one, with a switcher
   on every screen. Already built as `GET /v1/me`. [Q11]

And one gap this stage found and closed:

4. **A seat now requires acceptance before it grants a lens.** [Q10] See below.

## The lens model, as settled

Confirmed as already built, not changed: one account holds the teacher, student
and guardian lenses simultaneously, each computed per request from `Owner` and
`Enrollment`, with no role column anywhere [BR1.1]. `tests/authz/test_dual_role_cost.py`
proves all three resolve in one statement; `tests/batches/test_role_restricts_writes.py`
proves a student is refused a teacher's operations.

**What was missing is acceptance.** A teacher typing a phone number today makes
that account a student or guardian immediately — no consent, no notification, no
way to decline. A mistyped digit exposes a child's records to whoever owns that
number. From here:

- A seat a teacher creates is **pending**. It is visible to the account it names
  so they can act on it, and grants no student or guardian lens until accepted.
- **Declining is durable** and survives the teacher re-adding the same number, so
  a declined person is not prompted forever.
- **Acceptance markers are per link, not per row** [BR6.2] — `student_accepted_at`
  and `guardian_accepted_at`, mirroring the two erasure markers already on the
  seat. One flag cannot express the states, because the student's claim and the
  guardian's claim are independent facts about one seat.
- **The teacher's side never blocks on it.** Roster, batch and fee-cycle
  generation all work against a pending seat from creation. The debt is real
  whether or not anyone has opened the app. [Q13]
- **A pending state shows on the roster row** — the mechanism that catches a
  mistyped number, which would otherwise be indistinguishable from a student who
  has not opened the app yet. [Q14]
- **Dues predate acceptance and are shown in full**, so the teacher's roster and
  the student's own view never disagree about one seat. [Q13]
- **Removal is unchanged** [FR2.12, ADR-003]: edit any time, remove only while
  unclaimed, otherwise mark inactive. Acceptance does not create a new removal
  rule; it gives the existing dormant-vs-claimed distinction a precise meaning. [Q15]
- **One account may hold both links on one seat** — an adult student needing no
  guardian, or a teacher enrolling their own child. No special case. [Q12]

---

## A. What is already built

Frozen. Not re-planned, listed so the remaining plan reads against the real
state rather than the original one.

| Bolt | Unit | State |
|---|---|---|
| B1 `money-core` | U1 | Built. `Money` value object, both chokepoints, both import-boundary mechanisms, property test on the ledger identity. |
| B2 `api-contract` | U2 | Built. Committed OpenAPI, schema-diff gate, five-class error taxonomy, route-enumeration harness, schema-wide no-profile-field assertion. |
| B3 `identity-and-access` | U3 | Built. **The walking skeleton**, human-checkpointed. OTP with all seven abuse controls, computed lens, row-level security, auth audit log, first Alembic migration. |
| B5 `batches-and-enrollment` | U4 | Built. `Owner` indirection, Batch, enrollment with both links on one row, dormant-account resolution, `inactive_from`. |

Also landed outside a Bolt boundary: `GET /v1/me` (the lens summary), the
Compose design system, the app icon, a phone-installable APK, and the whole
deployment pipeline with its infrastructure.

**B4 `release-packaging` is partly built and is NOT complete.** Both release
gates exist in `android/release-gates.gradle.kts` — the merged-manifest
permission allowlist asserting the absence of `AD_ID`, and the minified-release
DEX scan for the ten forbidden identifiers. **The Macrobenchmark harness and the
low-end-device profile do not exist**, and the mid-class attendance latency
obligation [PU-3.6, TC-17] is dischargeable only by that harness. It is carried
into D5 below rather than being quietly assumed done.

---

## B. The remaining work, as six deliverable units

Nine outstanding Bolts, grouped by what a person can do when the group ships.
Each unit is independently installable and demonstrable on a phone.

| # | Deliverable unit | Bolts it groups | What a person can do when it ships |
|---|---|---|---|
| **D1** | `signing-up-and-joining` | V1 account creation, V1a seat acceptance | Create an account as a teacher, student or guardian; accept or decline a seat a teacher added you to |
| **D2** | `running-a-batch` | V2 batch and roster, V3 guardian view | Create a batch, add students and guardians, see the roster; a guardian switches between children |
| **D3** | `collecting-fees` | V4 fee cycles, V5 payment claims and verification | See what is owed, submit a payment, have a teacher verify it |
| **D4** | `teaching-and-recording` | V6 attendance, V7 marks | Record attendance mid-class; enter marks and publish a marksheet |
| **D5** | `knowing-how-it-is-going` | V8 insights, the outstanding half of B4 | See cross-batch dues and earnings; the latency obligation gets its harness |
| **D6** | `releasing-safely` | V9 privacy and governance | Delete an account, by either path; ship to a public Play track |

Sizes are relative, not estimates. Serial execution: this is a solo build and
there is no second worker [Q5], not because the DAG forbids concurrency.

### Why these groupings

- **D1** pairs signup with acceptance because they are one flow, not two
  features: a student whose teacher already added them signs up and claims that
  seat in a single pass through O1 state 3. Building them together also means
  the pending state is never shipped without a way to resolve it [Q16] — which
  is exactly the failure this re-cut exists to prevent.
- **D2** pairs the roster with the guardian view because both are screens over
  endpoints that already work. No new backend capability; the gap is entirely
  on the phone.
- **D3** keeps fees and payments together because a fee a person cannot pay is
  not a shippable capability. Splitting them would ship a screen that shows a
  debt with no way to clear it.
- **D4** pairs attendance with marks because they are the two things a teacher
  does *during and after* a class, and they share the batch-session surface.
- **D5** is grouped by necessity rather than affinity: insights is the last
  feature Unit, and the Macrobenchmark harness has to exist by the time the
  latency obligation is checked. See the risk note below.
- **D6** stands alone because it is release-blocking and terminal.

---

## C. Per-unit detail

Every unit inherits, without restatement below: tests per the affirmed Testing
Posture predicate; `make check` green locally and in CI; squash-merge to `main`
as one commit per Bolt; conventional-commit shaped; the per-Bolt governance
obligation (every table a migration creates carries a disposition row per
deleting actor and a retention class, or the schema-iterating test reddens CI);
Bangla and English both present with the layout surviving the longest Bangla
string; accessibility and back-stack, where Back must never land in another
lens's or another child's data.

**Every unit below also inherits the new screens rule**: it names the artboards
it must match, and it is not done until the capability can be exercised on a
phone.

### D1 — `signing-up-and-joining` (L)

**The slice that makes the app usable by someone who has never used it.** Nothing
in the built system creates an account.

**API.** `POST /v1/accounts` taking role, name, phone and address — creating the
`Account`, plus an `Owner` row when the role is Teacher and none otherwise, so
the role is decided by what gets created and never stored [BR1.1]. A lookup the
signup form calls before it renders, for the already-added case. Migrations for
`address` and a display name, each with its governance disposition row, both
being personal data [RC-5]. Seat acceptance: `student_accepted_at`,
`guardian_accepted_at` and their durable decline markers, with accept and
decline endpoints. The lens resolver reads the acceptance markers, so a pending
seat grants nothing.

Signup carries **its own per-number and per-IP ceilings**, separate from the OTP
ceilings. Unlike `POST /v1/auth/otp`, signup's response is deliberately
informative — state 5 of the artboard says "This number already has an account"
— so it is an existence oracle by construction and needs its own abuse control.

**The already-added lookup names neither the teacher nor the batch** [Q9]. It
confirms the number has been added and returns what the form needs to pre-fill
and lock the role, and nothing more. The artboard shows the teacher's name and
the batch; that is the one place this plan departs from the design, deliberately,
because anyone who typed a phone number would otherwise learn who teaches that
person and where.

**Screens.** `O1` create account, in all five states — empty, filled,
already-added with the role locked, sending, and the two errors. `O2` log in,
restyled. `O3` OTP, which already matches. The pending-seat list and its accept
and decline actions.

**Done when.** Someone installs the APK, signs up as a teacher on a number nobody
has entered, and reaches their own empty batch list. A student whose teacher
already added them signs up, sees their name pre-filled with the role locked,
and accepts the seat. A person who declines is not prompted again when the
teacher re-adds the same number.

**Confidence hypothesis.** *A phone number typed by a teacher grants that account
no student or guardian lens until the account holder accepts, and `POST
/v1/auth/otp` remains byte-identical for known and unknown numbers after signup
exists.* Falsified by: a lens resolving for an unaccepted seat, or the existing
adversarial OTP test failing once signup is added. Secondary: *a declined seat
re-added by the teacher does not re-prompt.*

### D2 — `running-a-batch` (M)

Everything the built endpoints already support, with the screens the design
specifies. **No new endpoints.**

**API.** `GET /v1/batches`, `POST /v1/batches`, `GET /v1/batches/{id}/roster`,
`POST /v1/batches/{id}/enrollments`, `DELETE /v1/enrollments/{id}` and
`GET /v1/guardian/children` all exist and work. The one addition is the pending
state on the roster response [Q14], which the roster screen renders.

**Screens.** `T6` batch list (built); `T7` single batch with roster, showing the
pending state per row; `T8` add student; create-batch, replacing the bare text
fields in `CreateForms.kt`; remove-student, which has no UI at all today. `G1`
guardian child home and switcher.

**OQ-7 settles here** — the guardian-child route shape was deferred to "when the
guardian screens are in front of the decider", and this is that unit.

**Done when.** A teacher creates a batch, adds two students by phone number, sees
them on the roster with their pending state, and removes one that nobody has
claimed. A guardian with two children switches between them.

**Confidence hypothesis.** *A teacher adding a student who never accepts sees that
seat as pending indefinitely and can correct the number, while a teacher adding a
student who accepts sees the state change without any action of their own.*
Falsified by: a roster that cannot distinguish the two, which is the mistyped-digit
failure this state exists to catch.

### D3 — `collecting-fees` (XL)

The money surface. Two Bolts, kept together because a fee nobody can pay is not a
capability.

**V4 — fee cycles and ledger.** Append-only `LedgerEntry` with its seven kinds;
the thin `FeeCycle` carrying only the `(enrollment_id, period)` unique constraint;
generation via `ON CONFLICT DO NOTHING` and never an application-level guard
[TC-12, D-21]; calendar-month periods with the short-month clamp; the daily
self-healing job; credit grant and apply; two-sided carry-forward, where a
`carried_out` entry relieves the originating period and a `carry_forward` entry
charges the receiving one; the server-computed status enum (`due`/`paid`/`partial`)
so no client ever compares a balance [TC-9]. **Owns the FCM adapter** per OQ-4:
`DeviceToken` lifecycle, `UNREGISTERED` deletes the token, dispatch after commit
outside the request transaction, failure logged and never surfaced.

`Money.format(locale)` becomes blocking here — deferred out of B1 and specified
at `construction/money-core/nfr-design/security-design.md` §A.6 (Western digits,
2,2,3 lakh/crore grouping, `৳` prefix with no space, decimals suppressed when
zero), with NFR9.26's build-time completeness check.

**V5 — payment claims and verification.** The identical submission form in the
student and guardian lenses; batch → enrollment → open-cycle resolution; partial
amounts; the server-supplied channel list as a database row and never a client
enum; the pending-verification list; approve, approve-less, reject;
carry-forward-or-waive on partial; over-approval becoming credit; verifier
identity and timestamp; payment history with overwrite-and-visible-history
[FR9.1, FR9.2].

**Screens.** `T5` dues, `S2` batch fees, `T4` verify, `S3` submit, `G3` history.

**Tests are mandatory here, not optional** [TC-20, D-23, PU-5.7], and test-first
by the predicate throughout: the correct output is knowable from the requirement
and a wrong answer is a money error. 100% branch coverage on the money module.
Idempotency tested with **overlapping concurrent** generations asserting the
outcome, plus the across-days case.

**Done when.** A teacher sees what each student owes, a student submits a payment
against an open cycle, the teacher approves it for less than claimed, and the
remainder carries forward with the enrollment total unchanged.

**Confidence hypothesis.** *A partial payment approved for less than claimed leaves
the originating period relieved and the receiving period charged such that the
enrollment-level total is unchanged, and an approval exceeding the claim becomes
an `available_credit` grant rather than a negative outstanding.* Falsified by: a
negative `outstanding` at any point, or a carry that changes the enrollment total.
Privacy secondary: *a guardian claiming against a non-child's enrollment, and a
student requesting a fee cycle not their own, each receive a 403 byte-identical
to the response for an id that does not exist.*

### D4 — `teaching-and-recording` (XL)

**V6 — sessions and attendance.** Session instances from weekly recurrence plus
ad-hoc; status transitions; reschedule and cancel; the topic log; the atomic
roster write with optimistic concurrency via `attendance_version` and
`client_mutation_id`; the four-state queue (queued / confirmed / failed /
conflicted) surviving app restart and syncing on reconnect; the refuse-on-conflict
rule, never merged and never silently applied [ADR-006, FR11.4]; the
conflict-resolution screen [FR11.5] offering re-apply or discard with the offline
entry preserved until chosen, where **re-apply uses a new `client_mutation_id`**
because reusing the old one silently turns re-apply into a no-op; announcements.

**V7 — exams and marksheets.** Exam creation per batch and subject; mark entry
with the four result states and correction history via `superseded_by_id`; the
batch-scoped marksheet, **anonymised** [FR4.5]; the `marksheet_visible` toggle;
exam dates; the guardian progress-over-time view. **Reuses V4's FCM adapter**;
reimplementing it is a Definition of Done failure.

**Screens.** `T1` today, `T2` record a class, `T3` mark entry, marksheet in light
and dark.

**PU-3.6's mid-class speed requirement is not discharged by a correctness test.**
It needs the Macrobenchmark on the low-end device profile — which does not exist
yet. See the sequencing risk in `risk-and-sequencing-rationale.md`.

**Done when.** A teacher takes attendance mid-class on a real phone, loses
connectivity mid-write, and gets an explicit conflicted state with a working
re-apply rather than a silent overwrite. A student sees an anonymised marksheet.

**Confidence hypothesis.** *An attendance roster composed offline against version N,
submitted after the teacher changed that roster from another device to version
N+1, is refused and surfaced as `conflicted` — never `failed`, never silently
applied, never merged — and re-applying it writes, because it carries a fresh
`client_mutation_id`.* Falsified by: a conflicted write presenting as failed, a
silent overwrite, or a re-apply returning success while changing nothing.

### D5 — `knowing-how-it-is-going` (M)

**V8 — teacher insights.** Cross-batch dues driven by **outstanding balance and
not active status**, so students who left owing money still appear [PU-7.2];
monthly earnings; earnings trend; collection rate with its carry-forward, waiver
and credit rules; next upcoming exam. The empty-state rule from AC9.2.5 honoured —
an explanation, never a bare empty state. List membership and order decided
server-side; the client may not filter or re-sort [TC-9].

**Carries OQ-2 explicitly**: FR8.3's collection-rate definition is open to
correction and AC8.3.4's credit rule postdates it. The `collection_rate` field
does not ship to a client until the arithmetic is settled — a field can be added
additively, a wrong number pinned into an installed client cannot be withdrawn.

**Plus the outstanding half of `release-packaging`**: the Macrobenchmark harness
and the low-end-device profile, the 15 MB download-size assertion measured from
the Play Console's reported `arm64-v8a` split, Syft SBOM per release build, and
the ZAP baseline pass wired against the committed OpenAPI schema.

**Done when.** A teacher sees every student who owes money across all their
batches, including one who left mid-year still owing.

**Confidence hypothesis.** *A student who left a batch mid-year owing 2000 BDT
appears on the cross-batch dues screen, and an active student who owes nothing does
not — the query is driven by balance and not by status.* Falsified by: the departed
debtor missing, which is the specific defect an "active students" query produces
naturally.

### D6 — `releasing-safely` (L) — release-blocking

Terminal, and the gate on any public Play track.

Both Governance manifests complete and the schema-iterating test green against
the final schema. **Both account-deletion paths**: in-app, and an externally
accessible route usable without reinstalling the app, as a public FastAPI route.
A test per path asserting deletion removes exactly what the Data Safety form
claims and retains exactly what the privacy policy discloses, **per each table's
written disposition** from `components.md` Appendix A — including the
uncomfortable ones: `Enrollment.guardian_phone` survives the guardian's deletion,
`PaymentClaim` is anonymised not deleted, `AuthAuditLog` is anonymised in place.
Deletion is idempotent [FR11.3]. The idempotent chunked purge honouring ADR-004's
clocks, with the visible-purge rule — a guardian opening the app in 2031 for a
2027 marksheet sees "records older than three years are not kept", never a bare
empty state. Privacy-policy text **generated from the manifests**, not written
independently. Data Safety form content. Play children's-data and target-audience
declarations. Deletion-confirmation copy naming what is retained, including
ADR-003's "a teacher cannot make their students' records go away".

**Acceptance adds two columns to this unit's scope**: `student_accepted_at` and
`guardian_accepted_at` each need a disposition and a retention class like any
other personal-data column.

**OQ-1 and OQ-5 must close before this unit starts.** See
`external-dependency-map.md`; the previous plan pointed at a "section D" that did
not exist in the document, which is corrected here.

**Done when.** A guardian deletes their account by each path and the database
matches the privacy policy row by row.

**Confidence hypothesis.** *After a guardian deletes their account, every column the
privacy policy says is removed is absent and every column it says is retained is
present — asserted row by row against the manifest rather than a remembered list —
and a second deletion request succeeds with no further effect.* Falsified by: any
divergence between the generated policy text and the database state, which is
precisely what this unit exists to prevent and which no review catches, because
nobody tests the absence of data.

---

## D. Gating

**Construction runs autonomously from here** [Q8]. The affirmed practice gated
"through the payment slice, then autonomous", and that slice was the platform
subscription boundary, which no longer exists — the app charges nobody. The fee
system remains in full, but it no longer marks a gating boundary.

Human stops that remain regardless, and are not affected by this: Plan Approval,
summary confirmation, verification-command selection, and any failure.

The walking skeleton is already built and was human-checkpointed at B3, so the
skeleton ceremony does not recur.

## Assumptions & Open Questions

- **Assumed:** a teacher's display name is all signup needs. A subscription plan,
  an institution name and a photo are all plausible and none is required to reach
  a batch list, so they are left out until something needs them.
- **Assumed:** acceptance needs no expiry. A pending seat stays pending
  indefinitely rather than lapsing after some period. An expiry is additive if
  teachers find stale pending rows a nuisance, and inventing a window now would
  be guessing at a problem nobody has reported.
- **Open, and it belongs to D4's sequencing rather than to this list:** whether
  the Macrobenchmark harness is built at the start of D4 or whether PU-3.6 carries
  an explicit manual pilot check instead. Both are acceptable; silently using a
  correctness test to discharge a performance requirement is not. Recorded in
  `risk-and-sequencing-rationale.md`.
- **Carried from Domain Design:** whether `PaymentClaim.transaction_id` survives
  the claimant's deletion. A product and legal judgement; D6 implements whichever
  answer lands.
- **Carried, OQ-2:** FR8.3's collection-rate definition remains open to
  correction. D5 ships without the `collection_rate` field rather than with
  provisional arithmetic.
