"""The teacher demand question: "Did the hub bring you a student?" [0042].

The product decides at day 90 whether the public hub is worth continuing,
from what publishing owners answer here. :func:`ask_due` puts the question
at day 60 and day 90 after an owner's FIRST publish, counted in Dhaka
dates; :func:`answer` records the reply, the latest one standing.

**Asked once, by the database.** Each question is an ``INSERT ... ON
CONFLICT DO NOTHING`` against the unique ``(owner_id, day)``, and only the
rows that insert reach anybody's inbox, in the same transaction. Two
overlapping runs therefore ask once and notify once: the second run's
insert waits on the first's row, then finds it and does nothing. An
application-level "already asked?" check would ask twice under exactly
that overlap.

**A missed run heals.** An owner is due while their first publish lies
between ``day`` and ``day + 7`` Dhaka days back, so a job that did not run
for up to a week still asks, late, and the eighth day lets it go rather
than asking a question about a moment long past.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.db.models import HubFeedback, Owner, OwnerListing
from app.errors import ConflictError
from app.hub.listings.shared import managing_accounts
from app.local_time import DHAKA
from app.notifications.inbox import HUB_FEEDBACK_QUESTION, deliver

__all__ = ["ANSWERS", "DAYS", "SELF_HEAL_DAYS", "answer", "ask_due"]

#: The days after the first publish on which the question is asked.
DAYS: Final[tuple[int, ...]] = (60, 90)

#: How many days late a missed run may still ask.
SELF_HEAL_DAYS: Final[int] = 7

#: The three replies; the table's CHECK holds the same words.
ANSWERS: Final[tuple[str, ...]] = ("yes", "not_yet", "not_sure")

_ASK: Final = sa.text(
    "INSERT INTO hub_feedback (id, owner_id, asked_on, day) "
    "SELECT gen_random_uuid(), owner_id, :today, :day FROM owner_listing "
    "WHERE first_published_at >= :start AND first_published_at < :end "
    "ORDER BY owner_id "
    "ON CONFLICT (owner_id, day) DO NOTHING RETURNING owner_id"
)


def _dhaka_midnight(day: dt.date) -> dt.datetime:
    """Return the moment a Dhaka date begins.

    :param day: The Dhaka date
    :return: Its midnight, timezone-aware
    """
    return dt.datetime.combine(day, dt.time(0, 0), tzinfo=DHAKA)


def _ask_one_day(session: Session, day: int, today: dt.date, now: dt.datetime) -> int:
    """Ask every owner now due for one day's question.

    :param session: The session, whose transaction the caller commits
    :param day: ``60`` or ``90``
    :param today: The Dhaka date the job runs for
    :param now: When the messages are sent
    :return: How many owners were newly asked
    """
    oldest = today - dt.timedelta(days=day + SELF_HEAL_DAYS)
    newest = today - dt.timedelta(days=day)
    owner_ids: list[uuid.UUID] = list(
        session.scalars(
            _ASK,
            {
                "today": today,
                "day": day,
                "start": _dhaka_midnight(oldest),
                "end": _dhaka_midnight(newest + dt.timedelta(days=1)),
            },
        )
    )
    for owner_id in owner_ids:
        owner = session.get_one(Owner, owner_id)
        name: str = session.execute(
            sa.select(OwnerListing.public_name).where(OwnerListing.owner_id == owner_id)
        ).scalar_one()
        deliver(
            session,
            account_ids=managing_accounts(session, owner),
            kind=HUB_FEEDBACK_QUESTION,
            batch_name=name,
            now=now,
            source_id=owner_id,
            preview=str(day),
        )
    return len(owner_ids)


def ask_due(session: Session, today: dt.date, *, now: dt.datetime | None = None) -> int:
    """Ask the demand question of every owner due today, in one transaction.

    :param session: The session to work through; committed here
    :param today: The Dhaka date the job runs for
    :param now: When the messages are sent; the real clock by default
    :return: How many ``(owner, day)`` questions were newly asked
    """
    sent_at = now or dt.datetime.now(tz=dt.UTC)
    asked = sum(_ask_one_day(session, day, today, sent_at) for day in DAYS)
    session.commit()
    return asked


def answer(
    session: Session, lens: TeacherLens, day: int, reply: str, now: dt.datetime
) -> None:
    """Record the owner's reply to one day's question; the latest stands.

    :param session: The request's session; committed here
    :param lens: The answering manager's lens on the owner
    :param day: ``60`` or ``90``
    :param reply: ``yes``, ``not_yet`` or ``not_sure``
    :param now: When it was answered
    :raises ConflictError: This owner was never asked that day's question
    """
    updated = session.execute(
        sa.update(HubFeedback)
        .where(HubFeedback.owner_id == lens.owner_id, HubFeedback.day == day)
        .values(answer=reply, answered_at=now, answered_by_account_id=lens.account_id)
        .returning(HubFeedback.id)
    ).scalar_one_or_none()
    if updated is None:
        session.rollback()
        raise ConflictError(
            code="HUB_FEEDBACK_NOT_ASKED", message_key="hub.feedback_not_asked"
        )
    session.commit()
