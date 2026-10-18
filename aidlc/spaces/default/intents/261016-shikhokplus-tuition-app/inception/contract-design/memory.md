<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations

- 2026-10-18 — The stage treats every dependency edge as a candidate contract, but this system deploys as one FastAPI container plus one Android module, so most DAG edges are in-process imports rather than wire boundaries. Writing an OpenAPI spec per edge would be ceremony describing nothing. The honest inventory is: the public REST API, two third-party adapters, the external deletion route, and the in-process boundaries the codebase enforces mechanically.
- 2026-10-18 — An in-process boundary still counts as a contract when a violation fails CI. `money-core`'s import boundary and `api-contract`'s schema-level guarantees are contracts in the sense that matters here, even with no wire involved, so they are pinned rather than omitted.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs

- 2026-10-18 — Asked for a representative OpenAPI fragment rather than the whole API: enough that the shape is unambiguous and the rest follows by pattern. The committed schema is generated from the implementation and gated by a schema-diff check, so a hand-written full spec here would be a second source of truth that drifts from the generated one.

- 2026-10-18 — The reviewer found a real self-contradiction: the taxonomy table marks a 401 `retryable: false` while the refresh rule instructs a replay of the original request. Both are correct but the artifact never reconciled them, so a client author reading only the table builds something that cannot do what the refresh rule requires, and one reading only the refresh rule builds a refresh loop. Resolved by stating what `retryable` actually answers — may the client repeat this request unchanged — and that refresh-then-replay is a different request first, not a retry.
- 2026-10-18 — OQ-6 was a decision wearing a question's clothes: listed as open while carrying a "proposed default". Decided it rather than shipping it open, because leaving it would have made every money response schema in U7, U8 and U9 provisional. Flagging is cheap and can quietly become a way to avoid deciding; the test is whether the answer needs judgement nobody has, or just needs someone to commit.
- 2026-10-18 — Kept `SmsPurpose` as a one-value enum and wrote down why. A one-value enum reads as speculative generality and the obvious simplification is to delete the parameter, which would be wrong: it exists so a later consumer cannot make one ceiling arbitrate between an abuse burst and a legitimate bulk action. Recording the reasoning is what stops a future reader removing it on tidiness grounds.

- 2026-10-18 — Hit the review-format parse failure again and guessed twice more (cell length, column shape) before reading `.claude/tools/aidlc-lib.ts`. The parser validates every Prior-findings row: `ID` must match `R-<digits>` and `Now` must be one of five literal words, so the placeholder row `| — | — | — | No prior iteration. |` fails validation. An empty table is the correct representation for a first review. I had already recorded a learning at Units Generation about reading the contract rather than guessing, and did not apply it — the rule was too narrow, naming only the protocol doc when the authoritative answer was in the implementation.

## Open questions

- 2026-10-18 — Carried in: whether `PaymentClaim.transaction_id` survives the claimant's deletion, and FR8.3's collection-rate definition, which is annotated open to correction.
