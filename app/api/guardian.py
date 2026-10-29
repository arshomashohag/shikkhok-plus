"""The guardian's home, payments and paying (G1, G3).

Every route resolves the guardian lens and reaches only seats that
guardian accepted. The per-child routes are keyed by any one of the
child's seats -- an id the guardian already reads -- and act on that
child's seats alone [BR5.3].
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, guardian_lens
from app.api.fees import claim_response, payables_response
from app.api.teaching import upcoming_response
from app.authz.lenses import GuardianLens
from app.errors import AuthorizationError
from app.fees import views
from app.fees.claims import submit_claim
from app.fees.payables import payables_for_seats
from app.guardians.children import Child, child_of, children_of
from app.guardians.payments import child_payments
from app.marks.summary import summarise
from app.marks.views import guardian_progress
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.fees import (
    ClaimResponse,
    ClaimSubmitRequest,
    PayablesResponse,
    PaymentDestinationResponse,
)
from app.schemas.guardian import (
    ChildBatchResponse,
    ChildResultResponse,
    ChildSummaryResponse,
    GuardianHomeResponse,
    PaymentLineResponse,
    PaymentMonthResponse,
    PaymentsResponse,
    ProgressSummaryResponse,
)
from app.schemas.money import Money as WireMoney
from app.teaching.upcoming import UpcomingSession, upcoming_sessions

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["guardian"])

#: The error shapes a guardian read can produce.
_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {"model": ErrorEnvelope, "description": "No lens reaches this."},
}


@router.get(
    "/guardian/home", response_model=GuardianHomeResponse, responses=_AUTH_ERRORS
)
def read_guardian_home(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> GuardianHomeResponse:
    """Every child, with what to pay next, what is checking and latest results (G1).

    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The children, by name
    """
    children = children_of(session, lens=lens)
    coming = upcoming_sessions(
        session,
        batch_ids=[seat.batch_id for child in children for seat in child.seats],
    )
    return GuardianHomeResponse(
        children=[_summary(session, lens, child, coming) for child in children]
    )


def _summary(
    session: Session,
    lens: GuardianLens,
    child: Child,
    coming: dict[uuid.UUID, list[UpcomingSession]],
) -> ChildSummaryResponse:
    """Summarise one child for G1.

    :param session: The request-scoped session
    :param lens: The guardian lens
    :param child: The child
    :param coming: Each batch's coming classes
    :return: The summary
    """
    found = payables_response(
        payables_for_seats(
            session, [(seat.enrollment_id, seat.batch_name) for seat in child.seats]
        )
    )
    return ChildSummaryResponse(
        key=child.key,
        display_name=child.display_name,
        batch_count=len(child.seats),
        next_payment=found.payable[0] if found.payable else None,
        waiting=found.waiting,
        latest_results=[
            result
            for seat in child.seats
            if (
                result := _latest_result(
                    session, lens, seat.enrollment_id, seat.batch_name
                )
            )
        ],
        batches=[
            ChildBatchResponse(
                enrollment_id=seat.enrollment_id,
                batch_name=seat.batch_name,
                teacher_display_name=seat.teacher_name,
                next_session=(
                    upcoming_response(coming[seat.batch_id][0])
                    if coming.get(seat.batch_id)
                    else None
                ),
            )
            for seat in child.seats
        ],
    )


def _latest_result(
    session: Session, lens: GuardianLens, enrollment_id: uuid.UUID, batch_name: str
) -> ChildResultResponse | None:
    """Return a seat's latest marked result and how it compares.

    The trend compares the two marks as shares of their totals, so a
    25-mark test and a 50-mark test compare fairly. None where nothing
    is marked, or where the teacher hides marksheets from families.

    :param session: The request-scoped session
    :param lens: The guardian lens
    :param enrollment_id: The seat
    :param batch_name: Its batch
    :return: The latest result, or None
    """
    try:
        entries = guardian_progress(session, lens=lens, enrollment_id=enrollment_id)
    except AuthorizationError:
        return None
    marked = [(entry, entry.marks) for entry in entries if entry.marks is not None]
    if not marked:
        return None
    last, marks = marked[-1]
    previous = marked[-2] if len(marked) > 1 else None
    trend: Literal["up", "down", "same", "first"] = "first"
    if previous is not None:
        now_share = marks * previous[0].total_marks
        then_share = previous[1] * last.total_marks
        if now_share > then_share:
            trend = "up"
        elif now_share < then_share:
            trend = "down"
        else:
            trend = "same"
    return ChildResultResponse(
        enrollment_id=enrollment_id,
        batch_name=batch_name,
        title=last.title,
        date=last.date,
        marks=marks,
        total_marks=last.total_marks,
        previous_marks=previous[1] if previous else None,
        trend=trend,
    )


@router.get(
    "/children/{enrollment_id}/payables",
    response_model=PayablesResponse,
    responses=_AUTH_ERRORS,
)
def read_child_payables(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> PayablesResponse:
    """List what can be paid for the child holding this seat.

    :param enrollment_id: Any one of the child's seats
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The payable months and the waiting batches
    """
    child = child_of(session, lens=lens, enrollment_id=enrollment_id)
    return payables_response(
        payables_for_seats(
            session, [(seat.enrollment_id, seat.batch_name) for seat in child.seats]
        )
    )


@router.get(
    "/children/{enrollment_id}/payment-destination",
    response_model=PaymentDestinationResponse | None,
    responses=_AUTH_ERRORS,
)
def read_child_payment_destination(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> PaymentDestinationResponse | None:
    """Return where to pay for this seat, for its guardian.

    The second downward disclosure of the collection number, to the
    accepted guardian of a seat in that teacher's batch.

    :param enrollment_id: The seat
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The destination, or None where the teacher set no number
    """
    destination = views.payment_destination(
        session, lens=lens, enrollment_id=enrollment_id
    )
    if destination is None:
        return None
    return PaymentDestinationResponse(
        collection_number=destination.collection_number,
        collection_channel=destination.collection_channel,
        channels=list(destination.channels),
        teacher_display_name=destination.teacher_display_name,
    )


@router.post(
    "/children/{enrollment_id}/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_AUTH_ERRORS,
)
def create_child_claim(
    enrollment_id: uuid.UUID,
    body: ClaimSubmitRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> ClaimResponse:
    """Record a guardian's payment for their child's oldest unpaid month.

    :param enrollment_id: The seat
    :param body: The claimed amount, channel and reference
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The pending claim
    """
    views.enrollment_fee_history(session, lens=lens, enrollment_id=enrollment_id)
    claim = submit_claim(
        session,
        enrollment_id=enrollment_id,
        submitted_by_account_id=lens.account_id,
        claimed_amount=parse(body.claimed_amount.root),
        channel=body.channel,
        transaction_id=body.transaction_id,
    )
    return claim_response(views.claim_detail(session, lens=lens, claim_id=claim.id))


@router.get(
    "/children/{enrollment_id}/payments",
    response_model=PaymentsResponse,
    responses=_AUTH_ERRORS,
)
def read_child_payments(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> PaymentsResponse:
    """Return a child's fee history, newest month first, with this year's total.

    :param enrollment_id: Any one of the child's seats
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The history
    """
    child = child_of(session, lens=lens, enrollment_id=enrollment_id)
    found = child_payments(session, lens=lens, child=child)
    months: dict[str, list[PaymentLineResponse]] = {}
    for line in found.lines:
        months.setdefault(line.period, []).append(
            PaymentLineResponse(
                enrollment_id=line.enrollment_id,
                batch_name=line.batch_name,
                amount=WireMoney(to_wire(line.amount)),
                state=line.state,
                due_date=line.due_date,
                sent_on=line.sent_on,
                decided_on=line.decided_on,
                channel=line.channel,
            )
        )
    return PaymentsResponse(
        display_name=child.display_name,
        year=found.year,
        paid_this_year=WireMoney(to_wire(found.paid_this_year)),
        months=[
            PaymentMonthResponse(period=p, lines=rows) for p, rows in months.items()
        ],
    )


@router.get(
    "/children/{enrollment_id}/progress/summary",
    response_model=ProgressSummaryResponse | None,
    responses=_AUTH_ERRORS,
)
def read_child_progress_summary(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> ProgressSummaryResponse | None:
    """Read a child's latest run of results in one batch (G2).

    :param enrollment_id: The seat
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: The run, or None with fewer than two marked results
    """
    found = summarise(
        guardian_progress(session, lens=lens, enrollment_id=enrollment_id)
    )
    if found is None:
        return None
    return ProgressSummaryResponse(
        direction=found.direction,
        run=found.run,
        first_marks=found.first_marks,
        last_marks=found.last_marks,
        total_marks=found.total_marks,
        above_average=found.above_average,
    )
