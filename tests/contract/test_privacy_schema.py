"""The schema-wide privacy gate.

Written before the implementation [NFR14.8]: a wrong answer is an
authorization error that passes silently, which is the team's test-first
predicate.

**Two forbidden field sets ride one iteration.** Owner-private profile
fields are what a student or guardian writes about themselves, which no
teacher may ever see [TC-13, D-5]. Account identifiers are a *global* key,
so a teacher-facing response carrying ``student_account_id`` hands teacher A
a stable handle on a student also enrolled with teacher B [ADR-001].

**The lens is read from the route, never guessed from the schema name.**
That is the decision that makes this gate real rather than heuristic, and
the three rejected alternatives each fail quietly -- see the tests at the
end.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.contract.privacy import (
    FORBIDDEN_ACCOUNT_ID_FIELDS,
    OWNER_PRIVATE_FIELDS,
    forbidden_fields,
)


def _teacher_lens() -> TeacherLens:
    """Stand in for U3's teacher-lens resolver.

    :return: A teacher lens
    """
    return TeacherLens(account_id=UUID(int=1), owner_id=UUID(int=2))


def _student_lens() -> StudentLens:
    """Stand in for U3's student-lens resolver.

    :return: A student lens
    """
    return StudentLens(account_id=UUID(int=1))


def _guardian_lens() -> GuardianLens:
    """Stand in for U3's guardian-lens resolver.

    :return: A guardian lens
    """
    return GuardianLens(account_id=UUID(int=1), child_enrollment_id=UUID(int=3))


class CleanRoster(BaseModel):
    """A teacher-facing roster carrying nothing forbidden.

    :ivar enrollment_id: Scoped to one owner, which is the point
    :ivar display_name: The name the teacher entered
    """

    enrollment_id: UUID
    display_name: str


class RosterWithProfile(BaseModel):
    """A teacher-facing roster that leaks an owner-private field.

    :ivar enrollment_id: Scoped to one owner
    :ivar self_name: Written by the student; no teacher may see it
    """

    enrollment_id: UUID
    self_name: str


class RosterWithAccountId(BaseModel):
    """A teacher-facing roster that leaks a global account key.

    :ivar enrollment_id: Scoped to one owner
    :ivar student_account_id: A global handle, forbidden by ADR-001
    """

    enrollment_id: UUID
    student_account_id: UUID


class NestedStudent(BaseModel):
    """An embedded student object.

    :ivar self_name: The likely place a profile field actually hides
    """

    self_name: str


class RosterWithNestedProfile(BaseModel):
    """A roster whose forbidden field is nested, not top-level.

    :ivar enrollment_id: Scoped to one owner
    :ivar student: The embedded object carrying the leak
    """

    enrollment_id: UUID
    student: NestedStudent


class RosterWithProfileList(BaseModel):
    """A roster whose forbidden field sits inside an array.

    :ivar students: Embedded objects, each carrying the leak
    """

    students: list[NestedStudent]


def _app_with(model: type[BaseModel], lens_dependency: object) -> FastAPI:
    """Build an application with one route returning ``model``.

    The dependency is attached via ``dependencies=[Depends(...)]`` rather
    than as a typed parameter: this module declares ``from __future__
    import annotations``, so a parameter annotation would reach FastAPI as
    an unresolvable string. The gate walks ``route.dependant`` either way,
    which is what it must do anyway for a nested dependency.

    :param model: The response model to expose
    :param lens_dependency: The lens resolver the route depends on
    :return: An application carrying exactly that route
    """
    app = FastAPI()

    @app.get(
        "/v1/probe",
        response_model=model,
        dependencies=[Depends(lens_dependency)],
    )
    def _probe() -> dict[str, str]:
        return {}

    return app


def test_clean_teacher_response_passes() -> None:
    """A teacher-facing response carrying nothing forbidden passes.

    :return: None
    """
    assert forbidden_fields(_app_with(CleanRoster, _teacher_lens)) == []


def test_owner_private_field_is_reported() -> None:
    """A profile field in a teacher-lens response is reported by name.

    :return: None
    """
    violations = forbidden_fields(_app_with(RosterWithProfile, _teacher_lens))

    assert len(violations) == 1
    assert violations[0].field == "self_name"
    assert violations[0].field_set == "owner-private"


def test_account_id_field_is_reported() -> None:
    """An account id in a teacher-lens response is reported by name.

    ADR-001's half of the invariant. A teacher-facing response exposes an
    enrollment id and never a global account key.

    :return: None
    """
    violations = forbidden_fields(_app_with(RosterWithAccountId, _teacher_lens))

    assert len(violations) == 1
    assert violations[0].field == "student_account_id"
    assert violations[0].field_set == "account-id"


def test_student_lens_response_may_carry_its_own_profile() -> None:
    """A profile field under a STUDENT lens is not a violation.

    It is the student's own data. A gate that reported this would be
    checking the field rather than the boundary, and would be silenced the
    first time it fired on a legitimate response.

    :return: None
    """
    assert forbidden_fields(_app_with(RosterWithProfile, _student_lens)) == []


def test_guardian_lens_response_is_not_teacher_facing() -> None:
    """A guardian-lens response is outside this gate's subject.

    :return: None
    """
    assert forbidden_fields(_app_with(RosterWithProfile, _guardian_lens)) == []


def test_nested_object_is_reached() -> None:
    """A forbidden field nested in an embedded object is reported.

    This is the likely shape of the defect, not a top-level one, so a gate
    checking only top-level properties would miss the realistic case.

    :return: None
    """
    violations = forbidden_fields(_app_with(RosterWithNestedProfile, _teacher_lens))

    assert [violation.field for violation in violations] == ["self_name"]


def test_array_items_are_reached() -> None:
    """A forbidden field inside an array of objects is reported.

    :return: None
    """
    violations = forbidden_fields(_app_with(RosterWithProfileList, _teacher_lens))

    assert [violation.field for violation in violations] == ["self_name"]


def test_self_referential_schema_terminates() -> None:
    """A self-referential ``$ref`` graph terminates rather than hanging.

    An unguarded walk **hangs** CI rather than failing it, and a hang is
    worse than a failure because nobody reads it as a result -- it looks
    like a slow build until someone cancels it.

    :return: None
    """

    class Node(BaseModel):
        """A node that refers to itself.

        :ivar child: The recursive reference
        """

        child: Node | None = None

    Node.model_rebuild()

    assert forbidden_fields(_app_with(Node, _teacher_lens)) == []


def test_route_without_response_model_is_skipped_safely() -> None:
    """A route declaring no response model does not crash the gate.

    :return: None
    """
    app = FastAPI()

    @app.get("/v1/no-model", dependencies=[Depends(_teacher_lens)])
    def _no_model() -> dict[str, str]:
        return {}

    assert forbidden_fields(app) == []


def test_schema_name_is_not_what_selects_a_route() -> None:
    """A model named for a teacher, returned under a student lens, passes.

    Matching on names would be defeated by a rename and blind to a shared
    model returned under two lenses. The lens comes from the route.

    :return: None
    """

    class TeacherSummary(BaseModel):
        """A model whose NAME suggests a teacher but whose route does not.

        :ivar self_name: The student's own data, legitimately present
        """

        self_name: str

    assert forbidden_fields(_app_with(TeacherSummary, _student_lens)) == []


def test_both_field_sets_are_non_empty() -> None:
    """Neither forbidden set is empty, which would make the gate vacuous.

    :return: None
    """
    assert OWNER_PRIVATE_FIELDS
    assert FORBIDDEN_ACCOUNT_ID_FIELDS


def test_the_real_app_passes() -> None:
    """The real application passes the gate.

    In B2 this iterates zero routes, which is exactly why the committed
    fixture exists.

    :return: None
    """
    from app.main import app as real_app

    assert forbidden_fields(real_app) == []
