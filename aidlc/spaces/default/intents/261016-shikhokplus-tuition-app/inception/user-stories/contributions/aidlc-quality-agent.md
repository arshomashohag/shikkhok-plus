**Collaborator:** aidlc-quality-agent

## Contribution

Reviewing solely for testability of the acceptance criteria. The draft is strong
on structure — Given/When/Then throughout, one actor per story, stable AC keys,
and three deliberate absence-assertions. The remaining weaknesses are
concentrated in exactly the places the affirmed Testing Posture cares about most:
the money state machine, the authorization boundary, and the idempotency
guarantee. Those three are where a vague criterion is most expensive, because
they are the three surfaces where the practices promise a *specification-grade*
test and the criterion is supposed to be that specification.

---

### 1. Criteria that are not testable as written

The inception rule is a clear pass/fail criterion and no ambiguous language
without a measurable threshold. Walking every criterion, these fail that bar.
I have split them, per remit item 7, into **vague** (fix now) and **deferrable**
(fine at story level, gets its specification at Functional Design).

#### Vague — fix in this artifact

**AC2.3.1 — "immediately"** is the clearest failure. "Immediately" is either a
latency claim (untestable without a threshold, and a threshold nobody wants to
commit to) or it means "no stale-cache step is required", which is the actual
intent. As written a developer can satisfy it with a 60-second Room cache TTL and
argue the criterion passed. It also quietly contradicts [TC-8] Room-as-read-cache:
the honest statement is about the *server*, not the client render.

> **AC2.3.1** (replace) — Given an enrollment, When I edit the display name and
> the write succeeds, Then the next fetch of any roster, marksheet or dues view
> returns the new name, and no view returns the old name after a successful
> write. [FR2.5]

Add a second criterion, because the client half is a real obligation and
currently hidden inside the word "immediately":

> **AC2.3.3** (new) — Given I edited a display name, When I return to a roster I
> had already viewed in this session, Then the cached old name is not shown.
> [FR2.5] [TC-8]

**AC1.3.3 — "not visually distinguished"** is a negative over an unbounded set.
A test cannot assert the absence of every possible visual treatment; it can
assert the absence of the *data* that would enable one. This is the mechanical
form the team's own "where a rule is important, it is mechanical" principle asks
for, and it is checkable at the API, which is where [TC-9] puts the decision
anyway.

> **AC1.3.3** (replace) — Given a dormant enrollment, When I fetch the roster,
> Then the response carries no field indicating whether the enrollment has been
> claimed, so no client can distinguish it. [FR1.8] [TC-9]

That phrasing also resolves the open assumption cleanly: if the human later
decides a teacher *should* see unclaimed numbers, the change is "add the field",
which is a visible, reviewable API diff rather than a UI opinion. **I support the
draft's design choice, but note the criterion as written is unfalsifiable and the
replacement is falsifiable in either direction.**

**AC3.4.3 — "with their age indicated"** has no verifier. Age of what, expressed
how, at what granularity? And it crosses the [TC-9] line: deciding what counts as
stale is a business rule.

> **AC3.4.3** (replace) — Given no connectivity, When I open a batch I have
> viewed before, Then the last fetched schedule and topics are shown together
> with the server-supplied `fetched_at` timestamp of that cached response, and
> the screen states that the data is cached. [NFR4] [TC-8]

**AC7.1.5, AC8.1.6 — "a defined empty state"** is a promissory note, not a
criterion: it says a definition exists elsewhere. At story level the testable
content is the *distinction* that matters, which is empty-versus-error-versus-
loading — the three-way confusion that actually ships broken.

> **AC7.1.5** (replace) — Given nobody owes anything, When I open the dues view,
> Then an explicit "nobody owes anything" state is shown, distinct from both the
> loading state and any error state, and no row is rendered. [FR7.3]

Same shape for **AC8.1.6** ("no upcoming exam" state). **AC2.6.2's "collapsed by
default"** is testable; leave it. The brief also lists AC3.3.x as an empty-state
case — US3.3 has no empty-state criterion at all, which is a gap rather than a
vague criterion (see §6).

