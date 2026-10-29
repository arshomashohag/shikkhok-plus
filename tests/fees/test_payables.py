"""What a student can pay (S3), and the notice when it is decided.

**Written before either existed.** "Which fee are you paying?" lists, per
seat, the month a claim would be recorded against -- the oldest unpaid
period, the one ``submit_claim`` already chooses -- with what is still
owed on it and when it was due. A seat whose payment is already waiting
for the teacher is not offered again; the board says so in a line.

**The amount is the server's fold**, never the phone's subtraction, and
only seats the student ACCEPTED appear: a pending invitation is not yet
their fee [BR1.1].

**The decision reaches the payer's inbox.** The board promises "You'll
get a notice when it's approved"; the inbox built for fee reminders is
where it goes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import StudentLens
from app.db.models import FeeCycle
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.payables import payables
from app.fees.verification import reject_claim, verify_claim
from app.money import Money
from app.notifications.inbox import inbox
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer


def _seat(
    session: Session,
    teacher: TeacherFixture,
    student: uuid.UUID,
    charges: list[tuple[str, str, dt.date]],
    decision: str = "accepted",
) -> uuid.UUID:
    """Seat a student and charge each ``(period, amount, due)``.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The student's account
    :param charges: Period, amount and due date for each charge
    :param decision: The student link's decision
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision=decision,
    )
    for period, amount, due in charges:
        append_entry(
            session,
            enrollment_id=seat,
            period=period,
            kind="charge",
            amount=Money(amount),
        )
        session.add(
            FeeCycle(
                enrollment_id=seat,
                period=period,
                due_date=due,
                created_at=dt.datetime.now(tz=dt.UTC),
            )
        )
    session.commit()
    return seat


def test_each_owing_seat_offers_its_oldest_unpaid_month(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """September is owed in full and October too: September is offered.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session,
        teacher,
        student,
        [
            ("2026-09", "1500.00", dt.date(2026, 9, 10)),
            ("2026-10", "1500.00", dt.date(2026, 10, 10)),
        ],
    )

    found = payables(restricted_session, lens=StudentLens(account_id=student))

    [row] = found.payable
    assert (row.enrollment_id, row.period, row.amount_due, row.due_date) == (
        seat,
        "2026-09",
        Money("1500.00"),
        dt.date(2026, 9, 10),
    )
    assert found.waiting == []


def test_a_part_paid_month_offers_what_is_left(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 charged and 800 received leaves 700 to pay.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session, teacher, student, [("2026-10", "1500.00", dt.date(2026, 10, 10))]
    )
    append_entry(
        owner_session,
        enrollment_id=seat,
        period="2026-10",
        kind="receipt",
        amount=Money("800.00"),
    )
    owner_session.commit()

    [row] = payables(restricted_session, lens=StudentLens(account_id=student)).payable

    assert row.amount_due == Money("700.00")


def test_a_seat_with_a_waiting_payment_is_listed_as_waiting(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Not offered twice; named so the screen can say why.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session, teacher, student, [("2026-10", "1500.00", dt.date(2026, 10, 10))]
    )
    submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        transaction_id="TX-1",
    )

    found = payables(restricted_session, lens=StudentLens(account_id=student))

    assert found.payable == []
    [waiting] = found.waiting
    assert (waiting.batch_name, waiting.period) == ("Physics", "2026-10")


def test_paid_up_and_unaccepted_seats_offer_nothing(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Nothing owed is nothing to pay; a pending seat is not yet theirs.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    paid = _seat(
        owner_session, teacher, student, [("2026-10", "1500.00", dt.date(2026, 10, 10))]
    )
    append_entry(
        owner_session,
        enrollment_id=paid,
        period="2026-10",
        kind="receipt",
        amount=Money("1500.00"),
    )
    owner_session.commit()
    stranger = account_factory()
    _seat(
        owner_session,
        teacher,
        stranger,
        [("2026-10", "1500.00", dt.date(2026, 10, 10))],
        decision="pending",
    )

    assert (
        payables(restricted_session, lens=StudentLens(account_id=student)).payable == []
    )
    assert (
        payables(restricted_session, lens=StudentLens(account_id=stranger)).payable
        == []
    )


def test_an_approval_and_a_rejection_reach_the_payers_inbox(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """One message per decision, naming the batch, month and amount.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session,
        teacher,
        student,
        [
            ("2026-09", "1500.00", dt.date(2026, 9, 10)),
            ("2026-10", "1500.00", dt.date(2026, 10, 10)),
        ],
    )
    first = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        transaction_id="TX-1",
    )
    verify_claim(
        owner_session,
        claim_id=first.id,
        approved_amount=Money("1500.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    second = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        transaction_id="TX-2",
    )
    reject_claim(
        owner_session, claim_id=second.id, verified_by_account_id=teacher.account_id
    )

    items = inbox(restricted_session, account_id=student).items

    assert [(i.kind, i.period, i.amount) for i in items] == [
        ("payment_rejected", "2026-10", Money("1500.00")),
        ("payment_approved", "2026-09", Money("1500.00")),
    ]
    assert {i.batch_name for i in items} == {"Physics"}


def test_the_payables_route_and_the_destination_name_the_teacher(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Money as a string; "Send money to <teacher>" has a name to use.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session, teacher, student, [("2026-10", "1500.00", dt.date(2026, 10, 10))]
    )
    owner_session.execute(
        sa.text(
            "UPDATE batch SET teacher_display_name = 'Najma', "
            "collection_number = '01712345678', collection_channel = 'bKash' "
            "WHERE id = :id"
        ),
        {"id": teacher.batch_id},
    )
    owner_session.commit()
    headers = bearer(owner_session, student)

    listed = api_client.get("/v1/me/payables", headers=headers).json()
    destination = api_client.get(
        f"/v1/enrollments/{seat}/payment-destination", headers=headers
    ).json()

    assert listed["payable"][0]["amount_due"] == "1500.00"
    assert listed["payable"][0]["batch_name"] == "Physics"
    assert destination["teacher_display_name"] == "Najma"
