"""Moderation events for reviews and replies.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-19

``hub_moderation_event`` records what moderation did in a closed
vocabulary, ``hub_moderation_event_kind`` [0036, 0044]. Reviews and their
replies add eleven acts, with ``target_kind`` ``review`` or ``reply``:

* ``review_approved`` / ``reply_approved`` -- an administrator approved an
  item waiting for review; a review then waits for the weekly publication,
  a reply is published at once (Calls 2 and 3);
* ``review_rejected`` / ``reply_rejected`` -- an administrator rejected it,
  its closed rejection code in ``decision_code``;
* ``review_held`` / ``reply_held`` -- a child-safety or personal-information
  report took a published item down at once, the report's reason in
  ``decision_code`` and no actor, because no administrator acted. The
  latest of these is the item's hold time [F11];
* ``review_restored`` / ``reply_restored`` -- a held item went back up;
* ``review_removed`` / ``reply_removed`` -- a held or reported item was
  taken down for good;
* ``review_published`` -- the weekly publication made an approved review
  public, with no actor.

``0045`` is released, so the labels are added here rather than there. As
``0044`` does, they are added in an autocommit block, because a new label
cannot be used in the transaction that adds it; committing ends Alembic's
transaction and with it the ``SET LOCAL lock_timeout`` ``env.py`` issued,
so the setting in force is read before the block and restored straight
after it [audit C-18]. ``ADD VALUE IF NOT EXISTS`` lets a run that failed
after the block proceed.

PostgreSQL cannot drop an enum label, so the downgrade rebuilds the type;
it refuses while an event names a review or reply act, because those rows
are the moderation record and are kept twelve months.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The enum type's name, shared by upgrade and downgrade.
KIND_TYPE: Final[str] = "hub_moderation_event_kind"

#: The labels ``0036`` and ``0044`` created, which the downgrade restores.
EARLIER_KINDS: Final[tuple[str, ...]] = (
    "report_filed",
    "report_upheld",
    "report_dismissed",
    "listing_suspended",
    "listing_unsuspended",
    "media_approved",
    "media_rejected",
    "media_held",
    "media_restored",
)

#: The labels this revision adds, in order.
REVIEW_KINDS: Final[tuple[str, ...]] = (
    "review_approved",
    "review_rejected",
    "review_held",
    "review_restored",
    "review_removed",
    "review_published",
    "reply_approved",
    "reply_rejected",
    "reply_held",
    "reply_restored",
    "reply_removed",
)


def upgrade() -> None:
    """Add the eleven review and reply labels.

    :return: None
    """
    lock_timeout = op.get_bind().execute(sa.text("SHOW lock_timeout")).scalar_one()
    with op.get_context().autocommit_block():
        for kind in REVIEW_KINDS:
            op.execute(
                sa.text(f"ALTER TYPE {KIND_TYPE} ADD VALUE IF NOT EXISTS '{kind}'")
            )
    # The block committed Alembic's transaction; this is the new one's.
    op.execute(
        sa.text("SELECT set_config('lock_timeout', :value, true)").bindparams(
            value=lock_timeout
        )
    )


def downgrade() -> None:
    """Refuse while an event names a review or reply act; else remove them.

    :return: None
    :raises RuntimeError: A moderation event records a review or reply act
    """
    used = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM hub_moderation_event "
                "WHERE event::text = ANY(:kinds)"
            ),
            {"kinds": list(REVIEW_KINDS)},
        )
        .scalar_one()
    )
    if used:
        raise RuntimeError(
            f"Cannot downgrade 0046: {used} moderation event(s) record a review "
            "or reply decision or hold, and the moderation record is kept "
            "twelve months."
        )
    # The type cannot lose a label in place: build the narrower one, move
    # the column onto it, and drop the old. Grants are on the table.
    labels = ", ".join(f"'{k}'" for k in EARLIER_KINDS)
    op.execute(sa.text(f"ALTER TYPE {KIND_TYPE} RENAME TO {KIND_TYPE}_0046"))
    op.execute(sa.text(f"CREATE TYPE {KIND_TYPE} AS ENUM ({labels})"))
    op.execute(
        sa.text(
            f"ALTER TABLE hub_moderation_event ALTER COLUMN event TYPE {KIND_TYPE} "
            f"USING event::text::{KIND_TYPE}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {KIND_TYPE}_0046"))
