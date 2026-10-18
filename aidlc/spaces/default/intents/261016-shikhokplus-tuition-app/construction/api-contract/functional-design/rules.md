# Business Rules — `api-contract` (U2)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`

## Sources

- [stage] `functional-design-questions.md` — Q1 (403 vs 404, resolved),
  Q3/Q4 (fixtures for checks that would otherwise pass trivially),
  Q6 (`retryable` derived), Q7 (what Schemathesis may count as)
- [upstream] `inception/contract-design/contract-summary.md` — §error
  taxonomy, §schema, §implementer notes
- [upstream] `inception/domain-design/decisions.md` — ADR-001 (the owner
  boundary as a keying rule)
- [upstream] `inception/requirements-analysis/requirements.md` — NFR14,
  NFR16
- [team] `## Code Style` → error handling, authorization
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
rules:

  # ---- BR1.x - The error taxonomy ----

  - id: BR1.1
    statement: >
      The exception hierarchy is closed at five classes, and every raise site
      in the system chooses one of them.
    category: constraint
    applies_to: Every raise site in the backend
    trigger: Any error condition
    logic: >
      IF an error condition occurs
      THEN it raises one of validation, authorization, conflict, transient or
      fatal
      ELSE the error is untyped and the envelope has nothing to carry.
    violation_behaviour: >
      A bare `except Exception` is caught by lint, with exactly two permitted
      sites: the response handler itself, and the scheduled job's top level
      where a crash must not kill the daily run.
    rationale: >
      Five classes because they map to five distinct caller behaviours. A
      sixth would mean a behaviour nobody has named; a looser hierarchy means
      every layer re-derives what to do.
    source: [team.md Error handling, contract-summary error taxonomy]

  - id: BR1.2
    statement: >
      Retryability is derived from the class at the single handler, never set
      at a raise site.
    category: calculation
    applies_to: The error handler
    trigger: Converting any taxonomy exception to a response
    logic: >
      IF an exception of class C reaches the handler
      THEN retryable is read from a single class-to-behaviour table, and the
      raise site has no say.
    violation_behaviour: >
      A raise site that sets retryable itself is a defect: two sites of the
      same class could then disagree, which is the condition the closed
      hierarchy exists to prevent.
    rationale: >
      The client holds no business logic, so it does not infer retryability
      from an HTTP status - it is told. That is only trustworthy if one place
      decides it.
    source: [team.md Error handling, TC-9, D-31]

  - id: BR1.3
    statement: >
      No English message is ever emitted in an error response. The envelope
      names a client string resource instead.
    category: constraint
    applies_to: Every error response
    trigger: Any error response
    logic: >
      IF an error response is built
      THEN it carries message_key naming a client string resource
      AND it carries no `message` field at any level.
    violation_behaviour: >
      Structural: the envelope declares additionalProperties false, so a
      `message` field fails schema validation and the diff gate.
    rationale: >
      A server-authored English string cannot be localized by the client, and
      in a Bangla-first UI that guarantees untranslated English error text in
      front of a teacher.
    source: [contract-summary, TC-15, D-43]

  - id: BR1.4
    statement: >
      A resource the lens does not reach, and a resource that does not exist
      under a lens that would reach it, return the SAME status. Neither case
      is distinguishable from the other.
    category: authorization
    applies_to: Every lens-scoped resource lookup
    trigger: A request naming a resource id
    logic: >
      IF the resolved lens does not reach the named resource
      OR the named resource does not exist
      THEN return authorization (403) in both cases, identically.
    violation_behaviour: >
      Splitting the two - 403 for unreachable, 404 for absent - is an
      enumeration oracle. Teacher A probes ids and reads 403 as a hit,
      enumerating teacher B's batches across the owner boundary ADR-001 draws.
    rationale: >
      **The upstream contract contradicts itself here, and the contradiction
      is recorded rather than silently resolved.** contract-summary's schema
      section specifies 403 for both cases; its implementer notes call it
      "the 404-instead-of-403 rule" and argue the opposite. B2's Definition
      of Done repeats the second wording.

      Worked through: the leak comes from SPLITTING, not from either status.
      A uniform 403 and a uniform 404 both close the oracle. So this is a
      wording conflict, not a vulnerability.

      403 is chosen for three reasons. The schema section is the normative
      artifact - it generates the OpenAPI document the diff gate compares
      against. 404 is not in the taxonomy at all, so the envelope's code and
      retryable would have nothing to carry. And 403 is honest to an
      authenticated caller: a teacher who mistypes their OWN batch id is told
      "not yours" rather than "does not exist", which would be actively
      misleading about data they do own.

      An implementer who reads only the implementer note will try to "fix"
      this back, which is precisely why the conflict is written down here.
    source: [contract-summary schema + implementer notes, ADR-001, TC-13]

  # ---- BR2.x - The committed schema ----

  - id: BR2.1
    statement: >
      The generated OpenAPI document and the committed one must be identical,
      or CI fails.
    category: constraint
    applies_to: Every change touching a route or a response model
    trigger: Every push
    logic: >
      IF the generated schema differs from the committed schema
      THEN the build fails and the diff is the review surface.
    violation_behaviour: Build failure, with the drift shown as a diff.
    rationale: >
      A stale committed schema is worse than none: the contract tests then
      pass against fiction, and a client is generated from a document that
      describes a server that no longer exists.
    source: [team.md Both surfaces, D-26, NFR16]

  - id: BR2.2
    statement: >
      Every money property in the schema is a string matching the canonical
      pattern, never a number.
    category: validation
    applies_to: Every response and request schema carrying money
    trigger: Schema generation
    logic: >
      IF a schema property carries a money value
      THEN its type is string and its pattern is the canonical money form
      ELSE the schema assertion fails the build.
    violation_behaviour: >
      Build failure. This is the half of the money boundary an import rule
      cannot see: a money value typed as a free-form string imports nothing
      and violates nothing lexically.
    rationale: >
      A JSON number is an IEEE 754 double in most parsers, so emitting one
      converts the value to a float on the client - reintroducing the exact
      representation error the money module exists to prevent, on the far
      side of the wire where none of its controls reach.
    source: [contract-summary B.5, NFR9, U1 NFR9.30]

  - id: BR2.3
    statement: >
      A `*_display` field never appears without its canonical money sibling.
    category: constraint
    applies_to: Every response schema
    trigger: Schema generation
    logic: >
      IF a schema declares `<x>_display`
      THEN it also declares `<x>` matching the money pattern.
    violation_behaviour: Build failure at the schema assertion.
    rationale: >
      A rendering string without the value it renders leaves the client
      nothing to compare or re-render and leaves the server's rendering
      decision unverifiable. Recorded in the schema rather than in prose so
      the diff gate catches a field gaining or losing its sibling.
    source: [contract-summary *_display rule, OQ-6 resolution]

  - id: BR2.4
    statement: >
      No teacher-lens response schema contains any owner-private profile
      field, asserted by iterating the generated schema.
    category: authorization
    applies_to: Every teacher-lens response schema, including ones added later
    trigger: Schema generation
    logic: >
      IF a teacher-lens response schema declares a field in the owner-private
      set
      THEN the build fails.
    violation_behaviour: Build failure.
    rationale: >
      Iteration rather than per-endpoint tests is the whole point: a
      per-endpoint test covers the endpoints someone remembered, and misses
      the one added in a later Bolt after everyone stopped thinking about it.
      This is also the assertion a conformance tool cannot make - a response
      wrongly including profile fields is perfectly conformant.
    source: [TC-13, D-7, NFR14, contract-summary]

  # ---- BR3.x - The route harness ----

  - id: BR3.1
    statement: >
      Every route resolves a lens, except those on an explicit public
      allowlist.
    category: authorization
    applies_to: Every route in the application
    trigger: Test collection, against the real application object
    logic: >
      IF a route resolves no dependency whose return annotation is a Lens
      subtype
      AND the route is not in PUBLIC_ROUTES
      THEN the build fails.
    violation_behaviour: >
      Build failure on the commit that adds the unlensed endpoint, not on a
      later review.
    rationale: >
      The failure mode is not a wrong lens, it is a FORGOTTEN one - and a
      dependency somebody forgot produces an endpoint that works perfectly
      and authorizes nothing. The allowlist is the load-bearing half:
      adding a public endpoint means editing a list in a test, which is a
      deliberate, reviewable act.
    source: [team.md Authorization, TC-11, D-2, US10.1]

  - id: BR3.2
    statement: >
      The harness matches on the dependency's RETURN ANNOTATION being a Lens
      subtype, never on the function's name, and walks nested dependencies
      recursively.
    category: constraint
    applies_to: The route harness
    trigger: Every run
    logic: >
      IF a dependency is examined
      THEN its return annotation decides whether it is a lens
      ELSE a rename would silently defeat the check.
    violation_behaviour: >
      A name-matching implementation is a defect even while it passes, since
      it certifies nothing after the first rename.
    rationale: >
      Recursion matters because a lens may be nested inside a composed
      dependency; annotation-matching matters because names are the one thing
      a refactor changes freely.
    source: [team.md Authorization]

  # ---- BR4.x - Gates that would otherwise pass trivially ----

  - id: BR4.1
    statement: >
      Every schema-wide assertion and the route harness ship with a committed
      fixture that violates them, asserted to fail.
    category: policy
    applies_to: BR2.2, BR2.3, BR2.4, BR3.1
    trigger: The first commit of this Unit
    logic: >
      IF an assertion in this Unit is delivered
      THEN a fixture violating it is delivered alongside, and a test asserts
      the assertion refuses that fixture.
    violation_behaviour: >
      Delivering an assertion without its fixture does not satisfy this
      Unit's definition of done.
    rationale: >
      **B2 has no routes and no money endpoint.** Every one of these
      assertions therefore iterates an empty set and passes trivially,
      recording a green check that has never once looked at a real field.
      A gate nobody has watched fail is a gate nobody knows works - the same
      reasoning that put violation fixtures in B1's import gates, and the
      reason those gates were later found to have a real bypass.
    source: [questions Q3, Q4, B1 NFR9.6]

  - id: BR4.2
    statement: >
      A conformance tool validates conformance and never counts as privacy
      coverage, stated in writing in the artifact.
    category: policy
    applies_to: The conformance suite
    trigger: Interpreting its results
    logic: >
      IF a conformance run passes
      THEN it is evidence about unexpected failures, type drift and auth
      presence
      AND it is NOT evidence about the privacy boundary.
    violation_behaviour: >
      Treating a green conformance run as privacy coverage is a reasoning
      defect, which is why the limitation is written into the artifact rather
      than left for a reader to infer.
    rationale: >
      A teacher-facing response schema that wrongly includes profile fields
      matches its own declaration perfectly. BR2.4 is what catches that.
    source: [team.md Testing Posture, contract-summary]
