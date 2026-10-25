"""The anonymised marksheet: a disclosure mechanism, not a view.

**Pure computation. No I/O, no session, no HTTP.** That is what makes
the 100% branch target reachable here, the same property that makes it
true of ``app/money/`` -- and it is why this module lives in its own
file rather than beside the session reads, which would invite a session
parameter and the target with it.

**Treating the marksheet as a feature rather than a disclosure is how
it ships wrong.** In a batch of 8 to 20 students who sit together and
compare marks, twelve unattributed numbers are deanonymised by
inference within a day, so a row list would over-claim "anonymised"
for a product under a Families declaration.

Three mechanisms carry it:

* **Shape, not filtering** [§ 4.1]. :class:`Published` has **no
  per-student collection at all**, so there is no array a future
  change can populate. A filtered list is one forgotten predicate from
  a leak; an absent field is not.
* **The merge repeats** [BR6.3, § 4.2]. One pass can produce a
  neighbour that is itself still under three, and the repetition is
  the part an implementation drops.
* **Two independent suppression conditions** [BR6.4], both of which
  must hold before anything is compared.

**The band edges cover the whole scale inclusively, and the top band
is wide rather than short.** Generating them the obvious way -- fixed
steps of the band width -- leaves the maximum mark falling through
every band: it still counts in the average, the rank and the
five-result threshold, while the distribution silently totals one
fewer than the marked count. A count-based test does not catch it,
because the student is ABSENT from the bands rather than miscounted.
The invariant that does catch it, anywhere in the edge set rather than
only at the top, is that **the band counts sum to the marked count**,
and a test asserts exactly that over generated mark lists.

**The bands are computed over the exam's OWN scale**, never over a
percentage. ``total_marks`` has a floor of 1 and is not always 100, and
converting to a percentage first would hide a second rounding decision
inside the banding -- so a 40-mark exam is banded in steps of 20 over
0..40, which is two bands before merging rather than five.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.marks.results import SeatResult

__all__ = [
    "BAND_WIDTH",
    "MINIMUM_BAND_SIZE",
    "MINIMUM_MARKED_RESULTS",
    "Band",
    "Marksheet",
    "Published",
    "Suppressed",
    "compute_marksheet",
]

#: The band width, in marks. **This design's choice**: no upstream
#: artifact fixes a width or a count, and all four sources say only
#: "banded distribution". The merge rule makes the width largely
#: immaterial to the disclosure property -- what is published is
#: whatever survives merging -- but it is visible to students.
BAND_WIDTH = 20

#: No published band holds fewer than this [BR6.3, NFR14.56]. **A band
#: of one IS a named mark**, with the name supplied by anyone who knows
#: who is in the batch.
MINIMUM_BAND_SIZE = 3

#: No comparison of any kind below this many marked results [BR6.4].
#: Below five, a rank plus a band identifies people directly.
MINIMUM_MARKED_RESULTS = 5


@dataclass(frozen=True, slots=True)
class Band:
    """One published band of the distribution.

    Holds a **count, never a membership**. Both bounds are inclusive.

    :ivar low: The lowest mark in the band
    :ivar high: The highest mark in the band
    :ivar count: How many marked results fall in it
    """

    low: int
    high: int
    count: int


@dataclass(frozen=True, slots=True)
class Published:
    """A marksheet with its comparison [BR6.2].

    **No per-student collection.** The only collection is
    :attr:`bands`, which holds counts rather than people, and a test
    asserts that over the type rather than over one instance.

    :ivar viewer_marks: The viewer's own mark, named, or None where
        they were absent
    :ivar viewer_rank: Their rank among marked results, or None
    :ivar average: The mean of marked results
    :ivar highest: The highest marked result
    :ivar marked_count: How many results were marked
    :ivar bands: The merged distribution
    """

    viewer_marks: int | None
    viewer_rank: int | None
    average: float
    highest: int
    marked_count: int
    bands: list[Band]


@dataclass(frozen=True, slots=True)
class Suppressed:
    """A marksheet with no comparison at all [BR6.4].

    Carries the viewer's own mark and nothing else. **Not an empty
    comparison**: a rank of None beside an average of 0 would read as
    a real result.

    :ivar viewer_marks: The viewer's own mark, or None
    :ivar reason: ``too_few_results`` or ``marking_incomplete``
    """

    viewer_marks: int | None
    reason: str


#: Either outcome. The two are distinct TYPES rather than one object
#: with nullable comparison fields, so a caller cannot render a rank
#: that was never computed.
Marksheet = Published | Suppressed


def _band_edges(total_marks: int) -> list[tuple[int, int]]:
    """Build inclusive band edges covering 0..total_marks.

    **The top band absorbs the remainder rather than being truncated.**
    Edges of ``(0,19), (20,39), ... (80,99)`` over a total of 100 leave
    a full mark in no band at all, which is invisible to a count-based
    assertion because the student is absent from the distribution
    rather than miscounted.

    :param total_marks: The exam's denominator, at least 1
    :return: Inclusive ``(low, high)`` pairs covering the whole scale
    """
    edges: list[tuple[int, int]] = []
    low = 0
    while low <= total_marks:
        high = low + BAND_WIDTH - 1
        # **The LAST band ABSORBS the remainder rather than being
        # truncated or leaving a stub.** Two wrong shapes are ruled
        # out here, and both were produced by earlier versions of this
        # loop over a total of 100:
        #
        # * stopping at `high >= total_marks` gives a final band of
        #   80-99, so a full mark falls through EVERY band while still
        #   counting in the average, the rank and the threshold;
        # * starting a fresh band for the remainder gives a
        #   degenerate 100-100 holding at most the perfect scores,
        #   which the merge would then fold anyway but which is not
        #   the shape the design computes.
        #
        # The design writes the top band as 80-100, so the rule is:
        # if what remains after this band is less than a full band,
        # this band runs to the top of the scale.
        if high + BAND_WIDTH > total_marks:
            edges.append((low, total_marks))
            break
        edges.append((low, high))
        low = high + 1
    return edges


def _merge_small_bands(bands: list[Band]) -> list[Band]:
    """Merge any band under the minimum into its neighbour, repeatedly.

    **The repetition is the requirement** [§ 4.2]. One pass can
    produce a neighbour that is itself still under three, which is why
    this loops until a full pass changes nothing. The terminal case is
    one band holding every result, which discloses nothing beyond the
    count -- and the count is already disclosed by the five-result
    threshold.

    Merging is **downward-biased**: a small band joins the band below
    it where one exists, and the lowest band joins the one above. That
    keeps the published boundaries aligned to the bottom of the scale,
    which is what the worked examples compute.

    :param bands: The raw bands, low to high, empty ones included
    :return: The published bands, each holding at least the minimum
    """
    working = [band for band in bands if band.count > 0]

    while True:
        if len(working) <= 1:
            # One band cannot be merged into anything, and it holds
            # every result by construction.
            return working

        index = next(
            (
                position
                for position, band in enumerate(working)
                if band.count < MINIMUM_BAND_SIZE
            ),
            None,
        )
        if index is None:
            return working

        if index == 0:
            first, second = working[0], working[1]
            merged = Band(
                low=first.low, high=second.high, count=first.count + second.count
            )
            working = [merged, *working[2:]]
        else:
            previous, current = working[index - 1], working[index]
            merged = Band(
                low=previous.low,
                high=current.high,
                count=previous.count + current.count,
            )
            working = [*working[: index - 1], merged, *working[index + 1 :]]


def _distribution(marks: list[int], total_marks: int) -> list[Band]:
    """Band the marks and merge until every band is large enough.

    :param marks: Every marked result
    :param total_marks: The exam's denominator
    :return: The published bands
    """
    raw = [
        Band(
            low=low,
            high=high,
            count=sum(1 for mark in marks if low <= mark <= high),
        )
        for low, high in _band_edges(total_marks)
    ]
    return _merge_small_bands(raw)


def _rank_of(mark: int, marks: list[int]) -> int:
    """Return a mark's standard competition rank.

    Tied marks share a rank and the next distinct mark skips: two
    students on 80 are both 1st and the next is 3rd. Giving one of
    them 2nd would publish an ordering between identical results that
    does not exist.

    :param mark: The viewer's mark
    :param marks: Every marked result
    :return: The 1-based rank
    """
    return 1 + sum(1 for other in marks if other > mark)


def compute_marksheet(
    results: list[SeatResult],
    *,
    total_marks: int,
    viewer: SeatResult,
) -> Marksheet:
    """Compute one viewer's marksheet [BR6.2-BR6.5].

    **The two suppression conditions are independent and both must
    hold** [BR6.4]: fewer than five marked results, or any seat still
    ``not_entered``. A rank that drifts from 2nd to 7th as marks
    arrive reads as the app changing the student's result.

    ``joined_after`` is **not** incomplete marking: the seat could not
    have sat the exam, so it is not work the teacher still owes.
    Treating it as incomplete would suppress every marksheet in a
    batch that ever took a new student.

    **Absences are excluded from every aggregate** [BR6.5] -- the
    average's numerator and denominator, the rank ordering, and every
    band. Counting an absence as zero drags the average down and moves
    every rank, which is a quiet arithmetic error that looks like a
    real result.

    :param results: Every seat's result for this exam
    :param total_marks: The exam's denominator, at least 1
    :param viewer: The seat whose marksheet this is
    :return: The published comparison, or a suppressed marksheet
    """
    marks = [
        result.marks
        for result in results
        if result.result_state == "marked" and result.marks is not None
    ]

    if len(marks) < MINIMUM_MARKED_RESULTS:
        return Suppressed(viewer_marks=viewer.marks, reason="too_few_results")

    if any(result.result_state == "not_entered" for result in results):
        return Suppressed(viewer_marks=viewer.marks, reason="marking_incomplete")

    return Published(
        viewer_marks=viewer.marks,
        viewer_rank=(None if viewer.marks is None else _rank_of(viewer.marks, marks)),
        average=sum(marks) / len(marks),
        highest=max(marks),
        marked_count=len(marks),
        bands=_distribution(marks, total_marks),
    )
