## Review

**Verdict:** NOT-READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-18T05:14:36Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/money-core/nfr-design/security-design.md > A.6 "Behaviour while OQ-B1-1 is open" | A missing locale row fails at request time inside a consumer Unit, not at build time in B1; no B1 gate can fail on it — see note A | State where the missing-row failure surfaces and add a build-time gate in B1 that fails when a locale in the supported set has no specification row | New |
| R-02 | Critical | construction/money-core/nfr-design/security-design.md > A.5 "Closure is the absence of a default" | The unrecognised-kind raise has no error class; functional-spec §5.6's refusal table is closed and does not contain it — see note B | Name the class the unrecognised-kind raise uses and reconcile it with BR1.8 and the §5.6 refusal table, or record the conflict for Functional Design to close | New |
| R-03 | Major | construction/money-core/nfr-design/security-design.md > A.2 note on fixture shape | Fixtures live outside the linted paths, so the test proves the checker can fail, not that the shipped configuration covers the real tree — see note C | Require each fixture to be exercised under the same configuration that runs in CI, with the path scope asserted rather than bypassed | New |
| R-04 | Major | construction/money-core/nfr-design/security-design.md > A.3 "What makes them unbypassable" | A money column declared as a raw SQL type string or a str-typed schema field reaches neither chokepoint and needs no banned import — see note D | Add a check that every money column and money schema field resolves to the chokepoint type, rather than relying on Gate 2 to catch the declaration | New |
| R-05 | Major | construction/money-core/nfr-design/security-design.md > A.4 coverage configuration | Coverage scoped to the package is defeated by relocating a branch out of the package, which the design does not address — see note E | Pair the package-scoped target with a check that the module's public surface stays inside the measured package | New |
| R-06 | Minor | construction/money-core/nfr-design/security-design.md > Part D residual risk table | 12 worked cases is stated against entities.md's 8 worked scenarios, and the omitted residual is Gate 2's reach — see note F | Reconcile the worked-case count with entities.md and add the Gate-2-reach residual, or state why it is closed | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Upstream id coverage (manual) | PASS | All 25 NFR9.x appear in `upstream_ids` with a coverage row; no extras, none dropped. Confirms the dispatcher's own check |
| Dependency diagram against the DAG | PASS | `unit-of-work-dependency.md` declares `depends_on: [money-core]` for `api-contract`, `batches-and-enrollment` and `fee-cycles-and-ledger` only; U8 and U9 reach U1 transitively. The corrected diagram and the leaf claim are right |
| Mermaid parse and node declaration | PASS | Every edge endpoint is a declared node; text fallback present |

### Notes

**Note A — the loud failure is loud in the wrong Unit, and in the wrong phase.**
`contract-summary.md` §B.5 and the B1 DoD both pin the wire shape: where a screen
needs a formatted amount the response carries **both** `amount` and
`amount_display`, and `functional-spec.md` §2.8 step 4 repeats it. So the
formatting operation is called by whatever assembles a response in U7, U8 and U9
— not by U1. A missing Bangla row therefore raises inside a request handler in
B6, B7 or B10, against a Bangla-locale request, at runtime. The concrete
sequence: B1 ships green with the English row only; B6 ships green, because its
own tests exercise the English locale that exists; the first Bangla-locale
request to a fee-cycle endpoint raises, and under `team.md`'s error taxonomy an
unclassified raise from the money module surfaces as a 500. "Fails loudly" is
true and is still the right choice over a silent Latin-digit fallback, but the
document presents it as if the failure were contained in B1, which is what makes
it safe to defer. It is not contained: the document states the supported locale
set is finite and known (Bangla and English, TC-15/D-43), so B1 can assert at
build time that every locale in that set has a specification row — and that
assertion is exactly what would fail in B1 rather than in production. Without it,
OQ-B1-1 staying open past B1 converts a known gap into a latent runtime defect in
three later Bolts. The related conflict worth noting: the B1 DoD lists
`format(locale)` as a DoD item unconditionally, so "ship B1 without the
formatting operation" (the NFR Requirements fallback) does not satisfy B1's
stated definition of done.

