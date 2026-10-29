"""G2's one-line reading of a child's results.

"Marks went up in each of the last 4 tests, from 31 to 44 out of 50. Now
above the batch average." compares results, so it is made here and the
phone renders it [TC-9].

**Marks are compared as shares of their totals**, so a 25-mark test and
a 50-mark test compare fairly. **An absence is skipped, never a zero**
[BR6.6]: a missed test is not a collapse. The run is the latest stretch
moving one way, counted in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.marks.views import ProgressEntry

__all__ = ["ProgressSummary", "summarise"]

#: Which way the latest run went.
Direction = Literal["up", "down", "same"]


@dataclass(frozen=True, slots=True)
class ProgressSummary:
    """The latest run of results.

    :ivar direction: Which way it went
    :ivar run: How many tests it spans, at least two
    :ivar first_marks: The run's first mark
    :ivar last_marks: Its last mark
    :ivar total_marks: The last test's total
    :ivar above_average: Whether the last mark beats the published batch
        average; None where none was published
    """

    direction: Direction
    run: int
    first_marks: int
    last_marks: int
    total_marks: int
    above_average: bool | None


def summarise(entries: list[ProgressEntry]) -> ProgressSummary | None:
    """Read the latest run from a seat's results, oldest first.

    :param entries: The seat's results, oldest first
    :return: The run, or None with fewer than two marked results
    """
    marked = [(entry, entry.marks) for entry in entries if entry.marks is not None]
    if len(marked) < 2:
        return None

    def step(index: int) -> Direction:
        (before, then), (after, now) = marked[index - 1], marked[index]
        lhs, rhs = now * before.total_marks, then * after.total_marks
        return "up" if lhs > rhs else "down" if lhs < rhs else "same"

    last_step = len(marked) - 1
    direction = step(last_step)
    start = last_step
    while start > 1 and step(start - 1) == direction:
        start -= 1
    first_marks = marked[start - 1][1]
    last_entry, last_marks = marked[-1]
    average = last_entry.batch_average
    return ProgressSummary(
        direction=direction,
        run=last_step - start + 2,
        first_marks=first_marks,
        last_marks=last_marks,
        total_marks=last_entry.total_marks,
        above_average=None if average is None else last_marks > average,
    )
