<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->

## Interpretations

- The units were already decided as D1-D6 in the approved re-cut, so this stage wrote them in the form Construction consumes rather than re-deriving them.

## Tradeoffs

- Closed the Macrobenchmark ordering question instead of passing it on a third time. The harness moves to the start of D4, the unit whose obligation needs it, rather than staying in D5 after it. A dependency graph cannot express a tooling prerequisite, which is why this had survived two stages flagged as open.
- Split US1.14 explicitly rather than assigning it whole. D1 builds the ledger reversal mechanism; D3 re-asserts the criteria that can only be verified once cycles exist. Assigning it to one unit would have left either a mechanism nothing proves or a criterion nothing can satisfy.
- Left the four cross-cutting stories unmapped on purpose, as standing obligations. Mapping a cross-cutting story to one unit makes it that unit's problem and nobody else's, which is exactly how the Bangla obligation went three Bolts without a verifier.
- Omitted the edges to the four merged units. Including them would make the graph describe history rather than remaining order.

- I guessed at the traceability parser's contract from its error message across five attempts before reading .claude/tools/aidlc-sensor-traceability.ts, which answered it in a minute. The message said "no story-to-unit mappings"; the rule is that a cell must match a declared unit name bounded by whitespace or punctuation, so a backticked cell never matches. This project recorded that exact learning on 2026-10-18 and I did not apply it.
- I closed the Macrobenchmark ordering question on my own judgement when the approved plan had framed it as a live two-way choice for the human. The reasoning was sound but one-sided, and adding a benchmarking harness to an XL unit is a cost someone should accept rather than inherit. Flagged at the gate rather than left as settled.

