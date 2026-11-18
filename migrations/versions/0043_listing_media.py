"""Owner photos: ``listing_media``, the object outbox and the public view.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-18

An owner uploads a photo for their own page (``batch_id`` NULL) or for one
batch's page. A row moves through seven statuses, ``media_status``:
``awaiting_upload`` -> ``processing`` -> ``pending_review`` -> ``approved``,
or off to ``rejected`` or ``withdrawn``; ``held`` is an approved photo taken
down at once by a child-safety or personal-information report while an
admin decides.

**``public_key`` exists exactly while a photo is approved.** It is 32 hex
digits of randomness naming the photo's public objects (``public/{key}/``)
and URL (``/m/{key}/{w}.webp``); a CHECK ties it to the status both ways,
so a photo that leaves ``approved`` cannot keep its URL in the row. A
restore after a hold mints a fresh key, so no cached URL comes back.

**Approved positions are unique per gallery** -- the owner's gallery and
each batch's -- through a partial index over ``coalesce(batch_id, nil)``,
because NULLs never collide in a plain unique index.

**``media_object_task`` is the bucket's deletion outbox.** A takedown, a
rejection, a withdrawal or an account deletion writes the prefixes to
delete in its own transaction, as ``0041``'s ``cdn_invalidation`` does for
the edge cache, and the drain deletes them. A prefix is CHECKed to exactly
one of four shapes, each naming one photo's objects: a prefix any wider
(``staged/`` alone, a traversal, another top-level folder) would let one
row empty the bucket.

**``hub_public_media`` reads ``hub_public_owner`` and ``hub_public_batch``**
rather than restating their filters, so a photo is public exactly where
its page is: approved, under a published owner listing, and for a batch
photo under a batch that view shows -- listing published, batch active,
owner listing published. The batch is matched on the owner's slug too, so
a row whose batch belongs to another owner shows on neither page. It is
``security_barrier`` and granted to the hub reader only, as ``0040``'s
views are; the reader is granted nothing on either table.

**A batch photo's batch must be its owner's**, held by a trigger in the
style of ``0036``'s ``batch_listing`` guard, on insert and on any update
of ``batch_id`` or ``owner_id``. ``width`` and ``height`` are INTEGER: the
decoder admits 40M pixels, which a 40000 x 1000 image is.

The application role may read, write and delete both tables.
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

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The statuses, in lifecycle order.
STATUSES: Final[tuple[str, ...]] = (
    "awaiting_upload",
    "processing",
    "pending_review",
    "approved",
    "rejected",
    "withdrawn",
    "held",
)

#: A canonical lower-case UUID, as ``str(uuid.UUID)`` renders a media id.
_UUID: Final[str] = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

#: The four prefix shapes: one quarantined object, or one photo's folder.
PREFIX_CHECK: Final[str] = (
    f"prefix ~ '^(quarantine/{_UUID}|(staged|archive)/{_UUID}/"
    "|public/[0-9a-f]{32}/)$'"
)

#: The batch-owner guard's function, as ``0036``'s guards for batch_listing.
OWNER_FUNCTION: Final[str] = "hub_listing_media_owner_matches"

#: The public view's body.
VIEW: Final[str] = """
    SELECT o.slug AS owner_slug, b.slug AS batch_slug, m.id AS media_id,
           m.public_key, m.width, m.height, m.widths, m.alt_en, m.alt_bn,
           m.position
    FROM listing_media m
    JOIN hub_public_owner o ON o.owner_id = m.owner_id
    LEFT JOIN hub_public_batch b
        ON b.batch_id = m.batch_id AND b.owner_slug = o.slug
    WHERE m.status = 'approved'
      AND (m.batch_id IS NULL OR b.batch_id IS NOT NULL)
