"""Bolt 5's confidence hypothesis, asserted in both halves.

> *A student who left mid-year owing money appears on the cross-batch
> dues screen; an active student owing nothing does not.*

**Both halves, because a test covering one passes against an
implementation failing the other** [BR1.2, BR1.3]. They are the opposite
sides of one predicate:

* an **inactive, owing** seat is **present** -- the half a test using
  only active owing seats cannot see, because such a test passes against
  a query carrying ``inactive_from``;
* an **active, owing-nothing** seat is **absent** -- the half a
  membership-only test cannot see.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.analytics.dues import dues_rows
from app.analytics.seats import ledger_for_seats, owned_seats
from app.money import Money
from tests.analytics.conftest import lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def _rows(session: Session, teacher: TeacherFixture) -> list[object]:
    """Build the dues rows for a teacher, the way the route does.

    :param session: The session under test
    :param teacher: The teacher
    :return: The dues rows
    """
    seats = owned_seats(session, lens_for(teacher))
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    return list(dues_rows(seats, ledger))


def test_an_inactive_seat_that_owes_money_appears(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A student who left owing money is exactly who the view is for.

    **The seat is both inactive AND owing**, which is the fixture shape
    the rule requires: a test using only active owing seats passes
    against a query carrying ``inactive_from`` [BR1.2].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    left_owing = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Left owing",
        entries=[("charge", "2027-01", "1500.00")],
        inactive_from=dt.date(2027, 1, 20),
    )

    rows = _rows(restricted_session, teacher)
    present = {row.enrollment_id for row in rows}  # type: ignore[attr-defined]

    assert left_owing in present, (
        "an inactive seat owing 1500.00 is missing from the dues view. "
        "Membership is driven by outstanding balance and NEVER by active "
        "status [BR1.2] -- this is the roster predicate being reused."
    )


def test_an_active_seat_owing_nothing_is_absent(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The other half: owing nothing means absent, active or not [BR1.3].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    settled = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Paid up",
        entries=[
            ("charge", "2027-01", "1000.00"),
            ("receipt", "2027-01", "1000.00"),
        ],
    )

    rows = _rows(restricted_session, teacher)
    present = {row.enrollment_id for row in rows}  # type: ignore[attr-defined]

    assert settled not in present, (
        "a seat owing nothing appeared in the dues view. A dues view "
        "listing everyone is not a dues view [BR1.3]."
    )


def test_both_halves_together_in_one_teacher_s_view(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The hypothesis as one sentence, over one dues read.

    Stated as its own test rather than relying on the two above, because
    the hypothesis is about what one teacher sees on one screen.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    left_owing = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Left mid-year, owing",
        entries=[("charge", "2027-02", "900.00")],
        inactive_from=dt.date(2027, 2, 10),
    )
    active_settled = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Active, settled",
        entries=[
            ("charge", "2027-02", "900.00"),
            ("receipt", "2027-02", "900.00"),
        ],
    )

    present = {
        row.enrollment_id  # type: ignore[attr-defined]
        for row in _rows(restricted_session, teacher)
    }

    assert left_owing in present
    assert active_settled not in present


def test_a_declined_seat_owing_money_is_absent(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The mistyped-digit case [BR1.7].

    A seat someone declined because it was never theirs must not keep
    appearing on a list of people to chase for money. It **owes**,
    deliberately: a declined seat owing nothing is absent under BR1.3
    anyway and would prove nothing about this clause.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    declined = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Wrong number",
        entries=[("charge", "2027-02", "1100.00")],
        student_decision="declined",
    )

    present = {
        row.enrollment_id  # type: ignore[attr-defined]
        for row in _rows(restricted_session, teacher)
    }

    assert declined not in present


def test_a_waived_balance_removes_the_seat_from_the_view(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Forgiveness relieves the obligation, so nothing is owed [BR1.3].

    The case an "outstanding = charges - receipts" implementation gets
    wrong: a fully waived cycle has received nothing and owes nothing.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    waived = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Waived",
        entries=[
            ("charge", "2027-03", "700.00"),
            ("forgiveness", "2027-03", "700.00"),
        ],
    )

    present = {
        row.enrollment_id  # type: ignore[attr-defined]
        for row in _rows(restricted_session, teacher)
    }

    assert waived not in present


def test_recording_a_receipt_removes_the_row_with_no_intervening_job(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Computed on open; no generate step, no cached rollup [BR1.4].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    from app.fees.ledger_writer import append_entry

    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="About to pay",
        entries=[("charge", "2027-04", "600.00")],
    )

    before = {
        row.enrollment_id  # type: ignore[attr-defined]
        for row in _rows(restricted_session, teacher)
    }
    assert seat in before

    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2027-04",
        kind="receipt",
        amount=Money("600.00"),
    )
    restricted_session.commit()

    after = {
        row.enrollment_id  # type: ignore[attr-defined]
        for row in _rows(restricted_session, teacher)
    }
    assert seat not in after
