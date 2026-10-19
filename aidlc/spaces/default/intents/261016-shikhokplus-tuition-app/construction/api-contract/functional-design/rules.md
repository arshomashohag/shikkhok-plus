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
      under a lens that would reach it, return a BYTE-IDENTICAL response.
      Status, code, message_key, details and every header are the same in
      both cases.
    category: authorization
    applies_to: Every lens-scoped resource lookup
    trigger: A request naming a resource id
    logic: >
      IF the resolved lens does not reach the named resource
      OR the named resource does not exist
      THEN return authorization (403) with an identical body in both cases,
      carrying a single code that distinguishes neither,
      AND reach that response having performed the SAME LOOKUP WORK in
      both branches - neither branch returns before the other's query has
      run.
    violation_behaviour: >
      Any observable difference between the two cases is an enumeration
      oracle, whether it is the status, the code, the message_key, the
      details object or a header.

      A branch that SHORT-CIRCUITS is the same defect arriving by a
      different route. An implementer who checks existence first and
      returns immediately on a miss, skipping the ownership query, makes
      the absent case measurably cheaper than the unreachable one - and
      the oracle is restored in the timing, with every byte identical.
      This mirrors the OTP issue path, which asserts the STRUCTURAL
      property that the unknown-number branch performs the same hash
      computation rather than returning early.

      Like the OTP control, this is asserted structurally and NOT as a
      wall-clock bound: a millisecond assertion is flaky and gets deleted
      the third time CI fails on it. What is asserted is that both
      branches execute the same queries, which is inspectable and stable.
    rationale: >
      **The upstream contract contradicts itself on the STATUS, and an
      earlier draft of this rule resolved only that half - which left the
      oracle wide open through the response body.**

      On the status: contract-summary line 133 states normatively that "404
      is deliberately not in the taxonomy… a resource a lens does not reach
      is AuthorizationError/403, not 404", and the schema's Forbidden
      response says the same. One prose note at line 873 calls it "the
      404-instead-of-403 rule", mis-titling the very rule it points at. 403
      wins: two normative statements against one mis-titled cross-reference.

      **But uniformity of status is not uniformity.** Two 403s emitting
      BATCH_NOT_FOUND and BATCH_NOT_YOURS restore the oracle completely
      through a field no rule constrained. So do distinct message_keys, a
      populated details object, or a header present in one case only. The
      earlier draft said the two cases were "identical" in prose while
      requiring sameness of nothing but the status.

      Byte-identity is the property that actually closes it, and it is the
      same bar the OTP issue path already carries for the same reason: a
      response that differs in any observable way answers the question the
      attacker asked.
    source: [contract-summary line 133 + schema Forbidden + line 873, ADR-001, AC10.1.4, TC-13]

  - id: BR1.5
    statement: >
      A single error code covers both the unreachable and the absent case,
      and no code in the registry distinguishes them.
    category: authorization
    applies_to: The error code registry
    trigger: Adding or reviewing any authorization code
    logic: >
      IF a code would be emitted only when a resource exists
      OR only when it does not
      THEN it is an oracle and must not be added.
    violation_behaviour: >
      A code pair like RESOURCE_NOT_FOUND / RESOURCE_FORBIDDEN is the
      defect, even though each code is individually reasonable.
    rationale: >
      BR1.4 states the property; this states the thing most likely to break
      it. An implementer writing helpful, specific error codes produces
      exactly this pair without ever intending an oracle, because each code
      reads as good practice on its own.
    source: [BR1.4, ADR-001]

  - id: BR1.6
    statement: >
      `retryable: false` on a 401 is correct, and refresh-then-replay is the
      one documented exception. `retryable` answers "may the client repeat
      THIS REQUEST UNCHANGED?", which for an expired token is genuinely no.
    category: policy
    applies_to: The 401 path and every client built against it
    trigger: An access token expires mid-session
    logic: >
      IF a request fails with 401 and code ACCESS_TOKEN_EXPIRED
      THEN the client may issue a DIFFERENT request first - the refresh -
      and then replay EXACTLY ONCE with a new access token
      ELSE any second 401 logs the user out.
    violation_behaviour: >
      A client that treats 401 as retryable builds a refresh loop; a client
      that reads `retryable: false` literally cannot refresh at all. Both
      are produced by reading one half of the contract.
    rationale: >
      This reconciliation is a whole paragraph in the upstream contract
      written for exactly this hazard, and an earlier draft of these rules
      omitted it - stopping at BR1.2's "retryable is derived" without
      recording what the derived value MEANS on the one status where it
      reads as a contradiction.

      The two are not in conflict once the question is stated precisely.
      Repeating the same request with the same expired token fails
      identically, so `false` is right. What the refresh rule permits is not
      a retry but a different request followed by one replay - bounded at
      one, only on that code, with any second failure ending the session.
    source: [contract-summary B.2 and B.3, team.md Error handling]

  - id: BR1.7
    statement: >
      A lens hint claiming a lens the account's data does not support is
      REFUSED with 403 `LENS_NOT_AVAILABLE`, never silently ignored and
      never resolved to a different lens. A missing hint on a
      lens-ambiguous route is refused with 400 `LENS_HINT_REQUIRED`.
    category: policy
    applies_to: Every route whose response carries lens-scoped data
    trigger: A request arrives carrying X-Lens-Hint
    logic: >
      IF the hinted lens has data behind it for this account
      THEN resolve that lens and name it in the response's `lens` field
      ELSE IF a hint was sent and the hinted lens has no data behind it
      THEN refuse with 403 `LENS_NOT_AVAILABLE`
      ELSE IF no hint was sent and exactly one lens is available
      THEN resolve that lens
      ELSE refuse with 400 `LENS_HINT_REQUIRED`.
    violation_behaviour: >
      An implementer who reads AC10.1.6 alone builds the silent fallback:
      an unsupported hint quietly resolves to whatever lens the account
      does have, and the caller is served data under a lens they did not
      ask for. That is indistinguishable from the AC10.1.8 failure the
      story set exists to prevent, and it converts a crafted probe into a
      successful request.
    rationale: >
      TWO UPSTREAM SOURCES CONTRADICT EACH OTHER HERE, and this rule
      records the reconciliation rather than picking one quietly.

      `stories.md` AC10.1.6 says the server "ignores it and resolves the
      lens from owned batches and enrollments". `contract-summary.md` B.4
      says the server "refuses with 403 `LENS_NOT_AVAILABLE` if the hinted
      lens has no data behind it [FR1.4]". Both cite the lens-is-computed
      requirement; they differ on what happens to the hint.

      FR1.4 settles it: "At login, only the lenses that have data are
      offered." A hint for an unsupported lens therefore cannot arise from
      a client that followed the contract - it is a stale client, a bug, or
      a crafted request. Silent fallback serves all three the data of a
      lens they did not name, which is the exact shape of AC10.1.8's
      failure. Refusal makes the condition visible.

      The two readings AGREE on the half that carries the security
      property, which is why this is a wording conflict and not a
      vulnerability: the hint is never trusted, and the lens is always
      re-derived from owned batches and enrollments. AC10.1.6's "ignores
      it" is a true statement about AUTHORIZATION - the hint grants
      nothing - written before B.4 fixed the refusal shape. B.4 is the
      later and more specific artifact and names a status, a code and a
      citation, so it wins on the ROUTING question while AC10.1.6's
      authorization reading stands unchanged.

      U2 owns the status, the code and the class here because that is
      error-contract surface. U3 owns the derivation that decides which
      branch applies.
    source: >
      [contract-summary B.4], [stories.md AC10.1.6], [requirements FR1.3,
      FR1.4, FR1.5], [project: never trust a client-supplied lens hint]

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
      Every money-carrying property references the shared `Money` schema
      component by `$ref`, and never declares an inline type. The component
      itself carries the canonical pattern.
    category: validation
    applies_to: Every response and request schema carrying money
    trigger: Schema generation
    logic: >
      IF a property is money-carrying
      THEN it is `$ref: '#/components/schemas/Money'`
      ELSE it declares its own type inline, and the build fails.
    violation_behaviour: >
      Build failure on any inline-declared money property, and on any change
      to the `Money` component that widens its pattern.
    rationale: >
      **An earlier draft of this rule was circular, and the circularity is
      worth recording.** It said "every property CARRYING MONEY is a string
      matching the pattern" - but "carrying money" is not decidable from a
      generated document. Selecting properties by the pattern makes the
      assertion tautological (it checks the pattern on properties chosen for
      having it), and selecting by name misses by design. Worse, the defect
      NFR9.30 motivates this check by - a money value typed as a free-form
      string - is exactly the case a pattern-based selector cannot see.

      `$ref` to the declared component is the decidable predicate. The
      component exists already [contract-summary B.6], carries the pattern
      once, and makes the real assertion structural: a money property either
      references the single definition or it does not.

      A JSON number is an IEEE 754 double in most parsers, so emitting one
      converts the value to a float on the client - reintroducing the exact
      representation error the money module exists to prevent, on the far
      side of the wire where none of its controls reach. Referencing one
      component is what makes that impossible to do one endpoint at a time.
    source: [contract-summary B.5 and B.6, NFR9, U1 NFR9.30]

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
      No teacher-facing response schema contains an owner-private profile
      field, AND none contains `student_account_id` or any other account id.
      Both sets are asserted by the same schema-wide iteration.
    category: authorization
    applies_to: Every teacher-lens response schema, including ones added later
    trigger: Schema generation
    logic: >
      IF a teacher-lens response schema declares a field in the owner-private
      set
      OR declares an account id of any kind
      THEN the build fails.
    violation_behaviour: Build failure.
    rationale: >
      **Two field sets, one mechanism - and an earlier draft of this rule
      carried only the first.**

      The profile set is the student-and-guardian privacy boundary [TC-13,
      D-7]. The account-id set is ADR-001's owner boundary: a teacher-facing
      response exposes `enrollment_id` and never `student_account_id`,
      because an account id is a GLOBAL key while an enrollment id is scoped
      to one owner. ADR-001 records choosing this gate over building a new
      mechanism - "the existing schema-wide invariant test gains one more
      forbidden field set rather than a new mechanism" is its stated
      positive consequence.

      Omitting the second set has a concrete failure: a later Bolt ships a
      roster response declaring `student_account_id`, this gate passes, and
      teacher A holds a stable global key for a student also enrolled with
      teacher B - the exact cross-teacher traversal ADR-001 exists to
      prevent, through the gate ADR-001 nominated to catch it.

      Iteration rather than per-endpoint tests is what covers the endpoint
      added in a later Bolt after everyone stopped thinking about it. It is
      also the assertion a conformance tool cannot make: a response wrongly
      including either field set is perfectly conformant.
    source: [TC-13, D-7, NFR14, ADR-001, contract-summary E.2 gate 3]

  # ---- BR3.x - The route harness ----

  - id: BR3.1
    statement: >
      Every route resolves a lens, except the five routes in `PUBLIC_ROUTES`
      and the one route in `LENS_EXEMPT_AUTHENTICATED`. The two sets are
      separate and neither is open-ended.
    category: authorization
    applies_to: Every route in the application
    trigger: Test collection, against the real application object
    logic: >
      IF a route resolves no dependency whose return annotation is a Lens
      subtype
      AND the route is in neither set
      THEN the build fails.
    violation_behaviour: >
      Build failure on the commit that adds the unlensed endpoint, not on a
      later review.
    rationale: >
      The failure mode is not a wrong lens, it is a FORGOTTEN one - and a
      dependency somebody forgot produces an endpoint that works perfectly
      and authorizes nothing.

      **Two sets, not one, and an earlier draft of this rule had only an
      open-ended `PUBLIC_ROUTES` "empty in B2 and growing".**

      `PUBLIC_ROUTES` holds exactly five entries, fixed by contract-summary
      §B.3: OTP issue, OTP verify, health, and the external deletion route.
      These are genuinely public - no token, no identity.

      `POST /v1/auth/refresh` is NOT public. It authenticates by the refresh
      token itself and resolves no lens, which makes it the one route
      needing an explicit no-lens-by-design marker. It lives in a SEPARATE
      set precisely "so the route-enumeration test does not need a hole in
      its main allowlist" [§B.3].

      The failure the separation prevents is concrete: with one growing
      allowlist, the implementer who first hits a failing refresh route
      takes the cheapest green edit and adds it to `PUBLIC_ROUTES`, where
      nothing records that it must stay authenticated. A route that
      authenticates silently becomes one that does not.

      "Exactly five" is also the stronger control: a sixth entry is a diff
      against a stated number, where an addition to a growing set reads as
      routine.
    source: [contract-summary B.3 and E.2, team.md Authorization, TC-11, D-2, US10.1]

  - id: BR3.2
    statement: >
      The harness resolves each dependency's return annotation with
      `typing.get_type_hints` against the function's own module, treats a
      union as a lens when EVERY member is a Lens subtype, unwraps
      `Annotated` and generic aliases, and walks nested dependencies
      recursively. A resolution failure fails the build; it is never
      swallowed.
    category: constraint
    applies_to: The route harness
    trigger: Every run
    logic: >
      IF an annotation cannot be resolved to a type
      THEN the build fails naming the route
      ELSE the resolved type decides whether the dependency is a lens, with
      a union counting only when all members qualify.
    violation_behaviour: >
      Name-matching certifies nothing after the first rename. **Swallowing a
      resolution error is worse**: a blanket `except TypeError: return True`
      makes this rule pass universally and authorize nothing.
    rationale: >
      Annotation-matching is right, but three shapes defeat a naive
      `issubclass` and none of them is exotic here:

      - **String annotations.** `from __future__ import annotations` makes
        every annotation a string, and `issubclass('TeacherLens', Lens)`
        raises. The project's own lint configuration selects the `UP` rule
        set, which encourages exactly that import - so this is the expected
        shape, not an edge case.
      - **Unions.** `TeacherLens | GuardianLens` is the natural annotation
        for the dual-lens account AC10.1.8 describes. A union is a lens only
        when every member is, or the check admits a dependency that
        sometimes returns something else.
      - **`Annotated` and generic aliases**, which wrap the type the check
        needs.

      The damage is not the false negative. It is the implementer who hits
      the `TypeError`, wraps the call, and returns True on failure - after
      which every route passes and none is checked.
    source: [team.md Authorization, AC10.1.8, project Ruff UP ruleset]

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
      Unit's definition of done. **A fixture that triggers more than one
      assertion must assert WHICH violation was reported**, not merely that
      the gate refused: a fixture carrying both an inline money type and an
      unsibling'd display field is refused by the pairing rule alone, which
      certifies the money rule while it selects nothing.
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

  - id: BR4.3
    statement: >
      BR1.4's uniform-403 decision contradicted FIVE downstream artifacts,
      each of which has now been amended. This is a cross-Bolt obligation,
      not a note, and it is DISCHARGED rather than outstanding.
    category: policy
    applies_to: bolt-plan.md and risk-and-sequencing-rationale.md
    trigger: This stage's approval
    logic: >
      IF BR1.4 stands
      THEN each of the following is amended to match, or the Bolt that
      carries it fails its own stated criterion while being correct.
    violation_behaviour: >
      A Bolt whose confidence hypothesis is falsified by a correct
      implementation. Worst at B3, where the hypothesis is the walking
      skeleton's privacy claim and is checked at a human checkpoint.
    rationale: >
      **An earlier draft of this Unit recorded only B2's own DoD as
      contradicting the decision. Four more artifacts did**, and the
      decision was therefore taken against an incomplete picture. The
      fifth was missed by review as well, and found only by sweeping the
      record for `404` rather than working from the list:

      - **B2 DoD** - repeats "the 404-instead-of-403 rule".
      - **B3 confidence hypothesis** - "*receives a 404 and not a 403, and
        the response is byte-indistinguishable*". This is the walking
        skeleton's privacy hypothesis, read at a human checkpoint.
      - **B7 confidence hypothesis** - "*a guardian receives a 404, and a
        student receives a 404*".
      - **B9 confidence hypothesis** - "*returns a 404 rather than a 403*".
      - **`risk-and-sequencing-rationale.md`, the B3 checkpoint criterion**
        - "*a cross-teacher request returns 404 and not 403*". Named in
        neither draft nor review; found by grep. It is the criterion a
        human reads at the skeleton checkpoint, so it is arguably the
        costliest of the five to have left wrong.

      A confidence hypothesis is a falsification criterion. Under BR1.4 all
      four are falsified by implementations that are correct, which is the
      worst possible shape for a check: it fails on the right answer.

      **Status: all five amended 2026-10-18**, each naming a 403 whose two
      responses are byte-identical. The generalisable lesson is that a
      decision reversing a widely-cited value is verified by searching the
      record for that value, not by enumerating the places one remembers.

      Note that B3's wording already demands **byte-indistinguishable**,
      which is BR1.4's own property and stronger than the status alone -
      further evidence that the status is the incidental half of this
      decision and the response body is the substantive one.

      B1 set this project's precedent at NFR9.32: a cross-Bolt obligation
      is recorded as an obligation with named owners, never left as a hope
      that somebody notices.
    source: >
      [bolt-plan B2/B3/B7/B9], [risk-and-sequencing-rationale B3
      checkpoint], [contract-summary line 873], [B1 NFR9.32]

  - id: BR4.4
    statement: >
      BR1.4's structural-equivalence clause is an obligation on U3, the
      first Unit that implements a lens-scoped lookup. U2 cannot test it
      and does not claim to.
    category: policy
    applies_to: U3 `identity-and-access` (B3), and any later Unit adding a lens-scoped lookup
    trigger: The first lens-scoped resource lookup is implemented
    logic: >
      IF a Unit implements a lookup that can fail as unreachable or absent
      THEN that Unit carries a test asserting BOTH branches execute the
      same queries - not merely that the two responses match byte for
      byte, which a short-circuited implementation also satisfies.
    violation_behaviour: >
      The clause silently becomes advisory. An implementer checks
      existence first, returns early on a miss, and ships a
      byte-identical pair of responses whose timings differ - passing
      every test BR4.1 requires, because none of them looks at the
      queries.
    rationale: >
      **BR4.1's fixture obligation deliberately excludes BR1.4**, and
      correctly: U2 owns no lookup code, so there is nothing here to
      fixture. But an obligation excluded from the Unit that states it,
      and not handed to the Unit that can discharge it, is an obligation
      nobody holds.

      That is the gap this project's own precedent exists to close. B1
      set it at NFR9.32 and BR4.3 applies it by naming its five artifacts
      and their owners. BR1.4's structural clause was left as prose in a
      `violation_behaviour` field with no owner, no fixture and no test -
      the one rule in this Unit that states a requirement and assigns it
      to nobody.

      U3 is the right owner on three counts: it owns lens resolution, it
      is the first Unit with a lookup that can fail either way, and it is
      the walking skeleton, so the obligation is discharged at the point
      the human checkpoint reads the privacy claim rather than several
      Bolts later.

      The test is structural, as BR1.4 requires - assert the queries both
      branches execute, never a wall-clock difference.
    source: >
      [BR1.4], [BR4.1 exclusion], [B1 NFR9.32 precedent],
      [bolt-plan B3 - U3 owns lens resolution]
