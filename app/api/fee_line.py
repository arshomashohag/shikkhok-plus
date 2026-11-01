"""The fee line a family reader sees for one seat's latest period.

One function, so the student's batch list and both family batch views
(``/me/batches/{id}/teaching`` and ``/children/{id}/teaching``) render the
same server decision: whether a payment is being verified, and the day the
period was paid [TC-9]. A guardian's header built from the cycle list on
the phone showed Pay while a claim was pending, which is the client
deciding a business rule.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens
from app.db.models import PaymentClaim
from app.fees.views import enrollment_fee_history
from app.local_time import DHAKA
from app.money.wire import to_wire
from app.schemas.fees import CurrentFeeResponse
from app.schemas.money import Money as WireMoney

__all__ = ["current_fee"]


def current_fee(
    session: Session,
    lens: StudentLens | GuardianLens,
    enrollment_id: uuid.UUID,
) -> CurrentFeeResponse | None:
    """Read the seat's latest fee period through the fee module's rules.

    :param session: The session to read through
    :param lens: The student or guardian lens, which the fee read
        re-authorizes
    :param enrollment_id: The seat
    :return: The latest period, or None before the first is generated
    :raises AuthorizationError: The lens does not reach the seat's fees
    """
    history = enrollment_fee_history(session, lens=lens, enrollment_id=enrollment_id)
    if not history.cycles:
        return None
    latest = history.cycles[-1]
    claims = session.execute(
        sa.select(PaymentClaim.status, PaymentClaim.verified_at).where(
            PaymentClaim.enrollment_id == enrollment_id,
            PaymentClaim.period == latest.period,
        )
    ).all()
    approvals = [
        when for status, when in claims if status.startswith("approved") and when
    ]
    return CurrentFeeResponse(
        period=latest.period,
        status=latest.status,
        due_date=latest.due_date,
        outstanding=WireMoney(to_wire(latest.outstanding)),
        charged=WireMoney(to_wire(latest.charged)),
        verifying=any(status == "pending" for status, _ in claims),
        paid_on=max(approvals).astimezone(DHAKA).date() if approvals else None,
    )
