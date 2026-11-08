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
    #: A rotated-out token was re-presented inside the grace window with
    #: its successor unused, so the successor was revoked and a fresh
    #: pair issued in the same family [PA-SEC-4]. Its own member rather
    #: than REFRESH_ROTATED, so "how often do responses get lost" and
    #: "is the grace being abused" are answerable from this table.
    REFRESH_GRACE_REISSUED = "REFRESH_GRACE_REISSUED"
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    SIGNUP_CEILING_BREACHED = "SIGNUP_CEILING_BREACHED"
    #: A signup form was held as a draft and its code issued [C-07].
    #: Always written with no account -- one exists, or does not, and
    #: saying which here would be the oracle signup no longer is.
    #: ``ACCOUNT_CREATED`` follows only when the code is verified.
    SIGNUP_REQUESTED = "SIGNUP_REQUESTED"
    #: A refresh family was ended by its holder [C-21]. Its own member,
    #: not a reuse: a signed-out device is not an attack.
    LOGGED_OUT = "LOGGED_OUT"
    #: Every family of one account was ended at its holder's request.
    LOGGED_OUT_EVERYWHERE = "LOGGED_OUT_EVERYWHERE"
    #: A verify was refused because a failed-verify ceiling was full
    #: [C-20]. No scope value, on ``SIGNUP_CEILING_BREACHED``'s
    #: reasoning: the value is an IP prefix.
    VERIFY_CEILING_BREACHED = "VERIFY_CEILING_BREACHED"
    # Platform administrator sign-in [0028], named members as D1's were.
    # Every admin session starts with one of these, so who reached the
    # admin surface, and when, is answerable from this table alone.
    ADMIN_MFA_ENROLLED = "ADMIN_MFA_ENROLLED"
    ADMIN_SIGNED_IN = "ADMIN_SIGNED_IN"
    ADMIN_MFA_FAILED = "ADMIN_MFA_FAILED"
    ADMIN_MFA_LOCKED = "ADMIN_MFA_LOCKED"
    ADMIN_RECOVERY_CODE_USED = "ADMIN_RECOVERY_CODE_USED"
    # The same factor at the app's own door [0028]: turned on, turned
    # off, a code passed or failed at sign-in, a lock, a recovery code
    # spent, and a fresh set of recovery codes.
    MFA_ENROLLED = "MFA_ENROLLED"
    MFA_DISABLED = "MFA_DISABLED"
    MFA_VERIFIED = "MFA_VERIFIED"
    MFA_FAILED = "MFA_FAILED"
    MFA_LOCKED = "MFA_LOCKED"
    MFA_RECOVERY_CODE_USED = "MFA_RECOVERY_CODE_USED"
    MFA_RECOVERY_CODES_RENEWED = "MFA_RECOVERY_CODES_RENEWED"
    # Passwords and email [0032]. A password sign-in that failed says so
    # without saying why: unknown account, no password and wrong
    # password are one event, as they are one response.
    PASSWORD_SET = "PASSWORD_SET"  # noqa: S105 -- a name, not a password
    PASSWORD_CHANGED = "PASSWORD_CHANGED"  # noqa: S105 -- a name, not a password
    PASSWORD_SIGN_IN_SUCCEEDED = "PASSWORD_SIGN_IN_SUCCEEDED"  # noqa: S105 -- a name, not a password
    PASSWORD_SIGN_IN_FAILED = "PASSWORD_SIGN_IN_FAILED"  # noqa: S105 -- a name, not a password
    PASSWORD_CEILING_BREACHED = "PASSWORD_CEILING_BREACHED"  # noqa: S105 -- a name, not a password
    CONTACT_ADDED = "CONTACT_ADDED"


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