```

---

## Part B — Rules summary

| Rule | Category | What it holds |
|---|---|---|
| **BR1.1** | constraint | Five classes, closed; every raise site picks one |
| **BR1.2** | calculation | `retryable` derived at the handler, never per raise site |
| **BR1.3** | constraint | No English message, ever; a string key instead |
| **BR1.4** | authorization | **403 for both unreachable and absent** — the upstream contradiction, resolved and recorded |
| **BR2.1** | constraint | Committed schema equals generated, or CI fails |
| **BR2.2** | validation | Money is a patterned string, never a number |
| **BR2.3** | constraint | `*_display` never appears without its sibling |
| **BR2.4** | authorization | No profile field in a teacher-lens response, by iteration |
| **BR3.1** | authorization | Every route resolves a lens, bar an explicit allowlist |
| **BR3.2** | constraint | Match on return annotation, never on name |
| **BR4.1** | policy | Every assertion ships a failing fixture |
| **BR4.2** | policy | Conformance is never privacy coverage, in writing |

**The three worth a second look:**

- **BR1.4** is the one an implementer will try to undo, because the upstream
  contract argues both sides. The rule records that the leak comes from
  *splitting*, not from either status.
- **BR4.1** exists because this Unit's gates have nothing to check yet. Four
  green checks over empty sets is the most plausible way B2 ships a false
  sense of safety.
- **BR2.4** is the privacy boundary's API half, and the reason it iterates
  rather than enumerating endpoints is that the endpoint it must catch has
  not been written yet.

---

## Assumptions & Open Questions

**Carried from B1**: OQ-B1-1, the Bangla money rendering. BR2.3's pairing is
structural and holds regardless of what the display string contains.
