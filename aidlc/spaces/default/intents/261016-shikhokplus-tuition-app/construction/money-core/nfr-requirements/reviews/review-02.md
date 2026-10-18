## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T05:01:06Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | construction/money-core/nfr-requirements/traceability.json > coverage row NFR3 | NFR3 is marked N/A on the ground that this Unit owns no screen, but this Unit owns the only locale-sensitive rendering decision in the system (BR5.4/BR5.6) and that rendering has no stated verifier here — see note A | Change the NFR3 row to a partial binding and add a requirement in security-requirements.md Part C fixing the digit system and separator placement of the formatted string per supported locale, with a named test per locale | Resolved (reviewer) |
| R-02 | Major | construction/money-core/nfr-requirements/security-requirements.md > Part C, row NFR9.14–NFR9.15 | The stated verification is "named tests, enumerated in the test plan", but no test plan exists as a deliverable of this stage or of B1, so the mechanism cannot fail any build — see note B | Name the enumeration's home (the B1 DoD list of named tests, or a committed test-manifest asserted by a meta-test) so a missing named test fails CI rather than review | Resolved (reviewer) |
| R-03 | Major | construction/money-core/nfr-requirements/security-requirements.md > Part A, threat list T1–T5 | No threat covers the ledger vocabulary: the seven entry kinds are a closed set whose classification drives BR4.3, and a kind added or mis-sided in a later Unit silently falsifies the identity — see note C | Add a threat and a requirement that the kind set is closed and that adding or reclassifying a kind requires extending the property test before the kind is usable | Resolved (reviewer) |
| R-04 | Minor | construction/money-core/nfr-requirements/security-requirements.md > Part C, row NFR9.6 | Verification is given as "Unit DoD", which is a review-time check, unlike every other row that fails in CI — see note D | Make the deliberate-violation demonstration a committed negative test that runs in CI, as B2 and B4 already do for their gates | Resolved (reviewer) |
| R-05 | Minor | construction/money-core/nfr-requirements/security-requirements.md > Part B, row "Input sanitization against injection" | The N/A reason says the module's inputs are "numbers and a part count", omitting the two string inputs the module parses: the canonical wire string and the locale argument — see note E | Restate the row to name the string inputs and the rule that bounds each, rather than asserting there are no string inputs | Resolved (reviewer) |
| R-06 | Minor | construction/money-core/nfr-requirements/tech-stack-decisions.md > A.4 item 1 | The claim that 100% branch coverage is reachable rests on the dependency surface alone and omits the one dependency that does carry branches: the locale facility or pinned digit table of BR5.6 — see note F | Add the locale-data dependency to the A.4 reasoning and state that its branches are reachable by passing each supported locale value | Resolved (reviewer) |
| R-07 | Major | construction/money-core/nfr-requirements/security-requirements.md > Part A, NFR9.20 | Deriving generators from the kind enumeration catches an omitted kind but not a mis-sided one, if the test's expected side is read from the same `identity_side` field the fold reads — see note A | Require the property test's expected side to come from a source independent of the fold's, or add a named worked case per kind asserting its economic effect | New |
| R-08 | Minor | construction/money-core/nfr-requirements/security-requirements.md > Part C, NFR9.14–NFR9.15 manifest | The manifest check asserts an entry resolves to a test that exists and runs; it cannot assert the test asserts the right thing — see note B | State that each manifest entry names the acceptance criterion it discharges, so a vacuous test is visible as a mismatch rather than as a green row | New |
| R-09 | Minor | construction/money-core/nfr-requirements/security-requirements.md > OQ-B1-1, "Who closes it and when" | OQ-B1-1 names no blocking Unit and sits only in this Unit's artifact, unlike OQ-1..OQ-7 which each name theirs — see note C | Name the Units blocked (U7, U8, U9, the display-sibling consumers) and record it where the human tracks open questions, not only here | New |

> R-01 Reviewer note: NFR3 row flipped to OK targeting NFR9.22–NFR9.24; T7 added; reverse rows present for all three. The verifier now exists where none did

> R-02 Reviewer note: Verification is now a committed manifest with a CI check asserting each entry resolves to a running test. See prose — the residual gap is narrower and is raised as a new Minor

> R-03 Reviewer note: T6 plus NFR9.19–NFR9.21 added. Closure is now executable. See prose — the mis-siding half is incompletely closed and is raised as a new Major

> R-04 Reviewer note: NFR9.6 row now reads committed violation fixtures running in CI, matching B2 and B4

> R-05 Reviewer note: Row rewritten around absence of a sink; both string inputs named with entry constraints; explicitly declines to pre-authorise a third

> R-06 Reviewer note: A.4 item 1 names the locale facility as the exception, states branches are reachable by argument, and separates reachable from correct

### Notes

**Note A — NFR9.20 is sufficient against omission, not against mis-siding.**
The orchestrator asked this directly and the answer is that the mechanism is
half of a control. `entities.md` already carries `identity_side` and
`enrollment_identity_role` per kind, which is the right design — but it creates
a single source that both the fold and the test can read. The concrete failure:
OQ-2 settles, someone adds `refund` to `LedgerEntryKind` with
`identity_side: credit_reduces_obligation` when the correct economic treatment
is a reversal of `charge`. NFR9.20 is satisfied — the kind appears in generated
histories automatically. NFR9.21 is satisfied — a side was stated. But if the
property test computes its expected left-hand side by reading `identity_side`,
the test and the implementation agree by construction and BR4.3 balances
exactly, while every enrollment carrying a refund reads a wrong outstanding.
This is precisely the T4 pattern the document names: a test passing against two
implementations that disagree, except here it is a test that cannot disagree
with the implementation at all. The recorded learning behind BR4.8 — that this
project's identity was wrong twice and a reviewer's own prescribed fix failed
four of twelve cases — is the same failure mode: a plausible classification
nobody independently checked. The fix is cheap: either the property test's
expected side is hand-written per kind (so adding a kind forces a second,
independent judgement, and a disagreement is a test failure rather than a
silent agreement), or each kind carries a named worked case asserting its
effect on outstanding and available credit, which is what BR4.8 already demands
of the identity itself. NFR9.21's "MUST require stating which side" is a
process obligation with no mechanism; NFR9.20's mechanism does not cover it.
I am raising this Major rather than Critical because the omission case — by
far the more likely of the two, and the one R-03 named — is genuinely closed,
and because the gap is one sentence of specification rather than a redesign.

