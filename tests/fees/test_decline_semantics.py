"""The decline asymmetry, from BOTH roles [BR1.6-BR1.9].

**A student decline stops generation and reverses what accrued. A
guardian decline does neither.** The asymmetry is the whole point, and
this project has already been bitten by its presentation half: a decline
confirmation reading "the fee stops" was shown to guardians as well as
students, telling a guardian a debt was cancelled when it was not.

So this file tests the rule **from both roles rather than from the one it
was written for**, which is the correction team memory records: a
role-dependent rule is checked against every surface it reaches, not only
the screen where it was written.

The arithmetic is computed, not asserted: a 1000 charge plus a 1000
forgiveness gives outstanding 0.00 with the identity balanced at 0 = 0
and the original `charge` row still present. Reversal is a REVERSAL
ENTRY, never a deleted row -- the ledger is append-only.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.generation import generate_due_cycles
from app.fees.ledger_writer import void_accrued_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll
from tests.fees.conftest import set_decision, set_joined_on

IN_FEBRUARY = dt.date(2027, 2, 20)
IN_MARCH = dt.date(2027, 3, 20)


def _periods(session: Session, enrollment_id: uuid.UUID) -> list[str]:
    """List the periods a seat has cycles for.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The period keys, oldest first
    """
    return [
        row[0]
        for row in session.execute(
            sa.text(
                "SELECT period FROM fee_cycle WHERE enrollment_id = :id ORDER BY period"
            ),
            {"id": enrollment_id},
        )
    ]


def _kinds(session: Session, enrollment_id: uuid.UUID) -> list[tuple[str, Money]]:
    """List a seat's ledger entries as (kind, amount) pairs.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The entries, oldest first
    """
    return [
        (row[0], Money(row[1]))
        for row in session.execute(
            sa.text(
                "SELECT kind, amount FROM ledger_entry "
                "WHERE enrollment_id = :id ORDER BY created_at, kind"
            ),
            {"id": enrollment_id},
        )
    ]


def _outstanding(session: Session, enrollment_id: uuid.UUID) -> Money:
    """Derive a seat's outstanding balance through the money module.

    Read through ``app.money.derive`` rather than summed in SQL, because
    the per-period floor is the rule and a SQL sum would reimplement it
    [BR3.5].

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The outstanding balance
    """
    from app.fees.balances import derive_for_enrollment

    return derive_for_enrollment(session, enrollment_id).total_outstanding


# ---------------------------------------------------------------------
# BR1.9 — a pending seat generates.
# ---------------------------------------------------------------------


def test_a_pending_seat_generates(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
) -> None:
    # Pending is the NORMAL state of a new seat, not a withheld one. A
    # teacher who adds a batch of students on Monday must see fees for
    # all of them without each installing the app first -- otherwise
    # the product is useless for the one task it exists for.
    seat_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Pending",
        student_decision="pending",
        guardian_decision="pending",
    )
    set_joined_on(owner_session, enrollment_id=seat_id, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    assert _periods(restricted_session, seat_id) == ["2027-02"]


# ---------------------------------------------------------------------
# BR1.7 — a GUARDIAN decline changes nothing about the money.
# ---------------------------------------------------------------------


def test_a_declined_guardian_link_does_not_stop_generation(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # If a guardian's refusal stopped generation, any student could
    # clear their own fees by having a guardian refuse.
    set_decision(owner_session, enrollment_id=seat, guardian="declined")
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=IN_MARCH)

    assert _periods(restricted_session, seat) == ["2027-02", "2027-03"]


def test_a_declined_guardian_link_writes_no_reversal(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The student's obligation stands IN FULL. This is the half the
    # presentation defect got wrong: the guardian was told the fee
    # stopped, and it did not.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    set_decision(owner_session, enrollment_id=seat, guardian="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    assert _kinds(restricted_session, seat) == [("charge", Money("1500.00"))]
    assert _outstanding(restricted_session, seat) == Money("1500.00")


# ---------------------------------------------------------------------
# BR1.6 — a STUDENT decline stops generation and voids what accrued.
# ---------------------------------------------------------------------


def test_a_declined_student_link_stops_generation(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    set_decision(owner_session, enrollment_id=seat, student="declined")
    generate_due_cycles(restricted_session, today=IN_MARCH)

    assert _periods(restricted_session, seat) == ["2027-02"]


def test_a_declined_student_link_voids_the_accrued_balance_by_reversal(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Computed: charge 1500 plus forgiveness 1500 gives outstanding
    # 0.00, with the ORIGINAL charge row still present. Deleting the
    # charge would also give zero and would destroy the audit trail
    # FR9.2 requires -- which is why the assertion is on both.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    set_decision(owner_session, enrollment_id=seat, student="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    entries = _kinds(restricted_session, seat)
    assert ("charge", Money("1500.00")) in entries
    assert ("forgiveness", Money("1500.00")) in entries
    assert _outstanding(restricted_session, seat) == Money("0.00")


def test_voiding_a_partly_paid_cycle_forgives_only_the_remainder(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The rule forgives the OUTSTANDING balance, not the charge. A seat
    # charged 1500 with 500 received must be forgiven 1000, or the
    # ledger records a relief that never happened.
    from app.fees.ledger_writer import append_entry

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="receipt",
        amount=Money("500.00"),
    )
    restricted_session.commit()

    set_decision(owner_session, enrollment_id=seat, student="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    forgiven = [
        pair for pair in _kinds(restricted_session, seat) if pair[0] == "forgiveness"
    ]
    assert forgiven == [("forgiveness", Money("1000.00"))]
    assert _outstanding(restricted_session, seat) == Money("0.00")


def test_voiding_a_settled_cycle_writes_no_forgiveness(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Nothing is owed, so there is nothing to relieve. A blanket
    # forgiveness of the charge would take the balance negative, which
    # the invariant forbids.
    from app.fees.ledger_writer import append_entry

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-02",
        kind="receipt",
        amount=Money("1500.00"),
    )
    restricted_session.commit()

    set_decision(owner_session, enrollment_id=seat, student="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    kinds = [pair[0] for pair in _kinds(restricted_session, seat)]
    assert "forgiveness" not in kinds
    assert _outstanding(restricted_session, seat) == Money("0.00")


# ---------------------------------------------------------------------
# BR1.8 — un-declining resumes without resurrecting a voided cycle.
# ---------------------------------------------------------------------


def test_un_declining_resumes_without_resurrecting_voided_cycles(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Accepting a seat must not retroactively re-bill months the person
    # was not participating in: that punishes correcting a mistake.
    # February's 1500 was voided and stays at zero; March generates.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)

    set_decision(owner_session, enrollment_id=seat, student="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    set_decision(owner_session, enrollment_id=seat, student="accepted")
    generate_due_cycles(restricted_session, today=IN_MARCH)

    from app.fees.balances import derive_for_enrollment

    derived = derive_for_enrollment(restricted_session, seat)

    assert _periods(restricted_session, seat) == ["2027-02", "2027-03"]
    # The voided period stays at zero; only March carries a balance.
    assert derived.per_cycle["2027-02"] == Money("0.00")
    assert derived.per_cycle["2027-03"] == Money("1500.00")
    assert derived.total_outstanding == Money("1500.00")


def test_the_forgiveness_entries_are_not_reversed_on_acceptance(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    set_decision(owner_session, enrollment_id=seat, student="declined")
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    before = _kinds(restricted_session, seat)
    set_decision(owner_session, enrollment_id=seat, student="accepted")

    # Acceptance alone writes nothing. The forgiveness stands.
    assert _kinds(restricted_session, seat) == before


def test_voiding_twice_forgives_once(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The daily job calls this for every declined seat it sees, so it
    # runs again tomorrow. A second blanket forgiveness would take the
    # balance below zero.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))
    generate_due_cycles(restricted_session, today=IN_FEBRUARY)
    set_decision(owner_session, enrollment_id=seat, student="declined")

    void_accrued_cycles(restricted_session, enrollment_id=seat)
    once = _kinds(restricted_session, seat)
    void_accrued_cycles(restricted_session, enrollment_id=seat)

    assert _kinds(restricted_session, seat) == once
    assert _outstanding(restricted_session, seat) == Money("0.00")
