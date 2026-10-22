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

- A re-run against an affirmed baseline, scoped by the user to reconciliation
  rather than re-derivation: the practices affirmed 2026-10-16 are settled and
  carried forward intact. The stage's job here was the mismatch between three
  affirmed practices and a codebase that does not implement them.
- Collaborators are off, so the release engineer ran alone — on a stage whose
  subject is quality tooling. That is worth naming: the draft had no independent
  quality, developer or devsecops pass, and the human gate is its only review.
  Recorded in evidence.md by the lead rather than left implicit.

## Tradeoffs

- Verified the absences independently at the current commit rather than trusting
  either the scan or the lead: four Gradle plugins and none for quality, no
  lint.xml anywhere, the CI step labelled "Lockfile verification" sitting
  directly above an unpinned pip install. All reproduced.
- The lead found a dependency the scan missed: lockfiles are a PRECONDITION for
  CVE scanning, not a parallel gap. A scanner pointed at `mypy>=1.11` reports a
  range; pointed at a lockfile it reports the build. Closing the CVE half first
  produces findings nobody can act on. That reorders the work.
- Discovered rules deliberately do not restate the 31 existing ones, because
  promotion appends rather than replaces. Six new rules, each tied to a verified
  finding rather than a preference.
- The clearest account of how the gap opened was already in the codebase:
  NoFloatingPointTest.kt's docstring records correct reasoning, names the Bolt
  that would install detekt, and nothing watched for it. The practice clause
  "arriving with the Bolt that first needs them" names no Bolt and permits
  indefinite deferral, which is what happened.
- One obligation remains unverifiable from here: "a green main" now rests on
  GitHub branch protection, which cannot be read from the repository. Flagged
  rather than resolved.

