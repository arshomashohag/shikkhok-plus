"""Step 17 (RED): `inactive_from` semantics, four named tests [AC2.4.1].

**Money-adjacent and fails quietly**, which is why ``team.md``'s
predicate puts it under test-first and why these are four tests rather
than one with four assertions: a single test reports the first failure
and stops, and an implementation can satisfy any three of these and miss
the fourth.

U4 records the date; U7 charges against it. The tests pin the predicate
against this Unit's own function so the semantics exist before the
consumer does -- otherwise U7 would be free to invent them.

The subtle one is the second. Marking a student inactive on the 10th
does **not** prorate that month: the period charges in full unless the
teacher adjusts it [AC2.4.5]. An implementer who "fixes" that to prorate
has written a money bug no test outside this Unit would catch.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.periods import Period, generates_for_period


def test_a_period_beginning_strictly_after_the_date_does_not_generate() -> None:
    """The month after the student left is not charged.

    :return: None
    """
    inactive_from = dt.date(2026, 2, 15)

    assert not generates_for_period(Period(2026, 3), inactive_from=inactive_from)
    assert not generates_for_period(Period(2026, 4), inactive_from=inactive_from)


def test_the_period_containing_the_date_generates_in_full() -> None:
    """The month they left IS charged, and not prorated.

    **This is the one that looks wrong and is right.** Leaving on the
    15th does not halve February's fee; the teacher taught that month
    and adjusts it by hand if they choose to [AC2.4.5].

    :return: None
    """
    assert generates_for_period(Period(2026, 2), inactive_from=dt.date(2026, 2, 15))
    # The boundaries of the containing period, both inclusive.
    assert generates_for_period(Period(2026, 2), inactive_from=dt.date(2026, 2, 1))
    assert generates_for_period(Period(2026, 2), inactive_from=dt.date(2026, 2, 28))


def test_a_period_before_the_date_still_generates() -> None:
    """Existing dues stand; marking inactive is not a retroactive waiver.

    :return: None
    """
    assert generates_for_period(Period(2026, 1), inactive_from=dt.date(2026, 2, 15))


def test_a_null_date_generates_for_every_period() -> None:
    """An active enrollment is the common case and charges normally.

    :return: None
    """
    assert generates_for_period(Period(2026, 3), inactive_from=None)
    assert generates_for_period(Period(2030, 12), inactive_from=None)


def test_the_comparison_is_against_the_period_start_not_the_due_date() -> None:
    """The worked case that separates the two readings [BR4.0].

    ``fee_due_day`` 31 and ``inactive_from`` 2026-02-15. A period is the
    CALENDAR MONTH, so February's period starts on the 1st -- before the
    date -- and generates. Comparing against the clamped **due date**
    instead (28 February) would also generate, so February cannot tell
    the readings apart.

    **March is where they diverge.** March's period starts on the 1st,
    strictly after the 15th, so it must not generate. A due-date
    comparison asks whether 31 March is after the 15th, which it is, and
    charges a student who left six weeks earlier.

    :return: None
    """
    inactive_from = dt.date(2026, 2, 15)

    assert generates_for_period(Period(2026, 2), inactive_from=inactive_from)
    assert not generates_for_period(Period(2026, 3), inactive_from=inactive_from)


def test_a_period_knows_its_own_calendar_boundaries() -> None:
    """A period is the calendar month, 1st to last day [BR4.0].

    ``fee_due_day`` sets only the due date WITHIN a period and never
    moves a boundary. Treating it as the boundary would give every batch
    its own calendar, so two enrollments of one student in different
    batches would sit in different periods and "this month's dues" would
    stop being answerable across batches.

    :return: None
    """
    assert Period(2026, 3).start == dt.date(2026, 3, 1)
    assert Period(2026, 3).end == dt.date(2026, 3, 31)
    # The short month, and the leap year, since the clamp depends on both.
    assert Period(2026, 2).end == dt.date(2026, 2, 28)
    assert Period(2028, 2).end == dt.date(2028, 2, 29)


def test_the_due_date_clamps_to_the_months_last_day() -> None:
    """Day 31 in a short month is the last day, not an error [AC2.1.2].

    :return: None
    """
    assert Period(2026, 2).due_date(31) == dt.date(2026, 2, 28)
    assert Period(2026, 4).due_date(31) == dt.date(2026, 4, 30)
    assert Period(2026, 3).due_date(31) == dt.date(2026, 3, 31)
    assert Period(2026, 3).due_date(10) == dt.date(2026, 3, 10)


def test_an_impossible_due_day_is_refused() -> None:
    """A day outside 1-31 is a programming error, not a clamp.

    The column carries a CHECK constraint, so a value reaching here is a
    bug rather than bad input -- clamping it silently would hide that.

    :return: None
    """
    for day in (0, 32, -1):
        with pytest.raises(ValueError, match="1 and 31"):
            Period(2026, 3).due_date(day)


def test_marking_one_seat_inactive_leaves_the_others_alone(
    restricted_session: Session, owner_session: Session
) -> None:
    """The third property, which the pure function cannot express.

    One student in two of a teacher's batches is two seats [AC2.2.3].
    Leaving one class does not leave the other, so the date is recorded
    per enrollment and a write to one must not touch the other.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.batches.service import set_inactive_from
    from app.db.models import Enrollment
    from tests.batches.conftest import _account, enroll, make_teacher

    physics = make_teacher(owner_session, name="Physics")
    chemistry = make_teacher(owner_session, name="Chemistry")
    student = _account(owner_session)
    leaving = enroll(
        owner_session,
        batch_id=physics.batch_id,
        display_name="Rahim",
        student_account_id=student,
    )
    staying = enroll(
        owner_session,
        batch_id=chemistry.batch_id,
        display_name="Rahim",
        student_account_id=student,
    )

    set_inactive_from(
        restricted_session,
        lens=TeacherLens(account_id=physics.account_id, owner_id=physics.owner_id),
        enrollment_id=leaving,
        inactive_from=dt.date(2026, 2, 15),
    )

    restricted_session.expire_all()
    assert restricted_session.get(Enrollment, leaving).inactive_from == dt.date(
        2026, 2, 15
    )
    assert restricted_session.get(Enrollment, staying).inactive_from is None


def test_clearing_the_date_reactivates_the_seat(
    restricted_session: Session, owner_session: Session
) -> None:
    """A teacher who marked the wrong seat can undo it.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.batches.service import set_inactive_from
    from app.db.models import Enrollment
    from tests.batches.conftest import _account, enroll, make_teacher

    teacher = make_teacher(owner_session)
    student = _account(owner_session)
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
    )

    lens = TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)
    set_inactive_from(
        restricted_session,
        lens=lens,
        enrollment_id=seat,
        inactive_from=dt.date(2026, 2, 15),
    )
    set_inactive_from(
        restricted_session, lens=lens, enrollment_id=seat, inactive_from=None
    )

    restricted_session.expire_all()
    assert restricted_session.get(Enrollment, seat).inactive_from is None
