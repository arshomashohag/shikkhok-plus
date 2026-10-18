<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations

- 2026-10-18 — The stage is explicit that 2.7 produces topology only and must not pick a build order or a critical path — those are Delivery Planning's economic calls. That line matters here because Ideation already published a PU dependency order with a named critical path, and the temptation is to transcribe it. This stage restates what *can* depend on what; 2.9 decides what ships first.
- 2026-10-18 — Ideation's PU-1..PU-8 are capability groupings, not Units. The real decision this stage owns is how the two surfaces (FastAPI backend, Compose Android client) interact with that grouping, because a Unit is what Construction builds and reviews as one piece.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs

- 2026-10-18 — Dispatched the decomposition decision to an architect with the binding constraints stated rather than deciding it inline: `team.md`'s Walking Skeleton is already scoped to PU-1 as one working slice, so a decomposition splitting the skeleton across two Units would contradict an affirmed practice rather than merely being inconvenient.

- 2026-10-18 — The reviewer returned NOT-READY on a Critical finding that was exactly the question I had flagged in the dispatch: U3's "stands alone at runtime" claim. Lens resolution *reads* Ownership and Enrollment, so those tables must exist for the resolver to query even when they return nothing — empty is not the same as absent, and a query against a missing table fails. U3's stated migration covered only identity tables, so as scoped the skeleton could not have run end to end. Fixed by making U3's first migration create `Owner` and `Enrollment` as empty structures it reads and never writes.
- 2026-10-18 — Deliberately did NOT add a `U3 -> U4` edge for that. The dependency runs the other way; U3 creating two empty tables it only reads is not a dependency on U4's code, and the edge would have made the graph cyclic while describing nothing real. The fix is a scope item, not a topology change.
- 2026-10-18 — The Major finding was that splitting Teaching into U5 and U6 appeared to reopen ADR-008, which had rejected a three-way component split because it would duplicate the concurrency rule. The reviewer suspected it was defensible and said so rather than overclaiming. Verified against the entity table: `attendance_version` and `client_mutation_id` sit only on Session and Attendance (U5), while Mark carries `superseded_by_id` — correction history, a different mechanism. So the rule has one home and is not duplicated. The split was right; the artifact had simply never defended it against an explicit ADR, which is its own defect.
- 2026-10-18 — A Unit boundary is a delivery boundary, not a component boundary. That distinction was implicit and is now written down, because a reader comparing the Unit list against the component catalogue will otherwise read every split as a contradiction.

- 2026-10-18 — Burned four attempts recording the review verdict by guessing at the engine's findings-table format instead of reading `.claude/aidlc-common/protocols/stage-protocol-reviewer.md`. The contract is explicit: New-findings tables take exactly four columns with no ID and no Status, because the engine assigns R-NN itself, and oversized Note cells break the parse. I added precisely the columns it forbids. Reading the spec first would have cost one minute.

## Open questions

- 2026-10-18 — Carried in and still unowned: PU-8.2, the teacher analytics dashboard, is marked Must with no defined content. A Unit cannot be sized or built against an undefined deliverable.
- 2026-10-18 — Carried in from Domain Design: whether `PaymentClaim.transaction_id` survives the claimant's deletion (U2 in the disposition manifest). It is a product and legal judgement, not a design choice.
