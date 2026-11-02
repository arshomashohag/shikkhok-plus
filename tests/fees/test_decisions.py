"""Deciding a payment: approve with a split, or reject with a note [R1-R4].

**Written before the decision existed.** Every case is money or
authorization, so the test-first predicate holds: the expected ledger
is knowable from the charges and the teacher's choices alone, and a
wrong answer either credits the wrong child or lets another teacher
decide.

Two children, Tania and Tanvir, each owe 1000.00 for October unless a
test says otherwise. Child order is display name then id, so Tania is
first and Tanvir second everywhere.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    LedgerEntryRow,
    PaymentClaim,
    PaymentMethod,
    PaymentSubmission,
)
from app.fees.balances import derive_for_enrollment
from app.fees.claims import submit_claim
from app.fees.generation import generate_due_cycles
from app.fees.ledger_writer import append_entry, apply_available_credit
from app.fees.status import fee_status
from app.local_time import bangladesh_today
from app.money import Money
from app.notifications.inbox import inbox
from tests.batches.conftest import TeacherFixture, enroll, make_teacher
from tests.conftest import bearer
from tests.fees.conftest import add_method, charge_period, set_joined_on

OCTOBER = "2026-10"


@dataclass(frozen=True, slots=True)
class Family:
    """A guardian with two children on one teacher's batch.

    :ivar guardian: The guardian's account
    :ivar tania: Tania's seat, first in child order
    :ivar tanvir: Tanvir's seat, second in child order
    :ivar method: The teacher's bKash method
    """

    guardian: uuid.UUID
    tania: uuid.UUID
    tanvir: uuid.UUID
    method: uuid.UUID


def _family(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    *,
    owed: str | None = "1000.00",
) -> Family:
    """Seat two children under one guardian, each owing October's fee.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param owed: What each child is charged for October, or None for nothing
    :return: The family
    """
    guardian = account_factory()
    seats = [
        enroll(
            session,
            batch_id=teacher.batch_id,
            display_name=name,
            guardian_account_id=guardian,
            guardian_decision="accepted",
        )
        for name in ("Tanvir", "Tania")
    ]
    if owed is not None:
        for seat in seats:
            charge_period(session, enrollment_id=seat, period=OCTOBER, amount=owed)
    return Family(
        guardian=guardian,
        tania=seats[1],
        tanvir=seats[0],
        method=add_method(session, teacher.owner_id),
    )


def _submit(
    client: TestClient,
    session: Session,
    family: Family,
    amount: str,
    seats: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    """Report one payment for the family's children.

    :param client: The test client
    :param session: A session to issue the token through
    :param family: The family paying
    :param amount: The amount sent
    :param seats: The children covered; both by default
    :return: The submission id
    """
    covered = seats if seats is not None else [family.tania, family.tanvir]
    response = client.post(
        "/v1/payments",
        json={
            "enrollment_ids": [str(seat) for seat in covered],
            "payment_method_id": str(family.method),
            "amount": amount,
            "paid_on": bangladesh_today().isoformat(),
            "transaction_id": f"TX{uuid.uuid4().hex[:10]}",
            "note": "November fee",
        },
        headers=bearer(session, family.guardian),
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["submission_id"])


def _approve(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    submission_id: uuid.UUID,
    received: str,
    **choices: object,
) -> object:
    """Approve a submission as the teacher.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The deciding teacher
    :param submission_id: The submission
    :param received: The amount the teacher records as received
    :param choices: The disposition, chosen children, note or correcting
    :return: The response
    """
    body: dict[str, object] = {"received_amount": received}
    body.update(
        {
            key: str(value) if isinstance(value, uuid.UUID) else value
            for key, value in choices.items()
        }
    )
    return client.post(
        f"/v1/payments/{submission_id}/approval",
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


def test_full_approval_marks_every_child_paid(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 for two children owing 1000 each pays both October cycles.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")

    response = _approve(api_client, owner_session, teacher, submission, "2000.00")

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert response.json()["status"] == "approved"  # type: ignore[attr-defined]
    for seat in (family.tania, family.tanvir):
        assert (
            fee_status(restricted_session, enrollment_id=seat, period=OCTOBER) == "paid"
        )


def test_short_carry_lands_on_the_chosen_child(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 of 2000, carried by Tanvir: Tania paid, Tanvir carries 500.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
        carried_by_enrollment_id=family.tanvir,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert (
        fee_status(restricted_session, enrollment_id=family.tania, period=OCTOBER)
        == "paid"
    )
    assert _kinds(restricted_session, family.tanvir)["carry_forward"] == [
        ("2026-11", Money("500.00"))
    ]
    assert "carry_forward" not in _kinds(restricted_session, family.tania)


def test_short_waive_forgives_without_carry(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Waiving the 500 forgives it on Tanvir and carries nothing.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="waived",
        carried_by_enrollment_id=family.tanvir,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    tanvir = _kinds(restricted_session, family.tanvir)
    assert tanvir["forgiveness"] == [(OCTOBER, Money("500.00"))]
    assert "carry_forward" not in tanvir
    assert "forgiveness" not in _kinds(restricted_session, family.tania)


def test_over_payment_credits_the_chosen_child(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2500 for 2000 owed puts the 500 excess on Tania only.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2500.00")

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "2500.00",
        credit_to_enrollment_id=family.tania,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert _kinds(restricted_session, family.tania)["credit_grant"] == [
        (OCTOBER, Money("500.00"))
    ]
    assert "credit_grant" not in _kinds(restricted_session, family.tanvir)


def test_nothing_owed_payment_becomes_credit(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1000 with no cycle is all credit, and the next cycle spends it.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory, owed=None)
    submission = _submit(
        api_client, owner_session, family, "1000.00", seats=[family.tania]
    )

    response = _approve(api_client, owner_session, teacher, submission, "1000.00")

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, family.tania)
    assert [amount for _period, amount in kinds["credit_grant"]] == [Money("1000.00")]
    assert "receipt" not in kinds

    generate_due_cycles(restricted_session, today=bangladesh_today())

    spent = _kinds(restricted_session, family.tania)["credit_apply"]
    assert Money.sum([amount for _period, amount in spent]) == Money("1000.00")


def test_rejection_keeps_dues_and_shows_the_note(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A rejected payment moves no money and the family reads why.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    charge_period(owner_session, enrollment_id=seat, period=OCTOBER, amount="1000.00")
    method = add_method(owner_session, teacher.owner_id)
    before = derive_for_enrollment(restricted_session, seat).total_outstanding
    submitted = api_client.post(
        "/v1/payments",
        json={
            "enrollment_ids": [str(seat)],
            "payment_method_id": str(method),
            "amount": "1000.00",
            "paid_on": bangladesh_today().isoformat(),
            "transaction_id": "9KD7Q2XL1M",
        },
        headers=bearer(owner_session, student),
    ).json()

    response = api_client.post(
        f"/v1/payments/{submitted['submission_id']}/rejection",
        json={"note": "No such transaction in my bKash"},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert response.status_code == 200, response.text
    assert response.json()["decision_note"] == "No such transaction in my bKash"
    claim_id = submitted["claims"][0]["claim_id"]
    view = api_client.get(
        f"/v1/claims/{claim_id}", headers=bearer(owner_session, student)
    ).json()
    assert view["status"] == "rejected"
    assert view["decision_note"] == "No such transaction in my bKash"
    assert derive_for_enrollment(restricted_session, seat).total_outstanding == before
    [item] = inbox(restricted_session, account_id=student).items
    assert item.kind == "payment_rejected"
    assert item.preview == "No such transaction in my bKash"


def test_correction_reverses_every_childs_entries(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approve with carry, then reject as a correction: both folds return.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    seats = (family.tania, family.tanvir)
    before = {
        seat: derive_for_enrollment(restricted_session, seat).per_cycle
        for seat in seats
    }
    submission = _submit(api_client, owner_session, family, "1500.00")
    approved = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
        carried_by_enrollment_id=family.tanvir,
    )
    assert approved.status_code == 200  # type: ignore[attr-defined]

    refused = api_client.post(
        f"/v1/payments/{submission}/rejection",
        json={"note": "Wrong batch"},
        headers=bearer(owner_session, teacher.account_id),
    )
    corrected = api_client.post(
        f"/v1/payments/{submission}/rejection",
        json={"note": "Wrong batch", "correcting": True},
        headers=bearer(owner_session, teacher.account_id),
    )

    assert refused.status_code == 409
    assert _code(refused) == "PAYMENT_ALREADY_DECIDED"
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["status"] == "rejected"
    for seat in seats:
        after = derive_for_enrollment(restricted_session, seat).per_cycle
        assert {p: a for p, a in after.items() if not a.is_zero()} == {
            p: a for p, a in before[seat].items() if not a.is_zero()
        }
    claims = restricted_session.scalars(
        sa.select(PaymentClaim).where(PaymentClaim.payment_submission_id == submission)
    ).all()
    assert {claim.status for claim in claims} == {"rejected"}
    assert all(claim.previous_decision is not None for claim in claims)


def test_detail_shows_snapshot_after_method_edit(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The teacher sees the number the family paid to, not today's number.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")
    method = owner_session.get(PaymentMethod, family.method)
    assert method is not None
    method.mobile_number = "01899999999"
    owner_session.commit()

    response = api_client.get(
        f"/v1/payments/{submission}", headers=bearer(owner_session, teacher.account_id)
    )

    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["method"]["mobile_number"] == "01711000000"
    assert [child["display_name"] for child in detail["children"]] == [
        "Tania",
        "Tanvir",
    ]
    assert (detail["owed_together"], detail["total_amount"]) == ("2000.00", "1500.00")
    assert (detail["comparison"], detail["difference"]) == ("short", "500.00")
    assert detail["submitted_by"] == "guardian"
    assert detail["payer_note"] == "November fee"
    assert detail["status"] == "pending"


def test_other_teacher_cannot_decide(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Another teacher can neither read, approve nor reject the payment.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    stranger = make_teacher(owner_session, name="Chemistry")
    headers = bearer(owner_session, stranger.account_id)

    read = api_client.get(f"/v1/payments/{submission}", headers=headers)
    approve = _approve(api_client, owner_session, stranger, submission, "2000.00")
    reject = api_client.post(
        f"/v1/payments/{submission}/rejection", json={"note": None}, headers=headers
    )

    for response in (read, approve, reject):
        assert response.status_code == 403  # type: ignore[attr-defined]
        assert _code(response) == "NOT_AVAILABLE"


def test_a_short_payment_for_two_children_needs_the_bearer(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """No bearer named is the allocation's refusal, as a 400 with its code.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")

    missing = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
    )

    assert missing.status_code == 400  # type: ignore[attr-defined]
    assert _code(missing) == "ALLOCATION_BEARER_REQUIRED"
    assert (
        missing.json()["error"]["message_key"]  # type: ignore[attr-defined]
        == "fees.payment.allocation_bearer_required"
    )


