# Entity Model — `api-contract` (U2)

**Stage**: functional-design (3.1)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`

> **This Unit is not deployed and persists nothing.** It owns no table, no
> row, no endpoint and no running process. The "entities" below are
> **contract types**: the shapes every later Unit's API surface is built from
> and checked against. They exist so that a guarantee can be asserted once,
> over the generated schema, rather than remembered per endpoint.

## Sources

- [stage] `functional-design-questions.md` — Q1 (the 403/404 contradiction),
  Q2 (what a spec Unit produces), Q5 (lens types here, resolution in U3),
  Q6 (`retryable` derived at the handler)
- [upstream] `inception/contract-design/contract-summary.md` — the error
  envelope schema, the five classes, the money pattern, the `*_display` rule
- [upstream] `inception/units-generation/unit-of-work.md` — U2 definition
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US9.2,
  US10.1
- [upstream] `inception/domain-design/components.md` — the component
  catalogue
- [upstream] `inception/requirements-analysis/requirements.md` — NFR16
  (`/v1/` additive), NFR14 (privacy boundary)
- [team] `## Code Style` → error handling, authorization
- [project] `## Forbidden` / `## Mandated`

---

## Part A — Source of truth

```yaml
contract_types:

  - name: ErrorClass
    kind: closed_enumeration
    description: >
      The five caller behaviours, chosen because they map to five distinct
      things a caller does next. Closed: a sixth value would mean a caller
      behaviour nobody has named.
    values:
      - value: validation
        meaning: The request is wrong.
        caller_behaviour: Fix and resubmit. Never retry as-is.
        http: 400
        retryable: false
      - value: authorization
        meaning: No lens grants this.
        caller_behaviour: Re-authenticate or stop. Never retry.
        http: 403
        retryable: false
      - value: conflict
        meaning: Valid request; current state forbids it.
        caller_behaviour: Refetch and decide. Retry as-is is wrong.
        http: 409
        retryable: false
      - value: transient
        meaning: May succeed if repeated.
        caller_behaviour: Retry with backoff.
        http: 503
        retryable: true
      - value: fatal
        meaning: A bug, or unrecoverable.
        caller_behaviour: Do not retry. Alert.
        http: 500
        retryable: false

  - name: ErrorEnvelope
    kind: response_shape
    description: >
      The single shape every error response carries. No endpoint writes its
      own error body.
    fields:
      - name: error.code
        type: string
        required: true
        description: >
          A stable machine value. The client switches on this and never on
          message text.
      - name: error.retryable
        type: boolean
        required: true
        description: >
          Server-provided, derived from the class at the handler. The client
          holds no business logic, so it does not infer retryability from the
          HTTP status - it is told.
      - name: error.message_key
        type: string
        required: true
        description: >
          Names a client string resource. No English message is ever emitted:
          a server-authored string cannot be localized, and in a Bangla-first
          UI that guarantees untranslated English error text.
      - name: error.error_class
        type: ErrorClass
        required: false
      - name: error.details
        type: object
        required: false
        description: Typed per code. Rendered, never interpreted.
    constraints:
      - No `message` field is ever emitted, at any level.
      - additionalProperties is false, so an endpoint cannot smuggle a field
        past the diff gate.

  - name: Lens
    kind: abstract_type
    description: >
      The base of the three-way lens hierarchy. **U2 defines the types; U3
      resolves them.** This Unit needs the type to exist so the route harness
      can match on a dependency's RETURN ANNOTATION being a Lens subtype -
      never on the function's name, which a rename defeats.
    subtypes:
      - name: TeacherLens
        carries: The resolved owner_id every teacher-scoped query is rooted at.
      - name: StudentLens
        carries: The resolved account identity and its enrollments.
      - name: GuardianLens
        carries: The resolved account identity and its children's enrollments.
    constraints:
      - A lens is a DATA DEPENDENCY, not a side-effecting guard. The handler
        cannot compile a scoped query without it, because the scoping value
        lives inside the lens object. That is what converts authorization
        from a precondition somebody can forget into a value they need.
      - Response models are parameterized by lens type, so a teacher-lens
        endpoint returning a student-private response is a type error rather
        than a review finding.

  - name: MoneyField
    kind: schema_constraint
    description: >
      Every money value crosses the API as a JSON string in canonical form.
      Owned by U1 as a type; owned here as a SCHEMA-LEVEL assertion, which is
      what catches a money value typed as a free-form string - something no
      import rule can see.
    pattern: '^[0-9]+\.[0-9]{2}$'
    constraints:
      - type is string, never number. A JSON number is an IEEE 754 double in
        most parsers, so emitting one converts the value to a float on the
        client, where none of U1's controls reach.
      - The pattern admits no sign. A negative amount cannot cross the
        boundary; every quantity that legitimately does is one the sign rules
        already forbid to be negative.
      - A `*_display` field is a presentation string and is NOT matched
        against this pattern. It is constrained by the pairing rule below.

  - name: DisplayPairing
    kind: schema_constraint
    description: >
      A money field carries a sibling `*_display` string only where a screen
      renders it, and that sibling never appears alone.
    rule: >
      IF a response schema declares a field named `<x>_display`
      THEN it also declares `<x>` matching the MoneyField pattern.
    rationale: >
      A display string without its canonical amount leaves the client with
      nothing to compare, cache or re-render, and leaves the server's
      rendering decision unverifiable. Recorded in the schema rather than in
      prose so the diff gate catches a field gaining or losing its sibling.

  - name: OwnerPrivateField
    kind: field_set
    description: >
      The fields a student or guardian writes about themselves, which no
      teacher-lens response may ever carry.
    constraints:
      - Asserted schema-wide by iterating the generated document, NOT per
        endpoint. A per-endpoint test covers the endpoints someone
        remembered; iteration covers the endpoint added three Bolts later.
      - This is the assertion Schemathesis cannot make: a response wrongly
        including a profile field is perfectly conformant.

  - name: ForbiddenAccountIdField
    kind: field_set
    description: >
      Account identifiers of any kind, which no teacher-facing response may
      carry. ADR-001's half of the schema-wide invariant, checked by the
      same iteration as OwnerPrivateField.
    constraints:
      - A teacher-facing response exposes `enrollment_id` and never
        `student_account_id`. An account id is a GLOBAL key; an enrollment
        id is scoped to one owner.
      - ADR-001 chose to extend this gate rather than build a new mechanism,
        which is why both sets ride on one iteration.

  - name: LensHintOutcome
    kind: response_contract
    description: >
      What the server does with a client-supplied lens hint, and what it
      returns when the hint claims a lens the account's data cannot support.
    fields:
      - name: lens
        type: string
        required: true
        description: >
          The response is SELF-DESCRIBING: it names the lens that actually
          produced it, so the client renders from the response rather than
          from the hint it sent.
    constraints:
      - The hint affects navigation and UI shaping only. It is never trusted
        for authorization.
      - The server re-derives the lens from owned batches and enrollments on
        every request, and refuses with authorization (403)
        `LENS_NOT_AVAILABLE` when the hinted lens has no data behind it.
        Governed by BR1.7, which reconciles the two upstream sources that
        disagree on this point - AC10.1.6 says the hint is ignored, and
        contract-summary B.4 says it is refused.
      - A missing hint resolves the account's single available lens, or
        refuses with validation (400) `LENS_HINT_REQUIRED` when more than
        one is available and the route is lens-ambiguous.
      - This is error-contract surface, so U2 owns the code, the status and
        the class. U3 owns the derivation that decides which applies.
```

