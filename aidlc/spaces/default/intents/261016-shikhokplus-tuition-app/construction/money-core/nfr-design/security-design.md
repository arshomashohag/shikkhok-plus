# Security Design — `money-core` (U1)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U1 `money-core` — `library`, M
**Bolt**: B1 `b1-money-core`

> NFR Requirements stated **what** must hold: 25 requirements across seven
> threats. This document designs **how** — the concrete mechanism behind each,
> where it lives, what it fails on, and what it cannot catch. For a library
> with no runtime surface, every mechanism is a build-time or test-time one.
> There is no authentication flow, no encryption design and no security header
> here, because there is no request.

## Sources

- [stage] `nfr-design-questions.md` — Q1 (two gate directions), Q2
  (chokepoints), Q3 (coverage configuration), Q4 (vocabulary closure), Q5
  (formatting shape), Q7 (CI order)
- [upstream] `construction/money-core/nfr-requirements/security-requirements.md`
  — NFR9.1–NFR9.25, threats T1–T7
- [upstream] `construction/money-core/nfr-requirements/tech-stack-decisions.md`
  — TS1–TS11
- [upstream] `construction/money-core/functional-design/functional-spec.md` —
  §2, §5.6
- [upstream] `inception/contract-design/contract-summary.md` — §B.5, §E.1
- [team] `## Code Style`, `## Testing Posture`, `## Deployment`
- [project] `## Forbidden` / `## Mandated`

---

## Part A — The mechanism behind each requirement

### A.1 The float barrier (T1 → NFR9.1, NFR9.2, NFR9.3)

Three layers, each catching what the others cannot.

| Layer | Mechanism | Catches | Cannot catch |
|---|---|---|---|
| **Type** | Construction inspects the candidate and raises on a binary float | A float arriving as an amount, at runtime | A float that never reaches construction |
| **Lint** | Banned construction of the raw decimal from a float literal | `Decimal(0.1)` written literally — which yields a *decimal*, so a type check passes while the value is already wrong | The variable-valued case |
| **Surface** | No float or integer conversion defined on the type | A money value leaking back into float arithmetic | — |

**The gap each layer leaves is covered by another, and that is the design.**
The lint rule cannot see `Decimal(x)` where `x` is a float-valued variable;
the type's construction check catches it, because such a value cannot reach a
money value by any other path. The type check cannot see a float used in
arithmetic that never touches a money value; the import boundary of A.2 makes
that arithmetic impossible to write in the first place.

**Design detail that matters**: the construction check tests the *type* of the
candidate, not its value. A float that happens to be integral (`1000.0`) is
refused identically to `0.1`, because accepting the integral case would make
the rule value-dependent and therefore unpredictable to a caller.

### A.2 The two import gates (T2 → NFR9.4, NFR9.5, NFR9.6)

**They point in opposite directions. That is the entire reason there are two.**

| | Gate 1 — outward | Gate 2 — inward |
|---|---|---|
| **Asserts** | This module imports nothing from API, persistence, repository, authorization or schema layers | Nothing outside this module imports raw decimal arithmetic |
| **Mechanism** | A test walking the module's own import graph | A banned-import lint rule, module re-permitted by explicit per-path exception |
| **Catches** | "Someone gave the money module a database session to look up the batch default fee" | "Someone computed a fee in a route handler" |
| **Fails at** | Test run, in CI and locally | Lint, pre-commit and CI |
| **Fixture** | A committed test importing a repository, asserted to fail | A committed file importing raw decimal outside the module, asserted to fail |

Neither gate catches the other's case. Gate 1 would pass happily while a route
handler does decimal arithmetic; Gate 2 would pass happily while the money
module imports a session, because a session is not a decimal.

**Gate 2 is the load-bearing one.** Money arithmetic outside this module needs
either a raw decimal or a float. Banning the decimal import closes the door on
both, because the float is already forbidden project-wide.

**On the fixtures (NFR9.6).** Each gate ships a committed artefact that
violates it, asserted to fail, running in CI on every push. This replaces the
weaker "demonstrated once at Unit DoD": a person confirming a gate was watched
failing is a memory, and a later refactor of the lint configuration or the
import-graph contract can neuter either gate with nothing noticing. B2 and B4
both ship violation fixtures; B1's gates are the earliest and most
load-bearing in the project and have no business being held to a weaker
standard.

