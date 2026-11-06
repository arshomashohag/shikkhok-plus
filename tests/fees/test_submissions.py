"""Submitting a payment for one or several children, or with nothing owed.

**One submission per payment, one pending claim per child.** The family
reports what they sent once; the per-child ledger keeps doing its work
through the claims. Each claim's amount is a provisional share the
teacher's decision replaces.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens
from app.db.models import PaymentClaim, PaymentMethod, PaymentSubmission
from app.fees.ledger_writer import append_entry
from app.fees.submissions import PaymentDraft, submit_payment
from app.local_time import bangladesh_today
from app.money import Money
from app.notifications.inbox import inbox
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer


def _method(
    session: Session,
    owner_id: uuid.UUID,
    *,
    kind: str = "mobile",
    retired: bool = False,
) -> uuid.UUID:
    """Give an owner one payment method.

    :param session: An arranging session
    :param owner_id: The owner
    :param kind: ``mobile`` or ``bank``
    :param retired: Whether the method is already retired
    :return: The method id
    """
    now = dt.datetime.now(tz=dt.UTC)
    mobile = kind == "mobile"
    method = PaymentMethod(
        owner_id=owner_id,
        kind=kind,
        provider="bKash" if mobile else "City Bank",
        mobile_number="01711000000" if mobile else None,
        account_number=None if mobile else "1234567890",
        account_name=None if mobile else "Najma Akter",
        branch_name=None if mobile else "Dhanmondi",
        position=1,
        retired_at=now if retired else None,
        created_at=now,
        updated_at=now,
    )
    session.add(method)
    session.commit()
    return method.id


def _child(
    session: Session,
    batch_id: uuid.UUID,
    name: str,
    guardian: uuid.UUID,
    *,
    decision: str = "accepted",
) -> uuid.UUID:
    """Seat a child whose guardian holds the given decision.

    :param session: An arranging session
    :param batch_id: The batch
    :param name: The teacher-typed name
    :param guardian: The guardian's account
    :param decision: The guardian link's decision
    :return: The seat
    """
    return enroll(
        session,
        batch_id=batch_id,
        display_name=name,
        guardian_account_id=guardian,
        guardian_decision=decision,
    )


def _charge(session: Session, seat: uuid.UUID, period: str, amount: str) -> None:
    """Charge one period on a seat.

    :param session: An arranging session
    :param seat: The seat
    :param period: The period
    :param amount: The charge
    :return: None
    """
    append_entry(
        session, enrollment_id=seat, period=period, kind="charge", amount=Money(amount)
    )
    session.commit()


def _body(
    seats: list[uuid.UUID],
    method_id: uuid.UUID | None,
    amount: str = "1000.00",
    **overrides: object,
) -> dict[str, object]:
    """Build a payment request body.

    :param seats: The children covered
    :param method_id: The method paid to
    :param amount: The amount sent
    :param overrides: Fields to replace
    :return: The JSON body
    """
    body: dict[str, object] = {
        "enrollment_ids": [str(seat) for seat in seats],
        "payment_method_id": None if method_id is None else str(method_id),
        "amount": amount,
        "paid_on": bangladesh_today().isoformat(),
        "transaction_id": "9KD7Q2XL1M",
        "from_account": None,
        "note": "November fee",
    }
    body.update(overrides)
    return body


def _code(response: object) -> str:
    """Read the error code from an envelope.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def _claims(session: Session, submission_id: uuid.UUID) -> dict[str, PaymentClaim]:
    """Read a submission's claims keyed by the child's seat id.

    :param session: A reading session
    :param submission_id: The submission
    :return: Seat id string to claim
    """
    rows = session.scalars(
        sa.select(PaymentClaim).where(
            PaymentClaim.payment_submission_id == submission_id
        )
    )
    return {str(row.enrollment_id): row for row in rows}


