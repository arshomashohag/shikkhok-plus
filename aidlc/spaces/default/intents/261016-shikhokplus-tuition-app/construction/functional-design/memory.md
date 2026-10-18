<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-18 — [unit money-core] This Unit persists nothing, so `entities.md` describes value semantics and the seven ledger entry kinds rather than tables. Said so explicitly in the artifact rather than inventing persistence to fill the template. `frontend-components.md` is absent by design: no UI.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-18 — [unit money-core] Set the quality bar as "compute the scenarios, do not assert them", because this project's ledger identity was wrong twice before randomized testing settled it. That paid for itself: the agent independently reproduced the 20,000-history verification rather than trusting ADR-002, and found a defect while doing it.
- 2026-10-18 — [unit money-core] The agent found that my own illustrative figure for the one-sided carry bug was wrong. I had written "reads 2500 owed against a true 1500" into ADR-002, team.md and the bolt plan; computed, 1000 carried into a second 1000 charge is 2000 true and 3000 one-sided. Verified independently before accepting. The defect and the fix were real; the number attached to them was not, and it had propagated to four files. A worked example asserted rather than computed is exactly the failure the quality bar exists to catch, and I committed it while writing the rule that warns against it.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-18 — [unit money-core] The wrong figure also sits in an affirmed `team.md` rule, which cannot be edited directly — it goes through the learnings gate at this stage's end.