> **Implementation note on fixture shape.** A fixture that violates a lint rule
> cannot simply sit in the source tree, or it breaks the ordinary lint run.
> It lives outside the linted paths and is invoked by the test that asserts the
> failure — the test runs the checker against the fixture and asserts a
> non-zero result. This keeps "the gate works" and "the tree is clean" from
> contradicting each other.

**NFR9.29 — the fixtures prove the checker; a second assertion proves the
configuration.** A fixture invoked against the checker passes even when the
checker no longer covers the real tree. Three ways that happens, none of them
exotic:

- the module directory is renamed and the rule's path pattern no longer
  matches it;
- the re-permitting exception is widened from the money module's path to a
  parent path, so the ban stops applying anywhere;
- the linter's file-selection misses a newly added package.

Each leaves both fixtures green. **This is precisely the "a later refactor
neuters the gate with nothing noticing" scenario this design cites as its own
reason for having fixtures** — so the fixtures alone do not discharge it.

Each gate therefore also asserts **its own configuration**:

| Gate | Configuration assertion |
|---|---|
| Gate 1 | The module path it walks **resolves to a real package containing the money module**, and the package is non-empty. A renamed or missing path fails rather than vacuously passing |
| Gate 2 | The ban's scope **covers every Python source root**, and the re-permitting exception resolves to **exactly** the money module's path — not a parent, not a glob that widens it |

Both assertions are cheap, and both fail on the commit that breaks them rather
than on the commit that later exploits the breakage.

### A.3 The two chokepoints (T3 → NFR9.8, NFR9.9, NFR9.10, NFR9.11)

| Boundary | Chokepoint | Why not the obvious alternative |
|---|---|---|
| **API** | One annotated type reused by every schema | A per-field serializer works until one endpoint forgets — and a forgotten serializer is invisible in review, because the field still renders. An annotated type cannot be forgotten, because forgetting it means not having a money type |
| **Storage** | One type decorator mapping to the fixed-point column | A per-model column declaration means every model independently declares its type, and one eventually declares too few digits or a floating-point type |

**What makes them hard to bypass** is that there is usually nothing else to
reach for: a schema field either uses the money type or it is not a money
field, and an ORM-declared model column either uses the decorator or declares
its own decimal type — which needs the import Gate 2 refuses.

**That inference holds only for ORM-declared Python decimal columns, and three
paths defeat it.** Stated plainly, because an earlier draft of this section
claimed unbypassability outright:

| Bypass | Why Gate 2 misses it | Consequence |
|---|---|---|
| **A raw SQL migration** declaring the column directly | It imports nothing — the type is a string inside a SQL statement | A money column with the wrong precision, violating BR1.7's ten-integer-digit storage contract, with no mechanical defender at schema level |
| **A string-typed column declaration** | Same: no decimal import | Same |
| **A `str`-typed schema field carrying money** | A string field is ordinary | **Not hypothetical** — BR5.4 *mandates* an `amount_display` string sibling, so money-carrying strings are a normal part of this system's schemas |

**NFR9.30 — the chokepoints are backed by schema-level assertions, not by the
import inference alone.** Two checks, both matching idiom this project already
uses elsewhere (U2 iterates the generated OpenAPI schema for the
no-profile-field invariant; U11 iterates the live schema for its manifests):

- **Database schema check** — iterate the migrated schema and assert every
  money-carrying column has the exact declared type and precision, regardless
  of how it was created. This catches the raw-SQL and string-declaration
  paths, which no import rule can see.
- **API schema check** — iterate the generated OpenAPI schema and assert every
  money field matches the canonical pattern, and that every `*_display`
  sibling is accompanied by its canonical `amount` field. The display string
  is *expected* to be a string; what must not happen is a canonical money
  value typed as a free-form string.

> The honest version of this section's claim: the chokepoints make the
> *correct* path the easy one and the *incorrect* path require deliberate
> effort, and the two schema assertions catch the deliberate cases. "Nothing
> else to reach for" was an overstatement, and overstating a control is worse
> than a weaker control honestly described — it is the reason nobody adds the
> check that would have caught the gap.

