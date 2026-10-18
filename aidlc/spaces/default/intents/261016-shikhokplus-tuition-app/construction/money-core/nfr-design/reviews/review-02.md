## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T05:20:06Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/money-core/nfr-design/security-design.md > A.6 "Behaviour while OQ-B1-1 is open" | A missing locale row fails at request time inside a consumer Unit, not at build time in B1; no B1 gate can fail on it — see note A | State where the missing-row failure surfaces and add a build-time gate in B1 that fails when a locale in the supported set has no specification row | Resolved (reviewer) |
| R-02 | Critical | construction/money-core/nfr-design/security-design.md > A.5 "Closure is the absence of a default" | The unrecognised-kind raise has no error class; functional-spec §5.6's refusal table is closed and does not contain it — see note B | Name the class the unrecognised-kind raise uses and reconcile it with BR1.8 and the §5.6 refusal table, or record the conflict for Functional Design to close | Resolved (reviewer) |
| R-03 | Major | construction/money-core/nfr-design/security-design.md > A.2 note on fixture shape | Fixtures live outside the linted paths, so the test proves the checker can fail, not that the shipped configuration covers the real tree — see note C | Require each fixture to be exercised under the same configuration that runs in CI, with the path scope asserted rather than bypassed | Resolved (reviewer) |
| R-04 | Major | construction/money-core/nfr-design/security-design.md > A.3 "What makes them unbypassable" | A money column declared as a raw SQL type string or a str-typed schema field reaches neither chokepoint and needs no banned import — see note D | Add a check that every money column and money schema field resolves to the chokepoint type, rather than relying on Gate 2 to catch the declaration | Resolved (reviewer) |
| R-05 | Major | construction/money-core/nfr-design/security-design.md > A.4 coverage configuration | Coverage scoped to the package is defeated by relocating a branch out of the package, which the design does not address — see note E | Pair the package-scoped target with a check that the module's public surface stays inside the measured package | Unresolved |
| R-06 | Minor | construction/money-core/nfr-design/security-design.md > Part D residual risk table | 12 worked cases is stated against entities.md's 8 worked scenarios, and the omitted residual is Gate 2's reach — see note F | Reconcile the worked-case count with entities.md and add the Gate-2-reach residual, or state why it is closed | Resolved (reviewer) |
| R-07 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/nfr-design/security-design.md > Part B "Where step 9 actually runs" | NFR9.30 is authored in B1 but executes from B2/B3, and neither Bolt's DoD in bolt-plan.md carries the obligation — see note B | Record the schema assertions as named per-Bolt obligations in B2's and B3's DoD, or state the amendment as required, the way the B1 DoD amendment is named in A.6 | New |
| R-08 | Major | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/nfr-design/security-design.md > A.4 item 3 and A.5 NFR9.28 | A statically-verified assertion still emits an uncovered branch, so the 100% gate fails while pragmas are banned — see note C | State the mechanism that reconciles them: either the exhaustiveness check emits no coverable statement, or name the one sanctioned coverage exclusion and how it is bounded | New |
| R-09 | Minor | aidlc/spaces/default/intents/261016-shikhokplus-tuition-app/construction/money-core/nfr-design/security-design.md > A.6 NFR9.26 | The supported-locale set NFR9.26 enumerates has no designated authoritative source, so it can drift from the locales the app offers — see note D | Name the single artifact that defines the supported set and have NFR9.26 read it, or record the drift as a residual in Part D | New |

> R-01 Reviewer note: A.6 now states the failure lands in a B6/B7/B10 handler; NFR9.26 adds the build-time check; the DoD-amendment path is named. Residual locale-set drift is raised separately as new

> R-02 Reviewer note: Assertion-not-raise is correct and grounded: functional-spec §5.6 has exactly 8 rows and BR1.8 states fatal "is an assertion, not a raise site" verbatim. Closure holds

> R-03 Reviewer note: NFR9.29 adds per-gate configuration assertions; both named failure modes (renamed path, widened exception) now fail on the breaking commit

> R-04 Reviewer note: The unbypassable claim is withdrawn and the three bypass paths tabulated; NFR9.30 adds both schema assertions. Its execution anchoring is a new defect, raised below

> R-05 Reviewer note: NFR9.31 relies on Gate 2's decimal ban, but the ledger fold composes Money operations and needs no decimal import — see note A

> R-06 Reviewer note: Count corrected to eight, matching entities.md line 320. The Gate-2-reach residual is added to Part D

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Upstream id coverage (manual) | PASS | 31 ids, 31 coverage rows, no missing or extra; every NFR9.x cited in security-design.md resolves to a row |
| Citation spot-check against source | PASS | §2.8 step 4, §5.6's eight rows, entities.md's eight worked scenarios and B1's unconditional format(locale) all verified as cited |
| Bolt DoD cross-check (bolt-plan.md B2, B3) | FAIL | Neither DoD carries NFR9.30; the B1 pipeline cannot execute it either |
| Module surface vs NFR9.31 (functional-spec §7 class model) | FAIL | DerivedQuantities folds entries into eight Money quantities using Money-only operations; no decimal import is required |

