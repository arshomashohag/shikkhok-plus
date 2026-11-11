"""Request and response bodies for exams, marks and the marksheet.

**``total_marks`` is an integer COUNT and ``marks`` a count with at most
two decimal places (decided 2026-11-05); neither is ever money.**
They must never acquire a money type, for the same reason
``Batch.collection_number`` must not. ``total_marks`` matches the
money-name gate's ``total`` token and carries a per-field exemption
stating exactly that; ``marks`` matches no token at all.

**The marksheet carries no per-student collection** [§ 4.1, BR6.2].
The mechanism is schema SHAPE, not filtering: there is no array a
future change can populate, because a filtered list is one forgotten
predicate from a leak and an absent field is not. In a batch of 8 to
20 students who sit together and compare marks, twelve unattributed
numbers are deanonymised by inference within a day.

**A suppressed marksheet is a DIFFERENT shape, not a nulled one**
[BR6.4]. A rank of null beside an average of zero would read as a real
result, so the two outcomes are distinct response models and the
client switches on which arrived.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

__all__ = [
    "INT4_MAX",
    "MAX_TOTAL_MARKS",
    "BandResponse",
    "CorrectionEntryResponse",
    "ExamCancelRequest",
    "ExamCreateRequest",
    "ExamListItemResponse",
    "ExamResponse",
    "ExamResultsResponse",
    "ExamUpdateRequest",
    "ExaminerRequest",
    "MarkWriteRequest",
    "MarksheetResponse",
    "ProgressEntryResponse",
    "PublishedMarksheetResponse",
    "ResultState",
    "SeatResultResponse",
    "SuppressedMarksheetResponse",
    "SuppressionReason",
]

#: FR4.3's four states [BR4.3]. A client switches on this enum, so
#: adding a value is a breaking change under § B.1.1.
ResultState = Literal["marked", "absent", "not_entered", "joined_after"]

#: The two a teacher may TYPE. ``not_entered`` and ``joined_after``
#: are derived from facts and never selected.
EnterableState = Literal["marked", "absent"]

#: Why a marksheet published no comparison [BR6.4].
SuppressionReason = Literal["too_few_results", "marking_incomplete"]

#: The largest denominator an exam may have [SEC-3]. Generous for any
#: school paper (a hundred or two is usual, a thousand covers a whole
#: term's aggregate) and far inside ``Integer``, so an absurd total is a
#: 400 at the schema rather than an int4 overflow at the database.
MAX_TOTAL_MARKS: Final = 1000

#: The largest value the ``Integer`` ``total_marks`` column holds. An
#: EDIT is bounded only by this at the schema, so a total past it is
#: still a 422 rather than an int4 overflow at the database [SEC-3],
#: while an exam stored before :data:`MAX_TOTAL_MARKS` existed, with a
#: larger total, stays editable. The service then refuses any NEW total
#: past :data:`MAX_TOTAL_MARKS` (see :func:`app.marks.exams.update_exam`).
INT4_MAX: Final = 2**31 - 1


ExamTopic = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class ExamResponse(BaseModel):
    """One assessment.

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar date: When it was sat
    :ivar total_marks: The denominator, an integer COUNT
    :ivar subject_name: The subject assessed
    :ivar topics: What it covers, in the order the teacher gave
    :ivar cancelled: Whether the teacher cancelled it [0019]. A flag
        beside ``state`` rather than a new ``state`` value, so a client
        built before cancelling existed still decodes the list
    :ivar cancellation_reason: The teacher's note on cancelling, if any
    """

    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    title: str
    date: dt.date
    total_marks: int = Field(ge=1)
    subject_name: str
    topics: list[str] = Field(default_factory=list)
    cancelled: bool = False
    cancellation_reason: str | None = None
    examiner_member_id: uuid.UUID | None = None
    examiner_name: str | None = None


class ExamListItemResponse(ExamResponse):
    """One exam on the teacher's list, with its marking progress.

    Counted server-side, so the client never tallies a rows list to
    decide what counts as entered.

    :ivar entered_count: Seats with a mark or an absence entered
    :ivar expected_count: Seats that could have sat the exam
    :ivar published: Whether the results are out to students and
        guardians; a draft until the teacher publishes (2026-11-05)
    :ivar state: ``upcoming``, ``needs_marks`` or ``complete``, decided
        by the server so the client never compares a date or a count
    """

    entered_count: int = Field(ge=0)
    expected_count: int = Field(ge=0)
    state: Literal["upcoming", "needs_marks", "complete"]
    published: bool = False


class ExamCancelRequest(BaseModel):
    """Cancel an exam whose results are not published.

    :ivar reason: A short note for the record, if any
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=200)


