# NFR Design Questions — api-contract (U2)

**Stage**: nfr-design (3.3)
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Phase**: Construction
**Depth**: Comprehensive

> NFR Requirements stated **what** must hold — 23 requirements across nine
> threats. This stage designs **how**: the concrete mechanism per requirement,
> where it physically lives, and what fails when it is violated.
>
> Most of the design vocabulary this stage reaches for — circuit breakers,
> cache tiers, shard keys, SLO windows, auto-scaling rules — describes a
> running service. **U2 has no process.** Four of its five deliverables do not
> apply to a `spec` Unit by the stage's own kind-gating, and the honest design
> is build-time and test-time machinery, exactly as B1's was.
>
> One thing has changed since NFR Requirements and shapes several answers
> below: the four gates are no longer the only mechanism. **The error handler
> is runtime code on every error path in the system**, and `app.schemas`
> becomes a strict typing island here. The design has to place all three.

---

## Q1 — Where does each of the four gates physically run, and what is the single entry point?

`team.md` is explicit: *"one command, local and in CI, the same entrypoint in
both places"*, because *"a gate reproducible only by pushing is a gate that
gets bypassed."*

[Answer]: **All four run as pytest tests under `tests/contract/`, reached by
the same `make check` as everything else.** None is a bespoke script, a
pre-commit-only hook, or a CI-only job. Three consequences, each deliberate:

- **One runner, one failure format.** A contract violation reads like any
  other test failure, so there is nothing new to learn when it fires — which
  matters when the one reviewer is the person who has to act on it.
- **No secret is needed to run them.** The gates read a generated document and
  a Python app object; nothing touches the SMS gateway, the database or the
  network. The blocking suite therefore stays runnable locally, which is the
  property `team.md` says is most important for a solo build.
- **Collection-time, not runtime.** The route harness imports the real
  application object at test collection, so an unlensed endpoint reddens CI on
  the commit that adds it rather than when someone remembers to run a scan.

Physical layout:

```
tests/contract/
  test_schema_diff.py        # NFR16.1-16.3
  test_money_schema.py       # NFR9.1, NFR9.2
  test_privacy_schema.py     # NFR14.8  (both forbidden field sets)
  test_route_lenses.py       # NFR14.5-14.7
  fixtures/                  # the four violation fixtures  [NFR14.1]
```

---

## Q2 — The determinism obligation: what is the actual mechanism, given a same-run check cannot see the failure?

NFR16.3 requires cross-process determinism, and NFR Requirements recorded the
measurement: six interpreter processes printing one seven-element set gave six
different orderings.

[Answer]: **Two mechanisms, and the first is what actually fixes it; the
second only proves the first is still true.**

1. **Canonical serialization at the point of writing.** The committed document
   is written through one function that serializes with sorted keys and a fixed
   separator and indent. Determinism becomes a property of how the file is
   produced rather than an observed accident of dict ordering that a FastAPI or
   Pydantic upgrade could quietly change.

   **`sort_keys` alone is NOT sufficient, and assuming it is would leave the
   hole open.** It orders object *keys*; it does not order a list *value*. An
   OpenAPI `required` list built from a `set` stays in hash order through a
   fully canonical dump. Verified while designing this: a document whose
   `required` came from a set, dumped with `sort_keys=True` and fixed
   separators, still differed between an in-process and a subprocess
   generation. So canonical serialization must also **sort every
   order-insensitive list** — `required`, enum members, tag lists — and that
   is the half that actually fixes the defect.
2. **A cross-process assertion.** One test spawns a **subprocess** that
   regenerates the document and compares its bytes against an in-process
   generation. A subprocess gets a fresh hash seed, which is exactly the
   condition that reveals a set-derived ordering.

   Verified rather than assumed: against a document with a set-derived
   `required` list, the subprocess comparison **failed** while generating twice
   in one process **passed**. That is the whole argument for this shape,
   demonstrated rather than reasoned.

The second is the one that would have been wrong as a same-run check, and it
is cheap: a `subprocess.run` of one module entry point, about ten lines.

**`PYTHONHASHSEED` is deliberately not pinned.** Pinning it would make the
test pass while CI — which does not pin it — still fails. The gate must run
under the same randomization the real environment has.

---

## Q3 — How does the privacy assertion identify a "teacher-lens response schema" from a generated document?

NFR14.8 asserts that no teacher-lens response schema declares a field from
either forbidden set. The gate iterates the document — but the document does
not label schemas by lens.

