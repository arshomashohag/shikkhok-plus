"""The payment queue is reachable through its real route.

The queue route shares a prefix with ``/claims/{claim_id}``, which
parses its segment as a uuid. Declared in the wrong order, "queue" would
reach that route first and be refused with a 422 -- a defect no
service-level test can see.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.authz.lenses import StudentLens
from app.fees.ledger_writer import append_entry
from app.fees.submissions import PaymentDraft, submit_payment
from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll
from tests.fees.conftest import add_method


@pytest.fixture
def client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


def _bearer(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account.

    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


def _pending_payment(
    session: Session, teacher: TeacherFixture, student: uuid.UUID
) -> uuid.UUID:
    """Charge a seat 1200 and report a payment of 800 against it.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The payer's account
    :return: The submission id
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    append_entry(
        session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1200.00"),
    )
    session.commit()
    return submit_payment(
        session,
        lens=StudentLens(account_id=student),
        draft=PaymentDraft(
            enrollment_ids=(seat,),
            payment_method_id=add_method(session, teacher.owner_id),
            cash=False,
            amount=Money("800.00"),
            paid_on=bangladesh_today(),
            transaction_id="TX-1",
            from_account=None,
            note=None,
        ),
    ).id


def test_the_queue_route_answers_with_the_servers_figures(
    client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Money crosses as strings, and the comparison is named.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    submission = _pending_payment(owner_session, teacher, student)

    response = client.get(
        "/v1/claims/queue", headers=_bearer(owner_session, teacher.account_id)
    )

    assert response.status_code == 200, response.text
    [item] = response.json()["pending"]
    assert item["submission_id"] == str(submission)
    assert (item["owed_together"], item["comparison"], item["difference"]) == (
        "1200.00",
        "short",
        "400.00",
    )


def test_a_student_cannot_read_the_teachers_queue(
    client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The queue resolves a teacher lens; a student has none.

    :param client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    _pending_payment(owner_session, teacher, student)

    response = client.get("/v1/claims/queue", headers=_bearer(owner_session, student))

    assert response.status_code == 403
