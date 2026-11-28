"""How often an owner's public pages were viewed [0050], for the owner only.

The counts are one number per page per Bangladesh day, written by the
public pages' counting image (``app/api/hub_public.py``). They say nothing
about who viewed a page, and nobody but the people who manage the listing
reads them: no public page, search order or ranking uses them.

**A count of loads, not of people.** One person opening a page twice counts
twice, and a reader whose browser blocks images counts nothing. The owner's
screen says so in words; the numbers are a trend, not an audience.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens

__all__ = ["RECENT_DAYS", "WINDOW_DAYS", "PageViews", "Views", "for_owner"]

#: The short window: this week, today included.
RECENT_DAYS: Final[int] = 7

#: The long window, and the furthest back a count is read.
WINDOW_DAYS: Final[int] = 30

_COUNTS = sa.text(
    """
    SELECT v.page_kind::text AS kind,
           v.page_id,
           COALESCE(sum(v.views) FILTER (WHERE v.day >= :recent_from), 0)
               AS recent,
           sum(v.views) AS window
    FROM hub_page_view v
    WHERE v.day >= :window_from
      AND (
          (v.page_kind = 'owner' AND v.page_id = :owner)
          OR (
              v.page_kind = 'batch'
              AND v.page_id IN (SELECT b.id FROM batch b WHERE b.owner_id = :owner)
          )
      )
    GROUP BY v.page_kind, v.page_id
    """
)


@dataclass(frozen=True, slots=True)
class Views:
    """One page's views in the two windows.

    :ivar last_7_days: Views in the last seven days, today included
    :ivar last_30_days: Views in the last thirty days, today included
    """

    last_7_days: int
    last_30_days: int


#: A page nobody has viewed in the window.
_NONE: Final[Views] = Views(last_7_days=0, last_30_days=0)


@dataclass(frozen=True, slots=True)
class PageViews:
    """The owner's page and each of the owner's batch pages.

    :ivar owner: The owner page's views
    :ivar batches: Each batch page's views, by batch id; a batch with no
        views in the window is absent
    """

    owner: Views
    batches: dict[uuid.UUID, Views]


def for_owner(session: Session, lens: TeacherLens, today: dt.date) -> PageViews:
    """Read the owner's page views in the two windows.

    :param session: The session, as the application role
    :param lens: The owner's lens; only this owner's pages are read
    :param today: Today in Bangladesh, the last day of both windows
    :return: The owner's page views
    """
    rows = session.execute(
        _COUNTS,
        {
            "owner": lens.owner_id,
            "recent_from": today - dt.timedelta(days=RECENT_DAYS - 1),
            "window_from": today - dt.timedelta(days=WINDOW_DAYS - 1),
        },
    ).all()
    owner = _NONE
    batches: dict[uuid.UUID, Views] = {}
    for row in rows:
        views = Views(last_7_days=int(row.recent), last_30_days=int(row.window))
        if row.kind == "owner":
            owner = views
        else:
            batches[row.page_id] = views
    return PageViews(owner=owner, batches=batches)
