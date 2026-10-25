"""Two verifications racing on one claim converge [NFR6.35, NFR14.45].

**Double-crediting a payment is a money error**, and it is the one
concurrent path in this unit that the fee-cycle unique constraint does
not already cover: a claim has no `(enrollment, period)` uniqueness to
conflict on, so two teachers approving the same claim at the same
moment would otherwise write two full sets of ledger entries and credit
the payment twice.

The mechanism the design names is a **conditional update**: the status
moves only `WHERE status = 'pending'`, and zero rows updated means
another verification won. The loser raises `ConflictError` rather than
appending a second set of entries, because **correction is a distinct
path** [BR5.7] with its own audit trail.

Same shape as `test_generation_races.py`: real threads released from a
barrier against real PostgreSQL, asserting the **outcome**. A sequential
version passes against an implementation with no guard at all.

`import threading` is at the top of this file, as the project requires.
"""

from __future__ import annotations

import threading
import uuid

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import PaymentClaim
from app.errors import ConflictError
from app.fees.claims import submit_claim
from app.fees.ledger_writer import append_entry
from app.fees.verification import verify_claim
from app.money import Money
from tests.batches.conftest import TeacherFixture

#: Matches the generation races and the ceilings precedent.
WORKERS = 8


def _charged_claim(
    session: Session,
    seat: uuid.UUID,
    account_id: uuid.UUID,
) -> PaymentClaim:
    """Arrange one 1000.00 charge and a pending claim against it.

    :param session: The session to write through
    :param seat: The enrollment
    :param account_id: Who submitted the claim
    :return: The pending claim
    """
    append_entry(
        session,
        enrollment_id=seat,
        period="2027-02",
        kind="charge",
        amount=Money("1000.00"),
    )
    session.commit()
    return submit_claim(
        session,
        enrollment_id=seat,
        submitted_by_account_id=account_id,
        claimed_amount=Money("1000.00"),
        channel="bKash",
    )


def test_racing_verifications_record_one_decision_and_one_receipt(
    restricted_engine: Engine,
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    claim = _charged_claim(restricted_session, seat, account_factory())
    claim_id = claim.id

    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(WORKERS)
    accepted: list[int] = []
    conflicts: list[int] = []
    other: list[BaseException] = []
    lock = threading.Lock()

    def attempt() -> None:
        session = factory()
        try:
            barrier.wait(timeout=30)
            verify_claim(
                session,
                claim_id=claim_id,
                approved_amount=Money("1000.00"),
                shortfall_disposition=None,
                verified_by_account_id=teacher.account_id,
            )
            with lock:
                accepted.append(1)
        except ConflictError:
            with lock:
                conflicts.append(1)
        except BaseException as error:  # noqa: BLE001  recorded, then asserted
            with lock:
                other.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert other == [], (
        f"{len(other)} racing verifications raised something other than "
        f"ConflictError, the first being {other[0]!r}. The loser of the "
        "race must raise the class the taxonomy already names for this "
        "shape [NFR14.45]"
    )

    # THE OUTCOME ASSERTION, not a call count. Exactly one verification
    # took effect and the rest were refused.
    assert len(accepted) == 1, (
        f"{len(accepted)} of {WORKERS} racing verifications were accepted. "
        "Each one appends a full set of ledger entries, so a second "
        "acceptance credits the payment twice [NFR6.35]"
    )
    assert len(conflicts) == WORKERS - 1

    verify = factory()
    try:
        receipts = verify.execute(
            sa.text(
                "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
                "WHERE enrollment_id = :id AND kind = 'receipt'"
            ),
            {"id": seat},
        ).scalar_one()
        assert Money(receipts) == Money("1000.00"), (
            f"receipts total {receipts} against one 1000.00 claim: the "
            "payment was credited more than once"
        )

        decided = verify.get(PaymentClaim, claim_id)
        assert decided is not None
        assert decided.status == "approved_full"
        # The loser must not have overwritten the winner's decision with
        # a previous_decision record of its own, which would make a
        # concurrent repeat indistinguishable from a correction.
        assert decided.previous_decision is None, (
            "a racing verification was recorded as a CORRECTION. "
            "Correction is a distinct path with its own audit trail "
            "[BR5.7]; a concurrent repeat is a conflict"
        )
    finally:
        verify.close()


def test_a_deliberate_correction_is_still_permitted(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # The guard must refuse a concurrent REPEAT without refusing a
    # deliberate correction, which FR9.2 requires to stay possible. A
    # guard written as "refuse any verification of a decided claim"
    # would pass the race test above and break correction entirely.
    claim = _charged_claim(restricted_session, seat, account_factory())

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
        correcting=True,
    )

    assert corrected.claim.status == "approved_partial"
    assert corrected.claim.previous_decision is not None


def test_re_verifying_a_decided_claim_without_correcting_is_refused(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
    account_factory: object,
) -> None:
    # The sequential half of the same rule. It does NOT replace the
    # race test -- it would pass against an implementation with no
    # atomicity at all -- but it states the intent plainly: deciding a
    # claim twice is a conflict unless the second is declared a
    # correction.
    import pytest

    claim = _charged_claim(restricted_session, seat, account_factory())

    verify_claim(
        restricted_session,
        claim_id=claim.id,
        approved_amount=Money("1000.00"),
        shortfall_disposition=None,
        verified_by_account_id=teacher.account_id,
    )

    with pytest.raises(ConflictError):
        verify_claim(
            restricted_session,
            claim_id=claim.id,
            approved_amount=Money("800.00"),
            shortfall_disposition="waived",
            verified_by_account_id=teacher.account_id,
        )
