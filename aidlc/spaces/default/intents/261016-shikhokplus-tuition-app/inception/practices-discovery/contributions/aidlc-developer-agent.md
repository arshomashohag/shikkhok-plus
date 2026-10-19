**Collaborator:** aidlc-developer-agent

## Contribution

Remit: naming, layer boundaries, error handling, file organization, code-style
conventions. The draft is strong on *what* should be true and weak on *what
makes it true*. Most of my objections share one shape: a rule stated as a
structural guarantee but enforced by review. With a single reviewer who is
learning one of the two surfaces [OC-1, OC-3], review-enforced structure is the
weakest available mechanism, and it is weakest exactly where the draft most
needs it (money, lens, layer boundary). Below, each is converted into something
that fails in CI or at import.

---

### 1. Python conventions

**Ruff for format and lint: correct, and the reasoning should be stronger than
"one configuration."** The real argument is speed-at-the-commit-boundary: Ruff
runs the whole backend in well under a second, which is what makes a pre-commit
hook survive contact with a solo build. A Black-plus-Flake8-plus-isort chain is
slow enough that it gets skipped, and a skipped check is not a check. Keep Ruff;
state the reason as "fast enough to run on every save and every commit."

Two gaps in the Ruff proposal:

- **The draft never names the rule set.** "Ruff" without a selected rule set is
  roughly Flake8's defaults, which catch almost none of what matters here. Name
  it in `pyproject.toml`. My recommendation, with the reason each earns its
  place on *this* project:
  `E,F,W` (baseline), `I` (import order, replaces isort), `UP` (pyupgrade —
  keeps 3.12 idiom), `B` (bugbear — catches mutable default args, which is a
  real defect class in FastAPI dependency signatures), `ASYNC` (blocking calls
  inside `async def` — directly relevant, because a sync SQLAlchemy call in an
  async endpoint will silently serialize the whole event loop on a 2 GB
  Lightsail instance), `S` (bandit subset — hardcoded secrets, weak hashing;
  relevant to the OTP-hashing and no-secrets rules), `DTZ` (naive datetime —
  relevant because fee periods are calendar-month-with-clamp in a non-UTC
  country and a naive `datetime.now()` will eventually produce an off-by-one-day
  due date), `NPY`/`PD` not applicable, `RUF` (Ruff's own). Add `PLR2004`
  (magic value comparison) scoped to the money and fee modules only.
- **`S` and `DTZ` need per-path exclusions for tests**, or the test suite
  becomes a rule-ignore graveyard. Set `[tool.ruff.lint.per-file-ignores]` with
  `"tests/**" = ["S101"]` from the first commit rather than retrofitting it.

**Line length: the draft does not state one.** It should, because this is the
one style choice that silently changes how code is *written* rather than just
formatted. Ruff defaults to 88. Note for the interview: the user's global
Python standard is 79 characters, and Ruff's formatter honours whatever
`line-length` is set. If 79 is the house rule it must be declared in
`pyproject.toml` at project setup, because 79 vs 88 is not a diff you want to
discover on Bolt four — it rewrites every file. This belongs in the interview.

**Partial-strict mypy: coherent, but the draft describes it in a way that will
not work.** "Strict mode on the money module, the authorization layer and the
Pydantic schemas" is the right *target* and the wrong *mechanism*, for a reason
worth stating precisely:

mypy strictness is not a property of the module being checked; it is mostly a
property of what that module can *see*. `--strict` bundles
`disallow_untyped_defs` (local — fine, applies per-module) with
`disallow_untyped_calls` and `disallow_any_expr`-adjacent behaviours (not
local — they fire on values arriving from un-annotated code elsewhere). So
"strict on the money module" where the money module imports an unchecked
repository gives you one of two outcomes: either a wall of
`Call to untyped function` errors that get silenced with `# type: ignore` until
the strictness is decorative, or `Any` flows in from the un-strict side and
strict mode checks nothing of consequence. That is the boundary problem, and it
is real.

The fix is not to abandon partial strictness — it is to make the strict region
**import-closed**, which it almost is already:

```toml
[tool.mypy]
python_version = "3.12"
strict = false
warn_unused_ignores = true
warn_redundant_casts = true
disallow_untyped_defs = true        # baseline everywhere, not just strict islands
check_untyped_defs = true

[[tool.mypy.overrides]]
module = ["app.money.*", "app.authz.*", "app.schemas.*"]
strict = true
disallow_any_explicit = true        # the point: no Any laundering in these three
```

Two things make this hold rather than rot:

1. **`disallow_untyped_defs = true` as the global baseline**, not just inside the
   strict islands. This is the single setting that makes partial strictness
   coherent: every function anywhere has annotated params and return, so
   `disallow_untyped_calls` inside the strict region has nothing to complain
   about. The *remaining* strict-only settings are then genuinely local
   (`disallow_any_explicit`, `warn_return_any`, no implicit `Optional`). Without
   this baseline, partial strict is the incoherent thing the brief suspects it
   is. With it, it is a clean two-tier model.
2. **The strict region must not import the un-strict region.** `app.money` should
   depend on nothing but `decimal` and its own value types — no ORM, no session,
   no settings. `app.authz` depends on repository *protocols*, not repository
   implementations. That is the same discipline §2 requires for the money
   boundary, which is convenient: one architectural rule buys both.

One addition: **`warn_unused_ignores = true` globally**. Without it, a
`# type: ignore` added during a hard afternoon stays forever and nobody learns
it became unnecessary.

**Docstrings on every module, class and public function: I object, and would
replace it.** Not because documentation is bad, but because "every public
function" on a solo agent-written codebase produces a predictable failure mode:
the docstring restates the signature. A function named
`resolve_teacher_lens(account_id: AccountId, batch_id: BatchId) -> bool` with a
docstring reading "Resolve the teacher lens. :param account_id: the account id.
:return: whether the lens applies" has added a maintenance obligation and zero
information, and — worse — it will drift, at which point it is actively
misleading to a reviewer who is already stretched thin on the Android side.

What I would mandate instead, which is narrower and higher-value:

- **Module docstring on every module: keep this.** It is one sentence per file
  and it is the thing that orients a reviewer, and it is cheap because a module
  changes purpose rarely.
- **Docstring mandatory where the signature does not carry the meaning**, which
  on this project is a nameable set rather than a vague judgement call:
  (a) every function in the money module — document the rounding behaviour, the
  sign convention, and what happens at zero and negative, because those are
  exactly the branches [TC-20] requires tests for and prose is where the intent
  lives; (b) every authorization/lens function — document which lens and which
  relationship grants it, because "which lens authorizes this" is a §3 rule;
  (c) anything whose correctness depends on something not in the signature:
  concurrency assumptions, the `ON CONFLICT DO NOTHING` contract, short-month
  clamping, idempotency guarantees, retry-safety.
- **`:raises:` is mandatory wherever a caller must handle it** — which ties into
  §6 below, because the error taxonomy is only usable if the raise sites
  document which class they raise.
- Enforce via Ruff `D` rules scoped by path, not globally:
  `pydocstyle` convention, `D100` (module) everywhere;
  `D102`/`D103` (public method/function) in `per-file-ignores` *off* for
  `app/money/**` and `app/authz/**` and ignored elsewhere. That makes
  "docstrings where they matter" a lint result rather than a review opinion, and
  it is a two-line config.

**Type hints not duplicated in docstrings: agree, unreservedly.** With Sphinx
style, that means `:param x:` with a description and no `:type x:` / `:rtype:`.
Worth stating explicitly in the config note, because autodoc will happily
produce both and some editor templates insert `:type:` by default.

**One missing Python convention the draft should add: `Decimal` construction is
itself a boundary.** `Decimal(0.1)` is a silent float-to-decimal laundering that
no `float` ban catches, because the resulting type *is* `Decimal` — the value is
just already wrong. Ban `Decimal(<float>)` construction specifically (Ruff
`RUF032` covers `Decimal()` called with a float literal; a variable-valued float
needs the §2 type discipline instead). This is the single most likely way the
`NEVER use float or double for money` rule gets violated while passing every
check in the draft.

---

### 2. The money-module boundary

**Yes, the import-boundary check should exist from day one, not "if it is ever
violated."** The draft's conditional framing inverts the economics. The cost of
adding the check at project setup is about fifteen lines of config. The cost of
adding it after the first violation is the same fifteen lines *plus* finding and
unwinding however much arithmetic leaked in the interim — and with the fee model
already known to be in revision [D-18], the leak will be inside code that is
about to be rewritten, which is the worst time to discover it. "We add it if
violated" also means the first violation is detected by review, which is the
mechanism the rule exists to avoid depending on.

Concretely, two independent mechanisms, because they catch different things:

**(a) Import-direction check — catches the wrong module importing money
internals.** Ruff's `flake8-tidy-imports` banned-api, in `pyproject.toml`:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"decimal".msg = "Import money types from app.money; raw Decimal is money-module-only."
"app.money._internal".msg = "Use the app.money public API."
```

with `per-file-ignores` re-permitting `decimal` inside `app/money/**`. This is
the load-bearing one: **banning raw `decimal` imports outside the money module**
is what makes the boundary mechanical rather than aspirational, because every
piece of money arithmetic outside the module needs either `Decimal` or a float,
and both are now blocked.

**(b) A layered-import test, which the draft has no equivalent of.** One pytest
test using `import-linter` (or ~30 lines walking the AST) asserting the contract:
`app.money` imports nothing from `app.api`, `app.db`, `app.repositories`,
`app.authz`, or `app.schemas`. This is the test that keeps the strict region
import-closed for §1's benefit, and it is the one that catches the *plausible*
violation — not someone doing arithmetic in a view, but someone making
`app.money` take a `Session` "just to look up the batch default fee," which
destroys both the testability and the mypy story in one commit. It fails in CI,
names the offending import, and costs nothing to maintain.

**How to structure the module so the boundary is enforceable:**

The key structural decision, and the one the draft does not make: **money is a
type, not a number**. Introduce `Money` as a value object — a frozen dataclass
wrapping a `Decimal` with BDT implicit — and make it the only money type that
crosses the module boundary. Everything then follows:

- `Money` has no `__float__`, no `__int__`, and raises on
  `Money(<float>)`. A float cannot get in, and a `Money` cannot get out into a
  float context. The `NEVER float for money` rule becomes a property of the type
  rather than a rule someone enforces.
- `Money.__add__` / `__sub__` accept only `Money` (mypy catches
  `money + 5` as an error rather than it quietly working).
- Multiplication is *not* `__mul__`. `Money * x` is where rounding enters, so it
  is a named method that forces the caller to say what they mean:
  `amount.apply_rate(rate: Decimal) -> Money` — rounds, with the module's single
  rounding mode. No anonymous rounding.
- Division is not exposed at all until a requirement needs it. If a requirement
  needs splitting an amount, that is `Money.allocate(n)` returning a list whose
  sum is exactly the original — the standard remainder-distribution method. An
  unconstrained `/` is how a one-paisa discrepancy enters a ledger.
- `ROUND_HALF_UP` declared once as a module constant, passed to `quantize` at
  the two or three places rounding occurs. Note for the interview: banker's
  rounding (`ROUND_HALF_EVEN`, Python's default) is wrong for consumer-facing
  BDT fee amounts — a teacher checking arithmetic by hand expects half-up. This
  is a decision, not a default; it must be made explicitly and written down,
  because it is invisible once chosen and expensive to change after a ledger
  exists.
- Store the `Decimal` already quantized to 2dp at construction. An unquantized
  `Decimal` inside `Money` means equality and `__hash__` are inconsistent
  (`Decimal("1.5") == Decimal("1.50")` is True but their hashes differ in ways
  that bite in sets/dict keys), and means two "equal" amounts can serialize
  differently.

**What counts as "money arithmetic" at the edges — the brief is right that the
draft leaves this undefined, and it is the question that decides whether the
rule is usable.** My answer:

| Operation | Inside the module? | Why |
|---|---|---|
| Add, subtract | **Inside** — as `Money.__add__`/`__sub__` | Any ledger total is arithmetic. |
| Summation for display (a dues total across batches) | **Inside** — `Money.sum(iterable)` | This is the one the draft's phrasing would accidentally permit, and it is the one that will be written as a Python `sum()` with a `0` start value, which crashes or coerces. Provide `Money.sum()` with a zero identity and the problem disappears. |
| Comparison (`>`, `==`, is-it-paid) | **Inside** — `__eq__`/`__lt__` on the type | Comparison is not arithmetic, but it must still be *type-safe*: `balance > 0` comparing `Money` to `int` must be a type error, not a surprise. Define a `Money.ZERO` constant so callers write `balance > Money.ZERO`. Cheap, and it removes the one place a bare `0` creeps in. |
| Percentage / rate (a discount, a late fee) | **Inside** — `apply_rate` | Rounding point. Never outside. |
| Is-zero / is-negative predicates | **Inside** — `is_zero()`, `is_positive()` | Keeps sign-convention knowledge in one place. |
| Formatting for display (`"৳1,200.00"`) | **Outside** is acceptable, *inside* is better | Not arithmetic, but note: with Bangla locale [TC-15], digit rendering and separator placement are locale decisions. Put `Money.format(locale)` in the module so the server is the only thing deciding, consistent with [TC-9]. |
| JSON string serialization | **Inside** — the module owns the Pydantic serializer/validator for `Money` | [D-20] says money crosses as a JSON string. That must be *one* Pydantic annotated type reused by every schema, not a per-field `field_serializer`. Per-field is how one endpoint eventually emits a number. |
| SQLAlchemy column type | **Inside** — the module owns a `TypeDecorator` mapping `Money` ↔ `NUMERIC(12,2)` | Otherwise every model independently declares `Numeric(12,2)` and one eventually declares `Numeric(10,2)` or a `Float`. |

That last pair is the strongest argument for making money a type rather than a
rule: **it gives the boundary two chokepoints that every money value must pass
through anyway** (DB and API), and both are owned by the module. A money value
physically cannot enter or leave the system without going through
`app.money`. That is what makes the boundary enforceable rather than
aspirational — not the lint rule, which is only the backstop.

One consequence the lead should note: this makes the money module a Unit of its
own in the DAG, buildable and fully testable before any endpoint exists. It is
the natural home for the 100% branch coverage the draft proposes, and it is
pure-function code with no I/O, which is why that target is achievable there and
would not be elsewhere. The quality agent's remit, but it follows from this
structure.

---

### 3. "Every endpoint names its lens"

The draft's instinct — explicit dependency, not a comment — is right. Its gap is
that an explicit dependency is still *optional*: the failure mode is not a wrong
lens, it is a **forgotten** lens, and a dependency you forgot to add produces an
endpoint that works perfectly and authorizes nothing. That is precisely the
silent failure [D-2, TC-11] is meant to prevent, and it must fail in CI.

**Structure it so the un-lensed endpoint is detectable, in three layers:**

**(a) The lens is a dependency that returns a value the handler needs.** Not
`dependencies=[Depends(require_teacher_lens)]` (a side-effecting guard whose
absence is invisible), but:

```python
async def list_batch_students(
    lens: Annotated[TeacherLens, Depends(teacher_lens_for_batch)],
) -> StudentListResponse:
```

where `TeacherLens` carries the resolved `owner_id` the query needs. Now the
lens is not a guard the handler can be written without — the handler *cannot
compile a query* without it, because the scoping value lives inside the lens
object. A forgotten lens becomes a `NameError`/type error rather than an open
endpoint. This is the single most valuable change: it converts authorization
from a precondition into a data dependency.

**(b) A test that enumerates the route table and asserts every route resolves a
lens.** This is the mechanical check the brief asks for, and it is about 20 lines:

```python
def test_every_route_declares_a_lens(app: FastAPI) -> None:
    unlensed = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and not any(
            _is_lens(d) for d in route.dependant.dependencies
        )
    ]
    assert not unlensed, f"routes with no lens: {unlensed}"
```

with `PUBLIC_ROUTES` an **explicit frozenset** containing exactly the OTP issue
and verify endpoints, the health endpoint, and the external deletion route
[TC-19]. The allowlist is the important half: adding a public endpoint requires
editing a list in a test, which is a reviewable, deliberate act. `_is_lens`
walks `route.dependant` recursively (a lens may be nested inside a composed
dependency) and matches on the dependency's return annotation being a `Lens`
subtype, not on the function's name — name-matching is how this check gets
defeated by a rename.

This runs at collection time against the real app object, so it is effectively
import-time: a new endpoint without a lens turns the CI red on the commit that
adds it, not in review.

**(c) Response-schema separation, which the draft has as a privacy rule and
should also be a lens rule.** Teacher-facing and student-facing responses are
distinct Pydantic models [D-7]. Add: a lens type parameterizes which response
models an endpoint may return, so a teacher-lens endpoint returning a
`StudentPrivateResponse` is a mypy error. This is the layer that catches the
*right-lens-wrong-data* case, which (a) and (b) do not.

One warning on FastAPI mechanics: if lens resolution hits the database on every
request (it must — [TC-11] forbids caching), the lens dependency is the hottest
query in the system, and on a single 2 GB Lightsail instance that matters. The
right answer is per-request memoization within one request's scope (same
account, same batch, resolved once per request), which is **not** a cached role
and does not violate [TC-11] — worth stating explicitly in the practice so that
nobody later "optimizes" it into a real cache, and so nobody avoids the
necessary memoization out of fear of the rule. Name the distinction:
request-scoped memoization is permitted; cross-request caching is forbidden.

---

### 4. Android conventions

**"Whatever current Google samples do" is sound as a default and unsound as a
rule, and the draft states it as a rule.** Deferring to the best-documented
convention is right for exactly the reason given [OC-3] — reviewability and
applicable help. But "where our preference and the Google sample disagree, the
Google sample wins" has no exception clause, and there are three places it will
actively mislead:

1. **Google samples assume analytics and Firebase SDKs are fine.** `nowinandroid`
   and most architecture samples wire in Firebase Analytics/Crashlytics as a
   matter of course. Here that is a [TC-3, TC-6, D-37] violation that would be
   copied in while following the rule. The forbidden-identifier check must
   outrank the sample, explicitly.
2. **Google samples have no money.** There is no canonical Android sample for
   decimal money, so "what the sample does" is `Double` or a formatted string,
   and the sample is wrong for this project. [TC-7] outranks it.
3. **Google samples are offline-first.** `nowinandroid`'s whole data layer is
   built around local-first with sync and an offline write path. [TC-8, D-9]
   explicitly forbid a write queue in V1. A developer following the sample's
   repository pattern will inherit an architecture designed for the opposite
   constraint, and will build the scaffolding for a write queue that must not
   exist.

So the rule needs a stated precedence, which I would phrase as: *project
constraints outrank the Google sample; the sample decides everything the
constraints do not.* That keeps the benefit and closes the three traps. The
draft's version, read literally, loses on all three.

Also: "current Google samples" is not a single thing and the draft should name
which. Pin it. `architecture-samples` and `nowinandroid` differ substantially,
and "whatever is current" is unpinnable a year from now. Name the repo and the
commit/tag consulted, in the practice, so a later disagreement is resolvable.

**ktlint vs spotless: these are not alternatives and the draft treats them as
one.** Spotless is a Gradle plugin that *runs* formatters; ktlint is the
formatter. The real choice is ktlint-via-spotless, ktlint-via-its-own-Gradle-
plugin, or ktfmt-via-spotless. Recommendation: **ktlint with
`official` code style, run through spotless**, because spotless gives
`spotlessApply`/`spotlessCheck` uniformly and will also cover the XML
(`strings.xml`, with Bangla content) and the Gradle files, which ktlint alone
will not. Decide it at project setup; the draft is right that after the first
Android Bolt is too late, because the first reformat is a whole-module diff.

Add **detekt** as a separate decision from the formatter, since the draft's
`Double`/`Float` money rule needs it (Android Lint cannot express it).

**On the `Double`/`Float` detekt rule: the draft's version is too narrow and
will not catch the real failure.** "Forbidding `Double`/`Float` in
money-carrying model classes" requires knowing which classes carry money, which
is the thing a reviewer unfamiliar with the codebase cannot reliably know, and a
custom detekt rule is real work to write and maintain.

The better mechanism is the same one as §2: **make money a type on the client
too.** A `Money` value class (Kotlin `@JvmInline value class Money(val amount:
BigDecimal)`) with a kotlinx.serialization serializer that reads *only* a JSON
string and rejects a JSON number. Then:

- A `Double` cannot be assigned to a `Money` field — the compiler stops it, with
  no custom lint rule at all.
- A backend regression that emits a JSON number for a money field fails *client
  decoding at runtime and in the contract test*, which is strictly better than
  the draft's contract-test-only assertion, because it also catches a
  hand-written client model that forgot the annotation.
- The detekt rule then becomes a trivial backstop rather than the mechanism:
  forbid `Double`/`Float` in the whole `:data:model` package (a package-scoped
  ban, which `ForbiddenTypes`-style config can express) rather than a semantic
  "money-carrying" judgement.

The symmetry with §2 is the point: one `Money` type per surface, two
serializers, and the float ban is a compiler property on both sides rather than
two lint rules and a review habit.

**File organization for a developer unfamiliar with Android: by feature, with a
layer split inside each feature.** Not by layer at the top level. Reasoning,
specific to this situation rather than general taste:

- Top-level-by-layer (`ui/`, `data/`, `domain/` each containing all features)
  means every Bolt touches every top-level package, so every diff is spread
  across the tree. For a reviewer who is learning the framework, the single most
  valuable property of a diff is that it is *localized* — "this Bolt is the
  attendance screen, here are its seven files, all in one folder." By-layer
  destroys that.
- The Bolt structure is already feature-shaped: PU-1 through PU-7 are vertical
  slices. Matching the directory layout to the Bolt layout means a Bolt maps to
  a directory, which makes "is this Bolt complete" a question you can answer by
  looking at one folder.
- By-feature also scopes the review of the layering rule: whether a ViewModel
  holds business logic is checkable within one feature folder, against the three
  or four files next to it.

So:

```
feature/
  auth/        { ui/ (composables + screen), AuthViewModel.kt, AuthUiState.kt }
  batches/     { ui/, BatchesViewModel.kt, BatchesUiState.kt }
  attendance/  ...
  fees/        ...
core/
  network/     { Retrofit service interfaces, DTOs, Money serializer }
  database/    { Room entities, DAOs }
  model/       { domain models incl. Money }
  designsystem/
  ui/          { shared composables }
```

Two notes on this. First, this *is* the `nowinandroid` shape
(`feature/*` + `core/*`), so it satisfies the defer-to-Google rule rather than
contradicting it — which is a point in its favour. Second: keep it as **packages
in one Gradle module for V1, not Gradle modules.** `nowinandroid` uses ~40
Gradle modules; replicating that multiplies build configuration and build times
for a two-surface solo project and is a learning cost paid for nothing. One
`:app` module with this package structure converts to modules later if ever
needed. This is a place where copying the sample faithfully is a mistake, and it
belongs in the interview as an explicit "do not do the modularization part."

**On the layering rule itself, one sharpening.** "ViewModel holds UI state,
repository holds data access, no business logic in either" leaves a gap: with
[TC-9] forbidding business logic client-side, where does the *UI-state mapping*
live? Formatting a balance, deciding whether to show a "paid" badge, choosing
which empty state to render — these are not business rules, but they are
decisions, and if they have no declared home they will end up in composables,
which is where they are untestable. Declare it: the ViewModel maps a server
response to a UI state data class, that mapping is where all such decisions
live, and a composable receives a UI state and renders it with no conditionals
that depend on domain values. Then "a composable that computes a fee balance is
a bug" generalizes correctly, and the Turbine/JUnit tests the draft proposes
have a well-defined target — the mapping function — rather than being an
untargeted "test the ViewModel."

---

### 5. Layer boundaries across the whole system

The constraint is [TC-9, D-31]: every business rule server-side, the client
renders. **Where it erodes first, in the order I expect it:**

1. **Empty-state and badge logic in composables.** The very first screen that
   shows a fee status will have `if (balance > 0) "Due" else "Paid"` in the
   composable. That is a business rule — *what counts as due* — rendered as if
   it were presentation. It is also almost invisible in review because it looks
   like UI code. This is erosion #1 and it will happen in the first fee Bolt.
   **Convention that prevents it:** the server response carries the *decided*
   value, not the input to the decision. `status: "due" | "paid" | "partial"` as
   a field the server computes, alongside the amount. The client switches on a
   server-provided enum, never on a comparison. State this as a rule:
   **if the client is comparing a domain value, the server should have sent a
   decision.** That is a mechanically checkable review question and it is the
   single highest-value layering convention on this project.

2. **Client-side filtering and sorting of a list.** The cross-batch dues screen
   [PU-7] is driven by outstanding balance rather than active status [PU-7.2] —
   a *business* definition of who appears. The moment the client sorts or
   filters that list locally, it has reimplemented that definition. **Convention:**
   list endpoints return the list in the order and membership the server
   decided; the client may not filter or re-sort a domain list. Client-side sort
   is permitted only for purely lexical cases the server has declared unordered.

3. **Room cache as a shadow model.** [TC-8, D-9] make Room a read cache. The
   erosion is Room entities drifting into a parallel domain model with their own
   derived fields and their own staleness rules, at which point the client has a
   data model with business semantics. **Convention:** Room entities mirror the
   API DTO shape one-to-one and carry no derived fields, only a
   `fetched_at` timestamp. Any derived value in a Room entity is a layering
   defect.

4. **Validation duplicated client-side and then diverging.** Some client
   validation is legitimate UX (phone number length before submit). It erodes
   when it becomes authoritative — the client rejecting a payment amount by a
   rule the server does not have, or the two rules diverging silently.
   **Convention:** client-side validation is permitted only for *format*, never
   for *policy*, and every client-side check must have a server-side check that
   would also reject it. The client check is an optimization, never a gate.

5. **The lens hint shaping more than the UI.** [D-2] allows the client to send a
   lens hint for UI shaping and forbids trusting it for authorization. Erosion:
   the hint starts selecting which endpoint to call, then which fields to
   expect, and eventually some code path treats it as the role. **Convention:**
   the hint affects navigation only, and the server response is
   self-describing — it says which lens produced it. The client renders from the
   response, not from the hint it sent.

The cross-cutting convention behind all five: **the API returns decisions, not
inputs to decisions.** Every one of these erosions is the client receiving raw
domain values and deciding something about them. If the response carries the
decision, the client has nothing to decide with, and the boundary holds
structurally rather than by discipline. I would promote that one sentence into
the practice, because it converts an unfalsifiable rule ("no business logic
client-side") into a checkable one ("does this response force the client to
compute something?").

---

### 6. Error handling

**Not specific enough to act on, no.** "Error handling at every integration
boundary, recoverable distinguished from fatal" is a statement of intent, and
every developer who reads it will implement something different. It also does
not say *who* distinguishes, *where* the distinction is recorded, or what the
client does with it — and with the client forbidden from holding business logic
[TC-9], the client cannot be the one deciding whether an error is retryable.

**What the convention should be — four parts:**

**(a) A closed error taxonomy, defined once, as an exception hierarchy.** Not
per-boundary ad-hoc handling. Four classes, chosen because they map to four
distinct caller behaviours:

| Class | Meaning | Caller behaviour | HTTP |
|---|---|---|---|
| `ValidationError` | The request is wrong | Fix and resubmit; never retry as-is | 400/422 |
| `AuthorizationError` | No lens grants this | Re-auth or stop; never retry | 401/403 |
| `ConflictError` | Valid request, state forbids it (cycle already paid, enrollment inactive) | Refetch and decide; retry is wrong | 409 |
| `TransientError` | The operation may succeed if repeated (gateway timeout, DB deadlock, FCM 5xx) | Retry with backoff | 503 |
| `FatalError` | Bug or unrecoverable (fallthrough) | Do not retry; alert | 500 |

The important property: **retryability is a property of the error class, not a
judgement at the call site.** That is what makes "recoverable distinguished from
fatal" actionable — the distinction is made once, at the raise site, by choosing
a class, and every layer above reads it off the type. One exception handler in
FastAPI maps the hierarchy to responses, so no endpoint writes its own
try/except for these.

**(b) The wire format carries the class, so the client does not infer it.** A
single error envelope: `{"error": {"code": "FEE_CYCLE_ALREADY_SETTLED",
"retryable": false, "message_key": "..."}}`. Three things to note: `retryable`
is a **server-provided boolean**, which is exactly the [TC-9] point — the client
does not decide retryability from an HTTP status, it is told; `code` is a stable
machine value, so the client switches on it rather than on message text; and
`message_key` rather than `message`, because the user-facing string must come
from `strings.xml` in Bangla or English [TC-15, D-43] and a server-sent English
message cannot be localized by the client. The draft's localization rule and its
error-handling rule collide here and neither notices — a server `message` field
guarantees untranslated English error text in a Bangla UI. Worth flagging to the
lead as an actual contradiction to resolve, not a refinement.

**(c) Per-boundary rules, named, because the four named boundaries genuinely
differ:**

- **SMS gateway** — the only boundary where a failure *costs money* and where a
  retry may *double-charge* and double-message. Rule: the gateway call is
  wrapped in one adapter [PU-1.4], a send is attempted **once** with no
  automatic retry, a timeout is recorded as `unknown` rather than `failed`
  (because the SMS may have been delivered), and the user-facing path is
  "request a new OTP" rather than a silent resend. Automatic retry here is a
  bug, not resilience. The global daily ceiling [D-33] is checked *before* the
  call, and the ceiling breach is a `ConflictError`, not a `TransientError` —
  retrying into a cost ceiling is exactly wrong.
- **Database** — distinguish three cases rather than one: a constraint violation
  on `(enrollment_id, period)` is **not an error at all** (it is the
  `ON CONFLICT DO NOTHING` success path [D-21]); a serialization failure or
  deadlock is `TransientError` with bounded retry of the whole transaction; a
  connection failure is `TransientError` but must not be retried inside a
  request — it fails fast, because a 2 GB single instance under connection
  pressure gets worse, not better, if every request retries. State the
  transaction boundary too: one transaction per request, committed by the
  endpoint, never by a repository method — otherwise a partial money write
  becomes possible.
- **FCM** — best-effort by nature. A failed push must **never** fail the
  operation that triggered it. Rule: push dispatch happens after commit, outside
  the request transaction, and its failure is logged and not surfaced. An
  `UNREGISTERED` response is not an error, it is a signal to delete the stored
  token [D-42]. This is the boundary the draft's "silent failures are not
  acceptable" would get wrong if read literally — here a non-fatal logged
  failure is correct, and the rule needs to say so.
- **S3 (`pg_dump` backups)** — a failed backup is a *fatal operational* event
  even though no user notices. Rule: backup failure alerts; and the draft's own
  "an untested backup is not a backup" needs the corollary that an unverified
  *upload* is not a backup either — assert object existence and non-trivial size
  after upload.

**(d) Two rules that make the taxonomy hold:**

- **Never catch bare `Exception` except in exactly two places**: the FastAPI
  exception handler, and the scheduled fee-generation job's top level (where a
  crash must not kill the daily run). Everywhere else, catch the specific
  exception and re-raise as a taxonomy class. Ruff `BLE001` enforces this.
- **Every log of an error carries the request/correlation id and never carries a
  phone number, an OTP, or a token.** The draft has `NEVER store or log an OTP in
  plaintext` as a rule; generalize it, because the likelier leak is a phone
  number in an exception message from the gateway adapter, which no OTP rule
  catches. Phone numbers are children's-adjacent personal data under
  [RC-1/RC-2/RC-3], so this is a compliance rule, not hygiene.

---

### 7. What the interview must resolve

In my remit, ordered by cost-of-getting-it-wrong:

1. **Rounding mode for BDT money: `ROUND_HALF_UP` or `ROUND_HALF_EVEN`.** Must
   be decided before the first money line is written, is invisible afterwards,
   and is expensive to change once a ledger has rows. I recommend
   `ROUND_HALF_UP`; the user must confirm, because Python's default is the other
   one and a default here is a silent decision.
2. **Python line length: 79 or 88.** Decided at setup or it is a whole-repo
   reformat later. The user's stated global standard is 79; the draft is silent;
   Ruff defaults to 88.
3. **`Money` as a value type on both surfaces, or `Decimal`/`BigDecimal`
   directly with lint rules.** This is the structural fork behind §2 and §4. I
   recommend the value type; it is more code up front and it is what makes the
   float ban a compiler property instead of a review habit. The user should
   decide knowingly rather than inherit it.
4. **Whether the lens-coverage test and the import-boundary check are in from
   the first Bolt.** The draft defers both to "if violated." I recommend both at
   setup. Cheap now, and they are the two checks that convert the draft's two
   most important structural rules from aspirations into CI results.
5. **Docstring scope: everywhere, or money-plus-authz-plus-modules.** The user's
   global standard says everywhere; I argue it becomes noise and drift at
   "every public function" on an agent-written codebase. Needs an explicit
   call, since it is a direct tension between a stated personal standard and a
   project-specific argument.
6. **Android: one Gradle module with feature packages, or multi-module.** The
   Google sample says multi-module; I say that part of the sample should not be
   copied. Explicit decision, because reversing it later is a build-system
   rewrite.
7. **ktlint-via-spotless vs ktlint-plugin vs ktfmt, and detekt yes/no.** The
   draft presents ktlint and spotless as alternatives, which they are not.
8. **Does the error envelope carry `message_key` or `message`?** This resolves
   the localization/error-handling contradiction in §6(b). Server-sent English
   message text in a Bangla-first UI is a user-visible defect, and the draft
   currently mandates both halves without noticing they conflict.
9. **Precedence when a Google Android sample conflicts with a project
   constraint.** The draft gives the sample unconditional priority; three named
   conflicts exist ([TC-3/TC-6] analytics SDKs, [TC-7] money as `Double`,
   [TC-8] offline-first write queue). Needs a stated precedence rule.
10. **Where UI-state mapping lives**, given [TC-9]. Not currently assigned a
    home, which means it will land in composables.

## Positions

- AGREE: Ruff for both format and lint — the decisive argument is that it is
  fast enough to run on every save and commit, so it does not get skipped.
- AGREE: Partial-strict mypy is a coherent position, but only with
  `disallow_untyped_defs` as the *global* baseline and the strict region kept
  import-closed; without both, the boundary problem the brief suspects is real.
- AGREE: Money confined to one module with the rounding mode declared once — and
  the module should own the Pydantic serializer and the SQLAlchemy
  `TypeDecorator`, which is what makes the boundary unavoidable rather than
  observed.
- AGREE: The lens should be an explicit dependency, not a comment — strengthened
  by having it return the scoping value the handler needs, so a forgotten lens
  cannot compile.
- AGREE: Deferring to Google samples for Android is right as a default, for the
  reviewability reason given.
- AGREE: ktlint/spotless decided before the first Android Bolt, not after — the
  first reformat is a whole-module diff.
- AGREE: Room as read-cache-only and no write queue in V1, consistent with
  [TC-8, D-9].
- OBJECT: "We add an import-boundary lint check for the money module if it is
  ever violated" — it should exist from the first commit; the conditional
  framing means the first violation is found by review, which is the mechanism
  the rule exists to replace.
- OBJECT: "Docstrings on every module, class and public function" — at "every
  public function" on an agent-written codebase this produces signature
  restatements that drift and mislead; mandate module docstrings everywhere plus
  docstrings on money, authorization, and anything whose correctness depends on
  something absent from the signature, enforced by path-scoped Ruff `D` rules.
- OBJECT: The detekt rule forbidding `Double`/`Float` "in money-carrying model
  classes" is the wrong mechanism — it requires knowing which classes carry
  money. A Kotlin `Money` value class with a string-only serializer makes it a
  compiler property; the detekt rule then degrades to a package-scoped backstop.
- OBJECT: "Where our preference and the Google sample disagree, the Google
  sample wins", stated without exception — it would import analytics SDKs
  [TC-3/TC-6], `Double` money [TC-7], and offline-first write-queue scaffolding
  [TC-8]. Project constraints must outrank the sample; the sample decides what
  the constraints do not.
- OBJECT: Copying the Google samples' Gradle multi-modularization — ~40 modules
  is build-config and build-time cost paid for nothing on a solo two-surface
  V1. One module with feature packages.
- OBJECT: "Error handling at every integration boundary, recoverable
  distinguished from fatal" is not actionable as written — replace it with a
  closed exception taxonomy where retryability is a property of the error class,
  a single error envelope that carries `retryable` from the server, and the four
  named per-boundary rules (SMS never auto-retries; a
  `(enrollment_id, period)` conflict is a success not an error; FCM failure
  never fails its triggering operation; backup failure alerts).
- OBJECT: "Silent failures are not acceptable", stated absolutely, is wrong at
  the FCM boundary, where a logged non-fatal failure is the correct behaviour.
  The rule needs that exception stated or it will be implemented wrongly.
- OBJECT: The draft mandates server-side error handling and full Bangla/English
  localization without noticing they conflict — a server-sent English `message`
  field cannot be localized by the client. The envelope must carry a
  `message_key`, and the client must own the string.
- OBJECT: The draft is silent on Python line length, which is the one style
  choice that changes how code is written and cannot be changed cheaply later;
  the user's stated global standard (79) differs from Ruff's default (88), so
  silence here is a decision made by accident.
- OBJECT: "Every rule server-side" has no checkable form in the draft. Add: the
  API returns decisions, not inputs to decisions — if the client is comparing a
  domain value, the server should have sent a status. This is the convention
  that prevents the five named erosion paths.
- OBJECT: The draft does not assign a home to UI-state mapping, which [TC-9]
  makes ambiguous; unassigned, it lands in composables where it is untestable.
  Declare the ViewModel's response-to-UiState mapping as its home and the target
  of the Turbine tests.
