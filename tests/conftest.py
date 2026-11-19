"""The database fixtures every integration test in this Bolt depends on.

**The restricted session is the load-bearing fixture.** Connecting as
``postgres`` would silently void the entire privacy suite: superusers and
table owners bypass row-level security, so every probe would pass against
a missing policy. The meta-test in ``tests/privacy`` runs first precisely
because this fixture is easy to get wrong in a way nothing else detects.

The container migrates with **Alembic from zero** rather than loading a
schema dump, which gives the migration path continuous exercise at no
extra cost.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import mfa_crypto, passwords
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.tokens import JWT_ACTIVE_KID_ENV, JWT_KEYS_ENV, issue_pair
from app.db.roles import APP_ROLE

#: The password the restricted role connects with inside the test
#: container. A test-only value for a container that is destroyed with the
#: session; it is not a deployment credential.
RESTRICTED_PASSWORD = "test-only-restricted"  # noqa: S105

#: The scrypt costs production uses, read before anything lowers them, so
#: :func:`production_scrypt` can put them back.
_PRODUCTION_SCRYPT: dict[tuple[object, str], int] = {
    (passwords, "_N"): passwords._N,
    (passwords, "_R"): passwords._R,
    (passwords, "_P"): passwords._P,
    (mfa_crypto, "_SCRYPT_N"): mfa_crypto._SCRYPT_N,
    (mfa_crypto, "_SCRYPT_R"): mfa_crypto._SCRYPT_R,
    (mfa_crypto, "_SCRYPT_P"): mfa_crypto._SCRYPT_P,
}

#: The costs every other test hashes at. N=16 rather than 1024, because
#: ``scrypt$1024$8$1`` is the "old parameters" example the rehash test
#: needs to stay old.
_TEST_SCRYPT: dict[tuple[object, str], int] = {
    (passwords, "_N"): 2**4,
    (passwords, "_P"): 1,
    (mfa_crypto, "_SCRYPT_N"): 2**4,
}


@pytest.fixture(autouse=True, scope="session")
def _test_cost_scrypt() -> Iterator[None]:
    """Hash passwords and recovery codes at a test-only cost.

    Production scrypt is ~160 ms a password hash, and every sign-up,
    sign-in and wrong-password test pays it, often more than once: about
    a quarter of the account and auth suites' time. What those tests
    assert is the flow, not the cost. The cost itself is covered by the
    tests that take :func:`production_scrypt`.

    :return: A context manager that restores the module values after
    """
    with pytest.MonkeyPatch.context() as patch:
        for (module, name), value in _TEST_SCRYPT.items():
            patch.setattr(module, name, value)
        yield


@pytest.fixture
def production_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put production's scrypt costs back for one test.

    :param monkeypatch: The patcher, which undoes this after the test
    :return: None
    """
    for (module, name), value in _PRODUCTION_SCRYPT.items():
        monkeypatch.setattr(module, name, value)


