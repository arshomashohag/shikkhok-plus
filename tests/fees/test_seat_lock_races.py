"""Two different payments on one seat, approved at once, settle once.

**The existing race test covers one submission approved twice; this is
the other half** [audit C-03]. Two DIFFERENT submissions covering the
same child -- a guardian and a student each reporting, or a sibling
payment beside an individual one -- each pass their own submission's
guard. Before the seat lock, each derived the month as still owed from
the same snapshot and each wrote a full receipt against it: the month
was receipted twice, and the per-cycle zero floor discarded the surplus
instead of turning it into credit.

Real threads, real PostgreSQL, the real route; the assertion is on the
outcome: every taka received is accounted for exactly once.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.fees.balances import derive_for_enrollment
from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer
from tests.fees.conftest import add_method, charge_period

WORKERS = 2


def test_two_payments_on_one_seat_never_receipt_a_month_twice(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """One month owed 1000, two 1000 payments: 1000 receipted, 1000 credit.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Tania",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    charge_period(owner_session, enrollment_id=seat, period="2026-10", amount="1000.00")
    method = add_method(owner_session, teacher.owner_id)
    submissions = []
    for reference in ("FIRST111", "SECOND22"):
        submitted = api_client.post(
            "/v1/payments",
            json={
                "enrollment_ids": [str(seat)],
                "payment_method_id": str(method),
                "amount": "1000.00",
                "paid_on": bangladesh_today().isoformat(),
                "transaction_id": reference,
            },
            headers=bearer(owner_session, guardian),
        )
        assert submitted.status_code == 201, submitted.text
        submissions.append(submitted.json()["submission_id"])

    barrier = threading.Barrier(WORKERS)
    statuses: list[int] = []
    guard = threading.Lock()

    def approve(submission_id: str) -> None:
        """Approve one submission in full.

        :param submission_id: The submission
        :return: None
        """
        header = bearer(owner_session, teacher.account_id)
        barrier.wait(timeout=30)
        response = api_client.post(
            f"/v1/payments/{submission_id}/approval",
            json={"received_amount": "1000.00"},
            headers=header,
        )
        with guard:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=approve, args=(s,)) for s in submissions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)
    assert statuses == [200, 200]

    receipted = restricted_session.scalar(
        sa.text(
            "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
            "WHERE enrollment_id = :seat AND period = '2026-10' "
            "AND kind = 'receipt'"
        ),
        {"seat": seat},
    )
    assert Money(receipted) == Money("1000.00")
    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_outstanding == Money.ZERO
    assert derived.available_credit == Money("1000.00")
