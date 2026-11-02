"""A retried payment submission records the payment once [PA-DB-1].

**The failure this closes is a timed-out-but-committed submit.** The
family's phone loses the 201, the app retries, and before the replay key
the retry recorded a second pending claim per child for money sent once
-- which the teacher then sees as two payments to verify, and which, if
both are approved, is a receipt for money that never arrived.

**Written test-first**: the expected outcome of every case is fixed by
the contract (same account + same ``client_mutation_id`` returns the
original submission with the original status code and writes nothing),
and a wrong answer is a money error. The contract is the one the Android
client is built against, so these tests pin it from the server side:

- a replay returns the same submission and writes no second row;
- concurrent replays on two connections still produce exactly one row;
- **the constraint is the guarantee**, proven by blinding the fast-path
  lookup and replaying anyway;
- the same id with a different body is a conflict, not a replay;
- an omitted id keeps the old behaviour, for builds that send none;
- two accounts may use the same UUID, because uniqueness is per account.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.local_time import bangladesh_today
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer
from tests.fees.conftest import add_method, charge_period

WORKERS = 2


def _seat(
    session: Session, teacher: TeacherFixture, guardian: uuid.UUID, name: str
) -> uuid.UUID:
    """Seat one child whose guardian accepted, owing 1000.00 for October.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param guardian: The guardian's account
    :param name: The teacher-typed name
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name=name,
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    charge_period(session, enrollment_id=seat, period="2026-10", amount="1000.00")
    return seat


def _body(
    seats: list[uuid.UUID],
    method: uuid.UUID,
    mutation_id: uuid.UUID | None,
    **overrides: object,
) -> dict[str, object]:
    """Build a payment body, optionally carrying a replay key.

    :param seats: The children covered
    :param method: The method paid to
    :param mutation_id: The replay key, or None to omit the field
    :param overrides: Fields to replace
    :return: The JSON body
    """
    body: dict[str, object] = {
        "enrollment_ids": [str(seat) for seat in seats],
        "payment_method_id": str(method),
        "amount": "1000.00",
        "paid_on": bangladesh_today().isoformat(),
        "transaction_id": "9KD7Q2XL1M",
        "note": "October fee",
    }
    if mutation_id is not None:
        body["client_mutation_id"] = str(mutation_id)
    body.update(overrides)
    return body


def _submissions(session: Session, account: uuid.UUID) -> int:
    """Count one account's submissions.

    :param session: A reading session
    :param account: The submitting account
    :return: The count
    """
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM payment_submission "
                "WHERE submitted_by_account_id = :account"
            ),
            {"account": account},
        ).scalar_one()
    )


def _claims(session: Session, seats: list[uuid.UUID]) -> int:
    """Count the claims on some seats.

    :param session: A reading session
    :param seats: The seats
    :return: The count
    """
    return int(
        session.execute(
            sa.text(
                "SELECT count(*) FROM payment_claim WHERE enrollment_id = ANY(:ids)"
            ),
            {"ids": seats},
        ).scalar_one()
    )


def test_a_replay_returns_the_original_and_writes_nothing(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Same account, same id, same body: one submission, the same response.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seats = [
        _seat(owner_session, teacher, guardian, "Tania"),
        _seat(owner_session, teacher, guardian, "Tanvir"),
    ]
    method = add_method(owner_session, teacher.owner_id)
    body = _body(seats, method, uuid.uuid4(), amount="2000.00")
    headers = bearer(owner_session, guardian)

    first = api_client.post("/v1/payments", json=body, headers=headers)
    again = api_client.post("/v1/payments", json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json() == first.json()
    assert _submissions(restricted_session, guardian) == 1
    assert _claims(restricted_session, seats) == 2
    # The teacher is told once, not once per retry.
    told = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM notification WHERE account_id = :teacher "
            "AND source_id = :submission"
        ),
        {
            "teacher": teacher.account_id,
            "submission": uuid.UUID(first.json()["submission_id"]),
        },
    ).scalar_one()
    assert told == 1