**AC7.1.4 — "in one action" and "renders current data on open"**. The first half
is testable only against a navigation model that does not exist yet; the second
half is the load-bearing one and is testable now. Split:

> **AC7.1.4** (replace) — Given outstanding balances exist, When I open the dues
> view, Then it returns current balances computed at request time, with no
> user-initiated generate, refresh or run step required. [FR7.3]
>
> **AC7.1.6** (new, deferrable) — Given the teacher's top-level navigation, Then
> the dues view is reachable from it directly. Reachability is specified at
> Functional Design. [FR7.3]

**AC8.1.3 — the collection rate** is nearly a formula and should be exactly one.
"Received divided by charged, excluding carried-forward amounts from both sides
and waived amounts from the denominator" is three exclusions in prose, and the
third is ambiguous: waived excluded from the denominator only, or from both? Under
the team's `charged - received - forgiven == outstanding` invariant, the intent
appears to be `received / (charged - carried_forward - forgiven)`. State it as an
expression, name the period basis, and add a worked example:

> **AC8.1.3** (replace) — Given a period, Then the collection rate is
> `received / (charged - carried_forward - forgiven)` for cycles whose period is
> that period, where `carried_forward` is the amount carried *into* a later
> period and `forgiven` is the waived amount. Worked case: charged 3000, received
> 1500, carried forward 500, forgiven 200 → `1500 / 2300`. [FR8.3]

Without the worked case this criterion cannot be turned into a failing test
without reading the implementation, which by the team's own rule makes the
criterion the defect.

**AC1.1.5 — "when the cooldown expires"** names a cooldown that no criterion
defines and no FR in this story cites. Either give it the number or cite the NFR
that holds it; an undefined threshold inside a criterion is the ambiguity rule's
exact target.

**AC1.6.1 — "per each table's recorded disposition"** is correctly cautious
(dispositions are decided at Domain Design) but as a *criterion* it is
untestable today and will be forgotten. Make the forward dependency explicit so
the test obligation survives:

> **AC1.6.1** (replace) — Given I request deletion and confirm, Then my account
> and private profile are removed, and for every table holding my data the
> outcome matches that table's written disposition, with no table lacking one.
> The disposition set is decided at Domain Design; this criterion is the test
> that every table has one and is honoured. [FR1.14] [FR11.1]

#### Deferrable — fine as story-level statements

AC1.7.2 ("names the app and developer" — a Play content requirement, verified
against the Data Safety form), AC2.1.3 (owner-entity indirection — a schema
assertion at Domain Design), AC4.3.2 ("without an attached identity" — testable
as a schema invariant once the marksheet response exists), AC3.5.2 and AC3.4.2
(straightforward reads), AC2.6.2's "all history still reachable". These are
genuinely awaiting a design, not vague. I would not touch them.

---

### 2. The test-first predicate

The predicate: write the failing test first when the correct output is knowable
from the requirement **and** a wrong answer is a money or authorization error.
Criteria meeting it, with a verdict on whether each is already a usable test
specification:

| Criterion | Predicate | Specification-grade? |
|---|---|---|
| AC2.1.2 (due-day clamp) | money | **Yes** — but needs the boundary table in §3 |
| AC2.4.1–2.4.4 (`inactive_from`) | money | **2.4.1 no** — "period beginning after that date" is ambiguous at the boundary |
| AC5.1.1 (charged = enrollment fee) | money | Yes |
| AC5.1.2–5.1.3 (idempotency) | money | **No** — see §5 |
| AC5.1.4 (inactive → no cycle) | money | Yes |
| AC5.2.1 (adjust, four-way ledger) | money | **No** — no arithmetic stated |
| AC6.1.4 (partial accepted) | money | Partly — no bounds |
| AC6.3.2–6.3.4 (approve/part/reject) | money | **No** — see §3 |
| AC8.1.3 (collection rate) | money | **No** — fixed above |
| AC1.2.2–1.2.3 (lens offered) | authorization | Yes, but only positively — see §4 |
| AC1.5.2 (profile invisible to teacher) | authorization | Partly — single-teacher only |
| AC2.8.1–2.8.2 (number-scoped guardian) | authorization | Yes — the best-written authz criteria here |
| AC4.2.2 (marksheet off) | authorization | Yes |
| AC4.3.2–4.3.3 (anonymised, batch-scoped) | authorization | Yes |

