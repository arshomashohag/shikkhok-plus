"""Reviews: ``review``, ``review_reply`` and the two threshold views.

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-19

A guardian whose seat qualifies writes one review of a batch (spec section 6):
a rating from 1 to 5 and an optional body of up to 1000 characters.
``UNIQUE (batch_id, author_account_id)`` makes a guardian with two
children in one batch write one review. ``enrollment_id`` records the seat
that evidenced eligibility and ``tenure_bucket`` the length of that seat,
frozen at first submit; V1 accepts guardians only, so ``author_role`` is
CHECKed to ``guardian`` although its enum also holds ``student``.

**Statuses** (Call 2): ``pending`` -> ``approved`` (a moderator approved it;
it waits for the weekly publication) -> ``published``, or off to
``rejected`` or ``removed``; ``held`` is a published review taken down by a
report while an admin decides. A reply has the same set without
``approved``: it publishes on approval (Call 3). Three CHECKs keep the
stored times honest: ``published_month`` exists exactly while published or
held, and is always the first of a month; ``approved_at`` exists exactly
while approved, so the weekly job's queue is the column; and a rejection or
removal carries its closed code.

**``review.id`` is minted by the server as ``gen_random_uuid()``** [F22].
Public pages order reviews by ``published_month DESC, id`` (Call 10), which
says nothing about submission order only while ids are random, and a
raw-SQL insert would bypass the ORM's ``uuid4`` default.

**The k-threshold is enforced here, in the views, not in Python** (Call 5;
Review Focus 2). :data:`REVIEW_THRESHOLD` is interpolated into both:

* ``hub_public_rating`` holds one row per batch visible in
  ``hub_public_batch`` that has **at least** :data:`REVIEW_THRESHOLD`
  published reviews: the count, the average in integer tenths (rounded half
  up: ``round(numeric)``), the sum, and the distribution from one star to
  five. **Below the threshold it holds no row at all** -- not even a count
  [F18, spec over plan]. The plan had the count shown always and the rest
  NULL below 3; a count of 1 or 2 helps a teacher who knows which family
  just became eligible work out who wrote a review, which is the anti-goal
  spec section 6 names, so a batch below the threshold is indistinguishable
  from a batch with no reviews.
* ``hub_public_review`` holds the published reviews of exactly those
  batches, with the reply's text and month only while the reply is
  ``published``.

Neither view reads an author, a seat, a decision-maker or any time finer
than a month: ``pg_depend`` is checked for that in
``tests/privacy/test_hub_public_review_view.py``. Both read
``hub_public_batch`` rather than restating its filter, as ``0043``'s photo
view does, so a review is public exactly where its batch's page is.

**Deviation from spec section 2, recorded** [F18]: the spec lists four
reader views, and ``0043`` already made five; ``hub_public_rating`` is a
seventh, beside ``hub_public_review``. An aggregate cannot be read from the
review view without reading every row of it, and the average must come
from SQL (no float, no Python ``decimal``), so it is a view of its own,
under the same threshold, grants and ``security_barrier``.

**Grants** (Call 6): both views go to the hub reader and to the application
role. The application role already reads both base tables, so its grant
adds no reach; it lets the teacher API read reviews through the same
threshold as the public inside a write transaction, without
``SET LOCAL ROLE``. Unlike ``0040``'s views, the application role's grant is
stated rather than inherited, so it is a reviewed audience. The reader is
granted nothing on either table.

**Cascades.** A review goes with its author's account and with its batch's
listing (a solo owner's listing goes with their account); deleting the
evidencing seat only clears ``enrollment_id``. A reply goes with its
review; deleting the account that wrote it only clears
``written_by_account_id``, so a centre's reply survives a manager.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE, HUB_READER_ROLE

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Published reviews a batch needs before anything about them is public.
REVIEW_THRESHOLD: Final[int] = 3

#: Each enum this revision creates and its labels, in declaration order.
ENUMS: Final[dict[str, tuple[str, ...]]] = {
    "hub_review_status": (
        "pending",
        "approved",
        "published",
        "rejected",
        "removed",
        "held",
    ),
    "hub_reply_status": ("pending", "published", "rejected", "removed", "held"),
    "hub_review_author_role": ("guardian", "student"),
    "hub_review_tenure": ("lt_6m", "6_12m", "gt_1y"),
}

#: ``published_month`` exists exactly while the item is shown or held.
MONTH_IFF_SHOWN: Final[str] = (
    "(status = 'published' OR status = 'held') = (published_month IS NOT NULL)"
)

#: A month is stored as its first day.
MONTH_IS_FIRST: Final[str] = (
    "published_month IS NULL OR extract(day FROM published_month) = 1"
)

#: A rejection or a removal carries its closed code.
REJECTION_CODE: Final[str] = (
    "status NOT IN ('rejected', 'removed') OR rejection_code IS NOT NULL"
)

#: Each view's body, in creation order: the review view reads the rating.
VIEWS: Final[dict[str, str]] = {
    "hub_public_rating": f"""
        SELECT r.batch_id,
               count(*)::int AS review_count,
               round(10 * sum(r.rating)::numeric / count(*))::int
                   AS average_tenths,
               sum(r.rating)::int AS rating_sum,
               ARRAY[
                   count(*) FILTER (WHERE r.rating = 1),
                   count(*) FILTER (WHERE r.rating = 2),
                   count(*) FILTER (WHERE r.rating = 3),
                   count(*) FILTER (WHERE r.rating = 4),
                   count(*) FILTER (WHERE r.rating = 5)
               ]::int[] AS distribution
        FROM review r
        JOIN hub_public_batch pb ON pb.batch_id = r.batch_id
        WHERE r.status = 'published'
        GROUP BY r.batch_id
        HAVING count(*) >= {REVIEW_THRESHOLD}
    """,  # noqa: S608  a module constant, never input
    "hub_public_review": f"""
        SELECT r.id, r.batch_id, r.rating, r.body, r.tenure_bucket,
               r.author_role, r.published_month,
               CASE WHEN p.status = 'published' THEN p.body END AS reply_body,
               CASE WHEN p.status = 'published' THEN p.published_month END
                   AS reply_month
        FROM review r
        JOIN hub_public_rating g ON g.batch_id = r.batch_id
        LEFT JOIN review_reply p ON p.review_id = r.id
        WHERE r.status = 'published'
          AND g.review_count >= {REVIEW_THRESHOLD}
    """,  # noqa: S608  a module constant, never input
}


def _enum(name: str) -> postgresql.ENUM:
    """Return one of this revision's enums, without creating it again.

    :param name: The enum's name
    :return: The enum type
    """
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _account_fk(table: str, column: str, ondelete: str) -> sa.Column[object]:
    """Build a nullable-or-not account reference with a convention name.

    :param table: The table the column belongs to
    :param column: The column's name
    :param ondelete: ``CASCADE`` or ``SET NULL``
    :return: The column
    """
    return sa.Column(
        column,
        PgUUID(as_uuid=True),
        sa.ForeignKey(
            "account.id", ondelete=ondelete, name=conv(f"fk_{table}_{column}")
        ),
        nullable=ondelete == "SET NULL",
    )


def upgrade() -> None:
    """Create the enums, both tables, both views and their grants.

    :return: None
    """
    bind = op.get_bind()
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name).create(bind)

    op.create_table(
        "review",
        sa.Column(
            "id",
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "batch_listing.batch_id",
                ondelete="CASCADE",
                name=conv("fk_review_batch_id"),
            ),
            nullable=False,
        ),
        _account_fk("review", "author_account_id", "CASCADE"),
        sa.Column(
            "enrollment_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "enrollment.id",
                ondelete="SET NULL",
                name=conv("fk_review_enrollment_id"),
            ),
            nullable=True,
        ),
        sa.Column("author_role", _enum("hub_review_author_role"), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _enum("hub_review_status"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("tenure_bucket", _enum("hub_review_tenure"), nullable=False),
        sa.Column("rejection_code", sa.String(32), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_month", sa.Date(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _account_fk("review", "decided_by_account_id", "SET NULL"),
        sa.UniqueConstraint(
            "batch_id", "author_account_id", name=conv("uq_review_batch_author")
        ),
        sa.CheckConstraint(
            "author_role = 'guardian'", name=conv("ck_review_author_role_v1")
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name=conv("ck_review_rating")),
        sa.CheckConstraint(
            "body IS NULL OR char_length(body) <= 1000", name=conv("ck_review_body")
        ),
        sa.CheckConstraint(
            MONTH_IFF_SHOWN, name=conv("ck_review_published_month_iff_shown")
        ),
        sa.CheckConstraint(
            MONTH_IS_FIRST, name=conv("ck_review_published_month_first")
        ),
        sa.CheckConstraint(REJECTION_CODE, name=conv("ck_review_rejection_code")),
        sa.CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL)",
            name=conv("ck_review_approved_at_iff_approved"),
        ),
    )
    op.create_index(
        "ix_review_batch_id_published",
        "review",
        ["batch_id"],
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index("ix_review_author_account_id", "review", ["author_account_id"])
    op.create_index("ix_review_enrollment_id", "review", ["enrollment_id"])

    op.create_table(
        "review_reply",
        sa.Column(
            "review_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "review.id", ondelete="CASCADE", name=conv("fk_review_reply_review_id")
            ),
            primary_key=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum("hub_reply_status"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        _account_fk("review_reply", "written_by_account_id", "SET NULL"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_month", sa.Date(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _account_fk("review_reply", "decided_by_account_id", "SET NULL"),
        sa.Column("rejection_code", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 1000", name=conv("ck_review_reply_body")
        ),
        sa.CheckConstraint(
            MONTH_IFF_SHOWN, name=conv("ck_review_reply_published_month_iff_shown")
        ),
        sa.CheckConstraint(
            MONTH_IS_FIRST, name=conv("ck_review_reply_published_month_first")
        ),
        sa.CheckConstraint(
            REJECTION_CODE, name=conv("ck_review_reply_rejection_code")
        ),
    )

    for table in ("review", "review_reply"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )

    for name, body in VIEWS.items():
        op.execute(sa.text(f"CREATE VIEW {name} WITH (security_barrier) AS {body}"))
        # The reader for public pages; the application role for the
        # teacher's reviews, read under the same threshold (Call 6).
        op.execute(
            sa.text(f"GRANT SELECT ON {name} TO {HUB_READER_ROLE}, {APP_ROLE}")
        )


def downgrade() -> None:
    """Drop the views, both tables and the enums, refusing while a review exists.

    A review is what a guardian wrote about a class and cannot be rebuilt,
    and a reply hangs off one, so any review blocks the downgrade.

    :return: None
    :raises RuntimeError: A review exists
    """
    bind = op.get_bind()
    reviews = bind.execute(sa.text("SELECT count(*) FROM review")).scalar()
    if reviews:
        raise RuntimeError(
            f"Cannot downgrade 0045: {reviews} review(s) that guardians wrote "
            "would be lost. Refusing."
        )
    for name in reversed(VIEWS):
        op.execute(sa.text(f"DROP VIEW {name}"))
    op.drop_table("review_reply")
    op.drop_table("review")
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(bind)
