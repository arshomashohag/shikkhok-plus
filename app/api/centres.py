"""Centre, member and membership-offer routes [0022].

Three kinds of route, each bounded differently:

* **Opening a centre** acts on the authenticated account itself, so it
  resolves no lens, on ``DELETE /v1/me``'s reasoning: an account holding
  no lens must still be able to open one.
* **The member routes** resolve the teacher lens of the workspace the
  request names, so only a manager of that centre reaches them, and they
  refuse a solo workspace, which has no members.
* **The offer routes** each resolve a :class:`MembershipLens` carrying
  the one offer they may touch; the listing above them is lens-exempt on
  ``GET /v1/invitations``'s reasoning.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import (
    authenticated_account,
    get_session,
    membership_lens,
    teacher_lens,
)
from app.authz.lenses import MembershipLens, TeacherLens
from app.centres import service
from app.centres.memberships import (
    MembershipRow,
    available_memberships,
    decide_membership,
    read_membership,
)
from app.schemas.centres import (
    CentreCreateRequest,
    CentreResponse,
    MemberInviteRequest,
    MemberResponse,
    MembershipDecisionResponse,
    MembershipResponse,
)
from app.schemas.errors import ErrorEnvelope

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["centres"])

_AUTH_ERRORS: Final[dict[int | str, dict[str, object]]] = {
    401: {"model": ErrorEnvelope, "description": "No credential, or an expired one."},
    403: {
        "model": ErrorEnvelope,
        "description": "No lens reaches this; absence reads the same.",
    },
}

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


def _member(row: service.MemberRow) -> MemberResponse:
    """Render one membership for a manager.

    :param row: The membership
    :return: The response body
    """
    return MemberResponse.model_validate(
        {
            "member_id": row.member_id,
            "display_name": row.display_name,
            "phone": row.phone,
            "role": row.role,
            "decision": row.decision,
            "invited_at": row.invited_at,
            "revoked": row.revoked,
            "is_you": row.is_you,
        }
    )


def _offer(row: MembershipRow) -> MembershipResponse:
    """Render one offer for the person invited.

    :param row: The offer
    :return: The response body
    """
    return MembershipResponse.model_validate(
        {
            "member_id": row.member_id,
            "centre_name": row.centre_name,
            "role": row.role,
            "decision": "declined" if row.decision == "declined" else "pending",
        }
    )


@router.post(
    "/centres",
    response_model=CentreResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def open_centre(
    body: CentreCreateRequest,
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> CentreResponse:
    """Open a coaching centre with the caller as its first manager.

    :param body: The centre's name and the caller's name in it
    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The new workspace
    """
    owner_id = service.create_centre(
        session,
        account_id=account_id,
        name=body.name,
        manager_name=body.manager_name,
    )
    session.commit()
    return CentreResponse(owner_id=owner_id, name=body.name.strip())


@router.get(
    "/centre/members",
    response_model=list[MemberResponse],
    responses=_WRITE_ERRORS,
)
def list_centre_members(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[MemberResponse]:
    """List the centre's members, live ones first.

    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: Every membership the centre has recorded
    """
    return [_member(row) for row in service.list_members(session, lens=lens)]


@router.post(
    "/centre/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ERRORS,
)
def invite_centre_member(
    body: MemberInviteRequest,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> MemberResponse:
    """Invite a number to the centre; nothing is granted until they accept.

    :param body: The number, name and role
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: The new, pending membership
    """
    member_id = service.invite_member(
        session,
        lens=lens,
        phone=body.phone,
        display_name=body.display_name,
        role=body.role,
    )
    for row in service.list_members(session, lens=lens):
        if row.member_id == member_id:
            return _member(row)
    raise AssertionError("an invited member is listed")  # pragma: no cover


@router.post(
    "/centre/members/{member_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def revoke_centre_member(
    member_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """End a membership; the member loses the centre on their next request.

    :param member_id: The membership
    :param lens: The manager's lens on the centre
    :param session: The request-scoped session
    :return: None
    """
    service.revoke_member(session, lens=lens, member_id=member_id)


@router.get(
    "/memberships",
    response_model=list[MembershipResponse],
    responses=_AUTH_ERRORS,
)
def list_memberships(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> list[MembershipResponse]:
    """List the centres inviting this account, unanswered or declined.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: One entry per offer, oldest first
    """
    return [
        _offer(read_membership(session, lens=lens))
        for lens in available_memberships(session, account_id)
    ]


@router.post(
    "/memberships/{member_id}/accept",
    response_model=MembershipDecisionResponse,
    responses=_AUTH_ERRORS,
)
def accept_membership(
    lens: Annotated[MembershipLens, Depends(membership_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> MembershipDecisionResponse:
    """Accept an offer, from ``pending`` or from ``declined``.

    :param lens: The membership lens carrying the one offer
    :param session: The request-scoped session
    :return: The offer and the decision
    """
    decide_membership(session, lens=lens, accept=True)
    return MembershipDecisionResponse(member_id=lens.member_id, decision="accepted")


@router.post(
    "/memberships/{member_id}/decline",
    response_model=MembershipDecisionResponse,
    responses=_AUTH_ERRORS,
)
def decline_membership(
    lens: Annotated[MembershipLens, Depends(membership_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> MembershipDecisionResponse:
    """Decline an offer; the holder may still accept it later.

    :param lens: The membership lens carrying the one offer
    :param session: The request-scoped session
    :return: The offer and the decision
    """
    decide_membership(session, lens=lens, accept=False)
    return MembershipDecisionResponse(member_id=lens.member_id, decision="declined")
