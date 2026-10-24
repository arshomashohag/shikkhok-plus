"""The calendar: what a period is, and when a cycle falls due.

**This is the knowledge `app.money` refuses to hold** [BR2.1]. A period
is an opaque string there, with no calendar arithmetic at all, precisely
so that the fold stays pure and this unit owns months, anchors and the
clamp.

**The clamp does not degrade the stored anchor** [BR2.2], and that is a
design choice rather than an implied one. The due date is a pure function
of the stored anchor and the period: no hidden write, no order
dependence, and a re-run of the self-healing job cannot change an answer
it already gave. A degrading clamp -- one that rewrites
``Batch.fee_due_day`` to 28 after a February -- would make BR1.4's daily
job non-idempotent across days, contradicting a rule in the same unit,
and one short month would silently move every future due date for that
batch for ever.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Self

__all__ = [
    "PERIOD_PATTERN",
    "Period",
    "days_in_period",
    "due_date_for",
    "periods_from_through",
]

#: The canonical period key. Fixed width, so lexical order IS
#: chronological order -- which is what lets the oldest unpaid cycle be
#: resolved by sorting keys [BR5.1]. A single-digit month would sort
#: "2027-9" after "2027-10".
PERIOD_PATTERN: Final = re.compile(r"^([0-9]{4})-(0[1-9]|1[0-2])$")

#: The highest day-of-month any anchor may name. Beyond this the clamp
#: has nothing left to clamp to.
_MAX_ANCHOR_DAY: Final = 31


@dataclass(frozen=True, slots=True, order=True)
class Period:
    """One calendar month, the unit a fee cycle is charged for.

    Ordered, so a list of periods sorts chronologically without anyone
    sorting their string keys by hand.

    :ivar year: The four-digit year
    :ivar month: The month, 1 through 12
    """

    year: int
    month: int

    def __post_init__(self) -> None:
        """Refuse a month outside the calendar.

        :raises ValueError: If the month is not between 1 and 12.
        """
        if not 1 <= self.month <= 12:
            raise ValueError(
                f"{self.month} is not a calendar month; a period is one "
                "month of one year."
            )

    @classmethod
    def parse(cls, key: str) -> Self:
        """Read a period from its canonical ``YYYY-MM`` key.

        :param key: The stored key.
        :return: The period it names.
        :raises ValueError: If the key is not in canonical form.
        """
        match = PERIOD_PATTERN.match(key)
        if match is None:
            raise ValueError(
                f"{key!r} is not a period key. The canonical form is "
                "YYYY-MM, fixed width, so that lexical order is "
                "chronological order."
            )
        return cls(year=int(match.group(1)), month=int(match.group(2)))

    @classmethod
    def containing(cls, day: dt.date) -> Self:
        """Return the period a date falls in.

        :param day: The date.
        :return: The period containing it.
        """
        return cls(year=day.year, month=day.month)

    def first_day(self) -> dt.date:
        """Return the period's first day.

        This is the comparand ``inactive_from`` is tested against
        [BR1.5]: a seat generates for the period CONTAINING the date, so
        the test is whether the date falls on or after this day.

        :return: The first day of the month.
        """
        return dt.date(self.year, self.month, 1)

    def last_day(self) -> dt.date:
        """Return the period's last day.

        :return: The last day of the month.
        """
        return dt.date(self.year, self.month, days_in_period(self))

    def next(self) -> Period:
        """Return the following period.

        :return: The next calendar month.
        """
        if self.month == 12:
            return Period(year=self.year + 1, month=1)
        return Period(year=self.year, month=self.month + 1)

    def __str__(self) -> str:
        """Render the canonical key.

        :return: The period as ``YYYY-MM``.
        """
        return f"{self.year:04d}-{self.month:02d}"


def days_in_period(period: Period) -> int:
    """Return how many days the period's month has.

    :param period: The period.
    :return: The day count, leap years included.
    """
    return calendar.monthrange(period.year, period.month)[1]


def due_date_for(period: Period, *, anchor_day: int | None) -> dt.date:
    """Compute a cycle's due date, clamping without degrading [BR2.2].

    A NULL anchor means the last day of the period [BR2.3]. That is an
    assumption flagged for the human rather than an upstream fact: the
    column is nullable and nothing says what a null means. Last-day is
    chosen because it is the only default that cannot make a fee due
    before the month it pays for has been taught, and because it
    degrades to the same behaviour as an anchor of 31.

    :param period: The period being generated.
    :param anchor_day: The batch's stored anchor day, or None.
    :return: The day ``min(anchor, days_in_month)`` of that period.
    :raises ValueError: If the anchor is outside 1 through 31. The
        column is validated ``ge=1, le=31`` at the schema, so reaching
        here with another value means a row bypassed that path.
    """
    last = days_in_period(period)
    if anchor_day is None:
        return dt.date(period.year, period.month, last)
    if not 1 <= anchor_day <= _MAX_ANCHOR_DAY:
        raise ValueError(
            f"{anchor_day} is not a day of the month. The anchor is "
            "validated 1-31 at the schema; a value outside that range "
            "means a row reached the database by another path."
        )
    return dt.date(period.year, period.month, min(anchor_day, last))


def periods_from_through(first: Period, last: Period) -> Iterator[Period]:
    """Yield every period from `first` through `last`, inclusive.

    **Inclusive at both ends, and that is what makes a missed day
    self-heal** [BR1.4]. Generation considers every period from the
    enrollment's first generating one through the current one and
    inserts only those with no existing cycle, so a hole left by a
    missed run is filled by the next one rather than being permanent.

    An empty range is a real case rather than an error: an enrollment
    whose first generating period is next month is considered by a run
    today and yields nothing.

    :param first: The earliest period to consider.
    :param last: The latest period to consider.
    :return: The periods in chronological order, possibly none.
    """
    current = first
    while current <= last:
        yield current
        current = current.next()
