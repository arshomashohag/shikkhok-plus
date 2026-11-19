"""Hub join requests: the guardian's routes and the owner's [H5].

**Who reaches what.** The guardian's four routes act as the authenticated
account alone and are lens-exempt (``LENS_EXEMPT_AUTHENTICATED`` gives the
reasoning): a guardian asking to join holds no lens on that owner yet. The
target and the send are bounded by
:func:`app.hub.enquiries.target.resolve`, one SQL statement that reaches
only a published owner accepting requests, never one the caller runs; the
list and the withdrawal are scoped by account id in SQL. The owner's three
``/v1/hub/enquiries`` routes resolve the owner's
:class:`~app.authz.lenses.TeacherLens`, which a centre's class teacher, a
student and a guardian do not hold.

**The switch runs first** (global constraints, the off table). Each gated
route lists :func:`~app.hub.enquiries.switch.require_enquiries_on` in its
decorator, which FastAPI resolves before any parameter dependency, so an
off switch answers ``HUB_ENQUIRIES_OFF`` to everyone alike and never a
target, ownership or lens refusal. The switch never gates the guardian's
own list or their withdrawal.

**Nothing is read before** ``resolve`` on the target and the send, so every
target the caller may not ask answers the same bytes as a slug that never
existed (Review Focus 2). The slug is taken as given, with no pattern: a
malformed slug is one more slug that never existed, not a 422.

**Transactions.** Each write service commits on success and rolls back on
any exception, taxonomy or not, and the request scope rolls back every 4xx
and 5xx besides; ``test_write_routes_roll_back_on_an_unexpected_error``
holds all three writes to it.

**Nothing here logs.** ``student_name``, ``message`` and the guardian's
contact are never logged, so no line can pair them with a correlation id.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import authenticated_account, get_session, teacher_lens
from app.authz.lenses import TeacherLens
from app.hub.enquiries import owner, sending
from app.hub.enquiries.owner import OwnerEnquiry
from app.hub.enquiries.sending import MyEnquiry
from app.hub.enquiries.switch import (
    ENQUIRIES_OFF_RESPONSES,
    enquiries_off_responses,
    require_enquiries_on,
)
from app.schemas.enquiries import (
    EnquiryClose,
    EnquiryTargetResponse,
    EnquiryWrite,
    MyEnquiryWire,
    OwnerEnquiryWire,
)
from app.schemas.errors import ErrorEnvelope

__all__ = ["router"]

router = APIRouter(prefix="/v1", tags=["hub"])

#: The owner's public path, under which a guardian asks.
_OWNER: Final = "/hub/owners/{owner_slug}"

#: The guardian's own requests.
_MINE: Final = "/me/hub/enquiries"

#: The owner's requests.
_INBOX: Final = "/hub/enquiries"

_Responses = dict[int | str, dict[str, object]]


def _envelope(description: str) -> dict[str, object]:
    """Document one error status as the error envelope.

    :param description: What the status means here, naming its codes
    :return: The OpenAPI response entry
    """
    return {"model": ErrorEnvelope, "description": description}


_UNAUTHENTICATED: Final = _envelope("No credential, or an expired one.")

_NO_TEACHER: Final = _envelope(
    "NO_TEACHER_LENS: the caller runs no workspace, or not the one named."
)

#: The second 404 of the target and the send.
_TARGET_NOT_FOUND: Final = (
    "ENQUIRY_TARGET_NOT_FOUND: no published listing accepting requests by "
    "that slug, no open listed batch of it by that id, or a listing the "
    "caller runs; a slug that never existed answers the same."
)

#: The second 404 of the owner's read and close.
_NOT_FOUND: Final = (
    "ENQUIRY_NOT_FOUND: no request of this owner's by that id; another "
    "owner's request answers the same."
)

#: The form's read of a target.
_TARGET_ERRORS: Final[_Responses] = {
    401: _UNAUTHENTICATED,
    **enquiries_off_responses(_TARGET_NOT_FOUND),
}

#: The send.
_SEND_ERRORS: Final[_Responses] = {
    400: _envelope(
        "ENQUIRY_CONTAINS_CONTACT: the student's name or the message carries "
        "a phone number or a web address; details name the field."
    ),
    401: _UNAUTHENTICATED,
    **enquiries_off_responses(_TARGET_NOT_FOUND),
    409: _envelope(
        "ENQUIRY_ALREADY_OPEN: the caller already has a request open with "
        "this owner. HUB_ENQUIRY_CEILING: today's requests are spent."
    ),
}

#: The guardian's own list and withdrawal: authentication only.
_MINE_ERRORS: Final[_Responses] = {401: _UNAUTHENTICATED}

#: The owner's list.
_LIST_ERRORS: Final[_Responses] = {
    401: _UNAUTHENTICATED,
    403: _NO_TEACHER,
    **ENQUIRIES_OFF_RESPONSES,
}

#: The owner's read of one.
_ONE_ERRORS: Final[_Responses] = {
    401: _UNAUTHENTICATED,
    403: _NO_TEACHER,
    **enquiries_off_responses(_NOT_FOUND),
}

#: The owner's answer.
_CLOSE_ERRORS: Final[_Responses] = {
    400: _envelope(
        "ENQUIRY_OUTCOME_INVALID: an outcome not in the request's outcomes_allowed."
    ),
    401: _UNAUTHENTICATED,
    403: _NO_TEACHER,
    **enquiries_off_responses(_NOT_FOUND),
    409: _envelope("ENQUIRY_ALREADY_CLOSED: the request was already answered."),
}


def _mine(enquiry: MyEnquiry) -> MyEnquiryWire:
    """Render one of the guardian's own requests.

    :param enquiry: The request
    :return: The wire body
    """
    return MyEnquiryWire.model_validate(dataclasses.asdict(enquiry))


def _owners(enquiry: OwnerEnquiry) -> OwnerEnquiryWire:
    """Render one request for the people who run the listing.

    :param enquiry: The request
    :return: The wire body
    """
    return OwnerEnquiryWire.model_validate(dataclasses.asdict(enquiry))


def _now() -> dt.datetime:
    """Give the present.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


