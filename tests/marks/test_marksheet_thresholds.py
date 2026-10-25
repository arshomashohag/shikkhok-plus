"""The two suppression conditions, one test each [§ 4.3, BR6.4].

**A test per condition, each holding the other satisfied.** A single
test varying both at once passes while only one check is implemented,
which is the defect shape rather than a stylistic preference.

The two conditions are independent:

* below five marked results, a rank plus a band identifies people
  directly;
* while any seat is still ``not_entered``, a rank that drifts from 2nd
  to 7th as marks arrive reads as the app changing the student's
  result.
"""

from __future__ import annotations

import uuid

from app.marks.marksheet import Published, Suppressed, compute_marksheet
from app.marks.results import SeatResult

TOTAL = 100


def _seat(marks: int | None, state: str = "marked") -> SeatResult:
    """Build one seat result.

    :param marks: The mark, or None
    :param state: The result state
    :return: The seat result
    """
    return SeatResult(
        enrollment_id=uuid.uuid4(),
        display_name="Student",
        result_state=state,
        marks=marks,
    )


def test_four_marked_with_marking_complete_suppresses() -> None:
    # Condition one alone. Marking IS complete -- no seat is
    # not_entered -- so only the count can be what suppresses.
    seats = [_seat(value) for value in (80, 70, 60, 50)]

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Suppressed)
    assert sheet.reason == "too_few_results"
    assert sheet.viewer_marks == 80


def test_eight_marked_with_one_not_entered_suppresses() -> None:
    # Condition two alone. Eight marked results is comfortably ABOVE
    # the five-result floor, so only the incompleteness can be what
    # suppresses.
    seats = [_seat(value) for value in (90, 85, 80, 75, 70, 65, 60, 55)]
    seats.append(_seat(None, state="not_entered"))

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Suppressed)
    assert sheet.reason == "marking_incomplete"


def test_five_marked_and_complete_publishes() -> None:
    # The positive case, which is what stops the suite passing against
    # an implementation that suppresses unconditionally.
    seats = [_seat(value) for value in (90, 80, 70, 60, 50)]

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sheet.marked_count == 5


def test_absences_do_not_count_toward_the_five() -> None:
    # Four marked plus two absent is still four MARKED results. An
    # implementation counting rows rather than marked results would
    # publish a comparison over four numbers.
    seats = [_seat(value) for value in (80, 70, 60, 50)]
    seats += [_seat(None, state="absent"), _seat(None, state="absent")]

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Suppressed)
    assert sheet.reason == "too_few_results"


def test_absences_do_not_make_marking_incomplete() -> None:
    # An absence is a RECORDED result; the teacher is finished with
    # that seat. Treating it as incomplete would suppress the
    # marksheet of every batch where anyone missed the exam.
    seats = [_seat(value) for value in (90, 85, 80, 75, 70)]
    seats.append(_seat(None, state="absent"))

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
