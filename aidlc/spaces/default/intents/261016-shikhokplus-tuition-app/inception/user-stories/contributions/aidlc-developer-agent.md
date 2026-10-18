**Collaborator:** aidlc-developer-agent

## Contribution

Remit: implementability and story sizing. The draft is strong on behavioural
coverage and on actor separation. The weaknesses that remain are (a) three
stories that are not one sitting of work, (b) eight FRs with no criterion
anywhere, (c) four criteria that cannot be implemented as written, and (d) one
dependency edge that is drawn wrong. Addressed in the order the brief asks.

---

### 1. Sizing

Criterion count is the wrong sizing proxy and it is what the INVEST table uses.
US1.1 has six criteria and is roughly four days of work; US3.3 has four and is
half a day. The right proxy for this backlog is **how many architectural
surfaces a story forces into existence for the first time**. On that measure:

**Too large to deliver in a sitting — split.**

- **US8.1 — confirmed, split into four.** The lead's instinct is right but the
  reason given ("four distinct views") understates it. AC8.1.3 is not a view, it
  is a money-module aggregation with a specified exclusion rule (carried-forward
  out of both sides, waived out of the denominator) that needs its own test
  matrix; AC8.1.5 is a cross-batch exam query with a whole-days calendar
  computation in a non-UTC timezone. Those two share no code with AC8.1.1. Split:

  - **US8.1 — Teacher sees this month's receipts.** AC8.1.1.
  - **US8.2 — Teacher sees the earnings trend.** AC8.1.2.
  - **US8.3 — Teacher sees the collection rate.** AC8.1.3, AC8.1.4.
  - **US8.4 — Teacher sees the next exam.** AC8.1.5, AC8.1.6.

  Renumber the existing US8.1 criteria into the new stories rather than
  reindexing them, so `AC8.1.3` becomes `AC8.3.1` — the keys are declared
  permanent, so if the lead would rather not move them, keep the old IDs inside
  the new stories and note the remap. Either is fine; silently reusing `AC8.1.3`
  for a different story is not.

- **US1.1 — split the OTP lifecycle out from sign-in.** Six criteria, but the
  real objection is that AC1.1.3, AC1.1.4 and AC1.1.5 are the *adversarial* half
  of the auth surface — expiry, attempt exhaustion, delivery failure and
  cooldown — and each needs datastore-backed counters per the affirmed skeleton
  practice. That is a different day's work from "a number reaches the issue
  endpoint and a token comes back". Proposed split:

  - **US1.1 — Teacher signs in with a phone number and a code.** AC1.1.1,
    AC1.1.2, AC1.1.6.
  - **US1.8 — The code cannot be abused.** AC1.1.3, AC1.1.4, AC1.1.5 plus the
    new criteria in §3 below.

  This is not padding: it makes the abuse surface a reviewable story the human
  gates, rather than three criteria buried in a happy-path story. Given the money
  exposure in §3 that matters.

- **US6.3 — borderline, split if Delivery Planning needs a smaller unit.** Six
  criteria, and AC6.3.3 (partial approval with a carry-forward-or-waive fork) and
  AC6.3.6 (verification correction history) are each a money state transition
  with a mandated test. If it stays one story, it is the largest money story in
  the backlog and should be flagged as such. My preference is to lift AC6.3.6
  into its own story — **US6.5 — Teacher corrects a verification they got
  wrong** — because correction history is a distinct mechanism (FR9.1–FR9.3)
  shared with US5.2 and with marks, and implementing it inside the
  approve/reject story invites three independent implementations of one
  mechanism.

**Too small — merge.**

- **US6.2 is not a story.** A single criterion whose whole content is "identical
  to the guardian's" has no independent test and no independent implementation;
  it is one line in US6.1. The one-story-per-actor rule from [Q2] is the reason
  it exists, and this is the case where that rule produces a non-story. Merge it
  into US6.1 as `AC6.1.6 — Given I am a student rather than a guardian, When I
  submit a payment, Then the form, validation and confirmation are the same, and
  the submission is attributed to my account.` The attribution clause is the only
  part that is actually different and it is currently unstated anywhere.

- **US3.5 is almost entirely US3.4.** AC3.5.1 (attendance per session) is
  genuinely guardian-only — a student seeing their own attendance is nowhere in
  the draft, which is a gap, see §4 — but AC3.5.2 duplicates AC3.4.2 exactly.
  Keep US3.5 for the attendance criterion, drop AC3.5.2, and add the missing
  student-attendance criterion to US3.4.

- **US4.2 (two criteria, a boolean toggle)** is small but it is a distinct
  teacher-controlled policy with a privacy consequence. Leave it.

---

### 2. Hidden implementation cost

The four the brief names, plus three it does not.

