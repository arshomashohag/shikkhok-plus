"""The "Runs classes on ShikkhokPlus" badge: five accepted seats and recent use."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.hub.listings.badge import runs_classes
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
