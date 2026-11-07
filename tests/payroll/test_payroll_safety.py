"""Payroll carries the protections the older money paths have [audit C-30].

Three gaps, each a way to pay a salary wrongly with nothing stopping it:

* the overpay guard in ``pay`` had only sequential tests, so nothing
  proved two payments at once cannot both pass the remaining check;
* a payment's retry key was looked up without the line it pays, so a
  key reused on another line returned that line unchanged and paid
  nothing, reporting success;
* "approval freezes the line" lived in Python alone, while the ledger,
  expenses and extra fees are protected in the database too.
"""

from __future__ import annotations

import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Expense
from tests.payroll.test_payroll import Setup, _code, setup  # noqa: F401

WORKERS = 2


def _approved_office_line(setup: Setup) -> dict:  # noqa: F811
    """Draw the month and approve the receptionist's 8000.00 line.

    :param setup: The arrangement
    :return: The line, as drawn
    """
    line = setup.line_of(setup.draw(), setup.office_staff)
    approved = setup.post(f"/v1/centre/payroll/lines/{line['line_id']}/approve")
    assert approved.status_code == 200, approved.text  # type: ignore[attr-defined]
    return line


def test_two_payments_at_once_cannot_both_pass_the_remaining_check(
    setup: Setup,  # noqa: F811
) -> None:
    """5000.00 twice against 8000.00: exactly one is paid.

    :param setup: The arrangement
    :return: None
    """
    line = _approved_office_line(setup)
    path = f"/v1/centre/payroll/lines/{line['line_id']}/payments"
    headers = [setup.centre.headers() for _ in range(WORKERS)]
    barrier = threading.Barrier(WORKERS)
    outcomes: list[int] = []
    guard = threading.Lock()

    def pay(header: dict[str, str]) -> None:
        """Pay 5000.00 under a fresh key.

        :param header: This worker's authorization
        :return: None
        """
        body = {"amount": "5000.00", "client_mutation_id": str(uuid.uuid4())}
        barrier.wait(timeout=30)
        response = setup.centre.client.post(path, json=body, headers=header)
        with guard:
            outcomes.append(response.status_code)

    threads = [threading.Thread(target=pay, args=(h,)) for h in headers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)

    assert sorted(outcomes) == [200, 409]
    paid = setup.centre.session.scalar(
        sa.select(sa.func.count())
        .select_from(Expense)
        .where(Expense.salary_line_id == uuid.UUID(line["line_id"]))
    )
    assert paid == 1


def test_a_retry_key_reused_on_another_line_is_refused_not_ignored(
    setup: Setup,  # noqa: F811
) -> None:
    """A key that paid one line cannot report success on another.

    :param setup: The arrangement
    :return: None
    """
    lines = setup.draw()
    office = setup.line_of(lines, setup.office_staff)
    teacher = setup.line_of(lines, setup.teacher_staff)
    for line in (office, teacher):
        setup.post(f"/v1/centre/payroll/lines/{line['line_id']}/approve")
    key = str(uuid.uuid4())
    first = setup.post(
        f"/v1/centre/payroll/lines/{office['line_id']}/payments",
        {"amount": "1000.00", "client_mutation_id": key},
    )
    assert first.status_code == 200, first.text  # type: ignore[attr-defined]

    reused = setup.post(
        f"/v1/centre/payroll/lines/{teacher['line_id']}/payments",
        {"amount": "1000.00", "client_mutation_id": key},
    )

    assert reused.status_code == 409, reused.text  # type: ignore[attr-defined]
    assert _code(reused) == "MUTATION_ID_ALREADY_USED"


def test_the_database_refuses_to_rewrite_an_approved_line(
    setup: Setup,  # noqa: F811
    restricted_session: Session,
) -> None:
    """The application role cannot change a frozen line's amounts.

    :param setup: The arrangement
    :param restricted_session: The application's role
    :return: None
    """
    line = _approved_office_line(setup)

    with pytest.raises(DBAPIError) as refusal:
        restricted_session.execute(
            sa.text("UPDATE salary_line SET rate = 1 WHERE id = :id"),
            {"id": line["line_id"]},
        )
    assert "salary_line_frozen" in str(refusal.value)
    restricted_session.rollback()


def test_the_database_refuses_an_adjustment_on_an_approved_line(
    setup: Setup,  # noqa: F811
    restricted_session: Session,
) -> None:
    """Nothing is added to a line after it is approved.

    :param setup: The arrangement
    :param restricted_session: The application's role
    :return: None
    """
    line = _approved_office_line(setup)

    with pytest.raises(DBAPIError) as refusal:
        restricted_session.execute(
            sa.text(
                "INSERT INTO salary_adjustment "
                "(id, salary_line_id, kind, label, amount, created_at) "
                "VALUES (gen_random_uuid(), :line, 'addition', 'Bonus', 100, now())"
            ),
            {"line": line["line_id"]},
        )
    assert "salary_line_frozen" in str(refusal.value)
    restricted_session.rollback()
