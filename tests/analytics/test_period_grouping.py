"""An entry belongs to the month its ``period`` names [BR2.6].

**These are database tests and the others in this package are not**, and
the reason is the whole point: ``created_at`` exists on the **row** and
not on the value shape the fold takes. A pure-fold test cannot express
the defect at all, because ``LedgerEntry`` carries no creation stamp --
so grouping by ``created_at`` is only reachable, and only catchable,
through a real read.

§ 3.3 of the unit test instructions names two fixtures and both are
here:

* **a late-recorded payment** -- period October, ``created_at``
  November. This is the normal case rather than an edge: a teacher
  verifies October's cash in early November;
* **a ``carry_forward``**, whose ``created_at`` is whenever generation
  ran. This one fails against the defect **even when no payment is
  late**, which is why it is not redundant with the first.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.earnings import period_totals
from app.analytics.seats import ledger_for_seats, owned_seats
from app.db.models import LedgerEntryRow
from app.money import Money
from tests.analytics.conftest import lens_for, seat_with_ledger
from tests.batches.conftest import TeacherFixture


def _restamp(
    session: Session, enrollment_id: object, kind: str, when: dt.datetime
) -> None:
    """Move an entry's ``created_at`` without touching its period.

    The only way to build the fixture: ``append_entry`` stamps the
    current time, and the defect under test is precisely a read that
    prefers that stamp over the period the entry names.

    :param session: An arranging session
    :param enrollment_id: The seat
    :param kind: Which kind of entry to restamp
    :param when: The creation stamp to write
    :return: None
    """
    session.execute(
        sa.update(LedgerEntryRow)
        .where(
            LedgerEntryRow.enrollment_id == enrollment_id,
            LedgerEntryRow.kind == kind,
        )
        .values(created_at=when)
    )
    session.commit()


def _totals(session: Session, teacher: TeacherFixture) -> dict[str, Money]:
    """Fold every entry on this teacher's seats into period totals.

    :param session: The session under test
    :param teacher: The teacher whose seats to read
    :return: Money received per period
    """
    seats = owned_seats(session, lens_for(teacher))
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    entries = [entry for rows in ledger.values() for entry in rows]
    return period_totals(entries)


def test_a_payment_recorded_in_november_counts_in_its_october_period(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Period October, created November, counted in October [BR2.6].

    **The likeliest wrong number in the unit.** Grouping by
    ``created_at`` understates October, overstates November, and
    produces a trend showing a dip and a spike that never happened.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Paid late",
        entries=[
            ("charge", "2026-10", "1000.00"),
            ("receipt", "2026-10", "1000.00"),
        ],
    )
    _restamp(
        owner_session,
        seat,
        "receipt",
        dt.datetime(2026, 11, 2, 9, 30, tzinfo=dt.UTC),
    )

    totals = _totals(restricted_session, teacher)

    assert totals.get("2026-10") == Money("1000.00"), (
        f"October read {totals.get('2026-10')}, not 1000.00. The fold is "
        "grouping by created_at, so a payment verified on 2 November "
        "moved out of the month it was for [BR2.6]."
    )
    assert "2026-11" not in totals, (
        f"November carries {totals.get('2026-11')} from an entry whose "
        "period is 2026-10."
    )


def test_a_carry_forward_counts_in_the_period_it_lands_on(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A carry fails against the defect with no late payment at all.

    A ``carry_forward`` lands on the **receiving** period while its
    ``created_at`` is whenever generation ran, so ``created_at``
    grouping scatters carries into arbitrary months.

    A carry is not money received, so the assertion is on where the
    **receipt that settles it** counts: the carry gives the receiving
    period an obligation stamped in a different month, and a receipt
    against that period must still count there.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat = seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Carried over",
        entries=[
            ("charge", "2026-09", "1000.00"),
            ("carried_out", "2026-09", "1000.00"),
            ("carry_forward", "2026-10", "1000.00"),
            ("receipt", "2026-10", "1000.00"),
        ],
    )
    # Generation ran in September; the money arrived against October.
    _restamp(
        owner_session,
        seat,
        "carry_forward",
        dt.datetime(2026, 9, 1, 0, 5, tzinfo=dt.UTC),
    )
    _restamp(
        owner_session,
        seat,
        "receipt",
        dt.datetime(2026, 9, 1, 0, 5, tzinfo=dt.UTC),
    )

    totals = _totals(restricted_session, teacher)

    assert totals.get("2026-10") == Money("1000.00"), (
        f"October read {totals.get('2026-10')}. The entry's period is "
        "2026-10 and its created_at is in September, so a fold grouping "
        "by created_at puts this money in the wrong month [BR2.6]."
    )
    assert "2026-09" not in totals


def test_a_carry_forward_is_not_itself_money_received(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The carry is an accounting move, not cash [BR2.1].

    Asserted separately from the grouping, because a fold that counted
    carries would pass the grouping test above by arriving at the right
    month for the wrong reason.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    seat_with_ledger(
        owner_session,
        restricted_session,
        batch_id=teacher.batch_id,
        display_name="Carried, unpaid",
        entries=[
            ("charge", "2026-09", "1000.00"),
            ("carried_out", "2026-09", "1000.00"),
            ("carry_forward", "2026-10", "1000.00"),
        ],
    )

    totals = _totals(restricted_session, teacher)

    assert totals.get("2026-10", Money.ZERO) == Money.ZERO