[Answer]: **The lens is read from the route, not guessed from the schema
name**, and this is the design decision that makes the gate real rather than
heuristic.

The iteration walks `app.routes`, and for each route resolves the lens type
from its dependency return annotations — the same resolution NFR14.7 already
requires for the route harness, reused rather than reimplemented. A route
whose lens resolves to `TeacherLens` has its `response_model` inspected, and
every field in that model's schema — recursively through `$ref`, `items`,
`allOf`, `anyOf` — is checked against both forbidden sets.

**Three rejected alternatives, each of which fails quietly:**

- *Matching schema names containing "Teacher"* — defeated by a rename, and
  blind to a shared model returned under two lenses.
- *Checking only top-level properties* — a profile field nested inside an
  embedded student object is the likely shape of the defect, not a top-level
  one.
- *Checking the schema in isolation* — a model is only teacher-facing by
  virtue of some route returning it under a teacher lens. That fact lives on
  the route.

**The recursion needs a cycle guard.** `$ref` graphs can be self-referential,
and an unguarded walk hangs CI rather than failing it — a hang is worse than a
failure because nobody reads it as a result.

---

## Q4 — Where does the error handler live, and how is "no I/O" enforced rather than intended?

NFR17.2 requires the handler to perform no I/O, because it sits on every error
path and a handler that can fail turns a handled 403 into an unhandled 500.

[Answer]: **`app/errors/` — a package importing only the standard library,
FastAPI's response types, and the five exception classes.** The prohibition is
enforced the same way B1 enforces the money boundary, because that mechanism
is already proven here and the reviewer already knows how to read it:

**A layered-import test** asserts `app.errors` imports nothing from `app.db`,
`app.repositories`, `app.api` or any HTTP client. This is the same shape as
B1's `test_import_gates.py`, which currently passes 81 tests, so it is a
pattern with a working precedent in this repository rather than a new idea.

The realistic violation it catches is not an obvious one: it is someone adding
*structured error logging that writes to the database*, or a lookup to enrich
`details` with a human-readable name. Both look like improvements and both put
a query on every error path.

**Totality (NFR17.3) is a typing property, not a test.** The class-to-response
mapping is a dictionary keyed by the five classes, and the handler ends with
`assert_never` on the unmatched case — the same construct B1 uses for its
ledger kinds, which mypy proves exhaustive statically. Adding a sixth class
without a mapping is then a type error at build time rather than a 500 in
production.

---

## Q5 — What does the four-fixture obligation look like concretely, and how does a fixture avoid passing for the wrong reason?

NFR14.1 requires a committed violation fixture per gate; NFR14.2 requires each
to assert *which* violation was reported.

[Answer]: **Each fixture is a minimal artifact that violates exactly one rule
and is otherwise valid**, paired with a test asserting the specific error.

The "otherwise valid" half is what makes NFR14.2 achievable. A fixture that is
merely malformed fails every gate for the wrong reason:

| Gate | Fixture | Asserted |
|---|---|---|
| Money schema | Valid OpenAPI document, one property an inline `{"type": "string"}` where a `$ref` belongs | Error names **that property path** |
| Display pairing | Valid document with `amount_display` and no `amount` | Error names **the orphan field** |
| Privacy | Valid document, one teacher-lens response declaring `date_of_birth`, a second declaring `student_account_id` | **Two** errors, one per field set |
| Route lenses | A throwaway `FastAPI()` app with one unlensed route, not the real app | Error names **that route's path** |

Two design points:

- **The route fixture builds its own app object** rather than mutating the
  real one. A fixture that registers a bad route on the production app and
  removes it afterwards leaks into any test that runs between, and the failure
  mode is an unrelated test failing mysteriously.
- **The privacy fixture asserts two distinct errors**, because NFR14.8 carries
  two field sets through one iteration. A fixture tripping only the profile set
  would leave ADR-001's account-id set unexercised while the gate still
  reported green.

---

## Q6 — Does a `spec` Unit have any reliability, scalability or observability design at all?

The stage's own kind-gating excludes those three deliverables for a `spec`
Unit, but the reasoning deserves recording rather than an empty file.

[Answer]: **No, and the reason is structural rather than a scoping
convenience.**

Reliability patterns — circuit breakers, retries with backoff, health checks,
failover — all presuppose a process that can be unavailable. U2 ships no
process. The one piece of U2 that runs in production, the error handler, has
its reliability requirement expressed as the *absence* of a failure mode
(no I/O, total over the taxonomy) rather than as a recovery pattern. A circuit
breaker around an error handler would be incoherent: there is nothing
downstream to break.

