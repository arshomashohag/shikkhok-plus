"""Payroll at a centre [P1]: draw, adjust, approve, pay, and My pay.

Written before the code. Money-path and authorization outcomes throughout,
so the team's test-first predicate holds. Every figure is computed in the
test from what it arranges:

* Drawing a month draws one line per paid staff member working that
  month, and drawing it again draws nothing.
* A draft per-class line counts the classes that person HELD in the month
  at that centre: not cancelled ones, not another teacher's.
* Approval freezes the count and the base, so a class held later never
  reprices an approved salary; adjustments are refused once approved.
* A payment is an expense against the line; paid and remaining are
  derived; paying past what is owed is refused; a resend is a replay;
  voiding the expense restores what remains.
* A centre teacher reads their own approved pay and nobody else's.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Expense, SalaryLine, Staff
from app.db.models import Session as ClassSession
from app.local_time import bangladesh_today
from tests.batches.conftest import make_teacher
from tests.centres.test_class_teacher import _account, _teacher
from tests.conftest import bearer
from tests.scheduling.test_scheduling import Centre

TODAY = bangladesh_today()
PERIOD = TODAY.strftime("%Y-%m")
FIRST_OF_MONTH = TODAY.replace(day=1)


def _code(response: object) -> str:
    """Read an error code.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


class Setup:
    """A centre with a per-class teacher and a monthly receptionist.

    :ivar centre: The centre
    :ivar account: The teacher's account
    :ivar member: The teacher's membership
    :ivar teacher_staff: The teacher's staff record, 500.00 a class
    :ivar office_staff: The receptionist's record, 8000.00 a month
    :ivar batch: A batch the teacher teaches
    """

    def __init__(self, client: TestClient, session: Session) -> None:
        """Arrange it.

        :param client: The test client
        :param session: An arranging session
        """
        self.centre = Centre(client, session)
        self.account = _account(session)
        self.member = _teacher(self.centre, self.account)
        self.teacher_staff = self._staff(
            kind="teacher", basis="per_class", rate="500.00", member_id=self.member
        )
        self.office_staff = self._staff(kind="other", basis="monthly", rate="8000.00")
        self.batch = self.centre.batch("Class 9")

    def _staff(self, **values: object) -> uuid.UUID:
        """Arrange one staff record joined before the month.

        :param values: Columns overriding the defaults
        :return: The record id
        """
        from app.money import Money

        rate = values.pop("rate", None)
        row = Staff(
            owner_id=self.centre.owner_id,
            kind=values.pop("kind"),
            display_name=f"Person {uuid.uuid4().hex[:4]}",
            pay_basis=values.pop("basis"),
            pay_rate=None if rate is None else Money(str(rate)),
            joined_on=FIRST_OF_MONTH - dt.timedelta(days=60),
            created_at=dt.datetime.now(tz=dt.UTC),
            **values,
        )
        self.centre.session.add(row)
        self.centre.session.commit()
        return row.id

    def held_class(
        self,
        day: dt.date,
        *,
        start: str = "16:00",
        teacher: uuid.UUID | None = None,
        status: str = "held",
    ) -> None:
        """Arrange one class in the batch.

        :param day: Its date
        :param start: Its start time
        :param teacher: Its teacher, the arranged one by default
        :param status: Its status
        """
        hour, minute = (int(part) for part in start.split(":"))
        self.centre.session.add(
            ClassSession(
                batch_id=self.batch,
                date=day,
                start_time=dt.time(hour, minute),
                end_time=dt.time(hour + 1, minute),
                status=status,
                origin="ad_hoc",
                attendance_version=0,
                topic_version=0,
                created_at=dt.datetime.now(tz=dt.UTC),
                teacher_member_id=teacher or self.member,
                assignment_source="override",
            )
        )
        self.centre.session.commit()

    def draw(self) -> list[dict]:
        """Draw this month's lines as the manager.

        :return: The month's lines
        """
        response = self.centre.client.post(
            f"/v1/centre/payroll/{PERIOD}/lines", headers=self.centre.headers()
        )
        assert response.status_code == 200, response.text
        lines: list[dict] = response.json()
        return lines

    def line_of(self, lines: list[dict], staff_id: uuid.UUID) -> dict:
        """Pick one person's line.

        :param lines: The month's lines
        :param staff_id: The person
        :return: Their line
        """
        return next(line for line in lines if line["staff_id"] == str(staff_id))

    def post(self, path: str, body: object | None = None) -> object:
        """POST as the manager.

        :param path: The path
        :param body: The JSON body, if any
        :return: The response
        """
        return self.centre.client.post(path, json=body, headers=self.centre.headers())