**AC2.4.1 is a boundary defect, not a wording nit.** "No fee cycle generates for
any period beginning after that date" leaves the period *containing* the date to
AC2.4.4, which is right, but says nothing about `inactive_from` landing exactly on
a period boundary — the 1st of a month. That is the single case a developer will
get wrong, and it is money. Replace with:

> **AC2.4.1** (replace) — Given I mark a student inactive from date D, Then no
> fee cycle generates for any period whose first day is on or after D, and the
> period containing D (where D is not its first day) generates in full per
> AC2.4.4. [FR2.11] [FR5.3]

**AC5.2.1 is the weakest money criterion in the draft.** "The balance
recalculates and the ledger records charged, received, carried forward and
forgiven separately" names four fields and zero arithmetic. The team's invariant
is stated in `team.md`; put it in the criterion so it is testable from the story:

> **AC5.2.1** (replace) — Given a fee cycle with charged C, received R and
> forgiven F, When I adjust the charged amount to C′, Then the ledger records C′,
> R and F unchanged, and the outstanding balance equals `C′ - R - F`. [FR5.1]
>
> **AC5.2.3** (new) — Given an adjustment that would make `charged - received -
> forgiven` negative, Then the outcome is defined by the overpayment rule
> (AC5.2.4) and the balance is never silently negative. [FR5.1]

---

### 3. Money-path criteria — the gaps

The practices demand a named test per fee-cycle and payment state transition plus
a documented boundary case per money input. Measuring the draft against that
list, these are missing. The brief asks specifically about three; all three are
absent, and I found four more.

**(a) Approved amount exceeding the claimed amount — absent.** AC6.3.2 covers
approving in full, AC6.3.3 approving less. Nothing covers approving *more*, and it
is not hypothetical: a guardian types 1000, actually paid 1500, and the teacher
approves what arrived. Unspecified, this either silently accepts (creating a
negative balance nothing handles) or throws an unclassified 500. It is named
explicitly in `team.md` as a required boundary case.

> **AC6.3.7** (new) — Given a submission claiming amount A, When I approve an
> amount greater than A, Then the request is refused as a `ValidationError` and
> no money is recorded; recording more than was claimed requires a new submission
> or a charge adjustment. [FR6.6] [FR5.1]

(The team may prefer "accepted and credited" over "refused" — but the criterion
must *state* which, and refusal is the safer default for a V1 ledger with one
reviewer.)

**(b) Zero-amount payment — absent.** No criterion bounds the submitted amount at
all. Zero, and negative, are both reachable from the client.

> **AC6.1.6** (new) — Given the payment form, When I submit an amount of zero or
> less, Then it is refused as a `ValidationError` and nothing is recorded.
> [FR6.1] [FR6.4]
>
> **AC6.1.7** (new) — Given the payment form, When I submit a non-numeric or
> malformed amount, or an amount with more than two decimal places, Then it is
> refused as a `ValidationError`. [FR5.7] [FR6.1]

**(c) Negative balance / overpayment — absent.** The team's property-based
invariant asserts `outstanding` never goes negative. No criterion says what
happens when an approval would drive it below zero, and this is the normal case
for a guardian paying two months at once.

> **AC5.2.4** (new) — Given an approved amount that exceeds the cycle's
> outstanding balance, Then the outstanding balance for that cycle becomes zero
> and the excess is recorded as a credit carried to the next cycle; the
> outstanding balance is never negative. [FR5.1] [FR6.8]

