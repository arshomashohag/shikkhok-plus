"""Self-healing across days [BR1.4, AC5.1.3].

**This is a different test from the concurrency one, and it is the
forgettable one.** Racing threads cannot reach a re-run on a LATER day:
they all carry the same clock. The failure this file covers is a missed
day that leaves a permanent hole, or a re-run that double-charges every
prior month -- neither of which a barrier can produce.

Team memory records this obligation as "lands in D3 and has not been
exercised yet, because fee cycles are not built". This is where it
lands.

**Time is injected, not patched.** The job takes ``today`` as a
parameter, so a test simply passes a different day. A patched module
global would be wider than the test and invisible at the call site, and
the across-days property is precisely about the job being called again
with a new date.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.generation import generate_due_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture
from tests.fees.conftest import set_joined_on


def _state(session: Session, enrollment_id: uuid.UUID) -> tuple[list[str], Money, int]:
    """Describe a seat's cycles and ledger in one comparable value.

    :param session: The session to read through
    :param enrollment_id: The seat
    :return: The periods, the charged total and the entry count
    """
    periods = [
        row[0]
        for row in session.execute(
            sa.text(
                "SELECT period FROM fee_cycle WHERE enrollment_id = :id ORDER BY period"
            ),
            {"id": enrollment_id},
        )
    ]
    charged = Money(
        session.execute(
            sa.text(
                "SELECT coalesce(sum(amount), 0) FROM ledger_entry "
                "WHERE enrollment_id = :id AND kind = 'charge'"
            ),
            {"id": enrollment_id},
        ).scalar_one()
    )
    entries = session.execute(
        sa.text("SELECT count(*) FROM ledger_entry WHERE enrollment_id = :id"),
        {"id": enrollment_id},
    ).scalar_one()
    return periods, charged, entries


def test_a_missed_day_is_caught_up_by_the_next_run(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The job never ran in December or January. February's run must
    # fill both holes rather than charging only the current month --
    # a hole nothing ever fills is the failure the inclusive period
    # range exists to prevent.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2026, 12, 1))

    generate_due_cycles(restricted_session, today=dt.date(2027, 2, 20))

    periods, charged, _ = _state(restricted_session, seat)
    assert periods == ["2026-12", "2027-01", "2027-02"]
    assert charged == Money("4500.00")


def test_a_later_rerun_on_a_new_day_appends_nothing(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # Day N, then day N+1, then day N+1 again. The row set and the
    # ledger total must be IDENTICAL after runs two and three -- which
    # is the assertion AC5.1.3 names and the one a concurrency test
    # cannot make.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=dt.date(2027, 2, 20))
    after_first = _state(restricted_session, seat)

    generate_due_cycles(restricted_session, today=dt.date(2027, 2, 21))
    after_second = _state(restricted_session, seat)

    generate_due_cycles(restricted_session, today=dt.date(2027, 2, 21))
    after_third = _state(restricted_session, seat)

    assert after_second == after_first
    assert after_third == after_second
    assert after_third == (["2027-02"], Money("1500.00"), 1)


def test_crossing_a_month_boundary_adds_exactly_one_period(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The run on 1 March must add March and leave February untouched.
    # A job that recomputed from scratch each day, or that re-charged
    # the periods it already knew, fails here and nowhere else.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    generate_due_cycles(restricted_session, today=dt.date(2027, 2, 28))
    february = _state(restricted_session, seat)
    assert february == (["2027-02"], Money("1500.00"), 1)

    generate_due_cycles(restricted_session, today=dt.date(2027, 3, 1))

    periods, charged, entries = _state(restricted_session, seat)
    assert periods == ["2027-02", "2027-03"]
    assert charged == Money("3000.00")
    assert entries == 2


def test_running_many_times_across_many_days_is_a_fixed_point(
    restricted_session: Session,
    owner_session: Session,
    teacher: TeacherFixture,
    seat: uuid.UUID,
) -> None:
    # The daily job is safe to run any number of times on any number of
    # days [BR1.4]. Twenty runs across February must leave exactly one
    # period's charge.
    set_joined_on(owner_session, enrollment_id=seat, when=dt.date(2027, 2, 1))

    for day in range(1, 21):
        generate_due_cycles(restricted_session, today=dt.date(2027, 2, day))

    assert _state(restricted_session, seat) == (
        ["2027-02"],
        Money("1500.00"),
        1,
    )
