# Security Design — `api-contract` (U2)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Depth**: Comprehensive
**Summary confirmed**: 2026-10-18

> NFR Requirements stated **what** must hold. This document states **how**:
> the concrete mechanism per requirement, where it physically lives, and what
> fails when it is violated.
>
> **This is a design stage.** Snippets below are interface-level and
> illustrative; the implementations belong to Code Generation.
>
> U2 has no process, so most NFR-design vocabulary — circuit breakers, cache
> tiers, shard keys, SLO windows — does not apply, and §D records that as a
> structural finding rather than an empty file. What U2 *does* own is three
> things that must be placed: four CI gates, one piece of runtime code on
> every error path, and one typing island.

## Sources

- [stage] `nfr-design-questions.md` — Q1 (where the gates run), Q2
  (determinism), Q3 (identifying a teacher-lens schema), Q4 (the handler),
  Q5 (fixtures), Q6 (what does not apply), Q7 (what is handed forward)
- [upstream] `construction/api-contract/nfr-requirements/security-requirements.md`
  — NFR3.1–NFR17.3
- [upstream] `construction/api-contract/nfr-requirements/tech-stack-decisions.md`
  — A.1–A.4
- [upstream] `construction/api-contract/functional-design/functional-spec.md`
- [upstream] `inception/contract-design/contract-summary.md` — §B.2 the error
  envelope, §B.3 the allowlists, §B.4 the lens contract
- [team] `## Code Style` → error handling, authorization; `## Testing Posture`
- [project] `## Forbidden` / `## Mandated`

---

## A. Where everything lives

```
app/
  errors/            # NFR17.2, NFR17.3 — runtime, no I/O
    __init__.py      #   the five classes
    handler.py       #   one FastAPI exception handler
    codes.py         #   the code registry        [NFR14.3, NFR1.5]
  schemas/           # NFR14.11 — strict mypy island
  authz/
    lenses.py        #   the Lens type hierarchy  (U3 resolves them)
    annotations.py   #   the shared resolver      [NFR14.7] — two callers
  contract/
    serialize.py     #   canonical serialization  [NFR16.3]

tests/contract/
  test_schema_diff.py      # NFR16.1–16.3
  test_money_schema.py     # NFR9.1, NFR9.2
  test_privacy_schema.py   # NFR14.8
  test_route_lenses.py     # NFR14.5–14.7
  test_error_contract.py   # NFR3.1, NFR13.1, NFR17.3
  fixtures/                # four violation fixtures [NFR14.1, NFR14.2]

openapi.json         # the committed contract      [NFR16.1]
```

**One entry point.** All of it runs under `make check`, the same command
locally and in CI. No gate is a bespoke script, a pre-commit-only hook, or a
CI-only job, because a gate reproducible only by pushing is one that gets
bypassed, and one that runs only locally is one that gets skipped.

**No secret is required.** Every gate reads a generated document or a Python
app object. Nothing touches the gateway, the database or the network, so the
blocking suite stays runnable on a laptop.

---

## B. The four gates

### B.1 Schema diff — NFR16.1, NFR16.2, NFR16.3

**Mechanism.** `test_schema_diff.py` generates the document from the live app
and compares its bytes against the committed `openapi.json`.

**Canonical serialization is the fix; the comparison only proves it holds.**
One function in `app/contract/serialize.py` is the sole writer:

```python
def canonical(document: dict) -> str:
    """Serialize deterministically across processes."""
    return json.dumps(
        _sort_lists(document),      # the half that matters
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"
```

> **`sort_keys` alone is NOT sufficient, and this was verified rather than
> assumed.** It orders object *keys*; it does not order a list *value*. An
> OpenAPI `required` list built from a `set` keeps its hash ordering straight
> through a fully canonical dump. Measured while designing this stage: a
> document whose `required` came from a set, dumped with `sort_keys=True` and
> fixed separators, **still differed** between an in-process and a subprocess
> generation. `_sort_lists` sorts the order-insensitive ones — `required`,
> enum members, tag lists — and that is what actually closes it.

**The cross-process assertion** spawns a subprocess that regenerates and
compares:

```python
def test_generation_is_deterministic_across_processes() -> None:
    in_process = canonical(build_openapi())
    result = subprocess.run(
        [sys.executable, "-m", "app.contract.emit"],
        capture_output=True, text=True, check=True,
    )
    assert in_process == result.stdout
```

