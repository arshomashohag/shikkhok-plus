# Risk and Sequencing Rationale

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive
**Revision**: re-run 2026-10-22. Supersedes the 2026-10-18 rationale.

> Why the six remaining deliverable units sit in the order they do, what each
> buys, and where this plan is most likely wrong.
>
> A **deliverable unit** groups one or more Bolts — one build pass over a piece
> of work, ending in something that runs — by what a person can do when the
> group ships.

## Sources

- [upstream] the re-cut Bolt plan and the Units Generation DAG
- [upstream] `inception/contract-design/contract-summary.md` open questions
- [decision] `docs/delivery/vertical-slices.md`, committed 2026-10-22
- [human] the stated top risk: the privacy boundary [Q2, unchanged]
- [code] the built state on disk, read 2026-10-22

---

## A. The heuristic

**Dependency-forced first, then user-visible value, with one exception forced by
a tooling prerequisite.**

Walking-skeleton-first no longer applies: the skeleton is built and was
human-checkpointed at B3. Risk-first, which drove the original ordering, has
largely spent itself — the privacy boundary's mechanisms are all in place and
proven (see section C). What remains is mostly forced by the DAG, and where it is
not, the deciding question is which group makes the app usable soonest.

**No WSJF or other formal scoring, and this is recorded rather than silently
omitted** [Q4, unchanged and still correct]. The reasoning survives the re-cut
intact: every remaining capability is Must Have, so cost of delay is identical
across all six units and the value axis is constant; job sizes span two steps at
most; and four of the six positions are dependency-forced. A scoring model whose
value axis does not vary is not a model. The one genuinely free choice — where
the Macrobenchmark harness goes — turns on a hard prerequisite that no score
would have surfaced, which is the same thing that happened last time.

## B. The order, and what forces each position

| # | Unit | Forced? | Why here |
|---|---|---|---|
| 1 | D1 `signing-up-and-joining` | **Yes, absolutely** | Nothing else can be demonstrated by a real person until an account can exist. Today a teacher exists only by hand-inserting a database row, so every other unit's "done when" is currently unreachable. |
| 2 | D2 `running-a-batch` | Yes | Every remaining capability is scoped to a batch and a roster. Also the cheapest unit by far — no new endpoints, screens only — so it converts a large amount of already-paid-for backend work into something usable. |
| 3 | D3 `collecting-fees` | By DAG | `fee-cycles-and-ledger` depends on `batches-and-enrollment`; `payment-claims` depends on fee cycles. Chosen ahead of D4 because the fee model is *already known to be in revision* [D-18] and pinning the arithmetic under test is what makes that revision cheap rather than frightening. |
| 4 | D4 `teaching-and-recording` | By DAG | Both members depend on `batches-and-enrollment`. Deferred past money deliberately: it is the largest surface and carries the offline queue, but none of it is money or privacy risk and nothing downstream waits on it except insights. |
| 5 | D5 `knowing-how-it-is-going` | **Yes** | `teacher-insights` depends on both `payment-claims` and `exams-and-marksheets`, so it cannot precede D3 or D4. |
| 6 | D6 `releasing-safely` | **Yes** | Topologically terminal: its schema-iterating test is vacuous until the last table exists. |

Serial throughout. This is a solo build with no second worker [Q5]; the
parallelisable sets recorded at Units Generation describe reorderability, which
matters when a dependency slips, not simultaneity.

## C. Addressing the stated privacy worry

The human's chief worry [Q2] is the privacy boundary: nothing a student or
guardian writes reaching any teacher, row-level security genuinely in force, no
cross-teacher leak. **Most of that is now proven rather than planned**, which is
the single biggest change since the original rationale.

**Already demonstrated, in built and merged code:**

- A route without a lens cannot merge, and a teacher-lens response schema cannot
  carry a profile field — both enforced in CI against deliberately introduced
  violations, and both covering endpoints that do not exist yet, including every
  endpoint D1 through D6 will add. This was the highest-leverage position in the
  original sequence and it paid off: the gates were installed before the routes.
- Row-level security is in force, asserted by a meta-test that `current_user` is
  not a superuser and `row_security` is on, running *before* the privacy suite so
  the suite cannot pass vacuously.
- The lens is computed per request with no role field and no cache, and one
  account resolves all three lenses in a single statement.
- A student is refused a teacher's operations — including the teacher batch list
  as a 403 rather than an empty list, because an empty list tells a non-teacher
  they are a teacher with no classes.
- Two teachers sharing one student account cannot see each other's data, and
  teacher-facing reads are keyed on `enrollment_id` rather than an account id.

**What this plan adds to the privacy surface:**

- **Acceptance closes a real hole that nobody had named.** Today a teacher typing
  a phone number grants that account a guardian lens over a child immediately. A
  mistyped digit is a children's-data exposure to a stranger, and nothing in the
  built system prevents, detects or even logs it. D1 makes a seat grant nothing
  until accepted, and the pending state on the roster row [Q14] is what makes the
  mistyped digit *visible* rather than silent. I rate this the most valuable
  single change in this plan.
- **The already-added lookup is narrowed** [Q9]. O1 state 3 as designed names the
  teacher and the batch to an unauthenticated caller, so anyone who typed a phone
  number would learn who teaches that person and where. The lookup now confirms
  only that the number was added. This is a deliberate departure from the
  artboard, recorded as such.

