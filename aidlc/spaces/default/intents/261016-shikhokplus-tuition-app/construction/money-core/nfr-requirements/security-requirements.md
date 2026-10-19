# Security Requirements — `money-core` (U1)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> **This Unit has no authentication, no authorization, no session, no network
> and no stored data.** Its security requirements are therefore **integrity**
> requirements, not confidentiality or access-control ones. The asset under
> protection is the correctness of every money value in the system, and the
> threat is a silent arithmetic defect that produces a plausible wrong number
> nobody detects. A document here listing login controls would be filler; this
> one treats the money boundary as the asset.

## Sources

- [stage] `nfr-requirements-questions.md` — Q2 (integrity not access control),
  Q3 (coverage as a real gate), Q5 (dependency policy), Q6 (supply chain)
- [upstream] `construction/money-core/functional-design/rules.md` — BR1.1,
  BR1.2, BR1.7, BR1.8, BR5.1–BR5.7, BR6.1–BR6.4
- [upstream] `construction/money-core/functional-design/functional-spec.md` —
  §2.9, §2.10, §2.11, §5.6
- [upstream] `inception/requirements-analysis/requirements.md` — NFR9, NFR10,
  NFR17
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [team] `## Code Style` → "Money as a type, on both surfaces"; `## Deployment`
  → scanning posture
- [project] `## Forbidden` / `## Mandated` money rules

---

## Part A — Threat model for a pure-arithmetic module

Five threats, each with the mechanism that addresses it. These are the real
ones for this Unit; the generic web threats (injection, XSS, CSRF, broken
auth) have no surface here because the module has no input parser, no
template, no session and no endpoint.

### T1 — A float reaches a money value and the error is invisible

**The threat.** Binary floating-point cannot represent most decimal fractions
exactly. A value that is `0.1` in the source becomes slightly more or less
than a tenth in memory, and the error compounds across a ledger. The
dangerous property is that it is **invisible at normal scale**: a single fee
displays correctly, and only a reconciliation across hundreds of entries
reveals the drift — by which time the ledger is the record of record.

**Why it is the top threat.** It is the one defect class that produces
*financial* error with *no* error signal, in a system whose users are
individual teachers reconciling fees by hand against what parents paid.

**Mechanisms** — three independent layers, because one is not enough:

| # | Mechanism | Catches | Rule |
|---|---|---|---|
| 1 | Construction from a float raises | A float arriving as an amount | NFR9.1 [BR1.1] |
| 2 | Raw decimal construction from a float is forbidden module-wide | `Decimal(0.1)` — which yields a *decimal*, so a type check passes while the value is already wrong | NFR9.2 [BR1.2] |
| 3 | No float or integer conversion is defined on the type | A money value leaking back out into float arithmetic | NFR9.3 [BR1.6] |

**NFR9.1** — Constructing a money value from a binary floating-point number
MUST raise. No coercion, no rounding into acceptability, no log-and-continue.

**NFR9.2** — Constructing the underlying fixed-point decimal from a
floating-point value MUST be forbidden anywhere in the module, whether the
float is a literal or a variable. The literal case is caught by lint; the
variable case is caught by NFR9.1, because such a value cannot reach a money
value by any other path.

**NFR9.3** — The money type MUST define no conversion to float and none to
integer. The float conversion would reintroduce this entire threat by the back
door; the integer conversion silently discards paisa.

### T2 — Money arithmetic escapes the module and the boundary stops meaning anything

**The threat.** Someone computes a fee in a route handler, a repository or a
Compose function. The arithmetic is then outside the rounding mode, outside
the coverage obligation and outside the tests. The boundary becomes
documentation rather than a control, and nothing announces the moment it
happened.

**The plausible violation is not the obvious one.** Nobody writes a fee
calculation in a view on purpose. What actually happens is somebody gives this
module a database session "just to look up the batch default fee" — one
reasonable-looking commit that destroys the testability story, the strict
typing story and the coverage target simultaneously.

**NFR9.4** — The module MUST import nothing from the API, persistence,
repository, authorization or schema layers, enforced by a layered-import test
that fails the build. [BR6.1]

**NFR9.5** — Raw fixed-point decimal arithmetic MUST be confined to this
module, enforced by a banned-import check with the module itself re-permitted
by explicit exception. This is the load-bearing half: money arithmetic outside
the module needs either a raw decimal or a float, so banning the one closes
the door on the other. [BR6.2]

