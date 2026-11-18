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

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final, Literal

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.authz.annotations import resolve_lens_type
from app.authz.lenses import TeacherLens
from app.contract.routes import (
    LENS_EXEMPT_AUTHENTICATED,
    PUBLIC_ROUTES,
    REVIEWER_ROUTES,
    _api_routes,
)

__all__ = [
    "ACCOUNT_PRIVATE_FIELDS",
    "FORBIDDEN_ACCOUNT_ID_FIELDS",
    "OWNER_PRIVATE_FIELDS",
    "OWN_ACCOUNT_FIELDS",
    "PUBLIC_API_EXEMPTIONS",
    "PUBLIC_FORBIDDEN_FIELDS",
    "REVIEW_FORBIDDEN_FIELDS",
    "REVIEW_RESPONSE_ROUTES",
    "STAFF_PRIVATE_FIELDS",
    "STAFF_ROUTE_PREFIX",
    "FieldViolation",
    "account_private_leaks",
    "forbidden_fields",
    "is_teacher_facing",
    "lens_types_of",
    "public_field_leaks",
    "review_field_leaks",
    "staff_field_leaks",
]

#: Fields of the owner-private ``Profile``, visible only to its own account.
#: Taken from the domain component catalogue rather than invented here.
#:
#: **Hand-maintained and matched by FIELD NAME, which is this gate's one
#: manual step** [BR3.4]. The set is deliberately NOT derived from
#: ``Profile``'s columns: deriving it would make the gate depend on the
#: ORM being imported here, and on a column never being renamed between
#: the model and a response schema that mirrors it. The cost of the
#: choice is that adding a column does not enrol it, so an unenrolled
#: field leaves the invariant passing over a field it cannot see.
#:
#: ``address`` joined in D1, in the same Unit that added the column, and
#: ``tests/privacy/test_profile_probes.py`` asserts the membership of
#: every ``Profile`` column rather than of that one name -- so the next
#: column added fails the suite instead of slipping past it. A child's
#: home address is the single most consequential disclosure available
#: in this product [TC-13].
OWNER_PRIVATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "self_name",
        "photo_ref",
        "address",
        "address_house",
        "address_road",
        "address_city",
        "address_postcode",
        # [U1: BR8.2] A child's username is the owner's alone, like a
        # profile field. This set is walked on teacher-facing routes only,
        # so :data:`ACCOUNT_PRIVATE_FIELDS` carries the same two names
        # through the every-route walk below.
        "username",
        "username_key",
    }
)

#: The account's own sign-in name and its key [U1: BR8.1, ADR-010].
#: Walked on EVERY route by :func:`account_private_leaks`, because the
#: teacher-facing walk alone would let a guardian, student, membership or
#: admin response carry a child's username with CI green. A column added
#: under a name containing ``username`` must join this set;
#: ``tests/contract/test_privacy_schema.py`` asserts it [BR8.3].
ACCOUNT_PRIVATE_FIELDS: Final[frozenset[str]] = frozenset({"username", "username_key"})

#: Account identifiers in any spelling. ADR-001's half of the invariant.
FORBIDDEN_ACCOUNT_ID_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "account_id",
        "student_account_id",
        "guardian_account_id",
        "teacher_account_id",
    }
)


#: A centre employee's own contact and address [0023]. Adults' personal
#: data that **only the centre's managers** may read, so these fields may
#: appear in a response only beneath :data:`STAFF_ROUTE_PREFIX`. Named
#: apart from the profile's address fields on purpose: reusing those
#: would have meant exempting them, weakening the profile boundary for
#: every route.
STAFF_PRIVATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "email",
        "staff_house",
        "staff_road",
        "staff_city",
        "staff_postcode",
    }
)

#: Everything a public, anonymous page must never carry: all of the sets
#: above plus contact numbers and per-person keys. ``self_name`` also sits
#: in the owner-private set and is repeated so the union reads as stated.
PUBLIC_FORBIDDEN_FIELDS: Final[frozenset[str]] = (
    OWNER_PRIVATE_FIELDS
    | FORBIDDEN_ACCOUNT_ID_FIELDS
    | STAFF_PRIVATE_FIELDS
    | frozenset(
        {
            "phone",
            "student_phone",
            "guardian_phone",
            "invited_phone",
            "collection_number",
            "display_name",
            "enrollment_id",
            "student_id",
            "self_name",
        }
    )
)

