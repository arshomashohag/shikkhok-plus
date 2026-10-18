"""The schema-wide privacy gate.

**Two forbidden field sets, one iteration** [NFR14.8, BR2.4]:

* **Owner-private profile fields** -- what a student or guardian writes
  about themselves. ``Profile`` belongs to exactly one ``Account`` and is
  visible only to its owner, so no teacher-facing response may carry one
  [TC-13, D-5].
* **Account identifiers** -- a *global* key. A teacher-facing response
  exposes an enrollment id and never ``student_account_id``, because the
  latter hands teacher A a stable handle on a student also enrolled with
  teacher B [ADR-001].

**Iteration, not enumeration.** A per-endpoint test covers the endpoints
someone remembered; walking the generated document covers the endpoint
added three Units later, after everyone stopped thinking about it.

**The lens is read from the route, never guessed from the schema name.**
Three alternatives were rejected, each of which fails quietly: matching
schema names containing "Teacher" is defeated by a rename and blind to a
shared model returned under two lenses; checking only top-level properties
misses a field nested in an embedded object, which is the likely shape;
and checking a schema in isolation cannot know the lens at all, because a
model is teacher-facing only by virtue of some route returning it under a
teacher lens. That fact lives on the route.

**This is the assertion a conformance tool cannot make.** A response
wrongly declaring a profile field matches its own declaration perfectly, so
Schemathesis passes it and the pass is evidence of nothing about privacy
[NFR14.9, BR4.2].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.authz.annotations import resolve_lens_type
from app.authz.lenses import TeacherLens

__all__ = [
    "FORBIDDEN_ACCOUNT_ID_FIELDS",
    "OWNER_PRIVATE_FIELDS",
    "FieldViolation",
    "forbidden_fields",
]

#: Fields of the owner-private ``Profile``, visible only to its own account.
#: Taken from the domain component catalogue rather than invented here.
OWNER_PRIVATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "self_name",
        "photo_ref",
    }
)

#: Account identifiers in any spelling. ADR-001's half of the invariant.
FORBIDDEN_ACCOUNT_ID_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "account_id",
        "student_account_id",
        "guardian_account_id",
        "teacher_account_id",
    }
)


@dataclass(frozen=True, slots=True)
class FieldViolation:
    """A forbidden field found in a teacher-facing response schema.

    :ivar path: The route whose response declares it
    :ivar schema: The schema component the field was found in
    :ivar field: The offending field name
    :ivar field_set: Which forbidden set it belongs to
    """

    path: str
    schema: str
    field: str
    field_set: Literal["owner-private", "account-id"]


def _classify(field: str) -> Literal["owner-private", "account-id"] | None:
    """Report which forbidden set a field name belongs to, if any.

    :param field: The field name to classify
    :return: The set name, or None when the field is permitted
    """
    if field in OWNER_PRIVATE_FIELDS:
        return "owner-private"
    if field in FORBIDDEN_ACCOUNT_ID_FIELDS:
        return "account-id"
    return None


def _walk(
    schema: dict[str, object],
    definitions: dict[str, dict[str, object]],
    seen: set[str],
) -> list[tuple[str, str]]:
    """Collect forbidden field names reachable from a schema.

    Recurses through ``$ref``, ``items``, ``allOf``, ``anyOf`` and
    ``oneOf``. The ``seen`` set is a **cycle guard**: a self-referential
    ``$ref`` graph would otherwise recurse forever, and an unguarded walk
    hangs CI rather than failing it.

    :param schema: The schema node to walk
    :param definitions: The document's component schemas, for ``$ref``
    :param seen: Component names already visited on this path
    :return: One ``(component, field)`` pair per forbidden field found
    """
    found: list[tuple[str, str]] = []

    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            return found
        target = definitions.get(name)
        if target is not None:
            return _walk(target, definitions, seen | {name})
        return found

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for field, child in properties.items():
            classification = _classify(str(field))
            if classification is not None:
                found.append((schema.get("title", "?"), str(field)))  # type: ignore[arg-type]
            if isinstance(child, dict):
                found.extend(_walk(child, definitions, seen))

    items = schema.get("items")
    if isinstance(items, dict):
        found.extend(_walk(items, definitions, seen))

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict):
                    found.extend(_walk(branch, definitions, seen))

    return found


def forbidden_fields(app: FastAPI) -> list[FieldViolation]:
    """List every forbidden field in a teacher-facing response schema.

    Takes the application as an argument so the committed violation fixture
    and the real gate call one function rather than two implementations
    that drift apart silently.

    :param app: The application whose generated schema is checked
    :return: One entry per violation, empty when the schema is clean
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )

    violations: list[FieldViolation] = []

    for route in app.routes:
        if not isinstance(route, APIRoute) or route.response_model is None:
            continue
        if resolve_lens_type_of(route) is not TeacherLens:
            continue

        name = getattr(route.response_model, "__name__", "?")
        component = definitions.get(name)
        if component is None:
            continue

        for schema_name, field in _walk(component, definitions, {name}):
            classification = _classify(field)
            if classification is None:  # pragma: no cover - _walk filters
                continue
            violations.append(
                FieldViolation(
                    path=route.path,
                    schema=str(schema_name),
                    field=field,
                    field_set=classification,
                )
            )

    return violations


def resolve_lens_type_of(route: APIRoute) -> type | None:
    """Resolve the lens a route's dependency tree yields.

    Shares :func:`app.authz.annotations.resolve_lens_type` with the
    route-enumeration gate: one function, two callers, because a second
    implementation would almost certainly be the naive ``issubclass`` the
    requirement exists to forbid.

    :param route: The route to inspect
    :return: The lens type, or None when the route resolves none
    """
    stack = [route.dependant]
    while stack:
        node = stack.pop()
        if node.call is not None:
            lens = resolve_lens_type(node.call)
            if lens is not None:
                return lens
        stack.extend(node.dependencies)
    return None