Scalability is the same. No process, no load, no shard key, no capacity
threshold.

Observability has one genuine edge worth naming rather than dismissing:
**NFR3.2 constrains what an error log may contain** — correlation id yes;
phone number, OTP or token never. That is a log *content* rule and it belongs
to the error envelope design, which is in `security-design.md`. There is no
metric, no SLI and no dashboard here, because there is nothing running to
measure.

**Performance**: no latency target, deliberately. U2 has no endpoint to
measure one on, and the handler's cost is bounded structurally by the no-I/O
rule — a number would be unmeasurable here and undefendable.

---

## Q7 — What does this Unit hand forward, and what must not be re-derived later?

[Answer]: **Four things, and the fourth is the one most likely to be
accidentally re-implemented.**

1. **The five exception classes and the single handler** — so no later
   endpoint writes its own try/except for them.
2. **The `Lens` type hierarchy** — U3 resolves them; the types exist here so
   the route harness has something to match on.
3. **The committed schema and its regeneration command** — the contract, plus
   the only sanctioned way to change it.
4. **The annotation-resolution helper** (NFR14.7) — `typing.get_type_hints`
   against the function's own module, unions counted only when every member
   qualifies, `Annotated` unwrapped, resolution failure raising rather than
   returning a default. **Both the route harness and the privacy iteration use
   it**, so it is one function with two callers, not two near-copies that
   drift. A second implementation would almost certainly be the naive
   `issubclass` the requirement exists to forbid.

---

## Assumptions & Open Questions

**None.** [assumption] OQ-B1-1 closed on 2026-10-18, so the `*_display`
pairing gate's structural check has settled content behind it. The pairing
rule was always structural and independent of that content, so no design here
changes as a result.

---

## Consolidated Summary Confirmation

U2's NFR design is build-time and test-time machinery, not runtime
infrastructure — the same shape as B1's, and for the same reason: no process.
Reliability, scalability, performance and observability design are **absent by
structure rather than by scoping convenience**, and the reasoning is recorded
rather than left as an empty file. Circuit breakers presuppose a process that
can be unavailable; the one piece of U2 that runs in production expresses its
reliability requirement as the *absence* of a failure mode.

**All four gates are pytest tests under `tests/contract/`, reached by the same
`make check` local and in CI**, needing no secret to run — the property
`team.md` calls most important for a solo build. The route harness imports the
real app object at collection time, so an unlensed endpoint reddens CI on its
own commit.

**Determinism gets two mechanisms**: canonical serialization at the point of
writing, which is what actually fixes it, and a **subprocess** regeneration
comparison, which is the only arrangement that gets a fresh hash seed and can
therefore observe a set-derived ordering. Both were verified rather than
reasoned about, and the check corrected a detail: **`sort_keys` is not
sufficient on its own** — it orders object keys but not list values, so a
`required` list built from a set survives a fully canonical dump unchanged.
Canonical serialization must sort order-insensitive lists too.
`PYTHONHASHSEED` stays unpinned deliberately — pinning it would make the test
pass while CI still failed.

**The privacy gate reads the lens from the route, not from the schema name**,
reusing the same annotation resolution the route harness needs, and recurses
through `$ref`/`items`/`allOf`/`anyOf` with a cycle guard, because a hang is
worse than a failure. Matching on names would be defeated by a rename;
checking only top-level properties would miss the likely shape of the defect.

**The error handler lives in `app/errors/`**, with no-I/O enforced by a
layered-import test of the same shape as B1's working import gates, and
totality enforced by `assert_never` over a five-key mapping — a build-time type
error rather than a production 500. The realistic violation is not obvious:
structured error logging that writes to a database, or a lookup enriching
`details`, both of which look like improvements.

**Each of the four fixtures is otherwise-valid and violates exactly one rule**,
which is what makes "assert which violation" achievable — a merely malformed
fixture fails every gate for the wrong reason. The route fixture builds its own
app object rather than mutating the real one, and the privacy fixture asserts
two distinct errors so ADR-001's account-id set is actually exercised.

One helper is shared rather than duplicated: the annotation resolver, used by
both the route harness and the privacy iteration, because a second
implementation would almost certainly be the naive `issubclass` the
requirement exists to forbid.

Does this all look correct before I generate the artifact?

[Answer]: Looks correct

---

## Assumption Confirmation

A. Accept assumptions
B. Convert to follow-up questions

[Answer]: A. Accept assumptions
