"""Set the row-level-security context for one request.

The ``profile`` policy reads ``app.account_id`` from the session. This
module is the only thing that sets it, and it sets it **local to the
transaction**: ``set_config(..., true)`` scopes the value to the current
transaction, so it is discarded at commit or rollback.

**That ``true`` is the whole control.** Without it the setting is
session-scoped and therefore *connection*-scoped -- and connections are
pooled, so the next request to borrow that connection would inherit the
previous request's account id and read another person's profile. A
session-scoped set looks identical in every single-request test.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import SESSION_ACCOUNT_KEY

__all__ = ["clear_account_context", "set_account_context"]


def set_account_context(session: Session, account_id: uuid.UUID) -> None:
    """Bind this transaction to an account for the RLS policy.

    :param session: The session whose transaction is being bound
    :param account_id: The authenticated account
    :return: None
    """
    session.execute(
        sa.text("SELECT set_config(:key, :value, true)"),
        {"key": SESSION_ACCOUNT_KEY, "value": str(account_id)},
    )


def clear_account_context(session: Session) -> None:
    """Clear the bound account.

    Rarely needed -- the transaction-local setting is discarded at commit
    or rollback -- but explicit clearing is what makes a long-lived
    arranging session safe to reuse in tests.

    :param session: The session to clear
    :return: None
    """
    session.execute(
        sa.text("SELECT set_config(:key, '', true)"),
        {"key": SESSION_ACCOUNT_KEY},
    )
