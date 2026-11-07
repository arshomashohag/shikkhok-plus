"""Another tenant reaches nothing in the centre-era routes [audit C-15].

The security review traced every one of these routes and found them
scoped correctly. What it also found is that the probes proving it were
partial: payroll adjustments, payments and the month read, a staff
member's pay terms, a room, and an extra fee's detail and listing had no
test sending another tenant's request. Row-level security covers only
``profile``, so for these tables the owner predicate in the query is the
whole boundary, and a probe is what makes a forgotten one fail in CI
rather than in production.

Each probe asserts the refusal AND that nothing changed or leaked.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Room, SalaryAdjustment, Staff
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.fees.test_extra_fees import _fee_id, _raise
from tests.payroll.test_payroll import PERIOD, Setup, setup  # noqa: F401
from tests.scheduling.test_scheduling import Centre

REFUSED = {403, 404}


def _approved_line(setup: Setup) -> dict:  # noqa: F811
    """Draw the month and return the receptionist's draft line.

    :param setup: The arrangement
    :return: The line, as drawn
    """
    return setup.line_of(setup.draw(), setup.office_staff)


def test_another_centre_cannot_adjust_pay_or_read_payroll(
    setup: Setup,  # noqa: F811
    api_client: TestClient,
    owner_session: Session,
) -> None:
    """Adjust, remove an adjustment, pay and read: each refused.

    :param setup: The arrangement
    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    line = _approved_line(setup)
    base = f"/v1/centre/payroll/lines/{line['line_id']}"
    own = setup.post(
        f"{base}/adjustments",
        {"kind": "addition", "label": "Bonus", "amount": "100.00"},
    )
    assert own.status_code == 200, own.text  # type: ignore[attr-defined]
    adjustment = owner_session.scalars(
        sa.select(SalaryAdjustment.id).where(
            SalaryAdjustment.salary_line_id == uuid.UUID(line["line_id"])
        )
    ).one()

    other = Centre(api_client, owner_session)
    attempts = [
        api_client.post(
            f"{base}/adjustments",
            json={"kind": "addition", "label": "Mine", "amount": "999.00"},
            headers=other.headers(),
        ),
        api_client.delete(f"{base}/adjustments/{adjustment}", headers=other.headers()),
        api_client.post(
            f"{base}/payments",
            json={"amount": "1.00", "client_mutation_id": str(uuid.uuid4())},
            headers=other.headers(),
        ),
    ]
    for response in attempts:
        assert response.status_code in REFUSED, response.text

    month = api_client.get(f"/v1/centre/payroll/{PERIOD}", headers=other.headers())
    assert month.status_code == 200, month.text
    assert line["line_id"] not in month.text

    labels = owner_session.scalars(
        sa.select(SalaryAdjustment.label).where(
            SalaryAdjustment.salary_line_id == uuid.UUID(line["line_id"])
        )
    ).all()
    assert labels == ["Bonus"]


def test_another_centre_cannot_change_a_staff_members_pay(
    setup: Setup,  # noqa: F811
    api_client: TestClient,
    owner_session: Session,
) -> None:
    """A foreign PATCH of pay terms is refused and changes nothing.

    :param setup: The arrangement
    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    other = Centre(api_client, owner_session)

    response = api_client.patch(
        f"/v1/centre/staff/{setup.office_staff}",
        json={"pay_rate": "1.00"},
        headers=other.headers(),
    )

    assert response.status_code in REFUSED, response.text
    owner_session.expire_all()
    staff = owner_session.get(Staff, setup.office_staff)
    assert staff is not None and str(staff.pay_rate) == "8000.00"


def test_another_centre_cannot_rename_or_archive_a_room(
    api_client: TestClient, owner_session: Session
) -> None:
    """A foreign PATCH of a room is refused and changes nothing.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    centre = Centre(api_client, owner_session)
    room = centre.room("Room 1")
    other = Centre(api_client, owner_session)

    response = api_client.patch(
        f"/v1/centre/rooms/{room}",
        json={"name": "Taken", "archived": True},
        headers=other.headers(),
    )

    assert response.status_code in REFUSED, response.text
    owner_session.expire_all()
    stored = owner_session.get(Room, room)
    assert stored is not None
    assert stored.name == "Room 1"


def test_another_teacher_cannot_read_an_extra_fee(
    api_client: TestClient,
    owner_session: Session,
) -> None:
    """The fee's detail and the batch's listing name families; both refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher: TeacherFixture = make_teacher(owner_session)
    enroll(owner_session, batch_id=teacher.batch_id, display_name="Tania")
    fee = _fee_id(_raise(api_client, owner_session, teacher))
    stranger = make_teacher(owner_session)
    headers = bearer(owner_session, stranger.account_id)

    detail = api_client.get(f"/v1/extra-fees/{fee}", headers=headers)
    listing = api_client.get(
        f"/v1/batches/{teacher.batch_id}/extra-fees", headers=headers
    )

    for response in (detail, listing):
        assert response.status_code in REFUSED, response.text
        assert "Tania" not in response.text