This one is a genuine **product** question, not only a test gap: there may be no
credit concept in the model at all. If the answer is "the excess is refused", say
so. But silence here will ship as a negative number on a guardian's screen.

**(d) Due-day clamp boundaries — under-specified.** AC2.1.2 states the clamp but
names no cases. The team requires a documented boundary case per money input.

> **AC2.1.4** (new) — Given a fee due day of 31, Then the due date is 28 February
> in a common year, 29 February in a leap year, 30 April, and 31 May. Given a due
> day of 30, Then February clamps to 28 or 29. Given a due day of 1 to 28, Then
> no clamping occurs in any month. [FR5.2]

**(e) Rounding at the half — absent entirely.** `ROUND_HALF_UP` is an affirmed,
expensive-to-change decision and no criterion exercises it. It will be exercised
the first time a per-enrollment fee is set to an odd amount and a rate is applied.

> **AC5.1.6** (new) — Given a money computation whose exact result falls on a
> half-paisa, Then it rounds half away from zero (`ROUND_HALF_UP`), so 10.005
> becomes 10.01 and never 10.00. [FR5.7]

**(f) Carry-forward versus waive is stated as a choice but never as arithmetic.**
AC6.3.3 says the teacher chooses; nothing says what each branch does to the
ledger. This is the exact fork the practices call out as the one an 80% line floor
leaves unexecuted.

> **AC6.3.8** (new) — Given a claim of A approved at B where B < A, When I carry
> the remainder forward, Then `received` increases by B, `forgiven` is unchanged,
> and the unpaid remainder of the original charge appears in the next period's
> outstanding balance. When I waive it instead, Then `received` increases by B,
> `forgiven` increases by the remainder of the *charge*, and nothing carries to
> the next period. [FR6.6] [FR6.8] [FR5.1]

Note the subtlety the draft's wording obscures: "the remainder" in AC6.3.3 could
mean `A - B` (claimed minus approved) or `charged - B`. Those differ whenever the
claim is not equal to the charge, which is common. The criterion must pick one;
I have written it as `charged - B`, since the claim is an assertion and the charge
is the obligation.

**(g) Partial payment has no upper bound criterion.** AC6.1.4 covers "less than
the balance". Nothing covers equal to, or greater than — the latter now handled by
AC5.2.4 above, but the "exactly equal closes the cycle" transition is a named
state transition with no criterion:

> **AC6.1.8** (new) — Given an approved amount exactly equal to the outstanding
> balance, Then the cycle's status becomes paid and its outstanding balance is
> zero. [FR5.8] [FR6.4]

Finally, **AC5.3.1's three-value status (`paid | partly paid | unpaid`) has no
definition**, and under [TC-9] the server owns it. A test needs the predicate:

> **AC5.3.3** (new) — Given a fee cycle, Then the server supplies its status as
> exactly one of `paid` (outstanding is zero), `partial` (received is greater
> than zero and outstanding is greater than zero) or `unpaid` (received is zero
> and outstanding is greater than zero); the client never derives status from an
> amount comparison. [FR5.8] [TC-9]

---

### 4. Authorization criteria — the happy path only

This is the draft's largest structural gap. Every authorization criterion is
written from the actor's own view: what the actor *sees*. Not one asks what
happens when an actor requests something that is not theirs. The practices name
the three IDOR probes required, and **none of the three appears anywhere in the
stories**.

The counter-argument — that this is covered by a schema-wide test at Construction
and does not belong in stories — is wrong for one specific reason. The team's
privacy suite is a *schema-wide invariant plus adversarial probes*, and the probe
half requires knowing the intended policy. The intended policy is what a user
story is for. If the stories never state "teacher A gets 403 on teacher B's
batch", the probe suite is written from the implementer's guess at the policy,
which is precisely the vulnerability class the practices say a scanner cannot
find.

Add one story. It is a legitimate story — the actor is any authenticated account,
the action is requesting a record, the value is that the privacy boundary holds —
and it is the one story whose criteria are a direct test specification.

