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

- The component model was settled and this stage did not reopen it. Its work was four columns, one lens type, and the governance for both.

## Tradeoffs

- Two of my own claims were wrong in the same way: I asserted things about built code without reading it. "Every existing row is pending by construction" ignored that is_dormant is student_account_id IS NULL, so a plain DEFAULT would have withdrawn a working lens from every signed-in student. "A fourth branch of the same one-statement query" ignored that _LENS_QUERY returns scalars, so an invitation grant that is a set could not fit it.
- The most dangerous finding was an absence rather than an error: nothing said the existing lens queries must start reading the decision columns. The traceability file asserted the coverage and no artifact delivered it. Adding columns nobody reads would have shipped the entire acceptance model as decoration, with the mistyped-number exposure untouched.
- There were TWO queries granting lenses, not one, in different modules, and GET /v1/me reads the one I had not looked at. A fix to either alone is a silent half-fix.
- Checked rather than assumed on Profile: nothing reads it today, so making it non-optional breaks nothing. I had claimed otherwise in the first draft.
- The basis string disclosure was a comment: nothing reads `basis` and the only test checks its length. Named D6 as the installing unit rather than leaving an unverified claim.

- Adding a column is not adding a behaviour. Name the queries that must start reading it, because the ones already granting access go on granting it on the old evidence. Here two separate statements in different modules granted lenses, GET /v1/me read the one not examined, and the acceptance model would have shipped as columns nobody read with the exposure it exists to close still open.
- Before asserting how a change fits built code, read the code. Two claims in this stage's first draft were confidently wrong in the same way: a plain column default would have withdrawn a working lens from every signed-in student, and a per-enrollment grant was described as a fourth scalar in a query that returns scalars for one account.