**Negative values at the boundary (NFR9.11).** The canonical wire pattern
admits no sign, so serializing a negative raises. This is a **consistency
check on the sign rules**, not a limitation: every quantity that legitimately
crosses the API is one the sign rules already forbid to be negative, so a
negative reaching serialization means a floor was missed upstream. Failing at
emission turns that into a loud error rather than a string the client cannot
parse — or worse, a dropped sign that displays a debt as a credit.

**Client side (NFR9.9).** The value class makes a float assignment a compile
error, with no custom lint rule. The serializer reads only a string and
rejects a JSON number. The package-wide float ban is a backstop requiring no
semantic judgement about which fields carry money.

### A.4 Coverage, configured so it cannot be met dishonestly (T4 → NFR9.13)

Three configuration decisions, each closing a specific way a 100% target gets
defeated:

1. **Scoped to this module's package**, not a global average. A global figure
   lets well-covered code elsewhere mask a gap here.
2. **Branch coverage, not line.** The defects in this module live in the
   branches — the carry-versus-waive fork, the partial-approval path, the zero
   and negative edges. An 80% line floor can be met with the waiver branch
   entirely unexecuted.
3. **No exclusion pragmas permitted in this package.** An inline
   coverage-exclusion comment is the standard way a 100% target is quietly
   defeated, and it looks innocuous in a diff. If a line genuinely cannot be
   covered, that is a **design signal** — exactly what the dead
   `ConflictError` branch turned out to be at Functional Design review — not
   an occasion for a pragma. The one sanctioned exception is NFR9.28's
   exhaustiveness construct, which is written to emit no coverable branch at
   all — and, only where the language cannot express that, is named in the
   **coverage configuration file** by path and symbol. The distinction from a
   pragma is not pedantry: a configuration entry is reviewed, enumerable and
   greppable, while an inline comment is invisible in a diff among the lines
   it exempts.
4. **Relocation out of the package is treated as suppression.** A
   package-scoped target is defeated most easily not by a pragma but by
   **moving a branch somewhere else** — a new `money_utils` or `fee_math`
   module sitting outside the covered package. It reads as refactoring in a
   diff, which makes it both likelier and less visible than a pragma, and
   **neither existing control catches it**: Gate 1 only refuses imports *into*
   the module from the API, persistence, repository, authorization and schema
   layers, and a new sibling utility module is none of those.

   **NFR9.31 — and Gate 2 does not close this, which an earlier draft of this
   section wrongly claimed.** The claim was that relocated arithmetic needs
   the raw decimal import Gate 2 bans. That holds for exactly one operation:
   `apply_rate`, the only part of the surface taking a `Decimal`. **Every
   other operation is Money-to-Money** — `add`, `subtract`, `sum`, `allocate`,
   `is_zero`, `is_positive`, `Money.ZERO` — and `functional-spec.md` §7
   defines the eight derived quantities as a fold over Money values grouped by
   kind.

   So the branches that actually matter — the carry-versus-waive fork, the
   partial-approval path, the per-cycle credit attribution — relocate into a
   sibling `fee_math` module **with no decimal import whatsoever**, pass Gate
   2 untouched, and leave the money package at a comfortable 100% while the
   arithmetic that matters sits outside it.

   The mechanism therefore has to be positive rather than prohibitive:

   - **NFR9.31a** — The coverage target MUST be scoped by **what the code
     does, not where it lives**: any module that imports the money type and
     performs branching over money values is inside the 100% branch obligation
     and MUST be listed in the coverage configuration's covered set.
   - **NFR9.31b** — A CI check MUST assert that **every module importing
     `app.money` is either in the covered set or on an explicit, reviewed
     allowlist of pure pass-through consumers.** A new module importing the
     money type appears in neither and fails the build on the commit that adds
     it — which is the point at which relocation is cheap to refuse and
     obvious in review.

   > This inverts the earlier reasoning. Gate 2 asks "did you import
   > `decimal`?", which the relocated fold does not. The right question is
   > "are you doing money arithmetic?", and the honest proxy for that is "do
   > you import the money type and branch on what you get back". The allowlist
   > is the load-bearing half: adding a module to it is a deliberate,
   > reviewable act, while a silent relocation is not possible.

