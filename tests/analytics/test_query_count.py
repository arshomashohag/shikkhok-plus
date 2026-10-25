"""The statement count is flat in BATCHES per teacher [BR1.6, NFR20.31].

**The shape is D3's and the DIMENSION is not**, and that difference is
the whole reason this file exists. ``tests/fees/test_query_count.py``
grows **seats within one batch**, which is correct for a per-batch read
-- and D5 is the first unit reading across **every batch a teacher
owns**, so a test growing seats inside a single batch **passes against a
correct-looking per-batch loop**. That loop is BR1.6's trap.

So seats-per-batch is held fixed and batches-per-teacher grows.

**The property is constant-in-N, not minimal.** D3's file states why and
it holds here: asserting a literal count pins an implementation detail,
and the first time a correct change moves it the number gets raised
rather than investigated -- which is how a check gets retired while
staying green. ``at_two == at_twenty_five`` asserts the thing that
actually matters.

**No latency assertion anywhere** [NFR2.10]. D3 established that
statement count is the measurable property on this product's single
small instance, and a timing assertion there is flaky in both
directions.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.analytics.dues import dues_rows
from app.analytics.earnings import period_totals, trend
from app.analytics.seats import ledger_for_seats, owned_seats
from app.analytics.upcoming import next_exam
from tests.analytics.conftest import add_batch, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture, make_teacher
from tests.fees.test_query_count import QueryCounter

#: Two seats per batch, held FIXED while batches vary. Two rather than
#: one because a one-row fixture cannot see N+1 at all: one row produces
#: one follow-up query, indistinguishable from none.
SEATS_PER_BATCH = 2


@pytest.fixture
def counted(restricted_session: Session) -> Iterator[QueryCounter]:
    """Count statements issued on the session's engine.

    :param restricted_session: The session under test
    :return: A context manager yielding the counter
    """
    counter = QueryCounter()
    engine: Engine = restricted_session.get_bind()
    sa.event.listen(engine, "before_cursor_execute", counter)
    yield counter
    sa.event.remove(engine, "before_cursor_execute", counter)


def _teacher_with_batches(
    owner_session: Session,
    restricted_session: Session,
    *,
    batches: int,
    label: str,
) -> TeacherFixture:
    """Build a teacher owning ``batches`` batches of two charged seats.

    ``make_teacher`` creates the teacher **and one batch**, so the
    remainder are added to the same owner -- which is what lets this
    grow the dimension D3's test holds fixed.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session the charges are written on
    :param batches: How many batches the teacher owns
    :param label: A distinguishing name
    :return: The teacher
    """
    teacher = make_teacher(owner_session, name=f"{label} 1")
    batch_ids = [teacher.batch_id]
    for index in range(2, batches + 1):
        batch_ids.append(add_batch(owner_session, teacher.owner_id, f"{label} {index}"))

    for position, batch_id in enumerate(batch_ids):
        for seat in range(SEATS_PER_BATCH):
            seat_with_ledger(
                owner_session,
                restricted_session,
                batch_id=batch_id,
                display_name=f"{label} {position}-{seat}",
                entries=[
                    ("charge", "2027-02", "1000.00"),
                    ("receipt", "2027-02", "400.00"),
                ],
            )
    return teacher


def _read_dues(session: Session, teacher: TeacherFixture) -> None:
    """Perform the dues read exactly as the route does.

    :param session: The session under test
    :param teacher: Whose dues to read
    :return: None
    """
    seats = owned_seats(session, lens_for(teacher))
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    dues_rows(seats, ledger)


def test_the_dues_read_does_not_grow_with_the_number_of_batches(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """The same number of statements at 2 batches and at 25.

    **This is the assertion a seat-growing test cannot make.** A read
    looping over owned batches and querying each one is flat in seats
    and linear in batches, so it passes D3's shape and fails here.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    small = _teacher_with_batches(
        owner_session, restricted_session, batches=2, label="Small"
    )
    large = _teacher_with_batches(
        owner_session, restricted_session, batches=25, label="Large"
    )

    counted.count = 0
    _read_dues(restricted_session, small)
    at_two = counted.count

    counted.count = 0
    _read_dues(restricted_session, large)
    at_twenty_five = counted.count

    assert at_two == at_twenty_five, (
        f"{at_two} statements for 2 batches and {at_twenty_five} for 25: "
        "the dues read issues a query per batch [BR1.6, NFR20.31]. D3's "
        "own test grows seats within ONE batch and passes against this "
        "shape, which is why this one grows batches."
    )