**NFR9.6** — Both checks MUST be present from the **first commit** of this
Unit, and each MUST be demonstrated failing against a deliberate violation
before the Unit is done. A gate nobody has watched fail is a gate nobody knows
works. [BR6.3]

**NFR9.7** — On the client surface, the money type MUST be a decimal-backed
value type, with floating-point types banned package-wide in the shared model
package. The compiler is the primary mechanism; the package-wide ban is a
backstop that needs no semantic judgement about which fields carry money.
[BR6.4]

### T3 — A money value crosses a boundary and loses precision in transit

**The threat.** JSON numbers are IEEE 754 doubles in most parsers. A money
value emitted as a JSON number is converted to a float by the *client*, which
reintroduces T1 on the other side of the wire where this module's controls
cannot reach. The failure mode that matters is a **lenient decoder**: one that
silently accepts a number and converts it, so a happy-path test on both sides
passes while the value is already wrong.

**NFR9.8** — Every money value MUST cross the API as a JSON **string** in the
canonical form `^[0-9]+\.[0-9]{2}$`, emitted through a single chokepoint
rather than per-field discipline. [BR5.1, BR5.3]

**NFR9.9** — The client MUST reject a JSON number for a money field **loudly**
rather than coercing it. A serialization test MUST assert both directions: the
server never emits a number, and the client fails on one. [BR5.2]

**NFR9.10** — A single storage-type mapping MUST be the only path to a money
column, mapping to `NUMERIC(12,2)`. No model may declare a money column
independently — that is how one eventually declares too few digits or a
floating-point type. [BR5.3]

**NFR9.11** — A negative money value MUST NOT cross the API boundary; the
attempt raises. The canonical pattern admits no sign, so there is no
representation to emit, and a negative value reaching serialization means a
sign rule was violated upstream. Refusing here turns that into a loud failure
rather than a dropped sign that displays a debt as a credit. [BR5.7]

### T4 — An arithmetic defect survives because the test that should catch it cannot

**The threat.** This is the subtlest one and it has already materialised twice
in this project. A test can pass against **two different implementations that
disagree**, which means the test certifies nothing about the disagreement:

- The ledger identity was stated wrongly twice before randomized testing
  settled it. Both wrong forms satisfied their own worked examples.
- Allocation of a negative amount has two reasonable implementations giving
  different splits, and **both sum to exactly the original** — so the
  exact-sum property test passes against either. [BR2.9]
- A one-sided carry-forward passes a single-carry test, because the error is
  still small enough to look plausible; it only diverges visibly over multiple
  periods. [BR4.6]

**NFR9.12** — The ledger identity MUST be verified by **property-based testing
over randomized histories**, not by worked examples alone. Worked examples
establish the cases a human thought of; randomized composition establishes the
ones nobody did. [BR4.8]

**NFR9.13** — 100% **branch** coverage on this module is a build gate and MUST
NOT be weakened to make a step pass. Line coverage is insufficient here: the
defects live in the branches — the carry-versus-waive fork, the partial
approval path, the zero and negative edges, the short-month clamp. An 80% line
floor can be met with the waiver branch entirely unexecuted. [NFR17,
project.md NEVER-rule]

**NFR9.14** — Coverage MUST be supplemented by obligations not reducible to a
percentage: a named test per ledger operation, a named test per money
boundary case (period boundaries, rounding at the half, zero, negative, an
approved amount exceeding the claimed amount), and a multi-period carry test
rather than a single-carry one.

**NFR9.15** — Where an operation admits more than one answer that satisfies
its own property test, the design MUST fix the answer explicitly rather than
leaving it to the implementer. [BR2.9 is the worked instance.]

### T5 — Supply chain: a dependency introduces arithmetic or I/O

**The threat.** A dependency added to this module could bring in its own
numeric handling, or I/O that breaks the coverage target and the
buildable-before-any-endpoint property.

**NFR9.16** — The module's dependency surface MUST be limited to the
language's own decimal arithmetic, its locale facilities, and the
type/serialization annotations needed for the two chokepoints. No ORM, no
session, no settings, no HTTP client, no date library. [Q5]

**NFR9.17** — Any new dependency on this module MUST carry an explicit
admission note recording what it brings in, because the import checks of
NFR9.4 and NFR9.5 will generate findings and this is where the answer is
recorded.

