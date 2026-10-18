"""Step 2's own check: the runner is ready.

A Red step is invalid without a runnable command, so this is the first
thing that must work. It asserts the container migrated from zero, that
the restricted role exists, and that the two shells are present and
empty -- "empty is not absent" is the whole point of BR6.1.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import APP_ROLE

OWNED_TABLES = (
    "account",
    "profile",
    "otp_request",
    "verify_attempt",
    "refresh_token",
    "rate_limit_counter",
    "auth_audit_log",
)

SHELL_TABLES = ("owner", "enrollment")

#: The tables U4 adds. Listed so the from-zero run asserts they exist.
U4_TABLES = ("batch", "batch_subject", "schedule_slot", "hidden_batch_preference")


def test_the_migration_created_every_owned_table(restricted_session: Session) -> None:
    present = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    }
    assert set(OWNED_TABLES) <= present


def test_the_two_shells_exist_and_are_empty(restricted_session: Session) -> None:
    # Empty is not absent. A query against a table that does not exist
    # fails, so lens resolution needs both to exist [BR6.1].
    for table in SHELL_TABLES:
        count = restricted_session.execute(
            sa.text(f"SELECT count(*) FROM {table}")  # noqa: S608  a fixed literal
        ).scalar_one()
        assert count == 0


def test_the_migration_created_this_units_tables(restricted_session: Session) -> None:
    present = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    }
    assert set(U4_TABLES) <= present


def test_the_schema_is_at_the_head_revision(restricted_session: Session) -> None:
    revision = restricted_session.execute(
        sa.text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    assert revision == "0002"


def test_the_restricted_role_exists(restricted_session: Session) -> None:
    exists = restricted_session.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
        {"role": APP_ROLE},
    ).scalar_one_or_none()
    assert exists == 1