A subprocess gets a **fresh hash seed**, which is the condition that reveals a
set-derived ordering. Verified: against the set-derived document above, this
comparison **failed** while generating twice in one process **passed**. That
is the entire argument for this shape, demonstrated rather than reasoned.

**`PYTHONHASHSEED` is deliberately not pinned.** Pinning it would make the
test pass while CI — which does not pin it — still fails randomly.

**Regeneration is the only sanctioned fix** [A.1, NFR16.4]. The committed file
is an *output*; `make openapi` rewrites it, and that command is documented
beside the file. Hand-editing it to make a red diff green inverts the control
into a rubber stamp, and it looks exactly like fixing the problem.

### B.2 Money in the schema — NFR9.1, NFR9.2

**Mechanism.** Walk the generated document's schemas. Two assertions:

1. **No property declares an inline money-shaped type.** Every money-carrying
   property `$ref`s the shared `Money` component, which alone carries
   `pattern: ^[0-9]+\.[0-9]{2}$` and `type: string`.
2. **No `<x>_display` field exists without a sibling `<x>`** that `$ref`s the
   component. The display string is not pattern-matched — it is presentation,
   and its content is the rendering specification closed at OQ-B1-1.

**Why `$ref` rather than "properties carrying money".** The latter is
undecidable from a generated document and circular besides: selecting by the
pattern checks the pattern on properties chosen for having it, and the defect
this gate exists to catch — a money value typed as a free-form string — is
exactly what a pattern-based selector cannot see.

### B.3 The privacy boundary — NFR14.8

**The lens is read from the route, never guessed from the schema name.** This
is the decision that makes the gate real rather than heuristic:

```python
for route in app.routes:
    lens = resolve_lens_type(route)          # shared with B.4 [NFR14.7]
    if lens is not TeacherLens:
        continue
    for field_path in walk_schema(route.response_model):   # cycle-guarded
        assert field_path.name not in OWNER_PRIVATE_FIELDS
        assert field_path.name not in FORBIDDEN_ACCOUNT_IDS
```

**Both forbidden sets ride one iteration** [BR2.4, ADR-001]: owner-private
profile fields, and account identifiers. A teacher-facing response carrying
`student_account_id` hands teacher A a stable global handle on a student also
enrolled with teacher B — the cross-teacher traversal ADR-001 exists to
prevent.

**Three rejected alternatives, each of which fails quietly:**

| Rejected | Fails when |
|---|---|
| Match schema names containing "Teacher" | A rename; or a shared model returned under two lenses |
| Check only top-level properties | The profile field is nested in an embedded student object — the likely shape |
| Check schemas in isolation | A model is teacher-facing only because some route returns it under a teacher lens; that fact lives on the route |

**The recursion carries a cycle guard.** `$ref` graphs can be
self-referential, and an unguarded walk **hangs** CI rather than failing it. A
hang is worse than a failure because nobody reads it as a result — it looks
like a slow build until someone cancels it.

**Schemathesis is not this gate and never counts as privacy coverage**
[NFR14.9, BR4.2]. A response wrongly declaring a profile field is perfectly
conformant: it matches its own declaration.

### B.4 Route lenses — NFR14.5, NFR14.6, NFR14.7

**Mechanism.** `test_route_lenses.py` imports the **real application object at
test collection time**, so an unlensed endpoint reddens CI on the commit that
adds it. For each route it walks `route.dependant` recursively — a lens may be
nested inside a composed dependency — and resolves each dependency's return
annotation.

**One shared resolver, two callers** [Q7]. `app/authz/annotations.py` holds it;
B.3 and B.4 both call it. A second implementation would almost certainly be the
naive `issubclass` the requirement exists to forbid:

```python
def resolve_lens_type(obj) -> type | None:
    """Resolve a return annotation to a Lens subtype, or None.

    :raises AnnotationResolutionError: the annotation cannot be resolved
    """
    hints = typing.get_type_hints(obj)      # string annotations
    ann = _unwrap(hints.get("return"))      # Annotated, generic aliases
    if _is_union(ann):                      # every member must qualify
        return ann if all(_is_lens(m) for m in _members(ann)) else None
    return ann if _is_lens(ann) else None
```

Three defeaters are handled explicitly, and none is exotic here:

- **String annotations.** The project's Ruff config selects `UP`, which
  encourages `from __future__ import annotations` — so this is the *expected*
  shape, not an edge case, and a bare `issubclass` raises on it.
- **Unions.** `TeacherLens | GuardianLens` is the natural annotation for the
  dual-lens account of AC10.1.8. A union qualifies only when **every** member
  does, or the check admits a dependency that sometimes returns something else.