**What coverage cannot do, and what covers that gap.** Coverage measures
whether branches executed, never whether the right tests exist. A missing
named test — BR4.6's multi-period carry, say, whose branches the single-carry
test already covers — is invisible to the gate. Hence the **named-test
manifest** (NFR9.14): entries in the repository, each naming its test *and its
acceptance criterion*, with a CI check asserting every entry resolves to a
test that exists and runs. The manifest cannot verify that a test asserts
anything useful; stating the criterion per entry is what makes a
trivially-asserting test visible to a reader as a mismatch.

### A.5 Ledger vocabulary closure (T6 → NFR9.19, NFR9.20, NFR9.21, NFR9.25)

**Closure is the absence of a default.** The fold is a total mapping from kind
to effect, written so an unrecognised kind cannot pass through unnoticed. No
`else: pass`, no lookup-with-default, no fallthrough. Silently excluding an
unknown kind is the specific failure that produces a balance that looks right
and is not.

**NFR9.27 — the unrecognised-kind check is an assertion, not a raise, and the
distinction is load-bearing.** An earlier draft said "an unrecognised kind
raises", which contradicted two things at once:

- `functional-spec.md` §5.6 enumerates **eight** refusal paths and this is not
  among them. The table claims to cover every refusal in the module.
- BR1.8 states every refusal raises a **validation failure and only** that,
  on the rationale that every refusal here is caused by **the input itself**.
  An unrecognised kind is not bad input — it is a developer who extended the
  enumeration without extending the fold. Classing it as validation would map
  a **code defect** to a 400/422, telling a teacher their request was
  malformed when the real fault is ours.

`team.md`'s taxonomy calls that class `FatalError`, and BR1.8 correctly
excludes it on the grounds that a fatal failure "is an assertion, not a raise
site". So the mechanism follows the taxonomy rather than contradicting it:
**the total mapping is enforced by an assertion** — exhaustiveness checked
statically where the type system can do it, and an assertion at the fold's
default position where it cannot. It is not a refusal, it does not appear in
§5.6's table, and it does not weaken BR1.8's single-class claim.

**NFR9.28 — exhaustiveness is verified statically, and the assertion emits no
coverable statement.** The assertion branch is unreachable while the
enumeration and the fold agree, which is exactly the dead-branch problem that
made the 100% coverage target unmeetable once already.

**An earlier draft said the branch was "excluded from the coverage obligation
by being statically verified instead". That does not work mechanically**, and
the gap is worth stating because the wording would otherwise become a
loophole. The type checker and the coverage tool share no channel: a coverage
tool reports an uncovered branch regardless of what the type checker
concluded. NFR9.13 is a build gate and `project.md` forbids weakening it, so
as written B1 would face a gate that cannot pass, with the only standard
remedy being the pragma §A.4 bans. "Statically verified" would then be
available as cover for the *next* unreachable branch, which is precisely the
reasoning that produced the dead `ConflictError`.

The resolution is structural rather than configurational. **The exhaustiveness
check MUST be written so it produces no coverable branch in the first place**:
the mapping is declared total over the enumeration and the static checker
proves the totality, so there is no runtime `else` arm to cover. Where the
language cannot express that, **one bounded, named exclusion is permitted for
this single construct** — named in the coverage configuration by path and
symbol, never as an inline pragma, so it appears in a reviewed configuration
file rather than disappearing into a diff.

> The distinction being preserved: a branch unreachable **because a stronger
> check guarantees it** is different from one unreachable because nobody
> wrote a test. But that distinction justifies *how* the line is accounted
> for, never a claim that the coverage tool will somehow agree. Exactly one
> construct in this module qualifies, and it is named; a second candidate is
> a design signal, not a second exclusion.

**Two independent halves, and both are needed:**

| | NFR9.20 — generators from the enumeration | NFR9.25 — hand-written expected effect |
|---|---|---|
| **Catches** | A kind added to the enumeration but to neither side of the identity | A kind added to *both* but **on the wrong side** |
| **How** | Generated histories automatically include the new kind, so the identity fails on the commit that adds it | A named worked case per kind asserts what that kind alone does to outstanding and available credit |
| **Independent of** | — | The shared `identity_side` field that the fold itself reads |

