"""Verification: the shortfall, the disposition, and correction.

**The separating case is the point of this file.** A cycle charged
1000, a claim of 1500, approved at 600:

===================================  ===========
Formula                              Shortfall
===================================  ===========
``charged - approved`` (correct)     **400.00**
``claimed - approved`` (wrong)         900.00
===================================  ===========

A test using a claim equal to the charge cannot tell those apart, which
is why the named boundary case uses one where they differ. A claim is an
*assertion*; a charge is the *obligation*. Measuring against the claim
would let a payer change what they owe by changing what they assert.

Every other figure here was computed the same way, through the fold.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import PaymentClaim
from app.errors import ValidationError
from app.fees.balances import derive_for_enrollment
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.verification import reject_claim, verify_claim
from app.money import Money
from tests.batches.conftest import TeacherFixture


def _charge(session: Session, seat: uuid.UUID, period: str, amount: str) -> None:
    """Append one charge entry.

    :param session: The session to write through
    :param seat: The enrollment
    :param period: The period
    :param amount: The amount, as a canonical string
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period=period,
        kind="charge",
        amount=Money(amount),
    )
    session.commit()


def _claim(
    session: Session,
    seat: uuid.UUID,
    account_id: uuid.UUID,
    amount: str,
) -> PaymentClaim:
    """Submit one pending claim.

    :param session: The session to write through
    :param seat: The enrollment
    :param account_id: Who submitted it
    :param amount: The claimed amount, as a canonical string
    :return: The pending claim
    """
    return submit_claim(
        session,
        enrollment_id=seat,
        submitted_by_account_id=account_id,
        claimed_amount=Money(amount),
        channel="bKash",
        transaction_id="TX-1",
    )


# ---------------------------------------------------------------------
# BR5.3 — the shortfall base.
# ---------------------------------------------------------------------


def test_the_shortfall_is_charged_minus_approved_not_claimed_minus_approved(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # THE SEPARATING CASE: 1000 charged, 1500 claimed, 600 approved.
    # Correct is 400.00; measuring against the claim gives 900.00.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1500.00")

    outcome = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="carried",
        verified_by_account_id=teacher.account_id,
    )

    assert outcome.shortfall == Money("400.00")


def test_the_carried_shortfall_lands_in_the_next_period(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # Computed: carried leaves 0.00 in the origin and 400.00 in the
    # next period.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1500.00")

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="carried",
        verified_by_account_id=teacher.account_id,
    )

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.per_cycle["2027-01"] == Money("0.00")
    assert derived.per_cycle["2027-02"] == Money("400.00")
    assert derived.total_outstanding == Money("400.00")


def test_the_waived_shortfall_carries_nothing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # Computed: waived leaves 0.00 and nothing carried. The two
    # dispositions have OPPOSITE consequences for the student, which is
    # why neither may be a default.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1500.00")

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="waived",
        verified_by_account_id=teacher.account_id,
    )

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_outstanding == Money("0.00")
    assert derived.total_forgiven == Money("400.00")
    assert derived.total_carry_forward == Money("0.00")


# ---------------------------------------------------------------------
# BR5.4 — the disposition is required, and only when there is one.
# ---------------------------------------------------------------------


def test_a_shortfall_with_no_disposition_is_refused(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    with pytest.raises(ValidationError):
        verify_claim(
            restricted_session,
            claim_id=claim.id,
            approved_amount=Money("600.00"),
            shortfall_disposition=None,
            verified_by_account_id=teacher.account_id,
        )
    restricted_session.rollback()

    reloaded = restricted_session.get(PaymentClaim, claim.id)
    assert reloaded is not None
    assert reloaded.status == "pending"


def test_a_full_approval_needs_no_disposition(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    outcome = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )

    assert outcome.shortfall == Money("0.00")
    assert outcome.claim.status == "approved_full"
    assert outcome.claim.shortfall_disposition is None
    assert derive_for_enrollment(restricted_session, seat).total_outstanding == Money(
        "0.00"
    )


def test_over_approval_records_a_receipt_and_a_credit_grant(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR4.2] Computed: a 1000 charge approved at 1200 gives
    # outstanding 0.00 and credit 200.00, identity at -200 both sides.
    # Cash in is receipt + credit_grant, which is exactly where
    # ADR-002's first correction attempt failed.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1200.00")

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1200.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )

    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_receipt == Money("1000.00")
    assert derived.total_credit_grant == Money("200.00")
    assert derived.total_outstanding == Money("0.00")
    assert derived.available_credit == Money("200.00")


# ---------------------------------------------------------------------
# BR5.5 — the decision and its entries commit together.
# ---------------------------------------------------------------------


