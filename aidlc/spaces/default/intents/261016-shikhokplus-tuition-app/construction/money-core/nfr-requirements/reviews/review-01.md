## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T04:56:01Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | construction/money-core/nfr-requirements/traceability.json > coverage row NFR3 | NFR3 is marked N/A on the ground that this Unit owns no screen, but this Unit owns the only locale-sensitive rendering decision in the system (BR5.4/BR5.6) and that rendering has no stated verifier here — see note A | Change the NFR3 row to a partial binding and add a requirement in security-requirements.md Part C fixing the digit system and separator placement of the formatted string per supported locale, with a named test per locale | New |
| R-02 | Major | construction/money-core/nfr-requirements/security-requirements.md > Part C, row NFR9.14–NFR9.15 | The stated verification is "named tests, enumerated in the test plan", but no test plan exists as a deliverable of this stage or of B1, so the mechanism cannot fail any build — see note B | Name the enumeration's home (the B1 DoD list of named tests, or a committed test-manifest asserted by a meta-test) so a missing named test fails CI rather than review | New |
| R-03 | Major | construction/money-core/nfr-requirements/security-requirements.md > Part A, threat list T1–T5 | No threat covers the ledger vocabulary: the seven entry kinds are a closed set whose classification drives BR4.3, and a kind added or mis-sided in a later Unit silently falsifies the identity — see note C | Add a threat and a requirement that the kind set is closed and that adding or reclassifying a kind requires extending the property test before the kind is usable | New |
| R-04 | Minor | construction/money-core/nfr-requirements/security-requirements.md > Part C, row NFR9.6 | Verification is given as "Unit DoD", which is a review-time check, unlike every other row that fails in CI — see note D | Make the deliberate-violation demonstration a committed negative test that runs in CI, as B2 and B4 already do for their gates | New |
| R-05 | Minor | construction/money-core/nfr-requirements/security-requirements.md > Part B, row "Input sanitization against injection" | The N/A reason says the module's inputs are "numbers and a part count", omitting the two string inputs the module parses: the canonical wire string and the locale argument — see note E | Restate the row to name the string inputs and the rule that bounds each, rather than asserting there are no string inputs | New |
| R-06 | Minor | construction/money-core/nfr-requirements/tech-stack-decisions.md > A.4 item 1 | The claim that 100% branch coverage is reachable rests on the dependency surface alone and omits the one dependency that does carry branches: the locale facility or pinned digit table of BR5.6 — see note F | Add the locale-data dependency to the A.4 reasoning and state that its branches are reachable by passing each supported locale value | New |

### Notes

**Note A — NFR3.** `traceability.json` marks NFR3 N/A because this Unit "owns no
screen, no string resource and no layout". That is true and not the whole
requirement. NFR3's substance is that Bangla rendering is correct, and BR5.4
places digit rendering and separator placement in this module precisely so the
client never decides them; `contract-summary.md` §B.5 confirms the client renders
`amount_display` and never formats the canonical value. So the one decision NFR3
cares about most on the money surface — whether `1500.00` renders as `১,৫০০.০০`,
as `১৫০০.০০`, or as Latin digits under a Bangla locale — is made in this Unit and
nowhere else. The concrete failure: `format("bn")` is implemented as a pass-through
of the canonical string. Every requirement in `security-requirements.md` passes,
100% branch coverage passes (the branch executes), the import checks pass, the
schema-diff gate passes, and the Bangla screens ship Latin digits in V1 with no
check anywhere able to fail. Neither this document nor `rules.md` states what the
Bangla output is, so there is no assertion to write. Note that `rules.md` BR5.1
does pin the *wire* form to Latin digits — it is only the display string, the
thing NFR3 is about, that is unpinned.

