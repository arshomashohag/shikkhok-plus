"""The collection number appears in exactly one response [BR6.4].

**The direction the built privacy gate does not check.** That gate
asserts no TEACHER-facing response carries an owner-private profile
field or a global account id. The collection number is neither: it is
teacher-authored and deliberately disclosed *downward* to the students
and guardians who need it in order to pay. So the question here is not
"may a teacher see it" -- they may, it is theirs -- but "does it reach
anybody else", and that needs its own mechanism.

**An equality, not a membership test.** A membership test passes the
moment the field spreads to a second response, which is exactly the
failure NFR14.33 names: it must appear in no listing and no search, and
that falls out of the equality rather than needing a separate assertion.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.authz.lenses import StudentLens, TeacherLens
from app.contract.collection_number import (
    DOWNWARD_ROUTES,
    PERMITTED_ROUTES,
    collection_number_routes,
)
from app.main import create_app


def _student_lens() -> StudentLens:
    """Stand in for the student-lens resolver.

    :return: A student lens
    """
    from uuid import uuid4

    return StudentLens(account_id=uuid4())


def _teacher_lens() -> TeacherLens:
    """Stand in for the teacher-lens resolver.

    :return: A teacher lens
    """
    from uuid import uuid4

    return TeacherLens(account_id=uuid4(), owner_id=uuid4())


def test_exactly_the_allowlisted_routes_carry_the_collection_number() -> None:
    # An EQUALITY. A membership test passes the moment the field
    # spreads to another response, and NFR14.33's "never in a listing"
    # falls out of this rather than needing its own assertion.
    assert collection_number_routes(create_app()) == set(PERMITTED_ROUTES)


def test_the_downward_route_resolves_no_teacher_lens() -> None:
    # The allowlist alone cannot tell a downward disclosure from a
    # teacher reading their own field, so the distinction is asserted
    # here. A payment-destination route reachable under a teacher lens
    # would satisfy the equality while meaning something different.
    from app.contract.privacy import lens_types_of
    from app.contract.routes import _api_routes

    app = create_app()
    checked: set[tuple[str, str]] = set()

    for route in _api_routes(app):
        for method in sorted(route.methods or set()):
            if (method, route.path) not in DOWNWARD_ROUTES:
                continue
            checked.add((method, route.path))
            lenses = lens_types_of(route)
            assert lenses, f"{method} {route.path} resolves no lens at all"
            assert not any(
                isinstance(lens, type) and issubclass(lens, TeacherLens)
                for lens in lenses
            ), (
                f"{method} {route.path} is reachable under a teacher lens. "
                "The destination route exists so a STUDENT or GUARDIAN can "
                "pay; a teacher reads their own number on their own batch."
            )

    # Not vacuous: every declared downward route was actually found and
    # checked, so a renamed path cannot empty this test silently.
    assert checked == set(DOWNWARD_ROUTES)


def test_every_non_downward_permitted_route_is_the_teachers_own() -> None:
    # The other direction of the same distinction. These routes carry
    # the number because it belongs to the caller; if one stopped
    # requiring a teacher lens, it would have become a disclosure
    # without anybody editing the allowlist.
    from app.contract.privacy import lens_types_of
    from app.contract.routes import _api_routes

    app = create_app()
    owner_routes = set(PERMITTED_ROUTES) - set(DOWNWARD_ROUTES)
    checked: set[tuple[str, str]] = set()

    for route in _api_routes(app):
        for method in sorted(route.methods or set()):
            if (method, route.path) not in owner_routes:
                continue
            checked.add((method, route.path))
            lenses = lens_types_of(route)
            assert lenses and all(
                isinstance(lens, type) and issubclass(lens, TeacherLens)
                for lens in lenses
            ), (
                f"{method} {route.path} carries the collection number and "
                "is reachable by something other than its owner"
            )

    assert checked == owner_routes


# --------------------------------------------------------------------------
# The fixture that proves the gate can fire.
#
# Without it, a gate reporting "no violations" is indistinguishable from
# a gate that checks nothing -- which this project has now found twice,
# in the route gate and in the privacy gate, both of which passed over
# zero routes.
# --------------------------------------------------------------------------


class _LeakyRosterRow(BaseModel):
    """A roster row that wrongly carries the teacher's payment number.

    :ivar enrollment_id: The seat
    :ivar collection_number: The field that must not be here
    """

    enrollment_id: str
    collection_number: str


def test_the_gate_fires_on_a_second_route_carrying_the_field() -> None:
    app = FastAPI()
    app.state.included_routers = []

    @app.get("/v1/leaky-roster", response_model=list[_LeakyRosterRow])
    def leaky(lens: StudentLens = Depends(_student_lens)) -> list[_LeakyRosterRow]:
        """Return a roster row carrying the number.

        :param lens: The student lens
        :return: The leaky rows
        """
        return []

    found = collection_number_routes(app)

    assert ("GET", "/v1/leaky-roster") in found, (
        "the gate did not see a response declaring collection_number; it "
        "would report clean over a real leak"
    )


def test_the_gate_sees_the_field_nested_in_an_embedded_object() -> None:
    # The likely shape of a real leak is not a top-level field: it is a
    # batch summary embedded in a roster row. A gate checking only
    # top-level properties reports clean over it.
    class _Destination(BaseModel):
        collection_number: str

    class _Wrapper(BaseModel):
        batch: _Destination

    app = FastAPI()
    app.state.included_routers = []

    @app.get("/v1/nested", response_model=_Wrapper)
    def nested(lens: StudentLens = Depends(_student_lens)) -> _Wrapper:
        """Return a nested destination.

        :param lens: The student lens
        :return: The wrapper
        """
        return _Wrapper(batch=_Destination(collection_number="x"))

    assert ("GET", "/v1/nested") in collection_number_routes(app)


def test_the_injection_is_now_redundant() -> None:
    """The shared-component stopgap in `main.py` is a no-op at D3.

    It was added at U3 because no route referenced ``Money`` or
    ``ErrorEnvelope``, so neither reached the committed contract and
    the diff gate passed over their absence. Its own docstring said it
    "stays until a Unit whose routes genuinely reference them lands, at
    which point it becomes a no-op rather than a lie."

    **This asserts the no-op rather than trusting the sentence.** D3's
    nine fee routes declare their error responses against the envelope,
    and U4's responses carry real money properties, so both components
    are emitted by FastAPI itself. If a later Unit removed the last
    reference, this fails and the comment stops being false silently.

    The injection is kept regardless, because it is what stops that
    removal dropping a component out of the contract unnoticed.

    :return: None
    """
    from fastapi.openapi.utils import get_openapi

    from app.contract.routes import _api_routes

    app = create_app()
    # The document FastAPI builds from the ROUTES ALONE, with no
    # injection. `_api_routes` is the shared enumerator both contract
    # gates use, so this sees exactly what they see rather than a
    # second traversal that could drift.
    natural = get_openapi(
        title=app.title,
        version=app.version,
        routes=list(_api_routes(app)),
    )

    schemas = natural.get("components", {}).get("schemas", {})
    assert "ErrorEnvelope" in schemas, (
        "no route references the error envelope, so the injection in "
        "main.py is load-bearing again rather than a no-op. Its "
        "docstring says otherwise -- fix one or the other."
    )
    assert "Money" in schemas, (
        "no route references the Money component, so the injection is "
        "load-bearing again."
    )


def test_the_gate_reports_nothing_for_a_clean_application() -> None:
    app = FastAPI()
    app.state.included_routers = []

    class _Clean(BaseModel):
        enrollment_id: str

    @app.get("/v1/clean", response_model=_Clean)
    def clean(lens: TeacherLens = Depends(_teacher_lens)) -> _Clean:
        """Return a row with no payment number.

        :param lens: The teacher lens
        :return: The clean row
        """
        return _Clean(enrollment_id="x")

    assert collection_number_routes(app) == set()
