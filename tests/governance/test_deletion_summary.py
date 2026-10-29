"""What a teacher is told before deleting: batches, students, money owed.

**Written before the route existed.** The O5 board's teacher variant
reads "You have 3 batches with 31 students" and "৳8,400 recorded as
owed stays on those records". All three are the server's figures; the
money is the same fold the dues view uses, so the two cannot disagree.
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.fees.ledger_writer import append_entry
from app.money import Money
from tests.batches.conftest import enroll, make_teacher
from tests.conftest import bearer


def test_a_teacher_is_told_what_they_leave_behind(
    api_client: TestClient, owner_session: Session
) -> None:
    """Two batches, three students, 1500 still owed across them.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    second = make_teacher(owner_session, name="Chemistry")
    owner_session.execute(
        sa.text("UPDATE batch SET owner_id = :o WHERE id = :b"),
        {"o": teacher.owner_id, "b": second.batch_id},
    )
    owner_session.commit()
    seats = [
        enroll(owner_session, batch_id=teacher.batch_id, display_name=name)
        for name in ("A", "B")
    ] + [enroll(owner_session, batch_id=second.batch_id, display_name="C")]
    append_entry(
        owner_session,
        enrollment_id=seats[0],
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    owner_session.commit()

    response = api_client.get(
        "/v1/me/deletion-summary", headers=bearer(owner_session, teacher.account_id)
    )

    assert response.status_code == 200
    assert response.json() == {
        "batch_count": 2,
        "student_count": 3,
        "outstanding": "1500.00",
    }


def test_someone_owning_nothing_sees_zeros(
    api_client: TestClient, owner_session: Session
) -> None:
    """A student or guardian is told nothing stays, not refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: None
    """
    teacher = make_teacher(owner_session, name="Physics")
    enroll(owner_session, batch_id=teacher.batch_id, display_name="A")
    stranger = make_teacher(owner_session, name="Other")
    owner_session.execute(
        sa.text("DELETE FROM batch WHERE id = :b"),
        {"b": stranger.batch_id},
    )
    owner_session.commit()

    response = api_client.get(
        "/v1/me/deletion-summary", headers=bearer(owner_session, stranger.account_id)
    )

    assert response.json() == {
        "batch_count": 0,
        "student_count": 0,
        "outstanding": "0.00",
    }


def test_the_summary_needs_a_credential(api_client: TestClient) -> None:
    """No token, no summary.

    :param api_client: The test client
    :return: None
    """
    assert api_client.get("/v1/me/deletion-summary").status_code == 401
