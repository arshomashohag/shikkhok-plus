"""What T7's fee chips need beyond a status: days overdue and verifying.

**Written before the fields existed.** Both are money decisions shown to
a teacher about a named student: "৳3,600 · 68 days" and "Verifying
৳800". The expected values follow from the charges, due dates and claims
below without any implementation.

**Overdue counts from Bangladesh's date**, the same rule Today uses: a
period still owing whose due date has passed. The count runs from the
OLDEST such period, because that is how late the student is.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import FeeCycle
from app.fees import views
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.overdue import days_overdue, overdue_balance
from app.fees.verification import verify_claim
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll

TODAY = dt.date(2026, 10, 17)


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _seat(
    session: Session,
    teacher: TeacherFixture,
    student: uuid.UUID,
    charges: list[tuple[str, str, dt.date]],
) -> uuid.UUID:
    """Seat a student and charge each ``(period, amount, due)``.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The student's account
    :param charges: Period, amount and due date for each charge
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
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


def test_days_overdue_runs_from_the_oldest_unpaid_due_date() -> None:
    """September due 10 Sep and October due 10 Oct: 37 days, from September.

    :return: None
    """
    per_cycle = {"2026-09": Money("1200.00"), "2026-10": Money("1200.00")}
    due = {"2026-09": dt.date(2026, 9, 10), "2026-10": dt.date(2026, 10, 10)}

    assert days_overdue(per_cycle, due, TODAY) == 37
    assert overdue_balance(per_cycle, due, TODAY) == Money("2400.00")


def test_a_paid_or_not_yet_due_period_is_not_overdue() -> None:
    """Nothing owing, or owing but not yet due, is no days and no money.

    :return: None
    """
    per_cycle = {"2026-09": Money.ZERO, "2026-10": Money("1200.00")}
    due = {"2026-09": dt.date(2026, 9, 10), "2026-10": dt.date(2026, 10, 20)}

    assert days_overdue(per_cycle, due, TODAY) is None
    assert overdue_balance(per_cycle, due, TODAY) == Money.ZERO


def test_the_due_date_itself_is_not_yet_overdue() -> None:
    """Due today is due, not late.

    :return: None
    """
    per_cycle = {"2026-10": Money("1200.00")}

    assert days_overdue(per_cycle, {"2026-10": TODAY}, TODAY) is None


def test_the_batch_rows_carry_days_overdue(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The roster's fee chip reads "৳2,400 · 37 days".

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    _seat(
        owner_session,
        teacher,
        account_factory(),
        [
            ("2026-09", "1200.00", dt.date(2026, 9, 10)),
            ("2026-10", "1200.00", dt.date(2026, 10, 10)),
        ],
    )

    [row] = views.batch_fee_overview(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, today=TODAY
    )

    assert row.outstanding == Money("2400.00")
    assert row.days_overdue == 37
    assert row.verifying is None


def test_a_waiting_claim_reads_as_verifying_and_a_decided_one_does_not(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Show a waiting claim as verifying until the teacher decides it.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = _seat(
        owner_session, teacher, student, [("2026-10", "1200.00", dt.date(2026, 10, 20))]
    )
    claim = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("800.00"),
        channel="bKash",
        transaction_id="TX-1",
    )

    [waiting] = views.batch_fee_overview(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, today=TODAY
    )
    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("800.00"),
        shortfall_disposition="carried",
        verified_by_account_id=teacher.account_id,
    )
    restricted_session.expire_all()
    [decided] = views.batch_fee_overview(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id, today=TODAY
    )

    assert waiting.verifying == Money("800.00")
    assert decided.verifying is None