def test_a_chosen_child_outside_the_payment_is_refused(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Naming a seat the payment does not cover is refused.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2500.00")

    outside = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "2500.00",
        credit_to_enrollment_id=uuid.uuid4(),
    )

    assert outside.status_code == 400  # type: ignore[attr-defined]
    assert _code(outside) == "PAYMENT_CHILD_NOT_IN_PAYMENT"


def test_the_decision_tells_the_family_once_and_settles_the_teachers_item(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """One guardian item for a two-child payment, carrying the note.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    [waiting] = inbox(restricted_session, account_id=teacher.account_id).items
    assert waiting.source_id == submission

    response = _approve(
        api_client, owner_session, teacher, submission, "2000.00", note="Thanks"
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    [item] = inbox(restricted_session, account_id=family.guardian).items
    assert (item.kind, item.preview, item.source_id) == (
        "payment_approved",
        "Thanks",
        submission,
    )
    assert item.child_name == "Tania, Tanvir"
    assert item.amount == Money("2000.00")
    teacher_inbox = inbox(restricted_session, account_id=teacher.account_id)
    assert teacher_inbox.unread == 0
    opened = api_client.get(
        f"/v1/me/notifications/{item.notification_id}",
        headers=bearer(owner_session, family.guardian),
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["available"] is True
    assert opened.json()["payment"]["outcome"] == "approved"


def test_the_queue_lists_one_item_per_submission(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Two children paid together are one queue item, then one decision.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    headers = bearer(owner_session, teacher.account_id)

    waiting = api_client.get("/v1/claims/queue", headers=headers).json()
    _approve(api_client, owner_session, teacher, submission, "2000.00")
    decided = api_client.get("/v1/claims/queue", headers=headers).json()

    [item] = waiting["pending"]
    assert item["submission_id"] == str(submission)
    assert (item["comparison"], item["difference"]) == ("matches", "0.00")
    assert decided["pending"] == []
    [recent] = decided["decided_recently"]
    assert (recent["submission_id"], recent["status"], recent["amount"]) == (
        str(submission),
        "approved",
        "2000.00",
    )


NOVEMBER = "2026-11"


def _fold(session: Session, seat: uuid.UUID) -> tuple[dict[str, Money], Money]:
    """Read a seat's non-zero per-period outstanding and its held credit.

    :param session: A reading session
    :param seat: The seat
    :return: Period to outstanding, without zero periods, and the credit
    """
    derived = derive_for_enrollment(session, seat)
    owing = {p: a for p, a in derived.per_cycle.items() if not a.is_zero()}
    return owing, derived.available_credit


def _two_months(
    session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> Family:
    """Seat the family with Tania owing October and November.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: The family
    """
    family = _family(session, teacher, account_factory)
    charge_period(
        session, enrollment_id=family.tania, period=NOVEMBER, amount="1000.00"
    )
    return family


def _sum(entries: list[tuple[str, Money]]) -> Money:
    """Total the amounts of some entries.

    :param entries: ``(period, amount)`` pairs
    :return: Their total
    """
    return Money.sum([amount for _period, amount in entries])


def test_two_month_child_full_approval_pays_both_months(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 for October and November pays both months and grants no credit.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "2000.00", seats=[family.tania]
    )

    response = _approve(api_client, owner_session, teacher, submission, "2000.00")

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, family.tania)
    assert kinds["receipt"] == [
        (OCTOBER, Money("1000.00")),
        (NOVEMBER, Money("1000.00")),
    ]
    assert "credit_grant" not in kinds
    assert _fold(restricted_session, family.tania) == ({}, Money.ZERO)


def test_two_month_child_short_waived_forgives_the_later_month(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 of 2000, waived: November's 500 is forgiven and nothing is owed.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "1500.00", seats=[family.tania]
    )

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="waived",
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    kinds = _kinds(restricted_session, family.tania)
    assert kinds["forgiveness"] == [(NOVEMBER, Money("500.00"))]
    assert "credit_grant" not in kinds
    assert _fold(restricted_session, family.tania) == ({}, Money.ZERO)
    claim = restricted_session.scalars(
        sa.select(PaymentClaim).where(PaymentClaim.payment_submission_id == submission)
    ).one()
    assert (claim.status, claim.shortfall_disposition) == (
        "approved_partial",
        "waived",
    )


def test_two_month_child_short_carried_moves_the_rest_on(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 of 2000, carried: 500 is owed in December and nowhere else.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "1500.00", seats=[family.tania]
    )

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert _fold(restricted_session, family.tania) == (
        {"2026-12": Money("500.00")},
        Money.ZERO,
    )


def test_below_one_month_waived_forgives_the_whole_shortfall_shown(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """400 of 2000, waived: the 1600 the teacher was shown is what is forgiven.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "400.00", seats=[family.tania]
    )
    shown = api_client.get(
        f"/v1/payments/{submission}", headers=bearer(owner_session, teacher.account_id)
    ).json()["difference"]

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "400.00",
        shortfall_disposition="waived",
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    forgiven = _sum(_kinds(restricted_session, family.tania)["forgiveness"])
    assert forgiven == Money(shown) == Money("1600.00")
    assert _fold(restricted_session, family.tania) == ({}, Money.ZERO)