**Why NFR9.20 alone is half a control.** If the property test derives its
expectation from the same `identity_side` field the fold reads, then test and
implementation **agree by construction**. A mis-sided kind balances exactly,
every check passes, and every enrollment carrying it is wrong. That is the T4
pattern — a test that cannot disagree with its implementation — reappearing
inside the fix for T6, and it is the same shape as the two defects this
project has already hit.

A single source of truth is correct for the *implementation* and fatal for the
*test*. The hand-written expectation costs one worked case per kind — seven
today — and is the only thing capable of contradicting a wrong side.

### A.6 The formatting operation (T7 → NFR9.22, NFR9.23, NFR9.24)

> **OQ-B1-1 is CLOSED (2026-10-18).** The rendering specification is below.
> The shape described in this section is unchanged; what was missing was the
> data, and the data now exists. The formatting operation was deferred out
> of B1 by the human's choice at that Bolt ("build everything except
> formatting"), so it arrives with the first Unit that assembles a money
> response, carrying NFR9.26 with it.
>
> **The rendering specification, both supported locales:**
>
> | Property | `bn-BD` | `en` |
> |---|---|---|
> | Digit set | **Western** `0123456789` | Western |
> | Grouping interval | **2,2,3** (lakh/crore): `12,34,567` | 3,3,3 |
> | Group separator | `,` | `,` |
> | Decimal separator | `.` | `.` |
> | Currency symbol | `৳` U+09F3 | `BDT ` |
> | Symbol position | **prefix, no space**: `৳1,234` | prefix + space |
> | Decimal places | 2 stored; **suppressed when zero** | same |
>
> **Two of these deliberately contradict CLDR, and the reasons are
> recorded so nobody later "fixes" them back to the locale default:**
>
> - **Digits.** CLDR gives `bn` a default numbering system of `beng`
>   (Bengali digits ০–৯), and Android's platform formatter follows it. We
>   use Western digits anyway. Every Bangladeshi *transactional* surface
>   checked renders money in Western digits — bKash, Nagad, Daraz,
>   Bangladesh Bank — while Bengali digits dominate *prose*, such as
>   newspapers. The split is by register, not by language. Our users read
>   money in bKash daily; matching that costs them nothing, and diverging
>   from it makes a fee figure unfamiliar at the moment trust matters most.
>   **This was the human's decision**, taken against the alternative, and it
>   is the one choice here that is a product call rather than a locale fact.
> - **Symbol position.** CLDR's `bn` currency pattern is `#,##,##0.00¤` —
>   symbol *after* the amount. Bangladeshi practice is uniformly `৳` first,
>   no space. CLDR is wrong for purpose here; note that `bn-IN` uses the
>   prefix, so the suffix is specific to the Bangladesh-default data.
>
> **Grouping is 2,2,3 and this one follows CLDR**, which matches practice:
> Bangladesh Bank's own circulars write `BDT 5,00,000`. It only becomes
> visible above ৳99,999 — rare for one fee, routine for the cross-batch
> dues total [PU-7.2], which is exactly where a wrong grouping would be
> least noticed and most embarrassing.
>
> **Poisha are withdrawn from circulation** — the smallest coin is ৳1 — so
> whole-Taka display is correct. The suppression is a *display* rule only:
> storage stays `NUMERIC(12,2)` and the `Money` type keeps 2dp, because
> partial approval, carry-forward and waiver arithmetic can all produce a
> non-zero paisa even when every input amount is whole.
>
> **A library hazard worth naming, because it will otherwise be found on a
> device.** The three candidate toolchains disagree, and no two of them
> fully agree: Python `babel` emits Western digits and 2,2,3 but cannot
> produce Bengali digits for this locale at all; ICU4J is CLDR-faithful
> (Bengali digits, 2,2,3, suffix symbol); the **desktop JDK gets the
> grouping wrong**, emitting 3,3,3. Android has backed `java.text` with ICU
> since API 24, so **a money-formatting test passing on desktop JVM or
> Robolectric can still be wrong on a phone** — the same class of defect as
> this project's SQLite-versus-real-Postgres rule, and it earns the same
> treatment. None of the three produces our specification by default, so
> the formatter is driven by an **explicit pattern**, never a locale
> default, and that explicitness is itself the thing under test.
>
> Server-side `format(locale)` remains the single renderer [TC-9, TC-15],
> which is what keeps this one specification authoritative instead of two
> surfaces drifting.

