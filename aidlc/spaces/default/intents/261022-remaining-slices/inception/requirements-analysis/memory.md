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

- The product's requirements were already written, traced and gated: 102 entries
  with no gaps, whose FR IDs are permanent keys that built code references. This
  stage did not re-derive them. Its real work was that four requirements now
  contradict decisions taken after they were written.
- The sharpest contradiction: FR1.9 called a mistyped number "correct behaviour,
  not an error state". Under the lens model that mistyped number silently grants
  a stranger a guardian lens over a child. The requirement had blessed the
  exposure that acceptance exists to close.

## Tradeoffs

- Recorded the supersessions in this record rather than editing the prior one.
  The prior artifact is gated, and overwriting it would destroy the evidence of
  what changed and when.
- The review found three Critical gaps that were real, not noise, and each was
  verified before being acted on. The two that mattered were both about a real
  person being harmed by a rule written for a stranger: a mis-tapped decline was
  permanent and unfixable, and a declined seat accrued debt forever. Both came
  from writing the durability rule without asking who it protects and from whom.
- The decline/fee gap is the mistyped-digit failure relocated. Acceptance closed
  it on the lens and the draft reopened it on the ledger, which is worth noticing
  as a pattern: closing an exposure in one dimension does not close it in the
  others that share the same cause.
- Dropped FR0.2 rather than ship it. "Verified per screen" named no artifact, no
  recorded result and no actor, and the project's own rule as of 2026-10-22
  forbids exactly that. It was also vacuous for D5, which has no artboard — a
  requirement that cannot apply to one of the six units it governs.
- The reviewer also confirmed the part most at risk of being wrong: the scope
  boundary. Declining to restate 102 traced requirements held up under challenge.