class ExamCreateRequest(BaseModel):
    """Create or edit an assessment [BR4.1].

    :ivar batch_subject_id: One of the batch's own subjects
    :ivar title: The teacher's name for it
    :ivar date: When it was sat
    :ivar total_marks: The denominator, 1 to :data:`MAX_TOTAL_MARKS`
    :ivar examiner_member_id: At a centre, the member who marks it; left
        out, the batch's one weekly teacher is the default. Read on
        creation only: an edit changes the examiner through its own route
    :ivar topics: What it covers: at most 20, each 1 to 120 characters
    """

    model_config = ConfigDict(extra="forbid")

    batch_subject_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    date: dt.date
    total_marks: int = Field(ge=1, le=MAX_TOTAL_MARKS)
    topics: list[ExamTopic] = Field(default_factory=list, max_length=20)
    examiner_member_id: uuid.UUID | None = None


class ExamUpdateRequest(BaseModel):
    """Edit an assessment: what it is called, when, and out of how much.

    No subject: an edit names what changes, and the exam stays in the
    subject it was set in.

    :ivar title: The teacher's name for it
    :ivar date: When it was sat
    :ivar total_marks: The denominator, and not below any mark already
        recorded. 1 to :data:`MAX_TOTAL_MARKS` when it changes; an exam
        whose stored total is already larger may keep that total, so the
        schema bounds it only by :data:`INT4_MAX`
    :ivar topics: What it covers, replacing the old list; omitted or null
        keeps the existing topics, so an app built before topics existed
        cannot wipe them by editing the title [D-26]
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    date: dt.date
    total_marks: int = Field(ge=1, le=INT4_MAX)
    topics: list[ExamTopic] | None = Field(default=None, max_length=20)


class MarkWriteRequest(BaseModel):
    """Enter or correct one seat's result [BR4.2].

    **No version field**: a mark is an interactive write and cannot
    conflict [BR3.11].

    ``marks`` is non-null if and only if ``result_state`` is
    ``marked``. A zero IS a mark: a zero stored as ``absent`` tells a
    guardian their child missed an exam they sat and failed.

    :ivar enrollment_id: The seat
    :ivar result_state: ``marked`` or ``absent``
    :ivar marks: The number, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    result_state: EnterableState
    marks: float | None = Field(default=None, ge=0)


