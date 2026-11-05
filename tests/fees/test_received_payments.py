"""A teacher records money received by hand [BR5.3, BR5.4, BR5.5].

**Written before the route existed.** Every case is money or
authorization, so the test-first predicate holds: the expected ledger
is knowable from the charge and the teacher's choice alone, and a wrong
answer either records money that never moved, forgives a debt nobody
chose to forgive, or lets one teacher write to another's seat.

Rahim's seat is charged 1500.00 for October unless a test says
otherwise. His student account and his guardian's both accepted, so
both are told; a second guardian-less seat is used where only the
recipients matter.

**The record is a claim the teacher submits and approves in one
transaction**, so every reader of the ledger -- balances, the month
strip, collections, the payment history -- sees it exactly as it sees
a family's approved payment. These tests read those consequences rather
than the rows the route writes, except where the row IS the guarantee
(one receipt, never two, under a replay).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import (
    LedgerEntryRow,
    Notification,
    PaymentClaim,
    PaymentSubmission,
)
from app.errors import ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.received import ReceivedPayment, record_received_payment
from app.fees.status import fee_status
from app.local_time import bangladesh_today
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.fees.conftest import charge_period

SEPTEMBER = "2026-09"
OCTOBER = "2026-10"


@dataclass(frozen=True, slots=True)
class Seat:
    """One seat with an accepted student and an accepted guardian.

    :ivar enrollment_id: The seat
    :ivar student: The student's account
    :ivar guardian: The guardian's account
    """

    enrollment_id: uuid.UUID
    student: uuid.UUID
    guardian: uuid.UUID


def _seat(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    *,
    charged: dict[str, str] | None = None,
) -> Seat:
    """Seat Rahim, both links accepted, charged October's 1500 by default.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param charged: Period to charge; October 1500.00 by default
    :return: The seat and its two accounts
    """
    student = account_factory()
    guardian = account_factory()
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_account_id=guardian,
        guardian_decision="accepted",
    )
    for period, amount in (charged or {OCTOBER: "1500.00"}).items():
        charge_period(session, enrollment_id=seat, period=period, amount=amount)
    return Seat(enrollment_id=seat, student=student, guardian=guardian)


def _record(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    amount: str,
    **fields: object,
) -> object:
    """Record a payment received by hand, as the teacher.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The recording teacher
    :param seat: The seat
    :param amount: The amount received
    :param fields: Any other body fields
    :return: The response
    """
    body: dict[str, object] = {"amount": amount}
    body.update(
        {
            key: str(value) if isinstance(value, uuid.UUID | dt.date) else value
            for key, value in fields.items()
        }
    )
    return client.post(
        f"/v1/enrollments/{seat}/payments",
        json=body,
        headers=bearer(session, teacher.account_id),
    )


def _kinds(session: Session, seat: uuid.UUID) -> dict[str, list[tuple[str, Money]]]:
    """Read a seat's ledger as kind to (period, amount) pairs.

    :param session: A reading session
    :param seat: The seat
    :return: Every entry, grouped by kind
    """
    found: dict[str, list[tuple[str, Money]]] = {}
    for row in session.scalars(
        sa.select(LedgerEntryRow)
        .where(LedgerEntryRow.enrollment_id == seat)
        .order_by(LedgerEntryRow.created_at)
    ):
        found.setdefault(row.kind, []).append((row.period, row.amount))
    return found


def _code(response: object) -> str:
    """Read the error code from an envelope.

    :param response: The response
    :return: The code
    """
    code: str = response.json()["error"]["code"]  # type: ignore[attr-defined]
    return code


def _status(response: object) -> int:
    """Read a response's status code.

    :param response: The response
    :return: The status
    """
    status: int = response.status_code  # type: ignore[attr-defined]
    return status


def _nothing_written(session: Session, seat: uuid.UUID) -> None:
    """Assert a refused record left no payment, entry or message behind.

    :param session: A reading session
    :param seat: The seat
    :return: None
    """
    assert session.scalars(sa.select(PaymentSubmission)).all() == []
    assert (
        session.scalars(
            sa.select(PaymentClaim).where(PaymentClaim.enrollment_id == seat)
        ).all()
        == []
    )
    assert set(_kinds(session, seat)) == {"charge"}
    assert session.scalars(sa.select(Notification)).all() == []


def test_full_amount_received_pays_the_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 cash against 1500 charged: one receipt, October paid.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "1500.00"
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["status"] == "approved"
    assert body["total_amount"] == "1500.00"
    assert body["method"]["kind"] == "cash"
    assert [c["approved_amount"] for c in body["children"]] == ["1500.00"]
    assert (
        fee_status(restricted_session, enrollment_id=seat.enrollment_id, period=OCTOBER)
        == "paid"
    )
    kinds = _kinds(restricted_session, seat.enrollment_id)
    assert kinds["receipt"] == [(OCTOBER, Money("1500.00"))]
    assert "forgiveness" not in kinds
    assert "credit_grant" not in kinds
    claim = restricted_session.scalars(sa.select(PaymentClaim)).one()
    assert claim.status == "approved_full"
    assert claim.channel == "cash"
    assert claim.submitted_by_account_id == teacher.account_id
    assert claim.verified_by_account_id == teacher.account_id


def test_partial_carried_stays_owed_on_its_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1000 of 1500, carried: October partly paid, 500 still owed.

    Carrying writes nothing for the shortfall: it stays owed on the
    month it belongs to, exactly as the verification path leaves it.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1000.00",
        shortfall_disposition="carried",
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    assert (
        fee_status(restricted_session, enrollment_id=seat.enrollment_id, period=OCTOBER)
        == "partly_paid"
    )
    derived = derive_for_enrollment(restricted_session, seat.enrollment_id)
    assert derived.total_outstanding == Money("500.00")
    kinds = _kinds(restricted_session, seat.enrollment_id)
    assert kinds["receipt"] == [(OCTOBER, Money("1000.00"))]
    assert "forgiveness" not in kinds
    assert "carry_forward" not in kinds
    claim = restricted_session.scalars(sa.select(PaymentClaim)).one()
    assert claim.status == "approved_partial"
    assert claim.shortfall_disposition == "carried"


def test_partial_waived_forgives_the_rest(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1000 of 1500, waived: 500 forgiven on October, nothing owed.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1000.00",
        shortfall_disposition="waived",
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, seat.enrollment_id)
    assert kinds["receipt"] == [(OCTOBER, Money("1000.00"))]
    assert kinds["forgiveness"] == [(OCTOBER, Money("500.00"))]
    derived = derive_for_enrollment(restricted_session, seat.enrollment_id)
    assert derived.total_outstanding == Money.ZERO


def test_partial_without_a_disposition_is_refused(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Less than owed with no carry-or-waive is refused, writing nothing.

    Neither choice may be a default [BR5.4]: the two have opposite
    consequences for the family.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "1000.00"
    )

    assert _status(response) == 400
    assert _code(response) == "SHORTFALL_DISPOSITION_REQUIRED"
    _nothing_written(restricted_session, seat.enrollment_id)


def test_disposition_when_nothing_is_short_is_refused(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A carry-or-waive on a full payment is refused, not ignored.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        shortfall_disposition="waived",
    )

    assert _status(response) == 400
    assert _code(response) == "SHORTFALL_DISPOSITION_NOT_APPLICABLE"
    _nothing_written(restricted_session, seat.enrollment_id)


def test_overpayment_becomes_credit_never_a_negative_balance(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 against 1500: receipt capped at 1500, 500 held as credit.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "2000.00"
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, seat.enrollment_id)
    assert kinds["receipt"] == [(OCTOBER, Money("1500.00"))]
    assert kinds["credit_grant"] == [(OCTOBER, Money("500.00"))]
    derived = derive_for_enrollment(restricted_session, seat.enrollment_id)
    assert derived.total_outstanding == Money.ZERO
    assert derived.available_credit == Money("500.00")


def test_oldest_month_is_settled_first(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 against September and October at 1500 each pays September.

    The shortfall is measured against everything the seat owes, so 1000
    short across the two months needs a disposition, and carrying it
    leaves October owing 1000 while September reads paid.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(
        owner_session,
        teacher,
        account_factory,
        charged={SEPTEMBER: "1500.00", OCTOBER: "1500.00"},
    )

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "2000.00",
        shortfall_disposition="carried",
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, seat.enrollment_id)
    assert kinds["receipt"] == [
        (SEPTEMBER, Money("1500.00")),
        (OCTOBER, Money("500.00")),
    ]
    assert (
        fee_status(
            restricted_session, enrollment_id=seat.enrollment_id, period=SEPTEMBER
        )
        == "paid"
    )
    derived = derive_for_enrollment(restricted_session, seat.enrollment_id)
    assert derived.total_outstanding == Money("1000.00")


def test_zero_is_refused(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Recording nothing received is refused before anything is written.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(api_client, owner_session, teacher, seat.enrollment_id, "0.00")

    assert _status(response) == 400
    assert _code(response) == "PAYMENT_AMOUNT_NOT_POSITIVE"
    _nothing_written(restricted_session, seat.enrollment_id)


def test_negative_is_refused_at_the_wire(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A signed amount does not cross the wire at all.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "-100.00"
    )

    assert 400 <= _status(response) < 500
    _nothing_written(restricted_session, seat.enrollment_id)


def test_negative_is_refused_by_the_service(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The service refuses a negative amount even past the wire.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)

    with pytest.raises(ValidationError) as refused:
        record_received_payment(
            restricted_session,
            lens=lens,
            enrollment_id=seat.enrollment_id,
            payment=ReceivedPayment(amount=Money("-1.00")),
        )

    assert refused.value.code == "PAYMENT_AMOUNT_NOT_POSITIVE"
    restricted_session.rollback()
    _nothing_written(restricted_session, seat.enrollment_id)


def test_a_replay_records_once(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same retry key twice is one payment and one receipt.

    A record can commit and lose its response on a flaky connection;
    the resend must return that payment rather than receive the money
    a second time.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    key = uuid.uuid4()
    fields: dict[str, object] = {
        "client_mutation_id": key,
        "paid_on": bangladesh_today(),
        "note": "Paid at the door",
    }

    first = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "1500.00", **fields
    )
    second = _record(
        api_client, owner_session, teacher, seat.enrollment_id, "1500.00", **fields
    )

    assert _status(first) == 201, first.text  # type: ignore[attr-defined]
    assert _status(second) == 201, second.text  # type: ignore[attr-defined]
    assert (
        first.json()["submission_id"]  # type: ignore[attr-defined]
        == second.json()["submission_id"]  # type: ignore[attr-defined]
    )
    assert _kinds(restricted_session, seat.enrollment_id)["receipt"] == [
        (OCTOBER, Money("1500.00"))
    ]
    assert len(restricted_session.scalars(sa.select(PaymentSubmission)).all()) == 1
    told = restricted_session.scalars(
        sa.select(Notification).where(Notification.account_id == seat.student)
    ).all()
    assert len(told) == 1


def test_a_reused_key_for_a_different_payment_is_a_conflict(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The same retry key with a different amount is refused, not merged.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    key = uuid.uuid4()
    _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        client_mutation_id=key,
    )

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1000.00",
        shortfall_disposition="carried",
        client_mutation_id=key,
    )

    assert _status(response) == 409
    assert _code(response) == "MUTATION_ID_ALREADY_USED"
    assert _kinds(restricted_session, seat.enrollment_id)["receipt"] == [
        (OCTOBER, Money("1500.00"))
    ]


def test_another_teachers_seat_is_not_available(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Teacher B recording on teacher A's seat gets the shared refusal.

    An absent seat and another teacher's are the same refusal, so a
    probe cannot tell which seat ids exist.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: Teacher A, the batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    other = make_teacher(owner_session, name="Chemistry")

    theirs = _record(api_client, owner_session, other, seat.enrollment_id, "1500.00")
    absent = _record(api_client, owner_session, other, uuid.uuid4(), "1500.00")

    assert _status(theirs) == 403
    assert _code(theirs) == "NOT_AVAILABLE"
    assert _status(absent) == 403
    assert theirs.json() == absent.json()  # type: ignore[attr-defined]
    _nothing_written(restricted_session, seat.enrollment_id)


def test_a_family_lens_cannot_record(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The seat's own student cannot mark their fee received.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = api_client.post(
        f"/v1/enrollments/{seat.enrollment_id}/payments",
        json={"amount": "1500.00"},
        headers=bearer(owner_session, seat.student),
    )

    assert _status(response) == 403
    _nothing_written(restricted_session, seat.enrollment_id)


def test_an_unknown_channel_is_refused(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Only cash and the offered mobile services are channels.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        channel="cheque",
    )

    assert _status(response) == 400
    assert _code(response) == "CLAIM_CHANNEL_UNKNOWN"
    _nothing_written(restricted_session, seat.enrollment_id)


def test_a_future_date_is_refused(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Money cannot have been received tomorrow.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        paid_on=bangladesh_today() + dt.timedelta(days=1),
    )

    assert _status(response) == 400
    assert _code(response) == "PAYMENT_DATE_IN_FUTURE"
    _nothing_written(restricted_session, seat.enrollment_id)


def test_mobile_service_keeps_its_name_and_reference(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A bKash payment sent straight to the teacher keeps its name and id.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)

    response = _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        channel="bKash",
        reference="9KD7Q2XL1M",
    )

    assert _status(response) == 201, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["method"] == {
        "kind": "mobile",
        "channel": None,
        "method_id": None,
        "provider": "bKash",
        "mobile_number": None,
        "account_number": None,
        "account_name": None,
        "branch_name": None,
        "note": None,
    }
    claim = restricted_session.scalars(sa.select(PaymentClaim)).one()
    assert claim.channel == "bKash"
    assert claim.transaction_id == "9KD7Q2XL1M"


def test_the_family_is_told_and_the_teacher_is_not_asked(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Student and accepted guardian get payment_recorded; no claim_to_verify.

    The teacher received the money and recorded it; asking them to
    verify their own record would be a to-do item with nothing to do.
    A guardian who has not accepted is not told [BR5.2].

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    pending_guardian = account_factory()
    other = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Karim",
        guardian_account_id=pending_guardian,
        guardian_decision="pending",
    )
    charge_period(owner_session, enrollment_id=other, period=OCTOBER, amount="1500.00")

    _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        note="Paid at the door",
    )
    _record(api_client, owner_session, teacher, other, "1500.00")

    rows = restricted_session.scalars(sa.select(Notification)).all()
    told = {(row.account_id, row.kind) for row in rows}
    assert told == {
        (seat.student, "payment_recorded"),
        (seat.guardian, "payment_recorded"),
    }
    guardian_copy = next(row for row in rows if row.account_id == seat.guardian)
    assert guardian_copy.amount == Money("1500.00")
    assert guardian_copy.child_name == "Rahim"
    assert guardian_copy.preview == "Paid at the door"


def test_the_family_inbox_opens_to_the_payment(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The new kind lists and opens to the payment's decision.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1000.00",
        shortfall_disposition="carried",
    )

    listed = api_client.get(
        "/v1/me/notifications", headers=bearer(owner_session, seat.student)
    )
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["kind"] == "payment_recorded"
    assert item["amount"] == "1000.00"

    opened = api_client.get(
        f"/v1/me/notifications/{item['notification_id']}",
        headers=bearer(owner_session, seat.student),
    )
    assert opened.status_code == 200, opened.text
    payment = opened.json()["payment"]
    assert opened.json()["available"] is True
    assert payment["approved"] == "1000.00"
    assert payment["period"] == OCTOBER


def test_the_record_shows_in_the_seat_history(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The month's history line reads the cash record, approved.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    seat = _seat(owner_session, teacher, account_factory)
    _record(
        api_client,
        owner_session,
        teacher,
        seat.enrollment_id,
        "1500.00",
        note="Paid at the door",
    )

    history = api_client.get(
        f"/v1/enrollments/{seat.enrollment_id}/fees?months=24",
        headers=bearer(owner_session, teacher.account_id),
    )

    assert history.status_code == 200, history.text
    lines = [
        row["history_line"]
        for row in history.json()["month_states"]
        if row["period"] == OCTOBER
    ]
    assert lines and lines[0] is not None
    assert lines[0]["channel"] == "cash"
    assert lines[0]["status"] == "approved_full"
    assert lines[0]["decision_note"] == "Paid at the door"
