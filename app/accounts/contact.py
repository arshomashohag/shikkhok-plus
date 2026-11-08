"""Adding a phone number or an email address an account does not have.

**Only adding, never replacing** [0032]. A phone number is what teachers
record students and guardians against, so it is permanent once set; an
email address follows the same rule so the two behave alike. A person
who signed up with one can add the other, once, proved by a code sent to
it.

**Adding a phone number links what teachers recorded against it**, by
the same function signup runs (:func:`~app.accounts.service.link_phone_seats`):
the seats and centre invitations reach an email-only student or guardian
the moment they prove the number, and not before. Proving it is the
point -- a number typed without a code would hand a stranger's child's
seats to whoever typed it.

**A destination another account holds is refused only after the code**:
the request is answered and the code sent whatever the destination, so
asking is not a way to learn who is registered. Whoever can read the
code has proved they hold it, and may be told.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.identifier import Identifier
from app.accounts.service import link_phone_seats
from app.audit.log import AuthEvent, write_audit
from app.auth import otp, pending
from app.errors import ConflictError

__all__ = ["already_has", "attach", "contact_already_set", "contact_taken"]


def contact_already_set() -> ConflictError:
    """Build the refusal for an account that already has this kind.

    :return: The error
    """
    return ConflictError(
        code="CONTACT_ALREADY_SET", message_key="account.contact.already_set"
    )


def contact_taken() -> ConflictError:
    """Build the refusal for a destination another account holds.

    :return: The error
    """
    return ConflictError(code="CONTACT_TAKEN", message_key="account.contact.taken")


def already_has(
    session: Session, account_id: uuid.UUID, identifier: Identifier
) -> bool:
    """Report whether the account already has a value of this kind.

    :param session: The session to read through
    :param account_id: The account
    :param identifier: The kind being added
    :return: True when that column is already set
    """
    return bool(
        session.execute(
            sa.text(
                f"SELECT {identifier.column} IS NOT NULL FROM account WHERE id = :a"  # noqa: S608
            ),
            {"a": account_id},
        ).scalar_one()
    )


def attach(
    session: Session,
    account_id: uuid.UUID,
    identifier: Identifier,
    code: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> None:
    """Spend the code sent to a destination and add it to the account.

    Commits on every outcome: a refused code records its attempt, and a
    destination found taken has still had its code spent.

    :param session: The session to write through
    :param account_id: The signed-in account
    :param identifier: The number or address being added
    :param code: The code sent to it
    :param correlation_id: Ties the audit rows to the request
    :param now: The moment, or None for the clock
    :return: None
    :raises CodeRefused: The code was refused
    :raises ConflictError: The account already has one, or another
        account holds this one
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    otp.consume_code(
        session,
        identifier,
        code,
        correlation_id,
        purpose=otp.CONTACT_PURPOSE,
        now=moment,
    )
    session.execute(
        sa.text("SELECT 1 FROM account WHERE id = :a FOR UPDATE"), {"a": account_id}
    )
    if already_has(session, account_id, identifier):
        session.commit()
        raise contact_already_set()
    holder = otp.account_for(session, identifier)
    if holder is not None:
        session.commit()
        raise contact_taken()

    try:
        with session.begin_nested():
            session.execute(
                sa.text(
                    f"UPDATE account SET {identifier.column} = :value WHERE id = :a"  # noqa: S608
                ),
                {"value": identifier.value, "a": account_id},
            )
    except IntegrityError as error:
        # Another account took it between the read above and this write.
        session.commit()
        raise contact_taken() from error

    if identifier.is_phone:
        link_phone_seats(session, account_id=account_id, phone=identifier.value)
    # A signup someone started for this destination is moot now.
    pending.discard(session, identifier=identifier)
    write_audit(session, account_id, AuthEvent.CONTACT_ADDED, correlation_id)
    session.commit()
