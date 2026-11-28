"""Seat counts on a batch listing, and the view that publishes them.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-28

An owner may show how many seats a batch has and how many are free. Both
numbers are **typed by the owner**, never counted from enrollments: the
public page states what the owner chose to say, and nothing it shows is
derived from a child's record.

**Shown only by choice.** ``show_seats`` defaults to false, so every
listing that exists when this runs is unaffected, as ``show_fee`` and
``show_schedule`` are a choice. A CHECK keeps the choice honest: showing
seats needs both numbers.

**The numbers are bounded and consistent.** A batch has 1 to 500 seats,
and the free count lies between 0 and that total. A free count without a
total means nothing, so it is refused.

**``seats_updated_at``** records when the owner last changed either
number, so the page can say how fresh they are. It is set by the
application, and a CHECK keeps it present exactly when a total is.

**``hub_public_batch_seats``**, a new view rather than a changed one, as
``0047`` chose: a column added to ``hub_public_batch`` could not be dropped
again by the downgrade while ``0043``'s and ``0045``'s views depend on it.
It reads ``hub_public_batch`` for which batches are public, so a draft,
hidden, suspended or inactive batch shows no seats, and reads only
``batch_id`` and the four seat columns from ``batch_listing``. The day is
published, never the time of day. It is ``security_barrier`` and granted
to the hub reader only, as every public view is.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

from app.db.roles import HUB_READER_ROLE

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The most seats a batch may state.
MAX_SEATS: Final[int] = 500

#: The view this revision creates.
VIEW: Final[str] = "hub_public_batch_seats"

#: Its body: the seats of public batches whose owner chose to show them.
VIEW_BODY: Final[str] = """
    SELECT b.batch_id, bl.seat_capacity, bl.seats_free,
           (bl.seats_updated_at AT TIME ZONE 'Asia/Dhaka')::date
               AS seats_updated_on
    FROM hub_public_batch b
    JOIN batch_listing bl ON bl.batch_id = b.batch_id
    WHERE bl.show_seats
"""

#: Each CHECK this revision adds, by name.
CHECKS: Final[dict[str, str]] = {
    "ck_batch_listing_seat_capacity": (
        f"seat_capacity IS NULL OR seat_capacity BETWEEN 1 AND {MAX_SEATS}"
    ),
    "ck_batch_listing_seats_free": (
        "seats_free IS NULL OR "
        "(seat_capacity IS NOT NULL AND seats_free BETWEEN 0 AND seat_capacity)"
    ),
    "ck_batch_listing_seats_shown_need_numbers": (
        "NOT show_seats OR (seat_capacity IS NOT NULL AND seats_free IS NOT NULL)"
    ),
    "ck_batch_listing_seats_updated_iff_capacity": (
        "(seat_capacity IS NULL) = (seats_updated_at IS NULL)"
    ),
}


def upgrade() -> None:
    """Add the columns and their checks, then create and grant the view.

    :return: None
    """
    op.add_column(
        "batch_listing",
        sa.Column(
            "show_seats", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("batch_listing", sa.Column("seat_capacity", sa.SmallInteger()))
    op.add_column("batch_listing", sa.Column("seats_free", sa.SmallInteger()))
    op.add_column(
        "batch_listing",
        sa.Column("seats_updated_at", sa.DateTime(timezone=True)),
    )
    for name, condition in CHECKS.items():
        op.create_check_constraint(conv(name), "batch_listing", condition)
    op.execute(sa.text(f"CREATE VIEW {VIEW} WITH (security_barrier) AS {VIEW_BODY}"))
    op.execute(sa.text(f"GRANT SELECT ON {VIEW} TO {HUB_READER_ROLE}"))


def downgrade() -> None:
    """Drop the view, the checks and the columns.

    The numbers are the owner's own and can be typed again; nothing here
    holds anyone else's data, so the downgrade does not refuse.

    :return: None
    """
    op.execute(sa.text(f"DROP VIEW {VIEW}"))
    for name in reversed(CHECKS):
        op.drop_constraint(conv(name), "batch_listing", type_="check")
    for column in ("seats_updated_at", "seats_free", "seat_capacity", "show_seats"):
        op.drop_column("batch_listing", column)