def test_over_payment_gives_no_credit_to_a_two_month_child_not_chosen(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """3500 for 3000 owed, credit to Tanvir: Tania's two months, no credit.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "3500.00")

    response = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "3500.00",
        credit_to_enrollment_id=family.tanvir,
    )

    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert "credit_grant" not in _kinds(restricted_session, family.tania)
    assert _fold(restricted_session, family.tania) == ({}, Money.ZERO)
    assert _kinds(restricted_session, family.tanvir)["credit_grant"] == [
        (OCTOBER, Money("500.00"))
    ]


def _reject_as_correction(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    submission_id: uuid.UUID,
) -> None:
    """Reject a decided payment as a correction.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The deciding teacher
    :param submission_id: The submission
    :return: None
    """
    response = client.post(
        f"/v1/payments/{submission_id}/rejection",
        json={"correcting": True},
        headers=bearer(session, teacher.account_id),
    )
    assert response.status_code == 200, response.text


def test_correcting_an_over_payment_restores_the_fold_exactly(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approve 2500 with 500 credit, then reject: both seats as before.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    seats = (family.tania, family.tanvir)
    before = {seat: _fold(restricted_session, seat) for seat in seats}
    submission = _submit(api_client, owner_session, family, "2500.00")
    _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "2500.00",
        credit_to_enrollment_id=family.tania,
    )

    _reject_as_correction(api_client, owner_session, teacher, submission)

    assert {seat: _fold(restricted_session, seat) for seat in seats} == before


def test_correcting_a_nothing_owed_payment_leaves_no_stray_credit(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A rejected credit-only payment does not pre-pay the next month.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory, owed=None)
    submission = _submit(
        api_client, owner_session, family, "1000.00", seats=[family.tania]
    )
    _approve(api_client, owner_session, teacher, submission, "1000.00")

    _reject_as_correction(api_client, owner_session, teacher, submission)

    assert _fold(restricted_session, family.tania) == ({}, Money.ZERO)
    generate_due_cycles(restricted_session, today=bangladesh_today())
    owing, credit = _fold(restricted_session, family.tania)
    assert credit == Money.ZERO
    assert owing == {NOVEMBER: Money("1500.00")}


def test_correcting_a_two_month_approval_restores_the_fold(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approve 1500 of two months carried, then reject: as before.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _two_months(owner_session, teacher, account_factory)
    before = _fold(restricted_session, family.tania)
    submission = _submit(
        api_client, owner_session, family, "1500.00", seats=[family.tania]
    )
    _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
    )

    _reject_as_correction(api_client, owner_session, teacher, submission)

    assert _fold(restricted_session, family.tania) == before


def test_a_wrapped_legacy_claim_is_reviewed_and_decided(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A pre-submission claim, wrapped as ``0014`` wraps it, can be decided.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    charge_period(owner_session, enrollment_id=seat, period=OCTOBER, amount="1000.00")
    claim = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=student,
        claimed_amount=Money("1000.00"),
        channel="Nagad",
        transaction_id="OLD123",
    )
    legacy = PaymentSubmission(
        batch_id=teacher.batch_id,
        destination_snapshot={"kind": "legacy", "channel": "Nagad"},
        total_amount=claim.claimed_amount,
        paid_on=bangladesh_today(),
        transaction_id="OLD123",
        submitted_by_account_id=student,
        submitted_at=claim.submitted_at,
        status="pending",
    )
    owner_session.add(legacy)
    owner_session.flush()
    claim.payment_submission_id = legacy.id
    owner_session.commit()
    headers = bearer(owner_session, teacher.account_id)

    detail = api_client.get(f"/v1/payments/{legacy.id}", headers=headers)
    decided = _approve(api_client, owner_session, teacher, legacy.id, "1000.00")

    assert detail.status_code == 200, detail.text
    assert detail.json()["method"] == {
        "kind": "legacy",
        "channel": "Nagad",
        "method_id": None,
        "provider": None,
        "mobile_number": None,
        "account_number": None,
        "account_name": None,
        "branch_name": None,
        "note": None,
    }
    assert decided.status_code == 200, decided.text  # type: ignore[attr-defined]
    assert fee_status(restricted_session, enrollment_id=seat, period=OCTOBER) == "paid"


def _spend_credit_on(session: Session, seat: uuid.UUID, period: str, fee: str) -> None:
    """Charge a later month and spend held credit on it, as generation does.

    :param session: The application's session
    :param seat: The seat
    :param period: The later month
    :param fee: That month's charge
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period=period,
        kind="charge",
        amount=Money(fee),
    )
    apply_available_credit(session, enrollment_id=seat, period=period)
    session.commit()