@router.get(
    f"{_OWNER}/enquiry-target",
    response_model=EnquiryTargetResponse,
    responses=_TARGET_ERRORS,
    dependencies=[Depends(require_enquiries_on)],
)
def get_enquiry_target(
    owner_slug: str,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    batch_id: uuid.UUID | None = None,
) -> EnquiryTargetResponse:
    """Say who a request would reach and what "share" would share.

    Informed consent needs the name of whoever would receive the contact.

    :param owner_slug: The owner's public slug
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :param batch_id: The listed batch asked about, if any
    :return: The target as the form shows it
    """
    found = sending.describe(session, account_id, owner_slug, batch_id)
    return EnquiryTargetResponse.model_validate(dataclasses.asdict(found))


@router.post(
    f"{_OWNER}/enquiries",
    status_code=status.HTTP_201_CREATED,
    response_model=MyEnquiryWire,
    responses=_SEND_ERRORS,
    dependencies=[Depends(require_enquiries_on)],
)
def send_enquiry(
    owner_slug: str,
    body: EnquiryWrite,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MyEnquiryWire:
    """Ask an owner, or one of its batches, to take a student.

    The people who run the listing are told a request arrived, and nothing
    the guardian typed travels with it.

    :param owner_slug: The owner's public slug
    :param body: The request; the declaration is checked and not stored
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The request as the guardian sees it
    """
    sent = sending.send(
        session,
        account_id,
        owner_slug,
        student_name=body.student_name,
        class_level=body.class_level,
        message=body.message,
        batch_id=body.batch_id,
        share_contact=body.share_contact,
        now=_now(),
    )
    return _mine(sent)


@router.get(_MINE, response_model=list[MyEnquiryWire], responses=_MINE_ERRORS)
def list_my_enquiries(
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> list[MyEnquiryWire]:
    """List the caller's own requests, newest first.

    Not switch-gated: while join requests are off a guardian can still see
    what they sent, so they can withdraw it.

    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The requests
    """
    return [_mine(enquiry) for enquiry in sending.mine(session, account_id)]


@router.delete(
    f"{_MINE}/{{enquiry_id}}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_MINE_ERRORS,
)
def withdraw_enquiry(
    enquiry_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> Response:
    """Withdraw one of the caller's requests, with every inbox item about it.

    Never switch-gated, and quiet for a missing id or another account's.

    :param enquiry_id: The request
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: An empty 204
    """
    sending.withdraw(session, account_id, enquiry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    _INBOX,
    response_model=list[OwnerEnquiryWire],
    responses=_LIST_ERRORS,
    dependencies=[Depends(require_enquiries_on)],
)
def list_owner_enquiries(
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> list[OwnerEnquiryWire]:
    """List the owner's requests, open first, then newest.

    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The requests
    """
    return [_owners(enquiry) for enquiry in owner.list_for(session, lens)]


@router.get(
    f"{_INBOX}/{{enquiry_id}}",
    response_model=OwnerEnquiryWire,
    responses=_ONE_ERRORS,
    dependencies=[Depends(require_enquiries_on)],
)
def get_owner_enquiry(
    enquiry_id: uuid.UUID,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerEnquiryWire:
    """Read one of the owner's requests.

    :param enquiry_id: The request
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The request
    """
    return _owners(owner.get(session, lens, enquiry_id))


@router.post(
    f"{_INBOX}/{{enquiry_id}}/close",
    response_model=OwnerEnquiryWire,
    responses=_CLOSE_ERRORS,
    dependencies=[Depends(require_enquiries_on)],
)
def close_owner_enquiry(
    enquiry_id: uuid.UUID,
    body: EnquiryClose,
    lens: Annotated[TeacherLens, Depends(teacher_lens)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerEnquiryWire:
    """Answer a request; its guardian is told the outcome and nothing else.

    :param enquiry_id: The request
    :param body: The outcome, one of the request's ``outcomes_allowed``
    :param lens: The owner's lens
    :param session: The request-scoped session
    :return: The closed request
    """
    return _owners(owner.close(session, lens, enquiry_id, body.outcome, _now()))
