"""Response bodies for the dues view and the teacher overview.

**Every money value is a JSON string, never a number** [BR6.2 of D3,
TC-7, D-20], through the shared ``Money`` component. A JSON number is an
IEEE 754 double in most parsers, so emitting one converts the value to a
float on the client -- reintroducing the representation error the money
module exists to prevent, on the far side of the wire where none of its
controls reach.

**Three kinds of nothing, none collapsible** [NFR19.52, reliability § 2]:

===================== ======================= ============
Case                  Wire shape              Rule
===================== ======================= ============
Nobody owes           an **empty collection** BR1.5
Nothing received      a **zero value**        BR2.2
Under two months      the trend is **absent** BR2.3
No upcoming exam      the exam is **absent**  BR3.4
===================== ======================= ============

**Absent and zero are different wire shapes and encoding either as the
other is the defect.** An absent earnings block tells a teacher their
records are missing when they are complete; a zero-point trend implies a
direction from one observation.

**No ``collection_rate`` field** [BR4.1]. OQ-2 is open and a field is
additive under ``/v1/`` -- a wrong number pinned into an installed
client cannot be withdrawn. ``tests/contract`` asserts its absence from
the generated document.

**``DuesResponse`` wraps the collection rather than the route returning
a bare list**, and that is a privacy control rather than a style
preference: ``app/contract/privacy.py`` finds a route's response
component by ``route.response_model.__name__``, which for ``list[X]``
is ``"list"`` and matches no component -- so a bare-list route is
**skipped by the schema-wide privacy gate entirely**. A dues list is a
list of people and is the natural place to leak a student's
self-authored name to a teacher, so this is the one response in the
product that most needs that gate to see it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.fees import ClaimQueueItemResponse
from app.schemas.money import MoneyField

__all__ = [
    "DuesResponse",
    "DuesRowResponse",
    "MonthlyEarningsResponse",
    "NextExamResponse",
    "OutstandingResponse",
    "OverviewResponse",
    "TodayClassResponse",
    "TodayResponse",
]


class DuesRowResponse(BaseModel):
    """One person who owes money, in one batch [FR7.1].

    The key is ``enrollment_id`` and never an account id [ADR-001], and
    ``display_name`` is the TEACHER's record rather than anything the
    student or guardian wrote [TC-13]. Both are asserted schema-wide by
    the built privacy gate rather than by remembering it here.

    :ivar enrollment_id: The teacher-facing key
    :ivar batch_id: The batch the debt sits in
    :ivar batch_name: That batch's name, because the same person may
        owe in two
    :ivar display_name: The teacher-typed name
    :ivar outstanding: What this seat still owes
    :ivar oldest_unpaid_period: Which period the debt starts in, or
        null
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    display_name: str
    outstanding: MoneyField
    oldest_unpaid_period: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"
    )


class DuesResponse(BaseModel):
    """Everyone who owes this teacher money, across every batch.

    **An empty ``rows`` is the defined empty state** [BR1.5], never a
    404 and never an error: a teacher whose students have all paid is
    getting the best possible news, and a failure shape would make the
    app render a retry prompt for it.

    :ivar rows: One entry per owing seat, largest debt first, possibly
        empty
    """

    model_config = ConfigDict(extra="forbid")

    rows: list[DuesRowResponse] = Field(default_factory=list)


class MonthlyEarningsResponse(BaseModel):
    """Money received in one calendar month [FR8.1].

    :ivar period: The month, as ``YYYY-MM``
    :ivar received: ``receipt`` plus ``credit_grant`` for that month
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    received: MoneyField


class NextExamResponse(BaseModel):
    """The soonest exam dated today or later [FR8.4].

    :ivar exam_id: The exam
    :ivar title: The teacher's name for it
    :ivar batch_name: Which class sits it
    :ivar subject_name: The subject assessed
    :ivar date: When it is sat
    :ivar days_remaining: Whole days, computed server-side [BR3.2] --
        a client computing it would use the device clock and would
        disagree across time zones
    """

    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    title: str
    batch_name: str
    subject_name: str
    date: dt.date
    days_remaining: int


class OverviewResponse(BaseModel):
    """The three blocks of the teacher overview, each independently absent.

    **``earnings`` is never absent and ``trend`` and ``next_exam``
    may be**, which is the distinction this model exists to publish:

    * ``earnings`` carries a **zero value** in a month with no receipts
      [BR2.2]. Rendering zero as "no data" tells a teacher their records
      are missing when they are complete, in the month they most need to
      know the number is really zero;
    * ``trend`` is **null under two months of history** [BR2.3], not a
      one-point series -- a single point implies a direction it cannot
      know;
    * ``next_exam`` is **null when nothing is scheduled** [BR3.4], which
      the client renders as a defined empty state rather than a failure.

    :ivar earnings: This month's money received; never absent
    :ivar trend: The monthly series ascending, or null under two months
    :ivar next_exam: The soonest upcoming exam, or null
    """

    model_config = ConfigDict(extra="forbid")

    earnings: MonthlyEarningsResponse
    trend: list[MonthlyEarningsResponse] | None = None
    next_exam: NextExamResponse | None = None


class OutstandingResponse(BaseModel):
    """What students owe across every batch, and how much is late (T1).

    **``overdue`` is the server's decision**: owing on a period whose
    due date has passed in Bangladesh. The client never compares a due
    date with its clock.

    :ivar total: Everything still owed
    :ivar overdue: The part owed on periods past their due date
    :ivar overdue_students: Seats with anything overdue
    :ivar batch_count: Batches with anything owing
    """

    model_config = ConfigDict(extra="forbid")

    total: MoneyField
    overdue: MoneyField
    overdue_students: int
    batch_count: int


class TodayClassResponse(BaseModel):
    """One class today (T1).

    :ivar session_id: The class
    :ivar batch_id: Its batch
    :ivar batch_name: The batch's name
    :ivar subject_name: The subject, where one is set
    :ivar start_time: When it starts
    :ivar end_time: When it ends, where set
    :ivar status: ``scheduled``, ``held`` or ``cancelled``
    :ivar topic: The logged topic, where one was written
    :ivar topic_logged: Whether a topic was written at all
    :ivar attendance_version: The version a roster write composes against
    :ivar topic_version: The version a topic write composes against
    :ivar is_next: The first class still to start
    :ivar starts_in_minutes: Minutes until it starts, or null once begun
    :ivar exam_id: An exam this batch sits today
    :ivar exam_title: That exam's title
    """

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    subject_name: str | None = None
    start_time: dt.time
    end_time: dt.time | None = None
    status: Literal["scheduled", "held", "cancelled"]
    topic: str | None = None
    topic_logged: bool
    attendance_version: int
    topic_version: int
    is_next: bool
    starts_in_minutes: int | None = None
    exam_id: uuid.UUID | None = None
    exam_title: str | None = None


class TodayResponse(BaseModel):
    """The teacher's Today screen in one read (T1).

    :ivar date: Today, in Bangladesh
    :ivar outstanding: Money owed and overdue
    :ivar classes: Today's classes, by start time
    :ivar to_verify_count: How many payments wait to be checked
    :ivar to_verify: The first few of them
    :ivar has_batches: Whether the teacher has made a batch yet
    """

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    outstanding: OutstandingResponse
    classes: list[TodayClassResponse]
    to_verify_count: int
    to_verify: list[ClaimQueueItemResponse]
    has_batches: bool
