"""The invitation routes, end to end through the application.

The service-level transitions are asserted in
``tests/authz/test_decision_transitions.py``, which was written before
the service existed. This file asserts the half those cannot see: that
the routes **resolve an invitation lens**, that the lens bounds what a
handler can reach, and that the list behaves as BR5.5 describes once a
decision has been made.

The sharpest assertion here is the IDOR probe: a person holding an
unaccepted seat of their own must not reach somebody else's by
substituting its id. That is the shape the lens exists to make
impossible, and a handler keyed on a path parameter without one would
pass every other test in this file.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Enrollment
from app.money import Money
from tests.accounts.conftest import auth_header, make_account
from tests.batches.conftest import TeacherFixture, make_teacher


def _seat(
    session: Session,
    *,
    teacher: TeacherFixture,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    student_decision: str = "pending",
    guardian_decision: str = "pending",
) -> uuid.UUID:
    """Create one seat with both decisions stated explicitly.

    :param session: An arranging session
    :param teacher: The teacher whose batch holds the seat
    :param student_account_id: The student link, or None
    :param guardian_account_id: The guardian link, or None
    :param student_decision: The student link's decision
    :param guardian_decision: The guardian link's decision
    :return: The new enrollment's id
    """
    record = Enrollment(
        batch_id=teacher.batch_id,
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        display_name="Rahim Uddin",
        fee_amount=Money("1200.00"),
        student_decision=student_decision,
        guardian_decision=guardian_decision,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def test_an_invitation_carries_exactly_the_three_fields(
    client: TestClient, owner_session: Session
) -> None:
    """Width, asserted on the response body [BR1.4, AC1.10.1].

    Batch name, subject and fee -- plus the seat's id, which the
    decision routes are keyed on, and this holder's own state so the
    screen offers the right action without deciding for itself [TC-9].
    No attendance, no marks, no other enrollment [AC1.10.2].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    enrollment_id = _seat(owner_session, teacher=teacher, student_account_id=student)

    response = client.get(
        f"/v1/invitations/{enrollment_id}",
        headers=auth_header(owner_session, student),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "enrollment_id",
        "batch_name",
        "subject",
        "fee_amount",
        "decision",
    }
    assert body["batch_name"] == "Physics"
    assert body["decision"] == "pending"
    # Money crosses as a JSON STRING, never a number [TC-7, D-20].
    assert body["fee_amount"] == "1200.00"
    assert isinstance(body["fee_amount"], str)


def test_a_person_cannot_reach_a_seat_that_is_not_theirs(
    client: TestClient, owner_session: Session
) -> None:
    """The IDOR probe [NFR14.13, security-design].

    Both people hold an unaccepted seat, so neither is refused for
    lacking a lens in general -- which is the fixture detail that
    makes this test load-bearing. The refusal must be about *this*
    seat.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    mine = make_account(owner_session)
    theirs = make_account(owner_session)
    _seat(owner_session, teacher=teacher, student_account_id=mine)
    other_seat = _seat(owner_session, teacher=teacher, student_account_id=theirs)

    response = client.get(
        f"/v1/invitations/{other_seat}",
        headers=auth_header(owner_session, mine),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NO_INVITATION_LENS"


def test_accepting_grants_the_lens_and_leaves_the_invitations(
    client: TestClient, owner_session: Session
) -> None:
    """Accept, end to end [AC1.10.3, BR5.5].

    One request changes two observable things: the seat leaves the
    invitation list, and ``GET /v1/me`` starts offering the student
    lens. Asserting both is what connects the decision column to the
    behaviour it exists to drive.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    enrollment_id = _seat(owner_session, teacher=teacher, student_account_id=student)
    headers = auth_header(owner_session, student)

    before = client.get("/v1/me", headers=headers).json()["lenses"]
    assert before == []

    accepted = client.post(f"/v1/invitations/{enrollment_id}/accept", headers=headers)

    assert accepted.status_code == 200
    assert accepted.json()["decision"] == "accepted"

    after = client.get("/v1/me", headers=headers).json()["lenses"]
    assert [entry["kind"] for entry in after] == ["student"]
    assert client.get("/v1/invitations", headers=headers).json() == []