**The shape, unchanged.**

The operation takes the locale as an argument [BR5.6] and dispatches over a
**per-locale rendering specification held as data** — digit map, grouping
interval, grouping separator, decimal separator — rather than as branching
code. Two properties follow:

- Adding or correcting a locale is a data change, not a code change.
- Each locale's expected-output test (NFR9.23) reads as a row beside its
  specification, which is what makes the test table and the data table
  reviewable against each other.

**Behaviour while OQ-B1-1 is open — corrected at review.** An earlier draft of
this section said the operation ships with the English row only, failing
loudly on a Bangla locale, and treated that as safe. **It is not safe, and the
reason is a Unit-boundary error worth stating plainly.**

`format(locale)` is **not called by this Unit at runtime.** `functional-spec.md`
§2.8 step 4 and `contract-summary.md` §B.5 both place the
`amount`/`amount_display` pair in a **response**, so the caller is response
assembly in U7, U8 and U9. A missing Bangla row therefore raises **inside a
request handler in B6, B7 or B10**, against a real Bangla-locale request, and
surfaces to a teacher as a server error. No gate in B1 can fail on it, because
B1 never executes that path. The "loud failure" was loud in the wrong Unit and
the wrong phase — months later, in production, to a user.

**NFR9.26** — B1 MUST assert **at build time** that every supported locale has
a rendering specification row. The supported set is finite and known — Bangla
and English [TC-15, NFR3] — so this is a static completeness check, not a
runtime guard: the test enumerates the supported locales and fails if any
lacks a specification. A locale added later without its row fails the build on
the commit that adds it.

> **What this check does and does not establish.** "Bangla and English"
> currently exists as prose in several artifacts, with **no file designated
> as the definition**. The app's real locale set will be Android resource
> qualifiers created in later Bolts, which a Python-side check cannot see — so
> adding a `values-xx/` directory fires nothing here.
>
> As written the check therefore asserts **self-consistency** — every locale
> this module claims to support has a specification — not completeness
> against what the app actually offers. That is adequate for the V1 two-locale
> case and the risk is that the requirement reads stronger than it is, so it
> is stated plainly rather than left to be discovered. **The cheap
> strengthening, if a third locale is ever added**: designate one committed
> file as the supported-locale definition and have both the backend check and
> the Android build read it, so the two surfaces cannot disagree silently.

**What this means for OQ-B1-1 — resolved, by the second path.** The deferral
was never free, and the choice between two paths was made explicitly:

- **OQ-B1-1 closes before B1's formatting operation is implemented** — not
  what happened; or
- **the formatting operation is deferred out of B1 entirely**, together with
  NFR9.26 — **this is the path taken.** B1's Definition of Done was amended
  at the time to drop `format(locale)`, because `bolt-plan.md` had listed it
  among B1's unconditional deliverables and a fallback that silently fails
  the Bolt's own DoD is not a fallback.

OQ-B1-1 itself then closed on 2026-10-18 with the specification recorded at
the head of this section. Both obligations travel with the operation to the
first Unit that assembles a money response: the rendering specification as
data, and **NFR9.26's build-time completeness check**, which is what keeps a
missing locale row a build failure in that Unit rather than a server error in
front of a teacher.

> The earlier framing made deferral look costless by assuming the failure was
> contained in B1. It was not. Naming the build-time check and the DoD
> amendment is what makes the choice between those two paths an honest one.
>
> The three formatting requirements remain **conditional on OQ-B1-1 closing**
> rather than independently sufficient: NFR9.23's exact-output assertion has
> nothing to assert until the specification exists. NFR9.24 defeats the
> pass-through implementation; NFR9.26 is what moves the detection of a
> missing locale from a production request back to the build.

### A.7 Dependency and supply chain (T5 → NFR9.16, NFR9.17, NFR9.18)

The dependency surface is bounded to the language's decimal arithmetic, its
locale facilities, and the type/serialization annotations for the two
chokepoints. **The bound is enforced by Gate 1**: a dependency that drags in
I/O would need an import the gate refuses.