- **`Annotated` and generic aliases**, which wrap the type the check needs.

**A resolution failure fails the build naming the route; it is never
swallowed.** The real damage is not the false negative — it is the implementer
who hits the error, wraps the call in `except TypeError: return True`, and
makes the whole check pass universally while authorizing nothing.

**Two allowlists with fixed lengths** [NFR14.6]:

```python
PUBLIC_ROUTES = frozenset({            # exactly 5
    ("POST", "/v1/auth/otp"),
    ("POST", "/v1/auth/verify"),
    ("GET",  "/health"),
    ("GET",  "/account-deletion"),     # TC-19, U11
    ("POST", "/account-deletion"),     # TC-19, U11
})
LENS_EXEMPT_AUTHENTICATED = frozenset({  # exactly 1
    ("POST", "/v1/auth/refresh"),      # authenticates by refresh token
})
assert len(PUBLIC_ROUTES) == 5
assert len(LENS_EXEMPT_AUTHENTICATED) == 1
```

The length assertions are the control: a sixth entry is a diff against a
stated number, not a line appended to a growing list. The **separation**
matters for a concrete reason — with one combined list, whoever first hits a
failing refresh route takes the cheapest green edit and adds it to
`PUBLIC_ROUTES`, after which nothing records that the route must stay
authenticated.

---

## C. The runtime code

### C.1 The error handler — NFR17.2, NFR17.3

**`app/errors/` imports only the standard library, FastAPI's response types,
and the five exception classes.** No database, no network, no file I/O.

**Enforced, not intended.** A layered-import test of the same shape as B1's
`test_import_gates.py` — which currently passes 81 tests in this repository —
asserts `app.errors` imports nothing from `app.db`, `app.repositories`,
`app.api`, or any HTTP client.

> The realistic violation is not an obvious one. It is **structured error
> logging that writes to the database**, or a lookup enriching `details` with
> a human-readable name. Both look like improvements, and both put a query on
> every error path in the system — so a database outage stops producing
> handled 503s and starts producing unhandled 500s, precisely when the system
> is already degraded.

**Totality is a typing property, not a test** [NFR17.3]:

```python
match error:
    case ValidationError():    return _respond(400, error, retryable=False)
    case AuthorizationError(): return _respond(error.status, error, retryable=False)
    case ConflictError():      return _respond(409, error, retryable=False)
    case TransientError():     return _respond(503, error, retryable=True)
    case FatalError():         return _respond(500, error, retryable=False)
    case unreachable:          assert_never(unreachable)
```

Mypy proves this exhaustive statically — the same construct B1 uses for its
ledger kinds. A sixth class without a mapping is a **build-time type error**
rather than a production 500.

`retryable` is read from the class here and nowhere else [BR1.2]. A raise site
has no say, which is what stops two sites of one class disagreeing.

**The handler's own `except Exception` is one of exactly two sanctioned sites**
in the backend; the other is the scheduled fee-generation job's top level.

### C.2 The error envelope — NFR3.1, NFR3.2, NFR13.1

```json
{"error": {"code": "...", "retryable": false, "message_key": "..."}}
```

- **`additionalProperties: false`**, so a `message` field fails schema
  validation and the diff gate. The absence of English message text is
  structural rather than a convention somebody maintains [NFR3.1] — a
  server-authored English string cannot be localized, and in a Bangla-first UI
  that guarantees untranslated English in front of a teacher.
- **`details` is typed per `code`**, never a free-form dump of request state.
  That typing is what keeps NFR3.2 achievable: there is no field into which a
  phone number, an OTP or a token could be casually placed. Every error log
  carries the correlation id and none of those three.
- **The code registry contains no pair distinguishing "unreachable" from
  "absent"** [NFR14.3, BR1.5]. A `RESOURCE_NOT_FOUND` / `RESOURCE_FORBIDDEN`
  pair is the defect, even though each code is individually reasonable.
- **`retryable: false` on a 401 is reconciled with refresh-then-replay in
  writing** [NFR13.1, BR1.6]: a *different* request (the refresh), then exactly
  one replay, only on `ACCESS_TOKEN_EXPIRED`, with any second 401 ending the
  session. Both halves produce a defect when read alone — a refresh loop, or a
  client that cannot refresh at all.

### C.3 The typing island — NFR14.11

```toml
[[tool.mypy.overrides]]
module = "app.schemas.*"
strict = true
disallow_any_explicit = true
```