**NFR9.18** — The project supply-chain posture is inherited unchanged:
lockfiles and checksum verification on both surfaces, secrets scanning
blocking every push, dependency CVEs annotating per-push and blocking at the
release gate with dated written exceptions. This Unit introduces **no
exception and asks for none**. [team.md Deployment]

> **B1-specific note.** The lockfiles and the secrets-scanning pre-commit hook
> arrive **in this Bolt**, because `team.md` sequences them as skeleton-time
> tooling. B1 is where they first exist rather than where they are merely
> obeyed. This Unit's own CVE exposure is near zero by NFR9.16 — the
> supply-chain risk it carries is almost entirely about the tooling it
> establishes for every later Bolt.

### T6 — The ledger vocabulary is extended and the identity silently stops holding

**The threat.** BR4.3's identity is true **only because each of the seven
entry kinds sits on a known side of it**. Closure of the kind set is asserted
in `entities.md` but enforced by nothing executable. An eighth kind added
later and folded into neither side balances perfectly across the six kinds the
identity knows about, while every enrollment carrying the new kind is wrong.

**Why this is not hypothetical.** The extension is already scheduled: the
collection-rate definition is open to correction and is expected to extend
this module's property test [`functional-spec.md` §5.1]. The change will be
made by someone reading a requirement about collection rate, not a document
about ledger closure.

**Why the existing tests do not catch it.** This is the T4 pattern again, in
its most dangerous form. A property-based test generates only the kinds it was
written to generate, so it **cannot produce a history containing a kind added
after it was written**. The test passes, the identity appears verified, and
the verification covers a vocabulary that is no longer the real one.

**NFR9.19** — The seven ledger entry kinds MUST be a **closed set, enforced
executably**: an unrecognised kind raises rather than being ignored or
defaulted. Silently excluding an unknown kind from the fold is the specific
failure that produces a balance that looks right and is not. [BR1.8 class;
`entities.md` closure assertion]

**NFR9.20** — The property-based test MUST derive its generated kinds **from
the kind enumeration itself**, not from a hand-written list. A kind added to
the enumeration then appears in generated histories automatically, and if the
identity does not account for it the test fails on the commit that adds it.
This is what converts closure from an assertion into a check.

**NFR9.21** — Adding a ledger entry kind MUST require stating which side of
the identity it falls on, and MUST re-run the randomized verification of
BR4.8 before the change is complete. A kind that belongs to neither side is a
design error, not a configuration choice.

**NFR9.25** — The property test MUST NOT read a kind's identity side from the
same source the fold reads. Each kind MUST carry a **hand-written expected
effect** in the test — a named worked case asserting what that kind alone does
to `total_outstanding` and `available_credit` — independent of
`entities.md`'s `identity_side` field.

> **Why NFR9.20 alone is only half a control, and this is the other half.**
> NFR9.20 catches an *omitted* kind: one added to the enumeration but to
> neither side of the identity. It does not catch a **mis-sided** one. If a
> kind is added to the enumeration *and* given an `identity_side`, but the
> wrong one, and the property test derives its expectation from that same
> field, then the test and the implementation agree **by construction**.
> BR4.3 balances exactly, every check passes, and every enrollment carrying
> the new kind is wrong.
>
> That is precisely the T4 pattern — a test that cannot disagree with the
> implementation it is testing — reappearing inside the fix for T6. It is the
> same shape as the two defects this project has already hit: the ledger
> identity that satisfied its own worked examples while being wrong, and the
> negative allocation whose two implementations both passed the sum test. A
> single source of truth is correct for the *implementation* and fatal for the
> *test*, and the distinction is what NFR9.15 already states in general terms.
>
> The hand-written expectation is what makes the two independent. Writing it
> costs one worked case per kind — seven today — and is the only thing that
> can disagree with a wrong `identity_side`.

### T7 — The display string is unspecified and ships wrong without any check failing

**The threat.** BR5.4 puts all locale digit rendering and separator placement
in this module and forbids the client from formatting. But **nothing states
what the formatting operation actually emits.** A pass-through implementation
— returning the canonical Latin-digit string unchanged — satisfies every
mechanical control this Unit has: the branch executes so coverage passes, the
import checks pass, the serialization tests pass, the schema matches.

**The concrete failure.** V1 ships with Bangla screens showing Latin digits,
and **no check anywhere in the system is capable of failing**. NFR3 requires
Bangla from the first screen; `team.md` requires a verifier for the Bangla
layout obligation rather than a hope. The canonical wire string is correctly
pinned to Latin digits by BR5.1 — it is the *display* string, the one NFR3 is
actually about, that is unpinned.