def _require_docker() -> None:
    """Skip the integration suite when no Docker daemon is reachable.

    **Except in CI, where it fails instead** [C-37]. A skip exits 0
    exactly as a pass does, so a runner that lost Docker would report the
    suite green having run none of the row-level-security probes. GitHub
    Actions sets ``CI=true`` on every runner; locally the skip stays, so
    the unit half still runs on a machine without Docker.

    :return: None
    """
    import shutil
    import subprocess

    def unavailable() -> None:
        """Skip, or fail under CI.

        :return: None
        """
        reason = "integration tests need a Docker daemon"
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(f"{reason}, and CI must run them", pytrace=False)
        pytest.skip(reason, allow_module_level=True)

    if shutil.which("docker") is None:
        unavailable()
        return
    probe = subprocess.run(
        ["docker", "info"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        unavailable()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a PostgreSQL 16 container and yield its owner URL.

    A real PostgreSQL rather than SQLite, because row-level security,
    ``NUMERIC(12,2)``, ``ON CONFLICT DO NOTHING`` and partial indexes are
    the behaviours under test and SQLite emulates none of them faithfully.

    **One container per pytest-xdist worker**, because a session fixture
    runs once per worker process. That is deliberate: migrations create
    cluster-wide roles and the migration tests alter them, so two workers
    sharing a cluster could see each other's role changes mid-test.

    :return: A context manager yielding the owner connection URL
    """
    _require_docker()
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """Migrate the container from zero with Alembic.

    :param postgres_url: The owner connection URL
    :return: The same URL, with the schema applied
    """
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url)
    os.environ.setdefault("SHIKKHOKPLUS_DATABASE_URL", postgres_url)
    command.upgrade(config, "head")

    owner = sa.create_engine(postgres_url, future=True)
    with owner.begin() as connection:
        # ALTER ROLE is a utility statement and cannot take a bind
        # parameter, so the literal is quoted by the driver instead. Both
        # the role name and the password are fixed module constants, never
        # request input.
        quoted = sa.String().literal_processor(dialect=connection.dialect)(
            RESTRICTED_PASSWORD
        )
        connection.execute(sa.text(f"ALTER ROLE {APP_ROLE} WITH PASSWORD {quoted}"))
    owner.dispose()
    return postgres_url


@pytest.fixture(scope="session")
def restricted_url(migrated_url: str) -> str:
    """Build the URL the restricted role connects with.

    :param migrated_url: The migrated owner URL
    :return: The same database, reached as the restricted role
    """
    url = sa.engine.make_url(migrated_url)
    return str(
        url.set(username=APP_ROLE, password=RESTRICTED_PASSWORD).render_as_string(
            hide_password=False
        )
    )


@pytest.fixture(scope="session")
def restricted_engine(restricted_url: str) -> Iterator[Engine]:
    """Yield an engine connected as the **restricted** role.

    :param restricted_url: The restricted-role URL
    :return: A context manager yielding the engine
    """
    engine = sa.create_engine(restricted_url, future=True, poolclass=sa.pool.NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(migrated_url: str) -> Iterator[Engine]:
    """Yield an engine connected as the table **owner**.

    Used only to arrange fixture data that the restricted role's policy
    would otherwise deny, and never to make an assertion -- an assertion
    made as the owner proves nothing about the policy.

    :param migrated_url: The migrated owner URL
    :return: A context manager yielding the engine
    """
    engine = sa.create_engine(migrated_url, future=True, poolclass=sa.pool.NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def restricted_session(restricted_engine: Engine) -> Iterator[Session]:
    """Yield a session connected as the RESTRICTED role, not postgres.

    :param restricted_engine: The restricted-role engine
    :return: A context manager yielding the session
    """
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def owner_session(owner_engine: Engine) -> Iterator[Session]:
    """Yield a session connected as the table owner, for arrangement only.

    :param owner_engine: The owner engine
    :return: A context manager yielding the session
    """
    factory = sessionmaker(bind=owner_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    """Empty the owned tables between integration tests.

    Only for tests that actually took a database fixture, so the pure unit
    suites pay nothing for it.

    :param request: The pytest request, used to detect database fixtures
    :return: A context manager
    """
    database_fixtures = {
        "restricted_session",
        "owner_session",
        "restricted_engine",
        "owner_engine",
    }
    if not database_fixtures & set(request.fixturenames):
        yield
        return

    # Requested before the test runs: pytest deprecates asking for a
    # fixture during teardown.
    engine = request.getfixturevalue("owner_engine")

    yield

    with engine.begin() as connection:
        # The table list is DERIVED from the schema, not maintained by
        # hand. A hand-kept list silently stops emptying a table a
        # later migration adds, and the leak shows up as a test that
        # passes alone and fails in sequence -- which is how
        # staging_sms_outbox was found leaking between tests.
        #
        # Deriving it is also strictly more correct: every table the
        # schema has is one a test can write.
        #
        # ``bd_area`` is the exception: a fixed vocabulary seeded by its
        # migration that no test writes, so emptying it would leave
        # every later test an empty list.
        tables = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'bd_area')"
                )
            )
        ]
        if not tables:
            return
        # **DELETE, not TRUNCATE, because this runs after ~3,000 tests.**
        # TRUNCATE swaps every table's storage file and was ~110 ms a test
        # on 51 near-empty tables, about a third of the whole suite's time.
        # DELETE on tables holding a handful of rows costs ~3 ms.
        #
        # `replica` turns off the foreign-key and ordinary triggers for
        # this transaction only, so the tables can be emptied in any order
        # and the append-only guards do not refuse the clean-up. It needs
        # a superuser, which the owner engine is (the container's own
        # user). Nothing is asserted here, so the restricted-role rule for
        # the privacy suite is untouched.
        connection.execute(sa.text("SET LOCAL session_replication_role = replica"))
        # S608: every name is one pg_tables just returned, quoted as an
        # identifier; none comes from a test or a request.
        quote = connection.dialect.identifier_preparer.quote
        connection.execute(
            sa.text("; ".join(f"DELETE FROM {quote(t)}" for t in tables))  # noqa: S608
        )
        # What RESTART IDENTITY did: put each sequence those tables own
        # back at its start, so an id a test reads does not depend on what
        # ran before it. Only sequences that have been used need it.
        connection.execute(
            sa.text(
                "SELECT setval(s.oid::regclass, ps.start_value, false) "
                "FROM pg_class s "
                "JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i') "
                "JOIN pg_class t ON t.oid = d.refobjid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "JOIN pg_sequences ps "
                "  ON ps.schemaname = n.nspname AND ps.sequencename = s.relname "
                "WHERE s.relkind = 'S' AND n.nspname = 'public' "
                "AND t.relname = ANY(:tables) AND ps.last_value IS NOT NULL"
            ),
            {"tables": tables},
        )


@pytest.fixture
def api_client(
    restricted_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Build a client whose app uses the restricted test engine.

    :param restricted_engine: The non-superuser engine
    :param monkeypatch: The patcher
    :return: A context manager yielding the client
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:test-signing-key-padded-to-thirty-two")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    from app.main import create_app

    app = create_app()
    app.state.engine = restricted_engine
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str]]]:
    """Capture every text and email the null gateways are asked to send.

    Used by the contact suites [0037] to read a code back and to assert
    what a removed-contact notice said and when it was sent.

    :param monkeypatch: The patcher
    :return: A context manager yielding ``(destination, body)`` per send
    """
    from app.gateway.email import EmailMessage, NullEmailGateway
    from app.gateway.null import NullGateway

    captured: list[tuple[str, str]] = []
    sms = NullGateway.send
    email = NullEmailGateway.send

    def capture_sms(
        self: NullGateway, number: str, message: str, correlation_id: str
    ) -> object:
        """Record a text, then send as the null gateway would.

        :param self: The gateway
        :param number: The destination
        :param message: The body
        :param correlation_id: The request's correlation id
        :return: The null gateway's result
        """
        captured.append((number, message))
        return sms(self, number, message, correlation_id)

    def capture_email(
        self: NullEmailGateway, address: str, message: EmailMessage, cid: str
    ) -> object:
        """Record an email, then send as the null gateway would.

        :param self: The gateway
        :param address: The destination
        :param message: The rendered email
        :param cid: The request's correlation id
        :return: The null gateway's result
        """
        captured.append((address, message.text))
        return email(self, address, message, cid)

    monkeypatch.setattr(NullGateway, "send", capture_sms)
    monkeypatch.setattr(NullEmailGateway, "send", capture_email)
    yield captured


def bearer(session: Session, account_id: uuid.UUID) -> dict[str, str]:
    """Authorize as an account.

    :param session: A session to write the token family through
    :param account_id: The account
    :return: The header mapping
    """
    pair = issue_pair(session, account_id=account_id, correlation_id=uuid.uuid4())
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def reviews_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch hub reviews on for one test.

    Reviews are off by default, so every test exercising a gated route
    asks for this. Defined here, not per directory, because the gated
    routes are reached from ``tests/hub``, ``tests/governance``,
    ``tests/admin`` and ``tests/moderation`` alike.

    :param monkeypatch: Restores the environment after the test
    :return: None
    """
    from app.hub.public.settings import HUB_REVIEWS_ENV

    monkeypatch.setenv(HUB_REVIEWS_ENV, "on")


@pytest.fixture
def reviews_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch hub reviews off for one test, whatever the ambient environment.

    Off is the default only while the variable is unset; a developer or CI
    runner that exports ``SHIKKHOKPLUS_HUB_REVIEWS=on`` would otherwise
    turn every switch-off test into a switch-on one.

    :param monkeypatch: Restores the environment after the test
    :return: None
    """
    from app.hub.public.settings import HUB_REVIEWS_ENV

    monkeypatch.delenv(HUB_REVIEWS_ENV, raising=False)


@pytest.fixture
def enquiries_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch hub join requests on for one test.

    Join requests are off by default, so every test exercising a gated
    route asks for this. Defined here, beside :func:`reviews_on`, because
    the gated routes are reached from ``tests/enquiries``, ``tests/hub``
    and ``tests/governance`` alike.

    :param monkeypatch: Restores the environment after the test
    :return: None
    """
    from app.hub.public.settings import HUB_ENQUIRIES_ENV

    monkeypatch.setenv(HUB_ENQUIRIES_ENV, "on")


@pytest.fixture
def enquiries_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch hub join requests off for one test, whatever the environment.

    Off is the default only while the variable is unset; a developer or CI
    runner that exports ``SHIKKHOKPLUS_HUB_ENQUIRIES=on`` would otherwise
    turn every switch-off test into a switch-on one.

    :param monkeypatch: Restores the environment after the test
    :return: None
    """
    from app.hub.public.settings import HUB_ENQUIRIES_ENV

    monkeypatch.delenv(HUB_ENQUIRIES_ENV, raising=False)
