"""The anonymised marksheet: bands, thresholds, aggregates [BR6.2-BR6.5].

**A band of one IS a named mark**, with the name supplied by anyone who
knows who is in the batch. In a batch of 8 to 20 students who sit
together and compare marks, twelve unattributed numbers are
deanonymised by inference within a day -- so this is a disclosure
mechanism and not a presentation nicety.

**The merge REPEATS**, and that is the part an implementation drops:
one merge pass can produce a neighbour that is itself still under
three. The property test is what catches the single-pass bug; the two
worked cases are the regressions that name it.

**The band counts must SUM to the number of marked results**, and this
assertion is stronger than checking the top edge. Generating width-20
bands the obvious way -- ``range(0, 100, 20)`` giving
``[(0,19),(20,39),(40,59),(60,79),(80,99)]`` -- leaves a full 100
falling through every band while still counting in the average, the
rank and the five-result threshold. A count-based test passes, because
the missing student is simply ABSENT rather than miscounted. The
design writes the top band as ``80-100``.
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.marks.marksheet import (
    BAND_WIDTH,
    MINIMUM_BAND_SIZE,
    MINIMUM_MARKED_RESULTS,
    Published,
    compute_marksheet,
)
from app.marks.results import SeatResult

#: The denominator every case here uses.
TOTAL = 100


def _marked(count: int, values: list[int]) -> list[SeatResult]:
    """Build `count` seat results carrying the given marks.

    :param count: How many seats
    :param values: The marks, one per seat
    :return: The seat results
    """
    return [
        SeatResult(
            enrollment_id=uuid.uuid4(),
            display_name=f"Student {index:02d}",
            result_state="marked",
            marks=value,
        )
        for index, value in enumerate(values[:count])
    ]


# ---------------------------------------------------------------------
# The two worked cases, computed upstream rather than asserted.
# ---------------------------------------------------------------------


def test_the_nine_mark_worked_case_publishes_three_bands_of_three() -> None:
    # BR6.3's own computed example: nine marked results out of 100,
    # [92, 88, 81, 74, 71, 68, 55, 41, 12], five fixed bands of width
    # 20. Raw counts high to low are 3, 3, 2, 0, 1; walking downward
    # and merging any band under three collapses the bottom three into
    # one 0-59 band holding 3.
    values = [92, 88, 81, 74, 71, 68, 55, 41, 12]
    seats = _marked(9, values)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[3])

    assert isinstance(sheet, Published)
    assert [(band.low, band.high, band.count) for band in sheet.bands] == [
        (0, 59, 3),
        (60, 79, 3),
        (80, 100, 3),
    ]
    # The same data's other aggregates, computed upstream.
    assert sheet.average == pytest.approx(64.67, abs=0.01)
    assert sheet.highest == 92
    assert sheet.viewer_marks == 74
    assert sheet.viewer_rank == 4
    assert sheet.marked_count == 9


def test_the_eight_mark_worked_case_collapses_to_one_band() -> None:
    # security-design § 4.2's computed case, which is the one that
    # proves the merge REPEATS: raw [0-20]:1 [21-40]:1 [41-60]:4
    # [61-80]:1 [81-100]:1, and after four passes a single band of 8.
    # The terminal case discloses nothing beyond the count, which the
    # five-result threshold already discloses.
    values = [10, 30, 45, 50, 55, 58, 70, 90]
    seats = _marked(8, values)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert len(sheet.bands) == 1
    assert sheet.bands[0].count == 8
    assert (sheet.bands[0].low, sheet.bands[0].high) == (0, 100)


# ---------------------------------------------------------------------
# The property form, which is what catches the single-pass bug.
# ---------------------------------------------------------------------


@settings(max_examples=250, deadline=None)
@given(
    marks=st.lists(
        st.integers(min_value=0, max_value=TOTAL),
        min_size=MINIMUM_MARKED_RESULTS,
        max_size=40,
    )
)
def test_no_published_band_ever_holds_fewer_than_three(
    marks: list[int],
) -> None:
    seats = _marked(len(marks), marks)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sheet.bands == [] or min(band.count for band in sheet.bands) >= (
        MINIMUM_BAND_SIZE
    ), (
        f"a published band holds fewer than {MINIMUM_BAND_SIZE} results "
        f"for {sorted(marks)}: one merge pass can leave a neighbour "
        "still under three, which is why the rule repeats [BR6.3]"
    )


@settings(max_examples=250, deadline=None)
@given(
    marks=st.lists(
        st.integers(min_value=0, max_value=TOTAL),
        min_size=MINIMUM_MARKED_RESULTS,
        max_size=40,
    )
)
def test_the_band_counts_sum_to_the_marked_count(marks: list[int]) -> None:
    # **The assertion that catches a mark falling through a gap**
    # anywhere in the edge set, not just at the top. A full 100 under
    # naively generated edges lands in no band while still counting in
    # the average, the rank and the threshold -- and a count-based
    # test passes, because the student is absent rather than
    # miscounted.
    seats = _marked(len(marks), marks)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sum(band.count for band in sheet.bands) == len(marks), (
        f"the bands total {sum(b.count for b in sheet.bands)} but "
        f"{len(marks)} results were marked: a mark fell through a gap "
        f"in the band edges for {sorted(marks)}"
    )


def test_a_full_mark_lands_in_the_top_band() -> None:
    # The specific instance, named so a regression reads clearly.
    # `range(0, 100, 20)` yields a top band of 80-99 and
    # `any(lo <= 100 <= hi)` is False.
    values = [100, 100, 100, 50, 50, 50]
    seats = _marked(6, values)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sum(band.count for band in sheet.bands) == 6
    assert sheet.highest == 100


def test_a_zero_lands_in_the_bottom_band() -> None:
    values = [0, 0, 0, 90, 90, 90]
    seats = _marked(6, values)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sum(band.count for band in sheet.bands) == 6


def test_a_non_percentage_total_still_bands_every_mark() -> None:
    # `total_marks` is not always 100 -- the CHECK is `marks <=
    # exam.total_marks` with a floor of 1. The bands are computed over
    # the exam's own scale rather than over a percentage, so there is
    # no second rounding decision hiding in a conversion.
    seats = _marked(6, [0, 7, 13, 20, 33, 40])

    sheet = compute_marksheet(seats, total_marks=40, viewer=seats[0])

    assert isinstance(sheet, Published)
    assert sum(band.count for band in sheet.bands) == 6
    assert sheet.bands[-1].high == 40


# ---------------------------------------------------------------------
# The two independent suppression conditions [BR6.4].
# ---------------------------------------------------------------------


def test_four_marked_and_complete_returns_no_comparison() -> None:
    # A test PER CONDITION, each holding the other satisfied. A single
    # test varying both at once passes while only one check exists.
    # Here: below five marked, and marking is COMPLETE.
    seats = _marked(4, [80, 70, 60, 50])

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert not isinstance(sheet, Published)
    assert sheet.viewer_marks == 80
    assert sheet.reason == "too_few_results"


def test_eight_marked_with_one_not_entered_returns_no_comparison() -> None:
    # The other condition: ABOVE five marked, and marking incomplete.
    # A rank that drifts from 2nd to 7th as marks arrive reads as the
    # app changing the student's result.
    seats = _marked(8, [90, 85, 80, 75, 70, 65, 60, 55])
    seats.append(
        SeatResult(
            enrollment_id=uuid.uuid4(),
            display_name="Unmarked",
            result_state="not_entered",
            marks=None,
        )
    )

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert not isinstance(sheet, Published)
    assert sheet.reason == "marking_incomplete"


def test_a_joined_after_seat_does_not_block_the_comparison() -> None:
    # `joined_after` is not `not_entered`: the seat could not have sat
    # the exam, so it is not marking the teacher still owes. Treating
    # it as incomplete would suppress every marksheet in a batch that
    # ever took a new student.
    seats = _marked(6, [90, 85, 80, 75, 70, 65])
    seats.append(
        SeatResult(
            enrollment_id=uuid.uuid4(),
            display_name="Joined later",
            result_state="joined_after",
            marks=None,
        )
    )

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)


# ---------------------------------------------------------------------
# Absences, and what the shape may contain [BR6.2, BR6.5].
# ---------------------------------------------------------------------


def test_absences_change_no_aggregate() -> None:
    # BR6.5's own named assertion: identical marked results with and
    # without two absent seats produce an IDENTICAL average, rank and
    # band set. Counting an absence as zero drags the average down and
    # moves every rank -- a quiet arithmetic error that looks like a
    # real result.
    values = [92, 88, 81, 74, 71, 68]
    without = _marked(6, values)
    with_absences = _marked(6, values) + [
        SeatResult(
            enrollment_id=uuid.uuid4(),
            display_name=f"Absent {index}",
            result_state="absent",
            marks=None,
        )
        for index in range(2)
    ]

    first = compute_marksheet(without, total_marks=TOTAL, viewer=without[0])
    second = compute_marksheet(
        with_absences, total_marks=TOTAL, viewer=with_absences[0]
    )

    assert isinstance(first, Published)
    assert isinstance(second, Published)
    assert first.average == second.average
    assert first.highest == second.highest
    assert first.viewer_rank == second.viewer_rank
    assert first.marked_count == second.marked_count
    assert [(b.low, b.high, b.count) for b in first.bands] == [
        (b.low, b.high, b.count) for b in second.bands
    ]


def test_the_published_shape_carries_no_per_student_collection() -> None:
    # **The mechanism is schema SHAPE, not filtering** [§ 4.1]. A
    # filtered list is one forgotten predicate from a leak; an absent
    # field is not. Asserted over the type rather than over one
    # instance, so a future field cannot be added unnoticed.
    seats = _marked(9, [92, 88, 81, 74, 71, 68, 55, 41, 12])

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])

    assert isinstance(sheet, Published)
    for name in Published.__slots__:
        value = getattr(sheet, name)
        if name == "bands":
            continue
        assert not isinstance(value, list), (
            f"Published.{name} is a collection: the marksheet carries "
            "no row attributable to another student [BR6.2]"
        )

    # And the one collection it does carry holds counts, not people.
    for band in sheet.bands:
        assert set(type(band).__slots__) == {"low", "high", "count"}


def test_a_rank_is_the_viewers_position_among_marked_results() -> None:
    seats = _marked(9, [92, 88, 81, 74, 71, 68, 55, 41, 12])

    top = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])
    bottom = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[8])

    assert isinstance(top, Published)
    assert isinstance(bottom, Published)
    assert top.viewer_rank == 1
    assert bottom.viewer_rank == 9


def test_tied_marks_share_a_rank() -> None:
    # Standard competition ranking. Two students on 80 are both 1st
    # and the next is 3rd; giving one of them 2nd would publish an
    # ordering between identical results that does not exist.
    values = [80, 80, 70, 60, 50, 40]
    seats = _marked(6, values)

    first = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[0])
    second = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[1])
    third = compute_marksheet(seats, total_marks=TOTAL, viewer=seats[2])

    assert isinstance(first, Published)
    assert isinstance(second, Published)
    assert isinstance(third, Published)
    assert first.viewer_rank == 1
    assert second.viewer_rank == 1
    assert third.viewer_rank == 3


def test_an_absent_viewer_sees_the_comparison_but_no_own_mark() -> None:
    seats = _marked(6, [90, 85, 80, 75, 70, 65])
    absent_viewer = SeatResult(
        enrollment_id=uuid.uuid4(),
        display_name="Absent",
        result_state="absent",
        marks=None,
    )
    seats.append(absent_viewer)

    sheet = compute_marksheet(seats, total_marks=TOTAL, viewer=absent_viewer)

    assert isinstance(sheet, Published)
    assert sheet.viewer_marks is None
    assert sheet.viewer_rank is None
    assert sheet.average is not None


def test_the_band_width_is_the_designs_twenty() -> None:
    assert BAND_WIDTH == 20
    assert MINIMUM_BAND_SIZE == 3
    assert MINIMUM_MARKED_RESULTS == 5
