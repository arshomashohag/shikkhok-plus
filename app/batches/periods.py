"""Fee periods, and what `inactive_from` does to them.

**U4 records the anchor; U7 charges against it.** The semantics live here
rather than with the consumer because they are the subtlest thing in this
Unit and because leaving them to U7 would mean inventing them twice.

A period is a **calendar month** [BR4.0]. It starts on the 1st and ends
on the last day of that month. ``fee_due_day`` sets only the due date
*within* a period and never moves a boundary -- treating it as the
boundary would give every batch its own calendar, so two enrollments of
one student in different batches would sit in different periods and
"this month's dues" would stop being answerable across batches.

``inactive_from`` has three separate properties and an implementation can
satisfy any two:

* no cycle for a period beginning **strictly after** the date;
* the period **containing** the date still generates **in full**;
* other enrollments of the same student are unaffected.

The second is the one that looks wrong. Marking a student inactive on
the 10th does not prorate that month: the teacher taught it, and adjusts
it by hand if they choose to [AC2.4.5]. An implementer who "fixes" this
to prorate has written a money bug.

This module holds no money and does no arithmetic on amounts, so it is
calendar logic rather than ledger logic and does not belong in
``app.money``.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

__all__ = ["Period", "generates_for_period"]

#: The inclusive bounds a day-of-month may take. 29, 30 and 31 are legal
#: and clamp to the month's last day [AC2.1.2]; the column carries a
#: CHECK constraint, so a value outside this range is a bug rather than
#: bad input.
MIN_DUE_DAY = 1
MAX_DUE_DAY = 31


@dataclass(frozen=True, slots=True, order=True)
class Period:
    """One calendar month, the unit a fee cycle is generated for.

    Ordered so periods compare and sort naturally, which is what lets
    "strictly after" be expressed as a comparison rather than as
    arithmetic on month numbers.

    :ivar year: The calendar year
    :ivar month: The calendar month, 1-12
    """

    year: int
    month: int

    @property
    def start(self) -> dt.date:
        """The first day of the period.

        :return: The 1st of the month
        """
        return dt.date(self.year, self.month, 1)

    @property
    def end(self) -> dt.date:
        """The last day of the period.

        :return: The month's final day, accounting for leap years
        """
        return dt.date(
            self.year, self.month, calendar.monthrange(self.year, self.month)[1]
        )

    def contains(self, day: dt.date) -> bool:
        """Report whether a date falls inside this period.

        :param day: The date to test
        :return: True if the date is within this calendar month
        """
        return self.start <= day <= self.end

    def due_date(self, fee_due_day: int) -> dt.date:
        """Resolve the due date within this period, clamping short months.

        :param fee_due_day: The batch's day of month, 1-31
        :return: That day, or the month's last day when it is shorter
        :raises ValueError: The day is outside 1-31
        """
        if not MIN_DUE_DAY <= fee_due_day <= MAX_DUE_DAY:
            raise ValueError(f"fee_due_day must be between 1 and 31, got {fee_due_day}")
        last_day = calendar.monthrange(self.year, self.month)[1]
        return dt.date(self.year, self.month, min(fee_due_day, last_day))


def generates_for_period(period: Period, *, inactive_from: dt.date | None) -> bool:
    """Report whether a fee cycle generates for this period.

    **The comparison is against the period's START, never its due date**
    [BR4.0]. Worked: ``fee_due_day`` 31 and ``inactive_from`` 2026-02-15.
    February's period starts on the 1st, before the date, so it
    generates -- and a due-date comparison agrees, which is why February
    cannot tell the two readings apart. March is where they diverge:
    March starts on the 1st, strictly after the 15th, so it must not
    generate, while comparing against 31 March would charge a student
    who left six weeks earlier.

    :param period: The period a cycle would be generated for
    :param inactive_from: The date the enrollment went inactive, or None
    :return: True if a cycle should generate
    """
    if inactive_from is None:
        return True
    # Strictly after: the period CONTAINING the date still generates, in
    # full and unprorated [AC2.4.5].
    return period.start <= inactive_from