**NFR9.22** — The formatting operation's output MUST be specified per
supported locale, not left to the implementer: which digit set, which
grouping separator, which decimal separator, and which grouping interval.
"Formats for the locale" is not a specification — it is the name of the
problem.

**NFR9.23** — Each supported locale MUST carry a **named test asserting the
exact expected output string** for a representative amount, including at least
one amount large enough to exercise grouping. A test asserting only that the
output is non-empty, or that it differs between locales, does not distinguish
a correct rendering from a plausible wrong one.

**NFR9.24** — The Bangla rendering MUST be asserted to differ from the
canonical Latin-digit form wherever the locale requires it. This is the single
check that makes the pass-through implementation fail, and it is the reason
this requirement exists.

> **Where the specification itself belongs.** The exact digit set and
> separator rules for each locale are a Functional Design concern, and
> `functional-spec.md` §2.8 does not currently carry them. This Unit's NFR
> position is that the gap is real and must close before implementation; the
> **open question below records it rather than inventing the glyph table
> here**, because getting Bangla numerals wrong in a requirements document is
> worse than naming the gap.

---

## Part B — What this Unit does NOT have, and why that is correct

Stated explicitly so a reviewer can tell the difference between an analysis
that found nothing and an analysis that was not done.

| Control | Status | Why |
|---|---|---|
| Authentication | **N/A** | No process, no request, no caller identity. U3 owns this. |
| Authorization / lens resolution | **N/A** | No data to scope and no query to scope it on. U3 owns the lens; U2 owns the route-enumeration harness. |
| Row-level security | **N/A** | This Unit owns no table. U3 and U11 own the privacy boundary. |
| Input sanitization against injection | **N/A** | No query is constructed here and no template is rendered, so there is no interpreter for an injected payload to reach. Note that this module **does** take string input — the wire value at §2.10 and the locale at §2.8 — so the reason is the absence of a sink, not the absence of strings. Both are constrained at entry: the wire value must match the canonical pattern, and the locale must be one of the finite supported set. A future third string input would need its own constraint; this row does not pre-authorise one. |
| Rate limiting / abuse controls | **N/A** | No endpoint. U3 owns the OTP abuse controls. |
| Secrets handling | **N/A** | The module reads no configuration at all [BR5.6], so it cannot hold a secret. |
| Audit logging | **N/A** | No actor and no access event. U3 owns the authentication audit log. |
| PII handling | **Indirect** | Money amounts are financial data about minors' guardians, but this Unit never sees a name, a phone number or an identifier — only an amount and an entry kind. |
| Encryption at rest | **Inherited** | NFR10 binds the infrastructure that hosts the column this Unit's storage mapping targets. The mapping is this Unit's; the encryption is not. |

> The useful consequence: **this Unit cannot leak personal data**, because it
> never receives any. That is a property of the design rather than of a
> control, and it is why the privacy obligations that dominate every other
> Unit are genuinely absent here.

---

## Part C — Verification

Every requirement above is mechanically verifiable. None rests on review.

| Requirement | How it is verified | When it fails |
|---|---|---|
| NFR9.1–NFR9.3 | Unit tests asserting the raise; lint rule for the literal case | Build / test |
| NFR9.4 | Layered-import test walking the module's imports | Build |
| NFR9.5 | Banned-import check with per-file exception | Build |
| NFR9.6 | **Committed violation fixtures** — see below | CI |
| NFR9.7 | Compiler, plus package-scoped float ban | Client build |
| NFR9.8–NFR9.11 | Serialization tests both directions; schema pattern | Test / contract |
| NFR9.12 | Property-based test over randomized histories | Test |
| NFR9.13 | Coverage report with the floor enforced | CI |
| NFR9.14–NFR9.15 | **A named-test manifest, asserted present** — see below | CI |
| NFR9.16–NFR9.17 | Dependency manifest review at admission | PR |
| NFR9.18 | Secrets scan, lockfile verification, CVE gate | Push / release |
| NFR9.19–NFR9.21 | Unknown-kind raise test; generators derived from the kind enumeration | Test |
| NFR9.22–NFR9.24 | Exact-output test per locale, including a Bangla-differs assertion | Test |

**The point of this table.** `team.md` states the organising principle:
"where a rule is important, it is mechanical", because a rule enforced by
review is enforced by one stretched reviewer. Every row above fails in CI
rather than in review. Review remains the backstop and stops being the
mechanism.

