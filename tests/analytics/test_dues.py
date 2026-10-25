"""What a dues row carries, and in what order [BR1.1, BR1.5, BR1.6].

Membership itself is in ``test_dues_membership.py``; this module covers
the row's contents and the collection's shape.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.dues import DuesRow, dues_rows
from app.analytics.seats import ledger_for_seats, owned_seats
from app.money import Money
from tests.analytics.conftest import add_batch, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture, make_teacher


def _rows(session: Session, teacher: TeacherFixture) -> list[DuesRow]:
    """Build the dues rows for a teacher, the way the route does.

    :param session: The session under test
    :param teacher: The teacher
    :return: The dues rows
    """
    seats = owned_seats(session, lens_for(teacher))
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    return list(dues_rows(seats, ledger))


def test_three_seats_across_two_batches_produce_exactly_two_rows(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """BR1.1's own assertable case, with its own figures.

    Three seats with outstanding 0, 500 and 1200 produce exactly two
    rows carrying 500 and 1200 and naming their own batches.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    second = add_batch(owner_session, teacher.owner_id, "Chemistry")

    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Settled",
        entries=[
            ("charge", "2027-01", "800.00"),
            ("receipt", "2027-01", "800.00"),
        ],
    )
    owes_500 = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Owes five hundred",
        entries=[
            ("charge", "2027-01", "1000.00"),
            ("receipt", "2027-01", "500.00"),
        ],
    )
    owes_1200 = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=second,
        display_name="Owes twelve hundred",
        entries=[("charge", "2027-01", "1200.00")],
    )

    rows = _rows(restricted_session, teacher)

    assert len(rows) == 2
    by_seat = {row.enrollment_id: row for row in rows}
    assert by_seat[owes_500].outstanding == Money("500.00")
    assert by_seat[owes_1200].outstanding == Money("1200.00")
    assert by_seat[owes_500].batch_name == "Physics"
    assert by_seat[owes_1200].batch_name == "Chemistry"


def test_a_teacher_with_batches_and_no_debts_gets_an_empty_list(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Nobody owing is an empty collection, not an error [BR1.5].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Paid",
        entries=[
            ("charge", "2027-01", "400.00"),
            ("receipt", "2027-01", "400.00"),
        ],
    )

    assert _rows(restricted_session, teacher) == []


def test_a_teacher_with_no_seats_at_all_gets_an_empty_list(
    owner_session: Session,
    restricted_session: Session,
) -> None:
    """The degenerate case is still an empty list [BR1.5].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    empty = make_teacher(owner_session, name="No students yet")

    assert _rows(restricted_session, empty) == []


def test_rows_are_ordered_by_outstanding_descending(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The largest debt is first, decided here [functional-spec § 7a].

    Ordered in the fold rather than in the client: a client sorting a
    domain list is the second of the five erosion paths ``team.md``
    names, and it is the one most easily reached on a list screen.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    for name, amount in (("Small", "100.00"), ("Large", "3000.00"), ("Mid", "900.00")):
        seat_with_ledger(
            owner_session,
            restricted_session,
            batch_id=teacher.batch_id,
            display_name=name,
            entries=[("charge", "2027-01", amount)],
        )

    rows = _rows(restricted_session, teacher)

    assert [row.outstanding for row in rows] == [
        Money("3000.00"),
        Money("900.00"),
        Money("100.00"),
    ]


def test_the_row_carries_the_oldest_unpaid_period(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Which period the debt starts in [BR1.1].

    Three periods, the first of them settled, so the answer is the
    middle one rather than either boundary -- an implementation taking
    ``min(per_cycle)`` without the balance test would read January.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Three periods",
        entries=[
            ("charge", "2027-01", "500.00"),
            ("receipt", "2027-01", "500.00"),
            ("charge", "2027-02", "500.00"),
            ("charge", "2027-03", "500.00"),
        ],
    )

    rows = {row.enrollment_id: row for row in _rows(restricted_session, teacher)}

    assert rows[seat].oldest_unpaid_period == "2027-02"


def test_the_in_fold_period_equals_the_built_function_s_answer(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The reimplementation is pinned to the built one [NFR20.33].

    ``app/fees/balances.py``'s ``oldest_unpaid_period`` takes one
    enrollment and folds its ledger, so calling it per dues row is a
    query per seat -- the exact N+1 BR1.6 forbids, reached by reusing a
    correct function at the wrong granularity.

    D5 therefore computes the same value from the ``per_cycle`` map it
    already has. **Without this test that copy is merely cheap**; with
    it, a later change to the built function that this copy does not
    track fails.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    from app.fees.balances import oldest_unpaid_period

    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Pinned",
        entries=[
            ("charge", "2027-05", "600.00"),
            ("receipt", "2027-05", "600.00"),
            ("charge", "2027-06", "600.00"),
            ("receipt", "2027-06", "100.00"),
            ("charge", "2027-07", "600.00"),
        ],
    )

    rows = {row.enrollment_id: row for row in _rows(restricted_session, teacher)}

    assert rows[seat].oldest_unpaid_period == oldest_unpaid_period(
        restricted_session, seat
    )


def test_the_row_carries_an_enrollment_id_and_no_account_id(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A dues list is a list of people, and names none of them globally.

    The seat is the teacher-facing key; a ``student_account_id`` would
    hand teacher A a stable handle on a student also enrolled with
    teacher B [ADR-001]. Asserted on the dataclass's own fields, since
    the schema-wide gate covers the wire shape.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Someone",
        entries=[("charge", "2027-01", "300.00")],
    )

    row = _rows(restricted_session, teacher)[0]
    fields = set(DuesRow.__dataclass_fields__)

    assert "enrollment_id" in fields
    assert (
        not {
            "account_id",
            "student_account_id",
            "guardian_account_id",
        }
        & fields
    )
    assert row.display_name == "Someone"
