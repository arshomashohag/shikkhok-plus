"""D5's four figures, probed adversarially with their VALUES asserted.

**A wrong scope on a row query returns a row somebody can point at. A
wrong scope on a sum returns a number that looks right** [NFR14.66,
security-design § 2]. If the owned-seat join lost its ``owner_id``
predicate the dues list would be obviously wrong -- unfamiliar names --
while the earnings total would simply be **a larger number**, and
nothing about it announces that it spans two teachers.

So every probe here asserts the figure's VALUE against data the test
seeded, never merely that a response arrived. Asserting "a 200 with a
number" passes against a figure summed across two teachers.

**Teacher B is seeded so that a leak would CHANGE teacher A's answer**,
and only two of the four figures have a magnitude relation at all:

============ ==========================================================
Figure       The seeding that makes a leak visible
============ ==========================================================
Earnings     **B larger.** If A dominated the sum, A's figure would
             barely move under a leak
Dues         **B has more owing seats.** A length assertion then changes
Trend        **Different periods**, not larger ones -- a leak shows as
             A's series carrying a month A has no data in
Next exam    **B's exam SOONER.** An unscoped ``LIMIT 1`` returns
             *somebody's* soonest exam, so a probe where B's is later
             passes against a leak
============ ==========================================================

**This suite runs as ``APP_ROLE``**, a granted non-owner,
non-superuser, and the built meta-test gates the package before any
probe runs. A probe suite running as superuser reports a **pass**,
which is the worst available outcome [pg-rls].

D5 adds no row-level-security policy -- it creates no table and so no
column naming a reader -- so these lens-scoped probes **are** the
mechanism rather than a second check on one [NFR14.72].
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session as DbSession

from app.analytics.dues import dues_rows
from app.analytics.earnings import period_totals, trend
from app.analytics.seats import ledger_for_seats, owned_seats
from app.analytics.upcoming import next_exam
from app.money import Money
from tests.analytics.conftest import add_exam, lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture, make_teacher

TODAY = dt.date(2027, 9, 10)


def _teacher_a(session: DbSession) -> TeacherFixture:
    """Build the teacher whose figures the probes read.

    :param session: A session able to arrange fixture data
    :return: Teacher A
    """
    return make_teacher(session, name="A: Physics")


def _teacher_b(session: DbSession) -> TeacherFixture:
    """Build the attacker: a real teacher with a lens of their own.

    A VALID lens deliberately. An unauthenticated caller is refused one
    step earlier and proves nothing about this boundary.

    :param session: A session able to arrange fixture data
    :return: Teacher B
    """
    return make_teacher(session, name="B: Chemistry")


def _totals(session: DbSession, teacher: TeacherFixture) -> dict[str, Money]:
    """Fold a teacher's whole ledger into period totals.

    :param session: The session under test
    :param teacher: Whose figures to compute
    :return: Money received per period
    """
    seats = owned_seats(session, lens_for(teacher))
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    return period_totals([entry for rows in ledger.values() for entry in rows])


def test_the_earnings_total_is_a_s_own_and_not_the_sum_of_both(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """A's total is **1000.00**, not 8000.00 and not "a number".

    **B is seeded seven times larger**, deliberately: if A dominated the
    sum, A's figure would barely move under a leak and an approximate
    assertion would still pass.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)
    teacher_b = _teacher_b(owner_session)

    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="A's student",
        entries=[
            ("charge", "2027-09", "1000.00"),
            ("receipt", "2027-09", "1000.00"),
        ],
    )
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_b.batch_id,
        display_name="B's student",
        entries=[
            ("charge", "2027-09", "7000.00"),
            ("receipt", "2027-09", "7000.00"),
        ],
    )

    total = Money.sum(_totals(restricted_session, teacher_a).values())

    assert total == Money("1000.00"), (
        f"teacher A's earnings read {total}. 8000.00 means the seat set "
        "spans both teachers [BR2.5, NFR14.66] -- and a wrong scope on a "
        "sum returns a number that looks right, which is why this "
        "asserts the value rather than that a figure came back."
    )