def test_the_dues_read_does_not_grow_with_the_number_of_seats_either(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """D3's dimension too, so neither axis is left unasserted.

    The per-row trap is ``app/fees/balances.py``'s
    ``oldest_unpaid_period``: correct, tested, and one
    ``derive_for_enrollment`` per call [NFR20.32].

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    small = make_teacher(owner_session, name="Two seats")
    for index in range(2):
        seat_with_ledger(
            owner_session,
            restricted_session,
            batch_id=small.batch_id,
            display_name=f"Small {index}",
            entries=[("charge", "2027-02", "1000.00")],
        )

    large = make_teacher(owner_session, name="Twenty-five seats")
    for index in range(25):
        seat_with_ledger(
            owner_session,
            restricted_session,
            batch_id=large.batch_id,
            display_name=f"Large {index}",
            entries=[("charge", "2027-02", "1000.00")],
        )

    counted.count = 0
    _read_dues(restricted_session, small)
    at_two = counted.count

    counted.count = 0
    _read_dues(restricted_session, large)
    at_twenty_five = counted.count

    assert at_two == at_twenty_five, (
        f"{at_two} statements for 2 seats and {at_twenty_five} for 25: a "
        "function taking a single enrollment_id is being called per row "
        "[NFR20.32]."
    )


def test_the_dues_read_is_two_statements_not_a_handful(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """A generous upper bound, excluding the per-seat shapes.

    The property above is the real verifier; this excludes the shapes
    that are constant-in-N and still wrong -- a second fold, or a cycle
    lookup the design does not need.

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    teacher = _teacher_with_batches(
        owner_session, restricted_session, batches=4, label="Bounded"
    )

    counted.count = 0
    _read_dues(restricted_session, teacher)

    assert counted.count <= 4, (
        f"{counted.count} statements for a four-batch dues read. The "
        "design is two: the owned-seat join and the ledger select "
        "[performance § 1]."
    )


def test_the_overview_read_does_not_grow_with_the_number_of_batches(
    restricted_session: Session,
    owner_session: Session,
    counted: QueryCounter,
) -> None:
    """Three blocks, three statements, whatever the teacher's size.

    The earnings total and the trend fold the **same** ledger read, so
    two of the three figures cost one statement between them
    [NFR20.34].

    :param restricted_session: The session under test
    :param owner_session: A session able to arrange fixture data
    :param counted: The statement counter
    :return: None
    """
    import datetime as dt

    small = _teacher_with_batches(
        owner_session, restricted_session, batches=2, label="OvSmall"
    )
    large = _teacher_with_batches(
        owner_session, restricted_session, batches=25, label="OvLarge"
    )
    today = dt.date(2027, 2, 15)

    def read(teacher: TeacherFixture) -> None:
        seats = owned_seats(restricted_session, lens_for(teacher))
        ledger = ledger_for_seats(
            restricted_session, [seat.enrollment_id for seat in seats]
        )
        entries = [entry for rows in ledger.values() for entry in rows]
        trend(period_totals(entries))
        next_exam(restricted_session, lens_for(teacher), today=today)

    counted.count = 0
    read(small)
    at_two = counted.count

    counted.count = 0
    read(large)
    at_twenty_five = counted.count

    assert at_two == at_twenty_five, (
        f"{at_two} statements for 2 batches and {at_twenty_five} for 25 "
        "on the overview read [NFR20.34]."
    )
    assert at_twenty_five <= 5, (
        f"{at_twenty_five} statements for the overview. The design is "
        "three: the seat join, the ledger select and the exam select "
        "[performance § 2]."
    )