Added in this Bolt because **U2 is the Unit that first populates
`app.schemas`**. `team.md` names three strict islands; B1 configured only
`app.money.*`, correctly, since an override naming a non-existent module is
dead configuration — which left this one with no owning Bolt until now.
`app.authz.*` stays unconfigured until U3 creates it.

**Response-schema separation is a typing control as well as a privacy one.** A
lens type parameterizes which response models an endpoint may return, so a
teacher-lens endpoint returning a student-private response is a **mypy error**
rather than a review finding. That is the layer catching right-lens-wrong-data,
which neither B.3 (which checks fields, not which endpoint returns them) nor
B.4 (which checks a lens is present, not which data it guards) can see.

`disallow_any_explicit` earns its place here specifically: a response field
typed `Any` carries a profile field at runtime while declaring nothing in the
schema — a hole straight through B.3.

---

## D. The four fixtures — NFR14.1, NFR14.2

**Every gate in §B iterates a collection that is empty in B2.** No routes, no
money endpoints, no response schemas. Each returns green having examined
nothing, and a passing test and a vacuous test are the same colour.

**Each fixture is otherwise-valid and violates exactly one rule.** That is what
makes "assert which violation" achievable — a merely malformed fixture fails
every gate for the wrong reason and certifies nothing while looking like a
working test.

| Gate | Fixture | Asserted |
|---|---|---|
| Money | Valid document, one property inline `{"type":"string"}` where a `$ref` belongs | Error names **that property path** |
| Display pairing | Valid document, `amount_display` with no `amount` | Error names **the orphan field** |
| Privacy | Valid document, one teacher-lens response declaring `date_of_birth`, a second declaring `student_account_id` | **Two** errors, one per field set |
| Route lenses | A throwaway `FastAPI()` app with one unlensed route | Error names **that route's path** |

Two design points:

- **The route fixture builds its own app object** rather than registering a bad
  route on the real one and removing it afterwards. That mutation leaks into
  any test running in between, and the failure presents as an unrelated test
  failing mysteriously.
- **The privacy fixture asserts two distinct errors**, because B.3 carries two
  field sets through one iteration. A fixture tripping only the profile set
  leaves ADR-001's account-id set unexercised while the gate reports green.

**A fixture that stops failing is itself a build failure** [NFR17.1]. These are
the one part of U2 whose *failure* is the passing condition.

---

## E. What this Unit does not design, and why

Not an omission — a structural finding. The stage's own kind-gating excludes
four deliverables for a `spec` Unit; the reasoning is recorded so a later
reader sees the analysis happened.

| Category | Status | Why |
|---|---|---|
| **Reliability** | No design | Circuit breakers, retries, health checks and failover all presuppose a process that can be unavailable. U2 ships none. The one piece that runs in production states its requirement as the **absence** of a failure mode (no I/O, total over the taxonomy) rather than as a recovery pattern. A circuit breaker around an error handler is incoherent — there is nothing downstream to break. |
| **Scalability** | No design | No process, no load, no shard key, no capacity threshold. |
| **Performance** | No design | No endpoint to measure. The handler's cost is bounded structurally by the no-I/O rule; a latency number would be unmeasurable here and undefendable. |
| **Observability** | One rule only | No metric, no SLI, no dashboard — nothing is running. The one genuine edge is **NFR3.2**, a log *content* rule, designed in §C.2 where the envelope lives. |
| **Logical components** | Not produced | `produces_kinds` gates it to `service`/`ui`/`library`. U2 is `spec`. |

---

## F. Handed forward

| What | Owner next | Must not be re-derived |
|---|---|---|
| Five exception classes + one handler | Every later Unit | No endpoint writes its own try/except for them |
| `Lens` type hierarchy | **U3** resolves them | The types exist here so B.4 has something to match on |
| Committed schema + regeneration command | Every later Bolt | Hand-editing the output inverts the gate |
| **The annotation resolver** | B.3 and B.4 today; every later lens check | **One function, two callers.** A second implementation would be the naive `issubclass` the requirement forbids |
| **NFR14.4** — structural equivalence | **U3**, per BR4.4 | U2 owns no lookup code; both branches must execute the same queries, asserted structurally and never as a wall-clock bound |

---

## Assumptions & Open Questions

**None.** [assumption] OQ-B1-1 closed on 2026-10-18, so the `*_display`
pairing gate has settled rendering content behind it. The pairing rule was
always structural and independent of that content, so no design here changes
as a result.
