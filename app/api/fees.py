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

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.analytics.collections import DEFAULT_MONTHS
from app.api.deps import (
    family_lens,
    family_lenses,
    get_session,
    guardian_lens,
    student_lens,
    teacher_lens,
)
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Enrollment, PaymentClaim
from app.fees import views
from app.fees.decisions import approve_submission, reject_submission
from app.fees.payables import Payables, payables
from app.fees.purposes import FeeRef, Target, fees_charging_all, owed_for_target
from app.fees.queue import (
    PaymentReview,
    payment_review,
    pending_count,
    verification_queue,
)
from app.fees.received import ReceivedPayment, record_received_payment
from app.fees.reminders import remind
from app.fees.submissions import (
    PaymentDraft,
    lens_reaching,
    owed_children,
    submit_payment,
)
from app.money import Money as DomainMoney
from app.money.wire import parse, to_wire
from app.schemas.errors import ErrorEnvelope
from app.schemas.extra_fees import ExtraFeeRefResponse, PaymentPurpose
from app.schemas.fees import (
    BatchFeesResponse,
    ClaimResponse,
    DuplicatePaymentResponse,
    FeeCycleResponse,
    FeeHistoryResponse,
    HistoryLineResponse,
    MonthCountsResponse,
    MonthStateResponse,
    OwedChildResponse,
    OwedTogetherResponse,
    PayableResponse,
    PayablesResponse,
    PaymentApprovalRequest,
    PaymentRejectionRequest,
    PaymentReviewResponse,
    PaymentSubmitRequest,
    PaymentSubmittedResponse,
    ReceivedPaymentRequest,
    RecentDecisionResponse,
    ReminderRequest,
    ReminderResponse,
    ReviewChildResponse,
    RosterFeeRowResponse,
    SubmittedClaimResponse,
    VerificationQueueCountResponse,
    VerificationQueueResponse,
    WaitingPaymentResponse,
)
from app.schemas.money import Money as WireMoney
from app.schemas.payment_methods import PaymentDestinationResponse

__all__ = [
    "claim_response",
    "payables_response",
    "payment_review_response",
    "router",
]

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


def claim_response(detail: views.ClaimDetail) -> ClaimResponse:
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
        decision_note=detail.decision_note,
        previous_decision=(
            None
            if previous is None
            else {
                key: None if value is None else str(value)
                for key, value in previous.items()
            }
        ),
    )


def _history_line(line: views.HistoryLine | None) -> HistoryLineResponse | None:
    """Render a month's latest claim for the wire.

    :param line: The claim as the view described it, or None
    :return: The response body, or None
    """
    if line is None:
        return None
    return HistoryLineResponse(
        amount=_to_wire(line.amount),
        channel=line.channel,
        paid_on=line.paid_on,
        status=line.status,
        decision_note=line.decision_note,
        covered_names=list(line.covered_names),
    )


def _history_response(history: views.FeeHistory) -> FeeHistoryResponse:
    """Render one seat's periods and strip for the wire.

    :param history: The history as the view described it
    :return: The response body
    """
    return FeeHistoryResponse(
        cycles=[_cycle_response(row) for row in history.cycles],
        total_outstanding=_to_wire(history.total_outstanding),
        month_states=[
            MonthStateResponse(
                period=row.period,
                state=row.state,
                history_line=_history_line(row.history_line),
            )
            for row in history.month_states
        ],
    )