> ### US10.1 — The privacy boundary refuses a request outside the lens
>
> As **any signed-in account**, I want a request for a record that is not mine to
> be refused, so that nobody can read another family's data by changing an id.
>
> - **AC10.1.1** — Given I am teacher A and teacher B owns batch X, When I
>   request batch X or any session, exam, enrollment, fee cycle or payment under
>   it, Then it is refused as an `AuthorizationError` and no field of it is
>   returned. [TC-11] [TC-13] [FR2.2]
> - **AC10.1.2** — Given I am a guardian whose number reaches child C, When I
>   request an enrollment belonging to a child my number does not reach, Then it
>   is refused as an `AuthorizationError`. [FR2.7] [FR2.18]
> - **AC10.1.3** — Given I am a student, When I request a fee cycle belonging to
>   another enrollment, Then it is refused as an `AuthorizationError`. [FR5.8]
> - **AC10.1.4** — Given any teacher-facing response, Then it carries no field
>   from the owner-private profile set, for every endpoint without exception.
>   [TC-13] [FR9.4] [FR1.12]
> - **AC10.1.5** — Given a client-supplied lens hint naming a lens I do not hold,
>   When I make any request, Then the hint is ignored for authorization and the
>   server resolves my lens from owned batches and enrollments. [TC-11] [D-2]
> - **AC10.1.6** — Given a refusal under AC10.1.1 to AC10.1.3, Then the response
>   does not reveal whether the requested record exists. [TC-13]
> - **AC10.1.7** — Given any endpoint other than OTP issue, OTP verify, health
>   and the external deletion route, Then it resolves a lens; an endpoint that
>   resolves none is a defect. [TC-11]

AC10.1.6 is worth arguing for specifically: existence disclosure is the half of
IDOR that survives a correct 403, and nothing in the draft forbids it.

Two existing criteria also need adversarial counterparts:

**AC1.5.2** proves a teacher sees their typed name rather than the profile name,
which is the *positive* framing. The negative is the one that matters and it is
stronger as a schema invariant — covered by AC10.1.4 above. Keep AC1.5.2, but it
does not discharge the privacy obligation and the draft's INVEST table should not
imply it does.

**AC4.2.2** ("no marksheet is shown at all") is client-side language for a
server-side rule. Restate:

> **AC4.2.2** (replace) — Given marksheet visibility is off for a batch, When a
> student or guardian requests that batch's marksheet, Then the request is
> refused and no mark for any student is returned in any response for that batch.
> [FR4.6]

---

### 5. Idempotency — AC5.1.2 is the defect the practices warn about

**AC5.1.2 as written specifies sequential.** "Given generation runs twice for the
same period" is two runs in order. That is exactly the test `team.md` says passes
against the broken implementation the database constraint exists to prevent: an
application-level "has this already run?" guard satisfies AC5.1.2 completely and
fails under two Uvicorn workers. The project rule is explicit — *ALWAYS test
fee-cycle generation idempotency with overlapping concurrent generations, never
with sequential calls* — and the criterion as drafted authorizes the forbidden
test. This is the single highest-value fix in my review.

> **AC5.1.2** (replace) — Given N overlapping concurrent generation runs for the
> same period, Then exactly one fee cycle exists per `(enrollment, period)` and
> the ledger total is unchanged from a single run; no run raises an unhandled
> error. [FR5.4] [TC-12] [D-21]
>
> **AC5.1.7** (new) — Given a fee cycle already generated for a period, When
> generation runs again on a later day, Then no second cycle is created for that
> period. [FR5.5]

AC5.1.3 is adequate for the self-healing *forward* case (a missed day catching
up) and I would keep it, but it conflates two things — the missing cycle appearing
and no duplicate being created. AC5.1.7 above isolates the across-days
idempotency case that `team.md` names separately, because concurrency alone misses
it.

One more, because the constraint is the mechanism and the criterion should say so:

> **AC5.1.8** (new) — Given generation encounters an existing
> `(enrollment, period)` row, Then the conflict is the success path and is not
> surfaced as an error. [D-21]