"""


def upgrade() -> None:
    """Create the enum, both tables, the view and their grants.

    :return: None
    """
    postgresql.ENUM(*STATUSES, name="media_status").create(op.get_bind())
    op.create_table(
        "listing_media",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "owner.id", ondelete="CASCADE", name=conv("fk_listing_media_owner")
            ),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey(
                "batch.id", ondelete="CASCADE", name=conv("fk_listing_media_batch")
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*STATUSES, name="media_status", create_type=False),
            nullable=False,
            server_default=sa.text("'awaiting_upload'"),
        ),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.CHAR(32), nullable=True),
        # INTEGER, not SMALLINT: the decoder admits 40M pixels, so a
        # 40000 x 1000 image is valid and its width exceeds 32767.
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("widths", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("alt_en", sa.String(200), nullable=True),
        sa.Column("alt_bn", sa.String(200), nullable=True),
        sa.Column(
            "position",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("rejection_code", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("public_key", name=conv("uq_listing_media_public_key")),
        sa.CheckConstraint(
            "(status = 'approved') = (public_key IS NOT NULL)",
            name=conv("ck_listing_media_public_key_iff_approved"),
        ),
        sa.CheckConstraint(
            "public_key IS NULL OR public_key ~ '^[0-9a-f]{32}$'",
            name=conv("ck_listing_media_public_key"),
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name=conv("ck_listing_media_content_type"),
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 1 AND 8388608",
            name=conv("ck_listing_media_byte_size"),
        ),
        sa.CheckConstraint(
            "widths IS NULL OR widths <@ ARRAY[320, 960, 1600]::smallint[]",
            name=conv("ck_listing_media_widths"),
        ),
    )
    op.create_index("ix_listing_media_owner_id", "listing_media", ["owner_id"])
    op.create_index("ix_listing_media_batch_id", "listing_media", ["batch_id"])
    op.create_index(
        "uq_listing_media_approved_position",
        "listing_media",
        [
            "owner_id",
            sa.text("coalesce(batch_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "position",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "media_object_task",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("op", sa.String(8), nullable=False),
        sa.Column("prefix", sa.String(80), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.CheckConstraint("op IN ('delete')", name=conv("ck_media_object_task_op")),
        sa.CheckConstraint(PREFIX_CHECK, name=conv("ck_media_object_task_prefix")),
    )
    op.create_index(
        "ix_media_object_task_pending",
        "media_object_task",
        ["requested_at"],
        postgresql_where=sa.text("done_at IS NULL"),
    )

    # A batch photo's batch must be its owner's, as ``0036`` holds for
    # ``batch_listing``: quotas, the solo-owner deletion scope and the
    # upload service all key on ``owner_id``, so a row on another owner's
    # batch would be counted and deleted under the wrong owner.
    op.execute(
        sa.text(
            f"CREATE FUNCTION {OWNER_FUNCTION}() RETURNS trigger "  # noqa: S608
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "  IF NEW.batch_id IS NOT NULL AND NEW.owner_id IS DISTINCT FROM "
            "     (SELECT owner_id FROM batch WHERE id = NEW.batch_id) THEN "
            "    RAISE EXCEPTION 'media owner does not match the batch owner' "
            "      USING ERRCODE = 'check_violation'; "
            "  END IF; "
            "  RETURN NEW; "
            "END $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_listing_media_owner_matches "
            "BEFORE INSERT OR UPDATE OF batch_id, owner_id ON listing_media "
            f"FOR EACH ROW EXECUTE FUNCTION {OWNER_FUNCTION}()"
        )
    )

    for table in ("listing_media", "media_object_task"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )

    op.execute(
        sa.text(f"CREATE VIEW hub_public_media WITH (security_barrier) AS {VIEW}")
    )
    # The reader is the only grantee, as for ``0040``'s views: the
    # application role reaches it only by inheriting the reader's grants.
    op.execute(sa.text(f"GRANT SELECT ON hub_public_media TO {HUB_READER_ROLE}"))


def downgrade() -> None:
    """Drop the view, both tables and the enum, refusing while it would lose work.

    A photo row is what an owner uploaded and described, and an undone
    object task is the only record that a photo's objects must still be
    deleted from the bucket; neither can be rebuilt. Finished tasks can go.

    :return: None
    :raises RuntimeError: A photo exists, or an object deletion is not done
    """
    bind = op.get_bind()
    photos = bind.execute(sa.text("SELECT count(*) FROM listing_media")).scalar()
    pending = bind.execute(
        sa.text("SELECT count(*) FROM media_object_task WHERE done_at IS NULL")
    ).scalar()
    if photos or pending:
        raise RuntimeError(
            f"Cannot downgrade 0043: {photos} photo(s) and {pending} object "
            "deletion(s) not yet done would be lost. Refusing."
        )
    op.execute(sa.text("DROP VIEW hub_public_media"))
    op.drop_table("media_object_task")
    op.drop_table("listing_media")
    op.execute(sa.text(f"DROP FUNCTION {OWNER_FUNCTION}()"))
    postgresql.ENUM(name="media_status").drop(bind)