**What remains unproven until late, stated plainly:**

- **Deletion actually removing what the policy says it removes** is unproven until
  D6, the final unit, now running autonomously. This is the gap I am least
  comfortable with. `team.md` is explicit that deletion features are "the ones
  most reliably shipped broken, because nobody tests the absence of data", and
  the DAG genuinely puts that test last. The previous plan recommended re-gating
  it as a human checkpoint; that recommendation was overtaken by the decision to
  run autonomously [Q8], and I am recording rather than re-litigating it — the
  human stops that remain (Plan Approval, summary confirmation, any failure)
  apply to D6 like any other unit.
- **The purge honouring retention clocks** is likewise D6-only, and its failure
  mode is silent: children's data simply persisting past its stated retention,
  which no user notices and no test outside D6 covers.
- **The AC9.4.2 back-stack case** — Back must never land in another lens's or
  another child's data — is a standing per-unit obligation verified per screen.
  No screen-count-complete assertion exists in this plan. With the lens switcher
  now on every screen [Q11], this case gets materially more surface than it had
  when the app assumed a single lens. Flagging: if a global assertion is wanted,
  it belongs in D6's Definition of Done and is a scope addition.

## D. Top risks, re-ranked

1. **The Macrobenchmark harness is a prerequisite nobody is scheduled to build.**
   Likelihood **high**, impact medium. PU-3.6's mid-class speed requirement is
   dischargeable only by a Macrobenchmark on a low-end device profile, and
   `team.md` is explicit that a Compose correctness test does not discharge a
   performance requirement. That harness belonged to `release-packaging`, which
   shipped its two release gates and not its harness. It now sits in D5 — *after*
   D4, which is the unit that needs it. **This is the one genuine sequencing
   defect in this plan and I am naming it rather than hiding it.** Three ways out,
   and the choice belongs to whoever starts D4: build the harness at the start of
   D4 rather than in D5; or give PU-3.6 an explicit manual pilot check and drop
   the automated claim; or move all of D5's packaging remainder ahead of D4. The
   first is cheapest. What is not acceptable is discovering at D5 that a
   correctness test was quietly treated as the verifier.

2. **Privacy-boundary failure.** Likelihood **low-medium**, down from medium,
   impact **critical** — a children's-data breach under RC-1/RC-2/RC-3. The
   mechanisms are built and proven, which is why the likelihood dropped. What
   keeps it from being low: every remaining unit adds endpoints and screens, the
   lens switcher multiplies the back-stack surface, and acceptance introduces a
   genuinely new state (pending) that the lens resolver must honour everywhere.

3. **Money arithmetic defect.** Likelihood medium, impact high. The ledger
   identity was wrong twice before randomized testing settled it, and the fee
   model is still known to be in revision [D-18]. D3 is where this lands, and it
   is why D3 precedes D4.

4. **Deletion shipped broken.** Likelihood medium, impact high — no public Play
   track, or worse, a policy that contradicts the database. Last unit, autonomous,
   and the thing a compressed schedule squeezes.

5. **Android surface quality** [OC-3]. Likelihood medium-high, impact medium. The
   thinnest-reviewed part of the product, and this re-cut *increases* its share of
   the remaining work substantially — every one of the six units now ships screens,
   where the original plan had four that were backend-only. Mitigated mechanically
   rather than by more review: ViewModel state-machine tests, the serialization
   test per money-carrying model, the Kotlin coverage no-regression ratchet.

6. **Play release blocked late.** Likelihood medium, impact high. The 12-tester,
   14-day closed-testing window and the four release-blocking deliverables all live
   in the terminal unit.

7. **Schedule.** Every capability is Must Have, so nothing absorbs variance. The
   original estimate of 10–16 weeks covered eleven Bolts; four have shipped, and
   the re-cut adds account creation and acceptance, which did not exist in that
   estimate. **I am not restating a number here.** A range invented at this point
   would be less honest than the original, because the one thing that has changed
   is that real velocity data now exists — four Bolts over six days — and whoever
   wants an estimate should derive it from that rather than from a planning guess.

## E. What each unit buys

- **D1** buys the ability for a real person to use the app at all, and closes the
  unconsented-guardian hole. Everything else is undemonstrable without it.
- **D2** buys the largest ratio of usable capability to work in the whole plan:
  no new endpoints, screens only, against nine endpoints already built and tested.
- **D3** buys the fee arithmetic pinned under test before the known revision lands,
  and the concurrency-tested idempotency constraint.
- **D4** buys the offline conflict path — the one piece of genuinely novel
  client-side behaviour in the product, and the only place where a wrong answer is
  silent data loss during a live class.
- **D5** buys the cross-batch dues view, which is the feature the product brief
  named as distinctive, and the benchmark harness that should have arrived earlier.
- **D6** buys a public release, and is the only unit that gates one.

## F. Deviations from topological order

None. Every position is either DAG-forced or free, and no free choice was used to
move a unit ahead of its dependencies.

One **prerequisite inversion** is recorded instead, because the DAG does not
express it: D4's latency obligation needs a harness that D5 carries. A dependency
DAG records data and call dependencies; a tooling prerequisite is a third kind it
does not express. This is the same class of problem that settled
`release-packaging`'s position in the original plan, and it has recurred for the
same reason — which is itself worth noting as a pattern rather than an accident.
