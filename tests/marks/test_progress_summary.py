"""G2's one-line reading of a child's results, made by the server.

**Written before the function existed.** "Marks went up in each of the
last 4 tests, from 31 to 44 out of 50. Now above the batch average." is
a comparison of results, so the server states it [TC-9]. These are pure:
the summary is a fold over progress entries.
"""

from __future__ import annotations

import datetime as dt
import uuid

from app.marks.summary import summarise
from app.marks.views import ProgressEntry


def _entry(
    marks: int | None, total: int = 50, average: float | None = None
) -> ProgressEntry:
    """Build one progress entry.

    :param marks: The mark, or None for an absence
    :param total: Out of how many
    :param average: The published batch average, if any
    :return: The entry
    """
    return ProgressEntry(
        exam_id=uuid.uuid4(),
        title="Test",
        date=dt.date(2026, 10, 1),
        total_marks=total,
        result_state="marked" if marks is not None else "absent",
        marks=marks,
        batch_average=average,
    )


def test_a_rising_run_is_counted_from_its_start() -> None:
    """31, 35, 39, 44: up in each of the last 4, now above a 36.7 average.

    :return: None
    """
    summary = summarise([_entry(31), _entry(35), _entry(39), _entry(44, average=36.7)])

    assert summary is not None
    assert (
        summary.direction,
        summary.run,
        summary.first_marks,
        summary.last_marks,
    ) == ("up", 4, 31, 44)
    assert (summary.total_marks, summary.above_average) == (50, True)


def test_a_fall_ends_the_run_and_shares_are_compared() -> None:
    """20/25 then 30/50 is down, whatever the raw numbers say.

    :return: None
    """
    summary = summarise([_entry(20, total=25), _entry(30, total=50)])

    assert summary is not None
    assert (summary.direction, summary.run) == ("down", 2)
    assert summary.above_average is None


def test_absences_are_skipped_and_one_result_says_nothing() -> None:
    """An absence is not a zero; a single mark has no direction.

    :return: None
    """
    assert summarise([_entry(40), _entry(None)]) is None
    flat = summarise([_entry(40), _entry(None), _entry(40)])
    assert flat is not None
    assert (flat.direction, flat.run) == ("same", 2)
