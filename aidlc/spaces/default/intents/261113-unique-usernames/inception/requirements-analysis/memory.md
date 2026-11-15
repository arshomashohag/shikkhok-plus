<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-11-13T00:00:00Z — accepted a public username-availability lookup as a deliberate existence oracle for usernames only, bounded by its own ceilings; the alternative (learn only at submit) is still an oracle and a worse sign-up experience.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-11-13T00:00:00Z — reviewer: what happens to a linked seat when the teacher edits or clears its recorded contact, and when a freed contact is verified by a second account; settle in domain design.
- 2026-11-13T00:00:00Z — reviewer: contact replace/remove may need an old-contact notice, session effects and a rate ceiling; settle in NFR requirements.