- **US1.2 — the largest hidden cost in the backlog, and it is understated by
  its four criteria.** AC1.2.2 ("both lenses are offered") requires the whole
  lens machinery: the `Lens` type hierarchy, the FastAPI dependency that returns
  the scoping value rather than guarding, the request-scoped memo, the
  route-enumeration test with its `PUBLIC_ROUTES` frozenset, and
  response-schema-per-lens parameterization. That is the single most structurally
  unusual decision in the system [D-2, TC-11] and all of it lands behind one
  criterion. It also silently requires the *dormant-record claim* transition
  (AC1.2.1) which is a write path on the identity table that nothing else
  exercises. **Recommendation**: leave the story whole but add an implementation
  note to the story — not a criterion — stating that this story establishes the
  lens mechanism and that the route-enumeration test ships with it. Delivery
  Planning will otherwise size it off the four criteria.

- **US2.7/US2.8 — the guardian multi-number model.** Confirmed as understated,
  but for a reason the lead has not named. AC2.8.2 ("the child appears once, not
  twice") requires deduplicating *student accounts* reachable from the
  authenticated guardian number across enrollments recorded by different
  teachers — which is FR2.14's resolution set, and FR2.14 is cited nowhere (§4).
  That resolution is a join over `enrollment.guardian_phone -> student_account`
  with a distinct on the student side, and it is the query the guardian lens is
  built on. It also interacts with the open teacher-vs-teacher privacy question
  the requirements hand to Domain Design: a guardian lens resolved across two
  teachers' enrollments is exactly the edge that question is about. **Add to the
  Assumptions section**: US2.7/US2.8 cannot be fully specified until the
  teacher-vs-teacher boundary question is answered at Domain Design, and the
  stories are written against the current reading.

- **US5.1 — correctly identified as the highest risk per criterion, and
  under-criteria'd.** AC5.1.2 and AC5.1.3 together are the whole idempotency
  guarantee, and the affirmed practice requires a *concurrent* test with
  overlapping generations plus a *cross-day* test, enforced by a database unique
  constraint and `ON CONFLICT DO NOTHING`, never an application guard. The
  criteria as written ("generation runs twice") would be satisfied by the
  sequential test the practice explicitly forbids. Fix the criteria so the
  acceptance criterion cannot be discharged by the wrong test — see §5. Also
  hidden: AC5.1.1 needs the period-boundary clamp (AC2.1.2's due-day clamp
  applied at generation time), and the money module with its `ROUND_HALF_UP`
  constant and 2dp quantization must exist before this story can produce a
  charged amount at all.

- **US7.1 — confirmed, and the hidden cost is an index, not a query.** The dues
  view is balance-driven not active-driven [FR7.2], so it cannot use the
  `inactive_from` predicate that every other enrollment query uses; it needs an
  aggregate over the fee ledger per enrollment across all of one owner's
  batches, with `Money.sum` and a zero identity, filtered on positive balance.
  AC7.1.4 says it "renders current data on open with no generate step", which
  on a 2 GB single instance means this is the one query that needs a partial
  index and a stated cost. Not a reason to split the story; a reason to note
  that it carries a performance obligation none of the other read stories do.

Three the brief does not name:

- **US1.6/US1.7 — account deletion is the most under-criteria'd work in the
  backlog.** Three criteria for US1.6, two for US1.7, and between them they
  require: a written disposition per table (hard delete / anonymize-in-place /
  retain-with-stated-basis) decided at Domain Design, a test per path asserting
  that deletion removes what the Data Safety form claims, an unauthenticated web
  surface that does not exist in the approved architecture (TC-19 is flagged as
  uncosted), and OTP-based ownership verification on that web surface — which
  means the rate-limit and abuse controls apply to a second entry point. AC1.7.1
  says "deletion proceeds identically", which hides an entire second ownership-
  verification flow. **Add a criterion**: `AC1.7.3 — Given the external route,
  When I request deletion, Then ownership of the number is verified by the same
  one-time-code mechanism, subject to the same abuse controls as sign-in.
  [FR1.15] [NFR12]`

- **US2.4 — `inactive_from` is three money-adjacent behaviours that fail
  quietly**, and the affirmed Testing Posture names it explicitly as a test-first
  case. Four criteria is right; the hidden cost is that AC2.4.1's "no fee cycle
  generates for any period beginning after that date" is a predicate inside the
  generation job that US5.1 builds, so US2.4 cannot be fully verified until US5
  exists. That is a real forward dependency — see §7.

- **US1.5 — profile is where row-level security first appears.** AC1.5.2 is the
  privacy boundary: a teacher viewing a roster must see the typed display name
  and not the self-entered one. The affirmed practice enforces that structurally
  in three layers (separate tables by writer, RLS on `profile`, teacher-facing
  schemas with no profile fields) and requires the test suite to connect as a
  restricted non-superuser role with a meta-test. One criterion, an entire
  structural mechanism. Add the implementation note.

---

### 3. The walking skeleton gap — this is a real gap, not correctly deferred

**I disagree with deferring it, and the argument against deferral is stronger
than the one for it.**

The case for deferral is coherent: a story states observable behaviour from an
actor's point of view, a Bolt definition states the engineering content of a
delivery unit, and "JWT `kid` support with two verification keys" is not
something a teacher wants. Taken alone that reasoning is correct, and it is why
I am not asking for a story called "As a developer I want key rotation".

It fails here for three specific reasons.

**First, three of the seven abuse controls are plainly user-observable and
therefore belong in criteria under this draft's own rules.** The per-number
3/hour and 5/day limits, the per-IP 10/hour limit, and the global ceiling with
its sub-ceilings all change what a real user sees: a teacher who requests a
fourth code within an hour is refused, and a legitimate teacher hitting the
sub-ceiling sees something. The affirmed practice explicitly says the global
ceiling needs a tier beneath it precisely so a financial attack does not
"cliff-edge" into a total lockout, and that it must be defined "what a
legitimate user sees when it trips and whether any path to log in remains."
**That is an acceptance criterion with no home.** It is user-visible behaviour,
it is specified, and it appears nowhere in the draft. Deferring it to the Bolt
means the Bolt invents the degraded-mode UX, which is exactly the decision a
story is for.

**Second, the draft already set the precedent and cannot now claim the line is
principled.** AC1.1.3 (5-minute expiry) and AC1.1.4 (5 verify attempts) are two
of the seven controls, already written as criteria. AC1.1.6 asserts the absence
of a SIM read, which is a pure implementation constraint with no user-observable
behaviour at all. So the draft has already admitted both implementation
constraints and abuse controls into criteria. Including two of seven and
excluding five is not a drawn line, it is an omission.

**Third, the cost of being wrong is asymmetric and lands on the wallet.**
Per-SMS billing makes an unprotected issue endpoint a direct attack on the
project's budget against a USD 50/month ceiling. The skeleton is gated by the
human at a checkpoint; what the human reviews at that checkpoint is the stories.
Controls that exist only in a Bolt definition are controls the gate does not see.

**What I would and would not add.** Split by observability:

Belongs in criteria — add to the proposed **US1.8 — The code cannot be
abused**:

- `AC1.8.1 — Given I have requested three codes for my number within an hour, When I request a fourth, Then it is refused and I am told when I may try again. [NFR12]`
- `AC1.8.2 — Given I have requested five codes for my number within a day, When I request a sixth, Then it is refused. [NFR12]`
- `AC1.8.3 — Given ten code requests from one IP within an hour, When an eleventh arrives, Then it is refused. [NFR12]`
- `AC1.8.4 — Given the global daily SMS ceiling is reached, When I request a code, Then I am refused with a message distinguishing a service-wide limit from a wrong number, and a defined path to sign in later is stated. [NFR12] [team: Walking Skeleton]`
- `AC1.8.5 — Given a number that has no account, When a code is requested for it, Then the response is indistinguishable from the response for a known number. [NFR12] [project: NEVER return a response or timing that reveals whether a phone number exists]`
- `AC1.8.6 — Given a rate limit applies, When the backend runs with more than one worker process, Then the limit still holds, because the counter is datastore-backed and not per-process. [NFR12] [team: Walking Skeleton]`

AC1.8.6 is an implementation constraint, and I am proposing it deliberately for
the same reason the lead proposed AC1.1.6: the per-process dictionary is the
obvious implementation, it passes every behavioural test, and it stops working
silently at two workers. The affirmed practice calls that out as a correctness
bug presenting as "the limit works in testing". A criterion is the cheapest place
to stop it.

Does **not** belong in a story, and the lead is right to leave it to the Bolt:

- OTP hashing (the stored value differing from the transmitted one) — it has no
  observable behaviour; AC1.8.5 covers the only user-facing consequence.
- JWT `kid` and two verification keys — purely an operational-readiness property.
- The Alembic-from-zero migration against real Postgres — a test-harness
  property, not behaviour.

One that is neither and needs a home: **both language bundles on screen one**
[NFR3, TC-15, D-43]. It is user-visible, it is mandated, it is skeleton-scoped,
and it appears in no criterion. [Q4] deferred all NFR *stories* to stage 3.2,
which the lead followed correctly — but the draft then admitted NFR4, NFR5 and
NFR13 into criteria where user-visible, so NFR3 on the first screen is the same
case. Add to US1.1:

- `AC1.1.7 — Given my device locale is Bangla, When I open the sign-in screen, Then every string on it is Bangla, and the layout holds at the longest Bangla string; given any other locale, Then it falls back to English. [NFR3]`

**Net position**: the five observable abuse criteria plus the localization
criterion are a genuine gap in the stories. The three non-observable items are
correctly left to the Bolt. The lead should also add one line to the Assumptions
section recording that the skeleton's non-observable obligations live in the Bolt
definition by design, so a reader does not read their absence as an oversight.

---

### 4. FRs with no story coverage

I extracted every `FR{n}.{m}` cited in `stories.md` and diffed it against the 84
in `requirements.md`. **Eight FRs are cited nowhere.** Taking the six the brief
names first:

- **FR1.3 (no role field; lenses resolved per request) — genuinely uncovered,
  and it is the single most important uncovered requirement.** AC1.2.2 and
  AC1.2.3 cover *which* lenses are offered; nothing states that the role is
  computed rather than stored. That is the project's most-mandated rule
  ("ALWAYS compute role as a per-request lens... no role field on the account and
  no cached role") and the one most likely to be mis-implemented quietly as a
  cached role, because a cached role behaves identically on every happy path.
  **Add to US1.2:**
  `AC1.2.5 — Given my enrollments change — a teacher enrolls me, or marks me inactive — When I make my next request without signing out, Then the lenses available to me reflect the change, because the lens is computed from current data on each request and never stored or cached on my account. [FR1.3] [TC-11] [D-2]`
  That phrasing is observable (behaviour differs between computed and cached) and
  therefore testable, which "no role field" alone is not.

- **FR2.2 (owner indirection) — covered, at AC2.1.3.** It is an implementation
  constraint with no observable behaviour, exactly like AC1.1.6, and I would keep
  it for the same reason: a batch owned directly by an account is cheap now and a
  migration later. No change.

- **FR9.4 (the privacy fence on correction history) — uncovered, and this is a
  dangerous omission.** AC5.2.2, AC6.3.6 and AC6.4.3 all make correction history
  *visible to the student and guardian*, which is FR9.2. Nothing anywhere states
  the converse fence: that correction history never applies to student- or
  guardian-authored content, and specifically that a teacher never sees the edit
  history of a payment claim, a hidden-batch preference or a private profile. An
  implementer building "correction history" as a generic mechanism will attach it
  to every mutable record, which is the natural and wrong implementation, and it
  breaches a `NEVER` rule. **Add to US6.3:**
  `AC6.3.7 — Given a guardian or student edited or resubmitted anything — a payment claim, a hidden-batch preference, a profile — When I view the record, Then I see no edit history for it, because correction history applies only to records I authored. [FR9.4] [project: NEVER expose anything a student or guardian writes to any teacher]`

- **FR11.3 (idempotent deletion) — covered at AC1.6.3.** But it is covered only
  for the in-app path. Add to US1.7:
  `AC1.7.4 — Given my account is already deleted, When a second request arrives through the external route, Then it succeeds without error and reveals nothing about whether an account ever existed. [FR11.3] [FR1.15]`
  The non-disclosure clause matters: an unauthenticated route that answers
  "no such account" differently from "deleted" is a phone-number enumeration
  oracle, and that is the same attack AC1.8.5 closes on the issue endpoint.

- **FR11.4 (concurrent edits) — uncovered, and I disagree with the lead's
  reasoning for leaving it uncovered.** The Assumptions entry says writing it as
  a story "would require describing a race the teacher cannot observe." The
  teacher *can* observe the outcome: they edit a mark on their phone, their
  tablet had it open, and one of the two values wins. Last-write-wins per field
  is a deliberate decision with observable consequences, and leaving it out of
  the stories means the implementer either invents optimistic-concurrency
  rejection (a 409 nobody specified, and the error taxonomy has a `ConflictError`
  class sitting right there inviting it) or implements whole-row overwrite rather
  than per-field. Both are plausible wrong implementations. **Add to US2.3** (the
  natural home — it is the edit story):
  `AC2.3.3 — Given I have the same batch open on two devices and edit a different field on each, When both writes land, Then both changes survive, because the last write wins per field rather than per record. [FR11.4]`
  `AC2.3.4 — Given I edit the same field on two devices, When both writes land, Then the later write wins without a conflict prompt, and the correction history records both changes with their actor and time. [FR11.4] [FR9.2]`
  This is one of the cheapest criteria in the backlog to write and one of the
  most expensive to discover wrong.

- **NFR16 (API versioning / additive endpoints) — uncovered, and correctly so,
  with one reservation.** [Q4] defers all NFRs to stage 3.2 and NFR16 has no
  user-observable behaviour in V1 — there is no second version yet to be
  compatible with. I would not add a criterion. I *would* have the lead note it
  in Assumptions, because the consequence is a Bolt-time obligation (the
  committed OpenAPI schema and the schema-diff gate) that nothing in the stories
  implies, and "the app handles unknown fields rather than failing to parse" is a
  client decoding property that the first Android Bolt either builds in or does
  not.

The two the brief does not name, both real:

- **FR2.14 (the guardian's reachable-children resolution set) — uncovered.**
  US2.7 covers the *selection UI* (FR2.15–FR2.17) and US2.8 covers the scoping
  (FR2.7, FR2.18), but the resolution rule itself — "every distinct student
  account appearing on an enrollment where that number is the recorded guardian"
  — is cited nowhere, and it is the query both stories sit on. Add to US2.7:
  `AC2.7.5 — Given my number is the recorded guardian on enrollments belonging to three different students across any number of teachers and batches, When I sign in, Then exactly those three children are reachable, each once, and no child whose enrollments name a different guardian number is reachable. [FR2.14]`

- **FR3.1 (weekly recurring schedule slots) — only half covered.** AC2.1.1 has
  the teacher setting "weekly schedule slots" at batch creation, but nothing
  states that sessions derive from those slots, and US3.1 opens "a scheduled
  session" that nothing in the stories creates. There is a missing story here,
  not just a missing criterion: **US3.0 — Sessions appear from the batch
  schedule.** Without it the implementer has to guess whether sessions are
  materialized rows generated ahead of time or computed from the recurrence on
  read — which determines whether AC3.2.1 (reschedule) edits a row or creates an
  exception to a recurrence, and that is a schema decision. Proposed:

  > **US3.0 — Teacher's scheduled classes appear without being created one by one**
  >
  > As **a teacher**, I want each week's classes to appear from the batch
  > schedule, so that I do not create every session by hand.
  >
  > - `AC3.0.1 — Given a batch with weekly schedule slots, Then a session exists for each slot occurrence, with that slot's weekday, start time and end time. [FR3.1] [FR3.2]`
  > - `AC3.0.2 — Given I reschedule or cancel one occurrence, Then only that occurrence changes and the recurring slot is unaffected. [FR3.3] [FR3.4]`
  > - `AC3.0.3 — Given I change a batch's schedule slots, Then past sessions are unchanged. [FR3.1]`

  AC3.0.3 is the one that will otherwise be got wrong: editing a recurrence
  rewriting history is a classic calendar defect.

Three more uncited FRs that I judge correctly uncovered, listed so the
traceability file can mark them deliberately rather than by omission: **FR1.1**
(phone number is the identifier — a modelling statement, implied throughout),
**FR2.6** (guardian number captured per enrollment — implied by AC2.2.1 and
AC2.8.1), **FR2.10** (inactive *from a date*, not a flag — implied by AC2.4.1's
"from a date"; I would accept it as covered), and **FR6.10** (no payment
gateway — a scope exclusion, not a behaviour). Mark each `Covered by implication`
or `Out of scope` in traceability; do not leave them blank.

Finally, one missing *student-side* story the one-story-per-actor rule should have
produced and did not: **the student never sees their own attendance.** AC3.5.1
gives it to the guardian; FR3.7 grants it to "students and guardians". Add to
US3.4:
`AC3.4.4 — Given past sessions in my batch, Then I see whether I was marked present or absent in each. [FR3.7]`

---

### 5. Criteria that cannot be implemented as written

**AC2.3.1 — "reflects it immediately".** Unimplementable as written, and the
word "immediately" is the problem in a system with a Room read cache. Room is a
read cache by decision [TC-8, D-9] and a cached roster will show the old name
until it is refetched, so "immediately" is either false or forbids caching.
Replace:

> `AC2.3.1 — Given an enrollment, When I edit the display name, Then the next fetch of any roster, marksheet or dues view returns the new name, and no view returns the old name once refetched. [FR2.5]`

If the lead wants the stronger UX property (the screen the teacher is looking at
updates without a manual pull), that is a second, separate criterion and should
say so: `Then the screen I edited from shows the new name without my refreshing
it.` Those are two different obligations and one word is currently doing both.

**AC5.2.1 — "the ledger records charged, received, carried forward and forgiven
separately".** Ambiguous between a schema and a view, and the ambiguity is
load-bearing because the affirmed money practice pins a property-based invariant
on exactly these four quantities (`charged - received - forgiven == outstanding`,
`outstanding` never negative). A story should not pick columns, so the fix is to
state the invariant and the observable, not the storage:

> `AC5.2.1 — Given a fee cycle, When I adjust the charged amount, Then the outstanding balance equals charged minus received minus forgiven, carried-forward amounts are attributed to the period they originated in rather than the current one, and the outstanding balance is never negative. [FR5.1] [FR8.3]`

That is implementable, it is testable, it does not dictate schema, and it closes
the carried-forward attribution question that FR8.3's collection-rate exclusion
rule depends on — which is currently stated in FR8.3 and in no criterion of US5.

**AC6.1.5 — "resolves to the enrollment's open fee cycle".** Three unhandled
cases and it is the worst-specified criterion in the draft, because money lands
on whatever it resolves to.

1. No open cycle (paid up, or inactive before the period, or the guardian pays
   early before generation runs).
2. Two or more open cycles (the normal case the moment anyone is a month behind
   — FR5.5's self-healing and FR6.8's carry-forward both produce it).
3. An amount exceeding the resolved cycle's balance.

Replace with:

> `AC6.1.5 — Given one or more unsettled fee cycles on the enrollment, When I submit, Then the payment is applied against the oldest unsettled cycle first. [FR6.2]`
> `AC6.1.6 — Given my amount exceeds the oldest unsettled cycle's balance, When I submit, Then the submission is accepted whole and the excess is held against the next unsettled cycle, with nothing discarded. [FR6.2] [FR6.4]`
> `AC6.1.7 — Given the enrollment has no unsettled cycle, When I submit, Then I am told there is nothing currently due and the submission is refused rather than recorded against a future period. [FR6.2]`

Oldest-first is a product decision I am proposing, not deriving — flag it for the
human. The alternative (the guardian picks the period) is defensible and more
work. What is not defensible is leaving it unstated: an implementer facing two
open cycles will pick one, and whichever they pick becomes the product.

**AC2.4.4 — self-contradictory against AC2.4.1.** AC2.4.1 says no cycle
generates for a period beginning after the inactive date; AC2.4.4 says a cycle
already generated for the current period stands in full. Neither says what
happens when the inactive date falls inside a period for which generation has not
yet run — which is the common case, because generation runs daily and an inactive
date is usually set mid-month for a period whose cycle already exists, but not
always. FR5.3's predicate is `inactive_from` unset or falling *after* the period,
so a mid-period inactive date means no cycle generates — which contradicts
AC2.4.4's "stands in full" for the identical calendar situation, differing only
by whether the job happened to have run. Add:

> `AC2.4.5 — Given the inactive date falls inside a period, When generation has not yet run for that period, Then no cycle is generated for it, so whether a mid-period departure is charged depends on whether the cycle already existed. [FR5.3] [FR5.6]`

That is an uncomfortable criterion and it should be, because the underlying rule
is uncomfortable. Writing it down is how the human gets the chance to say "no,
charge it in full either way" — which I suspect is the intended rule and which
FR5.3's predicate does not implement. **This is a requirements-level
contradiction surfaced by story writing, and the inception phase rules forbid
carrying it forward unresolved. Flag it to the human as a decision, not as an
assumption.**

One more, less serious: **AC7.1.4's "renders current data on open with no
generate step"** — "current" is unverifiable against a Room cache. Say what is
meant: `Then the view is populated from a single request with no further action
from me, and any cached data shown is labelled with its age. [FR7.3] [NFR4]`

---

### 6. The three absence-asserting criteria

Sound practice in two cases out of three, and the lead's rationale ("an unstated
absence gets implemented as its opposite") is correct and unusually well judged
for this project specifically — review depth on the Android surface is limited,
so what is not written down is not caught.

- **AC1.3.3 (dormant enrollments not visually distinguished) — keep.** This is a
  genuine product decision with two defensible answers, and stating it is how the
  human gets to disagree. I think the human will disagree, incidentally: a
  teacher who mistyped a number and whose student therefore sees nothing has no
  way to discover it, and FR1.9 makes that state permanent. But that is a product
  argument, not a sizing one, and the criterion is the right vehicle for it.

- **AC3.1.4 (no speed requirement) — keep, and it is the most valuable of the
  three.** FR3.5 dropped the mid-class speed requirement explicitly, the persona
  file names it as the defining abandonment risk, and the affirmed Testing Posture
  says PU-3.6's speed obligation is *not* discharged by a correctness test. Without
  AC3.1.4 an implementer reading the persona file will invent a latency budget and
  then a Compose UI test that purports to verify it. Stating the absence prevents
  a fake verifier. Keep verbatim.

- **AC5.1.5 (money crosses the API as a string) — remove from US5.1 and I agree
  with the brief's framing.** It is not a criterion of "fee cycles generate
  monthly"; it is a system-wide invariant that holds for US5.2, US5.3, US5.4,
  US6.1, US6.3, US6.4, US7.1 and every US8 story. Three problems with it living
  here. It implies the other money stories are not bound by it. It is
  *mechanically* enforced by the affirmed practice — the Pydantic annotated type,
  the SQLAlchemy `TypeDecorator`, the Kotlin serializer that rejects a JSON
  number, and the schema-wide OpenAPI test — so the criterion duplicates a check
  that already fails in CI. And it will be verified once, globally, never
  per-story, so a per-story criterion mis-describes where the test lives.

  Where it should go: a short **System-wide invariants** section at the head of
  the stories file, listing the constraints every story inherits, with the
  money-as-string invariant, the lens-is-computed invariant (FR1.3), the
  no-device-identifier invariant (NFR11) and the privacy-boundary invariant
  (NFR14), each traced to its FR/NFR and marked as verified once globally rather
  than per story. That keeps the lead's defensible intent — the absence is stated,
  not inferred — without pretending it is a property of fee-cycle generation.
  AC1.1.6 and AC9.1.4 (both NFR11) are the same case and should move there too.

  If the lead prefers not to add a section, the fallback is to keep AC5.1.5
  worded as an invariant rather than a criterion of this story, and say so: `Then
  it is a string, never a JSON number — an invariant of every story in this
  backlog, not of this one.` Less clean, but better than the status quo.

---

### 7. Dependency correctness

The stated graph `US1 → US2 → {US3, US4, US5} → US6 → US7` is right in its spine
and wrong in three places.

**US8 does not depend only on US5 — the brief's suspicion is correct, and it is
worse than that.** With the US8 split from §1:

- US8.1 (this month's receipts) is "what was actually received", which is the
  verified-payment ledger. **Depends on US6, not US5.** A fee cycle with no
  verified payment has received = 0, so built on US5 alone this story is a screen
  that always shows zero.
- US8.2 (trend) — same, **US6**.
- US8.3 (collection rate) — received over charged, with waived excluded from the
  denominator. Waiver is created at AC6.3.3. **Depends on US6.**
- US8.4 (next exam) — **depends on US4 only**, not US5 or US6 at all. It is the
  one US8 story that could ship in the US4 slice.

So the correct edge is `US6 → {US8.1, US8.2, US8.3}` and `US4 → US8.4`. The
current `US8 depends on US5` would have Delivery Planning schedule an analytics
Bolt before the data it analyses exists.

**US7 is drawn as depending on US6 and it should be US5 and US6 both, stated
explicitly.** Outstanding balance is charged-minus-received-minus-forgiven: the
charged side is US5, the received and forgiven sides are US6. The current chain
`US5 → US6 → US7` gets this right transitively but the dues query touches both
directly, which matters for whether US7 can start while US6 is partially done.

**US2.4 has a forward dependency on US5 and the graph hides it.** AC2.4.1 and
AC2.4.4 are both assertions about fee-cycle generation, which US5.1 builds. US2.4
can be *implemented* in US2 (write `inactive_from`) but cannot be *verified*
until US5 exists, and it is one of the cases the affirmed Testing Posture names
as test-first. Either note it on the story, or move AC2.4.1/AC2.4.4 into US5.1
and leave US2.4 with the two criteria that are purely enrollment-scoped
(AC2.4.2, AC2.4.3). I mildly prefer the note: splitting the behaviour across two
stories is worse than a story with a stated forward dependency.

**US9 (notifications) is drawn as depending on US4; it depends on US5 and US6
too.** AC9.1.1 fires when a fee cycle becomes due, which is US5. Correct is
`{US4, US5} → US9`, and AC9.1.3 (delivery failure never fails the triggering
operation) can only be tested once there is a triggering operation to fail.

Nothing else in the graph has a backward edge. US1 → US2 is correct and US2 →
{US3, US4, US5} is correct, including that US3, US4 and US5 are mutually
independent, which they are.

---

### 8. Build order within US1

The story order does **not** match a sensible build order, and the mismatch
matters because US1 is the gated skeleton.

Current order: US1.1 sign-in, US1.2 claim, US1.3 dormant, US1.4 existing-teacher
warning, US1.5 profile, US1.6 in-app delete, US1.7 web delete.

What must exist before anything else in US1 can be built:

1. **The account and enrollment tables, and one Alembic migration from zero
   against a real Postgres container.** Nothing in US1 is testable without it,
   and the affirmed practice puts it in the skeleton. It is not a story and
   should not be, but the build order must name it.
2. **The datastore-backed rate-limit counters.** Before the OTP issue endpoint,
   not after, because retrofitting a per-process counter to a datastore one is a
   rewrite of the thing under test. This is the ordering mistake the current
   story sequence invites: US1.1's happy path gets built, the counters arrive
   with the abuse criteria later, and the implementation that passes the happy
   path is the per-process one.
3. **OTP issue and verify, with hashing and the enumeration-identical response**
   — US1.1's AC1.1.1, AC1.1.2 plus my AC1.8.5.
4. **Token issue, access-token expiry, refresh rotation with reuse detection, and
   `kid` support** [NFR13]. Not a story; must precede US1.2 because US1.2's
   AC1.2.4 (switch lens without re-authenticating) needs a working token.
5. **The lens mechanism** — US1.2. This is the structurally novel part and it is
   correctly second in the story order.
6. **The Compose sign-in screen with both language bundles** — my AC1.1.7.
   Last among skeleton items, because it is the surface over the proven backend,
   and per the affirmed Testing Posture the Compose surface is the one place
   test-after is right.

Then the rest of US1, and here the current order is wrong in two places:

- **US1.5 (profile) should come before US1.3 and US1.4.** Profile is where the
  `profile` table, its row-level security policy and the restricted non-superuser
  test role first appear, and that RLS setup is a prerequisite for the privacy
  suite that everything after it relies on. Building it fifth means four stories
  ship before the privacy boundary exists to be tested against.
- **US1.6 and US1.7 should move out of the skeleton Bolt entirely** and the
  story order should say so. They need the per-table deletion disposition, which
  is an open Domain Design question, plus a web surface the approved architecture
  does not contain and which is flagged uncosted. They are release-blocking V1
  deliverables, not skeleton deliverables, and leaving them last in the US1 list
  reads as "last in the first Bolt" rather than "a later Bolt in V1".

**Recommended US1 order**, as a build order annotation on the group rather than a
renumbering (the IDs are permanent): migration and counters → US1.1 → US1.8
(new) → US1.2 → US1.5 → US1.3 → US1.4 → [Bolt boundary] → US1.6 → US1.7.

---

## Positions

- AGREE: Grouping by proto-Unit rather than by persona or screen — the slices are already the delivery sequence and the Unit DAG consumes this grouping directly.
- AGREE: US8.1 is too large; the lead's own flag is correct, though the reason is aggregation complexity rather than view count.
- AGREE: AC3.1.4's deliberate absence assertion — without it an implementer invents a latency budget and then a fake verifier for it.
- AGREE: AC1.3.3 stated as a decision rather than left implicit, even though I expect the human to reverse it.
- AGREE: FR2.2's owner indirection belongs at AC2.1.3 despite having no observable behaviour; the later migration cost justifies it.
- AGREE: NFR16 correctly carries no criterion — there is no second API version in V1 for a compatibility behaviour to be observable against.
- OBJECT: The skeleton's observable abuse controls are a real gap, not a correct deferral — five of the seven change what a user sees, two are already criteria, and per-SMS billing makes the omission a budget exposure the human's checkpoint would not see.
- OBJECT: AC5.1.5 does not belong in US5.1 — it is a system-wide invariant, mechanically enforced in CI, and a per-story criterion implies the other seven money stories are unbound by it; move it to a System-wide invariants section with AC1.1.6 and AC9.1.4.
- OBJECT: FR1.3 is uncovered and it is the project's most-mandated rule; a cached role is indistinguishable from a computed one on every happy path, so it needs the observable criterion proposed in §4.
- OBJECT: FR9.4 is uncovered, and a generic correction-history mechanism attached to every mutable record is the natural implementation and breaches a `NEVER` rule.
- OBJECT: FR11.4 should carry criteria — the lead's reason ("a race the teacher cannot observe") is wrong; the teacher observes the outcome, and last-write-wins per field versus per record versus a 409 are three plausible implementations of an unstated rule.
- OBJECT: FR2.14 and FR3.1 are uncovered; FR3.1 needs a new story (US3.0), because whether sessions are materialized or computed from a recurrence is a schema decision no story currently forces.
- OBJECT: AC6.1.5 cannot be implemented as written — it does not handle zero open cycles, two or more open cycles, or an overpayment, and two open cycles is the normal case the moment anyone is a month behind.
- OBJECT: AC2.3.1's "immediately" is false or forbids the Room read cache the architecture mandates; restate as a property of the next fetch.
- OBJECT: AC5.2.1's four-amount wording is ambiguous between schema and view; restate as the money invariant so it does not dictate columns while remaining testable.
- OBJECT: AC2.4.4 contradicts FR5.3's generation predicate for the identical calendar situation, differing only by whether the daily job had run — a requirements-level contradiction the inception rules forbid carrying forward.
- OBJECT: The US8 dependency edge is wrong — received, waived and the collection rate all require verified payments from US6; as drawn, Delivery Planning would schedule analytics before the data exists.
- OBJECT: US9's dependency is drawn on US4 alone but AC9.1.1 fires on a fee cycle becoming due, which is US5.
- OBJECT: US6.2 is not a story — one criterion reading "identical to the guardian's" has no independent test; merge it into US6.1, adding the attribution clause that is the only real difference.
- OBJECT: US1's story order is not a build order — the datastore-backed rate-limit counters must precede the OTP happy path or the per-process implementation is what passes the first test, and US1.5's row-level security must precede the stories that depend on the privacy boundary.
