# Code Summary — `api-contract` (U2)

**Stage**: code-generation (3.5)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`

> **What this Unit shipped.** Not a feature: the committed OpenAPI contract
> and four CI gates that every later Unit is checked against. The gates
> exist before the first route does, which is why U2 precedes U3.

## Result

| | |
|---|---|
| Tests | **303 passing** (`make check` green) |
| Money module coverage | **100% branch**, unchanged |
| Backend coverage (new packages) | **94% line**, against an 80% floor now enforced |
| Lint / format / types | Ruff and mypy clean |
| Plan steps | 26 of 26 |

---

## What was built

### The four gates

| Gate | Module | Proven to fire by |
|---|---|---|
| Schema diff + determinism | `app/contract/serialize.py`, `emit.py` | Hand-edited committed file; subprocess comparison |
| Money contract | `app/contract/money_schema.py` | Inline-money and orphan-display fixtures |
| Privacy boundary | `app/contract/privacy.py` | Leaky fixture, **two** violations asserted |
| Route lenses | `app/contract/routes.py` | Unlensed-app fixture, by path |

Each takes its subject — the app, or the generated document — **as an
argument**, so the committed fixture and the real gate call one function.
Without that factoring the fixture exercises a parallel implementation that
drifts silently, which was a review finding at NFR Design.

### The runtime code

`app/errors/` — five closed classes, one handler, one envelope.
`retryable` is derived from the class at the handler and nowhere else.
`app/schemas/` — the shared `Money` component and the error envelope.
`app/authz/` — the `Lens` type hierarchy and the shared annotation resolver.

---

## Six things the build and review found that the design had wrong

Each is recorded because the design read as correct until the code was
written against it.

**1. `assert_never` could not sit in the handler.** `TaxonomyError` is
itself instantiable, so mypy cannot narrow the default arm to `Never`. The
static proof moved to a closed union in `_exhaustive.py`. But that only
catches a class added to the *union* and not to a match — a sixth class
added to the taxonomy and to **neither** is invisible to it, which I
verified by adding one and watching mypy pass. A runtime test now asserts
the union equals the real subclass set. **Either mechanism alone leaves a
gap the design claimed was closed.**

**2. `disallow_any_explicit` had to come off `app.schemas`.** Pydantic's
`BaseModel` is generic over `Any`, so *every* `class X(BaseModel)` reports
explicit-any regardless of how it is written — verified against a bare
three-line subclass. The flag would mean one unavoidable `# type: ignore`
per schema, and a file dense with ignores silences real findings too.
`strict = true` still applies in full, which is the bulk of the value: no
*implicit* `Any` flows through. **An explicit `Any` on a response field is
a residual, accepted gap** — review found an earlier version of this note
claiming the privacy gate compensated generically, and it does not: that
gate matches forbidden field *names* on teacher-facing routes, so an
`Any` field with an innocuous name is reported by nothing. Recorded as an
accepted gap rather than a covered one.

**3. An `Annotated` alias does not emit a schema component.** Pydantic
inlines it into every property, so the document would carry a copy of the
pattern per field and **no component to reference** — making the `$ref`
predicate the money gate depends on unimplementable. `Money` is a
`RootModel`, verified by generating both forms.

**4. The owner-private field set was invented.** The draft assumed
`date_of_birth`; the domain catalogue says `Profile` is
`(account_id, self_name, photo_ref)`. Checking the catalogue rather than
trusting the draft is what turned a plausible-looking gate into a correct
one.

**5. The shared components were absent from the committed document.**
FastAPI emits a component only when a route references one, and this Unit
declares no routes — so `Money` and the envelope would have been missing
from the contract, and a regression in the one definition every money
property must reference would not have appeared in the diff. The gate
would have passed, over nothing.

**6. Lens resolution returned the first match, and review caught it.**
`resolve_lens_type_of` walked the dependency tree and returned whichever
lens an unordered stack-pop reached first. On a route depending on two
lenses — a teacher lens and a guardian lens as independent `Depends()`
parameters — a teacher-facing response could be classified
guardian-facing and **skip the privacy gate entirely**, while the route
gate correctly reported the route as lensed. The leak was invisible to
both gates at once.

The bug was **intermittent**: set iteration order varies between runs, so
reverting the fix made the regression test fail twice and pass once. An
intermittent authorization hole is worse than a consistent one, because
it passes CI often enough to look fine. Resolution now collects *every*
lens and asks whether **any** is a teacher lens, which is the question
this gate actually asks. The route gate was unaffected, since "is there
any lens" is answered correctly by the first match.

---

## Two gaps closed that the plan did not name

**The 80% backend coverage floor was enforced nowhere.** The existing run
measures `app/money` at 100% branch; the new packages were measured by
nothing, so a regression would have passed silently. A second run now
enforces it — two runs, because the floors genuinely differ and one cannot
enforce both. Verified it fails when breached.

**The published `Money` description carried an implementation note.**
Pydantic copies a class docstring into the schema, so a client author
reading the contract would have received an explanation of why this is a
`RootModel`. Set explicitly instead.

---

## What this Unit deliberately did not build

- **No routes.** The Units that own the features add the endpoints.
- **No lens *resolution*.** The types exist so the harness has something to
  match on; **U3** resolves them against owned batches and enrollments.
- **No `Money` type.** U1 owns it, at 100% branch coverage. U2 asserts its
  *schema* representation, which is the half an import rule cannot see.
- **NFR14.4** — both lookup branches performing the same queries. **U3's**
  per BR4.4: U2 owns no lookup code, and building a mechanism it cannot run
  would be the over-reach the fixture obligation exists to prevent.

---

## For the next Unit

U3 inherits: the five exception classes and the single handler, so no
endpoint writes its own try/except; the `Lens` types; the shared annotation
resolver (**one function, two callers** — a second implementation would be
the naive `issubclass` the requirement forbids); and the committed contract
with `make openapi` as the only way to change it.

The allowlists are fixed at **five** public routes and **one**
lens-exempt-authenticated route, with the counts asserted. Adding a route
to either means editing a stated number, which is a reviewable act.
