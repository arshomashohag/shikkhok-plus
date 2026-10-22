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

- 45 stories already existed, traced and gated, with IDs built code references.
  This stage did not re-derive them. Its work was the criteria the acceptance
  model contradicts — and a stale acceptance criterion is more dangerous than a
  stale requirement, because a criterion is what someone writes a test against.

## Tradeoffs

- The human chose "keep US1.2, amend its criteria". I extended that to the title
  and narrative, because "claims a dormant record... without anyone inviting me"
  sitting above criteria saying the opposite is worse than either consistent
  option. Flagged the extension to the reviewer rather than letting it pass
  silently; the reviewer agreed it was right and not worth a re-ask.
- My contradiction sweep was WRONG and the review caught it. I counted six
  criteria across four stories; the true count was ten across five. The sweep
  stopped at stories whose titles mentioned acceptance, when it should have swept
  every criterion mentioning signing in or dormancy. The assessment now records
  the corrected count rather than quietly fixing the number.
- The most consequential miss was AC2.5.1: removal permitted only while dormant.
  Once dormant collapsed into pending, that forbade removing ANY seat a teacher
  creates — blocking the recovery path from a mistyped number, which is the exact
  exposure acceptance exists to close. A criterion in a different story group,
  reachable only by asking what the state change does to everything that names
  the old state.
- Two state-machine edges missed in the draft, both about two people disagreeing
  about one seat: a split decision had no criterion, and I had written the
  decline rule seat-scoped, so a guardian's decline would have stopped an
  accepting student's billing. Per-link acceptance was in the requirement; I
  wrote the stories as though a seat had one decider.
- Honoured the superseded reasoning rather than discarding it. AC1.3.3 refused to
  mark the roster because decorating most rows flags normality as a problem. That
  argument survives the dormant/pending collapse, so pending keeps a batch-level
  count and only declined is marked per row.
- Withdrew US1.17 rather than keep an obligation wearing a story's clothes. FR0.1
  was already N/A for the same reason; FR0.2 now matches.
- When a state is renamed, collapsed or added, sweep every artifact for criteria naming the OLD state, not only the stories about the change. Here dormant collapsed into pending, and the most consequential miss was a removal criterion in a different story group: permitting removal only while dormant forbade removing any seat a teacher creates, which blocked the recovery path from the exact exposure the change existed to close.
