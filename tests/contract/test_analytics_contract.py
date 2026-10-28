"""D5's three schema-level obligations, over the generated document.

**The empty-parameter-list assertion is this unit's no-id property made
checkable** [security-design § 1]. An earlier draft of the design said
"no parameter **naming a resource**", which is weaker in the way that
matters: whether a name denotes a resource is a judgement and a test
cannot make it. These two operations take **no parameters at all**, so
the assertion is a plain predicate and fails the day someone adds
``?batch_id=``, whatever they call it.

**The ``/me/`` prefix does not imply it.** Checked against the built
routes: ``GET /v1/me/fees`` carries a ``StudentLens`` **and** an
``enrollment_id`` query parameter. The prefix means "scoped to the
caller", not "takes no id" -- which is why this assertion is
load-bearing rather than a restatement of a convention. A later
``/v1/me/dues?batch_id=`` would be perfectly conventional and would
reintroduce the IDOR class the design removes.
"""

from __future__ import annotations

from typing import Final

from app.contract.routes import PUBLIC_ROUTES
from app.main import app as real_app

#: The two operations D5 adds, which take no input of any kind.
D5_OPERATIONS: Final[tuple[tuple[str, str], ...]] = (
    ("get", "/v1/me/dues"),
    ("get", "/v1/me/overview"),
)


def _document() -> dict[str, object]:
    """Return the generated OpenAPI document.

    :return: The document
    """
    return real_app.openapi()


def test_both_new_operations_declare_an_empty_parameter_list() -> None:
    """Neither route takes a path or query parameter [NFR14.65].

    A plain predicate over the generated document rather than a
    judgement about whether a name denotes a resource.

    :return: None
    """
    paths: dict[str, dict[str, dict[str, object]]] = _document()["paths"]  # type: ignore[assignment]

    for method, path in D5_OPERATIONS:
        assert path in paths, f"{path} is not in the generated document"
        operation = paths[path][method]
        parameters = operation.get("parameters", [])
        assert parameters == [], (
            f"{method.upper()} {path} declares parameters {parameters}. "
            "D5's reads take NO resource id, which is what removes the "
            "IDOR class from this unit entirely [security-design § 1]. "
            "The /me/ prefix does not imply this: GET /v1/me/fees "
            "carries an enrollment_id query parameter."
        )


def test_the_me_prefix_does_not_imply_the_property_being_asserted() -> None:
    """The counter-example, asserted so the test above is not circular.

    If every ``/v1/me/*`` route happened to take no parameters, the
    assertion above would be a restatement of a convention rather than a
    property of these two routes. ``GET /v1/me/fees`` takes one, so it
    is not.

    :return: None
    """
    paths: dict[str, dict[str, dict[str, object]]] = _document()["paths"]  # type: ignore[assignment]

    fees = paths["/v1/me/fees"]["get"]
    parameters = fees.get("parameters", [])

    assert parameters != [], (
        "GET /v1/me/fees no longer takes a parameter, so the empty-list "
        "assertion above has become a statement about the /me/ prefix "
        "rather than about D5's two routes. Find another counter-example "
        "or state the property differently."
    )


def test_the_generated_document_carries_no_collection_rate_field() -> None:
    """OQ-2 is open, so the field does not ship [BR4.1].

    A field is additive under ``/v1/``; a wrong number pinned into an
    installed client cannot be withdrawn. Asserted over the **whole
    serialized document** rather than over D5's own schemas, because the
    rule is that nothing ships it anywhere.

    :return: None
    """
    import json

    document = json.dumps(_document())

    assert "collection_rate" not in document, (
        "a collection_rate field reached the generated contract while "
        "OQ-2 is open [BR4.1]. What is open is narrow -- FR8.3's "
        "definition is annotated open to correction and AC8.3.4's credit "
        "rule postdates it -- and it is the human's to close."
    )
    assert "collectionRate" not in document


def test_public_routes_still_holds_exactly_eight() -> None:
    """D5 adds nothing unauthenticated [BR4.4].

    The count is asserted in ``tests/contract/test_route_lenses.py``
    too; this is the second of the two places the number is pinned, and
    it is here so a D5 reader meets the obligation in D5's own file.

    :return: None
    """
    assert len(PUBLIC_ROUTES) == 8
    assert ("GET", "/v1/me/dues") not in PUBLIC_ROUTES
    assert ("GET", "/v1/me/overview") not in PUBLIC_ROUTES


