"""The dues view and the teacher overview: two reads, no parameters.

**Neither route declares a path or query parameter**, which is this
unit's no-id property made concrete [security-design § 1]. D1 through D4
each validate an id a caller supplies and each therefore has a check
that can be omitted; these take no id at all, so the lens's ``owner_id``
is the only scoping value there is.

**The ``/me/`` prefix does not imply that, and it is worth saying so
because it reads as if it does.** ``GET /v1/me/fees`` carries a
``StudentLens`` **and** an ``enrollment_id`` query parameter. The prefix
means "scoped to the caller", not "takes no id" -- so the schema
assertion in ``tests/contract`` is load-bearing rather than a
restatement of a convention: a later ``/v1/me/dues?batch_id=`` would be
perfectly conventional and would reintroduce the class this design
removes.

**Three blocks in one overview response rather than three routes**
[logical-components § 2], because they are one screen and two of the
three share the ledger read. Three routes would be three seat-set
queries for one screen.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.dues import DuesSummary, dues_rows, dues_summary
from app.analytics.earnings import MonthlyEarnings, period_totals, trend
from app.analytics.seats import (
    due_dates_for_seats,
    last_reminders_for_seats,
    ledger_for_seats,
    owned_seats,
)
from app.analytics.today import today_view
from app.analytics.upcoming import next_exam
from app.api.deps import get_session, teacher_lens
from app.api.fees import queue_item_response
from app.authz.lenses import TeacherLens
from app.local_time import bangladesh_today
from app.money import Money as DomainMoney
from app.money.wire import to_wire
from app.schemas.analytics import (
    DuesGroupResponse,
    DuesResponse,
    DuesRowResponse,
    DuesSummaryResponse,
    MonthlyEarningsResponse,
    NextExamResponse,
    OutstandingResponse,
    OverviewResponse,
    TodayClassResponse,
    TodayResponse,
)
from app.schemas.errors import ErrorEnvelope
from app.schemas.money import Money as WireMoney

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["analytics"])

#: The error responses both routes can produce. Neither takes a body or
#: an id, so there is no 400 and no 409: the only refusal in this unit
#: is the shared one for a caller holding no teacher lens
#: [reliability § 3]. **No new error class and no new code** -- D5
#: raises nothing of its own.
_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {
        "model": ErrorEnvelope,
        "description": "No credential, or an expired one.",
    },
    403: {
        "model": ErrorEnvelope,
        "description": "This account holds no teacher lens.",
    },
}


def _to_wire(amount: DomainMoney) -> WireMoney:
    """Render a stored amount as the wire component.

    Two distinct types deliberately, as in ``app/api/fees.py``:
    ``app.money.Money`` is the arithmetic type and
    ``app.schemas.money.Money`` is the serialized one. Keeping them
    separate is what stops a domain value reaching a response body
    without passing the chokepoint, and mypy enforces the crossing.

    :param amount: The stored amount
    :return: The wire representation
    """
    return WireMoney(to_wire(amount))


def _earnings_response(figure: MonthlyEarnings) -> MonthlyEarningsResponse:
    """Render one month's earnings for the wire.

    :param figure: The month as the fold produced it
    :return: The response body
    """
    return MonthlyEarningsResponse(
        period=figure.period,
        received=_to_wire(figure.received),
    )


def _current_period(today: dt.date) -> str:
    """Return the period key for the server's calendar month.

    **The SERVER's month, never the device's** [BR2.6, entities.md].
    A device-supplied month would let a phone's clock change a
    teacher's reported earnings, which this product rules out for
    decisions elsewhere.

    :param today: The server's calendar date
    :return: The period key, as ``YYYY-MM``
    """
    return today.strftime("%Y-%m")


@router.get(
    "/me/dues",
    response_model=DuesResponse,
    responses=_AUTH_ERRORS,
)
def read_dues(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> DuesResponse:
    """Everyone who owes this teacher money, across every batch [FR7.1].

    **Four statements whatever the teacher's size**: the seats, the
    ledger, the due dates and the last reminders, then a fold in memory
    [BR1.6]. The oldest unpaid
    period comes from that same fold rather than from
    ``app/fees/balances.py``'s ``oldest_unpaid_period``, which takes one
    enrollment and would be one query per row.

    **Computed on open** [BR1.4]: no generate step, no refresh action,
    no materialised rollup. A stale figure about money is worse than a
    slow one -- a teacher chases a debt already paid, or fails to chase
    one just incurred.

    **No parameter of any kind.** The lens's ``owner_id`` is the only
    scoping value, so there is nothing to validate and nothing to
    forget.

    :param session: The request-scoped session, which is also what makes
        both statements read ONE snapshot [NFR6.62]
    :param lens: The teacher lens carrying the owner id
    :return: One row per owing seat, largest first, possibly empty
    """
    seats = owned_seats(session, lens)
    seat_ids = [seat.enrollment_id for seat in seats]
    rows = dues_rows(
        seats,
        ledger_for_seats(session, seat_ids),
        due_by_seat=due_dates_for_seats(session, seat_ids),
        last_reminded=last_reminders_for_seats(session, seat_ids),
        today=bangladesh_today(),
    )

    return DuesResponse(
        summary=_summary_response(dues_summary(rows)),
        rows=[
            DuesRowResponse(
                enrollment_id=row.enrollment_id,
                batch_id=row.batch_id,
                batch_name=row.batch_name,
                display_name=row.display_name,
                outstanding=_to_wire(row.outstanding),
                oldest_unpaid_period=row.oldest_unpaid_period,
                latest_unpaid_period=row.latest_unpaid_period,
                days_late=row.days_late,
                bucket=row.bucket,
                last_reminded_at=row.last_reminded_at,
                remindable=row.remindable,
            )
            for row in rows
        ],
    )


def _summary_response(summary: DuesSummary) -> DuesSummaryResponse:
    """Render the dues headline for the wire.

    :param summary: The totals
    :return: The response body
    """
    return DuesSummaryResponse(
        total=_to_wire(summary.total),
        count=summary.count,
        late_total=_to_wire(summary.late_total),
        remindable=summary.remindable,
        groups=[
            DuesGroupResponse(
                bucket=group.bucket,
                total=_to_wire(group.total),
                count=group.count,
                share=group.share,
            )
            for group in summary.groups
        ],
    )


@router.get(
    "/me/overview",
    response_model=OverviewResponse,
    responses=_AUTH_ERRORS,
)
def read_overview(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> OverviewResponse:
    """Return this month's earnings, the trend and the next exam [FR8.1-FR8.4].

    **The earnings total and the trend fold the SAME ledger read**
    [performance § 2]. Two figures from one read, so they cannot
    disagree -- a second query would be a second chance to.

    **Zero is a value, not an absence** [BR2.2]. A month with no
    receipts reports ``"0.00"``, which is a fact about the month, and
    the zero is supplied **here at the boundary** rather than inside the
    fold: inside, absence genuinely means zero, while at the edge it
    could mean the read failed [reliability § 1.3]. The fold runs over
    rows already in hand, so a failure raises rather than producing an
    empty map.

    :param session: The request-scoped session
    :param lens: The teacher lens carrying the owner id
    :return: The three blocks, each able to be absent without the others
    """
    today = dt.datetime.now(tz=dt.UTC).date()
    period = _current_period(today)

    seats = owned_seats(session, lens)
    ledger = ledger_for_seats(session, [seat.enrollment_id for seat in seats])
    entries = [entry for rows in ledger.values() for entry in rows]

    totals = period_totals(entries)
    series = trend(totals)
    upcoming = next_exam(session, lens, today=today)

    return OverviewResponse(
        earnings=_earnings_response(
            MonthlyEarnings(
                period=period,
                received=totals.get(period, DomainMoney.ZERO),
            )
        ),
        trend=(
            None if series is None else [_earnings_response(point) for point in series]
        ),
        next_exam=(
            None
            if upcoming is None
            else NextExamResponse(
                exam_id=upcoming.exam_id,
                title=upcoming.title,
                batch_name=upcoming.batch_name,
                subject_name=upcoming.subject_name,
                date=upcoming.date,
                days_remaining=upcoming.days_remaining,
            )
        ),
    )


@router.get(
    "/me/today",
    response_model=TodayResponse,
    responses=_AUTH_ERRORS,
)
def read_today(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> TodayResponse:
    """Read the teacher's Today screen in one request (T1).

    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: Money owed, today's classes and payments waiting
    """
    view = today_view(session, lens=lens)
    owed = view.outstanding
    return TodayResponse(
        date=view.date,
        outstanding=OutstandingResponse(
            total=WireMoney(to_wire(owed.total)),
            overdue=WireMoney(to_wire(owed.overdue)),
            overdue_students=owed.overdue_students,
            batch_count=owed.batch_count,
        ),
        classes=[
            TodayClassResponse(
                session_id=row.session_id,
                batch_id=row.batch_id,
                batch_name=row.batch_name,
                subject_name=row.subject_name,
                start_time=row.start_time,
                end_time=row.end_time,
                status=_session_status(row.status),
                topic=row.topic,
                topic_logged=row.topic_logged,
                attendance_version=row.attendance_version,
                topic_version=row.topic_version,
                is_next=row.is_next,
                starts_in_minutes=row.starts_in_minutes,
                exam_id=row.exam_id,
                exam_title=row.exam_title,
            )
            for row in view.classes
        ],
        to_verify_count=view.to_verify_count,
        to_verify=[queue_item_response(item) for item in view.to_verify],
        has_batches=view.has_batches,
    )


#: The session statuses the Today response publishes.
_SESSION_STATUSES: Final[tuple[Literal["scheduled", "held", "cancelled"], ...]] = (
    "scheduled",
    "held",
    "cancelled",
)


def _session_status(stored: str) -> Literal["scheduled", "held", "cancelled"]:
    """Narrow a stored session status onto the published set.

    :param stored: The value read from the column
    :return: The same value, narrowed
    :raises ValueError: The stored value is outside the set
    """
    for status in _SESSION_STATUSES:
        if stored == status:
            return status
    raise ValueError(f"{stored!r} is not a session status")
