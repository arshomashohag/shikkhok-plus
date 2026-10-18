# NFR Requirements Questions — money-core (U1)

**Stage**: nfr-requirements (3.2)
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`
**Phase**: Construction
**Depth**: Comprehensive

> U1 is a `library` Unit: no process, no endpoint, no database, no network.
> Most inception NFRs are about a running service and do not bind here, which
> is itself a decision worth recording rather than leaving as an empty file.
> The questions below are the ones that genuinely bind.

---

## Q1 — Which inception NFRs actually apply to a stateless library Unit?

NFR1–NFR17 were written for the system. A library with no process cannot have
an availability target, a throughput figure or an alerting threshold.

[Answer]: Three bind directly — **NFR9** (money representation: fixed-point
decimal, BDT, JSON string in transit, never float), **NFR17** (100% branch
coverage on the money module), and **NFR10** in a narrow sense (this Unit
defines the storage mapping that lands children's-adjacent financial data in
an encrypted-at-rest column, though the encryption itself is infrastructure).
**NFR7** binds indirectly: a library that forced a heavyweight dependency
would push hosting cost, so dependency weight is a real constraint.

Everything else is marked `N/A` with a reason, not silently dropped. The
reason is uniform and structural: no process, no I/O, no state. Recording it
explicitly is what stops a later reader assuming the analysis was skipped.

---

## Q2 — Does a pure-arithmetic library have security requirements at all, or is `security-requirements.md` a formality here?

This is the stage's review artifact, so the answer shapes what gets reviewed.

[Answer]: It has real ones, and they are the most important NFRs this Unit
has — but they are **integrity** requirements rather than the usual
confidentiality and access-control ones. This Unit has no authentication, no
authorization and no data to leak. What it does have is the one place in the
system where a silent arithmetic defect becomes financial loss that nobody
detects, and the three boundary mechanisms that keep it that way:
the float prohibition, the import boundary, and the serialization chokepoints.
A security document here that listed authentication controls would be
boilerplate; one that treats the money boundary as the asset under protection
is the honest version.

---

## Q3 — Is the 100% branch coverage target a real gate or an aspiration, and what makes it achievable?

`team.md` states 100% branch coverage on the money module and `project.md`
forbids weakening a coverage floor to make a step pass.

[Answer]: A real gate, failing the build below 100%. Three design properties
make it achievable rather than aspirational, and all three are already fixed
by Functional Design: no I/O, no session and no settings import [BR6.1,
BR6.2]; locale as an argument rather than configuration [BR5.6]; and exactly
one error class on every refusal path [BR1.8], so there is no unreachable
error branch. The last one is load-bearing — the design review found a
proposed `ConflictError` branch that could never execute, which would have
made 100% unmeetable. Branch coverage is supplemented by obligations not
reducible to a percentage: a named test per ledger operation, a documented
boundary case per money input, and the property-based test on the ledger
invariant.

---

## Q4 — What is the performance requirement for a library with no latency budget of its own?

NFR-wise this Unit has no response time. But it sits inside the hottest query
in the system — the fee views — on a single 2 GB instance.

[Answer]: No latency target is stated for U1 itself, because a target with no
measurable boundary is a wish. What is stated instead is a **complexity
bound**: the derived-quantity fold is a single linear pass over an
enrollment's entries, with no nested iteration and no per-entry allocation of
intermediate collections. That is checkable by reading the code, unlike a
millisecond figure for a function call. ADR-002 already records the escalation
trigger that *does* have numbers — p95 above 800 ms or more than 20,000 ledger
entries per owner — and that trigger belongs to U7, which owns the query.

This is also why `performance-requirements.md` is **not produced** for this
Unit: the stage's per-kind applicability excludes it for a `library`, and
inventing one would create a target nobody can measure or fail.

---

## Q5 — Dependency policy: what may this module depend on?

The module's value rests on depending on almost nothing.

[Answer]: The language's own decimal arithmetic and its locale facilities,
plus the type/serialization framework annotations needed for the two
chokepoints — and nothing else. No ORM, no session, no settings, no HTTP
client, no date library. Each new dependency on this module is a decision
requiring an explicit note, because the import boundary is checked
mechanically [BR6.1, BR6.2] and a dependency that drags in I/O would break
both the coverage target and the "buildable before any endpoint exists"
property. On the Kotlin side the equivalent is the value class plus its
serializer, with floats banned package-wide.

---

## Q6 — Supply-chain posture for this Unit specifically

`team.md` sets the project-wide posture: lockfiles, checksum verification,
Gitleaks blocking every push, CVEs annotating per-push and blocking at the
release gate.

[Answer]: Inherited unchanged — this Unit introduces no exception and asks for
none. Two B1-specific notes. The lockfiles and the Gitleaks pre-commit hook
arrive **in B1** because `team.md` sequences them as skeleton-time tooling,
so B1 is where they first exist rather than where they are merely obeyed. And
because this Unit's dependency surface is close to empty by Q5, its own CVE
exposure is near zero — the supply-chain risk it carries is almost entirely
about the tooling it establishes for every later Bolt, not about itself.

---

## Q7 — Tech stack: is anything actually open, or is it all settled upstream?

[Answer]: Settled upstream, and the document records the decisions with their
rationale rather than re-opening them: Python 3.12 with its native decimal
type; `NUMERIC(12,2)` as the storage mapping; Kotlin's `BigDecimal` behind a
value class; a JSON string on the wire; half-up rounding declared once; Ruff
and mypy in strict mode over this module. The one thing this stage genuinely
decides is the **property-based testing library** for the ledger invariant,
and `team.md` already names Hypothesis. Recorded as a decision with its
reason, not presented as an open choice.

---

## Assumptions & Open Questions

None.

---

## Consolidated Summary Confirmation

U1 is a stateless library, so most inception NFRs are marked `N/A` with the
same structural reason rather than silently dropped. Three bind: money
representation, 100% branch coverage, and the storage mapping that lands in an
encrypted column. Security for this Unit is **integrity**, not access control
— the money boundary is the asset. Coverage is a real build gate, achievable
because the design has no I/O, no settings and exactly one error class.
Performance is stated as a complexity bound rather than a latency figure, and
`performance-requirements.md` is not produced. The dependency surface is
deliberately near-empty, the project supply-chain posture is inherited
unchanged, and the stack is settled upstream with Hypothesis named for the
property test.

Does this all look correct?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