def test_guardian_pays_for_two_children_in_one_submission(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two children, one submission, two claims linked to it.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    tania = _child(owner_session, teacher.batch_id, "Tania", guardian)
    tanvir = _child(owner_session, teacher.batch_id, "Tanvir", guardian)
    _charge(owner_session, tania, "2026-10", "1000.00")
    _charge(owner_session, tanvir, "2026-10", "1000.00")
    method = _method(owner_session, teacher.owner_id)

    response = api_client.post(
        "/v1/payments",
        json=_body([tanvir, tania], method, "2000.00"),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 201
    submission_id = uuid.UUID(response.json()["submission_id"])
    submission = owner_session.get(PaymentSubmission, submission_id)
    assert submission is not None
    assert submission.total_amount == Money("2000.00")
    assert submission.status == "pending"
    assert submission.destination_snapshot["provider"] == "bKash"
    claims = _claims(owner_session, submission_id)
    assert set(claims) == {str(tania), str(tanvir)}
    assert {claim.claimed_amount for claim in claims.values()} == {Money("1000.00")}
    assert {claim.channel for claim in claims.values()} == {"bKash"}
    assert [row["enrollment_id"] for row in response.json()["claims"]] == [
        str(tania),
        str(tanvir),
    ]
    queue = api_client.get(
        "/v1/claims/queue", headers=bearer(owner_session, teacher.account_id)
    ).json()
    [item] = queue["pending"]
    assert item["duplicate_of"] is None
    assert [child["display_name"] for child in item["children"]] == [
        "Tania",
        "Tanvir",
    ]


def test_short_and_over_payments_are_split_onto_the_last_child(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A short payment leaves the last child short; an excess lands on them.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    tania = _child(owner_session, teacher.batch_id, "Tania", guardian)
    tanvir = _child(owner_session, teacher.batch_id, "Tanvir", guardian)
    _charge(owner_session, tania, "2026-10", "1000.00")
    _charge(owner_session, tanvir, "2026-10", "1000.00")
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, guardian)

    short = api_client.post(
        "/v1/payments",
        json=_body([tania, tanvir], method, "1500.00", transaction_id="SHORT1"),
        headers=headers,
    )
    over = api_client.post(
        "/v1/payments",
        json=_body([tania, tanvir], method, "2500.00", transaction_id="OVER1"),
        headers=headers,
    )

    short_claims = _claims(owner_session, uuid.UUID(short.json()["submission_id"]))
    over_claims = _claims(owner_session, uuid.UUID(over.json()["submission_id"]))
    assert short_claims[str(tania)].claimed_amount == Money("1000.00")
    assert short_claims[str(tanvir)].claimed_amount == Money("500.00")
    assert over_claims[str(tania)].claimed_amount == Money("1000.00")
    assert over_claims[str(tanvir)].claimed_amount == Money("1500.00")


def test_student_can_only_pay_for_their_own_seat(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A sibling's seat is refused, alone or alongside the student's own.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    own = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
    )
    sibling = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        student_account_id=account_factory(),
    )
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, student)

    alone = api_client.post(
        "/v1/payments", json=_body([sibling], method), headers=headers
    )
    mixed = api_client.post(
        "/v1/payments", json=_body([own, sibling], method), headers=headers
    )
    mine = api_client.post("/v1/payments", json=_body([own], method), headers=headers)

    assert alone.status_code == 403
    assert mixed.status_code == 403
    assert mine.status_code == 201


def test_submit_refuses_unaccepted_or_cross_batch_child(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A pending seat is out of reach; two batches cannot share a payment.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    pending = _child(
        owner_session, teacher.batch_id, "Tania", guardian, decision="pending"
    )
    here = _child(owner_session, teacher.batch_id, "Tanvir", guardian)
    other_teacher = make_teacher(owner_session, name="Chemistry")
    there = _child(owner_session, other_teacher.batch_id, "Tanvir", guardian)
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, guardian)

    unaccepted = api_client.post(
        "/v1/payments", json=_body([pending], method), headers=headers
    )
    across = api_client.post(
        "/v1/payments", json=_body([here, there], method), headers=headers
    )

    assert unaccepted.status_code == 403
    assert across.status_code == 400
    assert _code(across) == "PAYMENT_CHILDREN_ACROSS_BATCHES"