---

### 6. Missing negative criteria

The absence-assertion approach is **right**, and I want to be clear that I
support it: an unstated absence does get implemented as its opposite, and
AC3.1.4 in particular is a good piece of work — it prevents a developer inventing
a latency budget the requirements deliberately dropped. Two notes on the
existing three, then where else the approach is needed.

- **AC5.1.5** is not an absence-assertion; it is a positive type assertion
  ("money crosses the API as a string"). The draft's INVEST table miscounts it.
  Its true negative half is missing and matters on both surfaces:

  > **AC5.1.9** (new) — Given any money field in any response, Then the client
  > rejects a JSON number for it with a loud failure rather than coercing it.
  > [FR5.7] [TC-7]

- **AC3.1.4** is good but should name what it excludes, or it will be read as
  licence to be slow: "no criterion here constrains marking latency; the
  mid-class speed concern is carried as a manual pilot check, not an automated
  obligation [Q14.3]".

Where else a negative criterion is needed:

| Story | Missing negative |
|---|---|
| US1.1 | **The OTP rate limits.** Seven abuse controls are in the walking skeleton with numeric thresholds, and only two (5-minute expiry, 5 attempts) appear as criteria. Per-number per-hour, per-number per-day, per-IP, single-use-after-verify, hashed-at-rest, and identical responses for known and unknown numbers have no criterion at all. These are *money* (per-SMS billing) and have knowable outputs, so they meet the test-first predicate and belong in a story. |
| US1.2 | **A number that reaches nothing.** Signing in with a number no teacher recorded — no lens, and what the user sees. Currently undefined. |
| US1.4 | **Declining the warning.** AC1.4.1 warns, AC1.4.2 proceeds. Nothing says what happens when the teacher cancels: no enrollment created, no lens granted. |
| US2.5 | **Dormant-with-history.** AC2.5.1 requires dormant *and* no history; AC2.5.2 refuses with history. The claimed-but-no-history case is unstated and is reachable. |
| US3.2 | **Attendance already recorded, then cancelled.** AC3.2.2 forbids recording against a cancelled session but says nothing about attendance recorded *before* cancellation. Money-adjacent only indirectly, but it is a real state transition with no criterion. |
| US3.3 | **No announcements.** Empty state absent, per the brief's AC3.3.x note. Also: a deleted announcement must not be recoverable by a student who already fetched it on a later fetch. |
| US6.3 | **Double verification.** Approving a submission that is already approved or rejected. This is a `ConflictError` by the team's taxonomy and is the classic double-credit path. |
| US1.6 | **No new session after deletion.** Deletion must invalidate the refresh-token family, or a 30-day refresh token outlives the deleted account. |

For US1.1 I would add one consolidated criterion rather than seven, to keep the
story small while making the obligation explicit and traceable:

> **AC1.1.7** (new) — Given the OTP abuse controls, Then each of the seven stated
> thresholds refuses at its boundary: the 4th request for one number within an
> hour, the 6th within a day, the 11th from one IP within an hour, a code
> presented after 5 minutes, a 2nd verification of an already-verified code, the
> 6th wrong attempt against one code, and a request beyond the global daily SMS
> ceiling. Each refusal is observable and none reveals whether the number exists.
> [NFR12] [D-33]

> **AC1.1.8** (new) — Given a code was issued, Then the stored value is not equal
> to the transmitted value, and the transmitted value appears in no log line.
> [D-33]

---

### 7. Whole test classes missing

All four candidates in the brief are real gaps. Taking them in order of cost:

**(a) The four mark states [FR4.3] — partly covered, incompletely.** FR4.3
defines four states: numeric mark, Absent, not yet entered, joined after the exam.
AC4.1.3 covers Absent-versus-zero, AC4.1.4 not-entered, AC4.1.5 joined-later. What
is missing is the **four-way distinctness assertion itself** — that the four are
distinct values in the response, not three flags and a null. A null doing double
duty for "not entered" and "not applicable" is the obvious implementation and it
satisfies every current criterion.

