"""``python -m app.db.commands set-app-role-password`` [OPS-5].

Against the real container, because what is under test is what
PostgreSQL accepts at login afterwards -- a command that "ran" while the
role still could not sign in would leave every deployed API down.

**The role is cluster-wide and the rest of the session signs in as it**,
so every test that changes the password restores the suite's one in a
``finally``, through the command itself. That restore doubles as the
idempotence check: the command is run again against a role it already
configured.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa

from app.db.commands import APP_DB_PASSWORD_ENV, main
from app.db.roles import APP_ROLE
from app.db.session import DATABASE_URL_ENV, MIGRATION_DATABASE_URL_ENV
from tests.conftest import RESTRICTED_PASSWORD

#: A password with both quote characters and a backslash, so a command
#: that interpolated it unquoted would fail or, worse, run something else.
AWKWARD = 'it\'s a "test" \\ only-password'


def _signs_in(owner_url: str, password: str) -> bool:
    """Try to sign in as the restricted role.

    :param owner_url: The container's owner URL, for host and database
    :param password: The password to try
    :return: True when the login succeeds
    """
    url = sa.engine.make_url(owner_url).set(username=APP_ROLE, password=password)
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            return connection.execute(sa.text("SELECT current_user")).scalar_one() == (
                APP_ROLE
            )
    except sa.exc.OperationalError:
        return False
    finally:
        engine.dispose()


@pytest.fixture
def restores_password(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Yield the owner URL, and put the suite's password back afterwards.

    :param migrated_url: The migrated owner URL
    :param monkeypatch: The patcher
    :return: A context manager yielding the owner URL
    """
    monkeypatch.setenv(MIGRATION_DATABASE_URL_ENV, migrated_url)
    try:
        yield migrated_url
    finally:
        monkeypatch.setenv(MIGRATION_DATABASE_URL_ENV, migrated_url)
        monkeypatch.setenv(APP_DB_PASSWORD_ENV, RESTRICTED_PASSWORD)
        assert main(["set-app-role-password"]) == 0
        assert _signs_in(migrated_url, RESTRICTED_PASSWORD)


def test_the_role_signs_in_with_the_new_password_and_not_the_old(
    restores_password: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After the command, exactly the new password works.

    :param restores_password: The owner URL, restored afterwards
    :param monkeypatch: The patcher
    :param capsys: Captures what the command printed
    :return: None
    """
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, AWKWARD)

    assert main(["set-app-role-password"]) == 0

    assert _signs_in(restores_password, AWKWARD)
    assert not _signs_in(restores_password, RESTRICTED_PASSWORD)
    captured = capsys.readouterr()
    printed = captured.out + captured.err
    assert AWKWARD not in printed
    # The container's owner password is the same word as its user and
    # database, so the check is on the URL's credential part instead.
    owner = sa.engine.make_url(restores_password)
    assert f"{owner.username}:{owner.password}@" not in printed
    assert f"{owner.username}:***@" in printed


def test_running_it_twice_is_harmless(
    restores_password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A boot script may run it every boot.

    :param restores_password: The owner URL, restored afterwards
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, AWKWARD)

    assert main(["set-app-role-password"]) == 0
    assert main(["set-app-role-password"]) == 0

    assert _signs_in(restores_password, AWKWARD)


def test_the_server_stores_a_verifier_not_the_password(
    restores_password: str, monkeypatch: pytest.MonkeyPatch, owner_engine: sa.Engine
) -> None:
    """The plain text never reached the server, so never its log.

    :param restores_password: The owner URL, restored afterwards
    :param monkeypatch: The patcher
    :param owner_engine: The owner engine, which can read ``pg_authid``
    :return: None
    """
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, AWKWARD)

    assert main(["set-app-role-password"]) == 0

    with owner_engine.connect() as connection:
        stored = connection.execute(
            sa.text("SELECT rolpassword FROM pg_authid WHERE rolname = :role"),
            {"role": APP_ROLE},
        ).scalar_one()
    assert stored.startswith("SCRAM-SHA-256$")


@pytest.mark.parametrize("missing", [MIGRATION_DATABASE_URL_ENV, APP_DB_PASSWORD_ENV])
def test_each_variable_is_required(
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    """Unset, the command refuses loudly and changes nothing.

    ``SHIKKHOKPLUS_DATABASE_URL`` is set to the OWNER here on purpose:
    a command falling back to it would succeed, and this would fail.

    :param migrated_url: The migrated owner URL
    :param monkeypatch: The patcher
    :param capsys: Captures what the command printed
    :param missing: The variable left unset
    :return: None
    """
    monkeypatch.setenv(DATABASE_URL_ENV, migrated_url)
    monkeypatch.setenv(MIGRATION_DATABASE_URL_ENV, migrated_url)
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, AWKWARD)
    monkeypatch.delenv(missing)

    assert main(["set-app-role-password"]) == 1

    assert missing in capsys.readouterr().err
    assert _signs_in(migrated_url, RESTRICTED_PASSWORD)


def test_a_blank_password_is_refused(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whitespace is not a password.

    :param migrated_url: The migrated owner URL
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(MIGRATION_DATABASE_URL_ENV, migrated_url)
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, "   ")

    assert main(["set-app-role-password"]) == 1
    assert _signs_in(migrated_url, RESTRICTED_PASSWORD)


def test_a_failed_connection_prints_no_secret(
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wrong owner password fails with the URL redacted.

    :param migrated_url: The migrated owner URL
    :param monkeypatch: The patcher
    :param capsys: Captures what the command printed
    :return: None
    """
    wrong = sa.engine.make_url(migrated_url).set(password="wrong-owner-secret")  # noqa: S106  a throwaway test value
    monkeypatch.setenv(
        MIGRATION_DATABASE_URL_ENV, wrong.render_as_string(hide_password=False)
    )
    monkeypatch.setenv(APP_DB_PASSWORD_ENV, AWKWARD)

    assert main(["set-app-role-password"]) == 1

    printed = capsys.readouterr()
    assert "***" in printed.err
    assert "wrong-owner-secret" not in printed.out + printed.err
    assert AWKWARD not in printed.out + printed.err


def test_an_unknown_verb_is_a_usage_error() -> None:
    """No verb, or another verb, does nothing.

    :return: None
    """
    assert main([]) == 2
    assert main(["set-password"]) == 2