#: Everything a review response must never carry [H4]: the public set,
#: which already holds ``account_id``, ``enrollment_id`` and
#: ``display_name``, plus who wrote, replied to or decided a review, and
#: every exact time in its life. A review is shown with a tenure bucket and
#: a month; an author, a seat, a join date or a timestamp is what lets a
#: teacher who knows which family just became eligible say who wrote it.
#: ``written_by_account_id`` and ``decided_by_account_id`` are the reply's
#: writer and the moderator [F17].
REVIEW_FORBIDDEN_FIELDS: Final[frozenset[str]] = PUBLIC_FORBIDDEN_FIELDS | frozenset(
    {
        "author_account_id",
        "submitted_at",
        "approved_at",
        "edited_at",
        "decided_at",
        "joined_on",
        "written_by_account_id",
        "decided_by_account_id",
    }
)

#: The routes whose responses :func:`review_field_leaks` walks: the
#: reviewer's three, the teacher's three and the reviewable list.
REVIEW_RESPONSE_ROUTES: Final[frozenset[tuple[str, str]]] = REVIEWER_ROUTES | frozenset(
    {
        ("GET", "/v1/hub/reviews"),
        ("PUT", "/v1/hub/reviews/{review_id}/reply"),
        ("DELETE", "/v1/hub/reviews/{review_id}/reply"),
        ("GET", "/v1/hub/reviewable"),
    }
)

#: The manager-only staff console, the one place staff fields are served.
STAFF_ROUTE_PREFIX: Final = "/v1/centre/staff"

#: A field that shares a staff-private NAME but is the reader's own data
#: [0032], as ``(component, field)``. ``MeResponse.email`` is the email
#: address the account signs in with, served only to that account by the
#: lens-exempt ``/v1/me`` routes -- the same standing as its ``phone``.
#: Named pair by pair, never by field name alone, so a staff member's
#: ``email`` reaching any other schema still fails the gate.
#:
#: The two username pairs [U1: BR8.2] are the owner reading their own
#: name. For them the pair is not enough on its own: the route must also
#: be lens-exempt (:func:`account_private_leaks`), so ``MeResponse``
#: reused on a non-owner route still fails. ``username_key`` has no pair
#: and is served nowhere.
OWN_ACCOUNT_FIELDS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("MeResponse", "email"),
        ("MeResponse", "username"),
        ("UsernameChangeResponse", "username"),
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
    classify: Callable[[str], object | None] = _classify,
) -> list[tuple[str, str]]:
    """Collect forbidden field names reachable from a schema.

    Recurses through ``$ref``, ``items``, ``allOf``, ``anyOf`` and
    ``oneOf``. The ``seen`` set is a **cycle guard**: a self-referential
    ``$ref`` graph would otherwise recurse forever, and an unguarded walk
    hangs CI rather than failing it.

    :param schema: The schema node to walk
    :param definitions: The document's component schemas, for ``$ref``
    :param seen: Component names already visited on this path
    :param classify: Which field names count as forbidden
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
            return _walk(target, definitions, seen | {name}, classify)
        return found

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for field, child in properties.items():
            classification = classify(str(field))
            if classification is not None:
                found.append((schema.get("title", "?"), str(field)))  # type: ignore[arg-type]
            if isinstance(child, dict):
                found.extend(_walk(child, definitions, seen, classify))

    items = schema.get("items")
    if isinstance(items, dict):
        found.extend(_walk(items, definitions, seen, classify))

    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict):
                    found.extend(_walk(branch, definitions, seen, classify))

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

    # _api_routes, never app.routes. In this FastAPI version an included
    # router appears as an opaque wrapper, so `isinstance(route,
    # APIRoute)` over app.routes matches NOTHING -- and this gate, which
    # enforces project.md's NEVER rule that no teacher-lens response
    # carries a profile field, reported clean while checking zero routes.
    #
    # The route gate had the identical defect and was fixed first. This
    # one was found by asking what else enumerated routes the same way,
    # which is the sweep that should have followed that fix immediately.
    for route in _api_routes(app):
        if route.response_model is None:
            continue
        if not is_teacher_facing(route):
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


def _staff_field(field: str) -> str | None:
    """Report whether a field name is staff-private.

    :param field: The field name
    :return: The name when it is staff-private, else None
    """
    return field if field in STAFF_PRIVATE_FIELDS else None


def staff_field_leaks(app: FastAPI) -> list[tuple[str, str, str]]:
    """List staff-private fields served anywhere but the staff console.

    **Every route, whatever its lens**, not only teacher-facing ones: a
    staff member's address must not reach a family, a centre teacher or
    the account's own reader by way of a schema reused elsewhere.

    :param app: The application whose generated schema is checked
    :return: ``(path, component, field)`` per leak, empty when clean
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )
    leaks: list[tuple[str, str, str]] = []
    for route in _api_routes(app):
        if route.response_model is None or route.path.startswith(STAFF_ROUTE_PREFIX):
            continue
        name = getattr(route.response_model, "__name__", "?")
        component = definitions.get(name)
        if component is None:
            continue
        for schema_name, field in _walk(component, definitions, {name}, _staff_field):
            if (str(schema_name), field) in OWN_ACCOUNT_FIELDS:
                continue
            leaks.append((route.path, str(schema_name), field))
    return leaks