> **AC4.1.6** (new) — Given a marksheet, Then each result carries exactly one of
> four distinct states — a numeric mark (including zero), `absent`,
> `not_entered`, or `not_applicable` — represented as distinct values, never as a
> null shared between two states. [FR4.3]

**(b) The dormant-to-claimed transition — missing.** AC1.2.1 covers claiming;
AC1.3.1 covers staying dormant. Neither covers the *transition's* effect on
existing records: the attendance, marks and fee history written while the record
was dormant must all become visible on claim, and the teacher's view must not
change. This is both a privacy and a continuity assertion.

> **AC1.2.5** (new) — Given a dormant enrollment with existing attendance, marks
> and fee cycles, When the number signs in and claims it, Then all of that
> history becomes visible under the appropriate lens, and nothing the teacher
> sees changes. [FR1.8] [FR1.9]
>
> **AC1.2.6** (new) — Given an enrollment claimed and then deleted per AC1.6.2,
> When the same number signs in again, Then it re-claims the same enrollment and
> its history, and no duplicate enrollment is created. [FR11.1]

AC1.2.6 is the one I would push hardest for after the IDOR story and the
concurrency fix. AC1.6.2 says the enrollment reverts to dormant, which implies
re-claimable, and nothing tests the round trip. Delete-then-rejoin is a normal
user path and an unexercised one.

**(c) Correction history visibility to both parties — under-tested.** FR9.2 is
emphatic: never hidden from either party. FR9.3 scopes it to exactly three record
types; FR9.4 forbids extending it to student- or guardian-authored content. The
draft has AC5.2.2, AC6.3.6 and AC6.4.3 — three criteria covering two of the three
record types from assorted angles. **Exam marks, the third record type, have no
correction-history criterion at all**, and FR9.4's prohibition — the privacy half —
has none either.

> **AC4.1.7** (new) — Given I correct an entered mark, Then the previous value and
> that I changed it are retained and visible to me and to that student and
> guardian. [FR9.1] [FR9.2] [FR9.3]
>
> **AC10.1.8** (new) — Given a student or guardian edits a payment submission, a
> hidden-batch preference or their private profile, Then no edit history of it is
> retained or exposed to any teacher. [FR9.4] [TC-13]

**(d) Deletion asserting what the Data Safety form claims — missing, and
release-blocking.** This is the gap with the hardest external deadline. Both
deletion paths exist as stories (US1.6, US1.7) and both are release-blocking V1
deliverables by project rule, with a mandated test *per path* asserting that
deletion removes what the form claims and retains only what the policy discloses.
No criterion makes that assertion. AC1.6.1's "per each table's recorded
disposition" is adjacent but points at a document that does not exist yet.

> **AC1.6.4** (new) — Given my account is deleted by either path, Then for every
> data class the Data Safety form declares as deleted, no row identifying me
> remains; and for every data class the privacy policy declares as retained,
> exactly that data remains and nothing more. [TC-19] [RC-4] [RC-5]

That criterion is deliberately written against the two published documents rather
than against the schema, because that is the comparison a Play reviewer makes and
the one nobody runs. It also makes the privacy policy and the Data Safety form
*inputs to a test*, which is what the team's "privacy policy generated from the
dispositions" practice requires.

A fifth class the brief does not list but which I would add:

**(e) The lens-switching state machine.** AC1.2.4 and AC2.7.4 both say the view
changes "without re-authenticating". Neither says what must *not* leak across the
switch: data fetched under lens A must not remain visible under lens B. For an
account that is simultaneously a teacher and a guardian — explicitly normal
[FR1.6] — this is an authorization boundary inside one session, and the obvious
implementation (one cache keyed by resource id) breaks it.

> **AC1.2.7** (new) — Given I hold two lenses and have viewed data under the
> first, When I switch to the second, Then no record visible only under the first
> remains visible or cached in the second's views. [FR1.5] [TC-11]