def test_both_new_routes_resolve_a_teacher_lens() -> None:
    """Every route in this unit names its lens [BR4.4].

    Matched on the dependency's **return annotation** being a
    ``TeacherLens``, through the built gate, rather than on a function
    name.

    :return: None
    """
    from app.authz.lenses import TeacherLens
    from app.contract.privacy import lens_types_of
    from app.contract.routes import _api_routes

    by_path = {route.path: route for route in _api_routes(real_app)}

    for _, path in D5_OPERATIONS:
        lenses = lens_types_of(by_path[path])
        assert lenses == {TeacherLens}, (
            f"{path} resolves {lenses}, not exactly a teacher lens. "
            "Nothing in this unit is reachable by a student or guardian "
            "lens [functional-spec § 5]."
        )


def test_the_dues_route_is_visible_to_the_privacy_gate() -> None:
    """A bare ``list[X]`` response model would be skipped entirely.

    ``app/contract/privacy.py`` finds a route's response component by
    ``route.response_model.__name__``, which for ``list[X]`` is
    ``"list"`` and matches no component -- so a bare-list route is
    **not checked** by the schema-wide privacy gate.

    **A dues list is a list of people**, which makes it the natural
    place to leak a student's self-authored name to a teacher, so it is
    the one response in the product that most needs that gate to see it.
    Hence the ``DuesResponse`` wrapper, asserted here rather than left
    as a style note.

    :return: None
    """
    from app.contract.privacy import is_teacher_facing
    from app.contract.routes import _api_routes

    by_path = {route.path: route for route in _api_routes(real_app)}
    route = by_path["/v1/me/dues"]

    assert route.response_model is not None
    name = getattr(route.response_model, "__name__", "?")
    assert name == "DuesResponse", (
        f"the dues route's response model is {name!r}. A bare list[X] "
        "names 'list', which matches no component, so the privacy gate "
        "skips the route silently."
    )
    assert is_teacher_facing(route)

    schemas = _document()["components"]["schemas"]  # type: ignore[index]
    assert "DuesResponse" in schemas
    assert "DuesRowResponse" in schemas


def test_no_d5_response_schema_carries_an_account_id() -> None:
    """The built gate's own subject, asserted on D5's schemas directly.

    The schema-wide gate covers this already. Stated here as well
    because it is the half a reader of D5 would look for, and because an
    assertion over the named components fails with a clearer message
    than a whole-document one.

    :return: None
    """
    from app.contract.privacy import (
        FORBIDDEN_ACCOUNT_ID_FIELDS,
        OWNER_PRIVATE_FIELDS,
    )

    schemas: dict[str, dict[str, object]] = _document()["components"]["schemas"]  # type: ignore[index,assignment]
    forbidden = FORBIDDEN_ACCOUNT_ID_FIELDS | OWNER_PRIVATE_FIELDS

    for name in (
        "DuesResponse",
        "DuesRowResponse",
        "MonthlyEarningsResponse",
        "NextExamResponse",
        "OverviewResponse",
    ):
        properties = schemas[name].get("properties", {})
        assert isinstance(properties, dict)
        offending = set(properties) & forbidden
        assert offending == set(), f"{name} declares {sorted(offending)}"


def test_d5_adds_no_migration_and_no_governance_entry() -> None:
    """No table, no column, no revision [BR4.2].

    ``dispositions.py`` held 25 when D5 shipped and holds 26 since
    ``notification`` arrived with the inbox; D5 itself added none.
    Stated as an absence because a
    materialised rollup is the obvious optimisation and it would
    contradict BR1.4 outright.

    :return: None
    """
    from app.governance.dispositions import DISPOSITIONS

    assert len(DISPOSITIONS) == 26, (
        f"the governance manifest holds {len(DISPOSITIONS)} entries, not "
        "26. D5 creates no table, so it adds no disposition [BR4.2]."
    )


def test_d5_registers_no_job_and_no_heartbeat() -> None:
    """No cron entry, no ``stamp_heartbeat`` call [NFR25.28].

    D5's figures are computed on open, so there is nothing to schedule
    and nothing to stamp -- and a unit with no job needs no wiring into
    the freshness check.

    :return: None
    """
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[2] / "app" / "analytics"
    sources = "\n".join(path.read_text() for path in package.glob("*.py"))

    assert "stamp_heartbeat" not in sources
    assert "job_heartbeat" not in sources