### Notes

**Note A — NFR9.31 does not close R-05.** The claim is that relocated money
arithmetic "needs the raw decimal import that Gate 2 already bans". That holds
only for arithmetic touching `Decimal` directly. The module's published surface
is `add`, `subtract`, `apply_rate`, `allocate`, `sum`, `is_zero`,
`is_positive` and `Money.ZERO` — all `Money`-to-`Money`. The ledger fold is
exactly this shape: `functional-spec.md` §7 defines `DerivedQuantities` as
eight `Money` quantities computed by folding entries by kind. A developer who
moves the carry-versus-waive fork, the partial-approval path or the
outstanding-per-cycle computation into a sibling `fee_math` module writes
`Money.sum(...)`, `a.subtract(b)` and `balance > Money.ZERO`, imports nothing
from `decimal`, and passes Gate 2 untouched. The relocated branches then sit
outside the covered package and the 100% target is met with them unexecuted —
the precise defeat R-05 named, and the one A.4 item 4 correctly describes
before prescribing a control that does not reach it. `apply_rate` does take a
`Decimal`, so rate-scaling relocation is caught; the fold, which is where the
branches actually live, is not. Closing this needs a positive check that the
module's branch-carrying surface stays inside the measured package, not a
reuse of the decimal ban.

**Note B — NFR9.30's split has no mechanism to fail.** The authored-in-B1,
executed-from-B2/B3 pattern is sound in principle and the U2 precedent cited
is real. But that precedent works because B2's DoD explicitly lists the
schema-wide privacy invariant. Here, `bolt-plan.md` B2's DoD enumerates the
committed OpenAPI file, the schema-diff gate, the error taxonomy, the
`*_display` sibling rule, money-as-JSON-string asserted on both sides, the
route harness and the privacy invariant — and not U1's money-pattern
assertion. B3's DoD enumerates the first Alembic migration and the
schema-iterating governance test — and not the money column type and
precision assertion. B1's own pipeline step 9 cannot run it, by the
document's own statement that B1 has neither a table nor an endpoint. So if
B2 and B3 simply never wire it up, every Bolt passes its stated DoD and the
assertion never exists. This is the same shape as the delivery-planning
learning about naming added scope on the receiving Unit rather than absorbing
it quietly, and A.6 already demonstrates the correct handling by naming the
B1 DoD amendment outright. NFR9.30 needs the same treatment in the other
direction.

**Note C — the no-pragma rule and the statically-verified assertion are not
yet reconciled.** NFR9.13 is a build gate and `project.md` forbids weakening
it. A.4 item 3 bans exclusion pragmas, then admits NFR9.28's assertion as
"the one sanctioned exception... accounted for by the type checker rather
than by a comment". Reasoning is not measurement: a coverage tool reports the
branch as uncovered regardless of what the type checker concluded, because the
two tools share no channel. As written, B1 faces a gate that cannot pass —
the assertion line is unexecuted, the measured figure is below 100%, and the
only standard remedy is the pragma the same section bans. The argument that
the branch is unreachable *because a stronger check guarantees it* is correct
and worth keeping; what is missing is how the coverage report comes to agree.
Two honest resolutions exist — structure the exhaustiveness check so it emits
no coverable statement, or name a single bounded exclusion and the assertion
that keeps it to one site — and the document should pick one. Left as is, the
next unreachable branch is smuggled through on the same "statically verified"
wording, which is the loophole the orchestrator correctly suspected.

**Note D — NFR9.26's locale set is prose, not a source.** The supported set is
cited as "Bangla and English [TC-15, NFR3]" and appears as prose in
`functional-spec.md` §2.8, `rules.md`, `tech-stack-decisions.md` and here. No
artifact is designated as the definition NFR9.26's enumeration reads. B1 is a
Python library; the locales the app actually offers are Android resource
qualifiers created in later Bolts. A third locale added as a `values-xx/`
bundle therefore fires nothing in B1, and the check asserts only that B1's own
list matches B1's own specification rows — self-consistency, not completeness.
For the V1 two-locale case this is adequate, which is why it is Minor rather
than blocking; the risk is that the check reads as stronger than it is.

### Summary

The two Critical findings are genuinely closed and the R-02 fix in particular
is well grounded in the functional spec's own wording. Three fixes introduced
or left open structural gaps: NFR9.31 reuses a control that does not reach the
`Money`-only ledger fold where the branches live, NFR9.30 is authored in a Bolt
that cannot execute it and inherited by Bolts whose DoD never names it, and
NFR9.28's sanctioned unreachable line has no stated path to satisfying a
coverage gate that bans pragmas. Each is a specific, checkable mechanism gap
rather than a matter of framing.
