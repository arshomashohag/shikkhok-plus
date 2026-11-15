"""The public hub's read-only database role.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-15

``shikkhok_hub_reader`` is the role public pages read as. It is
``NOLOGIN`` (nothing connects as it), ``NOSUPERUSER`` and ``NOBYPASSRLS``,
and the application role is made a member so a request can
``SET LOCAL ROLE`` into it for one transaction.

**It is granted nothing but ``USAGE`` on the schema.** Every table the hub
may read is a later, reviewed grant; a table nobody granted is refused
with ``InsufficientPrivilege`` rather than filtered.

Roles are cluster-wide, so creation is guarded by ``IF NOT EXISTS``, the
same way ``0001`` creates the application role.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.roles import APP_ROLE, HUB_READER_ROLE

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the role, make the application role a member, grant usage.

    :return: None
    """
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM pg_catalog.pg_roles
                    WHERE rolname = '{HUB_READER_ROLE}'
                ) THEN
                    CREATE ROLE {HUB_READER_ROLE}
                        NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(sa.text(f"GRANT {HUB_READER_ROLE} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {HUB_READER_ROLE}"))


def downgrade() -> None:
    """Revoke the membership and the schema usage, then drop the role if free.

    :return: None
    """
    op.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {HUB_READER_ROLE}"))
    op.execute(sa.text(f"REVOKE {HUB_READER_ROLE} FROM {APP_ROLE}"))
    # Roles are cluster-wide: another database in the cluster may still
    # hold a grant to this one, and PostgreSQL then refuses the drop. That
    # is tolerated and only that. A dependency in THIS database means a
    # later revision's grant failed to revert, so fail loudly rather than
    # leave a privileged role behind under a successful downgrade.
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                role_oid oid;
                here integer;
            BEGIN
                SELECT oid INTO role_oid FROM pg_catalog.pg_roles
                WHERE rolname = '{HUB_READER_ROLE}';
                IF role_oid IS NULL THEN
                    RETURN;
                END IF;
                SELECT count(*) INTO here FROM pg_catalog.pg_shdepend
                WHERE refclassid = 'pg_catalog.pg_authid'::regclass
                  AND refobjid = role_oid
                  AND dbid = (
                      SELECT oid FROM pg_catalog.pg_database
                      WHERE datname = current_database()
                  );
                IF here > 0 THEN
                    RAISE EXCEPTION
                        '{HUB_READER_ROLE} still holds % object(s) in %; '
                        'revert their grants before downgrading 0034',
                        here, current_database();
                END IF;
                BEGIN
                    DROP ROLE {HUB_READER_ROLE};
                EXCEPTION WHEN dependent_objects_still_exist THEN
                    RAISE NOTICE
                        '{HUB_READER_ROLE} kept: another database still '
                        'depends on it';
                END;
            END
            $$;
            """  # noqa: S608  fixed module constants
        )
    )
