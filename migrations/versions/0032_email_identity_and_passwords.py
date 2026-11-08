"""Email as a second identifier, and passwords.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-08

* **``account.email``** -- an account is keyed on a phone number, an
  email address, or both. ``phone`` becomes nullable and a CHECK keeps
  at least one present. ``email`` is stored lowercased and is unique,
  like ``phone``.
* **``account.password_hash``** -- scrypt (:mod:`app.auth.passwords`),
  never the password. Null for every account that existed before this
  revision: those people set one through the code flow once.
* **``account.password_changed_at``** -- when the password was last set.
  A password-setup token carries the value it was issued against, so it
  is spent the moment a password is set with it.
* **``otp_request.email``**, **``pending_signup.email``** and
  **``staging_sms_outbox.email``** -- a code, a signup draft and a
  staging outbox entry are each for a phone number OR an email address,
  exactly one, so ``phone`` becomes nullable on each and a CHECK holds
  the "exactly one".

**Backward-compatible with the previous image** [team: Deployment]: every
new column is nullable, and the old code always writes ``phone``, which
satisfies every new CHECK. Nothing is renamed or dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: RFC 5321's limit on a forward path; nothing longer can receive mail.
EMAIL_LENGTH = 254


def upgrade() -> None:
    """Add the email columns, the password columns and their checks.

    :return: None
    """
    op.add_column("account", sa.Column("email", sa.String(EMAIL_LENGTH), nullable=True))
    op.add_column("account", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "account",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("account", "phone", existing_type=sa.String(20), nullable=True)
    op.create_unique_constraint("uq_account_email", "account", ["email"])
    op.create_check_constraint(
        "ck_account_has_identifier",
        "account",
        "phone IS NOT NULL OR email IS NOT NULL",
    )

    for table in ("otp_request", "pending_signup", "staging_sms_outbox"):
        op.add_column(table, sa.Column("email", sa.String(EMAIL_LENGTH), nullable=True))
        op.alter_column(table, "phone", existing_type=sa.String(20), nullable=True)
        op.create_check_constraint(
            f"ck_{table}_one_identifier",
            table,
            "(phone IS NULL) <> (email IS NULL)",
        )

    # The verify path reads the latest code for one destination.
    op.create_index(
        "ix_otp_request_email_issued_at", "otp_request", ["email", "issued_at"]
    )
    op.create_unique_constraint("uq_pending_signup_email", "pending_signup", ["email"])
    op.create_index(
        "ix_staging_sms_outbox_email_recorded",
        "staging_sms_outbox",
        ["email", "recorded_at"],
    )


def downgrade() -> None:
    """Drop what :func:`upgrade` added.

    **Refuses while an email-only row exists**: restoring ``NOT NULL`` on
    ``phone`` would fail on it anyway, and a downgrade that deleted
    accounts to make room would be data loss disguised as a rollback.

    :return: None
    """
    op.drop_index(
        "ix_staging_sms_outbox_email_recorded", table_name="staging_sms_outbox"
    )
    op.drop_constraint("uq_pending_signup_email", "pending_signup", type_="unique")
    op.drop_index("ix_otp_request_email_issued_at", table_name="otp_request")
    for table in ("staging_sms_outbox", "pending_signup", "otp_request"):
        op.drop_constraint(f"ck_{table}_one_identifier", table, type_="check")
        op.alter_column(table, "phone", existing_type=sa.String(20), nullable=False)
        op.drop_column(table, "email")

    op.drop_constraint("ck_account_has_identifier", "account", type_="check")
    op.drop_constraint("uq_account_email", "account", type_="unique")
    op.alter_column("account", "phone", existing_type=sa.String(20), nullable=False)
    op.drop_column("account", "password_changed_at")
    op.drop_column("account", "password_hash")
    op.drop_column("account", "email")
