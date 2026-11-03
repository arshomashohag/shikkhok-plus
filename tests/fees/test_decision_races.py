"""Two approvals racing on one submission credit the payment once.

**The guard moved from the claim to the submission.** The decision is
claimed by a conditional ``UPDATE payment_submission SET status = ...
WHERE id = ... AND status = 'pending'``; the loser's update matches no
row and is refused with a 409, before it writes a single entry.

Real threads against real PostgreSQL through the real route, asserting
the outcome: one acceptance, one conflict, and one receipt per child.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer
from tests.fees.conftest import add_method, charge_period

WORKERS = 2


def test_concurrent_approvals_credit_once(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Exactly one 200 and one 409, and the receipts are written once.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seats = [
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=name,
            guardian_account_id=guardian,
            guardian_decision="accepted",
        )
        for name in ("Tania", "Tanvir")
    ]
    for seat in seats:
        charge_period(
            owner_session, enrollment_id=seat, period="2026-10", amount="1000.00"
        )
    method = add_method(owner_session, teacher.owner_id)
    submitted = api_client.post(
        "/v1/payments",
        json={
            "enrollment_ids": [str(seat) for seat in seats],
            "payment_method_id": str(method),
            "amount": "2000.00",
            "paid_on": bangladesh_today().isoformat(),
            "transaction_id": "RACE123",
        },
        headers=bearer(owner_session, guardian),
    )
    assert submitted.status_code == 201, submitted.text
    url = f"/v1/payments/{submitted.json()['submission_id']}/approval"
    headers = [bearer(owner_session, teacher.account_id) for _ in range(WORKERS)]

    barrier = threading.Barrier(WORKERS)
    outcomes: list[tuple[int, str | None]] = []
    lock = threading.Lock()

    def attempt(header: dict[str, str]) -> None:
        """Approve once, recording the status and any error code.

        :param header: This worker's authorization header
        :return: None
        """
        barrier.wait(timeout=30)
        response = api_client.post(
            url, json={"received_amount": "2000.00"}, headers=header
        )
        code = None if response.status_code == 200 else response.json()["error"]["code"]
        with lock:
            outcomes.append((response.status_code, code))

    threads = [threading.Thread(target=attempt, args=(h,)) for h in headers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert sorted(outcomes, key=lambda o: o[0]) == [
        (200, None),
        (409, "PAYMENT_ALREADY_DECIDED"),
    ]
    receipts = restricted_session.execute(
        sa.text(
            "SELECT enrollment_id, coalesce(sum(amount), 0) FROM ledger_entry "
            "WHERE enrollment_id = ANY(:ids) AND kind = 'receipt' "
            "GROUP BY enrollment_id"
        ),
        {"ids": seats},
    ).all()
    assert {row[0]: Money(row[1]) for row in receipts} == {
        seat: Money("1000.00") for seat in seats
    }
