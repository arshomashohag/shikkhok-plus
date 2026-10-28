"""Fee, claim and verification routes.

**Every route resolves a lens**, and the route-enumeration gate fails CI
on one that does not. The lens is a dependency returning the value the
handler needs rather than a guard returning nothing, so a handler cannot
compile a scoped query without it [TC-11].

**D3 is the first unit with declared error responses**, which closes a
known stopgap: ``app/main.py`` injects ``ErrorEnvelope`` into the
generated schema explicitly because FastAPI emits a component only when
a route references one. These declarations turn that injection into a
no-op rather than a lie, exactly as its own comment anticipates -- and a
ZAP pass driven from the committed schema can now know which error
shapes to expect.

**Responses carry decisions, not inputs to decisions** [TC-9, D-31]. A
cycle carries its server-computed status; no response leaves a client to
compare an amount.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, guardian_lens, student_lens, teacher_lens
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.fees import views
from app.fees.claims import submit_claim
from app.fees.queue import QueueItem, shortfall_preview, verification_queue
from app.fees.reminders import remind
from app.fees.verification import reject_claim, verify_claim
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.fees import (
    ClaimQueueItemResponse,
    ClaimResponse,
    ClaimSubmitRequest,
    DuplicateClaimResponse,
    FeeCycleResponse,
    FeeHistoryResponse,
    PaymentDestinationResponse,
    RecentDecisionResponse,
    RejectionRequest,
    ReminderRequest,
    ReminderResponse,
    RosterFeeRowResponse,
    ShortfallPreviewRequest,
    ShortfallPreviewResponse,
    VerificationQueueResponse,
    VerificationRequest,
)
from app.schemas.money import Money as WireMoney

__all__ = ["queue_item_response", "router"]

router = APIRouter(prefix="/v1", tags=["fees"])

#: The error responses every lensed fee route can produce. Declared once
#: and spread onto each route, so a new route cannot quietly ship with
#: an undeclared envelope -- and so the shapes in the committed contract
#: match what the handlers actually raise.
_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {
        "model": ErrorEnvelope,
        "description": "No credential, or an expired one.",
    },
    403: {
        "model": ErrorEnvelope,
        "description": (
            "No lens reaches this. Deliberately indistinguishable from "
            "absence: one code covers both, because a pair would be an "
            "existence oracle."
        ),
    },
}

#: The same plus the validation shape, for routes that take a body.
_WRITE_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    **_AUTH_ERRORS,
    400: {
        "model": ErrorEnvelope,
        "description": "The request is wrong. Fix and resubmit; never retry as-is.",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "Valid request; current state forbids it. Refetch and decide.",
    },
}


def _to_wire(amount: DomainMoney) -> WireMoney:
    """Render a stored amount as the wire component.

    **Two distinct types, deliberately.** ``app.money.Money`` is the
    arithmetic type and ``app.schemas.money.Money`` is the serialized
    one -- a JSON string carrying the canonical pattern. Keeping them
    separate is what stops a domain value reaching a response body
    without passing the chokepoint, and mypy enforces the crossing
    because the two are not interchangeable.

    :param amount: The stored amount
    :return: The wire representation
    """
    return WireMoney(to_wire(amount))


def _optional_wire(amount: DomainMoney | None) -> WireMoney | None:
    """Render an optional stored amount.

    :param amount: The stored amount, or None
    :return: The wire representation, or None
    """
    return None if amount is None else _to_wire(amount)


def _cycle_response(row: views.FeeCycleRow) -> FeeCycleResponse:
    """Render one cycle for the wire.

    :param row: The cycle as the view described it
    :return: The response body
    """
    return FeeCycleResponse(
        period=row.period,
        due_date=row.due_date,
        charged=_to_wire(row.charged),
        outstanding=_to_wire(row.outstanding),
        status=row.status,
    )


def _claim_response(detail: views.ClaimDetail) -> ClaimResponse:
    """Render one claim for the wire.

    :param detail: The claim as the view described it
    :return: The response body
    """
    previous = detail.previous_decision
    return ClaimResponse(
        claim_id=detail.claim_id,
        period=detail.period,
        claimed_amount=_to_wire(detail.claimed_amount),
        approved_amount=_optional_wire(detail.approved_amount),
        status=detail.status,
        shortfall_disposition=detail.shortfall_disposition,
        channel=detail.channel,
        submitted_at=detail.submitted_at,
        verified_at=detail.verified_at,
        previous_decision=(
            None
            if previous is None
            else {
                key: None if value is None else str(value)
                for key, value in previous.items()
            }
        ),
    )


@router.get(
    "/batches/{batch_id}/fees",
    response_model=list[RosterFeeRowResponse],
    responses=_AUTH_ERRORS,
)
def read_batch_fees(
    batch_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> list[RosterFeeRowResponse]:
    """List every seat's fee position on one of this teacher's batches.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens carrying the owner id
    :return: One row per seat
    """
    return [
        RosterFeeRowResponse(
            enrollment_id=row.enrollment_id,
            display_name=row.display_name,
            outstanding=_to_wire(row.outstanding),
            current_period=row.current_period,
            current_status=row.current_status,
            due_date=row.due_date,
            days_overdue=row.days_overdue,
            verifying=_optional_wire(row.verifying),
        )
        for row in views.batch_fee_overview(session, lens=lens, batch_id=batch_id)
    ]


@router.get(
    "/enrollments/{enrollment_id}/fees",
    response_model=FeeHistoryResponse,
    responses=_AUTH_ERRORS,
)
def read_enrollment_fees_as_teacher(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> FeeHistoryResponse:
    """List one seat's generated periods, for its teacher.

    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: One row per generated period
    """
    history = views.enrollment_fee_history(
        session, lens=lens, enrollment_id=enrollment_id
    )
    return FeeHistoryResponse(
        cycles=[_cycle_response(row) for row in history.cycles],
        # The SERVER's total, from the ledger fold. The client is not
        # permitted to sum the rows [D-20, TC-9].
        total_outstanding=WireMoney(to_wire(history.total_outstanding)),
    )


@router.get(
    "/me/fees",
    response_model=FeeHistoryResponse,
    responses=_AUTH_ERRORS,
)
def read_my_fees(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> FeeHistoryResponse:
    """List this student's own periods for one of their seats.

    The seat arrives as a query parameter and the grant is checked
    against it, never the other way round: the handler cannot reach a
    second seat because the view refuses one this lens does not hold.

    :param enrollment_id: The seat to read
    :param session: The request-scoped session
    :param lens: The student lens
    :return: One row per generated period
    """
    history = views.enrollment_fee_history(
        session, lens=lens, enrollment_id=enrollment_id
    )
    return FeeHistoryResponse(
        cycles=[_cycle_response(row) for row in history.cycles],
        # The SERVER's total, from the ledger fold. The client is not
        # permitted to sum the rows [D-20, TC-9].
        total_outstanding=WireMoney(to_wire(history.total_outstanding)),
    )


@router.get(
    "/children/{enrollment_id}/fees",
    response_model=FeeHistoryResponse,
    responses=_AUTH_ERRORS,
)
def read_child_fees(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[GuardianLens, Depends(guardian_lens)],
) -> FeeHistoryResponse:
    """List one child's periods, for their recorded guardian.

    The child arrives as a **path parameter**, never from a
    client-supplied lens hint [BR5.1, OQ-7].

    :param enrollment_id: The child's seat, from the route path
    :param session: The request-scoped session
    :param lens: The guardian lens
    :return: One row per generated period
    """
    history = views.enrollment_fee_history(
        session, lens=lens, enrollment_id=enrollment_id
    )
    return FeeHistoryResponse(
        cycles=[_cycle_response(row) for row in history.cycles],
        # The SERVER's total, from the ledger fold. The client is not
        # permitted to sum the rows [D-20, TC-9].
        total_outstanding=WireMoney(to_wire(history.total_outstanding)),
    )


@router.get(
    "/enrollments/{enrollment_id}/payment-destination",
    response_model=PaymentDestinationResponse | None,
    responses=_AUTH_ERRORS,
)
def read_payment_destination(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> PaymentDestinationResponse | None:
    """Return where to pay for this seat [BR6.4, NFR14.32].

    **The one route in the product carrying the collection number**, and
    a test over the generated document asserts that as an equality
    rather than a membership.

    Returns **null where the teacher set no number** [NFR14.34], so the
    client omits the destination step entirely rather than rendering a
    field with a null in it.

    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The destination, or None
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
    )


