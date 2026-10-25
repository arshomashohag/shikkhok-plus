# Risk and Sequencing Rationale

**Stage**: delivery-planning (2.9)
**Record**: 261022-remaining-slices

> Why the six Bolts sit in that order, what each buys, and where this plan is
> most likely wrong. A **Bolt** is one build pass over a unit.

## Sources

- [upstream] `inception/units-generation/unit-of-work-dependency.md`
- [upstream] `inception/domain-design/decisions.md`
- [human] the stated top risk, unchanged: the privacy boundary

---

## The heuristic

**Dependency-forced first, then the fee-revision argument for the one free
choice.**

Walking-skeleton-first no longer applies: the skeleton is built and
checkpointed. Risk-first has largely spent itself, because the privacy
mechanisms are in place and proven. Five of six positions are forced by the
DAG; the sixth is D3 before D4.

**No scoring model**, and this is recorded rather than silently omitted. Every
remaining capability is Must Have, so cost of delay is constant and the value
axis does not vary. A model whose value axis is constant is not a model.

## The one free choice: D3 before D4

- **For D3 first:** the fee model is known to be in revision [D-18]. Pinning
  its arithmetic under test before the revision lands is what makes the
  revision cheap rather than frightening — the team's own stated reason for
  test-first on money.
- **For D4 first:** it is the larger surface and the one carrying genuinely
  novel client behaviour, so starting it earlier leaves more room for it to
  go wrong.

D3 wins on the revision argument. Nothing downstream distinguishes them: D5
needs both.

---

## Top risks

1. **The two query changes are invisible.** D1's exposure closes in
   `_LENS_QUERY` and `_SUMMARY_QUERY`, neither of which appears on a screen.
   Every other part of D1 is demonstrable on a phone; this part is
   demonstrable only by a test that fails without it. Likelihood of being
   missed: **was high** — no artifact named it until the Domain Design review
   — and is now low, because ADR-014 names it and the adversarial test guards
   it. Impact: critical. A stranger keeps a guardian lens over a child.

2. **The migration touches live data.** D1's backfill runs against staging
   seats where students have already signed in. A plain default would have
   un-accepted all of them; the conditional backfill does not. Likelihood now
   low, impact high, and the mitigation is that the `CASE WHEN` is three lines
   a reviewer can read in full.

3. **Money arithmetic.** D3. The ledger identity was wrong twice before
   randomized testing settled it, and the fee model is still in revision.

4. **Deletion shipped broken.** D6, last and autonomous — the thing a
   compressed schedule squeezes, and the one `team.md` names as most reliably
   shipped broken because nobody tests the absence of data.

5. **Android surface quality** [OC-3]. All six Bolts ship screens, where the
   prior plan had four that were backend-only. Mitigated mechanically: the
   toolchain installed on 2026-10-22, the ViewModel state-machine tests, the
   coverage ratchet.

6. **Play release blocked late.** The 14-day window on the critical path with
   nothing absorbing it.

7. **Schedule.** Every capability is Must Have, so nothing absorbs variance.
   **No range is stated here.** Four Bolts of real velocity data exist in this
   project; an invented number would be less honest than deriving one from it.

---

## What each Bolt buys

- **D1** buys the ability for a real person to use the app at all, and closes
  the unconsented-guardian exposure. Everything else is undemonstrable without
  it.
- **D2** buys the best ratio of usable capability to work in the plan: no new
  endpoints, screens against nine already built and tested.
- **D3** buys the fee arithmetic pinned under test before the known revision
  lands.
- **D4** buys the offline conflict path — the only genuinely novel
  client-side behaviour, and the only place a wrong answer is silent data loss
  during a live class.
- **D5** buys the cross-batch dues view, the feature the brief named as
  distinctive.
- **D6** buys a public release, and is the only Bolt that gates one.

---

## The privacy worry, addressed

Most of it is now proven rather than planned, in merged code: a route without
a lens cannot merge; a teacher-lens schema cannot carry a profile field; RLS
is in force behind a superuser meta-check; one account resolves three lenses
in one statement; two teachers sharing a student cannot see each other's data.

**What D1 adds** is acceptance, which closes the one hole none of that covered:
a teacher typing a phone number granting a stranger a guardian lens over a
child, with no consent and no notification.

**What remains unproven until late:** deletion actually removing what the
policy says, which is D6-only and runs autonomously. That is the gap I am
least comfortable with, and the 14-day Play window means a compressed schedule
squeezes exactly there.

---

## Deviations from topological order

None. One prerequisite inversion was recorded instead — D4's latency
obligation needed a harness that lived in D5, which a dependency graph cannot
express as an edge. **It dissolved on 2026-10-23** when the human chose the
manual pilot check over the harness: with nothing to schedule, there is
nothing out of order. PU-3.6's verifier is a named manual check in D4's
Definition of Done, and a Compose correctness test still does not discharge
it.
