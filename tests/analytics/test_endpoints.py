"""The two routes end to end through the real app.

**The money assertions are made at the HTTP boundary**, not at the
function boundary. A money value emitted as a JSON number is converted
to an IEEE 754 double by the client's parser, on the far side of the
wire where none of this project's controls reach -- so the only place
worth asserting it is where the bytes actually leave [TC-7, D-20].
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.tokens import issue_pair
from tests.analytics.conftest import add_batch, add_exam, seat_with_ledger
from tests.batches.conftest import TeacherFixture, _account, make_teacher


def test_an_unauthenticated_dues_read_is_refused(client: TestClient) -> None:
    """No credential reaches no figure [BR4.4].

    :param client: The test client
    :return: None
    """
    assert client.get("/v1/me/dues").status_code in {401, 403}


def test_an_unauthenticated_overview_read_is_refused(client: TestClient) -> None:
    """The same for the overview.

    :param client: The test client
    :return: None
    """
    assert client.get("/v1/me/overview").status_code in {401, 403}


def test_an_account_with_no_teacher_lens_is_refused(
    client: TestClient, owner_session: Session
) -> None:
    """An authenticated non-teacher reaches neither route [BR4.4].

    A VALID credential deliberately: an unauthenticated caller is
    refused one step earlier and says nothing about the lens.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    account = _account(owner_session)
    pair = issue_pair(owner_session, account_id=account, correlation_id=uuid.uuid4())
    headers = {"Authorization": f"Bearer {pair.access_token}"}

    assert client.get("/v1/me/dues", headers=headers).status_code == 403
    assert client.get("/v1/me/overview", headers=headers).status_code == 403


def test_money_crosses_as_a_json_string_never_a_number(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """``outstanding`` is a quoted string in the raw response body.

    Parsing the JSON first would hide the defect: a number and a string
    both decode to something truthy, and the damage is done by the
    client's parser before any assertion runs. The **raw text** carries
    the proof.

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
        display_name="Owes",
        entries=[("charge", "2027-01", "1250.00")],
    )

    response = client.get(
        "/v1/me/dues", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    assert '"outstanding":"1250.00"' in response.text.replace(" ", "")
    assert isinstance(response.json()["rows"][0]["outstanding"], str)


def test_the_earnings_figure_is_also_a_string_on_the_wire(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The overview's own money value, asserted at the boundary too.

    The dues row and the earnings figure travel through different
    response models, so one assertion does not cover the other.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    period = dt.datetime.now(tz=dt.UTC).date().strftime("%Y-%m")
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Paid this month",
        entries=[
            ("charge", period, "900.00"),
            ("receipt", period, "900.00"),
        ],
    )

    response = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    )

    assert response.status_code == 200
    assert '"received":"900.00"' in response.text.replace(" ", "")
    assert response.json()["earnings"]["period"] == period


def test_the_dues_response_carries_the_batch_name_per_row(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The same person may owe in two batches [AC7.1.1].

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    second = add_batch(owner_session, signed_in_teacher.owner_id, "Chemistry")
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Rahim",
        entries=[("charge", "2027-01", "300.00")],
    )
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=second,
        display_name="Rahim",
        entries=[("charge", "2027-01", "800.00")],
    )

    rows = client.get(
        "/v1/me/dues", headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["rows"]

    assert {row["batch_name"] for row in rows} == {"Physics", "Chemistry"}
    assert [row["outstanding"] for row in rows] == ["800.00", "300.00"]


def test_the_overview_carries_the_next_exam_with_its_days_remaining(
    client: TestClient,
    owner_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The exam block, rendered as a figure rather than an absence.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    when = dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=5)
    add_exam(
        owner_session,
        batch_id=signed_in_teacher.batch_id,
        title="Mid-term",
        date=when,
    )

    exam = client.get(
        "/v1/me/overview", headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["next_exam"]

    assert exam["title"] == "Mid-term"
    assert exam["batch_name"] == "Physics"
    assert exam["subject_name"] == "Physics"
    assert exam["days_remaining"] == 5


def test_one_teacher_s_response_never_carries_another_s_rows(
    client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    signed_in_teacher: TeacherFixture,
    teacher_token: str,
) -> None:
    """The scope boundary, asserted at the HTTP boundary as well.

    The unit probes assert it at the function boundary; this asserts
    that the route scopes on the lens it resolved rather than on
    anything else.

    :param client: The test client
    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session fixture data is written on
    :param signed_in_teacher: The authenticated teacher
    :param teacher_token: Their bearer token
    :return: None
    """
    other = make_teacher(owner_session, name="Someone else")
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=other.batch_id,
        display_name="Not yours",
        entries=[("charge", "2027-01", "9999.00")],
    )
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=signed_in_teacher.batch_id,
        display_name="Yours",
        entries=[("charge", "2027-01", "100.00")],
    )

    rows = client.get(
        "/v1/me/dues", headers={"Authorization": f"Bearer {teacher_token}"}
    ).json()["rows"]

    assert [row["display_name"] for row in rows] == ["Yours"]
    assert [row["outstanding"] for row in rows] == ["100.00"]
