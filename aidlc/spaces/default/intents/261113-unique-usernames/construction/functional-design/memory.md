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
- 2026-11-14T13:00:00Z — U2 review 2 (READY with open Majors): the lock order omits the account row (W5/W6/W7 take account FOR UPDATE then the contact advisory lock; a teacher save takes the advisory lock then an FK key-share on the account row) — code generation must take the contact advisory lock before the account row lock, or treat deadlock-detected as a bounded transaction retry.
- 2026-11-14T13:00:00Z — U2 review 2: account deletion (app/governance/deletion.py) deletes the account row and never sets student/guardian_relink_blocked_at, so BR6.2's "an erased number never relinks" is not enforced by built code today; structural, pre-existing, to raise with the person.
