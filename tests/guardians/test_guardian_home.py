"""The guardian's home (G1): children, what to pay next, what is checking.

**Written before the module existed.** G1 groups a guardian's seats by
CHILD -- "তাসনিম জাহান · 3 batches" -- where until now it listed seats.
Two seats are one child when the same student account holds both; a
seat with no student account yet is a child of its own. Only seats the
guardian ACCEPTED are reached [BR1.1], and grouping never reaches a seat
this guardian was not recorded on [BR5.3].

Every amount, every "late" and every choice of what to pay next is the
server's [TC-9].
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens
from app.db.models import Account, FeeCycle
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.verification import verify_claim
from app.guardians.children import children_of
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer


@pytest.fixture
def account_factory(owner_session: Session) -> Callable[[], uuid.UUID]:
    """Return a factory making accounts with unique phone numbers.

    :param owner_session: A session able to arrange fixture data
    :return: A callable producing a fresh account id each time
    """

    def make() -> uuid.UUID:
        account = Account(
            phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
            created_at=dt.datetime.now(tz=dt.UTC),
        )
        owner_session.add(account)
        owner_session.commit()
        return account.id

    return make


def _seat(
    session: Session,
    batch_id: uuid.UUID,
    name: str,
    *,
    guardian: uuid.UUID,
    student: uuid.UUID | None,
    decision: str = "accepted",
) -> uuid.UUID:
    """Seat a child with this guardian.

    :param session: An arranging session
    :param batch_id: The batch
    :param name: The teacher-typed name
    :param guardian: The guardian's account
    :param student: The student's account, if any
    :param decision: The guardian link's decision
    :return: The seat
    """
    return enroll(
        session,
        batch_id=batch_id,
        display_name=name,
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted" if student else None,
        guardian_decision=decision,
    )


def _charge(
    session: Session, seat: uuid.UUID, period: str, amount: str, due: dt.date
) -> None:
    """Charge one period.

    :param session: An arranging session
    :param seat: The seat
    :param period: The period
    :param amount: The charge
    :param due: Its due date
    :return: None
    """
    append_entry(
        session, enrollment_id=seat, period=period, kind="charge", amount=Money(amount)
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


def test_seats_held_by_one_student_are_one_child(
    owner_session: Session,
    restricted_session: Session,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two batches of one student are one child; another student is another.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param account_factory: Makes accounts
    :return: None
    """
    guardian, tasnim, ayan = account_factory(), account_factory(), account_factory()
    physics, chemistry = (
        make_teacher(owner_session, name="Physics"),
        make_teacher(owner_session, name="Chemistry"),
    )
    _seat(owner_session, physics.batch_id, "Tasnim", guardian=guardian, student=tasnim)
    _seat(
        owner_session, chemistry.batch_id, "Tasnim J", guardian=guardian, student=tasnim
    )
    _seat(owner_session, physics.batch_id, "Ayan", guardian=guardian, student=ayan)

    children = children_of(restricted_session, lens=GuardianLens(account_id=guardian))

    assert sorted(len(child.seats) for child in children) == [1, 2]
    # A child is named by the seat in the first batch alphabetically.
    assert {child.display_name for child in children} == {"Ayan", "Tasnim J"}