def test_a_s_dues_list_holds_only_a_s_seat(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """A's list has **length 1** and names A's own seat.

    **B has three owing seats to A's one**, so a leak changes the
    length rather than only the contents -- a membership assertion alone
    would pass against a list that contained A's seat and three others.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)
    teacher_b = _teacher_b(owner_session)

    mine = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="A's debtor",
        entries=[("charge", "2027-09", "500.00")],
    )
    for index in range(3):
        seat_with_ledger(
            owner_session,
            restricted_session,
            batch_id=teacher_b.batch_id,
            display_name=f"B's debtor {index}",
            entries=[("charge", "2027-09", "900.00")],
        )

    seats = owned_seats(restricted_session, lens_for(teacher_a))
    ledger = ledger_for_seats(
        restricted_session, [seat.enrollment_id for seat in seats]
    )
    rows = dues_rows(seats, ledger)

    assert len(rows) == 1, (
        f"teacher A's dues view holds {len(rows)} rows, not 1: B's three "
        "owing seats have leaked into A's list [BR2.5]."
    )
    assert rows[0].enrollment_id == mine
    assert rows[0].display_name == "A's debtor"


def test_a_s_trend_covers_only_the_months_a_has_data_in(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """A's series is A's two months, not B's two.

    **Different periods rather than larger ones**, because the trend has
    no magnitude relation to exploit: a leak shows as A's series
    carrying a month A has no data in at all.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)
    teacher_b = _teacher_b(owner_session)

    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="A's student",
        entries=[
            ("charge", "2027-01", "400.00"),
            ("receipt", "2027-01", "400.00"),
            ("charge", "2027-02", "400.00"),
            ("receipt", "2027-02", "400.00"),
        ],
    )
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_b.batch_id,
        display_name="B's student",
        entries=[
            ("charge", "2027-07", "400.00"),
            ("receipt", "2027-07", "400.00"),
            ("charge", "2027-08", "400.00"),
            ("receipt", "2027-08", "400.00"),
        ],
    )

    series = trend(_totals(restricted_session, teacher_a))

    assert series is not None
    assert [point.period for point in series] == ["2027-01", "2027-02"], (
        "teacher A's trend carries a month A has no data in, which is "
        "what a leak looks like on a figure with no magnitude relation "
        "[BR2.5]."
    )


def test_a_sees_a_s_own_next_exam_even_though_b_s_is_sooner(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """**B's exam is sooner**, which is the whole point of this probe.

    An unscoped ``LIMIT 1`` returns *somebody's* soonest exam. A probe
    where B's exam were later would pass against a leak, because the
    correct answer and the leaked one would both be A's -- and a probe
    asserting only "an exam came back" passes against everything.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)
    teacher_b = _teacher_b(owner_session)

    add_exam(
        owner_session,
        batch_id=teacher_b.batch_id,
        title="B's exam, SOONER",
        date=TODAY + dt.timedelta(days=2),
        subject_name="Chemistry",
    )
    add_exam(
        owner_session,
        batch_id=teacher_a.batch_id,
        title="A's exam, later",
        date=TODAY + dt.timedelta(days=9),
        subject_name="Physics",
    )

    found = next_exam(restricted_session, lens_for(teacher_a), today=TODAY)

    assert found is not None
    assert found.title == "A's exam, later", (
        f"teacher A was shown '{found.title}'. An unscoped LIMIT 1 "
        "returns somebody's soonest exam, and B's is sooner here "
        "precisely so that leak changes the answer [BR2.5, BR3.1]."
    )
    assert found.days_remaining == 9


def test_a_declined_owing_seat_is_absent_from_a_s_own_list(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """The declined clause, probed with a seat that **owes** [BR1.7].

    A probe using pending and accepted seats cannot distinguish a
    correct implementation from one missing the clause, and a declined
    seat owing nothing is absent under BR1.3 anyway.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)

    declined = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="Declined, owing",
        entries=[("charge", "2027-09", "1300.00")],
        student_decision="declined",
    )
    kept = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="Accepted, owing",
        entries=[("charge", "2027-09", "100.00")],
    )

    seats = owned_seats(restricted_session, lens_for(teacher_a))
    ledger = ledger_for_seats(
        restricted_session, [seat.enrollment_id for seat in seats]
    )
    present = {row.enrollment_id for row in dues_rows(seats, ledger)}

    assert declined not in present
    assert kept in present, (
        "the positive half: without it this probe passes against a "
        "boundary that denies unconditionally, which is the opposite "
        "of the requirement."
    )


def test_a_teacher_reads_their_own_figures_at_all(
    owner_session: DbSession,
    restricted_session: DbSession,
) -> None:
    """The positive twin of every probe above.

    Without it the whole suite passes against an implementation that
    returns nothing to anybody, which is not the requirement -- it is
    the opposite of one.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :return: None
    """
    teacher_a = _teacher_a(owner_session)

    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher_a.batch_id,
        display_name="A's student",
        entries=[
            ("charge", "2027-09", "650.00"),
            ("receipt", "2027-09", "650.00"),
        ],
    )

    totals = _totals(restricted_session, teacher_a)

    assert totals.get("2027-09") == Money("650.00")