def test_concurrent_replays_on_two_connections_record_one_payment(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two simultaneous sends of one draft: both 201, one row, one id.

    Real threads through the real route, each on its own pooled
    connection. The fast-path lookup is blinded so BOTH requests reach
    the insert, which is the race the lookup alone cannot win: the
    loser's insert meets the winner's uncommitted row and must wait on
    the constraint, then read the winner back.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param monkeypatch: The patcher
    :return: None
    """
    import app.fees.submissions as submissions

    monkeypatch.setattr(submissions, "_fast_path_prior", lambda *_a, **_k: None)
    guardian = account_factory()
    seat = _seat(owner_session, teacher, guardian, "Tania")
    method = add_method(owner_session, teacher.owner_id)
    body = _body([seat], method, uuid.uuid4())
    headers = [bearer(owner_session, guardian) for _ in range(WORKERS)]

    barrier = threading.Barrier(WORKERS)
    outcomes: list[tuple[int, str]] = []
    lock = threading.Lock()

    def send(header: dict[str, str]) -> None:
        """Send the draft once and record the status and submission.

        :param header: This worker's authorization header
        :return: None
        """
        barrier.wait(timeout=30)
        response = api_client.post("/v1/payments", json=body, headers=header)
        with lock:
            outcomes.append(
                (response.status_code, response.json().get("submission_id", ""))
            )

    threads = [threading.Thread(target=send, args=(h,)) for h in headers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert [status for status, _ in outcomes] == [201, 201], outcomes
    assert len({submission for _, submission in outcomes}) == 1, outcomes
    assert _submissions(restricted_session, guardian) == 1
    assert _claims(restricted_session, [seat]) == 1


def test_the_constraint_not_the_lookup_is_the_guarantee(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the fast-path lookup blinded, a replay still writes nothing.

    Blinding the lookup is how a lost race looks from inside one
    request: both requests checked, neither found the other. If the
    service relied on the lookup, this would record a second payment.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param monkeypatch: The patcher
    :return: None
    """
    import app.fees.submissions as submissions

    guardian = account_factory()
    seat = _seat(owner_session, teacher, guardian, "Tania")
    method = add_method(owner_session, teacher.owner_id)
    body = _body([seat], method, uuid.uuid4())
    headers = bearer(owner_session, guardian)

    first = api_client.post("/v1/payments", json=body, headers=headers)
    assert first.status_code == 201, first.text

    monkeypatch.setattr(submissions, "_fast_path_prior", lambda *_a, **_k: None)
    again = api_client.post("/v1/payments", json=body, headers=headers)

    assert again.status_code == 201, again.text
    assert again.json()["submission_id"] == first.json()["submission_id"]
    assert _submissions(restricted_session, guardian) == 1
    assert _claims(restricted_session, [seat]) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "900.00"},
        {"transaction_id": "OTHERREF01"},
        {"note": "A different note"},
        {"paid_on": "2026-10-01"},
    ],
    ids=["amount", "reference", "note", "date"],
)
def test_the_same_id_with_a_different_body_is_a_conflict(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    change: dict[str, object],
) -> None:
    """A reused id naming a different payment is refused, not answered.

    Returning the original here would tell the family a payment of a
    different amount or reference was recorded when it was not.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param change: The field that differs on the second send
    :return: None
    """
    guardian = account_factory()
    seat = _seat(owner_session, teacher, guardian, "Tania")
    method = add_method(owner_session, teacher.owner_id)
    key = uuid.uuid4()
    headers = bearer(owner_session, guardian)

    first = api_client.post(
        "/v1/payments", json=_body([seat], method, key), headers=headers
    )
    second = api_client.post(
        "/v1/payments", json=_body([seat], method, key, **change), headers=headers
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    error = second.json()["error"]
    assert error["code"] == "MUTATION_ID_ALREADY_USED"
    assert error["message_key"] == "fees.payment.mutation_id_already_used"
    assert error["retryable"] is False
    assert _submissions(restricted_session, guardian) == 1


def test_the_same_id_covering_different_children_is_a_conflict(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The children covered are part of what a replay must match.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    tania = _seat(owner_session, teacher, guardian, "Tania")
    tanvir = _seat(owner_session, teacher, guardian, "Tanvir")
    method = add_method(owner_session, teacher.owner_id)
    key = uuid.uuid4()
    headers = bearer(owner_session, guardian)

    first = api_client.post(
        "/v1/payments", json=_body([tania], method, key), headers=headers
    )
    second = api_client.post(
        "/v1/payments", json=_body([tanvir], method, key), headers=headers
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert _submissions(restricted_session, guardian) == 1


def test_an_omitted_id_keeps_the_old_behaviour(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A build that sends no id is not deduplicated and is not refused.

    Two identical bodies without a key are two reports, as before: the
    server cannot tell a retry from a second payment of the same amount,
    which is exactly why the key exists.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _seat(owner_session, teacher, guardian, "Tania")
    method = add_method(owner_session, teacher.owner_id)
    body = _body([seat], method, None)
    headers = bearer(owner_session, guardian)

    first = api_client.post("/v1/payments", json=body, headers=headers)
    second = api_client.post("/v1/payments", json=body, headers=headers)

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["submission_id"] != second.json()["submission_id"]
    assert _submissions(restricted_session, guardian) == 2
    stored = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM payment_submission "
            "WHERE submitted_by_account_id = :account "
            "AND client_mutation_id IS NULL"
        ),
        {"account": guardian},
    ).scalar_one()
    assert stored == 2


def test_two_accounts_may_use_the_same_id(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Another account's identical UUID is no duplicate at all.

    A lookup scoped by the key alone would hand guardian B guardian A's
    submission -- a silent success disclosing another family's payment.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    first_guardian, second_guardian = account_factory(), account_factory()
    first_seat = _seat(owner_session, teacher, first_guardian, "Tania")
    second_seat = _seat(owner_session, teacher, second_guardian, "Rahim")
    method = add_method(owner_session, teacher.owner_id)
    key = uuid.uuid4()

    first = api_client.post(
        "/v1/payments",
        json=_body([first_seat], method, key),
        headers=bearer(owner_session, first_guardian),
    )
    second = api_client.post(
        "/v1/payments",
        json=_body([second_seat], method, key),
        headers=bearer(owner_session, second_guardian),
    )

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["submission_id"] != second.json()["submission_id"]
    assert _submissions(restricted_session, first_guardian) == 1
    assert _submissions(restricted_session, second_guardian) == 1


def test_a_replay_after_the_decision_returns_the_decided_submission(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A late retry is still a replay, and reports where it now stands.

    The retry may arrive after the teacher approved, and the original
    must not be re-validated into a refusal or re-recorded as new. The
    status is the submission's current one rather than a hardcoded
    ``pending``, so the app is not told an approved payment still waits.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's role, for the counts
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _seat(owner_session, teacher, guardian, "Tania")
    method = add_method(owner_session, teacher.owner_id)
    body = _body([seat], method, uuid.uuid4())
    headers = bearer(owner_session, guardian)

    first = api_client.post("/v1/payments", json=body, headers=headers)
    assert first.status_code == 201, first.text
    approved = api_client.post(
        f"/v1/payments/{first.json()['submission_id']}/approval",
        json={"received_amount": "1000.00"},
        headers=bearer(owner_session, teacher.account_id),
    )
    assert approved.status_code == 200, approved.text

    again = api_client.post("/v1/payments", json=body, headers=headers)

    assert again.status_code == 201, again.text
    assert again.json()["submission_id"] == first.json()["submission_id"]
    assert again.json()["status"] == "approved"
    assert _submissions(restricted_session, guardian) == 1
