"""Two-step verification settings: the account's own authenticator factor.

**Authenticated, and lens-exempt on ``GET /v1/me``'s reasoning.** Every
route acts on the authenticated account's own factor and reads nothing
another account owns, so a lens would scope nothing -- and requiring one
would stop a person who holds none from protecting their own account.
All five are in ``LENS_EXEMPT_AUTHENTICATED`` with that justification.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.accounts import mfa
from app.api.auth import correlation_of
from app.api.deps import authenticated_account, get_session
from app.schemas.mfa import (
    MfaCodeRequest,
    MfaProofRequest,
    MfaRecoveryCodesResponse,
    MfaSetupResponse,
    MfaStatusResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/v1/me/mfa", tags=["mfa"])


def _status(session: Session, account_id: uuid.UUID) -> MfaStatusResponse:
    """Present the account's status.

    :param session: The session to read through
    :param account_id: The account
    :return: The response
    """
    found = mfa.status(session, account_id)
    return MfaStatusResponse(
        enabled=found.enabled,
        enabled_at=found.enabled_at,
        recovery_codes_left=found.recovery_codes_left,
        recommended=found.recommended,
        required=found.required,
    )


@router.get("", response_model=MfaStatusResponse)
def read_status(
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MfaStatusResponse:
    """Say whether two-step verification is on, and whether to suggest it.

    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The status
    """
    return _status(session, account_id)


@router.post("/setup", response_model=MfaSetupResponse)
def begin_setup(
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MfaSetupResponse:
    """Start turning it on: a new secret for an authenticator app.

    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The secret and its ``otpauth://`` URI
    """
    secret, uri = mfa.setup(session, account_id)
    session.commit()
    return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/confirm", response_model=MfaRecoveryCodesResponse)
def finish_setup(
    body: MfaCodeRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MfaRecoveryCodesResponse:
    """Turn it on with the first code the app shows.

    :param body: The code
    :param request: The incoming request
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: Ten recovery codes, shown once
    """
    codes = mfa.confirm(session, account_id, body.code, correlation_of(request))
    session.commit()
    return MfaRecoveryCodesResponse(recovery_codes=codes)


@router.post("/disable", response_model=MfaStatusResponse)
def turn_off(
    body: MfaProofRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MfaStatusResponse:
    """Turn it off, proven with an authenticator or recovery code.

    :param body: One of the two codes
    :param request: The incoming request
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: The new status
    """
    mfa.disable(
        session, account_id, body.code, body.recovery_code, correlation_of(request)
    )
    session.commit()
    return _status(session, account_id)


@router.post("/recovery-codes", response_model=MfaRecoveryCodesResponse)
def renew_codes(
    body: MfaCodeRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
) -> MfaRecoveryCodesResponse:
    """Replace the recovery codes, proven with an authenticator code.

    :param body: The code
    :param request: The incoming request
    :param session: The request-scoped session
    :param account_id: The authenticated account
    :return: Ten new codes; the old ones stop working
    """
    codes = mfa.renew_recovery_codes(
        session, account_id, body.code, correlation_of(request)
    )
    session.commit()
    return MfaRecoveryCodesResponse(recovery_codes=codes)
