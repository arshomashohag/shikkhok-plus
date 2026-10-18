"""The meta-test. It runs FIRST, and everything else here depends on it.

**A privacy suite run as a superuser passes identically whether the policy
is correct, broken, or entirely absent** [BR3.3]. PostgreSQL documents
that superusers and table owners bypass row-level security, and the
default test-container connection is ``postgres`` -- a superuser. So the
strongest test obligation in the project would certify nothing.

This file is named ``test_rls_meta.py`` and lives first in
``tests/privacy`` alphabetically, which is the collection order pytest
uses. The ordering is not decoration: a probe suite that runs before this
check has no standing to report a pass.

Three conditions, each of which independently voids the suite:

1. ``current_user`` is a superuser -- RLS is bypassed entirely.
2. ``row_security`` is off for this session -- the policy is not applied.
3. No policy exists on ``profile`` -- there is nothing to apply.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.roles import APP_ROLE


def test_the_suite_does_not_connect_as_a_superuser(
    restricted_session: Session,
) -> None:
    is_superuser = restricted_session.execute(
        sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar_one()
    assert is_superuser is False, (
        "The privacy suite is connected as a SUPERUSER. Every probe below "
        "would pass against a missing policy [project.md NEVER, BR3.3]."
    )


def test_the_suite_connects_as_the_restricted_role(
    restricted_session: Session,
) -> None:
    current = restricted_session.execute(sa.text("SELECT current_user")).scalar_one()
    assert current == APP_ROLE


def test_the_suite_does_not_own_the_table(restricted_session: Session) -> None:
    # A table OWNER bypasses RLS just as a superuser does, and unlike
    # superuser status this one is easy to acquire by accident -- the
    # migration runs as the owner, so an application connecting with the
    # same credentials inherits the bypass.
    owner = restricted_session.execute(
        sa.text(
            "SELECT tableowner FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'profile'"
        )
    ).scalar_one()
    assert owner != APP_ROLE


def test_row_security_is_on_for_this_session(restricted_session: Session) -> None:
    setting = restricted_session.execute(sa.text("SHOW row_security")).scalar_one()
    assert setting == "on"


def test_a_policy_exists_on_profile(restricted_session: Session) -> None:
    policies = [
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT policyname FROM pg_policies WHERE tablename = 'profile'")
        )
    ]
    assert policies, "No RLS policy on profile [BR3.2]."


def test_row_level_security_is_enabled_and_forced_on_profile(
    restricted_session: Session,
) -> None:
    # FORCE matters independently of ENABLE. Without it the policy does
    # not apply to the table's own owner -- so it would look present in
    # pg_policies and silently do nothing for the one connection most
    # likely to be used by mistake.
    enabled, forced = restricted_session.execute(
        sa.text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'profile'"
        )
    ).one()
    assert enabled is True
    assert forced is True
