"""The teacher's payment queue (R1): what waits to be checked.

**Written before the queue existed.** It is a read over money and over
other people's payments, so both halves of the test-first predicate
hold: the expected figures are knowable from the charges without any
implementation, and a wrong answer is a money error (a shortfall the
teacher acts on) or an authorization error (a payment from another
teacher's batch).

The figures are the server's decisions. A charge of 1200 against a
payment of 800 is ``short`` by ``400.00``; the app shows those words and
never subtracts. Each item is one payment, however many children it
covers.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import PaymentSubmission
from app.fees.decisions import approve_submission, reject_submission
from app.fees.queue import verification_queue
from app.fees.submissions import FamilyLens, PaymentDraft, submit_payment
from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.fees.conftest import add_method, charge_period

PERIOD = "2026-10"


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _student_seat(
    session: Session, teacher: TeacherFixture, name: str, student: uuid.UUID
) -> uuid.UUID:
    """Seat an accepted student charged 1200 for October.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param name: The teacher-typed name
    :param student: The student's account
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name=name,
        student_account_id=student,
        student_decision="accepted",
    )
    charge_period(session, enrollment_id=seat, period=PERIOD, amount="1200.00")
    return seat


def _pay(
    session: Session,
    teacher: TeacherFixture,
    lens: FamilyLens,
    seats: list[uuid.UUID],
    amount: str,
    transaction_id: str = "TX-1",
) -> PaymentSubmission:
    """Report one payment to the teacher's bKash method.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param lens: The payer's lens
    :param seats: The children covered
    :param amount: The amount sent
    :param transaction_id: The quoted reference
    :return: The submission
    """
    return submit_payment(
        session,
        lens=lens,
        draft=PaymentDraft(
            enrollment_ids=tuple(seats),
            payment_method_id=add_method(session, teacher.owner_id),
            cash=False,
            amount=Money(amount),
            paid_on=bangladesh_today(),
            transaction_id=transaction_id,
            from_account=None,
            note=None,
        ),
    )


def test_a_pending_payment_carries_what_is_owed_and_the_servers_comparison(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Owed 1200, sent 800: short by 400, decided by the server.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _student_seat(owner_session, teacher, "Rahim", student)
    submission = _pay(
        owner_session, teacher, StudentLens(account_id=student), [seat], "800.00"
    )

    [item] = verification_queue(restricted_session, lens=_lens(teacher)).pending

    assert item.submission_id == submission.id
    assert [child.display_name for child in item.children] == ["Rahim"]
    assert item.owed_together == Money("1200.00")
    assert item.total_amount == Money("800.00")
    assert (item.comparison, item.difference) == ("short", Money("400.00"))
    assert item.submitted_by == "student"
    assert item.transaction_id == "TX-1"
    assert item.method["provider"] == "bKash"
    assert item.duplicate_of is None


def test_a_payment_equal_to_the_owed_matches_and_one_above_is_over(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The other two comparisons, each with the figure that decides it.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    for name, sent in (("Exact", "1200.00"), ("Over", "1500.00")):
        student = account_factory()
        seat = _student_seat(owner_session, teacher, name, student)
        _pay(
            owner_session,
            teacher,
            StudentLens(account_id=student),
            [seat],
            sent,
            f"TX-{name}",
        )

    results = {
        item.children[0].display_name: (item.comparison, item.difference)
        for item in verification_queue(restricted_session, lens=_lens(teacher)).pending
    }

    assert results == {
        "Exact": ("matches", Money.ZERO),
        "Over": ("over", Money("300.00")),
    }


def test_another_teachers_payments_never_appear(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The queue is scoped to the batches this lens owns.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: A teacher with a pending payment
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _student_seat(owner_session, teacher, "Rahim", student)
    _pay(owner_session, teacher, StudentLens(account_id=student), [seat], "1200.00")
    stranger = make_teacher(owner_session, name="Chemistry")

    queue = verification_queue(restricted_session, lens=_lens(stranger))

    assert queue.pending == []
    assert queue.decided_recently == []


def test_a_decided_payment_leaves_the_queue_for_the_recent_list(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approved and rejected payments move to "decided today" [R3].

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    submissions: list[uuid.UUID] = []
    for name in ("Asha", "Bilal"):
        student = account_factory()
        seat = _student_seat(owner_session, teacher, name, student)
        submissions.append(
            _pay(
                owner_session,
                teacher,
                StudentLens(account_id=student),
                [seat],
                "1200.00",
                f"TX-{name}",
            ).id
        )
    approve_submission(
        owner_session,
        lens=_lens(teacher),
        submission_id=submissions[0],
        received=Money("1200.00"),
        disposition=None,
        carried_by_enrollment_id=None,
        credit_to_enrollment_id=None,
        note=None,
    )
    reject_submission(
        owner_session, lens=_lens(teacher), submission_id=submissions[1], note=None
    )

    queue = verification_queue(restricted_session, lens=_lens(teacher))

    assert queue.pending == []
    assert {item.status for item in queue.decided_recently} == {
        "approved",
        "rejected",
    }


def test_a_decision_older_than_a_day_is_not_recent(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Treat "approved today" as the last day, not every decision ever.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _student_seat(owner_session, teacher, "Rahim", student)
    submission = _pay(
        owner_session, teacher, StudentLens(account_id=student), [seat], "1200.00"
    )
    approve_submission(
        owner_session,
        lens=_lens(teacher),
        submission_id=submission.id,
        received=Money("1200.00"),
        disposition=None,
        carried_by_enrollment_id=None,
        credit_to_enrollment_id=None,
        note=None,
    )

    later = dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=2)
    queue = verification_queue(restricted_session, lens=_lens(teacher), now=later)

    assert queue.decided_recently == []


def test_a_transaction_id_used_twice_names_the_earlier_payment(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same bKash ID on two payments flags the later one.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    first_student = account_factory()
    first = _student_seat(owner_session, teacher, "Sakib", first_student)
    earlier = _pay(
        owner_session,
        teacher,
        StudentLens(account_id=first_student),
        [first],
        "1200.00",
        "8N7K2QX",
    )
    approve_submission(
        owner_session,
        lens=_lens(teacher),
        submission_id=earlier.id,
        received=Money("1200.00"),
        disposition=None,
        carried_by_enrollment_id=None,
        credit_to_enrollment_id=None,
        note=None,
    )
    second_student = account_factory()
    second = _student_seat(owner_session, teacher, "Rahim", second_student)
    _pay(
        owner_session,
        teacher,
        StudentLens(account_id=second_student),
        [second],
        "1200.00",
        " 8n7k2qx ",
    )

    [item] = verification_queue(restricted_session, lens=_lens(teacher)).pending

    assert item.duplicate_of is not None
    assert item.duplicate_of.submission_id == earlier.id
    assert item.duplicate_of.display_name == "Sakib"
    assert item.duplicate_of.status == "approved"
    assert item.duplicate_of.amount == Money("1200.00")


def test_a_guardian_submitted_payment_says_so_with_the_number_on_record(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Name a guardian submitter with the number the teacher typed.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        guardian_phone="+8801711234567",
        student_decision="accepted",
        guardian_decision="accepted",
    )
    charge_period(owner_session, enrollment_id=seat, period=PERIOD, amount="1200.00")
    _pay(owner_session, teacher, GuardianLens(account_id=guardian), [seat], "1200.00")

    [item] = verification_queue(restricted_session, lens=_lens(teacher)).pending

    assert item.submitted_by == "guardian"
    assert item.submitter_phone == "+8801711234567"
