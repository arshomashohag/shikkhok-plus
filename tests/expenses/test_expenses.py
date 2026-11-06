"""Expenses and the monthly summary [0021].

Written before the code. Every figure is computed in the docstring from
what the test records, and a wrong answer is a money error the owner acts
on, so these meet the team's test-first predicate.

The summary is **cash basis**: collected is what was approved for
payments paid in the month, spent is what was spent in the month, and a
voided expense counts for nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import Expense
from app.local_time import bangladesh_today
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.fees.conftest import add_method, charge_period


def _record(
    client: TestClient, session: Session, teacher: TeacherFixture, **body: object
) -> object:
    """Record an expense as the teacher: 850 of printing today by default.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :param body: Fields overriding the default request
    :return: The response
    """
    request: dict[str, object] = {
        "category": "printing",
        "what": "Question paper printing",
        "amount": "850.00",
        "spent_on": bangladesh_today().isoformat(),
    }
    request.update(body)
    return client.post(
        "/v1/expenses", json=request, headers=bearer(session, teacher.account_id)
    )


def _id(response: object) -> str:
    """Read the expense id from a successful record.

    :param response: The response
    :return: The id
    """
    assert response.status_code == 201, response.text  # type: ignore[attr-defined]
    expense_id: str = response.json()["expense_id"]  # type: ignore[attr-defined]
    return expense_id


def _month(client: TestClient, session: Session, teacher: TeacherFixture) -> dict:
    """Read this month's expenses as the teacher.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :return: The body
    """
    month = bangladesh_today().strftime("%Y-%m")
    response = client.get(
        f"/v1/expenses?month={month}", headers=bearer(session, teacher.account_id)
    )
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


def _code(response: object) -> str:
    """Read the error code from an envelope.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def test_recorded_expenses_total_by_category(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """850 printing + 6000 rent + 300 printing = 7150; printing 1150, rent 6000.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    _id(_record(api_client, owner_session, teacher))
    _id(_record(api_client, owner_session, teacher, category="rent", amount="6000.00"))
    _id(_record(api_client, owner_session, teacher, amount="300.00", what="Stapler"))

    body = _month(api_client, owner_session, teacher)

    assert body["total"] == "7150.00"
    assert {c["category"]: c["total"] for c in body["by_category"]} == {
        "printing": "1150.00",
        "rent": "6000.00",
    }
    assert len(body["expenses"]) == 3


def test_a_voided_expense_stays_listed_and_counts_for_nothing(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Two 850 printings, one voided as a duplicate: 850 spent, both listed.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    _id(_record(api_client, owner_session, teacher))
    duplicate = _id(_record(api_client, owner_session, teacher))

    voided = api_client.post(
        f"/v1/expenses/{duplicate}/void",
        json={"reason": "Entered twice"},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert voided.status_code == 200, voided.text
    assert voided.json()["voided"] is True
    body = _month(api_client, owner_session, teacher)
    assert body["total"] == "850.00"
    assert [e["voided"] for e in body["expenses"]].count(True) == 1
    row = owner_session.get(Expense, uuid.UUID(duplicate))
    assert row is not None
    assert str(row.amount) == "850.00"
    assert row.void_reason == "Entered twice"


def test_voiding_twice_is_refused(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A voided expense cannot be voided again: 409, the first reason kept.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    expense = _id(_record(api_client, owner_session, teacher))
    headers = bearer(owner_session, teacher.account_id)
    api_client.post(
        f"/v1/expenses/{expense}/void", json={"reason": "a"}, headers=headers
    )

    again = api_client.post(
        f"/v1/expenses/{expense}/void", json={"reason": "b"}, headers=headers
    )

    assert again.status_code == 409
    assert _code(again) == "EXPENSE_ALREADY_VOIDED"


def test_another_teacher_neither_sees_nor_voids_an_expense(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """A stranger's month is empty and their void is the shared 403.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    expense = _id(_record(api_client, owner_session, teacher))
    stranger = make_teacher(owner_session, name="Chemistry")

    seen = _month(api_client, owner_session, stranger)
    void = api_client.post(
        f"/v1/expenses/{expense}/void",
        json={"reason": "not mine"},
        headers=bearer(owner_session, stranger.account_id),
    )

    assert seen["expenses"] == []
    assert void.status_code == 403


def test_a_resend_records_one_expense(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The same retry key twice: one expense, the same id; a different body is 409.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The teacher
    :return: None
    """
    key = str(uuid.uuid4())

    first = _id(_record(api_client, owner_session, teacher, client_mutation_id=key))
    second = _id(_record(api_client, owner_session, teacher, client_mutation_id=key))
    other = _record(
        api_client, owner_session, teacher, client_mutation_id=key, amount="900.00"
    )

    assert first == second
    assert other.status_code == 409  # type: ignore[attr-defined]
    assert restricted_session.scalar(sa.select(sa.func.count(Expense.id))) == 1


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("what", "   ", "EXPENSE_WHAT_REQUIRED"),
        ("spent_on", "2999-01-01", "EXPENSE_DATE_IN_FUTURE"),
        ("amount", "0.00", "EXPENSE_AMOUNT_NOT_POSITIVE"),
    ],
)
def test_an_expense_that_could_not_have_happened_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    field: str,
    value: str,
    code: str,
) -> None:
    """A blank description, a future date or a zero amount is a 400.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param field: The field made wrong
    :param value: Its wrong value
    :param code: The refusal expected
    :return: None
    """
    response = _record(api_client, owner_session, teacher, **{field: value})

    assert response.status_code == 400, response.text  # type: ignore[attr-defined]
    assert _code(response) == code


def test_an_expense_tagged_to_another_teachers_batch_is_refused(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Tagging a batch this owner does not own is a 400, and nothing is written.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    stranger = make_teacher(owner_session, name="Chemistry")

    response = _record(
        api_client, owner_session, teacher, batch_id=str(stranger.batch_id)
    )

    assert response.status_code == 400  # type: ignore[attr-defined]
    assert _code(response) == "EXPENSE_BATCH_NOT_FOUND"


@pytest.mark.parametrize(
    "statement",
    ["UPDATE expense SET amount = 1", "DELETE FROM expense"],
)
def test_the_application_role_cannot_rewrite_an_expense(
    api_client: TestClient,
    owner_session: Session,
    restricted_engine: Engine,
    teacher: TeacherFixture,
    statement: str,
) -> None:
    """Append-only: no amount rewritten and no row deleted by the app's role.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_engine: The application role's engine
    :param teacher: The teacher
    :param statement: The forbidden write
    :return: None
    """
    _id(_record(api_client, owner_session, teacher))

    with pytest.raises(sa.exc.ProgrammingError), restricted_engine.begin() as conn:
        conn.execute(sa.text(statement))


# --- the summary -----------------------------------------------------------


def _paid(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    amount: str,
    **purpose: object,
) -> None:
    """Record cash received for a seat, approved at once.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The teacher
    :param seat: The seat
    :param amount: The amount
    :param purpose: ``purpose`` and ``extra_fee_id`` for an extra fee
    :return: None
    """
    response = client.post(
        f"/v1/enrollments/{seat}/payments",
        json={"amount": amount, **{k: str(v) for k, v in purpose.items()}},
        headers=bearer(session, teacher.account_id),
    )
    assert response.status_code == 201, response.text


def test_the_summary_sets_what_came_in_against_what_went_out(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """In 1500 (1000 monthly + 500 exam), out 850, left 650 surplus; owed both ways.

    Two seats each charged 1000 for this month and a 500 exam fee. Rafi
    pays his month (1000) and his exam fee (500); Tania pays nothing.
    Spent: 850 printing, plus a voided 6000 that counts for nothing.

    * collected: monthly 1000, exam 500, total 1500
    * spent: 850, all printing
    * net: 1500 - 850 = 650, a surplus
    * still owed to the owner: monthly 1000 (Tania), extra 500 (Tania)
    * per exam fee: collected 500 against 850 tagged to it

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :param account_factory: Makes accounts
    :return: None
    """
    period = bangladesh_today().strftime("%Y-%m")
    seats = [
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            student_account_id=account_factory(),
            student_decision="accepted",
        )
        for name in ("Rafi", "Tania")
    ]
    for seat in seats:
        charge_period(
            owner_session, enrollment_id=seat, period=period, amount="1000.00"
        )
    add_method(owner_session, teacher.owner_id)
    fee = api_client.post(
        f"/v1/batches/{teacher.batch_id}/extra-fees",
        json={
            "purpose": "exam",
            "label": "Half-yearly exam fee",
            "amount": "500.00",
            "due_on": bangladesh_today().isoformat(),
        },
        headers=bearer(owner_session, teacher.account_id),
    ).json()["extra_fee_id"]
    _paid(api_client, owner_session, teacher, seats[0], "1000.00")
    _paid(
        api_client,
        owner_session,
        teacher,
        seats[0],
        "500.00",
        purpose="extra",
        extra_fee_id=fee,
    )
    _id(_record(api_client, owner_session, teacher, extra_fee_id=fee))
    voided = _id(
        _record(api_client, owner_session, teacher, category="rent", amount="6000.00")
    )
    api_client.post(
        f"/v1/expenses/{voided}/void",
        json={"reason": "wrong month"},
        headers=bearer(owner_session, teacher.account_id),
    )

    response = api_client.get(
        f"/v1/money/summary?month={period}",
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["collected"] == {
        "monthly": "1000.00",
        "exam": "500.00",
        "other": "0.00",
        "total": "1500.00",
    }
    assert body["spent_total"] == "850.00"
    assert {c["category"]: c["total"] for c in body["spent_by_category"]} == {
        "printing": "850.00"
    }
    assert (body["net"], body["net_kind"]) == ("650.00", "surplus")
    assert (body["owed_monthly"], body["owed_extra"]) == ("1000.00", "500.00")
    assert [(f["label"], f["collected"], f["spent"]) for f in body["extra_fees"]] == [
        ("Half-yearly exam fee", "500.00", "850.00")
    ]


def test_a_month_that_spent_more_than_it_took_is_a_deficit(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """Nothing collected, 850 spent: net 850, a deficit, never a negative string.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    _id(_record(api_client, owner_session, teacher))
    period = bangladesh_today().strftime("%Y-%m")

    body = api_client.get(
        f"/v1/money/summary?month={period}",
        headers=bearer(owner_session, teacher.account_id),
    ).json()

    assert (body["net"], body["net_kind"]) == ("850.00", "deficit")


def test_a_malformed_month_is_refused(
    api_client: TestClient, owner_session: Session, teacher: TeacherFixture
) -> None:
    """``2026-13`` is a 400 on both reads, not an empty month.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The teacher
    :return: None
    """
    headers = bearer(owner_session, teacher.account_id)

    expenses = api_client.get("/v1/expenses?month=2026-13", headers=headers)
    summary = api_client.get("/v1/money/summary?month=2026-13", headers=headers)

    assert (expenses.status_code, summary.status_code) == (400, 400)
    assert _code(expenses) == "MONTH_INVALID"
