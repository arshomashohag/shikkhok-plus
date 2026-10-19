# Unit Test Instructions — `api-contract` (U2)

**Stage**: code-generation (3.5)
**Unit**: U2 `api-contract` — `spec`, S
**Bolt**: B2 `b2-api-contract`
**Test strategy**: Comprehensive (10–15 tests per component)
**Methodology**: custom — see the predicate below

---

## The exact command

**Runnable before the first test-first cycle** (the runner exists from B1):

```bash
python3 -m pytest tests/contract tests/authz -q
```

Full gate, local and in CI, the same entry point in both:

```bash
make check
```

`make check` runs: `pytest` (whole suite with coverage), `ruff check`,
`ruff format --check`, `mypy app`. **No secret is required** — every gate in
this Unit reads a generated document or a Python app object, and nothing
touches the gateway, the database or the network.

---

## Framework and configuration

Already present from B1; this Unit adds no new test dependency:

- **pytest** — configured in `pyproject.toml`
- **coverage** — `fail_under = 100` scoped to `app/money`; `app/errors` and
  `app/contract` carry the 80% line floor from the `classic` scope
- **mypy** — `disallow_untyped_defs` globally; strict islands on
  `app.money.*` and (added in this Bolt) `app.schemas.*`
- **Ruff** — the project's named rule sets, with `tests/** = ["S101"]`

New directories: `tests/contract/`, `tests/contract/fixtures/`, `tests/authz/`.

---

## Which tests are written first

The team's ordering is a **predicate, not a list**: write the failing test
first when **both** hold — the correct output is knowable from the requirement
without having written the code, **and** a wrong answer would be a money error
or an authorization error.

**Test-first in this Unit** (all three are authorization):

1. `tests/authz/test_annotations.py` — the lens resolver
2. `tests/contract/test_route_lenses.py` — the route gate
3. `tests/contract/test_privacy_schema.py` — the privacy gate

A wrong answer in any of them **silently authorizes nothing while passing**,
which is the failure mode the predicate exists to catch. Note that the
route-lens gate lives in a test file but *is* the authorization control for
every Unit after this one — where the code lives is not part of the test.

**Test-after** for the error taxonomy, the envelope, canonical serialization
and the money schema gate. Each is still written **from the acceptance
criterion**, never from the implementation: if writing the assertion requires
reading the code to know what to assert, the acceptance criterion is the
defect.

---

## Per-component test inventory

### `app/authz/annotations.py` — 10 tests

| # | Test | Asserts |
|---|---|---|
| 1 | Plain `TeacherLens` annotation | Resolves to `TeacherLens` |
| 2 | **String** annotation (`from __future__ import annotations`) | Resolves — the project's `UP` lint rules encourage this, so it is the *expected* shape |
| 3 | `TeacherLens \| GuardianLens` | Resolves — every member qualifies |
| 4 | `TeacherLens \| None` | Returns `None` — **not** every member qualifies |
| 5 | `Annotated[TeacherLens, Depends(...)]` | Unwraps and resolves |
| 6 | Non-lens return type | Returns `None` |
| 7 | No return annotation | Returns `None` |
| 8 | Unresolvable annotation | **Raises** `AnnotationResolutionError` |
| 9 | The error is not swallowed | A caller wrapping in `except TypeError: return True` would fail this |
| 10 | Nested generic alias | Unwraps |

> Test 9 is the one that matters most. The real damage is not the false
> negative — it is the implementer who hits a `TypeError`, wraps the call, and
> makes the whole check pass universally while authorizing nothing.

### `app/contract/routes.py` — 11 tests

Allowlist shape (4): `PUBLIC_ROUTES` has **exactly 5** entries; it contains
each expected route; `LENS_EXEMPT_AUTHENTICATED` has **exactly 1**; the two
sets are disjoint.

> The length assertions are the control: a sixth entry is a diff against a
> stated number, not a line appended to a growing list.

