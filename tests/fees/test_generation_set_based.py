"""Generation finds missing cycles set-based, and attempts only those [C-28].

The job used to issue an ``INSERT ... ON CONFLICT`` and a ``COMMIT`` for
every (seat, month) since each seat joined, every day, nearly all of them
no-ops. It now asks one anti-join which wanted pairs have no cycle and
attempts only those. Two properties pin that the narrowing is safe:

* **a hole anywhere is still filled** -- a seat whose ``joined_on`` moves
  earlier after generating gains exactly the earlier months, charged once,
  and the months it already had are counted skipped, not recharged;
* **a run with nothing new costs the same however long the history** --
  the statement count of a no-op rerun does not grow with the number of
  months generated, which is the whole point of the change.

The constraint-level guarantees (overlapping runs, reruns across days)
stay in ``test_generation_races.py`` and ``test_generation_across_days.py``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import FeeCycle, LedgerEntryRow
from app.fees.generation import generate_due_cycles
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_joined_on


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine runs inside the block.

    :param session: The session under test
    :return: A context manager yielding the growing statement list
    """
    engine = session.get_bind()
    seen: list[str] = []

    def _before(*args: object) -> None:
        """Record one statement.

        :param args: The event's arguments; the statement is the third
        :return: None
        """
        seen.append(str(args[2]))

    sa.event.listen(engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        sa.event.remove(engine, "before_cursor_execute", _before)


def _periods(session: Session, seat: uuid.UUID) -> list[str]:
    """List a seat's cycle periods, oldest first.

    :param session: The session to read through
    :param seat: The seat
    :return: The period keys
    """
    return list(
        session.scalars(
            sa.select(FeeCycle.period)
            .where(FeeCycle.enrollment_id == seat)
            .order_by(FeeCycle.period)
        )
    )


def _charges(session: Session, seat: uuid.UUID) -> list[str]:
    """List the periods a seat was charged for, one per charge.

    :param session: The session to read through
    :param seat: The seat
    :return: Period keys, oldest first, repeated if charged twice
    """
    return list(
        session.scalars(
            sa.select(LedgerEntryRow.period)
            .where(
                LedgerEntryRow.enrollment_id == seat, LedgerEntryRow.kind == "charge"
            )
            .order_by(LedgerEntryRow.period)
        )
    )


def test_an_earlier_join_fills_exactly_the_earlier_months(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    """Moving ``joined_on`` back two months creates two cycles, skips three.

    :param restricted_session: The application-role session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param seat: The seat under test
    :return: None
    """
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 3, 1))
    first = generate_due_cycles(restricted_session, today=dt.date(2027, 5, 9))
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 1, 15))
    second = generate_due_cycles(restricted_session, today=dt.date(2027, 5, 9))

    assert (first.cycles_created, first.cycles_skipped) == (3, 0)
    assert (second.cycles_created, second.cycles_skipped) == (2, 3)
    months = ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05"]
    assert _periods(restricted_session, seat) == months
    assert _charges(restricted_session, seat) == months


def test_a_rerun_with_nothing_new_does_not_grow_with_history(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    """Two years of cycles cost a no-op rerun no more than two months do.

    :param restricted_session: The application-role session
    :param owner_session: An arranging session
    :param teacher: The batch's owner
    :param seat: The seat under test
    :return: None
    """
    today = dt.date(2027, 12, 10)

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 11, 1))
    generate_due_cycles(restricted_session, today=today)
    with _counting(restricted_session) as short:
        quiet = generate_due_cycles(restricted_session, today=today)

    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2026, 1, 1))
    generate_due_cycles(restricted_session, today=today)
    with _counting(restricted_session) as long:
        quieter = generate_due_cycles(restricted_session, today=today)

    assert (quiet.cycles_created, quiet.cycles_skipped) == (0, 2)
    assert (quieter.cycles_created, quieter.cycles_skipped) == (0, 24)
    assert not any("INSERT" in statement for statement in long)
    assert len(long) == len(short)
