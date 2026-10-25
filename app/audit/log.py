"""Append-only, a closed event set, and no free-form field.

**An audit log that leaks what it audits is a common and self-defeating
mistake** [BR6.2]. The correlation id ties a row back to a request
*without carrying its contents*, and there is no ``message``, ``detail``
or ``note`` column -- because a free-form string is where a phone number
eventually lands, added by someone debugging in good faith.

A test asserts the dataclass has no ``str`` field but ``correlation_id``.
That is a stronger guarantee than a review comment, and it is the
mechanism rather than the intent.

**This component fails open**: it must not fail the authentication it was
recording. That makes it suppressible by causing write failures, which
would be a real weakness if it were silent -- so the failure is **silent
to the user and loud to the operator**. That resolution only works if the
alert exists, which is why it is one of the six things that reach a
human.
"""

from __future__ import annotations

import datetime as dt
import enum
import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = ["AuthEvent", "write_audit"]

_log = logging.getLogger(__name__)


class AuthEvent(enum.Enum):
    """The closed set of auditable authentication events.

    Closed deliberately: an open vocabulary is how a free-form value
    re-enters a log that is specified not to have one.

    **D1 extends it with NAMED MEMBERS and adds no field** [NFR12.7,
    NFR12.9, NFR12.10]. The obvious alternative -- one
    ``SIGNUP_EVENT`` member plus a ``detail`` column saying which --
    is the free-form string this log is specified not to have, arriving
    through the one door still open. Account creation belongs here on
    its merits: it is rate-limited, unauthenticated, and the place an
    enumeration attempt would surface.

    ``SIGNUP_CEILING_BREACHED`` records the breach and **not its scope
    value**, which is a phone number or an IP prefix [NFR12.10]. The
    scope KIND is operator-useful and reaches the logs through
    :func:`~app.auth.ceilings.fire_ceiling_alert`; neither reaches this
    table, which holds no content by design.
    """

    OTP_ISSUED = "OTP_ISSUED"
    VERIFY_FAILED = "VERIFY_FAILED"
    VERIFY_SUCCEEDED = "VERIFY_SUCCEEDED"
    REFRESH_ROTATED = "REFRESH_ROTATED"
    REFRESH_REUSE_DETECTED = "REFRESH_REUSE_DETECTED"
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    SIGNUP_CEILING_BREACHED = "SIGNUP_CEILING_BREACHED"


def write_audit(
    session: Session,
    account_id: uuid.UUID | None,
    event: AuthEvent,
    correlation_id: str,
    occurred_at: dt.datetime | None = None,
) -> None:
    """Append one audit row.

    ``account_id`` is **nullable**: an OTP issued for an unknown number
    has no account, and recording a placeholder would reintroduce the
    existence oracle the issue path exists to close [BR2.7].

    :param session: The session to write through
    :param account_id: The account, or None for an unknown number
    :param event: Which member of the closed vocabulary occurred
    :param correlation_id: Ties the row to a request, carrying no content
    :param occurred_at: When it happened, or None for the clock
    :return: None
    """
    moment = occurred_at or dt.datetime.now(tz=dt.UTC)

    # THE SAVEPOINT IS LOAD-BEARING, and catching the exception alone is
    # not enough -- which is how the first version of this function was
    # wrong.
    #
    # PostgreSQL aborts the ENTIRE transaction on any failed statement.
    # Swallowing the error leaves the caller holding an aborted
    # transaction whose later `commit()` issues a ROLLBACK and **returns
    # normally**. The caller sees success and loses its own writes.
    #
    # Measured against a live container: with the audit INSERT failing,
    # `otp.issue` returned a code, sent it, and committed nothing -- so
    # the user received an SMS whose code could never verify, having
    # already consumed a ceiling slot that brings them closer to
    # lockout. That is the fail-open guarantee INVERTED: the log did not
    # merely fail to record the authentication, it destroyed it.
    #
    # A nested transaction confines the abort to the savepoint, so a
    # rollback here leaves the caller's work intact and committable.
    savepoint = session.begin_nested()
    try:
        session.execute(
            sa.text(
                "INSERT INTO auth_audit_log "
                "(id, account_id, event, occurred_at, correlation_id) "
                "VALUES (:id, :account_id, :event, :occurred_at, "
                ":correlation_id)"
            ),
            {
                "id": uuid.uuid4(),
                "account_id": account_id,
                "event": event.value,
                "occurred_at": moment,
                "correlation_id": correlation_id,
            },
        )
        savepoint.commit()
    except sa.exc.SQLAlchemyError:
        savepoint.rollback()
        # Fails OPEN: the authentication must not fail because its
        # record did. Loud to the operator, silent to the user -- and
        # the alert on this line is what stops the log being
        # suppressible without anyone noticing.
        _log.critical(
            "audit write failed",
            extra={"correlation_id": correlation_id, "event": event.value},
        )