**Two rows needed strengthening to make that claim true**, and are recorded
here rather than left as the weaker form:

- **NFR9.6** previously read "demonstrated against a deliberate violation —
  Unit DoD", which is a person confirming a gate was once watched failing.
  That is review wearing a verification label, and it decays: a later
  refactor of the import-check configuration can neuter the gate with nothing
  noticing. B2 and B4 both ship their violation fixtures as committed tests,
  and B1's import gates are the **earliest and most load-bearing** in the
  project — they have no business being held to a weaker standard. So: each
  import check MUST carry a committed fixture that violates it, asserted to
  fail, running in CI on every push.
- **NFR9.14–NFR9.15** previously read "named tests, enumerated in the test
  plan". No test plan is produced by this stage, and the B1 definition of done
  states the obligation in prose. A missing named test — BR4.6's multi-period
  carry test, say, whose branches the single-carry test already covers — is
  invisible to the 100% coverage gate. So: the named-test obligations MUST be
  recorded as a **manifest in the repository**, with a CI check asserting that
  every entry resolves to a test that exists and runs. A manifest entry
  without a matching test fails the build. **Each entry MUST also state its
  acceptance criterion** — the specific assertion that makes the test
  meaningful, such as "a three-period carry reads 3000, not 4000" rather than
  "covers carry-forward". A manifest can verify that a test exists and runs,
  never that it asserts anything useful; naming the criterion per entry is
  what makes a trivially-asserting test visible as a mismatch to a reader.
  That residual is the general limit of every named-test obligation, and
  `team.md` already rejects always-passing tests in review.

> Both changes follow the same reasoning as the rest of this document: the
> 100% branch coverage gate measures whether branches execute, not whether the
> *right tests* exist. Every obligation that coverage cannot see needs its own
> mechanism, or it is an obligation held by one stretched reviewer.

---

## Assumptions & Open Questions

**OQ-B1-1 — The Bangla money rendering is not specified anywhere, and must be
before this module is implemented.** [NFR9.22, T7]

`BR5.4` and `contract-summary.md` §B.5 both place digit rendering and
separator placement in this module and forbid the client from formatting.
Neither says **what the output is**. Four things need deciding, and none is
this document's to invent:

1. **Digit set** — Bengali numerals (`০১২৩৪৫৬৭৮৯`) or Latin digits under a
   Bangla locale. Both occur in Bangladeshi financial contexts, and the answer
   is a product decision about what a teacher reconciling fees by hand expects
   to see, not a technical one.
2. **Grouping interval** — South Asian grouping (2,2,3: `১২,৩৪,৫৬৭`) or
   Western grouping (3,3: `১২৩,৪৫৬৭`). These genuinely differ above 99,999 and
   the choice is visible to the user.
3. **Separator characters** — which grouping and decimal separators accompany
   the chosen digit set.
4. **Whether the currency symbol or code appears** in the display string, or
   is supplied by the screen.

**Why it is flagged rather than defaulted.** `team.md` records that an open
question carrying a proposed default is a decision wearing a question's
clothes, and that the test is whether the answer needs judgement nobody has
yet. Here it does: items 1 and 2 are user-facing product judgements about
Bangladeshi convention, and getting Bengali numerals wrong in a requirements
document is worse than naming the gap. The *gap itself* is not deferred —
NFR9.22–NFR9.24 make the specification and its tests a precondition of
implementation.

**Who closes it and when.** The human, before this module's formatting
operation is implemented. It does not block the rest of B1: the money type,
the arithmetic, the ledger identity, both chokepoints and both import gates
are all independent of it. If it is still open when the rest of B1 is done,
the correct move is to ship B1 **without** the formatting operation rather
than with a guessed rendering — a display string is additive under the `/v1/`
policy, while a wrong rendering pinned into an installed client is not
withdrawable.

**Blocks:** B1's formatting operation, and then **B6** `fee-cycles-and-ledger`,
**B7** `payment-claims-and-verification` and **B10** `teacher-insights` — the
three Bolts whose screens consume a `*_display` sibling. Stated in the same
shape as the delivery-planning open questions (OQ-1..OQ-7), each of which
names its blocking Bolt, because an open question recorded only inside the
Unit that found it is one the delivery view cannot see. **This is the first
B1-originated open question**, so it has no existing home in
`external-dependency-map.md`; carrying it there belongs to whoever next
revises that artifact, and it is noted here rather than silently left local.