**Note B — the manifest closes the gap it was asked to close.** The
orchestrator's question is fair and the answer is mostly reassuring. A manifest
asserting tests exist does not assert they assert anything, so in the abstract
it moves the gap rather than closing it. But the gap it was raised against was
specific: BR4.6's multi-period carry test is invisible to the 100% branch gate
because the single-carry test already executes the same branches, so nothing
could tell it was missing. A manifest with a CI check does tell. What it still
cannot see is a manifest entry pointing at a test that runs and asserts
something trivial. That residual is real but much smaller, it is the general
limit of every named-test obligation rather than a defect introduced by this
fix, and `team.md` already rejects always-passing tests in review as defects in
their own right. Naming the acceptance criterion per entry would close most of
what remains at near-zero cost, which is why this is a Minor and not a reason
to reopen R-02.

**Note C — OQ-B1-1 is a legitimate open question, and the fallback is
viable.** Both halves of the orchestrator's question check out. On the
anti-pattern: `team.md` says the test is whether the answer needs judgement or
evidence nobody has yet, or merely needs someone to commit. Items 1 and 2 —
Bengali numerals versus Latin digits under a Bangla locale, and South Asian
2,2,3 grouping versus Western 3,3 — are product judgements about what a
Bangladeshi teacher reconciling fees by hand expects to see. That is judgement
nobody in this workflow holds, and the document is right that no default was
proposed. Contrast OQ-6 in `contract-summary.md`, which was correctly closed
because it carried a proposed default and merely needed commitment. This one
does not.

On the fallback: shipping B1 without the formatting operation is viable. U1 is
a `library` with no endpoint, the display sibling is consumed by U7, U8 and U9
which are all later Bolts, and §B.5 records which fields carry a sibling in the
schema — so an absent formatting operation in B1 is a missing function, not a
broken contract. The `/v1/` additive policy makes adding it later safe, and the
document's reasoning that a wrong rendering pinned into an installed client is
not withdrawable is correct. One caveat the artifact states and I am confirming
rather than disputing: nothing else in B1 depends on it, so the fallback costs
nothing structurally.

On NFR9.22–NFR9.24 against a wrong-but-plausible rendering: NFR9.24 defeats
pass-through, which was the named threat. NFR9.23's exact-output assertion
means the test cannot pass against a rendering that differs from the specified
one — but the specification is what OQ-B1-1 defers, so the three requirements
are correctly conditional on it closing rather than independently sufficient.
That is the right structure: they make the specification a precondition of
implementation rather than pretending to substitute for it. A wrong rendering
can still ship if the *human answers OQ-B1-1 wrongly*, which is a product risk
no NFR can carry.

**Nothing else material is missing from the NFR set.** I checked the usual
money-module gaps against this document: construction from float (NFR9.1),
decimal-from-float (NFR9.2), conversion escape (NFR9.3), the twelve-digit
storage overflow (BR1.7 upstream, bound by NFR9.10), rounding mode as a
declared constant (TS3), division not exposed and allocation exact-sum (BR2.9,
named in NFR9.15 as the worked instance), sign convention (NFR9.11), the two
chokepoints (NFR9.8, NFR9.10), both import mechanisms (NFR9.4, NFR9.5) with
fixtures (NFR9.6), and the client surface (NFR9.7, NFR9.9). The one upstream
correction mentioned in the dispatch — `rules.md` Part B's BR1.8 summary row
now reading one error class, consistent with Part A and `functional-spec.md`
§5.6 — is applied and consistent. I verified BR1.8's rationale independently:
three of the five taxonomy classes are structurally unreachable in a module
with no state and no I/O, so one class is correct rather than a simplification.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Sensor set (reported by orchestrator) | PASS ×5 | Structural checks pass. The findings above are about content the sensors do not read |
| traceability.json cross-check | PASS | 19 coverage rows, 24 reverse rows; every NFR9.x cited in security-requirements.md has a reverse row and vice versa; NFR9.19–NFR9.24 all present both directions; no dangling target |
| parseReviewerFindingsReport contract | Verified | Prior table requires ID matching R-[0-9]+ and Now from five literals; New table is four columns with optional ID; placeholder rows refused |

### Summary

All six prior findings are closed, and the three Major fixes close the gaps
they were raised against rather than restating them — NFR3 now has a verifier,
the named-test obligation now fails CI, and ledger closure is now executable.
One fix is incomplete in a way worth fixing before implementation: NFR9.20
catches a kind added and left off the identity but not one added and placed on
the wrong side, because the test and the fold can read the same
`identity_side` field and then agree by construction. That is a one-sentence
specification gap in a document whose whole argument is that a rule enforced by
review is a rule enforced by one stretched reviewer, so it belongs in the
document rather than in the implementer's head. The verdict is READY: one
Major and two Minor findings clear the threshold, and none of the three blocks
a developer from building from this.
