<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-23 — Treated the 2026-10-22 re-cut's sequence as settled rather than re-derived. Five of six positions are DAG-forced and the sixth turns on the fee model being in revision [D-18]; Domain Design added schema and a lens type to D1 but moved no unit. What it did change is D1's content, so the Definition of Done absorbed ADR-014's two query changes rather than the plan being rewritten around them.
- 2026-10-23 — Read the practices file's `make check` clause as already answering the verification-command question. It is the CI entrypoint, runs identically locally, and now covers the toolchain installed before D1. Presenting a second candidate would have been a question with one real answer.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-23 — No WSJF or any weighted scoring model, carried forward from the prior record's recorded decision. Every remaining capability is Must Have, so cost of delay is constant across all six units, and five positions are forced. Recorded as a decision rather than omitted, because a silent omission reads as an oversight.
- 2026-10-23 — No schedule stated. Four Bolts of real velocity data now exist in this project; an invented range would be less honest than deriving one from that, and nothing downstream needs a date.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-23 — PU-3.6 ships with no automated verifier. The human chose the manual pilot check over the Macrobenchmark harness, which keeps D4 focused on the offline queue and the conflict screen at the cost of a latency obligation discharged by a person with a stopwatch. Recording "no automated verifier" openly is what keeps the non-negotiable half honest: a Compose correctness test still does not discharge it.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-23 — Branch protection's "Require branches to be up to date before merging" cannot be verified from the repository. It is the one practice whose status this work genuinely cannot establish, and with squash-merge and one reviewer it is what stops a PR green against an older `main` from breaking `main`.
- 2026-10-23 — OQ-1 and OQ-5 are start conditions for D6, not completion criteria. OQ-1 (does `PaymentClaim.transaction_id` survive the claimant's deletion?) ideally closes before D3 so the payment-history schema is not revisited.
- 2026-10-23 — The Play Console account type is the most schedule-dangerous open item, with a full 14-day window on the critical path and nothing in the build able to shorten it.