---

### Summary of proposed changes

| Kind | Count | IDs |
|---|---|---|
| Replace (vague or wrong) | 9 | AC1.3.3, AC2.3.1, AC2.4.1, AC3.4.3, AC4.2.2, AC5.1.2, AC5.2.1, AC7.1.4, AC7.1.5, AC8.1.3 (and AC8.1.6 by analogy) |
| New — money | 11 | AC2.1.4, AC5.1.6, AC5.1.7, AC5.1.8, AC5.1.9, AC5.2.3, AC5.2.4, AC5.3.3, AC6.1.6, AC6.1.7, AC6.1.8, AC6.3.7, AC6.3.8 |
| New — authorization | 10 | US10.1 (AC10.1.1–10.1.8), AC1.2.7 |
| New — other classes | 8 | AC1.1.7, AC1.1.8, AC1.2.5, AC1.2.6, AC1.6.4, AC2.3.3, AC4.1.6, AC4.1.7, AC7.1.6 |

The three I would not ship without: **AC5.1.2 rewritten to concurrent**, **US10.1
added**, and **AC6.3.7 plus AC5.2.4** (the two overpayment boundaries). The rest
improve the artifact; those four prevent a defect the practices explicitly
predict.

## Positions

- AGREE: One story per actor [Q2] — it keeps the authorization boundary visible as a story-level concern rather than burying it inside a teacher story.
- AGREE: The deliberate absence-assertion technique (AC1.3.3, AC3.1.4) is right and AC3.1.4 in particular prevents a developer inventing a dropped latency budget.
- AGREE: Treating NFRs as deferred to NFR Requirements while surfacing three inside criteria where they are user-visible — that is coverage of behaviour, correctly labelled as such.
- AGREE: US8.1 is too large at six criteria across four views and should be split, as the draft itself flags.
- OBJECT: AC5.1.2 specifies sequential generation, which is the exact test the project rule forbids and which passes against the application-level guard the database constraint exists to replace — it must say overlapping concurrent runs.
- OBJECT: No criterion anywhere covers the three mandated IDOR probes, so the adversarial privacy suite would be written from the implementer's guess at the intended policy; US10.1 as drafted above fills it.
- OBJECT: Three money boundaries required by the affirmed practices are entirely absent — approved amount exceeding claimed, zero or negative submitted amount, and overpayment driving a negative balance — and the last is a product question, not only a test gap.
- OBJECT: AC5.2.1 names four ledger fields and no arithmetic, so it cannot be turned into a failing test without reading the implementation, which by the team's own rule makes the criterion the defect.
- OBJECT: AC2.3.1's "immediately" is either an uncommitted latency claim or a cache statement; as written a 60-second client TTL satisfies it.
- OBJECT: AC1.3.3's "not visually distinguished" is a negative over an unbounded set and unfalsifiable; the API-field form is checkable and keeps the design choice intact.
- OBJECT: "A defined empty state" (AC7.1.5, AC8.1.6) defers the criterion to a definition that does not exist; the testable content is empty-versus-error-versus-loading.
- OBJECT: AC8.1.3's collection-rate formula is ambiguous about whether waived amounts leave one side or both, and needs an expression plus a worked case.
- OBJECT: AC6.3.3's "the remainder" is ambiguous between claimed-minus-approved and charged-minus-approved, which differ whenever the claim is not equal to the charge.
- OBJECT: The seven OTP abuse controls are walking-skeleton obligations with numeric thresholds, and only two appear as criteria.
- OBJECT: Exam marks are one of FR9.3's three correction-history record types and have no correction criterion, and FR9.4's prohibition on exposing student-authored edit history has none either.
- OBJECT: Both deletion paths are release-blocking with a mandated test against the Data Safety form and privacy policy, and no criterion makes that assertion.
- OBJECT: AC5.1.5 is counted as an absence-assertion in the INVEST table but is a positive type assertion; its client-side negative half (reject a JSON number loudly) is missing.
