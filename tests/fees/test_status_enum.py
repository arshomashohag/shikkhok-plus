"""The server-computed fee status [BR6.1, BR6.3].

**The client never derives this.** `if (balance > 0) "Due" else "Paid"`
is a business rule about what counts as due wearing presentation's
clothes, and it diverges the first time a waiver is involved: **a fully
waived cycle has a zero balance and is not "Paid"**. That single case is
why the enum has four values rather than two, and it is the assertion
this file exists for.

Written from the state table in the functional spec, not from the
implementation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.fees.ledger_writer import append_entry
from app.fees.status import CLAIM_STATUS_VALUES, FEE_STATUS_VALUES, fee_status
from app.money import Money
from tests.batches.conftest import TeacherFixture


def _entry(session: Session, seat: uuid.UUID, kind: str, amount: str) -> None:
    """Append one entry in period 2027-01.

    :param session: The session to write through
    :param seat: The enrollment
    :param kind: The entry kind
    :param amount: The amount, as a canonical string
    :return: None
    """
    append_entry(
        session,
        enrollment_id=seat,
        period="2027-01",
        kind=kind,
        amount=Money(amount),
    )
    session.commit()


def test_an_untouched_charge_is_unpaid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    _entry(restricted_session, seat, "charge", "1000.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "unpaid"
    )


def test_a_part_settled_charge_is_partly_paid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "receipt", "300.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "partly_paid"
    )


def test_a_fully_received_charge_is_paid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "receipt", "1000.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "paid"
    )


def test_a_fully_waived_charge_is_waived_and_not_paid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # THE CASE THAT NEEDS THE ENUM. The balance is zero, so a
    # client-side `balance > 0` test reports "Paid" -- and nobody paid.
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "forgiveness", "1000.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "waived"
    )


def test_a_charge_settled_by_credit_is_paid_not_waived(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Credit IS money the family paid, just earlier. A cycle relieved by
    # credit is paid, which is the distinction between "relief included
    # cash or credit" and "relief was forgiveness alone".
    _entry(restricted_session, seat, "credit_grant", "1000.00")
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "credit_apply", "1000.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "paid"
    )


def test_a_part_waived_part_received_charge_is_paid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Settled, and relief included cash, so it is paid rather than
    # waived -- the teacher accepted 600 and excused the rest.
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "receipt", "600.00")
    _entry(restricted_session, seat, "forgiveness", "400.00")

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "paid"
    )


def test_a_carried_out_balance_leaves_the_origin_paid(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The origin period owes nothing once the balance moved, and the
    # obligation now lives in the receiving period.
    _entry(restricted_session, seat, "charge", "1000.00")
    _entry(restricted_session, seat, "receipt", "600.00")
    from app.fees.ledger_writer import append_carry_pair

    append_carry_pair(
        restricted_session,
        enrollment_id=seat,
        amount=Money("400.00"),
        origin="2027-01",
        receiver="2027-02",
    )
    restricted_session.commit()

    assert fee_status(restricted_session, enrollment_id=seat, period="2027-01") == (
        "paid"
    )
    assert fee_status(restricted_session, enrollment_id=seat, period="2027-02") == (
        "unpaid"
    )


def test_an_unknown_period_has_no_status(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # A period with no entries is not "paid": nothing was ever charged,
    # so there is nothing to have a status.
    with pytest.raises(KeyError):
        fee_status(restricted_session, enrollment_id=seat, period="2099-01")


def test_the_two_disposition_declarations_agree() -> None:
    # Two tuples exist deliberately and the docstring in
    # `app.fees.status` says so: the ORM's must stay importable
    # without pulling the fee package into the models, and the fee
    # package's must be TYPED so a membership test narrows. Two
    # declarations need a test, or the pair is a drift waiting to
    # happen -- which is this project's standing rule about any fact
    # stated in two places.
    from app.db.models import DISPOSITION_VALUES as MODEL_VALUES
    from app.fees.status import DISPOSITION_VALUES as CONTRACT_VALUES

    assert tuple(MODEL_VALUES) == tuple(CONTRACT_VALUES)


def test_the_claim_status_contract_matches_the_database_enum() -> None:
    # The same drift, over the four claim statuses. The migration
    # builds the column from the ORM's tuple and the client contract
    # is built from the fee package's.
    from app.db.models import CLAIM_STATUS_VALUES as MODEL_VALUES

    assert tuple(MODEL_VALUES) == tuple(CLAIM_STATUS_VALUES)


def test_the_status_sets_are_closed_and_match_the_rule() -> None:
    # The enum values are a contract with the client, and
    # `MessageKeyCoverageTest` on the Kotlin side keeps the two in step.
    assert FEE_STATUS_VALUES == ("paid", "partly_paid", "unpaid", "waived")
    assert CLAIM_STATUS_VALUES == (
        "pending",
        "approved_full",
        "approved_partial",
        "rejected",
    )
