"""Bangladesh's clock, for screens that speak of "today".

The server stores and generates in UTC, which is right for records and
wrong for a screen titled "Today": at 1 am in Dhaka it is still yesterday
in UTC. Bangladesh keeps no daylight saving, so a fixed UTC+6 offset is
exact and needs no time zone database in the image.
"""

from __future__ import annotations

import datetime as dt

__all__ = ["DHAKA", "bangladesh_now", "bangladesh_today"]

#: Bangladesh Standard Time. No daylight saving, so a fixed offset.
DHAKA = dt.timezone(dt.timedelta(hours=6), name="Asia/Dhaka")


def bangladesh_now(now: dt.datetime | None = None) -> dt.datetime:
    """Give the present, or a given moment, in Bangladesh time.

    :param now: A moment to convert; the real clock by default
    :return: The moment in Bangladesh time
    """
    return (now or dt.datetime.now(tz=dt.UTC)).astimezone(DHAKA)


def bangladesh_today(now: dt.datetime | None = None) -> dt.date:
    """Give Bangladesh's date, now or at a given moment.

    :param now: A moment; the real clock by default
    :return: That moment's date in Bangladesh
    """
    return bangladesh_now(now).date()
