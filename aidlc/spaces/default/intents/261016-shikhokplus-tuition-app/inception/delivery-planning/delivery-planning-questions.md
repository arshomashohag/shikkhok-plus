# Delivery Planning — Questions

**Stage**: delivery-planning (2.9)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` and `unit-of-work-dependency.md`
- [upstream] `inception/contract-design/contract-summary.md` — open contract questions
- [upstream] `ideation/approval-handoff/initiative-brief.md` §6
- [team] the affirmed Way of Working, Walking Skeleton and Deployment practices

---

## How this stage was answered

Several of the stage's strategic questions were already settled by affirmed
practice or recorded state — solo build (so no team to allocate and no parallel
Bolts), serial execution, unit-major iteration, checkpoints enabled, and the
walking skeleton. Those were not re-asked. Three genuinely open economic
judgements went to the human; the rest went to a dispatched delivery lead with
those answers as settled input.

## Q1. Where should the gated-to-autonomous switch fall?

[Answer]: After B7 `payment-claims-and-verification` (U8). This is the direct
translation of the affirmed "gated through the payment slice, then autonomous"
onto the current unit list — the practice was written when the payment slice was
PU-6, and the unit list has since changed shape. The money and privacy write
surfaces stay gated; analytics, packaging and governance follow automatically.

## Q2. What worries you most about this build?

[Answer]: The privacy boundary — nothing a student or guardian writes reaching
any teacher, row-level security genuinely in force, no cross-teacher leak. This
shaped what the early Bolts are asked to prove: B2, B3, B5, B7 and B9 each carry
a falsifiable privacy hypothesis rather than a feature one.

## Q3. How big should one Bolt be?

[Answer]: One Unit per Bolt — eleven Bolts matching the Unit list exactly.
Construction is already unit-major with per-unit checkpoints, so this keeps the
plan and the runtime in step and makes each checkpoint a demonstration of one
coherent thing.

## Q4. Should a formal scoring model rank the work?

[Answer]: No, and the rationale artifact says so explicitly rather than silently
omitting it. Seven of eleven positions are DAG-forced; every V1 capability is
Must Have, so cost of delay is identical across all Bolts and the value axis is
constant; job sizes span one step. Scoring would dress up a decision the
geometry already made. The one genuinely free choice turned on a hard constraint
no score would have surfaced.

## Q5. Can Bolts run concurrently?

[Answer]: No. Serial, because this is a solo build and there is no second worker
— not because the DAG forbids it. The parallelisable sets recorded at Units
Generation describe reorderability, which is useful when an external dependency
slips, not simultaneity.

## Q6. What external work could hold this up?

[Answer]: Seven dependencies mapped with owner, lead time, blocked Bolt and
fallback. Three want resolving before Construction starts rather than when their
Bolt arrives: the SMS vendor, the Play account type, and OQ-5. Lead times are
recorded as unknown where they genuinely are.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- **Eleven Bolts, one Unit each, serial.** Validated as a topological order
  against the DAG: no violations, and exactly three positions where the DAG left
  genuine freedom. The other seven are forced.
- **B3 `identity-and-access` is the walking skeleton**, with its own human
  checkpoint before later Bolts start.
- **`release-packaging` moves early, to position 4**, on a dependency the DAG
  does not carry: U5's latency obligation is dischargeable only by a
  Macrobenchmark, and that harness belongs to U10. The Play-clock argument is
  secondary.
- **`privacy-and-governance` stays terminal, but its mechanism moves to B3** —
  the manifest pair and the schema-iterating test, so every table-creating Bolt
  must carry its dispositions or CI reddens. This grows B3, already the largest.
- **No WSJF scoring**, with the reasoning recorded rather than the omission
  being silent.
- **No team to allocate**; the allocation artifact says so plainly instead of
  inventing roles.
- **Schedule: 10–16 weeks of build**, against the Ideation range of 8–12 —
  which sits on the optimistic side of a straightforward sum and excluded the
  analytics dashboard now in the plan. Best re-stated after B2, when the first
  real velocity data exists.
- **Three items flagged for the human, not decided**: re-gating B11 against the
  settled gating decision, starting SMS vendor selection now, and resolving the
  Play account type before Construction.

[Answer]: Looks correct