def test_the_decision_and_its_entries_are_one_transaction(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # A partial commit would leave a claim marked approved with no
    # money recorded, or money recorded against a pending claim -- and
    # the ledger is append-only, so the second cannot be tidied away.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    # An impossible disposition reaches the entry-writing branch after
    # the status has been set in the session, so a non-atomic
    # implementation leaves the status changed and no entries behind.
    with pytest.raises(ValidationError):
        verify_claim(
            restricted_session,
            claim_id=claim.id,
            approved_amount=Money("600.00"),
            shortfall_disposition="not-a-disposition",
            verified_by_account_id=teacher.account_id,
        )
    restricted_session.rollback()

    reloaded = restricted_session.get(PaymentClaim, claim.id)
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.approved_amount is None
    entries = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM ledger_entry WHERE enrollment_id = :id "
            "AND kind <> 'charge'"
        ),
        {"id": seat},
    ).scalar_one()
    assert entries == 0


def test_a_verification_records_who_and_when(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    before = dt.datetime.now(tz=dt.UTC)
    outcome = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )

    assert outcome.claim.verified_by_account_id == teacher.account_id
    assert outcome.claim.verified_at is not None
    assert outcome.claim.verified_at >= before


# ---------------------------------------------------------------------
# BR5.6 — rejection records nothing.
# ---------------------------------------------------------------------


def test_rejection_records_no_ledger_entry_and_leaves_the_balance(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")
    before = derive_for_enrollment(restricted_session, seat).total_outstanding

    rejected = reject_claim(
        restricted_session,
        claim_id=claim.id,
        verified_by_account_id=teacher.account_id,
    )

    assert rejected.status == "rejected"
    assert rejected.approved_amount is None
    entries = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM ledger_entry WHERE enrollment_id = :id "
            "AND kind <> 'charge'"
        ),
        {"id": seat},
    ).scalar_one()
    assert entries == 0
    assert derive_for_enrollment(restricted_session, seat).total_outstanding == before


# ---------------------------------------------------------------------
# BR5.7, BR3.3 — correction retains the previous decision.
# ---------------------------------------------------------------------


def test_a_correction_retains_the_previous_decision(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    corrected = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="waived",
        verified_by_account_id=teacher.account_id,
        # A DELIBERATE correction, declared as one. Without the flag
        # this is indistinguishable from a concurrent repeat, which
        # must be a ConflictError [NFR6.35].
        correcting=True,
    )

    previous = corrected.claim.previous_decision
    assert previous is not None
    assert previous["approved_amount"] == "1000.00"
    assert previous["status"] == "approved_full"
    assert previous["verified_by_account_id"] == str(teacher.account_id)
    assert previous["verified_at"]


def test_a_correction_compensates_rather_than_rewriting(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR3.3] The original rows stay and a compensating entry is
    # appended. After correcting 1000 down to 600 with the remainder
    # waived, the balance is 0.00 and BOTH receipts are on record.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )
    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="waived",
        verified_by_account_id=teacher.account_id,
        correcting=True,
    )

    receipts = [
        Money(row[0])
        for row in restricted_session.execute(
            sa.text(
                "SELECT amount FROM ledger_entry WHERE enrollment_id = :id "
                "AND kind = 'receipt' ORDER BY created_at"
            ),
            {"id": seat},
        )
    ]
    # The original 1000 receipt is still there, and the correction
    # appended a compensating forgiveness plus the new 600 receipt
    # rather than editing it.
    assert Money("1000.00") in receipts
    derived = derive_for_enrollment(restricted_session, seat)
    assert derived.total_outstanding == Money("0.00")

    superseded = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM ledger_entry WHERE enrollment_id = :id "
            "AND superseded_by_id IS NOT NULL"
        ),
        {"id": seat},
    ).scalar_one()
    assert superseded >= 1


def test_a_corrected_claim_reads_approved_partial(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # [BR6.3] A guardian must be able to tell a partial approval from a
    # full one, or a dispute has no shared record.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1500.00")

    outcome = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("600.00"),
        shortfall_disposition="carried",
        verified_by_account_id=teacher.account_id,
    )

    assert outcome.claim.status == "approved_partial"
    assert outcome.claim.approved_amount == Money("600.00")
    assert outcome.claim.shortfall_disposition == "carried"


def test_a_rejection_can_be_corrected_to_an_approval(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # The state machine has no terminal state: FR9.2 makes every
    # verification correctable.
    _charge(restricted_session, seat, "2027-01", "1000.00")
    claim = _claim(restricted_session, seat, account_factory(), "1000.00")

    reject_claim(
        restricted_session,
        claim_id=claim.id,
        verified_by_account_id=teacher.account_id,
    )
    outcome = verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
        correcting=True,
    )

    assert outcome.claim.status == "approved_full"
    assert outcome.claim.previous_decision is not None
    assert outcome.claim.previous_decision["status"] == "rejected"
    assert derive_for_enrollment(restricted_session, seat).total_outstanding == Money(
        "0.00"
    )