---

## Part B — Human-readable summary

**Six contract types, no persistence.** Each exists because something later
must be checkable against it:

- **`ErrorClass`** closes the taxonomy at five values. Each maps to one
  caller behaviour, which is what makes `retryable` derivable rather than a
  judgement at each raise site.
- **`ErrorEnvelope`** is the single error shape. `additionalProperties:
  false` means an endpoint cannot quietly add a field, and the absence of any
  `message` field is structural rather than a convention.
- **`Lens`** and its three subtypes exist here so the route harness has a
  *type* to match on. U3 owns everything that resolves one.
- **`MoneyField`** is U1's type expressed as a schema constraint — the half
  of the money boundary an import rule cannot see.
- **`DisplayPairing`** keeps a rendering string from appearing without the
  value it renders.
- **`OwnerPrivateField`** is the privacy boundary's API-level half, asserted
  by iterating the schema.

**What this Unit deliberately does not define**: any endpoint, any path, any
request or response body for a feature. Those belong to the Units that own
the features. U2 defines the *shapes and rules* those bodies are built from,
and the gates that check them.

---

## Assumptions & Open Questions

**Carried from B1**: the Bangla money rendering (OQ-B1-1) is unresolved. It
determines what a `*_display` string *contains*; the pairing rule here is
structural and holds regardless.