@router.post(
    "/enrollments/{enrollment_id}/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_claim(
    enrollment_id: uuid.UUID,
    body: ClaimSubmitRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> ClaimResponse:
    """Submit a payment claim against this seat's oldest unpaid cycle.

    :param enrollment_id: The seat, from the route path
    :param body: The claimed amount, channel and reference
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The pending claim
    """
    # The scope check first: a claim must not be recorded against a seat
    # this lens cannot reach.
    views.enrollment_fee_history(session, lens=lens, enrollment_id=enrollment_id)

    claim = submit_claim(
        session,
        enrollment_id=enrollment_id,
        submitted_by_account_id=lens.account_id,
        claimed_amount=parse(body.claimed_amount.root),
        channel=body.channel,
        transaction_id=body.transaction_id,
    )
    return _claim_response(views.claim_detail(session, lens=lens, claim_id=claim.id))


def queue_item_response(item: QueueItem) -> ClaimQueueItemResponse:
    """Render one waiting claim for the wire.

    :param item: The claim as the queue described it
    :return: The response body
    """
    duplicate = item.duplicate_of
    return ClaimQueueItemResponse(
        claim_id=item.claim_id,
        enrollment_id=item.enrollment_id,
        display_name=item.display_name,
        batch_name=item.batch_name,
        period=item.period,
        claimed_amount=_to_wire(item.claimed_amount),
        charged=_to_wire(item.charged),
        comparison=item.comparison,
        difference=_to_wire(item.difference),
        channel=item.channel,
        transaction_id=item.transaction_id,
        submitted_at=item.submitted_at,
        submitted_by=item.submitted_by,
        submitter_phone=item.submitter_phone,
        duplicate_of=(
            None
            if duplicate is None
            else DuplicateClaimResponse(
                claim_id=duplicate.claim_id,
                display_name=duplicate.display_name,
                status=duplicate.status,
                amount=_to_wire(duplicate.amount),
                decided_at=duplicate.decided_at,
            )
        ),
    )


# Declared before "/claims/{claim_id}": that route parses its segment as
# a uuid, so "queue" would reach it first and be refused with a 422.
@router.get(
    "/claims/queue",
    response_model=VerificationQueueResponse,
    responses=_AUTH_ERRORS,
)
def read_verification_queue(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> VerificationQueueResponse:
    """List the claims waiting for this teacher, and recent decisions (T4).

    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: Waiting claims and the last day's decisions
    """
    queue = verification_queue(session, lens=lens)
    return VerificationQueueResponse(
        pending=[queue_item_response(item) for item in queue.pending],
        decided_recently=[
            RecentDecisionResponse(
                claim_id=decision.claim_id,
                display_name=decision.display_name,
                batch_name=decision.batch_name,
                status=decision.status,
                amount=_to_wire(decision.amount),
                decided_at=decision.decided_at,
            )
            for decision in queue.decided_recently
        ],
    )


@router.post(
    "/claims/{claim_id}/shortfall",
    response_model=ShortfallPreviewResponse,
    responses=_WRITE_ERRORS,
)
def preview_shortfall(
    claim_id: uuid.UUID,
    body: ShortfallPreviewRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ShortfallPreviewResponse:
    """Say what approving an amount would leave short, before deciding.

    A read, posted only because it carries an amount: nothing is written.

    :param claim_id: The claim, from the route path
    :param body: The amount the teacher is considering
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The shortfall and whether carry-or-waive must be chosen
    """
    shortfall = shortfall_preview(
        session,
        lens=lens,
        claim_id=claim_id,
        approved_amount=parse(body.approved_amount.root),
    )
    return ShortfallPreviewResponse(
        shortfall=_to_wire(shortfall),
        disposition_required=shortfall.is_positive(),
    )


@router.get(
    "/claims/{claim_id}",
    response_model=ClaimResponse,
    responses=_AUTH_ERRORS,
)
def read_claim(
    claim_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> ClaimResponse:
    """Read one of this claimant's own claims and its outcome.

    The rejection the submitter must see [BR5.6] and the prior decision
    a correction retained [BR5.7] are both carried here.

    :param claim_id: The claim, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The claim and its decision
    """
    return _claim_response(views.claim_detail(session, lens=lens, claim_id=claim_id))


@router.post(
    "/claims/{claim_id}/verification",
    response_model=ClaimResponse,
    responses=_WRITE_ERRORS,
)
def record_verification(
    claim_id: uuid.UUID,
    body: VerificationRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ClaimResponse:
    """Approve a claim, in whole or in part [AC6.3.x].

    The shortfall is computed server-side as ``charged - approved``
    [BR5.3]; the request names the approved amount and the disposition,
    never the shortfall. A disposition is **required** where the
    approval falls below the charge and refused where it does not
    [BR5.4] -- the server decides which, because only it knows what the
    cycle was charged.

    :param claim_id: The claim, from the route path
    :param body: The approved amount and the disposition
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The decided claim
    """
    views.assert_claim_is_verifiable(session, lens=lens, claim_id=claim_id)

    outcome = verify_claim(
        session,
        claim_id=claim_id,
        approved_amount=parse(body.approved_amount.root),
        shortfall_disposition=body.shortfall_disposition,
        verified_by_account_id=lens.account_id,
        correcting=body.correcting,
    )
    return _claim_response(
        views.claim_detail(session, lens=lens, claim_id=outcome.claim.id)
    )


@router.post(
    "/claims/{claim_id}/rejection",
    response_model=ClaimResponse,
    responses=_WRITE_ERRORS,
)
def record_rejection(
    claim_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    body: RejectionRequest | None = None,
) -> ClaimResponse:
    """Reject a claim, recording nothing as received [BR5.6].

    A separate route from verification rather than an approval of zero:
    rejecting and approving nothing are different decisions, and the
    claimant is shown different things.

    :param claim_id: The claim, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :param body: Optional; carries ``correcting`` when revising
    :return: The rejected claim
    """
    views.assert_claim_is_verifiable(session, lens=lens, claim_id=claim_id)

    claim = reject_claim(
        session,
        claim_id=claim_id,
        verified_by_account_id=lens.account_id,
        correcting=body.correcting if body is not None else False,
    )
    return _claim_response(views.claim_detail(session, lens=lens, claim_id=claim.id))


@router.post(
    "/reminders",
    response_model=ReminderResponse,
    responses=_WRITE_ERRORS,
)
def send_reminders(
    body: ReminderRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> ReminderResponse:
    """Remind the people on these seats what they owe, in the app.

    Every seat must be this teacher's or nothing is sent. A seat owing
    nothing, already reminded today, or with nobody who accepted it is
    skipped and counted, not refused, so one tap over a list never
    fails on its least interesting row.

    :param body: The seats
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: How many were reminded and how many skipped
    """
    outcome = remind(session, lens=lens, enrollment_ids=body.enrollment_ids)
    return ReminderResponse(sent=outcome.sent, skipped=outcome.skipped)