@pytest.fixture
def setup(api_client: TestClient, owner_session: Session) -> Setup:
    """Arrange a centre with two paid staff.

    :param api_client: The test client
    :param owner_session: An arranging session
    :return: The arrangement
    """
    return Setup(api_client, owner_session)


def test_drawing_a_month_draws_one_line_per_paid_person_once(setup: Setup) -> None:
    """Unpaid staff and those who left before the month get none."""
    setup._staff(kind="other", basis="none")
    left = setup._staff(kind="other", basis="monthly", rate="5000.00")
    setup.centre.session.execute(
        sa.update(Staff)
        .where(Staff.id == left)
        .values(left_on=FIRST_OF_MONTH - dt.timedelta(days=1))
    )
    setup.centre.session.commit()

    lines = setup.draw()
    assert {line["staff_id"] for line in lines} == {
        str(setup.teacher_staff),
        str(setup.office_staff),
    }
    again = setup.draw()
    assert len(again) == 2
    assert (
        setup.centre.session.scalar(sa.select(sa.func.count()).select_from(SalaryLine))
        == 2
    )


def test_a_draft_per_class_line_counts_only_classes_held_by_that_teacher(
    setup: Setup,
) -> None:
    """Three held classes at 500.00 is 1500.00; cancelled and others' don't count."""
    other = _teacher(setup.centre, _account(setup.centre.session))
    for offset, start in ((0, "08:00"), (0, "10:00"), (1, "08:00")):
        setup.held_class(FIRST_OF_MONTH + dt.timedelta(days=offset), start=start)
    setup.held_class(FIRST_OF_MONTH, start="12:00", status="cancelled")
    setup.held_class(FIRST_OF_MONTH, start="14:00", teacher=other)

    line = setup.line_of(setup.draw(), setup.teacher_staff)
    assert (line["status"], line["classes_held"], line["base"]) == (
        "draft",
        3,
        "1500.00",
    )
    office = setup.line_of(setup.draw(), setup.office_staff)
    assert (office["base"], office["owed"]) == ("8000.00", "8000.00")