def _account_private_field(field: str) -> str | None:
    """Report whether a field name is an account's own username field.

    :param field: The field name
    :return: The name when it is account-private, else None
    """
    return field if field in ACCOUNT_PRIVATE_FIELDS else None


def account_private_leaks(app: FastAPI) -> list[tuple[str, str, str, str]]:
    """List every username field served anywhere but to its owner.

    [U1: BR8.1, BR8.2, NFR3.1] **Every route, whatever its lens**, shaped
    like the staff-field walk. A field named ``username`` or
    ``username_key`` is a leak unless its (schema, field) pair is in
    :data:`OWN_ACCOUNT_FIELDS` AND every method of the route is in
    ``LENS_EXEMPT_AUTHENTICATED`` -- the routes that act on the
    authenticated account alone. ``username_key`` has no pair, so it
    leaks everywhere.

    :param app: The application whose generated schema is checked
    :return: ``(method, path, component, field)`` per leak, empty when clean
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )
    leaks: list[tuple[str, str, str, str]] = []
    for route in _api_routes(app):
        if route.response_model is None:
            continue
        name = getattr(route.response_model, "__name__", "?")
        component = definitions.get(name)
        if component is None:
            continue
        found = _walk(component, definitions, {name}, _account_private_field)
        for method in sorted(route.methods or set()):
            owners_route = (method, route.path) in LENS_EXEMPT_AUTHENTICATED
            for schema_name, field in found:
                if owners_route and (str(schema_name), field) in OWN_ACCOUNT_FIELDS:
                    continue
                leaks.append((method, route.path, str(schema_name), field))
    return leaks


def lens_types_of(route: APIRoute) -> set[type]:
    """Collect **every** lens type a route's dependency tree yields.

    **Returns a set, not the first match, and that distinction is a
    privacy control rather than a refinement.** A route may legitimately
    depend on two lenses as independent ``Depends()`` parameters -- a
    teacher lens and a guardian lens, say. An earlier version walked the
    tree and returned whichever it popped first, so a teacher-facing
    response could be classified as guardian-facing and skip this gate
    entirely while :func:`app.contract.routes.unlensed_routes` correctly
    reported the route as lensed. Nothing fired. That is exactly the
    silent-authorization-hole class the gates exist to make impossible.

    The route gate is unaffected by the same traversal, because it asks
    "is there ANY lens" -- a question the first match answers correctly.
    This gate asks "is this teacher-facing", which it does not.

    Shares :func:`app.authz.annotations.resolve_lens_type` with the route
    gate: one function, two callers, because a second implementation would
    almost certainly be the naive ``issubclass`` the requirement forbids.

    :param route: The route to inspect
    :return: Every lens type the tree yields, empty when it yields none
    """
    found: set[type] = set()
    stack = [route.dependant]
    while stack:
        node = stack.pop()
        if node.call is not None:
            lens = resolve_lens_type(node.call)
            if lens is not None:
                found.add(lens)
        stack.extend(node.dependencies)
    return found


def is_teacher_facing(route: APIRoute) -> bool:
    """Report whether a route can produce a teacher-lens response.

    True when **any** lens in the tree is a teacher lens. A route reachable
    under both a teacher and a guardian lens is teacher-facing, because a
    teacher can reach it -- which is the only question this gate asks.

    :param route: The route to inspect
    :return: True if any resolved lens is a teacher lens
    """
    return any(
        isinstance(lens, type) and issubclass(lens, TeacherLens)
        for lens in lens_types_of(route)
    )


#: Existing unauthenticated API responses whose forbidden-NAME field is
#: not a disclosure, as ``(path, component, field)``. Named exactly, never
#: by field name alone, so the same field on any other public route or view
#: model still fails. ``SignupResponse.account_id`` is the id of the
#: account the caller has just created, returned to that caller only;
#: ``AlreadyAddedResponse.display_name`` is a deprecated field that is
#: always empty or None and never a name (see its docstring).
PUBLIC_API_EXEMPTIONS: Final[frozenset[tuple[str, str, str]]] = frozenset(
    {
        ("/v1/accounts", "SignupResponse", "account_id"),
        ("/v1/accounts/already-added", "AlreadyAddedResponse", "display_name"),
    }
)


def _public_field(field: str) -> str | None:
    """Report whether a field name is forbidden on a public surface.

    :param field: The field name
    :return: The name when it is forbidden, else None
    """
    return field if field in PUBLIC_FORBIDDEN_FIELDS else None


def _response_schema(
    document: dict[str, object], path: str, method: str
) -> dict[str, object]:
    """Resolve a route's 2xx JSON response schema from the OpenAPI document.

    Read from the operation itself rather than from the response model's
    class name, which is absent for ``list[X]`` and may differ from the
    component name. Fails closed: a declared response model whose schema
    cannot be found is an error, never a pass.

    :param document: The generated OpenAPI document
    :param path: The route path
    :param method: The HTTP method
    :return: The response schema node
    :raises LookupError: When no 2xx JSON schema can be resolved
    """
    paths = document.get("paths", {})
    operation = paths.get(path, {}).get(method.lower(), {})  # type: ignore[attr-defined]
    for status, response in (operation.get("responses", {}) or {}).items():
        if not str(status).startswith("2") or not isinstance(response, dict):
            continue
        content = (response.get("content", {}) or {}).get("application/json", {})
        schema = content.get("schema")
        if isinstance(schema, dict) and schema:
            return schema
    msg = f"public route {method} {path} has no resolvable response schema"
    raise LookupError(msg)


def public_field_leaks(
    app: FastAPI, view_models: Iterable[type[BaseModel]]
) -> list[tuple[str, str, str]]:
    """List forbidden fields reachable from anything the public can read.

    Two sources: the response schema of every route in
    :data:`app.contract.routes.PUBLIC_ROUTES`, and the schema of every
    registered public view model.

    :param app: The application whose generated schema is checked
    :param view_models: The registered public view models
    :return: ``(origin, component, field)`` per leak, empty when clean
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )
    leaks: list[tuple[str, str, str]] = []
    for route in _api_routes(app):
        if route.response_model is None:
            continue
        if not any((m, route.path) in PUBLIC_ROUTES for m in route.methods or ()):
            continue
        for method in sorted(
            m for m in route.methods or () if (m, route.path) in PUBLIC_ROUTES
        ):
            resolved = _response_schema(document, route.path, method)
            for schema_name, field in _walk(
                resolved, definitions, set(), _public_field
            ):
                if (route.path, str(schema_name), field) in PUBLIC_API_EXEMPTIONS:
                    continue
                leaks.append((f"route:{route.path}", str(schema_name), field))
    for model in view_models:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        view_defs: dict[str, dict[str, object]] = schema.get("$defs", {}) or {}
        for schema_name, field in _walk(
            schema, view_defs, {model.__name__}, _public_field
        ):
            leaks.append((f"view:{model.__name__}", str(schema_name), field))
    return leaks