```

---

## Part B — Rules summary

| Rule | Category | What it holds |
|---|---|---|
| **BR1.1** | constraint | Five classes, closed; every raise site picks one |
| **BR1.2** | calculation | `retryable` derived at the handler, never per raise site |
| **BR1.3** | constraint | No English message, ever; a string key instead |
| **BR1.4** | authorization | **Byte-identical 403** for unreachable and absent — the upstream contradiction, resolved and recorded |
| **BR1.5** | authorization | No error code distinguishes the two cases |
| **BR1.6** | policy | `retryable: false` on 401 reconciled with refresh-then-replay |
| **BR1.7** | policy | An unsupported lens hint is refused 403, never silently ignored |
| **BR2.1** | constraint | Committed schema equals generated, or CI fails |
| **BR2.2** | validation | Money properties `$ref` the shared component, never inline |
| **BR2.3** | constraint | `*_display` never appears without its sibling |
| **BR2.4** | authorization | **Two** forbidden field sets: profile fields and account ids |
| **BR3.1** | authorization | Five public routes, one authenticated exempt — two separate sets |
| **BR3.2** | constraint | Resolve annotations properly; never swallow a resolution error |
| **BR4.1** | policy | Every assertion ships a fixture, asserting *which* violation |
| **BR4.2** | policy | Conformance is never privacy coverage, in writing |
| **BR4.3** | policy | **Five downstream artifacts contradicted BR1.4**; all amended, discharged |
| **BR4.4** | policy | BR1.4's structural-equivalence clause is U3's obligation to test |

**The four worth a second look:**

- **BR1.4** is the one an implementer will try to undo, because the upstream
  contract argues both sides. Note what changed at review: an earlier draft
  settled only the *status* and called the two cases "identical" in prose,
  which left the oracle open through the response body. Two 403s carrying
  `BATCH_NOT_FOUND` and `BATCH_NOT_YOURS` leak everything the status hid.
- **BR4.3** is the obligation that decision creates. Three Bolt confidence
  hypotheses — including the walking skeleton's — assert 404 as their
  falsification criterion, so correct implementations would fail them.
- **BR2.4** carries **two** field sets because ADR-001 chose this gate over
  building another. Omitting the account-id half leaves a teacher holding a
  global key for a student shared with another teacher.
- **BR3.1** keeps the authenticated refresh route out of the public
  allowlist, because the cheapest green edit for a failing refresh route is
  to call it public — and then nothing records that it must not be.

## Assumptions & Open Questions

**Carried from B1**: OQ-B1-1, the Bangla money rendering. BR2.3's pairing is
structural and holds regardless of what the display string contains.