@router.get(
    "/batches/{batch_id}/fees",
    response_model=BatchFeesResponse,
    responses=_AUTH_ERRORS,
)
def read_batch_fees(
    batch_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    period: Annotated[str | None, Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")] = None,
) -> BatchFeesResponse:
    """Read one of this teacher's batches in one month.

    :param batch_id: The batch, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens carrying the owner id
    :param period: The month as ``YYYY-MM``; the current month by default
    :return: The month's totals, filter counts and one row per seat
    """
    month = views.batch_month(session, lens=lens, batch_id=batch_id, period=period)
    return BatchFeesResponse(
        period=month.period,
        collected=_to_wire(month.collected),
        charged=_to_wire(month.charged),
        counts=MonthCountsResponse(
            paid=month.counts.paid,
            checking=month.counts.checking,
            owed=month.counts.owed,
        ),
        seats=[
            RosterFeeRowResponse(
                enrollment_id=row.enrollment_id,
                display_name=row.display_name,
                outstanding=_to_wire(row.outstanding),
                current_period=row.current_period,
                current_status=row.current_status,
                due_date=row.due_date,
                days_overdue=row.days_overdue,
                verifying=_optional_wire(row.verifying),
                state=row.state,
                history_line=_history_line(row.history_line),
            )
            for row in month.seats
        ],
    )


@router.get(
    "/enrollments/{enrollment_id}/fees",
    response_model=FeeHistoryResponse,
    responses=_AUTH_ERRORS,
)
def read_enrollment_fees_as_teacher(
    enrollment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    months: Annotated[int, Query()] = DEFAULT_MONTHS,
) -> FeeHistoryResponse:
    """List one seat's generated periods and last months, for its teacher.

    :param enrollment_id: The seat, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :param months: How many months the strip covers, clamped to 1 to 24
    :return: One row per generated period and the month strip
    """
    return _history_response(
        views.enrollment_fee_history(
            session, lens=lens, enrollment_id=enrollment_id, months=months
        )
    )


@router.post(
    "/enrollments/{enrollment_id}/payments",
    response_model=PaymentReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def record_payment_received(
    enrollment_id: uuid.UUID,
    body: ReceivedPaymentRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> PaymentReviewResponse:
    """Record money this teacher received by hand for one seat.

    Recorded as a payment the teacher submitted and approved in one
    transaction, so balances, history and analytics read it as they
    read an approved family payment. A resend under the same
    ``client_mutation_id`` returns the original with the same 201.

    :param enrollment_id: The seat, from the route path
    :param body: The amount, channel, reference, note, date and the
        carry-or-waive when short
    :param session: The request-scoped session
    :param lens: The teacher lens; only the batch's owner reaches the seat
    :return: The recorded payment, as the teacher reviews it
    """
    submission = record_received_payment(
        session,
        lens=lens,
        enrollment_id=enrollment_id,
        payment=ReceivedPayment(
            amount=parse(body.amount.root),
            channel=body.channel,
            reference=body.reference,
            note=body.note,
            paid_on=body.paid_on,
            shortfall_disposition=body.shortfall_disposition,
            client_mutation_id=body.client_mutation_id,
            purpose=body.purpose,
            extra_fee_id=body.extra_fee_id,
        ),
    )
    return payment_review_response(
        payment_review(session, lens=lens, submission_id=submission.id)
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
    return _history_response(history)


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
    return _history_response(history)


@router.get(
    "/me/payables",
    response_model=PayablesResponse,
    responses=_AUTH_ERRORS,
)
def read_payables(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens, Depends(student_lens)],
) -> PayablesResponse:
    """List what this student can pay for now, and what is being checked (S3).

    :param session: The request-scoped session
    :param lens: The student lens
    :return: The payable months and the waiting seats
    """
    return payables_response(payables(session, lens=lens))


def payables_response(found: Payables) -> PayablesResponse:
    """Render what can be paid, and what is waiting, for the wire.

    :param found: The payables
    :return: The response body
    """
    return PayablesResponse(
        payable=[
            PayableResponse(
                enrollment_id=row.enrollment_id,
                batch_name=row.batch_name,
                period=row.period,
                amount_due=_to_wire(row.amount_due),
                due_date=row.due_date,
                total_due=_to_wire(row.total_due),
                later_periods=row.later_periods,
                days_late=row.days_late,
            )
            for row in found.payable
        ],
        waiting=[
            WaitingPaymentResponse(
                batch_name=row.batch_name,
                period=row.period,
                amount=_to_wire(row.amount),
                channel=row.channel,
                submitted_at=row.submitted_at,
            )
            for row in found.waiting
        ],
    )


@router.post(
    "/payments",
    response_model=PaymentSubmittedResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def create_payment(
    body: PaymentSubmitRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens | GuardianLens, Depends(family_lens)],
) -> PaymentSubmittedResponse:
    """Report one payment for one or several children (F3, F4).

    Accepted when nothing is owed: each claim then lands on Bangladesh's
    current period.

    :param body: The children, destination, amount, date and reference
    :param request: The request carrying the lens memo
    :param session: The request-scoped session
    :param lens: The authenticated family lens
    :return: The pending submission and each child's share
    """
    chosen = lens_reaching(
        session,
        family_lenses(request, session, lens.account_id),
        body.enrollment_ids[0],
    )
    submission = submit_payment(
        session,
        lens=chosen,
        draft=PaymentDraft(
            enrollment_ids=tuple(body.enrollment_ids),
            payment_method_id=body.payment_method_id,
            cash=body.cash,
            amount=parse(body.amount.root),
            paid_on=body.paid_on,
            transaction_id=body.transaction_id,
            from_account=body.from_account,
            note=body.note,
            client_mutation_id=body.client_mutation_id,
            purpose=body.purpose,
            extra_fee_id=body.extra_fee_id,
        ),
    )
    # A replay returns the ORIGINAL submission with the same 201, so the
    # body below is built from what is stored, never from the request --
    # and the status is the stored one, because a late resend after the
    # teacher decided must not be told the payment still waits.
    shares = session.execute(
        sa.select(PaymentClaim, Enrollment.display_name)
        .join(Enrollment, Enrollment.id == PaymentClaim.enrollment_id)
        .where(PaymentClaim.payment_submission_id == submission.id)
        .order_by(Enrollment.display_name, Enrollment.id)
    ).all()
    return PaymentSubmittedResponse(
        submission_id=submission.id,
        status=views.submission_status(submission.status),
        total_amount=_to_wire(submission.total_amount),
        paid_on=submission.paid_on,
        claims=[
            SubmittedClaimResponse(
                claim_id=claim.id,
                enrollment_id=claim.enrollment_id,
                display_name=name,
                period=claim.period,
                claimed_amount=_to_wire(claim.claimed_amount),
            )
            for claim, name in shares
        ],
    )


@router.get(
    "/payments/owed",
    response_model=OwedTogetherResponse,
    responses=_WRITE_ERRORS,
)
def read_owed_together(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[StudentLens | GuardianLens, Depends(family_lens)],
    enrollment_id: Annotated[list[uuid.UUID], Query(min_length=1, max_length=20)],
    extra_fee_id: uuid.UUID | None = None,
) -> OwedTogetherResponse:
    """Say what the chosen children owe together, for "Owed for ...".

    :param request: The request carrying the lens memo
    :param session: The request-scoped session
    :param lens: The authenticated family lens
    :param enrollment_id: The children, repeated once per child
    :param extra_fee_id: Ask about one extra fee rather than the months
    :return: The total and each child's figure, in child order
    """
    chosen = lens_reaching(
        session, family_lenses(request, session, lens.account_id), enrollment_id[0]
    )
    children = owed_children(
        session,
        lens=chosen,
        enrollment_ids=enrollment_id,
        purpose=None if extra_fee_id is None else "extra",
        extra_fee_id=extra_fee_id,
    )
    seats = [child.seat.id for child in children]
    options = [
        ref
        for ref in fees_charging_all(
            session, batch_id=children[0].seat.batch_id, enrollment_ids=seats
        )
        if DomainMoney.sum(
            [
                owed_for_target(
                    session,
                    target=Target(purpose="extra", extra_fee_id=ref.extra_fee_id),
                    enrollment_id=seat,
                )
                for seat in seats
            ]
        ).is_positive()
    ]
    return OwedTogetherResponse(
        extra_fee_options=[
            wire for wire in (_fee_ref(ref) for ref in options) if wire is not None
        ],
        owed_together=_to_wire(DomainMoney.sum([child.owed for child in children])),
        children=[
            OwedChildResponse(
                enrollment_id=child.seat.id,
                display_name=child.seat.display_name,
                owed=_to_wire(child.owed),
            )
            for child in children
        ],
    )


def _fee_ref(ref: FeeRef | None) -> ExtraFeeRefResponse | None:
    """Render an extra fee as a payment names it.

    :param ref: The fee, or None for the monthly fee
    :return: The wire shape, or None
    """
    if ref is None:
        return None
    return ExtraFeeRefResponse(
        extra_fee_id=ref.extra_fee_id,
        purpose="exam" if ref.purpose == "exam" else "other",
        label=ref.label,
        due_on=ref.due_on,
    )


def payment_review_response(review: PaymentReview) -> PaymentReviewResponse:
    """Render one payment's review for the wire.

    :param review: The payment as the review described it
    :return: The response body
    """
    duplicate = review.duplicate_of
    return PaymentReviewResponse(
        submission_id=review.submission_id,
        batch_name=review.batch_name,
        children=[
            ReviewChildResponse(
                claim_id=child.claim_id,
                enrollment_id=child.enrollment_id,
                display_name=child.display_name,
                period=child.period,
                owed=_to_wire(child.owed),
                approved_amount=_optional_wire(child.approved_amount),
            )
            for child in review.children
        ],
        owed_together=_to_wire(review.owed_together),
        total_amount=_to_wire(review.total_amount),
        comparison=review.comparison,
        difference=_to_wire(review.difference),
        method=PaymentDestinationResponse.model_validate(review.method),
        transaction_id=review.transaction_id,
        from_account=review.from_account,
        paid_on=review.paid_on,
        submitted_at=review.submitted_at,
        submitted_by=review.submitted_by,
        submitter_phone=review.submitter_phone,
        payer_note=review.payer_note,
        status=review.status,
        decision_note=review.decision_note,
        decided_at=review.decided_at,
        duplicate_of=(
            None
            if duplicate is None
            else DuplicatePaymentResponse(
                submission_id=duplicate.submission_id,
                display_name=duplicate.display_name,
                status=duplicate.status,
                amount=_to_wire(duplicate.amount),
                decided_at=duplicate.decided_at,
            )
        ),
        purpose=review.purpose,
        extra_fee=_fee_ref(review.extra_fee),
        requested_purpose=review.requested_purpose,
        requested_extra_fee=_fee_ref(review.requested_extra_fee),
        extra_fee_options=[
            ref
            for ref in (_fee_ref(option) for option in review.extra_fee_options)
            if ref is not None
        ],
    )


@router.get(
    "/payments/{submission_id}",
    response_model=PaymentReviewResponse,
    responses=_AUTH_ERRORS,
)
def read_payment(
    submission_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    purpose: PaymentPurpose | None = None,
    extra_fee_id: uuid.UUID | None = None,
) -> PaymentReviewResponse:
    """Read one payment on this teacher's batches (R2).

    ``purpose`` (with ``extra_fee_id``) previews the payment against
    something else it could be applied to, writing nothing.

    :param submission_id: The submission, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :param purpose: Preview against ``monthly`` or ``extra``
    :param extra_fee_id: The fee, when previewing ``extra``
    :return: The payment as the teacher reviews it
    """
    return payment_review_response(
        payment_review(
            session,
            lens=lens,
            submission_id=submission_id,
            preview_purpose=purpose,
            preview_extra_fee_id=extra_fee_id,
        )
    )


@router.post(
    "/payments/{submission_id}/approval",
    response_model=PaymentReviewResponse,
    responses=_WRITE_ERRORS,
)
def approve_payment(
    submission_id: uuid.UUID,
    body: PaymentApprovalRequest,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> PaymentReviewResponse:
    """Approve a payment, split across its children (R4).

    :param submission_id: The submission, from the route path
    :param body: What was received and how a shortfall or excess goes
    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: The decided payment
    """
    approve_submission(
        session,
        lens=lens,
        submission_id=submission_id,
        received=parse(body.received_amount.root),
        disposition=body.shortfall_disposition,
        carried_by_enrollment_id=body.carried_by_enrollment_id,
        credit_to_enrollment_id=body.credit_to_enrollment_id,
        note=body.note,
        correcting=body.correcting,
        purpose=body.purpose,
        extra_fee_id=body.extra_fee_id,
    )
    return payment_review_response(
        payment_review(session, lens=lens, submission_id=submission_id)
    )


@router.post(
    "/payments/{submission_id}/rejection",
    response_model=PaymentReviewResponse,
    responses=_WRITE_ERRORS,
)
def reject_payment(
    submission_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    body: PaymentRejectionRequest | None = None,
) -> PaymentReviewResponse:
    """Reject a payment, recording nothing as received [BR5.6].

    :param submission_id: The submission, from the route path
    :param session: The request-scoped session
    :param lens: The teacher lens
    :param body: Optional; the note and ``correcting`` when revising
    :return: The decided payment
    """
    reject_submission(
        session,
        lens=lens,
        submission_id=submission_id,
        note=body.note if body is not None else None,
        correcting=body.correcting if body is not None else False,
    )
    return payment_review_response(
        payment_review(session, lens=lens, submission_id=submission_id)
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
    """List the payments waiting for this teacher, and recent decisions (R1).

    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: Waiting payments and the last day's decisions
    """
    queue = verification_queue(session, lens=lens)
    return VerificationQueueResponse(
        pending=[payment_review_response(item) for item in queue.pending],
        decided_recently=[
            RecentDecisionResponse(
                submission_id=decision.submission_id,
                display_name=decision.display_name,
                batch_name=decision.batch_name,
                status=decision.status,
                amount=_to_wire(decision.amount),
                decided_at=decision.decided_at,
            )
            for decision in queue.decided_recently
        ],
    )


@router.get(
    "/claims/queue/count",
    response_model=VerificationQueueCountResponse,
    responses=_AUTH_ERRORS,
)
def read_verification_queue_count(
    session: Annotated[Session, Depends(get_session)],
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
) -> VerificationQueueCountResponse:
    """Count the payments waiting for this teacher, for the nav badge.

    One statement, building no review: the badge needs the length of
    ``GET /claims/queue``'s ``pending`` list and nothing else [C-13].

    :param session: The request-scoped session
    :param lens: The teacher lens
    :return: How many wait to be checked
    """
    return VerificationQueueCountResponse(pending=pending_count(session, lens=lens))


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

    The rejection the submitter must see [BR5.6], with the teacher's
    note, and the prior decision a correction retained [BR5.7] are both
    carried here.

    :param claim_id: The claim, from the route path
    :param session: The request-scoped session
    :param lens: The student lens
    :return: The claim and its decision
    """
    return claim_response(views.claim_detail(session, lens=lens, claim_id=claim_id))


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
