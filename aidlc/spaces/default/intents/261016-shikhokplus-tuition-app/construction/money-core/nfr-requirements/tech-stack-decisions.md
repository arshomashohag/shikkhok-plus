# Tech Stack Decisions — `money-core` (U1)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> Almost everything here was decided upstream. This document **records those
> decisions with the reasoning that binds them to this Unit**, rather than
> re-opening them. One decision is genuinely made at this stage: the
> property-based testing library, and `team.md` already names it.

## Sources

- [stage] `nfr-requirements-questions.md` — Q5 (dependency policy), Q7 (what
  is actually open)
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [upstream] `inception/domain-design/decisions.md` — ADR-002
- [upstream] `construction/money-core/functional-design/rules.md` — BR3.1,
  BR5.3, BR6.1–BR6.4
- [upstream] `inception/requirements-analysis/requirements.md` — NFR9, NFR17
- [team] `## Code Style`, `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. The decisions

| # | Decision | Where it was made | Why it binds this Unit |
|---|---|---|---|
| TS1 | **Python 3.12**, backend language | Upstream, project-wide | Its standard library carries exact decimal arithmetic with explicit rounding control, which is the whole substrate of this module |
| TS2 | **Native fixed-point decimal** as the wrapped type | NFR9, TC-7, D-20 | The only exact option. A float is forbidden; a scaled integer would push the scale into every caller |
| TS3 | **`ROUND_HALF_UP`**, declared once as a module constant | BR3.1 | See A.1 — this is a decision, not a default |
| TS4 | **`NUMERIC(12,2)`** storage mapping via one type decorator | BR5.3, §B.5 | Ten integer digits and two decimals; one mapping so no model declares its own |
| TS5 | **JSON string** on the wire, pattern `^[0-9]+\.[0-9]{2}$` | §B.5, NFR9 | A JSON number is a double in most parsers |
| TS6 | **Kotlin `@JvmInline value class`** over `BigDecimal` | §E.1 | Compile-time rejection of a float, with no custom lint rule |
| TS7 | **kotlinx.serialization** with a string-only serializer | §E.1 | Rejects a JSON number at decode rather than coercing |
| TS8 | **Ruff** (format + lint), **mypy** strict over this module | team.md Code Style | See A.2 |
| TS9 | **pytest** for unit tests | team.md Testing Posture | Project standard |
| TS10 | **Hypothesis** for the property-based ledger test | team.md Testing Posture | See A.3 — the one decision this stage actually makes |
| TS11 | **No database, no ORM, no HTTP client, no date library** | Q5, BR6.1 | See A.4 |

### A.1 — Why the rounding mode is a decision and not a default

Python's decimal default is `ROUND_HALF_EVEN` (banker's rounding). That is
**wrong for consumer-facing BDT fee amounts**: a teacher checking arithmetic
by hand expects a half to round up, and banker's rounding sends `0.005` to
`0.00` and `2.5` to `2`.

The two modes genuinely diverge — at three of five sampled halves in the
worked table at `functional-spec.md` §5.2. On a single value the difference is
one paisa and invisible; across a ledger it is a reconciliation discrepancy
nobody can explain.

**This is invisible once chosen and expensive to change after a ledger
exists**, which is exactly why it is declared once as a module constant rather
than passed at each call site. Alternative rejected: leaving the ambient
default and documenting it. Rejected because the ambient default is wrong, and
documentation does not round numbers.

### A.2 — Why strict typing is scoped, and why the global baseline matters

`team.md` sets `disallow_untyped_defs = true` globally with three strict
islands, this module among them. The global baseline is what makes partial
strictness coherent rather than decorative: strictness is mostly a property of
what a module can *see*, so strict-on-this-module while it imports unchecked
code yields either a wall of untyped-call errors silenced with ignores, or
untyped values flowing in from the unchecked side so strict mode checks
nothing of consequence.

Because this module imports nothing from the un-strict region [BR6.1], its
strict settings are genuinely local and genuinely effective. **The
architectural rule buys both the type story and the money boundary with one
constraint.**

### A.3 — Hypothesis, the one open decision

The ledger identity cannot be established by worked examples. This project's
own history is the argument: the identity was **wrong twice** before
randomized testing settled it, and both wrong forms satisfied their own
examples. What catches that class of defect is composing the operations in
arbitrary order over many generated histories.

Hypothesis is chosen because it is the established property-based testing
library for Python, `team.md` already names it, and it integrates with pytest
with no additional runner. It is a **test-only dependency** and therefore does
not enter the module's runtime dependency surface under TS11.

Alternative considered: hand-rolled randomized loops. Rejected — they provide
no shrinking, so a failure reports a 200-entry history rather than the
three-entry minimal case, which is the difference between a diagnosable
failure and an intimidating one.

### A.4 — The empty dependency surface is the point

This module depends on the language's decimal arithmetic, its locale
facilities, and the type/serialization annotations for the two chokepoints.
Nothing else.

That is not minimalism for its own sake. Three properties rest on it directly:

1. **100% branch coverage is reachable** — there is no I/O branch that needs a
   mock, and no configuration branch that needs global state mutated in a test.

   **One dependency does carry branches, and it is the exception worth
   naming**: the locale facility (or pinned digit table) behind the formatting
   operation. Its branches are reachable, because the supported locale set is
   finite and known and the locale arrives as an argument rather than from
   configuration [BR5.6] — so every branch is exercised by passing a value.
   But *reachable* is not *correct*: coverage proves the formatting branch
   executed, not that it emitted the right digits. That gap is what
   NFR9.22–NFR9.24 exist to close, and it is recorded as OQ-B1-1 because the
   rendering itself is still unspecified. **This is the one place where the
   coverage number alone would be misleading**, and the reason the coverage
   target is supplemented by named-output tests rather than trusted on its
   own.
2. **The module is buildable and fully testable before any endpoint exists**,
   which is what makes B1 viable as the first Bolt. [B1 DoD]
3. **The CVE surface is near zero**, so the supply-chain risk this Unit
   carries is about the tooling it establishes for later Bolts rather than
   about itself.

A dependency that drags in I/O breaks all three simultaneously, which is why
NFR9.17 requires an explicit admission note rather than treating a new
dependency as routine.

---

## B. Alternatives rejected

Recorded because a reader a year from now will wonder, and because
`inception.md` requires trade-off analysis on architectural choices.

| Alternative | Rejected because |
|---|---|
| **Scaled integers** (store paisa as `int`) | Exact and fast, but pushes the scale into every caller — a bare `150000` is ambiguous between Taka and paisa at every boundary, and the one place it is misread is a 100× error. The decimal type carries its own scale |
| **A third-party money library** | Adds a dependency to the one module whose near-empty surface is load-bearing (A.4), for behaviour that is roughly 200 lines here. Most such libraries also carry multi-currency machinery this system has no use for [BR1.4] |
| **Float with careful rounding** | Forbidden outright by `project.md`, and the "careful" part is exactly what fails silently |
| **`ROUND_HALF_EVEN`** (the ambient default) | Wrong for consumer-facing amounts — see A.1 |
| **JSON number on the wire with client-side care** | The client's parser decides before any client code runs. "Care" cannot execute before parsing |
| **Per-field serializers** rather than one chokepoint | Works until one endpoint forgets, and the forgetting is invisible in review. One annotated type cannot be forgotten [BR5.3] |
| **A money type without the import boundary** | The type stops a float; it does not stop someone handing the module a database session. The boundary and the type address different threats and neither substitutes for the other |

---

## C. What this Unit establishes for later Bolts

Recorded because several of these are B1's real deliverables and would
otherwise look like incidental setup:

- The **two import-boundary mechanisms**, present and demonstrated failing
  from the first commit [BR6.3]. Every later backend Bolt inherits them.
- **Ruff with its named rule sets** and **mypy's global baseline plus this
  module's strict island**. The rule selection matters more than the tool
  choice: Ruff at its defaults catches almost none of what matters here.
- **Lockfiles on both surfaces** and the **secrets-scanning pre-commit hook**,
  sequenced here by `team.md` as skeleton-time tooling.
- **pytest with the coverage floor wired into CI**, including the 100% branch
  configuration scoped to this module.
- **Hypothesis**, available to every later Bolt that needs a property test.

---

## Assumptions & Open Questions

None.
