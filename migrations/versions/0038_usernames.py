"""Every account may carry one unique username, and a released one is held.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-15

A person may now sign in with a username as well as a phone number or an
email address [FR1, FR4]. What this revision adds:

* **``account.username``** (the display form, as typed after trimming)
  and **``account.username_key``** (its lowercase form), unique on the
  key, so ``Rahim_01`` and ``rahim_01`` can never both exist [BR1.7].
* **The database backstops the shape** [BR1.9]. Three CHECKs: the two
  columns are both set or both null -- an equality check alone passes
  when either side is null, so the null case is written out -- the key
  is the lowercase form of the name, and the key has the FR1 shape. The
  application refuses first, with its own keyed refusals; these exist
  for a writer that bypassed it. The reserved list is not here.
* **``account.username_changed_at``** (the last ordinary rename) and
  **``account.username_reclaimed_at``** (the last exempt reclaim), which
  together decide the 30-day rename window [BR6.2, BR6.4].
* **``pending_signup.username``**: the name a sign-up draft asked for.
  Null only for a draft saved before this revision [BR2.7].
* **``username_hold``**, created after the account columns it references:
  one row per released name, keyed by a keyed digest of the name and
  never by its text [BR7.1]. ``releasing_account_id`` is ``SET NULL`` on
  erasure, so a renamed-away hold turns into one nobody may reclaim
  [BR7.4].

Every column is nullable with no default and no existing row is updated
[NFR7.1], so the CHECKs validate without a rewrite and the revision runs
as fast DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.db.roles import APP_ROLE

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The longest username FR1 allows, which sizes every column holding one.
USERNAME_LENGTH = 20

#: Lowercase hex of an HMAC-SHA256.
DIGEST_LENGTH = 64

#: The FR1 shape of a key: a letter, then letters, digits, ``_`` and
#: ``.``, not ending with a dot, 3 to 20 characters. The no-``..`` rule is
#: the second half of the CHECK.
KEY_SHAPE = (
    "username_key ~ '^[a-z][a-z0-9_.]{1,18}[a-z0-9_]$' "
    "AND position('..' in username_key) = 0"
)


def upgrade() -> None:
    """Add the username columns, their checks, and the hold ledger.

    :return: None
    """
    op.add_column(
        "account", sa.Column("username", sa.String(USERNAME_LENGTH), nullable=True)
    )
    op.add_column(
        "account", sa.Column("username_key", sa.String(USERNAME_LENGTH), nullable=True)
    )
    op.add_column(
        "account",
        sa.Column("username_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "account",
        sa.Column("username_reclaimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_account_username_key", "account", ["username_key"])
    op.create_check_constraint(
        "ck_account_username_both_or_neither",
        "account",
        "(username IS NULL) = (username_key IS NULL)",
    )
    op.create_check_constraint(
        "ck_account_username_key_lower", "account", "username_key = lower(username)"
    )
    op.create_check_constraint("ck_account_username_key_shape", "account", KEY_SHAPE)

    op.add_column(
        "pending_signup",
        sa.Column("username", sa.String(USERNAME_LENGTH), nullable=True),
    )

    op.create_table(
        "username_hold",
        sa.Column("key_digest", sa.String(DIGEST_LENGTH), nullable=False),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "releasing_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name="fk_username_hold_releasing_account_id_account",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_digest", name="pk_username_hold"),
    )
    # The purge deletes by expiry; the account delete's SET NULL probes
    # the releasing account.
    op.create_index("ix_username_hold_held_until", "username_hold", ["held_until"])
    op.create_index(
        "ix_username_hold_releasing_account_id",
        "username_hold",
        ["releasing_account_id"],
        postgresql_where=sa.text("releasing_account_id IS NOT NULL"),
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON username_hold TO {APP_ROLE}")
    )


def downgrade() -> None:
    """Drop what :func:`upgrade` added.

    **Refuses while any account has a username**: dropping the columns
    would erase how those people sign in, which is data loss disguised as
    a rollback. The rollback path is the previous image with the columns
    left in place [NFR6.3].

    :return: None
    """
    held = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM account WHERE username_key IS NOT NULL"))
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{held} account(s) carry a username; downgrading would erase "
            "how they sign in. Refusing."
        )
    op.drop_index("ix_username_hold_releasing_account_id", table_name="username_hold")
    op.drop_index("ix_username_hold_held_until", table_name="username_hold")
    op.drop_table("username_hold")
    op.drop_column("pending_signup", "username")
    op.drop_constraint("ck_account_username_key_shape", "account", type_="check")
    op.drop_constraint("ck_account_username_key_lower", "account", type_="check")
    op.drop_constraint("ck_account_username_both_or_neither", "account", type_="check")
    op.drop_constraint("uq_account_username_key", "account", type_="unique")
    op.drop_column("account", "username_reclaimed_at")
    op.drop_column("account", "username_changed_at")
    op.drop_column("account", "username_key")
    op.drop_column("account", "username")
