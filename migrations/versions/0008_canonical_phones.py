"""Store every phone number in one form, and give a seat its student's number.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28

**Why.** Numbers were stored exactly as typed. ``account.phone`` is unique
on that raw string, so one person who signed in as ``01711111111`` and
later as ``+8801711111111`` holds two accounts; a teacher's
``01711-234567`` never matched a guardian's account, so phone-based
linking silently failed. From this revision every request schema
canonicalises a number to ``+8801XXXXXXXXX`` on the way in
(``app.schemas.phone``), and this migration rewrites the numbers already
stored to match. Without it, an account stored as ``01711111111`` could
never sign in again: its owner's typed number would now arrive canonical
and match nothing.

**Two existing accounts that are the same phone stop the migration.** That
is the duplicate-account bug itself, and merging them would mean choosing
whose batches, seats and history survive -- a decision for a person, not a
migration. The error names both account ids; resolve them, then rerun.

**A number that cannot be canonicalised is left exactly as it is**, and
counted in the log: a seed value or a typing error is not guessed at. An
``account`` row left unconverted cannot sign in until fixed by hand, which
is the same as before this migration, not worse.

**The canonicalising logic is copied here, not imported**, deliberately. A
migration must produce the same result whenever it runs; importing
``app.accounts.phone`` would let a later change to that function rewrite
what this revision does to data already migrated elsewhere.

**Downgrade drops ``student_phone`` and leaves numbers canonical.** The raw
spellings are not recorded anywhere, so they cannot be restored -- and a
canonical number is still a valid string to every earlier revision.
"""

from __future__ import annotations

import logging
import re

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None

_log = logging.getLogger("alembic.runtime.migration")

_LOCAL_MOBILE = re.compile(r"01[3-9][0-9]{8}")
_SEPARATORS = re.compile(r"[\s\-().]")
_BANGLA_ZERO = 0x09E6


def _canonical(raw: str) -> str | None:
    """Return ``+8801XXXXXXXXX``, or None when ``raw`` is not a BD mobile.

    A frozen copy of ``app.accounts.phone.canonical_phone`` as it stood at
    this revision; see the module docstring for why it is not imported.

    :param raw: A stored number
    :return: The canonical form, or None
    """
    text = "".join(
        str(ord(c) - _BANGLA_ZERO) if 0 <= ord(c) - _BANGLA_ZERO <= 9 else c
        for c in raw
    )
    text = _SEPARATORS.sub("", text)
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("00"):
        text = text[2:]
    if text.startswith("880"):
        text = "0" + text[3:]
    if not _LOCAL_MOBILE.fullmatch(text):
        return None
    return f"+880{text[1:]}"


def _rewrite(bind: sa.engine.Connection, table: str, column: str) -> tuple[int, int]:
    """Canonicalise one column in place.

    :param bind: The migration's connection
    :param table: The table
    :param column: The phone column
    :return: (rows rewritten, rows left because they would not convert)
    """
    rows = bind.execute(
        sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
    ).all()
    rewritten = skipped = 0
    for row_id, raw in rows:
        canonical = _canonical(raw)
        if canonical is None:
            skipped += 1
        elif canonical != raw:
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),  # noqa: S608
                {"value": canonical, "id": row_id},
            )
            rewritten += 1
    return rewritten, skipped


def _refuse_duplicate_accounts(bind: sa.engine.Connection) -> None:
    """Stop if two accounts are one phone once canonicalised.

    :param bind: The migration's connection
    :return: None
    :raises RuntimeError: Two or more accounts share a canonical number
    """
    by_number: dict[str, list[str]] = {}
    for account_id, raw in bind.execute(sa.text("SELECT id, phone FROM account")).all():
        canonical = _canonical(raw)
        if canonical is not None:
            by_number.setdefault(canonical, []).append(str(account_id))
    clashes = {number: ids for number, ids in by_number.items() if len(ids) > 1}
    if clashes:
        listed = "; ".join(
            f"{n}: {', '.join(ids)}" for n, ids in sorted(clashes.items())
        )
        raise RuntimeError(
            "Two or more accounts are the same phone under different "
            f"spellings, and merging them is a person's decision: {listed}. "
            "Resolve each (keep one account, move or delete the other's "
            "data) and rerun this migration."
        )


def upgrade() -> None:
    """Add ``student_phone`` and store every number canonically.

    :return: None
    """
    bind = op.get_bind()
    _refuse_duplicate_accounts(bind)

    for table, column in (
        ("account", "phone"),
        ("otp_request", "phone"),
        ("enrollment", "guardian_phone"),
    ):
        rewritten, skipped = _rewrite(bind, table, column)
        _log.info(
            "0008: %s.%s rewritten=%d left-unconverted=%d",
            table,
            column,
            rewritten,
            skipped,
        )

    # The number a teacher typed for the STUDENT. A seat had nowhere to
    # keep it, so a student added by a teacher could never be linked to
    # their own account. Nullable: a seat may be created for a child
    # with no phone, reached through the guardian.
    op.add_column(
        "enrollment",
        sa.Column("student_phone", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_enrollment_student_phone", "enrollment", ["student_phone"])


def downgrade() -> None:
    """Drop ``student_phone``; numbers stay canonical (see module docstring).

    :return: None
    """
    op.drop_index("ix_enrollment_student_phone", table_name="enrollment")
    op.drop_column("enrollment", "student_phone")
