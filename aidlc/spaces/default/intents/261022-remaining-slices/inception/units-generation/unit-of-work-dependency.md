# Unit Dependency Topology

**Stage**: units-generation (2.7)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **Topology only.** This states what *can* depend on what. The build order
> was chosen at Delivery Planning on 2026-10-22 and is not restated here.

## Sources

- [upstream] `inception/units-generation/unit-of-work.md`
- [upstream] `inception/domain-design/components.md` — ADR-014's two queries
- [prior] the approved re-cut

---

## The edge block

Construction walks its Units from this block.

```yaml
units:
  - name: signing-up-and-joining
    kind: service
    depends_on: []
  - name: running-a-batch
    kind: ui
    depends_on: [signing-up-and-joining]
  - name: collecting-fees
    kind: service
    depends_on: [running-a-batch]
  - name: teaching-and-recording
    kind: service
    depends_on: [running-a-batch]
  - name: knowing-how-it-is-going
    kind: service
    depends_on: [collecting-fees, teaching-and-recording]
  - name: releasing-safely
    kind: spec
    depends_on:
      - signing-up-and-joining
      - running-a-batch
      - collecting-fees
      - teaching-and-recording
      - knowing-how-it-is-going
```

## The shape

```
D1 signing-up-and-joining          [root — nothing works until an account exists]
 └─> D2 running-a-batch
      ├─> D3 collecting-fees        ─┐
      └─> D4 teaching-and-recording ─┘ mutually independent
           └─> D5 knowing-how-it-is-going   [needs both]
                └─> D6 releasing-safely     [terminal, release-blocking]
```

Four units — `money-core`, `api-contract`, `identity-and-access`,
`batches-and-enrollment` — are merged. Every unit above depends on all four,
and those edges are omitted so the graph describes what remains.

## Why each edge exists

| Edge | Why |
|---|---|
| D1 → D2 | D2's roster shows acceptance state, which D1 creates. Its screens also need an account that can sign itself up. |
| D2 → D3 | A fee cycle is generated per enrollment, and D2 is where enrollments become manageable through the UI. |
| D2 → D4 | A session's attendance is recorded against a roster. |
| D3, D4 → D5 | Insights read fees (D3) and the next upcoming exam (D4). Both, not either. |
| all → D6 | The schema-iterating governance test is vacuous until the last table exists, and the generated privacy policy needs every disposition. |

## What is NOT an edge, and why that matters

**D3 and D4 are mutually independent.** Nothing in attendance reads a fee and
nothing in fees reads attendance. Either may be built first.

**D1 → D2 is not a schema edge.** D2 creates no table. It is a capability
edge: D2's roster cannot show a state that does not yet exist.

---

## The prerequisite the graph cannot express

**This is the one thing worth reading in this file.**

A dependency graph records data and call dependencies. A **tooling
prerequisite** is a third kind it does not express, and this project has now
been bitten by the same one twice.

D4's mid-class latency obligation [PU-3.6, TC-17] is dischargeable **only** by
a Macrobenchmark on a low-end device profile — the affirmed testing posture is
explicit that a Compose correctness test does not discharge a performance
requirement. That harness belongs to release packaging, whose remaining half
sits in **D5**, after D4.

So the graph says D4 before D5, and the obligation says the harness before D4.

**The resolution, taken by the human on 2026-10-23: no harness.** PU-3.6
carries an explicit named manual pilot check instead — timing a full batch's
attendance on a low-end device during the pilot, with the result recorded.

This stage first closed it the other way, moving the harness to D4's start,
and that was an overstep: the approved plan framed it as a live two-way choice
and said both were acceptable, and adding a benchmarking harness to an XL unit
is a cost that wants a person's agreement rather than an agent's reasoning.

**The prerequisite therefore dissolves rather than being scheduled.** With no
harness, nothing D4 needs lives in D5, and the inversion the graph could not
express stops existing. What remains non-negotiable is that a Compose
correctness test does not discharge a performance obligation.

---

## Another prerequisite, smaller

**D1 must land ADR-014's two query changes, or every later unit inherits an
open exposure.** The decision columns without the predicates are columns
nobody reads, and `GET /v1/me` would go on counting unaccepted seats. It is
not an edge — nothing downstream *reads* the predicates — but every unit after
D1 assumes the lens model is sound, and the adversarial test ADR-014 names is
what makes that assumption safe to rely on.

---

## Validated

Six units, every `depends_on` declared, no self-dependency, single root,
acyclic. The longest chain is D1 → D2 → D3 → D5 → D6, five units.

## Assumptions & Open Questions

- **Assumed**: D3 before D4, as Delivery Planning chose, because the fee model
  is known to be in revision [D-18] and pinning its arithmetic early is what
  makes the revision cheap. The graph permits either order.
- **Settled by the human, 2026-10-23**: no Macrobenchmark harness in V1.
  PU-3.6 takes a named manual pilot check, and the ordering problem dissolves
  with the harness.