def test_method_of_another_teacher_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A method the batch's owner does not hold is not offered.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    stranger = make_teacher(owner_session, name="Chemistry")
    foreign = _method(owner_session, stranger.owner_id)

    response = api_client.post(
        "/v1/payments",
        json=_body([seat], foreign),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 400
    assert _code(response) == "PAYMENT_METHOD_NOT_OFFERED"


def test_retired_method_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A retired method is no longer offered.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    retired = _method(owner_session, teacher.owner_id, retired=True)

    response = api_client.post(
        "/v1/payments",
        json=_body([seat], retired),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 400
    assert _code(response) == "PAYMENT_METHOD_NOT_OFFERED"


def test_mobile_needs_transaction_id_bank_needs_from_account(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Each kind takes exactly its own reference.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    mobile = _method(owner_session, teacher.owner_id)
    bank = _method(owner_session, teacher.owner_id, kind="bank")
    headers = bearer(owner_session, guardian)

    cases = [
        _body([seat], mobile, transaction_id=None),
        _body([seat], mobile, from_account="Sonali 0099"),
        _body([seat], bank),
        _body([seat], bank, transaction_id=None),
    ]
    for body in cases:
        response = api_client.post("/v1/payments", json=body, headers=headers)
        assert response.status_code == 400, body
        assert _code(response) == "PAYMENT_REFERENCE_MISMATCH"

    accepted = api_client.post(
        "/v1/payments",
        json=_body([seat], bank, transaction_id=None, from_account="Sonali 0099"),
        headers=headers,
    )
    assert accepted.status_code == 201


def test_paying_with_nothing_owed_is_accepted(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """With no cycle, the claim lands on Bangladesh's current period.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    method = _method(owner_session, teacher.owner_id)

    response = api_client.post(
        "/v1/payments",
        json=_body([seat], method, "500.00"),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 201
    [claim] = response.json()["claims"]
    assert claim["period"] == bangladesh_today().strftime("%Y-%m")
    assert claim["claimed_amount"] == "500.00"


def test_cash_in_hand_needs_no_method_and_no_reference(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Cash records the built-in channel and a cash snapshot.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    headers = bearer(owner_session, guardian)

    cash = api_client.post(
        "/v1/payments",
        json=_body([seat], None, cash=True, transaction_id=None),
        headers=headers,
    )
    neither = api_client.post(
        "/v1/payments", json=_body([seat], None, transaction_id=None), headers=headers
    )

    assert cash.status_code == 201
    submission_id = uuid.UUID(cash.json()["submission_id"])
    submission = owner_session.get(PaymentSubmission, submission_id)
    assert submission is not None
    assert submission.destination_snapshot == {"kind": "cash"}
    assert submission.payment_method_id is None
    assert {c.channel for c in _claims(owner_session, submission_id).values()} == {
        "cash"
    }
    assert neither.status_code == 400
    assert _code(neither) == "PAYMENT_METHOD_NOT_OFFERED"


def test_paid_on_in_the_future_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Tomorrow in Bangladesh is refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    method = _method(owner_session, teacher.owner_id)
    tomorrow = bangladesh_today() + dt.timedelta(days=1)

    response = api_client.post(
        "/v1/payments",
        json=_body([seat], method, paid_on=tomorrow.isoformat()),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 400
    assert _code(response) == "PAYMENT_DATE_IN_FUTURE"


def test_paid_on_long_before_joining_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Sixty days before joining is the earliest accepted day.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    joined = bangladesh_today() - dt.timedelta(days=10)
    owner_session.execute(
        sa.text("UPDATE enrollment SET joined_on = :day WHERE id = :id"),
        {"day": joined, "id": seat},
    )
    owner_session.commit()
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, guardian)

    too_early = api_client.post(
        "/v1/payments",
        json=_body(
            [seat], method, paid_on=(joined - dt.timedelta(days=61)).isoformat()
        ),
        headers=headers,
    )
    earliest = api_client.post(
        "/v1/payments",
        json=_body(
            [seat], method, paid_on=(joined - dt.timedelta(days=60)).isoformat()
        ),
        headers=headers,
    )

    assert too_early.status_code == 400
    assert _code(too_early) == "PAYMENT_DATE_TOO_EARLY"
    assert earliest.status_code == 201


def test_paid_on_today_in_bangladesh_is_accepted(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """At 00:30 in Dhaka it is already the next day, which is not the future.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    method = _method(owner_session, teacher.owner_id)
    half_past_midnight = dt.datetime(2026, 11, 1, 18, 30, tzinfo=dt.UTC)
    today = bangladesh_today(half_past_midnight)

    submission = submit_payment(
        restricted_session,
        lens=GuardianLens(account_id=guardian),
        draft=PaymentDraft(
            enrollment_ids=(seat,),
            payment_method_id=method,
            cash=False,
            amount=Money("1500.00"),
            paid_on=dt.date(2026, 11, 2),
            transaction_id="9KD7Q2XL1M",
            from_account=None,
            note=None,
        ),
        today=today,
    )

    assert submission.paid_on == dt.date(2026, 11, 2)
    [claim] = _claims(restricted_session, submission.id).values()
    assert claim.period == "2026-11"


def test_resubmitted_reference_is_flagged(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same transaction id twice marks the second as a duplicate.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    seat = _child(owner_session, teacher.batch_id, "Tania", guardian)
    _charge(owner_session, seat, "2026-10", "1000.00")
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, guardian)

    first = api_client.post("/v1/payments", json=_body([seat], method), headers=headers)
    second = api_client.post(
        "/v1/payments", json=_body([seat], method), headers=headers
    )

    queue = api_client.get(
        "/v1/claims/queue", headers=bearer(owner_session, teacher.account_id)
    ).json()
    by_submission = {item["submission_id"]: item for item in queue["pending"]}
    first_id = first.json()["submission_id"]
    second_id = second.json()["submission_id"]
    assert by_submission[first_id]["duplicate_of"] is None
    assert by_submission[second_id]["duplicate_of"]["submission_id"] == first_id


def test_one_notification_per_submission(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two children paid together put one item in the teacher's inbox.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    tania = _child(owner_session, teacher.batch_id, "Tania", guardian)
    tanvir = _child(owner_session, teacher.batch_id, "Tanvir", guardian)
    method = _method(owner_session, teacher.owner_id)

    response = api_client.post(
        "/v1/payments",
        json=_body([tania, tanvir], method, "2000.00"),
        headers=bearer(owner_session, guardian),
    )

    assert response.status_code == 201
    [item] = inbox(restricted_session, account_id=teacher.account_id).items
    assert item.kind == "claim_to_verify"
    assert item.amount == Money("2000.00")
    assert item.child_name == "Tania, Tanvir"
    assert inbox(restricted_session, account_id=guardian).items == []


def test_owed_together_is_served_in_child_order(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The form's owed line comes from the server, children by name.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    guardian = account_factory()
    tania = _child(owner_session, teacher.batch_id, "Tania", guardian)
    tanvir = _child(owner_session, teacher.batch_id, "Tanvir", guardian)
    _charge(owner_session, tanvir, "2026-10", "1200.00")
    headers = bearer(owner_session, guardian)

    response = api_client.get(
        "/v1/payments/owed",
        params={"enrollment_id": [str(tanvir), str(tania)]},
        headers=headers,
    )
    stranger = api_client.get(
        "/v1/payments/owed",
        params={"enrollment_id": [str(tania)]},
        headers=bearer(owner_session, account_factory()),
    )

    assert response.status_code == 200
    assert response.json() == {
        "owed_together": "1200.00",
        "children": [
            {"enrollment_id": str(tania), "display_name": "Tania", "owed": "0.00"},
            {"enrollment_id": str(tanvir), "display_name": "Tanvir", "owed": "1200.00"},
        ],
        # No exam or other fee was raised, so nothing else to pay for [0020].
        "extra_fee_options": [],
    }
    assert stranger.status_code == 403


def test_a_student_who_is_also_a_guardian_pays_for_their_child(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """An account holding both lenses reaches each seat through its own.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    parent = account_factory()
    own = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Najma",
        student_account_id=parent,
    )
    child = _child(owner_session, teacher.batch_id, "Tania", parent)
    method = _method(owner_session, teacher.owner_id)
    headers = bearer(owner_session, parent)

    for_child = api_client.post(
        "/v1/payments",
        json=_body([child], method, transaction_id="CHILD1"),
        headers=headers,
    )
    for_self = api_client.post(
        "/v1/payments",
        json=_body([own], method, transaction_id="SELF1"),
        headers=headers,
    )

    assert for_child.status_code == 201
    assert for_self.status_code == 201
