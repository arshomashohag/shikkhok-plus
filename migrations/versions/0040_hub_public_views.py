"""The public hub's views, search columns and reader grants.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-17

Public pages read **only** the four views this revision creates, and only
as ``shikkhok_hub_reader``:

* ``hub_public_owner`` -- published owner listings;
* ``hub_public_batch`` -- batch listings that are published, whose batch is
  active, AND whose owner listing is published. Unpublishing an owner leaves
  its batch rows ``published``, so all three are checked here;
* ``hub_public_teacher_name`` -- the names of a centre's members who
  accepted, are not revoked, agreed to be named, and teach a slot of a
  visible batch;
* ``hub_public_area`` -- ``bd_area`` as it stands.

**A view runs with its owner's rights and bypasses row-level security**, so
what a view selects is the boundary. None reads ``profile``, ``account``,
``enrollment``, ``student``, ``payment_method``, ``batch.name`` or
``owner_member.invited_phone``. Each is ``security_barrier`` so a caller's
predicate cannot be pushed beneath the view's own filter and observe rows
it excludes.

The "Runs classes" badge counts accepted seats in ``enrollment``, which no
view may read, so it is stored: ``owner_listing.runs_classes``, set by the
application from ``app.hub.listings.badge`` on save and publish, and daily
by ``app.hub.listings.badge_commands``.

Search: ``owner_listing.search_text`` gains the owner-entered Latin name and
the qualifications; ``batch_listing`` gains its own vector over its title,
both descriptions and its subject tags. PostgreSQL 16 cannot alter a
generated column's expression, so the owner vector is dropped and re-added.

A generated column's expression must be immutable, and ``array_to_string``
is only ``STABLE``: it is generic over element types, some of whose text
form depends on settings such as ``DateStyle``. A ``varchar`` element's text
form depends on nothing, so :data:`TAGS_FUNCTION` wraps the call for
``varchar[]`` alone and is declared ``IMMUTABLE`` truthfully.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.roles import HUB_READER_ROLE

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``0036``'s owner vector, restored by the downgrade.
OLD_OWNER_SEARCH: Final[str] = (
    "to_tsvector('simple', coalesce(public_name, '') || ' ' || "
    "coalesce(headline_en, '') || ' ' || coalesce(headline_bn, ''))"
)

#: The text normaliser both vectors apply, as the query side does.
NORM_FUNCTION: Final[str] = "hub_search_norm"

#: Its definition: strip zero-width characters, NFC, Bangla digits to Latin.
#: The same steps, in the same order, as
#: ``app.hub.public.normalise.query_terms`` applies to a query, so a word
#: indexed here and the same word typed into the search box agree whatever
#: digit set or composition either side used. Escapes, not literal
#: characters, so the invisible ones stay visible in review.
NORM_DEFINITION: Final[str] = (
    f"CREATE FUNCTION {NORM_FUNCTION}(t text) RETURNS text "
    "LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
    "AS $$ SELECT translate(normalize(translate(t, "
    "E'\\u200B\\u200C\\u200D\\uFEFF', ''), NFC), "
    "E'\\u09E6\\u09E7\\u09E8\\u09E9\\u09EA\\u09EB\\u09EC\\u09ED\\u09EE"
    "\\u09EF', '0123456789') $$"
)

#: The owner vector: both names, both headlines and the qualifications.
OWNER_SEARCH: Final[str] = (
    f"to_tsvector('simple', {NORM_FUNCTION}(coalesce(public_name, '') || ' ' || "
    "coalesce(public_name_latin, '') || ' ' || "
    "coalesce(headline_en, '') || ' ' || coalesce(headline_bn, '') || ' ' || "
    "coalesce(qualifications, '')))"
)

#: ``array_to_string`` for ``varchar[]`` only, so it may be immutable.
TAGS_FUNCTION: Final[str] = "hub_tags_text"

#: The batch vector: the public title, both descriptions and the tags.
BATCH_SEARCH: Final[str] = (
    f"to_tsvector('simple', {NORM_FUNCTION}(coalesce(public_title, '') || ' ' || "
    "coalesce(description_en, '') || ' ' || coalesce(description_bn, '') || "
    f"' ' || {TAGS_FUNCTION}(subject_tags)))"
)

#: Each view's body, in creation order.
VIEWS: Final[dict[str, str]] = {
    "hub_public_owner": """
        SELECT l.slug, l.public_name, l.public_name_latin, o.kind,
               l.headline_en, l.headline_bn, l.bio_en, l.bio_bn,
               l.qualifications, l.teaching_mode, l.district_code,
               l.upazila_code,
               CASE WHEN o.kind = 'organisation' THEN l.street_address END
                   AS street_address,
               l.public_contact_phone, l.runs_classes, l.published_at,
               l.search_text, l.owner_id
        FROM owner_listing l
        JOIN owner o ON o.id = l.owner_id
        WHERE l.status = 'published'
    """,
    "hub_public_batch": """
        SELECT ol.slug AS owner_slug, bl.slug, bl.public_title,
               bl.description_en, bl.description_bn,
               bl.syllabus_en, bl.syllabus_bn, bl.class_levels,
               bl.curriculum, bl.subject_tags, bl.mode, bl.admissions,
               CASE WHEN bl.show_fee THEN bt.default_fee END AS fee,
               CASE WHEN bl.show_schedule THEN (
                   SELECT coalesce(
                       jsonb_agg(
                           jsonb_build_object(
                               'weekday', s.weekday,
                               'start', to_char(s.start_time, 'HH24:MI'),
                               'end', to_char(s.end_time, 'HH24:MI')
                           )
                           ORDER BY s.weekday, s.start_time, s.end_time
                       ),
                       '[]'::jsonb
                   )
                   FROM schedule_slot s WHERE s.batch_id = bl.batch_id
               ) END AS schedule,
               bl.search_text, bl.batch_id
        FROM batch_listing bl
        JOIN batch bt ON bt.id = bl.batch_id
        JOIN owner_listing ol ON ol.owner_id = bl.owner_id
        WHERE bl.status = 'published' AND bt.active
          AND ol.status = 'published'
    """,
    "hub_public_teacher_name": """
        SELECT DISTINCT s.batch_id, m.display_name AS name
        FROM schedule_slot s
        JOIN owner_member m ON m.id = s.teacher_member_id
        JOIN batch_listing bl ON bl.batch_id = s.batch_id
        JOIN batch bt ON bt.id = bl.batch_id
        JOIN owner_listing ol ON ol.owner_id = bl.owner_id
        WHERE m.owner_id = bl.owner_id
          AND m.decision = 'accepted' AND m.revoked_at IS NULL
          AND m.public_name_consent_at IS NOT NULL
          AND bl.status = 'published' AND bt.active
          AND ol.status = 'published'
    """,
    "hub_public_area": """
        SELECT code, kind, parent_code, name_en, name_bn FROM bd_area
    """,
}


def upgrade() -> None:
    """Add the columns, rebuild the owner vector, create and grant the views.

    :return: None
    """
    op.add_column(
        "owner_listing",
        sa.Column("public_name_latin", sa.String(120), nullable=True),
    )
    op.add_column(
        "owner_listing",
        sa.Column(
            "runs_classes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(sa.text(NORM_DEFINITION))
    _replace_owner_search(OWNER_SEARCH)
    op.execute(
        sa.text(
            f"CREATE FUNCTION {TAGS_FUNCTION}(tags varchar[]) RETURNS text "
            "LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
            "AS $$ SELECT array_to_string(tags, ' ') $$"
        )
    )
    op.add_column(
        "batch_listing",
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(BATCH_SEARCH, persisted=True),
        ),
    )
    op.create_index(
        "ix_batch_listing_search_text",
        "batch_listing",
        ["search_text"],
        postgresql_using="gin",
    )

    for name, body in VIEWS.items():
        op.execute(sa.text(f"CREATE VIEW {name} WITH (security_barrier) AS {body}"))
        # The reader is the only grantee. The application role reaches the
        # views too, but only by inheritance: ``0034`` made it a member of
        # the reader so it can ``SET LOCAL ROLE``, and a member inherits
        # its role's grants. Granting the application role directly would
        # add nothing and would read as a second, unreviewed audience.
        op.execute(sa.text(f"GRANT SELECT ON {name} TO {HUB_READER_ROLE}"))


def _replace_owner_search(expression: str) -> None:
    """Drop the owner vector and its index, and add them back computed anew.

    :param expression: The generated column's expression
    :return: None
    """
    op.drop_index("ix_owner_listing_search_text", table_name="owner_listing")
    op.drop_column("owner_listing", "search_text")
    op.add_column(
        "owner_listing",
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
        ),
    )
    op.create_index(
        "ix_owner_listing_search_text",
        "owner_listing",
        ["search_text"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop the views and the new columns, refusing while a Latin name is held.

    A Latin name is what an owner typed and cannot be rebuilt; the badge
    and both vectors are derived and can.

    :return: None
    :raises RuntimeError: An owner listing carries a Latin name
    """
    held = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM owner_listing WHERE public_name_latin IS NOT NULL"
            )
        )
        .scalar()
    )
    if held:
        raise RuntimeError(
            f"Cannot downgrade 0040: {held} listing(s) hold a Latin name an "
            "owner typed, which the downgrade would erase. Refusing."
        )
    for name in reversed(VIEWS):
        op.execute(sa.text(f"DROP VIEW {name}"))
    op.drop_index("ix_batch_listing_search_text", table_name="batch_listing")
    op.drop_column("batch_listing", "search_text")
    op.execute(sa.text(f"DROP FUNCTION {TAGS_FUNCTION}(varchar[])"))
    _replace_owner_search(OLD_OWNER_SEARCH)
    op.execute(sa.text(f"DROP FUNCTION {NORM_FUNCTION}(text)"))
    op.drop_column("owner_listing", "runs_classes")
    op.drop_column("owner_listing", "public_name_latin")