The project supply-chain posture is inherited unchanged — lockfiles and
checksum verification on both surfaces, secrets scanning blocking every push,
CVEs annotating per-push and blocking at the release gate. This Unit takes no
exception.

**What B1 establishes rather than merely obeys**: the lockfiles themselves and
the secrets-scanning pre-commit hook, which `team.md` sequences as
skeleton-time tooling. This Unit's own CVE exposure is near zero by NFR9.16;
the supply-chain risk it carries is about the tooling every later Bolt
inherits from it.

---

## Part B — The gate pipeline

Ordered cheapest-first, so a cheap failure never waits behind an expensive
one. All of it behind **one entrypoint runnable identically locally and in
CI**, because `team.md` names a gate reproducible only by pushing as a gate
that gets bypassed.

| Order | Step | Blocks on | Approx. cost |
|---|---|---|---|
| 1 | Secrets scan | Any match, no severity threshold | ~1s |
| 2 | Lockfile / checksum verification | Drift or a failed checksum | ~1s |
| 3 | Format + lint, **including Gate 2** | Any violation | ~1s |
| 4 | Type check (strict over this module) | Any error | ~5s |
| 5 | Unit tests + **branch coverage below 100%** | Failure or shortfall | ~5s |
| 6 | **Gate 1**, both violation fixtures, and **both gate-configuration assertions** | A gate that does not fire, or one whose scope no longer covers the tree | ~2s |
| 7 | Named-test manifest check | An entry with no matching test | ~1s |
| 8 | **Locale completeness** — every supported locale has a specification row | A supported locale with no rendering specification | ~1s |
| 9 | **Schema assertions** — database column types and precision; OpenAPI money pattern | A money column or field declared outside the chokepoints | ~3s |
| 10 | Property test over randomized histories | Any identity violation | ~20s |

**Why the property test is last**: it is the slowest and the one most likely
to be under active iteration when something cheaper is already broken.

**Where step 9 actually runs, and why it is listed here anyway.** The two
schema assertions of NFR9.30 need something B1 does not have: a migrated
database and a generated OpenAPI document. B1 creates neither — it has no
table and no endpoint. So the **checks are authored in B1** as part of this
Unit's control set and **first execute in the Bolts that create their
subjects**: the database assertion from B3, which runs the first migration,
and the OpenAPI assertion from B2, which owns the schema and its diff gate.

Listing them in this Unit's pipeline with that note, rather than omitting
them, is deliberate: they exist because of *this* Unit's chokepoints and
would otherwise belong to nobody. An assertion authored by the Unit whose
invariant it protects, and executed by the Unit that first has something to
assert against, is the correct split — and it is the same shape as U2 owning
the schema-wide privacy invariant that covers routes added later.

**But the split needs a failure mechanism, and naming it is the difference
between a pattern and a way of marking work done that is not.** The U2
precedent works because B2's definition of done *lists* the privacy invariant
explicitly. Neither B2's nor B3's DoD currently lists these two assertions:
B2 enumerates the OpenAPI file, the diff gate, the taxonomy, the `*_display`
rule, the route harness and the privacy invariant; B3 enumerates the first
migration and the governance schema test. So if B2 and B3 simply never wire
them up, **every Bolt passes its own stated DoD and the checks never exist.**

**NFR9.32** — The two schema assertions MUST be added to the definitions of
done they execute from: the OpenAPI money-pattern and `*_display`-pairing
assertion to **B2**, and the column type-and-precision assertion to **B3**.
Until those DoDs carry them, NFR9.30 is a design intention with no owner.

> This is the same failure the B1 `format(locale)` conflict exposed in §A.6,
> in the opposite direction: there, a DoD listed something the design wanted
> to defer; here, a design wants something no DoD lists. Both are resolved
> the same way — by changing the DoD rather than by hoping the gap is
> noticed. **Recorded as a cross-Bolt obligation**, because this Unit cannot
> amend another Bolt's DoD from inside its own stage.

**Why steps 1–2 block absolutely**, with no severity threshold: they are
binary, near-zero false positive, and always actionable by the person who just
pushed. `team.md` sets this posture and the reasoning is that a gate a solo
developer bypasses once becomes decoration.

---

