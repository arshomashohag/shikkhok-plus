"""The address: the highest-stakes single disclosure in the product.

BR3.2 says the boundary is enforced **structurally** rather than per
endpoint, and that is true of the mechanism and **not automatic for a
new column** [BR3.4]. Three independent layers hold it, and D1 changes
exactly one of them:

* the **table**: ``address`` lands on ``Profile``, which the
  row-level-security policy keys on the session account -- inherited,
  unchanged;
* the **row**: that policy -- inherited, unchanged;
* the **schema**: no teacher-lens response may carry a ``Profile``
  field, matched by FIELD NAME against a hand-maintained set. This is
  the layer that does not extend itself, and the one D1 had to enrol
  ``address`` into.

These probes are **adversarial and run as the restricted role**, which
is what makes them mean anything: a superuser bypasses row-level
security entirely, so the same suite would pass against a policy that
was broken or absent [pg-rls]. ``tests/privacy/conftest.py`` asserts
that precondition before this file runs.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.rls import set_account_context
from app.contract.privacy import OWNER_PRIVATE_FIELDS, forbidden_fields
from app.db.models import Enrollment, Profile
from tests.accounts.conftest import auth_header, make_account
from tests.batches.conftest import TeacherFixture, make_teacher

#: What a teacher must never read.
HOME_ADDRESS = "House 7, Road 11, Dhanmondi, Dhaka"


def _seat(
    session: Session,
    *,
    teacher: TeacherFixture,
    student_account_id: uuid.UUID,
    student_decision: str = "accepted",
) -> uuid.UUID:
    """Create one seat the teacher can see on their roster.

    :param session: An arranging session
    :param teacher: The teacher whose batch holds the seat
    :param student_account_id: The student link
    :param student_decision: The student link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=teacher.batch_id,
        student_account_id=student_account_id,
        display_name="Rahim Uddin",
        student_decision=student_decision,
        guardian_decision="pending",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def test_address_is_a_member_of_the_owner_private_field_set() -> None:
    """The one manual step in the structural gate [BR3.4].

    ``OWNER_PRIVATE_FIELDS`` is not derived from ``Profile``'s columns,
    so adding ``address`` did **not** enrol it. An unenrolled field
    leaves the schema-wide invariant passing over a field it cannot
    see -- the gate reporting clean while checking nothing about the
    column it was most needed for.

    :return: None
    """
    assert "address" in OWNER_PRIVATE_FIELDS


def test_no_teacher_lens_response_schema_carries_a_profile_field(
    client: TestClient,
) -> None:
    """The schema-wide invariant, over the live application [NFR14.25].

    **Iteration, not enumeration.** A per-endpoint test covers the
    endpoints somebody remembered; walking every teacher-facing
    response schema in the generated document covers the one a later
    Unit adds after everyone has stopped thinking about it -- which is
    the endpoint that will carry the leak.

    :param client: A client against the restricted engine
    :return: None
    """
    violations = forbidden_fields(client.app)

    assert violations == [], (
        f"teacher-facing schemas declare forbidden fields: {violations}"
    )


def test_a_teacher_reading_their_roster_sees_no_address(
    client: TestClient, owner_session: Session, restricted_session: Session
) -> None:
    """The behavioural probe, through the real route [BR3.2].

    The schema invariant proves no teacher-facing schema *declares* a
    profile field. This proves the bytes a teacher actually receives
    carry none, which is the claim a person would make and is not the
    same statement.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    _seat(owner_session, teacher=teacher, student_account_id=student)

    # The profile is written as its OWNER, through the policy, which is
    # the only way this row can exist at all.
    set_account_context(restricted_session, student)
    restricted_session.add(
        Profile(account_id=student, self_name="Rahim's own name", address=HOME_ADDRESS)
    )
    restricted_session.commit()

    response = client.get(
        f"/v1/batches/{teacher.batch_id}/roster",
        headers=auth_header(owner_session, teacher.account_id),
    )

    assert response.status_code == 200
    assert HOME_ADDRESS not in response.text
    assert "address" not in response.text
    assert "Rahim's own name" not in response.text
    # And the teacher-typed name IS there, so the assertion above is
    # not passing because the roster is empty.
    assert "Rahim Uddin" in response.text


def test_the_row_policy_refuses_a_teacher_reading_another_profile(
    owner_session: Session, restricted_session: Session
) -> None:
    """The row layer, probed directly [BR3.2, TC-13].

    Beneath the schema layer: even a query that went looking for the
    column returns nothing, because the policy keys on the session
    account. This is the layer that survives somebody writing a new
    endpoint carelessly.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)

    set_account_context(restricted_session, student)
    restricted_session.add(
        Profile(account_id=student, self_name="Rahim", address=HOME_ADDRESS)
    )
    restricted_session.commit()

    # Now read as the TEACHER, going straight at the column.
    set_account_context(restricted_session, teacher.account_id)
    rows = restricted_session.execute(
        sa.select(Profile.address).where(Profile.account_id == student)
    ).all()

    assert rows == [], "the policy let a teacher read another profile"

    # And the owner still reads their own, so the assertion above is
    # not passing because the row is missing.
    set_account_context(restricted_session, student)
    own = restricted_session.execute(
        sa.select(Profile.address).where(Profile.account_id == student)
    ).scalar_one()
    assert own == HOME_ADDRESS


def test_a_guardian_cannot_read_a_non_childs_enrollment(
    client: TestClient, owner_session: Session
) -> None:
    """The IDOR shape, on the guardian axis [team: Testing Posture].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    guardian = make_account(owner_session)
    my_child = make_account(owner_session)
    someone_else = make_account(owner_session)

    mine = Enrollment(
        batch_id=teacher.batch_id,
        student_account_id=my_child,
        guardian_account_id=guardian,
        display_name="My child",
        student_decision="pending",
        guardian_decision="accepted",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(mine)
    other = _seat(owner_session, teacher=teacher, student_account_id=someone_else)
    owner_session.commit()

    # The guardian holds a real guardian lens, so this is not refused
    # for want of one -- it is refused for want of a claim on THIS seat.
    response = client.get(
        f"/v1/invitations/{other}",
        headers=auth_header(owner_session, guardian),
    )

    assert response.status_code == 403


def test_a_student_cannot_read_another_students_seat(
    client: TestClient, owner_session: Session
) -> None:
    """The IDOR shape, on the student axis [team: Testing Posture].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    mine = make_account(owner_session)
    theirs = make_account(owner_session)
    _seat(
        owner_session,
        teacher=teacher,
        student_account_id=mine,
        student_decision="accepted",
    )
    other = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=theirs,
        student_decision="pending",
    )

    response = client.get(
        f"/v1/invitations/{other}",
        headers=auth_header(owner_session, mine),
    )

    assert response.status_code == 403
