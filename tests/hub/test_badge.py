"""The "Runs classes on ShikkhokPlus" badge: five accepted seats and recent use."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.hub.listings.badge import runs_classes
from app.local_time import DHAKA
from tests.hub.support import add_attendance, solo_lens

TODAY = dt.date(2026, 11, 14)


def _at(days_ago: int) -> dt.datetime:
    """Return noon UTC ``days_ago`` days before :data:`TODAY`.

    :param days_ago: How many days back
    :return: The timestamp
    """
    day = TODAY - dt.timedelta(days=days_ago)
    return dt.datetime.combine(day, dt.time(12, 0), tzinfo=dt.UTC)


def test_badge_needs_five_accepted_and_recent_attendance(
    owner_session: Session, restricted_session: Session
) -> None:
    """Five accepted seats and attendance five days ago earns the badge.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    add_attendance(owner_session, lens, seats=6, accepted=5, last_recorded=_at(5))

    assert runs_classes(restricted_session, lens.owner_id, TODAY) is True


def test_badge_false_with_four_accepted(
    owner_session: Session, restricted_session: Session
) -> None:
    """Pending seats do not count, however many exist.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    add_attendance(owner_session, lens, seats=9, accepted=4, last_recorded=_at(1))

    assert runs_classes(restricted_session, lens.owner_id, TODAY) is False


def test_badge_false_when_last_attendance_31_days_ago(
    owner_session: Session, restricted_session: Session
) -> None:
    """Stale attendance does not count; thirty days ago still does.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    stale = solo_lens(owner_session)
    add_attendance(owner_session, stale, seats=5, accepted=5, last_recorded=_at(31))
    edge = solo_lens(owner_session)
    add_attendance(owner_session, edge, seats=5, accepted=5, last_recorded=_at(30))

    assert runs_classes(restricted_session, stale.owner_id, TODAY) is False
    assert runs_classes(restricted_session, edge.owner_id, TODAY) is True


def test_badge_false_without_any_attendance(
    owner_session: Session, restricted_session: Session
) -> None:
    """Accepted seats alone are not use.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    add_attendance(owner_session, lens, seats=5, accepted=5, last_recorded=None)

    assert runs_classes(restricted_session, lens.owner_id, TODAY) is False


def test_guardian_only_accepted_seats_earn_the_badge(
    owner_session: Session, restricted_session: Session
) -> None:
    """A seat the guardian accepted counts as accepted.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    add_attendance(owner_session, lens, seats=5, accepted=0, last_recorded=_at(2))
    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET guardian_decision = 'accepted' WHERE batch_id "
            "IN (SELECT id FROM batch WHERE owner_id = :o)"
        ),
        {"o": lens.owner_id},
    )
    owner_session.commit()

    assert runs_classes(restricted_session, lens.owner_id, TODAY) is True


def test_inactive_batch_and_departed_seats_do_not_count(
    owner_session: Session, restricted_session: Session
) -> None:
    """Seats in an inactive batch, or past ``inactive_from``, are not counted.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    add_attendance(owner_session, lens, seats=5, accepted=5, last_recorded=_at(2))
    assert runs_classes(restricted_session, lens.owner_id, TODAY) is True

    owner_session.execute(
        sa.text(
            "UPDATE enrollment SET inactive_from = :d WHERE id = "
            "(SELECT e.id FROM enrollment e JOIN batch b ON b.id = e.batch_id "
            "WHERE b.owner_id = :o LIMIT 1)"
        ),
        {"d": TODAY - dt.timedelta(days=1), "o": lens.owner_id},
    )
    owner_session.commit()
    assert runs_classes(restricted_session, lens.owner_id, TODAY) is False

    owner_session.execute(sa.text("UPDATE enrollment SET inactive_from = NULL"))
    owner_session.execute(
        sa.text("UPDATE batch SET active = false WHERE owner_id = :o"),
        {"o": lens.owner_id},
    )
    owner_session.commit()
    assert runs_classes(restricted_session, lens.owner_id, TODAY) is False


def test_window_starts_at_dhaka_midnight(
    owner_session: Session, restricted_session: Session
) -> None:
    """00:30 Dhaka time on the first day of the window counts.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    first_day = TODAY - dt.timedelta(days=30)
    dhaka_0030 = dt.datetime.combine(first_day, dt.time(0, 30), tzinfo=DHAKA)
    add_attendance(owner_session, lens, seats=5, accepted=5, last_recorded=dhaka_0030)

    assert runs_classes(restricted_session, lens.owner_id, TODAY) is True