def test_an_unaccepted_or_studentless_seat_is_handled_apart(
    owner_session: Session,
    restricted_session: Session,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A pending link is not reached; a seat with no student is its own child.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    teacher = make_teacher(owner_session, name="Physics")
    _seat(
        owner_session,
        teacher.batch_id,
        "Pending",
        guardian=guardian,
        student=None,
        decision="pending",
    )
    _seat(owner_session, teacher.batch_id, "Rafi", guardian=guardian, student=None)
    _seat(owner_session, teacher.batch_id, "Mim", guardian=guardian, student=None)

    children = children_of(restricted_session, lens=GuardianLens(account_id=guardian))

    assert sorted(child.display_name for child in children) == ["Mim", "Rafi"]


def test_the_home_says_what_to_pay_next_and_what_is_being_checked(
    api_client: TestClient,
    owner_session: Session,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Maths owes October; Chemistry's payment is waiting.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param account_factory: Makes accounts
    :return: None
    """
    guardian, tasnim = account_factory(), account_factory()
    maths: TeacherFixture = make_teacher(owner_session, name="Maths")
    chemistry: TeacherFixture = make_teacher(owner_session, name="Chemistry")
    maths_seat = _seat(
        owner_session, maths.batch_id, "Tasnim", guardian=guardian, student=tasnim
    )
    chem_seat = _seat(
        owner_session, chemistry.batch_id, "Tasnim", guardian=guardian, student=tasnim
    )
    _charge(owner_session, maths_seat, "2026-09", "1500.00", dt.date(2026, 9, 20))
    _charge(owner_session, maths_seat, "2026-10", "1500.00", dt.date(2026, 10, 20))
    _charge(owner_session, chem_seat, "2026-10", "1200.00", dt.date(2026, 10, 10))
    submit_claim(
        owner_session,
        enrollment_id=chem_seat,
        submitted_by_account_id=guardian,
        claimed_amount=Money("1200.00"),
        channel="Nagad",
        transaction_id="NG-1",
    )

    [child] = api_client.get(
        "/v1/guardian/home", headers=bearer(owner_session, guardian)
    ).json()["children"]

    assert child["batch_count"] == 2
    payment = child["next_payment"]
    assert (payment["enrollment_id"], payment["period"], payment["amount_due"]) == (
        str(maths_seat),
        "2026-09",
        "1500.00",
    )
    assert (payment["total_due"], payment["later_periods"]) == ("3000.00", 1)
    assert payment["days_late"] is not None
    [waiting] = child["waiting"]
    assert (waiting["batch_name"], waiting["amount"], waiting["channel"]) == (
        "Chemistry",
        "1200.00",
        "Nagad",
    )
    assert {row["batch_name"] for row in child["batches"]} == {"Maths", "Chemistry"}


def test_a_guardian_pays_for_the_child_and_hears_back(
    api_client: TestClient,
    owner_session: Session,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The guardian's payables, destination and claim routes work for their seat.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param account_factory: Makes accounts
    :return: None
    """
    guardian, stranger = account_factory(), account_factory()
    teacher = make_teacher(owner_session, name="Maths")
    seat = _seat(
        owner_session, teacher.batch_id, "Tasnim", guardian=guardian, student=None
    )
    _charge(owner_session, seat, "2026-10", "1500.00", dt.date(2026, 10, 20))
    headers = bearer(owner_session, guardian)

    payables = api_client.get(f"/v1/children/{seat}/payables", headers=headers).json()
    claim = api_client.post(
        f"/v1/children/{seat}/claims",
        json={
            "claimed_amount": "1500.00",
            "channel": "bKash",
            "transaction_id": "DJ62K0LQ7V",
        },
        headers=headers,
    )
    refused = api_client.post(
        f"/v1/children/{seat}/claims",
        json={"claimed_amount": "1500.00", "channel": "bKash"},
        headers=bearer(owner_session, stranger),
    )

    assert payables["payable"][0]["enrollment_id"] == str(seat)
    assert claim.status_code == 201
    assert claim.json()["status"] == "pending"
    assert refused.status_code == 403


def test_the_payment_history_lists_months_newest_first_with_the_year_total(
    api_client: TestClient,
    owner_session: Session,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """September paid by bKash; October sent by Nagad and checking.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    teacher = make_teacher(owner_session, name="Maths")
    seat = _seat(
        owner_session, teacher.batch_id, "Tasnim", guardian=guardian, student=None
    )
    _charge(owner_session, seat, "2026-09", "1500.00", dt.date(2026, 9, 20))
    _charge(owner_session, seat, "2026-10", "1500.00", dt.date(2026, 10, 20))
    september = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=guardian,
        claimed_amount=Money("1500.00"),
        channel="bKash",
        transaction_id="TX-1",
    )
    verify_claim(
        owner_session,
        claim_id=september.id,
        approved_amount=Money("1500.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=guardian,
        claimed_amount=Money("1500.00"),
        channel="Nagad",
        transaction_id="TX-2",
    )

    body = api_client.get(
        f"/v1/children/{seat}/payments", headers=bearer(owner_session, guardian)
    ).json()

    assert body["paid_this_year"] == "1500.00"
    assert [month["period"] for month in body["months"]] == ["2026-10", "2026-09"]
    october, september_line = (
        body["months"][0]["lines"][0],
        body["months"][1]["lines"][0],
    )
    assert (october["state"], october["channel"], october["decided_on"]) == (
        "verifying",
        "Nagad",
        None,
    )
    assert (september_line["state"], september_line["channel"]) == ("paid", "bKash")
    assert september_line["decided_on"] is not None
