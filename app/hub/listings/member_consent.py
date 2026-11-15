"""A centre member's own consent to be named on the centre's public page."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import CentreMemberLens

__all__ = ["set_public_name_consent"]


def set_public_name_consent(
    session: Session, lens: CentreMemberLens, consent: bool, now: dt.datetime
) -> None:
    """Record or withdraw the member's consent to be named publicly.

    The row is the lens's own membership; nothing here takes an id from the
    request body.

    :param session: The session
    :param lens: The caller's lens on their own membership
    :param consent: True to agree, False to withdraw
    :param now: The moment of agreement
    :return: None
    """
    session.execute(
        sa.text("UPDATE owner_member SET public_name_consent_at = :at WHERE id = :id"),
        {"at": now if consent else None, "id": lens.member_id},
    )
    session.commit()
