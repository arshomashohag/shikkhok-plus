"""Payment items in the inbox: the whole seat, the reason, the teacher.

A payment decision reaches every account that accepted the seat, not
only whoever submitted the claim; a correction leaves one item showing
the current outcome; and submitting a claim tells the batch teacher.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.authz.lenses import StudentLens
from app.db.models import PaymentClaim
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.submissions import PaymentDraft, submit_payment
from app.fees.verification import reject_claim, verify_claim
from app.local_time import bangladesh_today
from app.money import Money
from app.notifications.inbox import inbox
from tests.batches.conftest import TeacherFixture, enroll
from tests.conftest import bearer
from tests.fees.conftest import add_method


def _family_seat(
    session: Session,
    teacher: TeacherFixture,
    student: uuid.UUID,
    guardian: uuid.UUID,
) -> uuid.UUID:
    """Seat a student and accepted guardian owing October's 1200.

    :param session: An arranging session
    :param teacher: The batch's owner
    :param student: The student's account
    :param guardian: The guardian's account
    :return: The seat
    """
    seat = enroll(
        session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    append_entry(
        session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1200.00"),
    )
    session.commit()
    return seat


def _claim(session: Session, seat: uuid.UUID, by: uuid.UUID) -> PaymentClaim:
    """Submit a claim of 1200.

    :param session: The session to write through
    :param seat: The seat
    :param by: The submitter
    :return: The pending claim
    """
    return submit_claim(
        session,
        enrollment_id=seat,
        submitted_by_account_id=by,
        claimed_amount=Money("1200.00"),
        channel="bKash",
        transaction_id="TX-1",
    )


def _kinds(session: Session, account: uuid.UUID) -> list[str]:
    """List an account's inbox kinds.

    :param session: The session to read through
    :param account: The account
    :return: The kinds, newest first
    """
    return [item.kind for item in inbox(session, account_id=account).items]


def test_rejection_reaches_student_and_accepted_guardian(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The guardian who did not submit is still told.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    claim = _claim(owner_session, seat, student)

    reject_claim(
        owner_session, claim_id=claim.id, verified_by_account_id=teacher.account_id
    )

    assert _kinds(restricted_session, student) == ["payment_rejected"]
    assert _kinds(restricted_session, guardian) == ["payment_rejected"]
    [item] = inbox(restricted_session, account_id=guardian).items
    assert item.child_name == "Rahim"


def test_rejection_reason_is_stored_verbatim_and_blank_becomes_none(
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A reason is kept as written; whitespace alone is no reason.

    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    first = _claim(owner_session, seat, student)
    reject_claim(
        owner_session,
        claim_id=first.id,
        verified_by_account_id=teacher.account_id,
        reason="Transaction id does not match",
    )
    assert first.rejection_reason == "Transaction id does not match"

    reject_claim(
        owner_session,
        claim_id=first.id,
        verified_by_account_id=teacher.account_id,
        correcting=True,
        reason="   ",
    )
    assert first.rejection_reason is None


def test_partial_approval_is_its_own_kind(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Approving less than claimed says so; approving all does not.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    claim = _claim(owner_session, seat, student)

    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("700.00"),
        shortfall_disposition="carried",
        verified_by_account_id=teacher.account_id,
    )

    assert _kinds(restricted_session, guardian) == ["payment_partial"]
    assert _kinds(restricted_session, student) == ["payment_partial"]


def test_correction_replaces_the_earlier_item(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Rejecting, then approving as a correction, leaves one item.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    claim = _claim(owner_session, seat, student)
    reject_claim(
        owner_session, claim_id=claim.id, verified_by_account_id=teacher.account_id
    )

    verify_claim(
        owner_session,
        claim_id=claim.id,
        approved_amount=Money("1200.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
        correcting=True,
    )

    assert _kinds(restricted_session, student) == ["payment_approved"]
    assert _kinds(restricted_session, guardian) == ["payment_approved"]


def test_submitting_a_claim_tells_the_batch_teacher_only(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """The teacher gets a verify alert; the family gets nothing yet.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)

    _claim(owner_session, seat, student)

    [item] = inbox(restricted_session, account_id=teacher.account_id).items
    assert item.kind == "claim_to_verify"
    assert item.amount == Money("1200.00")
    assert item.child_name == "Rahim"
    assert _kinds(restricted_session, student) == []
    assert _kinds(restricted_session, guardian) == []


@pytest.mark.parametrize("decision", ["verify", "reject"])
def test_deciding_a_claim_marks_the_teachers_item_read(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    decision: str,
) -> None:
    """A decided claim no longer waits, so its item stops counting unread.

    Marked in the decision's own transaction; another teacher item about
    a claim still waiting stays unread.

    :param owner_session: An arranging session
    :param restricted_session: The application's session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param decision: Whether the claim is verified or rejected
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    decided = _claim(owner_session, seat, student)
    waiting = submit_claim(
        owner_session,
        enrollment_id=seat,
        submitted_by_account_id=guardian,
        claimed_amount=Money("100.00"),
        channel="bKash",
        transaction_id="TX-2",
    )

    if decision == "verify":
        verify_claim(
            owner_session,
            claim_id=decided.id,
            approved_amount=Money("1200.00"),
            shortfall_disposition=None,
            verified_by_account_id=teacher.account_id,
        )
    else:
        reject_claim(
            owner_session,
            claim_id=decided.id,
            verified_by_account_id=teacher.account_id,
        )

    items = inbox(restricted_session, account_id=teacher.account_id)
    read = {item.source_id: item.read for item in items.items}
    assert read == {decided.id: True, waiting.id: False}
    assert items.unread == 1


def test_a_note_over_500_chars_is_refused_by_the_api(
    api_client: TestClient,
    owner_session: Session,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A 501-character rejection note is a 422; 500 is accepted and stored.

    :param api_client: The test client
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :return: None
    """
    student, guardian = account_factory(), account_factory()
    seat = _family_seat(owner_session, teacher, student, guardian)
    submission = submit_payment(
        owner_session,
        lens=StudentLens(account_id=student),
        draft=PaymentDraft(
            enrollment_ids=(seat,),
            payment_method_id=add_method(owner_session, teacher.owner_id),
            cash=False,
            amount=Money("1200.00"),
            paid_on=bangladesh_today(),
            transaction_id="TX-1",
            from_account=None,
            note=None,
        ),
    )
    headers = bearer(owner_session, teacher.account_id)
    url = f"/v1/payments/{submission.id}/rejection"

    refused = api_client.post(url, json={"note": "x" * 501}, headers=headers)
    accepted = api_client.post(url, json={"note": "x" * 500}, headers=headers)

    assert refused.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["decision_note"] == "x" * 500