**Note B — the closure raise has no class, and the error taxonomy is closed
against it.** A.5 requires that an unrecognised kind raises. BR1.8 states that
every refusal in this module raises a validation failure **and only** a
validation failure, and `functional-spec.md` §5.6 enumerates the refusal paths in
a closed table of eight rows — construction from a float, magnitude overflow,
mixed-type arithmetic, float/negative rate, allocate count below one, negative
ledger entry amount, non-canonical wire value, serializing a negative. An
unrecognised ledger kind is not among them. This matters beyond bookkeeping,
because BR1.8's reasoning is that every refusal here is *caused by the input
itself*, and an unrecognised kind is not a caller-supplied bad input: it is a
developer having extended the enumeration without extending the fold. Calling
that a validation failure maps it, through U2's taxonomy, to a 400/422 — telling
the client its request was malformed when the defect is in the code. `team.md`'s
own taxonomy calls that case a `FatalError` ("a bug"), and BR1.8 explicitly
rejects a fatal class here on the grounds that it is "an assertion, not a raise
site" — which is a defensible answer, but then the design must say that the
closure mechanism is an assertion rather than a raise, because the two have
different behaviour under optimized bytecode and different coverage obligations.
The design says "raises" and stops. A developer implementing A.5 against §5.6
cannot tell which class to use, and whichever they pick, one of the two documents
is wrong. This also interacts with the 100% branch coverage target: the
unrecognised-kind branch must be executable by a test, which requires some way to
present a kind the fold does not know — worth stating, since the enumeration is
closed and a test cannot simply add a value to it.

**Note C — the fixture proves the checker runs, not that the gate is
configured.** A.2's fixture design has the violating file living outside the
linted paths, with a test invoking the checker against it and asserting non-zero.
The failure mode that leaves open is precisely the one NFR9.6 exists to prevent.
Gate 2 is a banned-import rule scoped by path — banned-api on raw decimal
everywhere, re-permitted inside the module by a per-path exception. Suppose a
later refactor renames the module directory, or widens the re-permitting
exception from `app/money/**` to `app/**`, or the lint configuration's file
selection stops covering a newly added package. The fixture test still passes,
because it invokes the checker against a fixture path with whatever configuration
the test supplies, and the checker is perfectly capable of flagging that fixture.
Meanwhile the real tree is no longer covered. The design's own stated rationale —
"a later refactor of the lint configuration can neuter either gate with nothing
noticing" — is the exact scenario its fixture placement fails to close. What
would close it is asserting the property rather than the capability: run the
checker in its shipped configuration and assert that the fixture path is within
the set of paths that configuration selects, or place the fixture inside the
linted tree and exempt it by a single explicit, reviewable entry whose presence
the test asserts. The current shape makes "the tree is clean" and "the gate works"
non-contradictory by decoupling them, which is also what makes the second claim
stop implying anything about the first.

**Note D — the chokepoints are bypassable without any banned import.** A.3 rests
the unbypassability claim on "a model column either uses the decorator or it
declares its own type — which requires importing raw decimal outside the module,
which Gate 2 refuses." That inference holds only for a column declared through
the ORM's Python decimal type. Three paths reach a money column without importing
raw decimal anywhere:

- A raw SQL migration. Alembic migrations are ordinary Python that execute SQL
  text; `op.execute("ALTER TABLE enrollment ADD COLUMN fee_amount NUMERIC(10,2)")`
  declares a money column with too few digits, imports nothing from `decimal`,
  and both gates pass. `team.md` makes migrations a reviewed artifact, but the
  whole organising principle is that the important rules are mechanical, and the
  storage contract of twelve digits with two places (BR1.7, which construction
  enforces in memory) has no mechanical defender at the schema level.
- A string-typed column declaration. The ORM accepts a type given as a string in
  several declaration styles, so a column can be declared without the Python type
  object being imported at all.
