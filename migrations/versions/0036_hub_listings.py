"""The public hub's listings, reports and moderation record.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-15

Four tables and one column, all dark until H2's views grant the hub reader
anything: ``owner_listing`` and ``batch_listing`` are what an owner chooses
to publish, ``hub_report`` is one reader's complaint about one target, and
``hub_moderation_event`` is the closed-vocabulary trail of what moderation
did.

**Rules that are shapes, not code.**

* A live listing has a slug and a name; a draft needs neither. The slug is
  three to sixty lower-case ASCII letters, digits or hyphens.
* ``street_address`` is for a coaching centre only. A trigger refuses it
  for a solo teacher, because a teacher's address is their home.
* ``batch_listing.owner_id`` must equal its batch's owner; a trigger keeps
  it so, which lets the hub read a listing without a join.
* ``show_fee`` and ``show_schedule`` have no default, so omitting one is an
  error rather than a quiet choice about what to disclose.
* ``hub_moderation_event`` carries no free text, and for the application
  role it is append-only: no ``UPDATE`` at all, and ``DELETE`` only past the
  twelve-month retention its disposition declares, the same shape as
  ``auth_audit_log`` in ``0015``.

``owner_member.public_name_consent_at`` records when a centre's member
agreed to be named on the centre's public page.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

from app.db.roles import APP_ROLE

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each enum's name and labels, in creation order.
ENUMS: Final[dict[str, tuple[str, ...]]] = {
    "hub_listing_status": ("draft", "published", "hidden", "suspended"),
    "hub_admissions": ("open", "waitlist", "closed"),
    "hub_teaching_mode": ("in_person", "home_visit", "online"),
    "hub_report_reason": (
        "personal_info",
        "child_safety",
        "abusive",
        "fake",
        "misleading",
        "other",
    ),
    "hub_report_target": ("listing", "media", "review", "reply"),
    "hub_report_status": ("open", "upheld", "dismissed"),
    "hub_moderation_event_kind": (
        "report_filed",
        "report_upheld",
        "report_dismissed",
        "listing_suspended",
        "listing_unsuspended",
    ),
}

#: A slug: 3 to 60 lower-case ASCII letters, digits or hyphens.
SLUG_CHECK: Final[str] = "slug IS NULL OR slug ~ '^[a-z0-9-]{3,60}$'"

#: The class levels a batch may teach.
CLASS_LEVELS: Final[tuple[str, ...]] = (
    *(f"class_{n}" for n in range(1, 13)),
    "ssc",
    "hsc",
    "admission",
    "o_level",
    "a_level",
    "other",
)

#: The curricula a batch may follow.
CURRICULA: Final[tuple[str, ...]] = (
    "national_bangla",
    "national_english",
    "english_medium",
    "madrasah",
    "other",
)

#: How long a moderation event is kept, as the append-only trigger's floor.
EVENT_DELETE_FLOOR: Final[str] = "364 days"

_STREET_FUNCTION: Final[str] = "hub_street_address_centre_only"
_OWNER_FUNCTION: Final[str] = "hub_batch_listing_owner_matches"
_EVENT_FUNCTION: Final[str] = "hub_moderation_event_retention_floor"

#: The indexed text of a listing; ``simple`` keeps Bangla and English alike.
SEARCH_TEXT: Final[str] = (
    "to_tsvector('simple', coalesce(public_name, '') || ' ' || "
    "coalesce(headline_en, '') || ' ' || coalesce(headline_bn, ''))"
)


def _enum(name: str) -> postgresql.ENUM:
    """Build the column type for an existing enum, without creating it.

    :param name: The type's name
    :return: The column type
    """
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _len_check(column: str, limit: int, table: str) -> sa.CheckConstraint:
    """Build a length check on a nullable text column.

    :param column: The column
    :param limit: The most characters it may hold
    :param table: The table, to name the constraint
    :return: The constraint
    """
    return sa.CheckConstraint(
        f"{column} IS NULL OR char_length({column}) <= {limit}",
        name=conv(f"ck_{table}_{column}"),
    )


def _quoted(values: Sequence[str]) -> str:
    """Render labels as a SQL array literal of ``varchar``.

    :param values: The labels
    :return: ``ARRAY['a', 'b']::varchar[]``
    """
    return "ARRAY[" + ", ".join(f"'{v}'" for v in values) + "]::varchar[]"


def upgrade() -> None:
    """Create the enums, the four tables, the guards and the grants.

    :return: None
    """
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name).create(op.get_bind())

    op.add_column(
        "owner_member",
        sa.Column("public_name_consent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "owner_listing",
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "owner.id", ondelete="CASCADE", name="fk_owner_listing_owner"
            ),
            primary_key=True,
        ),
        sa.Column("slug", sa.String(60), nullable=True),
        sa.Column(
            "status",
            _enum("hub_listing_status"),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("public_name", sa.String(120), nullable=False),
        sa.Column("headline_en", sa.Text(), nullable=True),
        sa.Column("headline_bn", sa.Text(), nullable=True),
        sa.Column("bio_en", sa.Text(), nullable=True),
        sa.Column("bio_bn", sa.Text(), nullable=True),
        sa.Column("qualifications", sa.Text(), nullable=True),
        sa.Column(
            "teaching_mode",
            postgresql.ARRAY(_enum("hub_teaching_mode")),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "district_code",
            sa.String(12),
            sa.ForeignKey("bd_area.code", name="fk_owner_listing_district_code"),
            nullable=True,
        ),
        sa.Column(
            "upazila_code",
            sa.String(12),
            sa.ForeignKey("bd_area.code", name="fk_owner_listing_upazila_code"),
            nullable=True,
        ),
        sa.Column("street_address", sa.Text(), nullable=True),
        sa.Column("public_contact_phone", sa.String(20), nullable=True),
        sa.Column("consent_version", sa.String(20), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consent_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name="fk_owner_listing_consent_by_account_id",
            ),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason_code", sa.String(40), nullable=True),
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_TEXT, persisted=True),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_owner_listing_slug"),
        sa.CheckConstraint(SLUG_CHECK, name=conv("ck_owner_listing_slug")),
        sa.CheckConstraint(
            "status = 'draft' OR slug IS NOT NULL",
            name=conv("ck_owner_listing_slug_when_live"),
        ),
        sa.CheckConstraint(
            "status = 'draft' OR length(trim(public_name)) > 0",
            name=conv("ck_owner_listing_name_when_live"),
        ),
        _len_check("headline_en", 140, "owner_listing"),
        _len_check("headline_bn", 140, "owner_listing"),
        _len_check("bio_en", 4000, "owner_listing"),
        _len_check("bio_bn", 4000, "owner_listing"),
        _len_check("qualifications", 1000, "owner_listing"),
        _len_check("street_address", 200, "owner_listing"),
    )
    op.create_index(
        "ix_owner_listing_status", "owner_listing", ["status"], unique=False
    )
    op.create_index(
        "ix_owner_listing_district_code", "owner_listing", ["district_code"]
    )
    op.create_index(
        "ix_owner_listing_search_text",
        "owner_listing",
        ["search_text"],
        postgresql_using="gin",
    )

    op.create_table(
        "batch_listing",
        sa.Column(
            "batch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "batch.id", ondelete="CASCADE", name="fk_batch_listing_batch"
            ),
            primary_key=True,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "owner.id", ondelete="CASCADE", name="fk_batch_listing_owner"
            ),
            nullable=False,
        ),
        sa.Column("slug", sa.String(60), nullable=True),
        sa.Column(
            "status",
            _enum("hub_listing_status"),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_bn", sa.Text(), nullable=True),
        sa.Column("syllabus_en", sa.Text(), nullable=True),
        sa.Column("syllabus_bn", sa.Text(), nullable=True),
        sa.Column(
            "class_levels",
            postgresql.ARRAY(sa.String(20)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("curriculum", sa.String(30), nullable=True),
        sa.Column(
            "subject_tags",
            postgresql.ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("mode", _enum("hub_teaching_mode"), nullable=True),
        sa.Column(
            "admissions",
            _enum("hub_admissions"),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("show_fee", sa.Boolean(), nullable=False),
        sa.Column("show_schedule", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(SLUG_CHECK, name=conv("ck_batch_listing_slug")),
        sa.CheckConstraint(
            "status = 'draft' OR slug IS NOT NULL",
            name=conv("ck_batch_listing_slug_when_live"),
        ),
        sa.CheckConstraint(
            f"class_levels <@ {_quoted(CLASS_LEVELS)}",
            name=conv("ck_batch_listing_class_levels"),
        ),
        sa.CheckConstraint(
            f"curriculum IS NULL OR curriculum IN "
            f"({', '.join(repr(c) for c in CURRICULA)})",
            name=conv("ck_batch_listing_curriculum"),
        ),
        _len_check("description_en", 4000, "batch_listing"),
        _len_check("description_bn", 4000, "batch_listing"),
        _len_check("syllabus_en", 4000, "batch_listing"),
        _len_check("syllabus_bn", 4000, "batch_listing"),
    )
    op.create_index(
        "uq_batch_listing_owner_slug",
        "batch_listing",
        ["owner_id", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )
    op.create_index("ix_batch_listing_owner_id", "batch_listing", ["owner_id"])
    op.create_index("ix_batch_listing_status", "batch_listing", ["status"])

    op.create_table(
        "hub_report",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_kind", _enum("hub_report_target"), nullable=False),
        sa.Column("target_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reporter_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="CASCADE",
                name="fk_hub_report_reporter_account_id",
            ),
            nullable=False,
        ),
        sa.Column("reason", _enum("hub_report_reason"), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "status",
            _enum("hub_report_status"),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decided_by_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name="fk_hub_report_decided_by_account_id",
            ),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "target_kind",
            "target_id",
            "reporter_account_id",
            name="uq_hub_report_target_reporter",
        ),
    )
    op.create_index(
        "ix_hub_report_status_created_at", "hub_report", ["status", "created_at"]
    )
    op.create_index(
        "ix_hub_report_reporter_account_id", "hub_report", ["reporter_account_id"]
    )

    op.create_table(
        "hub_moderation_event",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("event", _enum("hub_moderation_event_kind"), nullable=False),
        sa.Column("target_kind", _enum("hub_report_target"), nullable=False),
        sa.Column("target_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_admin_account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey(
                "account.id",
                ondelete="SET NULL",
                name="fk_hub_moderation_event_actor_admin_account_id",
            ),
            nullable=True,
        ),
        sa.Column("decision_code", sa.String(40), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "decision_code IS NULL OR decision_code ~ '^[a-z][a-z0-9_]*$'",
            name=conv("ck_hub_moderation_event_decision_code"),
        ),
    )
    op.create_index("ix_hub_moderation_event_at", "hub_moderation_event", ["at"])
    op.create_index(
        "ix_hub_moderation_event_target",
        "hub_moderation_event",
        ["target_kind", "target_id"],
    )

    _create_guards()
    for table in ("owner_listing", "batch_listing", "hub_report"):
        op.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        )
    # Append-only for the application role: no UPDATE at all, and DELETE
    # only through the retention floor trigger below.
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, DELETE ON hub_moderation_event TO {APP_ROLE}")
    )


def _create_guards() -> None:
    """Create the three trigger functions and their triggers.

    :return: None
    """
    op.execute(
        sa.text(
            f"CREATE FUNCTION {_STREET_FUNCTION}() RETURNS trigger "  # noqa: S608
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "  IF NEW.street_address IS NOT NULL AND NOT EXISTS ("
            "    SELECT 1 FROM owner WHERE id = NEW.owner_id "
            "    AND kind = 'organisation') THEN "
            "    RAISE EXCEPTION 'a street address is for a coaching centre only' "
            "      USING ERRCODE = 'check_violation'; "
            "  END IF; "
            "  RETURN NEW; "
            "END $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_owner_listing_street_address "
            "BEFORE INSERT OR UPDATE ON owner_listing "
            f"FOR EACH ROW EXECUTE FUNCTION {_STREET_FUNCTION}()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION {_OWNER_FUNCTION}() RETURNS trigger "  # noqa: S608
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "  IF NEW.owner_id IS DISTINCT FROM "
            "     (SELECT owner_id FROM batch WHERE id = NEW.batch_id) THEN "
            "    RAISE EXCEPTION 'listing owner does not match the batch owner' "
            "      USING ERRCODE = 'check_violation'; "
            "  END IF; "
            "  RETURN NEW; "
            "END $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_batch_listing_owner_matches "
            "BEFORE INSERT OR UPDATE ON batch_listing "
            f"FOR EACH ROW EXECUTE FUNCTION {_OWNER_FUNCTION}()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION {_EVENT_FUNCTION}() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ "
            "BEGIN "
            f"  IF current_user = '{APP_ROLE}' "
            f"     AND OLD.at >= now() - interval '{EVENT_DELETE_FLOOR}' "
            "  THEN "
            "    RAISE EXCEPTION 'hub_moderation_event row % is inside its "
            "retention window and cannot be deleted', OLD.id "
            "      USING ERRCODE = 'insufficient_privilege'; "
            "  END IF; "
            "  RETURN OLD; "
            "END $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_hub_moderation_event_retention_floor "
            "BEFORE DELETE ON hub_moderation_event "
            f"FOR EACH ROW EXECUTE FUNCTION {_EVENT_FUNCTION}()"
        )
    )


def downgrade() -> None:
    """Drop the tables, guards and enums, refusing while any listing exists.

    Listings are what owners chose to publish and cannot be rebuilt.

    :return: None
    """
    held = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM owner_listing) "
                "+ (SELECT count(*) FROM batch_listing)"
            )
        )
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"{held} listing(s) exist; downgrading would erase what owners "
            "chose to publish. Refusing."
        )
    op.drop_table("hub_moderation_event")
    op.drop_table("hub_report")
    op.drop_table("batch_listing")
    op.drop_table("owner_listing")
    for function in (_EVENT_FUNCTION, _OWNER_FUNCTION, _STREET_FUNCTION):
        op.execute(sa.text(f"DROP FUNCTION {function}()"))
    op.drop_column("owner_member", "public_name_consent_at")
    for name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(op.get_bind())