def test_a_declined_seat_leaves_the_enrollments_and_stays_listed(
    client: TestClient, owner_session: Session
) -> None:
    """Both halves of BR5.5 [AC1.10.4, AC1.13.1].

    Out of the enrollments because BR1.1 denies the lens; still in the
    invitations because BR5.4 needs the holder to reach it. A
    implementation that removed the seat entirely would satisfy the
    first half and make the reversal unreachable.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    enrollment_id = _seat(owner_session, teacher=teacher, student_account_id=student)
    headers = auth_header(owner_session, student)

    declined = client.post(f"/v1/invitations/{enrollment_id}/decline", headers=headers)

    assert declined.status_code == 200
    assert declined.json()["decision"] == "declined"
    assert client.get("/v1/me", headers=headers).json()["lenses"] == []

    listed = client.get("/v1/invitations", headers=headers).json()
    assert [entry["enrollment_id"] for entry in listed] == [str(enrollment_id)]
    assert listed[0]["decision"] == "declined"


def test_a_declined_seat_can_be_accepted_later(
    client: TestClient, owner_session: Session
) -> None:
    """The reversal, through the routes [AC1.13.2, BR5.4].

    The lens becomes available exactly as if the person had accepted
    first time, which is what makes a mis-tap recoverable rather than
    permanent.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    enrollment_id = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=student,
        student_decision="declined",
    )
    headers = auth_header(owner_session, student)

    client.post(f"/v1/invitations/{enrollment_id}/accept", headers=headers)

    lenses = client.get("/v1/me", headers=headers).json()["lenses"]
    assert [entry["kind"] for entry in lenses] == ["student"]
    assert lenses[0]["count"] == 1


def test_a_guardian_decline_leaves_the_students_seat_standing(
    client: TestClient, owner_session: Session
) -> None:
    """The role-dependent rule [BR5.2, AC1.10.6, AC1.14.1a].

    **The one a single decline confirmation got wrong**, by telling a
    guardian a debt was cancelled when it was not. The guardian's
    refusal withdraws the guardian's lens and nothing else.

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    guardian = make_account(owner_session)
    enrollment_id = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
    )

    client.post(
        f"/v1/invitations/{enrollment_id}/decline",
        headers=auth_header(owner_session, guardian),
    )

    student_lenses = client.get(
        "/v1/me", headers=auth_header(owner_session, student)
    ).json()["lenses"]
    guardian_lenses = client.get(
        "/v1/me", headers=auth_header(owner_session, guardian)
    ).json()["lenses"]

    assert [entry["kind"] for entry in student_lenses] == ["student"]
    assert guardian_lenses == []


def test_one_account_on_both_links_accepts_once_and_gains_both(
    client: TestClient, owner_session: Session
) -> None:
    """One action, two columns, one listing [BR5.3, AC1.10.5].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    person = make_account(owner_session)
    enrollment_id = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=person,
        guardian_account_id=person,
    )
    headers = auth_header(owner_session, person)

    listed = client.get("/v1/invitations", headers=headers).json()
    assert len(listed) == 1, "the seat was listed twice"

    client.post(f"/v1/invitations/{enrollment_id}/accept", headers=headers)

    kinds = {
        entry["kind"]
        for entry in client.get("/v1/me", headers=headers).json()["lenses"]
    }
    assert kinds == {"student", "guardian"}


def test_an_accepted_seat_is_no_longer_reachable_as_an_invitation(
    client: TestClient, owner_session: Session
) -> None:
    """The grant's negation, at the route [BR1.3, BR5.5].

    :param client: A client against the restricted engine
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    student = make_account(owner_session)
    enrollment_id = _seat(
        owner_session,
        teacher=teacher,
        student_account_id=student,
        student_decision="accepted",
    )

    response = client.get(
        f"/v1/invitations/{enrollment_id}",
        headers=auth_header(owner_session, student),
    )

    assert response.status_code == 403