- A schema field typed as `str` carrying a money value. A.3's claim that "a
  schema field either uses the money type or it is not a money field" is a
  definition rather than a check. An endpoint returning `total_display: str` or
  `amount: str` built by string formatting produces a field that is a money field
  in every sense a client cares about, passes the annotated-type chokepoint by
  never reaching it, and imports no decimal. Given BR5.4 mandates an
  `amount_display` string sibling on money-carrying responses, a `str`-typed
  money-adjacent field is not hypothetical here — it is the contract.

The fix is cheap and matches the project's existing idiom: U2 already iterates
the generated OpenAPI schema for the no-profile-field invariant, and the same
iteration can assert that every field matching the money pattern resolves to the
annotated chokepoint type; the storage half can be asserted by iterating the live
schema's columns for `NUMERIC` precision and scale, which U11 already does for
dispositions. Without something of that shape, "unbypassable" overstates what the
two chokepoints deliver, and it overstates it in the Unit whose blast radius
`logical-components.md` calls the largest in the product.

**Note E — coverage can be met by moving code, and the design names only
pragmas.** A.4 closes three specific escapes — global averaging, line-instead-of-
branch, and exclusion pragmas — and calls the pragma ban "the one that matters
most in practice". The escape it does not name is relocation: a branch moved out
of `app/money/**` into a neighbouring module stops being measured by a
package-scoped target, and the package's coverage can then read 100% while the
arithmetic it was protecting is partly uncovered. This is not an exotic bypass; it
is the natural consequence of combining a package-scoped measurement with a
backend whose 80% floor applies elsewhere, and it is likelier than a pragma
precisely because it looks like refactoring rather than like suppression. The
Gate 1 outward-import test does not catch it: moving a helper from `app.money` to
a new `app.money_utils` and importing it back creates an edge into a package that
is not API, persistence, repository, authorization or schema, so Gate 1 passes.
Note that A.4's own supplementary mechanism does not cover this either — the
named-test manifest asserts that named tests exist, not that the code under test
still lives in the measured package. A check that the module's public surface
(the operations `contract-summary.md` §E.1 enumerates) resolves to definitions
inside the measured package would close it, and is the same shape of check as
Gate 1.

**Note F — the residual table's arithmetic and its omission.** Two separate
points, both small:

- The "identity itself is wrong" row claims "12 worked cases and 20,000
  randomized histories". `entities.md`'s `verification_evidence` records "eight
  worked scenarios computed term by term" with the same 20,000 histories. One of
  the two numbers is wrong. 12 appears to have been carried over from the
  `team.md` correction about a reviewer's prescribed fix failing "four of twelve
  cases", which is a different count from a different exercise. This matters more
  than a typo would, because the residual-risk statement is the document a later
  reader consults to decide whether the identity needs re-verification, and
  `team.md` makes verifying-before-recording a standing rule for exactly this
  module.
- The omitted residual is Gate 2's reach. Every residual listed concerns
  something inside this Unit. But the control the document itself calls
  "the load-bearing one" is a backend-wide lint rule, and its reach is bounded by
  what the linter is configured to see — which does not include the Kotlin
  surface, raw SQL, or any Python added outside the configured source roots.
  Note D gives the concrete instances. A residual naming "money arithmetic in a
  surface Gate 2 does not scan" belongs in Part D, and its absence is what makes
  the table read as complete when the boundary has a stated edge. The four
  present residuals are otherwise the right ones.

### Summary

The dependency correction in `logical-components.md` is right and the leaf and
blast-radius reasoning holds. Two Critical findings block: the formatting
operation's "loud failure" lands at request time in U7/U8/U9 rather than at build
time in B1, with no gate capable of failing on it, and the unrecognised-kind raise
has no error class under a refusal taxonomy that functional-spec §5.6 closed
against it. Three Major findings concern mechanisms that assert less than the
document claims — fixtures that prove the checker rather than the configuration,
chokepoints bypassable by raw SQL or a `str`-typed field without any banned
import, and a package-scoped coverage target defeated by relocation.