Enumeration (7): an unlensed route is reported **by path**; a lensed route is
not; a route with a lens nested in a composed dependency is not (recursion); a
public-allowlisted unlensed route is not; the refresh route is not; a route
whose dependency has an unresolvable annotation **fails the build naming the
route**; the real app (zero routes in B2) reports zero violations.

### `app/contract/privacy.py` — 12 tests

Per field set (4): a teacher-lens response declaring an owner-private profile
field is reported; one declaring `student_account_id` is reported; a clean
teacher-lens response is not; a **student**-lens response declaring a profile
field is **not** reported (it is the student's own data).

Traversal (5): a nested object via `$ref`; an array `items`; an `allOf`
composition; an `anyOf` branch; a **self-referential `$ref` terminates**
rather than hanging.

> The cycle guard gets its own test because an unguarded walk **hangs** CI
> rather than failing it, and a hang is worse than a failure — it reads as a
> slow build until someone cancels it.

Lens identification (3): the lens is read from the **route**, not the schema
name — a model named `TeacherSummary` returned under a *student* lens is not
checked as teacher-facing; a shared model returned under two lenses is checked
under the teacher one; a route with no `response_model` is skipped safely.

### `app/contract/money_schema.py` — 10 tests

Money (5): a property `$ref`-ing the `Money` component passes; an inline
money-shaped string is reported **by property path**; a JSON **number** typed
money field is reported; a nested money property is reached; the component
itself carries the pattern.

Display pairing (5): `amount` + `amount_display` passes; `amount_display`
alone is reported **by field name**; `amount` alone passes (the display
sibling is optional); the display field is **not** pattern-matched; a nested
pairing is reached.

### `app/contract/serialize.py` — 8 tests

Canonical output is byte-stable within a process; object keys are sorted; a
`required` list built from a **set** is sorted; enum members are sorted; an
order-**sensitive** list (e.g. `servers`) is **not** reordered; the output
ends in a newline; non-ASCII is preserved (`ensure_ascii=False`); the function
is idempotent.

> The order-sensitive test is the guard against over-sorting. Sorting *every*
> list would corrupt parts of an OpenAPI document where order carries meaning.

### `app/errors/` — 14 tests

Taxonomy (6): each of the five classes maps to its documented status;
`AuthorizationError` accepts 401 and 403; a third status is a **type** error
(asserted via a mypy-run test or `typing.get_type_hints` check, not a runtime
assert).

Handler (5): `retryable` is derived from the class, never from the raise site;
the envelope carries `code`, `retryable`, `message_key`; **no `message` field
is ever emitted**; `details` is typed per code; the handler performs no I/O
(import-gate assertion).

Non-disclosure (3): the code registry contains **no pair** distinguishing
unreachable from absent; a 403 never carries `ACCESS_TOKEN_EXPIRED`; a 401
carries `retryable: false` **and** the refresh-then-replay reconciliation is
documented in the test's docstring.

### The four fixtures — 4 tests

One per gate, each asserting **which** violation was reported. A fixture that
stops failing is itself a build failure.

---

## Coverage obligations

| Module | Floor | Source |
|---|---|---|
| `app/money` | **100% branch** — unchanged | `team.md`, B1 |
| `app/errors` | 80% line | `classic` scope |
| `app/contract` | 80% line | `classic` scope |
| `app/authz` | **branch**, not line | `team.md`: lens resolution is pure branching, so line coverage on it is close to meaningless |

**No floor is weakened to make a step pass.** A gap is surfaced, not
configured away. This is a `project.md` NEVER rule, not a preference.

---

## What is explicitly not tested here

- **Lens resolution against real data** — U3's. U2 tests that a `Lens` *type*
  is correctly identified on a dependency, never that the right lens is
  produced for an account.
- **NFR14.4's structural equivalence** — U3's per BR4.4. U2 owns no lookup
  code.
- **Money arithmetic** — U1's, at 100% branch already.
- **Schemathesis** — wired at infrastructure/CI, and in any case it
  **never counts as privacy coverage**: a response wrongly declaring a profile
  field matches its own declaration perfectly.