## Part C — What this design does NOT include

Stated so a reviewer can distinguish an analysis that found nothing from one
that was not done.

| Usual security-design content | Status | Why |
|---|---|---|
| Authentication flow | **N/A** | No request, no caller identity. U3 owns it |
| Authorization model / lens design | **N/A** | No data to scope. U3 owns the lens; U2 the route harness |
| Encryption in transit | **N/A** | This module performs no network I/O. TLS terminates far above it |
| Encryption at rest | **Inherited** | This Unit owns the column *mapping*; the hosting decision owns the encryption |
| Input validation strategy | **Partial** | Two string inputs exist — the wire value and the locale — both constrained at entry by a pinned pattern and a finite set. No interpreter, so no injection sink |
| Security headers / CSRF / XSS | **N/A** | No HTTP response is produced here |
| Secrets management | **N/A** | The module reads no configuration at all [BR5.6], so it cannot hold a secret |
| Audit logging | **N/A** | No actor, no access event. U3 owns the authentication audit log |
| Rate limiting | **N/A** | No endpoint. U3 owns the OTP abuse controls |

---

## Part D — Residual risk

Honest statement of what remains after every mechanism above.

| Risk | Residual after controls | Why it cannot be fully closed here |
|---|---|---|
| **A wrong Bangla rendering ships** | **Open**, gated on OQ-B1-1 | NFR9.24 defeats a pass-through, and NFR9.23 defeats a rendering that differs from the specification. But if the human answers OQ-B1-1 *wrongly*, every test passes against the wrong answer. No NFR can carry a product judgement |
| **A named test exists but asserts nothing useful** | **Reduced, not closed** | The manifest verifies existence and the criterion makes a mismatch visible to a reader, but no mechanism can evaluate an assertion's worth. `team.md` already rejects always-passing tests in review, which is where this lands |
| **The identity itself is wrong in a way randomized testing does not reach** | **Low** | Eight worked scenarios and 20,000 randomized histories, with the kinds derived from the enumeration. The residual is a defect in the *generator*, which no test can self-detect |
| **A future dependency adds I/O** | **Low** | Gate 1 refuses the import, and NFR9.17 requires an admission note. The residual is a dependency performing I/O without an import the gate recognises |
| **Gate 2's reach is narrower than its role** | **Open, and named** | The control this document calls load-bearing is a **lint rule**, so it reaches exactly what the linter is configured to scan: Python source under the configured roots. It does **not** see Kotlin, raw SQL migrations, or any source outside those roots. NFR9.30's schema assertions cover the SQL path and NFR9.7's package-wide float ban covers the Kotlin surface, but the composite is three mechanisms with different reaches rather than one control — and reasoning about it as a single boundary is how a gap gets missed |

> **The honest summary**: every control above fails in CI. The two residuals
> that matter both involve a human judgement no mechanism can make — what
> Bangla numerals should look like, and whether a test asserts something
> worthwhile. Both are named rather than papered over.

---

## Assumptions & Open Questions

**OQ-B1-1 remains open**, carried from NFR Requirements. The Bangla money
rendering is unspecified: digit set, grouping interval, separators, currency
symbol.

**Its cost changed at this stage's review, and the change is the important
part.** The NFR Requirements framing treated deferral as free, on the
reasoning that a missing locale row fails loudly. §A.6 now records why that
was wrong: `format(locale)` is called by **response assembly in U7, U8 and
U9**, not by this Unit, so the failure would land in a request handler in B6,
B7 or B10 — in production, to a teacher, months later. NFR9.26 moves the
detection to B1's build. But a build-time completeness check **cannot pass
while a supported locale has no specification**, so the question must now be
answered rather than deferred around.

**Two honest paths, and the human picks one:**

1. **Close OQ-B1-1 before B1's formatting operation is implemented.** The
   intended path. Costs one early decision and nothing else.
2. **Defer the formatting operation out of B1 entirely**, with NFR9.26. This
   requires **amending the B1 Definition of Done**, which currently lists
   `format(locale)` among its unconditional deliverables — a fallback that
   silently fails the Bolt's own DoD is not a fallback.

**Blocks**: B1's formatting operation and NFR9.26's completeness check, then
B6, B7 and B10, whose response assembly calls it.