def test_adjustments_move_what_is_owed_and_cannot_take_it_below_zero(
    setup: Setup,
) -> None:
    """8000.00 + 500.00 bonus - 1000.00 advance = 7500.00; then too much is refused."""
    line = setup.line_of(setup.draw(), setup.office_staff)
    path = f"/v1/centre/payroll/lines/{line['line_id']}/adjustments"
    bonus = setup.post(path, {"kind": "addition", "label": "Bonus", "amount": "500.00"})
    advance = setup.post(
        path, {"kind": "deduction", "label": "Advance recovered", "amount": "1000.00"}
    )
    assert bonus.status_code == advance.status_code == 200, advance.text  # type: ignore[attr-defined]
    assert advance.json()["owed"] == "7500.00"  # type: ignore[attr-defined]

    too_much = setup.post(
        path, {"kind": "deduction", "label": "Mistake", "amount": "7500.01"}
    )
    assert too_much.status_code == 400, too_much.text  # type: ignore[attr-defined]
    assert _code(too_much) == "SALARY_BELOW_ZERO"

    removed = setup.centre.client.delete(
        f"{path}/{bonus.json()['adjustments'][0]['adjustment_id']}",  # type: ignore[attr-defined]
        headers=setup.centre.headers(),
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["owed"] == "7000.00"


def test_approval_freezes_the_count_and_closes_adjustments(setup: Setup) -> None:
    """A class held after approval does not reprice the salary."""
    setup.held_class(FIRST_OF_MONTH)
    line = setup.line_of(setup.draw(), setup.teacher_staff)
    approved = setup.post(f"/v1/centre/payroll/lines/{line['line_id']}/approve")
    assert approved.status_code == 200, approved.text  # type: ignore[attr-defined]
    assert approved.json()["base"] == "500.00"  # type: ignore[attr-defined]

    setup.held_class(FIRST_OF_MONTH, start="18:00")
    after = setup.line_of(setup.draw(), setup.teacher_staff)
    assert (after["status"], after["classes_held"], after["base"]) == (
        "approved",
        1,
        "500.00",
    )
    refused = setup.post(
        f"/v1/centre/payroll/lines/{line['line_id']}/adjustments",
        {"kind": "addition", "label": "Late bonus", "amount": "100.00"},
    )
    assert refused.status_code == 409, refused.text  # type: ignore[attr-defined]
    assert _code(refused) == "SALARY_APPROVED"


def test_paying_records_an_expense_and_tracks_what_remains(setup: Setup) -> None:
    """8000.00 approved; 3000.00 paid leaves 5000.00; the resend is a replay."""
    line = setup.line_of(setup.draw(), setup.office_staff)
    path = f"/v1/centre/payroll/lines/{line['line_id']}/payments"
    unapproved = setup.post(
        path, {"amount": "1000.00", "client_mutation_id": str(uuid.uuid4())}
    )
    assert unapproved.status_code == 409, unapproved.text  # type: ignore[attr-defined]
    assert _code(unapproved) == "SALARY_NOT_APPROVED"

    setup.post(f"/v1/centre/payroll/lines/{line['line_id']}/approve")
    body = {"amount": "3000.00", "client_mutation_id": str(uuid.uuid4())}
    paid = setup.post(path, body)
    again = setup.post(path, body)
    assert paid.status_code == again.status_code == 200, again.text  # type: ignore[attr-defined]
    assert (paid.json()["paid"], paid.json()["remaining"]) == ("3000.00", "5000.00")  # type: ignore[attr-defined]
    assert again.json()["remaining"] == "5000.00"  # type: ignore[attr-defined]

    expense = setup.centre.session.scalars(
        sa.select(Expense).where(Expense.salary_line_id == uuid.UUID(line["line_id"]))
    ).one()
    assert expense.category == "salary"

    over = setup.post(
        path, {"amount": "5000.01", "client_mutation_id": str(uuid.uuid4())}
    )
    assert over.status_code == 409, over.text  # type: ignore[attr-defined]
    assert _code(over) == "SALARY_OVERPAID"

    voided = setup.post(f"/v1/expenses/{expense.id}/void", {"reason": "Wrong amount"})
    assert voided.status_code == 200, voided.text  # type: ignore[attr-defined]
    restored = setup.line_of(setup.draw(), setup.office_staff)
    assert restored["remaining"] == "8000.00"


def test_my_pay_shows_my_approved_lines_and_nobody_elses(setup: Setup) -> None:
    """The teacher sees their approved line with its adjustments and payments."""
    setup.held_class(FIRST_OF_MONTH)
    lines = setup.draw()
    mine = setup.line_of(lines, setup.teacher_staff)
    teacher_headers = bearer(setup.centre.session, setup.account)

    assert setup.centre.client.get("/v1/me/pay", headers=teacher_headers).json() == []

    setup.post(
        f"/v1/centre/payroll/lines/{mine['line_id']}/adjustments",
        {"kind": "addition", "label": "Bonus", "amount": "100.00"},
    )
    setup.post(f"/v1/centre/payroll/lines/{mine['line_id']}/approve")
    office = setup.line_of(lines, setup.office_staff)
    setup.post(f"/v1/centre/payroll/lines/{office['line_id']}/approve")
    setup.post(
        f"/v1/centre/payroll/lines/{mine['line_id']}/payments",
        {"amount": "200.00", "client_mutation_id": str(uuid.uuid4())},
    )

    pay = setup.centre.client.get("/v1/me/pay", headers=teacher_headers)
    assert pay.status_code == 200, pay.text
    assert [line["line_id"] for line in pay.json()] == [mine["line_id"]]
    only = pay.json()[0]
    assert (only["owed"], only["paid"], only["remaining"]) == (
        "600.00",
        "200.00",
        "400.00",
    )
    assert [a["label"] for a in only["adjustments"]] == ["Bonus"]
    assert len(only["payments"]) == 1


def test_only_this_centres_manager_reaches_payroll(
    setup: Setup, api_client: TestClient, owner_session: Session
) -> None:
    """A solo tutor, another centre, and a centre teacher are refused."""
    line = setup.line_of(setup.draw(), setup.office_staff)

    tutor = make_teacher(owner_session)
    solo = api_client.get(
        f"/v1/centre/payroll/{PERIOD}", headers=bearer(owner_session, tutor.account_id)
    )
    assert solo.status_code == 409, solo.text
    assert _code(solo) == "NOT_A_CENTRE"

    other = Centre(api_client, owner_session)
    foreign = api_client.post(
        f"/v1/centre/payroll/lines/{line['line_id']}/approve", headers=other.headers()
    )
    assert foreign.status_code == 403, foreign.text

    teacher = api_client.get(
        f"/v1/centre/payroll/{PERIOD}",
        headers={
            **bearer(owner_session, setup.account),
            "X-Workspace-Id": str(setup.centre.owner_id),
        },
    )
    assert teacher.status_code == 403, teacher.text


def test_a_malformed_month_is_refused(setup: Setup) -> None:
    """The period is YYYY-MM."""
    response = setup.centre.client.get(
        "/v1/centre/payroll/2026-13", headers=setup.centre.headers()
    )
    assert response.status_code in (400, 422), response.text