**Note B — NFR9.14/NFR9.15.** Part C's closing claim is that "every row above
fails in CI rather than in review". This row does not. "Enumerated in the test
plan" names an artifact that this stage does not produce and that `bolt-plan.md`
B1 does not list as a deliverable; B1's DoD says "named test per fee-cycle and
payment state transition; documented boundary case per money input" in prose. A
missing named test — say, the multi-period carry test BR4.6 insists on over the
single-carry one — reduces coverage not at all, because the single-carry test
already executes the same branches. So the omission is invisible to the 100%
gate and visible only to a reviewer who remembers the list. That is exactly the
"rule enforced by review" shape `team.md` says to avoid, in the document that
claims to have avoided it.

**Note C — the ledger vocabulary.** BR4.3's identity reads the kinds by name:
`charged`, `forgiven`, `receipt`, `credit_grant`, `outstanding`,
`credit_apply`, and the two carry kinds that deliberately do not appear. The
identity is only true because each kind sits on a known side. `entities.md`
treats the seven kinds as a closed set, but nothing in the NFR artifacts makes
closure enforceable or makes an addition fail. The concrete failure is already
foreseen in this project's own plan: B10 carries OQ-2, the collection-rate
definition, whose resolution is expected to extend this module's property test
(`functional-spec.md` §5.1 says "this Unit's test is where that extension
lands"). A later Unit that adds an eighth kind — a discount, an adjustment, a
refund — and folds it into neither side of BR4.3 produces an identity that still
balances across the six it knows about while every enrollment holding the new
kind is silently wrong. The property test, generating only the kinds it was
written for, never produces such a history, so it passes. T1–T5 cover floats,
import escape, wire precision, weak tests and dependencies; this is a sixth
threat of the same family — a silent wrong number with no error signal — and it
is the one with a scheduled trigger date.

**Note D — NFR9.6.** Every other row in Part C names a build or CI mechanism.
This one names "Unit DoD", which means a person confirming at the gate that the
gate was once watched failing. B2's and B4's confidence hypotheses in
`bolt-plan.md` both make their deliberate-violation fixtures part of the shipped
test suite; B1's import-boundary checks are the earliest and most load-bearing
gates in the project and are held to a weaker standard than the ones that come
after. A committed fixture that is expected to fail the check keeps the
demonstration true after the first commit, which is where the risk actually
lives: a later refactor of the Ruff `per-file-ignores` or the import-linter
contract can silently neuter the check, and nothing re-demonstrates it.

**Note E — injection row.** The row's reason is stated as a property of the
input types, and the property is wrong. §2.10 parses an incoming canonical
string, and §2.8 takes a locale argument. Neither is a sanitization risk in the
usual sense, and the N/A is defensible — but it is defensible because the wire
string is pinned to `^[0-9]+\.[0-9]{2}$` and rejected otherwise, and because the
locale set is finite and known (BR5.6), not because the module takes no strings.
As written, the row states a false premise, and a later reader extending the
module with a third string input (a formatting pattern, a parse of a
user-supplied amount) will read this row as covering it.

**Note F — A.4.** A.4 lists "the language's locale facilities" in the dependency
surface and then argues 100% coverage is reachable because "there is no I/O
branch that needs a mock, and no configuration branch that needs global state".
BR5.6 explicitly contemplates "a pinned data table declared as an ordinary
dependency" as an alternative to the runtime's locale facilities. Whichever is
chosen carries per-locale branches, and those are the branches most likely to go
uncovered if only one locale is ever passed in a test. The reasoning is right but
incomplete, and the incompleteness points at exactly the branch note A says has
no assertion behind it.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Sensor set (reported by orchestrator) | PASS ×5 | Structural checks pass; every NFR has a coverage row with a justification string. The findings above are about the content of those justifications, which no sensor reads |

### Summary

The integrity framing is correct and the N/A reasoning in Part B is sound in
eight of nine rows — this is not a security document that skipped the analysis.
Three gaps survive into implementation: the locale display string, which this
Unit uniquely owns, has no stated output and no verifier despite NFR3 being
marked N/A; two Part C rows verify by review while the document claims none do;
and the closed ledger vocabulary, whose extension is already scheduled for B10,
has no threat and no mechanism protecting it.