class SeatResultResponse(BaseModel):
    """One seat's result, as its TEACHER sees it.

    Teacher-facing, which is why it may carry a per-student row at
    all: the privacy boundary this unit protects is between FAMILIES,
    and a teacher already knows who is in their own class. The
    marksheet a student reads carries nothing of the kind.

    :ivar enrollment_id: The teacher-facing key
    :ivar display_name: The TEACHER-typed name
    :ivar result_state: One of the four states
    :ivar marks: The number, or null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    display_name: str
    result_state: ResultState
    marks: float | None = None


class ExamResultsResponse(BaseModel):
    """One exam's results, with the exam and whether it may be written.

    **A wrapper rather than a bare array, and `writable` is why.** The
    screen must know whether to offer mark entry at all, and that is a
    server decision [BR5.5]: an exam in an inactive batch is read-only
    and the write is refused with `teaching.batch.inactive`. Without
    it the client either guesses, or offers an entry field that fails
    on save — which is the failure a person blames on the app.

    The exam travels with the results because the screen shows its
    title and total alongside them, and a second request to learn what
    the first was about is a round trip the server can spare.

    :ivar exam: The exam these results belong to
    :ivar results: One row per seat [BR4.3]
    :ivar writable: Whether marks may be entered, decided server-side
    """

    model_config = ConfigDict(extra="forbid")

    exam: ExamListItemResponse
    results: list[SeatResultResponse]
    writable: bool


class CorrectionEntryResponse(BaseModel):
    """One row in a seat's correction history [FR9.2].

    :ivar mark_id: The row
    :ivar result_state: What it recorded
    :ivar marks: Its number, or null
    :ivar recorded_at: When it was entered
    :ivar superseded: Whether a later row replaced it
    """

    model_config = ConfigDict(extra="forbid")

    mark_id: uuid.UUID
    result_state: ResultState
    marks: float | None = None
    recorded_at: dt.datetime
    superseded: bool


class BandResponse(BaseModel):
    """One published band of the distribution.

    Holds a **count, never a membership**. Both bounds inclusive.

    :ivar low: The lowest mark in the band
    :ivar high: The highest mark in the band
    :ivar count: How many marked results fall in it
    """

    model_config = ConfigDict(extra="forbid")

    low: int
    high: int
    count: int = Field(ge=3)


class PublishedMarksheetResponse(BaseModel):
    """A marksheet with its comparison [BR6.2].

    **No per-student collection.** ``bands`` holds counts rather than
    people, and a test over the generated document asserts that no
    property of this schema is a collection of student-shaped
    objects.

    :ivar published: Always true; the discriminator a client switches
        on
    :ivar exam_title: The exam's title
    :ivar total_marks: Its denominator
    :ivar viewer_result_state: The viewer's own result state
    :ivar viewer_marks: The viewer's own mark, or null if absent
    :ivar viewer_rank: Their rank among marked results, or null
    :ivar average: The mean of marked results
    :ivar highest: The highest marked result
    :ivar marked_count: How many results were marked
    :ivar bands: The merged distribution
    """

    model_config = ConfigDict(extra="forbid")

    published: Literal[True] = True
    exam_title: str
    total_marks: int = Field(ge=1)
    viewer_result_state: ResultState
    viewer_marks: float | None = None
    viewer_rank: int | None = None
    average: float
    highest: float
    marked_count: int
    bands: list[BandResponse]


class SuppressedMarksheetResponse(BaseModel):
    """A marksheet with no comparison at all [BR6.4].

    A **distinct shape** rather than the published one with nulls: a
    rank of null beside an average of zero would read as a real
    result.

    :ivar published: Always false; the discriminator
    :ivar exam_title: The exam's title
    :ivar total_marks: Its denominator
    :ivar viewer_result_state: The viewer's own result state
    :ivar viewer_marks: The viewer's own mark, or null
    :ivar reason: Why no comparison was published
    """

    model_config = ConfigDict(extra="forbid")

    published: Literal[False] = False
    exam_title: str
    total_marks: int = Field(ge=1)
    viewer_result_state: ResultState
    viewer_marks: float | None = None
    reason: SuppressionReason


#: Either outcome, discriminated by ``published``.
MarksheetResponse = PublishedMarksheetResponse | SuppressedMarksheetResponse


class ProgressEntryResponse(BaseModel):
    """One exam in a child's progress series [BR6.6].

    **An absence carries no numeric value**, rather than a zero: an
    absence plotted as zero shows a collapse in performance that did
    not happen.

    :ivar exam_id: The exam
    :ivar title: Its title
    :ivar date: When it was sat
    :ivar total_marks: Its denominator
    :ivar result_state: One of the four states
    :ivar marks: The number, or null
    :ivar subject_name: Which subject the exam was in
    :ivar rank: The viewer's rank, only where the marksheet publishes
        its comparison [BR6.4]; else null
    :ivar ranked_out_of: How many marked results the rank is among
    :ivar batch_average: The batch's average mark, on the same condition
    """

    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    title: str
    date: dt.date
    total_marks: int = Field(ge=1)
    result_state: ResultState
    marks: float | None = None
    subject_name: str | None = None
    rank: int | None = Field(default=None, ge=1)
    ranked_out_of: int | None = Field(default=None, ge=1)
    batch_average: float | None = Field(default=None, ge=0)


class ExaminerRequest(BaseModel):
    """Name, change or clear an exam's examiner [C4].

    :ivar examiner_member_id: The centre member who marks it, or null
    """

    model_config = ConfigDict(extra="forbid")

    examiner_member_id: uuid.UUID | None
