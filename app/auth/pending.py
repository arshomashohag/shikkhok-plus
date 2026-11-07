"""The signup draft: what a person typed, held until they prove the number.

**Verify first, create second** [C-07]. Signup used to create the
account, its profile, its ``Owner`` and its centre before anyone proved
they held the number, and answered an existing number with a 409. That
made the route an existence oracle -- the thing the sign-in path was
built never to be -- and let anyone squat a stranger's number with a
name, an address and a role of their choosing, which the real owner
then inherited along with every seat a teacher had recorded against it.

So the form is held here as a **draft**, keyed on the number, and an
account is created from it only when the code that went to that number
is verified (:func:`app.accounts.service.complete_signup`). Until then
nothing exists that a seat could link to and nothing reaches a lens.

**The draft is bound to one code, not to the number.** :func:`bind_code`
records which ``otp_request`` row it was issued with, and verify
completes only the draft bound to the row it just consumed. A later
signup for the same number replaces the draft and binds a new code, so
whoever submitted a draft cannot have it adopted unless the person
holding the phone types the code sent for it.

**Every signup writes one, whether or not the number has an account**,
so the request does the same work either way [BR2.7]. A draft for a
number that already has an account is never used: verify signs that
person in and :func:`discard` removes it.

Owner-private like ``profile`` -- it carries an address -- and read by
no route: the only reader is the verify path that turns it into rows.
It lives for :data:`DRAFT_LIFETIME` and is purged under its retention
class like every other short-lived auth table.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = [
    "DRAFT_LIFETIME",
    "SignupDraft",
    "bind_code",
    "discard",
    "save_draft",
    "take_bound_draft",
]

#: How long a draft can still be completed. Long enough that a person
#: who asks for a fresh code later the same day is not sent back to the
#: form; the code itself still expires on its own, much shorter, clock.
DRAFT_LIFETIME: Final = dt.timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class SignupDraft:
    """One person's signup form, as they submitted it.

    :ivar id: The id the account will carry if this draft is completed
    :ivar phone: The number the draft is for
    :ivar role: The claimed role, as the wire spells it
    :ivar self_name: The name the person chose for themselves
    :ivar address_house: House or flat
    :ivar address_road: Road or area
    :ivar address_city: City or district
    :ivar address_postcode: Four digits
    :ivar centre_name: The centre's name, for ``coaching`` only
    """

    id: uuid.UUID
    phone: str
    role: str
    self_name: str
    address_house: str
    address_road: str
    address_city: str
    address_postcode: str
    centre_name: str | None


#: One draft per number, replaced whole by a later signup. The id is
#: regenerated on every replacement, so the id a signup response reports
#: is new on every request whether or not the number has an account.
_UPSERT = sa.text(
    """
    INSERT INTO pending_signup
        (id, phone, role, self_name, address_house, address_road,
         address_city, address_postcode, centre_name, otp_request_id,
         created_at, expires_at)
    VALUES
        (:id, :phone, :role, :self_name, :address_house, :address_road,
         :address_city, :address_postcode, :centre_name, NULL,
         :created_at, :expires_at)
    ON CONFLICT (phone) DO UPDATE SET
        id = EXCLUDED.id,
        role = EXCLUDED.role,
        self_name = EXCLUDED.self_name,
        address_house = EXCLUDED.address_house,
        address_road = EXCLUDED.address_road,
        address_city = EXCLUDED.address_city,
        address_postcode = EXCLUDED.address_postcode,
        centre_name = EXCLUDED.centre_name,
        otp_request_id = NULL,
        created_at = EXCLUDED.created_at,
        expires_at = EXCLUDED.expires_at
    """
)


def save_draft(
    session: Session,
    *,
    phone: str,
    role: str,
    self_name: str,
    address_house: str,
    address_road: str,
    address_city: str,
    address_postcode: str,
    centre_name: str | None,
    now: dt.datetime,
) -> uuid.UUID:
    """Hold a signup form until its number is proved. Does not commit.

    :param session: The session to write through
    :param phone: The number the draft is for
    :param role: The claimed role, as the wire spells it
    :param self_name: The name the person chose
    :param address_house: House or flat
    :param address_road: Road or area
    :param address_city: City or district
    :param address_postcode: Four digits
    :param centre_name: The centre's name, or None
    :param now: The moment of the request
    :return: The draft's id, which the account takes if it is completed
    """
    draft_id = uuid.uuid4()
    session.execute(
        _UPSERT,
        {
            "id": draft_id,
            "phone": phone,
            "role": role,
            "self_name": self_name,
            "address_house": address_house,
            "address_road": address_road,
            "address_city": address_city,
            "address_postcode": address_postcode,
            "centre_name": centre_name,
            "created_at": now,
            "expires_at": now + DRAFT_LIFETIME,
        },
    )
    return draft_id


def bind_code(
    session: Session, *, phone: str, otp_request_id: uuid.UUID, now: dt.datetime
) -> bool:
    """Bind this number's live draft, if any, to a newly issued code.

    Run by :func:`app.auth.otp.issue` for **every** sign-in code, known
    number or not, so the statement is executed whatever the answer and
    the request does the same work [BR2.7]. Rebinding on a fresh code
    is what lets "send the code again" work after signup: the newer code
    shadows the older one at verify, so the draft must follow it.

    :param session: The session to write through
    :param phone: The number the code was issued for
    :param otp_request_id: The code's row
    :param now: The moment of issue
    :return: True when a live draft exists for this number
    """
    bound = session.execute(
        sa.text(
            "UPDATE pending_signup SET otp_request_id = :otp_request_id "
            "WHERE phone = :phone AND expires_at > :now RETURNING id"
        ),
        {"otp_request_id": otp_request_id, "phone": phone, "now": now},
    ).first()
    return bound is not None


def take_bound_draft(
    session: Session, *, otp_request_id: uuid.UUID, now: dt.datetime
) -> SignupDraft | None:
    """Return the live draft bound to one code, locking it.

    :param session: The session to read through
    :param otp_request_id: The code just verified
    :param now: The moment of verification
    :return: The draft, or None when no live draft is bound to the code
    """
    row = session.execute(
        sa.text(
            "SELECT id, phone, role, self_name, address_house, address_road, "
            "address_city, address_postcode, centre_name FROM pending_signup "
            "WHERE otp_request_id = :otp_request_id AND expires_at > :now "
            "FOR UPDATE"
        ),
        {"otp_request_id": otp_request_id, "now": now},
    ).one_or_none()
    if row is None:
        return None
    return SignupDraft(
        id=row.id,
        phone=row.phone,
        role=row.role,
        self_name=row.self_name,
        address_house=row.address_house,
        address_road=row.address_road,
        address_city=row.address_city,
        address_postcode=row.address_postcode,
        centre_name=row.centre_name,
    )


def discard(session: Session, *, phone: str) -> None:
    """Remove this number's draft, if any. Does not commit.

    :param session: The session to write through
    :param phone: The number whose draft is spent or moot
    :return: None
    """
    session.execute(
        sa.text("DELETE FROM pending_signup WHERE phone = :phone"),
        {"phone": phone},
    )
