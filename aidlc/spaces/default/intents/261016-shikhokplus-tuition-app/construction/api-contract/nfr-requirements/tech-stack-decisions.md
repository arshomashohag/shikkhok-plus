# Tech Stack Decisions — `api-contract` (U2)

**Stage**: nfr-requirements (3.2)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Depth**: Comprehensive
**Summary confirmed**: 2026-10-18

> **Almost everything here was decided at B1 and is inherited unchanged**:
> Python 3.12, FastAPI, Pydantic v2, pytest, Ruff with its named rule sets,
> mypy with its strict islands, `uv.lock`. Re-litigating them would be
> ceremony. **Four decisions are genuinely U2's**, and all four are narrow
> enough to state precisely — which is the point, because each one is a place
> where a plausible alternative quietly disables a gate.
>
> A.4 was found while writing this artifact rather than inherited from the
> questions: `team.md` names three strict mypy islands, B1 could only
> configure one, and nothing owned the second. Checking the committed
> `pyproject.toml` rather than restating the practice is what surfaced it.

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
| A.4 | **`app.schemas.*` becomes a strict mypy island in this Bolt**, since U2 first populates it | Leaving it to whichever Bolt notices, i.e. none |

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
handling of anything set-like.

**The determinism this needs is CROSS-PROCESS, and that distinction is the
whole requirement.** An earlier draft of this section proposed generating the
document twice in one test run and comparing — which is worse than no check,
because it passes while the gate fails. Python seeds its hash randomization
**once per process**, so two generations inside one run share an ordering by
construction and agree no matter how unstable the serialization is. Measured:
six separate interpreter processes printing one seven-element set produced
**six different orderings**; the same set printed twice inside one process
produces one.

That matters because an OpenAPI document contains set-derived collections —
`required` field lists most obviously. Any one of them built from a `set`
reorders between the author's machine and CI, and the gate then fails on a
commit that changed nothing.

So NFR16.3 is discharged by two things, neither of them a same-run comparison:

- **Canonical serialization**, not merely observed-stable serialization —
  `sort_keys` and an explicit ordering for every collection, so determinism is
  a property of how the document is written rather than a hope about dict
  insertion order surviving a dependency upgrade.
- **A cross-process check**: generate in two separate interpreter invocations
  and compare, which is the only arrangement that can observe the failure.
  Pinning `PYTHONHASHSEED` would hide it instead — the gate must survive the
  randomization CI actually runs with, not be insulated from it.

Without this, the gate produces false failures. A gate that cries wolf is
disabled by whoever is holding the pager on a bad afternoon, and then nothing
is checking the contract at all. **The determinism check is therefore part of
the gate, not an optimization of it** — which is also why getting its scope
wrong mattered enough to correct.

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
mypy with `disallow_untyped_defs` globally, `uv.lock`, Gitleaks as pre-commit
hook and CI job.

**One configuration change lands in this Bolt, and it is not optional.**
`team.md` names three strict mypy islands — `app.money.*`, `app.authz.*` and
`app.schemas.*` — but B1 configured only `app.money.*`, correctly, because the
other two packages did not exist and an override naming a missing module is
dead configuration. **U2 is the Unit that first populates `app.schemas`**, so
its override is added here:

```toml
[[tool.mypy.overrides]]
module = "app.schemas.*"
strict = true
disallow_any_explicit = true
```

This matters beyond tidiness. Response-schema separation is a *typing* control
as well as a privacy one: a lens type parameterizes which response models an
endpoint may return, so a teacher-lens endpoint returning a student-private
response is a **mypy error** rather than a review finding. That is the layer
catching right-lens-wrong-data, which neither the route harness (which checks a
lens is present, not which data it guards) nor the schema iteration (which
checks fields, not which endpoint returns them) can see.

`disallow_any_explicit` carries real weight on this package specifically: an
`Any` in a response model is a hole straight through the privacy assertion,
because a field typed `Any` can carry a profile field at runtime while
declaring nothing in the schema. **`app.authz.*` stays unconfigured until U3
creates it**, on the same reasoning that left it out of B1.

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
