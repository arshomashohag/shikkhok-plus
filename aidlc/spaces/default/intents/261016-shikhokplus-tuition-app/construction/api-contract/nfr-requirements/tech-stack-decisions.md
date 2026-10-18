# Tech Stack Decisions — `api-contract` (U2)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Depth**: Comprehensive

> **Almost everything here was decided at B1 and is inherited unchanged**:
> Python 3.12, FastAPI, Pydantic v2, pytest, Ruff with its named rule sets,
> mypy with its strict islands, `uv.lock`. Re-litigating them would be
> ceremony. **Three decisions are genuinely U2's**, and all three are narrow
> enough to state precisely — which is the point, because each one is a place
> where a plausible alternative quietly disables a gate.

## Sources

- [stage] `nfr-requirements-questions.md` — Q6 (what remains to decide)
- [upstream] `construction/api-contract/functional-design/rules.md` — BR2.1,
  BR2.2, BR4.2
- [upstream] `construction/money-core/nfr-requirements/tech-stack-decisions.md`
  — the inherited B1 stack
- [upstream] `inception/contract-design/contract-summary.md` — §B.1, §C9
- [team] `## Testing Posture`, `## Deployment` → scanning, `## Code Style`
- [project] `## Mandated`

---

## A. The decisions

| # | Decision | Alternative rejected |
|---|---|---|
| A.1 | The committed schema is **generated output only** — no hand-authored fragment is ever merged into it | Hand-maintaining or patching the document |
| A.2 | The diff is a **byte comparison** over deterministically serialized output | A semantic/structural differ |
| A.3 | **Schemathesis validates conformance only** and never counts as privacy coverage | Treating a green conformance run as privacy evidence |

---

### A.1 — The committed document is an output, never a source

FastAPI generates the OpenAPI document from the route and model definitions.
The committed file is that generation's output, and **nothing is ever merged
into it by hand** [BR2.1].

The rejected alternative is not "hand-writing the whole schema" — nobody would
propose that. It is the realistic one: **patching a fragment** to describe
something the generator renders imperfectly, or to add an example, or to
document a route that does not exist yet.

That is fatal here specifically, because of what the diff gate can and cannot
see. The gate compares committed against generated and fails on any
difference. It **cannot distinguish a deliberate hand-edit from drift** — both
are "the two files differ". So a project that hand-patches fragments must
either weaken the gate to tolerate known differences, or regenerate and lose
the patch on every run. Both outcomes end with the gate disabled.

If the generated document is wrong, the **model or route definition** is wrong,
and that is where the fix goes. This keeps a single source of truth and it is
what makes the gate's verdict meaningful rather than advisory.

> **The regeneration command is documented beside the committed file**
> (NFR16.4). This is the counterweight to the gate's one real misuse: an
> implementer seeing a red diff and hand-editing the committed file to make it
> green, which looks exactly like fixing the problem and inverts the control
> into a rubber stamp.

---

### A.2 — A byte comparison, which buys a determinism obligation

The diff is a **byte-for-byte** comparison, not a semantic one.

A semantic differ is the more sophisticated choice and it is wrong here for
two reasons. First, it needs its own correctness argument: a differ that
decides two documents are "equivalent" is now a piece of security-relevant
logic with no tests, inside the gate that is supposed to be the test. Second,
and more practically, **it would accept exactly the changes we want to see** —
a reordering, a reformatting, a rewritten description — and the entire value of
the committed schema is that a contract change shows up as a reviewable diff
in a pull request where the one reviewer sees it [D-26, OC-1].

The cost is a real obligation rather than a free win: **serialization must be
deterministic** (NFR16.3). Stable key ordering, stable formatting, stable
handling of anything set-like. Python dictionaries preserve insertion order and
FastAPI's generation is deterministic for a fixed app, but this must be
asserted rather than assumed — **generating twice in one test run and comparing
the two outputs** is the cheap check, and it catches the whole class before it
reaches CI.

Without that, the gate produces false failures. A gate that cries wolf is
disabled by whoever is holding the pager on a bad afternoon, and then nothing
is checking the contract at all. **The determinism check is therefore part of
the gate, not an optimization of it.**

---

### A.3 — Schemathesis's scope, fixed in writing

Schemathesis is wired here, driven from the committed document. **It validates
conformance and never counts as privacy coverage** [BR4.2].

This is a tooling decision rather than a testing note because the failure is a
*category error* that a green run actively encourages: a teacher-facing
response schema that wrongly declares an owner-private profile field is
**perfectly conformant**. It matches its own declaration. Schemathesis passes
it, and the pass is evidence of nothing about privacy.

What it is genuinely good at, and kept for:

- unexpected 500s, which are the `FatalError` path firing where it should not;
- type and required-field drift between declaration and response;
- authentication present on every route.

The privacy property is asserted instead by the schema-wide iteration of
NFR14.8, which reads the document and checks both forbidden field sets. Stating
the boundary in the artifact is what stops a future reader — or a future
reviewer under time pressure — from treating a green Schemathesis run as
discharge of a COPPA/GDPR-K obligation.

> `team.md` already draws this line and adds the complementary gate it
> motivates: *"we add the check it cannot provide: an OpenAPI schema-diff
> gate."* Both halves land in this Unit.

---

## B. What is inherited, and one thing that arrives here

**Inherited from B1 unchanged**: Python 3.12, FastAPI, Pydantic v2, pytest,
Ruff (with `E,F,W,I,UP,B,ASYNC,S,DTZ,BLE001,RUF` and the `D` docstring rules),
mypy with `disallow_untyped_defs` globally and strict islands on `app.money.*`,
`app.authz.*` and `app.schemas.*`, `uv.lock`, Gitleaks as pre-commit hook and
CI job.

**`app.schemas.*` is a strict mypy island and that matters here**, because U2
is the Unit that first populates it. Response-schema separation is a *typing*
control as well as a privacy one: a lens type parameterizes which response
models an endpoint may return, so a teacher-lens endpoint returning a
student-private response is a **mypy error** rather than a review finding. That
is the layer catching right-lens-wrong-data, which neither the route harness
nor the schema iteration can see.

**Arriving with this Bolt, by `team.md`'s explicit sequencing**: Schemathesis
and the OpenAPI schema-diff gate. Both were deliberately held back from the
skeleton-time toolchain so that B1 did not become a toolchain Bolt, and both
need a schema to exist before they mean anything.

**No new runtime dependency.** U2 adds a test-time dependency (Schemathesis)
and no production package. That is worth recording against NFR7: the hosting
budget is USD 50/month on a 2 GB instance, and a Unit that ships four CI gates
should not grow the deployed image at all.

---

## C. What this Unit establishes for later Bolts

- **The generated document is the contract**, and the only sanctioned way to
  change it is to change a model or a route. Every later Bolt inherits this.
- **Four gates exist before the first route does**, which is the whole reason
  U2 precedes U3. A gate written after the endpoints it guards is written
  around what those endpoints already do.
- **Two allowlists with stated lengths** (five and one), so every later Bolt
  adding a public or lens-exempt route edits a number as well as a list.
- **The error taxonomy as code** — five classes and one handler — so no later
  endpoint writes its own try/except for them, and `retryable` is derived once
  rather than decided per raise site.

---

## Assumptions & Open Questions

**None.** [assumption] The three decisions above are settled here rather than
deferred. A.2's determinism obligation is the only one carrying ongoing cost,
and it is discharged by a two-line test that generates the document twice and
compares — cheap enough that deferring it would cost more in discussion than in
implementation.
