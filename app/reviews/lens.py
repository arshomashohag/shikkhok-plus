"""The reviewer lens: reach for one batch's review, as its author or a member.

A :class:`~app.authz.lenses.Lens` subtype, so the route-enumeration gate
finds the dependency returning it by its return annotation, like every
other lens. It carries the batch and the assessment the handler needs, so a
handler cannot act on a batch other than the one the lens was resolved for,
and cannot write without having the standing in hand.

There is no role field and nothing cached: the lens is resolved per request
from :func:`app.reviews.eligibility.assess`, from the path's batch id and the
authenticated account, never from a client-supplied hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.authz.lenses import Lens
from app.reviews.eligibility import Assessment

__all__ = ["ReviewerLens"]


@dataclass(frozen=True, slots=True)
class ReviewerLens(Lens):
    """Reach for one batch's review by one account [spec §6, Call 7].

    Granted to a **member** (spec conditions 1-3), whatever their standing,
    or to the **author** of a review of the batch who is no longer a member.
    Writing a new review needs ``assessment.standing == "eligible"``; that is
    the write path's check, not the lens's.

    :ivar batch_id: The one batch this lens reaches, from the route path
    :ivar assessment: Where the account stands with that batch
    """

    batch_id: UUID
    assessment: Assessment
