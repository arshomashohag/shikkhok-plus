# NFR Design Questions — money-core (U1)

**Stage**: nfr-design (3.3)
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`
**Phase**: Construction
**Depth**: Comprehensive

> NFR Requirements stated **what** must hold — 25 requirements across seven
> threats. This stage designs **how**: the concrete mechanisms, where each
> lives, and what fails when each is violated. For a library Unit that means
> build-time and test-time machinery, not runtime infrastructure.

---

## Q1 — The two import-boundary mechanisms: what exactly checks what?

NFR9.4 and NFR9.5 require two independent checks, and NFR9.6 requires each to
ship with a committed fixture that violates it.

[Answer]: They are deliberately different in **direction**, which is why two
are needed rather than one. The first is an **outward** check — the money
module must not import from the API, persistence, repository, authorization or
schema layers — implemented as a test that walks the module's own import graph
and fails the build on any edge into those packages. The second is an
**inward** check on the rest of the backend: raw decimal arithmetic may not be
imported anywhere outside this module, implemented as a banned-import lint
rule with the module itself re-permitted by an explicit per-path exception.

The first catches "someone gave the money module a database session"; the
second catches "someone did fee arithmetic in a route handler". Neither
catches the other's case, which is the whole reason for having both.

Each ships a committed fixture that violates it, asserted to fail, running in
CI on every push — so a later refactor of either rule's configuration cannot
silently neuter the gate.

---

## Q2 — Where do the two serialization chokepoints physically live, and what makes them unbypassable?

NFR9.8 and NFR9.10 require one API chokepoint and one storage chokepoint, each
the only path for a money value.

[Answer]: The API chokepoint is **one annotated type reused by every schema**,
not a per-field serializer. The storage chokepoint is **one type decorator
mapping to the fixed-point column**, not a per-model column declaration. The
unbypassability comes from there being nothing else to reach for: a schema
field either uses the annotated money type or it is not a money field, and a
model column either uses the decorator or it declares its own type — which the
inward import check of Q1 then catches, because declaring a decimal column
outside the module needs the banned import.

**Why per-field serializers were rejected**: they work until one endpoint
forgets, and a forgotten serializer is invisible in review because the field
still renders. One annotated type cannot be forgotten, because forgetting it
means not having a money type at all.

---

## Q3 — How is the 100% branch coverage target configured so it cannot be met dishonestly?

NFR9.13 makes it a build gate; `project.md` forbids weakening a coverage floor
to make a step pass.

[Answer]: Branch coverage scoped **to this module's package specifically**,
not a global average — a global figure lets a well-covered module elsewhere
mask a gap here. Configured to fail the build below 100%, with **no exclusion
pragmas permitted in this package**: an inline coverage-exclusion comment is
the standard way a 100% target is quietly defeated, and banning them is what
keeps the number honest. If a line genuinely cannot be covered, that is a
design signal (the dead-branch case the Functional Design review caught), not
an occasion for an exclusion.

The supplementary obligations of NFR9.14 and NFR9.15 ride alongside as the
named-test manifest with its per-entry acceptance criterion, because coverage
measures whether branches executed, never whether the right tests exist.

---

## Q4 — How is the ledger vocabulary closed executably, and how does the property test stay independent of it?

NFR9.19–NFR9.21 and NFR9.25 together.

[Answer]: Closure is a **total mapping from kind to its effect on the fold**,
written so that an unrecognised kind raises rather than falling through to a
default. No `else: pass`, no `.get(kind, zero)` — the absence of a default is
the mechanism. The property test's generators derive their kind set from the
enumeration, so a kind added later automatically appears in generated
histories.

Independence comes from the test carrying a **hand-written expected effect per
kind** — a named worked case asserting what that kind alone does to
outstanding and to available credit — rather than reading the shared
`identity_side` field. That is the one thing capable of disagreeing with a
wrongly-sided kind, and it is why the generator derivation alone is only half
the control.

---

## Q5 — What is the design for the formatting operation, given its rendering is unspecified?

OQ-B1-1 leaves digit set, grouping, separators and currency symbol open.

[Answer]: Design the **shape** now, defer the **table** until OQ-B1-1 closes.
The operation takes a locale argument and dispatches over a per-locale
rendering specification held as data — digit map, grouping interval, grouping
separator, decimal separator — rather than as branching code. Two consequences
make this the right shape regardless of how OQ-B1-1 is answered: adding or
correcting a locale is a data change rather than a code change, and each
locale's expected output test (NFR9.23) reads naturally as a row beside its
specification.

If OQ-B1-1 is still open when the rest of B1 completes, the operation ships
with the English specification only and the Bangla row absent — which fails
loudly for a Bangla locale rather than silently falling back to Latin digits.
**That failure mode is deliberate**: it is the difference between a missing
feature and a wrong rendering shipped to installed phones.

---

## Q6 — Does a library Unit have anything meaningful to say in `logical-components.md`?

The stage describes it as infrastructure components, failure domains and blast
radius — none of which a library has.

[Answer]: It has one genuinely useful thing: **the blast radius of this module
is the entire financial surface of the product**, because every money value in
every Unit passes through it. That is worth stating precisely rather than
omitting as not-applicable, because it is the justification for every
disproportionate-looking control in this Unit — the 100% coverage, the two
import gates with fixtures, the property test, the named-test manifest.

The document therefore records: the module's logical position (a leaf
dependency with no outward edges), its consumers (every Unit that touches
money), its failure mode (silent wrong arithmetic rather than an outage), and
the isolation property that makes the controls achievable (no I/O, no state,
no configuration). It explicitly records no service boundary, no scaling unit
and no failure domain, with the reason.

---

## Q7 — What does this Unit contribute to the CI pipeline, and in what order?

B1 establishes tooling every later Bolt inherits.

[Answer]: Ordered by cost, cheapest first, so a cheap failure never waits
behind an expensive one: secrets scan and lockfile verification, then format
and lint (including the inward banned-import rule), then type checking, then
the unit tests with coverage, then the property test. The two import-boundary
fixtures run inside the test step. All of it behind **one entrypoint runnable
identically locally and in CI**, because `team.md` names a gate reproducible
only by pushing as a gate that gets bypassed.

The property test is last because it is the slowest and the most likely to be
the thing a developer is iterating on when something else is already broken.

---

## Assumptions & Open Questions

**OQ-B1-1 remains open**, carried from NFR Requirements: the Bangla money
rendering is unspecified — digit set, grouping interval, separators, currency
symbol. Q5 above designs around it rather than guessing it.

---

## Consolidated Summary Confirmation

The two import gates are deliberately opposite in direction — one stops the
module importing I/O, the other stops the rest of the backend doing money
arithmetic — and each ships a committed failing fixture. The two chokepoints
are one annotated type and one column decorator, unbypassable because there is
nothing else to reach for. Coverage is scoped to this package with **no
exclusion pragmas permitted**, since a pragma is how a 100% target is quietly
defeated. The ledger vocabulary closes by a total mapping with no default, and
the property test keeps a hand-written expected effect per kind so it can
disagree with a wrongly-sided one. Formatting is designed as per-locale data
rather than branching code, shipping without the Bangla row if OQ-B1-1 is
still open — failing loudly rather than falling back to Latin digits. The
logical-components document records that this module's blast radius is the
product's whole financial surface, which is what justifies its controls. CI
runs cheapest-check-first behind one entrypoint usable locally and in CI
alike.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
