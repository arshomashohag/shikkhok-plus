"""Four kinds of nothing, none collapsible [reliability § 2, NFR19.52].

============================= ========================= =======
Case                          Response                  Rule
============================= ========================= =======
Nobody owes                   empty collection, 200     BR1.5
Nothing received              **zero as a value**, 200  BR2.2
Under two months of history   trend **absent**, 200     BR2.3
No upcoming exam              exam **absent**, 200      BR3.4
============================= ========================= =======

**A test per row, asserting the status AND the shape.** "Not a 200"
passes against all three wrong answers; "a 200" passes against the wrong
shape. So each test here checks both, and the two that differ --
``earnings`` is a zero **value** while ``trend`` is **absent** -- are
asserted against each other in the same response, because encoding
either as the other is the defect.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.analytics.conftest import add_exam, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def test_nobody_owing_is_an_empty_collection_with_a_200(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """A teacher with batches and no debts gets 200 and ``rows: []``.

    Never a 404 and never an error: that would read to a client as a
    failure, and the teacher would see a retry prompt for the best
    possible news [BR1.5].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Paid up",
        entries=[
            ("charge", "2027-01", "500.00"),
            ("receipt", "2027-01", "500.00"),
        ],
    )

    response = client.get(
        "/v1/me/dues", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"rows": []}


def test_nothing_received_is_a_zero_value_and_not_an_absence(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """Zero earned is a fact about the month [BR2.2].

    Rendering it as "no data" tells a teacher their records are missing
    when they are complete, in the month they most need to know the
    number is really zero. The assertion is on the **string** ``"0.00"``
    rather than on truthiness, because a null, an omitted field and a
    zero are three different wire shapes and only one is correct.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Charged, unpaid",
        entries=[("charge", "2020-01", "500.00")],
    )

    response = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "earnings" in body
    assert body["earnings"]["received"] == "0.00"
    assert body["earnings"]["received"] is not None


def test_under_two_months_of_history_leaves_the_trend_absent(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """One point is not a trend, and absent is not an empty list [BR2.3].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="One month only",
        entries=[
            ("charge", "2026-03", "500.00"),
            ("receipt", "2026-03", "500.00"),
        ],
    )

    response = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    assert response.json()["trend"] is None


def test_two_months_returns_both_points_in_the_response_order(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The other half of BR2.3, and BR2.4's ordering on the wire.

    Asserted as a list rather than a set: the order **is** the contract,
    and a set assertion would pass against a client-sorted response.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Two months",
        entries=[
            ("charge", "2026-04", "500.00"),
            ("receipt", "2026-04", "500.00"),
            ("charge", "2026-03", "300.00"),
            ("receipt", "2026-03", "300.00"),
        ],
    )

    body = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()

    assert [point["period"] for point in body["trend"]] == ["2026-03", "2026-04"]
    assert [point["received"] for point in body["trend"]] == ["300.00", "500.00"]


def test_no_upcoming_exam_leaves_the_exam_absent_with_a_200(
    client: TestClient,
    owner_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """A teacher between terms sees "nothing scheduled" [BR3.4].

    The exam is dated in the past deliberately: a teacher with **no**
    exams at all would pass against an implementation that only ever
    returns nothing.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    add_exam(
        owner_session,
        batch_id=signed_in_teacher.batch_id,
        title="Last term",
        date=dt.date(2020, 1, 1),
    )

    response = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    assert response.json()["next_exam"] is None


def test_absent_and_zero_are_different_shapes_in_one_response(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The distinction, asserted where it is most easily collapsed.

    One response carrying **a zero value** for earnings and **an
    absence** for the trend. A test checking each in isolation can pass
    against an implementation that encodes both the same way.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="One old month",
        entries=[
            ("charge", "2026-05", "500.00"),
            ("receipt", "2026-05", "500.00"),
        ],
    )

    body = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()

    assert body["earnings"]["received"] == "0.00"
    assert body["trend"] is None
    assert body["next_exam"] is None
