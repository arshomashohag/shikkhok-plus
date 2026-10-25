"""The collection-number allowlist: exactly one response carries it.

**An allowlist, not a denylist, and the direction is the whole point**
[BR6.4, NFR14.32]. A denylist entry would say "no teacher-facing
response carries this field", which is backwards: the number is the
teacher's own and a teacher may see it. The property worth holding is
*exactly one response carries it*, and only an allowlist expresses that.

**The built schema-wide privacy gate is silent on this, not satisfied by
it.** ``app.contract.privacy`` asserts that no TEACHER-facing response
declares an owner-private profile field or a global account id. The
collection number is neither: it is teacher-authored, deliberately
disclosed *downward* to students and guardians enrolled in that batch,
and bounded rather than forbidden. That is a different question about a
different direction, so it needs its own mechanism.

**An equality against a one-element set, not a membership test.** A
membership test passes the moment the field spreads to a second
response -- a batch listing, a roster row, a fee-cycle collection -- and
NFR14.33's "never in a listing" falls straight out of the equality
instead of needing its own assertion.

Written in the same iterating shape as the built gates, so it covers the
route added three units later rather than the routes somebody remembered.
"""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI

from app.contract.routes import _api_routes

__all__ = [
    "COLLECTION_NUMBER_FIELD",
    "DOWNWARD_ROUTES",
    "PERMITTED_ROUTES",
    "collection_number_routes",
]

#: The field name this gate tracks.
COLLECTION_NUMBER_FIELD: Final = "collection_number"

#: The routes permitted to carry it, and **exactly three**. An equality
#: against this set is what the gate asserts, so a fourth entry is a
#: deliberate diff against a stated allowlist rather than a line
#: appended to a growing one.
#:
#: **The security design predicted one and the built application has
#: three, and the difference is not a weakening.** That document was
#: written against a schema in which D2's batch routes did not yet
#: exist; its single entry is the DOWNWARD disclosure -- the one
#: response that shows a teacher's number to somebody who is not that
#: teacher. The other two are the teacher reading and writing **their
#: own** number on **their own** batch, which discloses it to nobody.
#: Recorded here rather than silently widened, because a reader meeting
#: the design's `== {one route}` and this set needs to know which is
#: current and why.
#:
#: The distinction the gate cannot make on its own is therefore made
#: here, and the test makes it mechanical: the downward route is
#: asserted to resolve NO teacher lens, and the two batch routes are
#: asserted to resolve ONLY a teacher lens. A fourth route carrying the
#: field fails the equality whichever direction it faces.
PERMITTED_ROUTES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        # Downward: a student or guardian reads where to pay [BR6.4].
        ("GET", "/v1/enrollments/{enrollment_id}/payment-destination"),
        # The teacher's own batch, read and written by its owner.
        ("GET", "/v1/batches"),
        ("POST", "/v1/batches"),
    }
)

#: Of those, the one that discloses the number DOWNWARD -- to a reader
#: who is not the teacher who authored it. This is the entry the
#: security design named, and the one whose lens must not be a teacher's.
DOWNWARD_ROUTES: Final[frozenset[tuple[str, str]]] = frozenset(
    {("GET", "/v1/enrollments/{enrollment_id}/payment-destination")}
)


def collection_number_routes(app: FastAPI) -> set[tuple[str, str]]:
    """List every route whose response schema reaches the field.

    Takes the application as an argument so a violation fixture and the
    real gate call one function rather than two implementations that
    drift apart silently -- the same reasoning the built route and
    privacy gates use.

    Walks ``$ref``, ``items`` and the composition keywords through the
    shared traversal, so a field nested inside an embedded object or a
    list is found rather than only a top-level one.

    :param app: The application whose generated schema is checked
    :return: One ``(method, path)`` pair per route reaching the field
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )

    reaching: set[tuple[str, str]] = set()

    for route in _api_routes(app):
        if route.response_model is None:
            continue
        name = getattr(route.response_model, "__name__", None)
        component = definitions.get(name) if name else None
        if component is None:
            # An inline or union response model -- walk the declared
            # schema from the document instead, so a response typed
            # `X | None` is not silently skipped.
            component = _response_schema(document, route.path, route.methods)
        if component is None:
            continue

        if _declares(component, definitions, set()):
            for method in sorted(route.methods or set()):
                reaching.add((method, route.path))

    return reaching


def _response_schema(
    document: dict[str, object],
    path: str,
    methods: set[str] | None,
) -> dict[str, object] | None:
    """Read a route's declared 200 response schema from the document.

    :param document: The generated OpenAPI document
    :param path: The route path
    :param methods: The route's methods
    :return: The response schema node, or None
    """
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return None
    entry = paths.get(path)
    if not isinstance(entry, dict):
        return None
    for method in sorted(methods or set()):
        operation = entry.get(method.lower())
        if not isinstance(operation, dict):
            continue
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            continue
        for status in ("200", "201"):
            ok = responses.get(status)
            if not isinstance(ok, dict):
                continue
            content = ok.get("content")
            if not isinstance(content, dict):
                continue
            body = content.get("application/json")
            if isinstance(body, dict):
                schema = body.get("schema")
                if isinstance(schema, dict):
                    return schema
    return None


def _declares(
    schema: dict[str, object],
    definitions: dict[str, dict[str, object]],
    seen: set[str],
) -> bool:
    """Report whether the field is reachable from this schema node.

    Its own traversal rather than the privacy gate's, because that one
    reports only names in its two forbidden sets and the collection
    number is in neither -- it is a *permitted* field whose spread is
    what this gate bounds. The traversal shape is deliberately the
    same, including the ``seen`` cycle guard: an unguarded walk over a
    self-referential ``$ref`` graph hangs CI rather than failing it.

    :param schema: The schema node to walk
    :param definitions: The document's component schemas
    :param seen: Component names already visited, as a cycle guard
    :return: True if the field is reachable
    """
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            return False
        target = definitions.get(name)
        return (
            False if target is None else _declares(target, definitions, seen | {name})
        )

    properties = schema.get("properties")
    if isinstance(properties, dict):
        if COLLECTION_NUMBER_FIELD in properties:
            return True
        for child in properties.values():
            if isinstance(child, dict) and _declares(child, definitions, seen):
                return True

    items = schema.get("items")
    if isinstance(items, dict) and _declares(items, definitions, seen):
        return True

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict) and _declares(branch, definitions, seen):
                    return True

    return False
