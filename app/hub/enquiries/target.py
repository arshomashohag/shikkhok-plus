"""Who may send a join request, and to what [H5 Global Constraints].

A guardian may ask an owner, or one of its batches, to take a student when
all of these hold:

* the owner's slug is in ``hub_public_enquirable``: its listing is
  published and accepts requests;
* a named batch is a row of ``hub_public_batch`` under that owner's slug,
  with admissions not ``closed`` -- except for an interest [0049], which a
  family may share in a closed batch;
* the caller does not run the listing: they are neither the owner's own
  account nor an accepted, unrevoked manager of it.

Anything else answers the one :func:`not_found`, which is also the answer
for a slug that never existed, so a refusal never says which condition
failed (Review Focus 2).

**One SQL statement decides it** [F8]. The last condition restates, in SQL,
the predicate :func:`app.hub.listings.shared.managing_accounts` computes in
Python for delivery, and ``tests/enquiries/test_target.py`` asserts the two
refuse exactly the same accounts. A centre's class teacher who is not a
manager may send: requests are delivered to managers only, so a class
teacher never reads the inbox their request lands in. (They do run the
batch for review purposes, ``runs_batch_sql``; that is a different
question.)

The application role reads the two public views directly (Call 16), so the
check is the public pages' own predicate, inside the send's transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Session

from app.errors import AuthorizationError

__all__ = ["Target", "not_found", "resolve"]

#: The target, or no row. ``:batch_id`` may be NULL for a request about the
#: owner as a whole.
_RESOLVE: Final = sa.text(
    """
    SELECT e.owner_id, e.slug, o.public_name, b.batch_id, b.public_title
    FROM hub_public_enquirable e
    JOIN hub_public_owner o ON o.owner_id = e.owner_id
    LEFT JOIN hub_public_batch b
        ON b.batch_id = :batch_id
       AND b.owner_slug = e.slug
       AND (b.admissions <> 'closed' OR :closed_ok)
    WHERE e.slug = :slug
      AND (:batch_id IS NULL OR b.batch_id IS NOT NULL)
      AND NOT EXISTS (
          SELECT 1 FROM owner w
          WHERE w.id = e.owner_id AND w.account_id = :account_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM owner_member m
          WHERE m.owner_id = e.owner_id
            AND m.account_id = :account_id
            AND m.role = 'manager'
            AND m.decision = 'accepted'
            AND m.revoked_at IS NULL
      )
    """
).bindparams(
    sa.bindparam("batch_id", type_=PgUUID(as_uuid=True)),
    sa.bindparam("account_id", type_=PgUUID(as_uuid=True)),
    sa.bindparam("closed_ok", type_=sa.Boolean()),
)


@dataclass(frozen=True, slots=True)
class Target:
    """Where a join request may go.

    :ivar owner_id: The owner asked
    :ivar owner_slug: Its public slug
    :ivar owner_public_name: Its listing's public name
    :ivar batch_id: The batch asked about, or None for the owner as a whole
    :ivar batch_title: That batch's public title, or None
    """

    owner_id: uuid.UUID
    owner_slug: str
    owner_public_name: str
    batch_id: uuid.UUID | None
    batch_title: str | None


def not_found() -> AuthorizationError:
    """Build the one refusal for every target a request may not reach.

    :return: ``ENQUIRY_TARGET_NOT_FOUND`` (404)
    """
    return AuthorizationError(
        code="ENQUIRY_TARGET_NOT_FOUND",
        message_key="hub.enquiry.target_not_found",
        status=404,
    )


def resolve(
    session: Session,
    account_id: uuid.UUID,
    owner_slug: str,
    batch_id: uuid.UUID | None,
    *,
    closed_ok: bool = False,
) -> Target:
    """Find where the caller's join request would go, or refuse.

    :param session: The session to read through
    :param account_id: The authenticated caller
    :param owner_slug: The owner's public slug
    :param batch_id: The batch asked about, or None for the owner as a whole
    :param closed_ok: Accept a batch whose admissions are closed: an
        interest may be shared in a full batch, which is when it matters
        [0049]; a join request may not
    :return: The target
    :raises AuthorizationError: ``ENQUIRY_TARGET_NOT_FOUND`` (404) for any
        target the caller may not ask
    """
    row = session.execute(
        _RESOLVE,
        {
            "slug": owner_slug,
            "batch_id": batch_id,
            "account_id": account_id,
            "closed_ok": closed_ok,
        },
    ).one_or_none()
    if row is None:
        raise not_found()
    return Target(
        owner_id=row.owner_id,
        owner_slug=row.slug,
        owner_public_name=row.public_name,
        batch_id=row.batch_id,
        batch_title=row.public_title,
    )