def test_correcting_an_over_payment_whose_credit_was_spent_owes_it_all(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 for 1000 owed, 500 credit spent on November, then rejected: 2000 owed.

    Computed: October 1000 and November 1000 were charged and nothing
    was received, so 2000 is owed and no credit is held. Compensating
    the spent grant with a ``credit_apply`` would relieve October by
    500 a second time and read 1500.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "1500.00", seats=[family.tania]
    )
    _approve(api_client, owner_session, teacher, submission, "1500.00")
    _spend_credit_on(restricted_session, family.tania, NOVEMBER, "1000.00")

    _reject_as_correction(api_client, owner_session, teacher, submission)

    restricted_session.expire_all()
    derived = derive_for_enrollment(restricted_session, family.tania)
    assert derived.total_outstanding == Money("2000.00")
    assert derived.available_credit == Money.ZERO
    later = append_entry(
        restricted_session,
        enrollment_id=family.tania,
        period="2026-12",
        kind="credit_grant",
        amount=Money("100.00"),
    )
    restricted_session.commit()
    after = derive_for_enrollment(restricted_session, family.tania)
    assert later.amount == after.available_credit == Money("100.00")


def test_correcting_an_over_payment_whose_credit_was_partly_spent(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """500 credit, 300 of it spent on November, then rejected: 1300 owed.

    Computed: October 1000 and November 300 were charged and nothing
    was received, so 1300 is owed and the 200 still held is withdrawn.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(
        api_client, owner_session, family, "1500.00", seats=[family.tania]
    )
    _approve(api_client, owner_session, teacher, submission, "1500.00")
    _spend_credit_on(restricted_session, family.tania, NOVEMBER, "300.00")

    _reject_as_correction(api_client, owner_session, teacher, submission)

    restricted_session.expire_all()
    derived = derive_for_enrollment(restricted_session, family.tania)
    assert derived.total_outstanding == Money("1300.00")
    assert derived.available_credit == Money.ZERO


def _review(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    submission_id: uuid.UUID,
) -> dict[str, object]:
    """Read a payment's review as the teacher.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The reviewing teacher
    :param submission_id: The submission
    :return: The response body
    """
    response = client.get(
        f"/v1/payments/{submission_id}",
        headers=bearer(session, teacher.account_id),
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _owed_figures(body: dict[str, object]) -> tuple[object, ...]:
    """Pick the before-decision figures out of a review.

    :param body: The review body
    :return: Each child's owed, owed together, comparison and difference
    """
    children = body["children"]
    assert isinstance(children, list)
    return (
        [child["owed"] for child in children],
        body["owed_together"],
        body["comparison"],
        body["difference"],
    )


def test_a_full_approval_reviews_against_what_was_owed_before_it(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 for 2000 owed, approved: the review still reads 2000 owed, matches.

    Measured after the decision, both children owe 0 and the 2000 sent
    reads as 2000 over, which makes every correction look like an
    over-payment.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    _approve(api_client, owner_session, teacher, submission, "2000.00")

    body = _review(api_client, owner_session, teacher, submission)

    assert _owed_figures(body) == (
        ["1000.00", "1000.00"],
        "2000.00",
        "matches",
        "0.00",
    )


def test_a_carried_short_approval_reviews_against_what_was_owed_before_it(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 of 2000, carried by Tanvir: still 2000 owed and 500 short.

    Computed: Tanvir now owes November's 500 carried, and his relief
    from this payment is the 500 receipt plus the 500 carried out of
    October less the 500 carried into November, so before it he owed
    1000.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")
    _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
        carried_by_enrollment_id=family.tanvir,
    )

    body = _review(api_client, owner_session, teacher, submission)

    assert _owed_figures(body) == (
        ["1000.00", "1000.00"],
        "2000.00",
        "short",
        "500.00",
    )


def test_a_rejected_payment_reviews_against_what_is_owed(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A rejection relieved nothing, so before it and now are the same 2000.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    _approve(api_client, owner_session, teacher, submission, "2000.00")
    _reject_as_correction(api_client, owner_session, teacher, submission)

    body = _review(api_client, owner_session, teacher, submission)

    assert _owed_figures(body) == (
        ["1000.00", "1000.00"],
        "2000.00",
        "matches",
        "0.00",
    )


def test_a_full_approval_corrected_to_short_is_offered_and_accepted(
    api_client: TestClient,
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approved at 2000, corrected to 1500 carried by Tanvir: the review agrees.

    The correction sheet reads ``owed_together`` to decide what to ask.
    Read before the decision it is 2000, so 1500 is short and the
    carry choice the server requires is the one the sheet offers.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "2000.00")
    _approve(api_client, owner_session, teacher, submission, "2000.00")
    before = _review(api_client, owner_session, teacher, submission)

    corrected = _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
        carried_by_enrollment_id=family.tanvir,
        correcting=True,
    )

    assert before["owed_together"] == "2000.00"
    assert corrected.status_code == 200, corrected.text  # type: ignore[attr-defined]
    assert _owed_figures(_review(api_client, owner_session, teacher, submission)) == (
        ["1000.00", "1000.00"],
        "2000.00",
        "matches",
        "0.00",
    )
    assert _fold(restricted_session, family.tanvir) == (
        {NOVEMBER: Money("500.00")},
        Money.ZERO,
    )


def _october_line(
    client: TestClient,
    session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> dict[str, object]:
    """Read October's history line on a seat's fee history.

    :param client: The test client
    :param session: A session to issue the token through
    :param teacher: The seat's teacher
    :param seat: The seat
    :return: The history line
    """
    response = client.get(
        f"/v1/enrollments/{seat}/fees",
        headers=bearer(session, teacher.account_id),
    )
    assert response.status_code == 200, response.text
    [october] = [
        month for month in response.json()["month_states"] if month["period"] == OCTOBER
    ]
    line: dict[str, object] = october["history_line"]
    return line


def test_a_waiting_payment_shows_its_total_and_the_children_it_covers(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """2000 for both children, waiting: each child's line reads 2000 for both.

    Each child's provisional share is not what anybody paid, and for a
    child with a zero share it reads as nothing sent at all.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    _submit(api_client, owner_session, family, "2000.00")

    for seat in (family.tania, family.tanvir):
        line = _october_line(api_client, owner_session, teacher, seat)
        assert (line["amount"], line["status"], line["covered_names"]) == (
            "2000.00",
            "pending",
            ["Tania", "Tanvir"],
        )


def test_a_decided_payment_shows_what_was_approved_for_the_child(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """1500 for both, Tanvir carrying 500: Tania's line 1000, Tanvir's 500.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory)
    submission = _submit(api_client, owner_session, family, "1500.00")
    _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "1500.00",
        shortfall_disposition="carried",
        carried_by_enrollment_id=family.tanvir,
    )

    tania = _october_line(api_client, owner_session, teacher, family.tania)
    tanvir = _october_line(api_client, owner_session, teacher, family.tanvir)

    assert (tania["amount"], tania["status"], tania["covered_names"]) == (
        "1000.00",
        "approved_full",
        [],
    )
    assert (tanvir["amount"], tanvir["status"], tanvir["covered_names"]) == (
        "500.00",
        "approved_partial",
        [],
    )


def test_a_corrected_approval_leaves_fee_history_charged_unchanged(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approve 600 of 1500 carried, then reject: October still charged 1500.

    The correction writes a compensating 600 ``charge`` and a
    compensating 900 carry into October; counted, October would read
    3000 charged.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    family = _family(owner_session, teacher, account_factory, owed=None)
    set_joined_on(owner_session, enrollment_id=family.tania, when=dt.date(2026, 10, 1))
    generate_due_cycles(owner_session, today=dt.date(2026, 10, 20))
    submission = _submit(
        api_client, owner_session, family, "600.00", seats=[family.tania]
    )
    _approve(
        api_client,
        owner_session,
        teacher,
        submission,
        "600.00",
        shortfall_disposition="carried",
    )

    _reject_as_correction(api_client, owner_session, teacher, submission)

    response = api_client.get(
        f"/v1/enrollments/{family.tania}/fees",
        headers=bearer(owner_session, teacher.account_id),
    )
    assert response.status_code == 200, response.text
    charged = {cycle["period"]: cycle["charged"] for cycle in response.json()["cycles"]}
    assert charged[OCTOBER] == "1500.00"
