<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-23 — Answered this stage's questions from the upstream artifacts rather than asking the human. Six ADRs written three days earlier settle the schema, the lens type, the migration and the two query changes; 32 requirements and seven stories settle the behaviour; the screens are drawn down to their states. Each answer in the questions file names the source that settles it, and the three that nothing settles are recorded as assumptions instead.
- 2026-10-23 — Read rule IDs as unit-scoped, not globally unique. The prior record reuses `BR1.1` across several units, so D1 numbers its own rules from 1 and keeps the group meanings stable across units — group 1 authorization, 2 abuse control, 3 privacy — so a reader moving between units reads the same axis under the same number.
- 2026-10-23 — Treated `O5`'s deletion states as D6's and shipped only the profile-edit half in D1. The mockups draw all four states on one screen, but the unit boundary is the deletion paths, which are release-blocking D6 deliverables with their own tests.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-23 — Produced `frontend-components.md` although the unit is typed `service`. The stage makes it conditional on the unit including UI, and D1 ships five screens; typing it `service` reflects that its schema and authorization changes are the substance, not that it has no front end.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-23 — Carried the superseded `AC1.2.1`/`.2`/`.3` in `traceability.json` alongside the live `a` forms. The sensor derives acceptance IDs by regex over `stories.md`, which cannot tell a live criterion from one named in a Supersedes column. Mapping both to the same rules is accurate — the amended behaviour satisfies the superseded statement — and a note records why both appear, which is better than a coverage file that silently disagrees with the story it cites.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-23 — *(Closed in this stage.)* The story map's Directory column said `d1-signing-up-and-joining` and the YAML block Construction walks declares `signing-up-and-joining`. The traceability sensor reads the directory segment and rejected the prefixed form. Reconciled for all six units, with the reason recorded in the story map and in `unit-of-work.md`; the `D`-number stays as the Bolt slug, which names a branch rather than a path.
- 2026-10-23 — Whether `O4` is reachable from the lens switcher. The invitation lens is deliberately not one of the three a person chooses between, so the switcher is the wrong home for it, but this is a navigation choice with no rule behind it and the mockups record it as open.

## Review findings
- 2026-10-23 — The review found that D1's migration breaks a merged, routed write path and no artifact said so. `remove_enrollment` refuses when `student_account_id IS NOT NULL`, which meant "claimed" before acceptance existed; after D1 a pending person who signs up sets that column, so a teacher can no longer remove a seat created on a mistyped number — the exact recovery path the unit exists to open. Closed by BR7.1, and by a sweep of every reader of the two link columns rather than only the two ADR-014 names. Two further wrong readers turned up that the review had not named: the roster's `is_dormant` derivation (now BR7.2) and `list_guardian_children`, which is safe only because the lens it needs stops being granted.
- 2026-10-23 — This project recorded on 2026-10-22 that adding a column is not adding a behaviour and that the queries which must start reading it have to be named. I had that correction in context and still shipped a first draft that named only the two queries an ADR had already named for me. Following a recorded correction is not the same as having read it.