def _review_field(field: str) -> str | None:
    """Report whether a field name is forbidden on a review response.

    :param field: The field name
    :return: The name when it is forbidden, else None
    """
    return field if field in REVIEW_FORBIDDEN_FIELDS else None


def review_field_leaks(app: FastAPI) -> list[tuple[str, str, str]]:
    """List forbidden fields reachable from any review route's response.

    Walks the 2xx response of every route in :data:`REVIEW_RESPONSE_ROUTES`
    the application registers; a route answering 204 has no body to walk.
    A listed route declaring a response model whose schema cannot be found
    fails closed, as the public walk does.

    :param app: The application whose generated schema is checked
    :return: ``(method path, component, field)`` per leak, empty when clean
    """
    document = app.openapi()
    definitions: dict[str, dict[str, object]] = (
        document.get("components", {}).get("schemas", {}) or {}
    )
    leaks: list[tuple[str, str, str]] = []
    for route in _api_routes(app):
        if route.response_model is None:
            continue
        for method in sorted(route.methods or ()):
            if (method, route.path) not in REVIEW_RESPONSE_ROUTES:
                continue
            resolved = _response_schema(document, route.path, method)
            for schema_name, field in _walk(
                resolved, definitions, set(), _review_field
            ):
                leaks.append((f"{method} {route.path}", str(schema_name), field))
    return leaks
