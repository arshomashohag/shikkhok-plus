"""The outbox cannot exist in production, asserted three ways.

**Each mechanism is tested on its own**, because the whole point of
having three is that no single one is relied on. A test suite that only
proved "production has no route" would be satisfied by a build where
the writer still recorded OTPs to a table.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import ENVIRONMENT_ENV, ConfigurationError, check_startup_configuration
from app.gateway.outbox import (
    OUTBOX_FORCE_ENV,
    outbox_enabled,
    read_outbox,
    record_outbox,
)

# ---------------------------------------------------------------------------
# MECHANISM 1 -- the predicate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("environment", "flag", "expected"),
    [
        ("production", "1", False),
        ("production", "", False),
        ("staging", "1", True),
        ("staging", "", False),
        ("development", "1", True),
        ("", "1", False),
        ("Production", "1", False),
        ("staging ", "1", False),
    ],
)
def test_the_predicate_permits_only_an_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    flag: str,
    expected: bool,
) -> None:
    """Production is false whatever the flag says.

    The last two cases matter: a capitalised or space-padded
    environment name must not be read as permitted, because an
    environment variable set by hand is exactly where that happens.

    :param monkeypatch: The patcher
    :param environment: The environment name under test
    :param flag: The opt-in flag value
    :param expected: Whether the outbox should be enabled
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, environment)
    monkeypatch.setenv(OUTBOX_FORCE_ENV, flag)

    assert outbox_enabled() is expected


def test_the_predicate_is_read_fresh_not_captured_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process promoted to production loses the outbox immediately.

    A module-level constant would hold the value the process started
    with, so a redeploy that changed only the environment variable
    would keep serving codes until someone noticed.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    assert outbox_enabled() is True

    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    assert outbox_enabled() is False


# ---------------------------------------------------------------------------
# MECHANISM 2 -- the route is absent, not refusing.
# ---------------------------------------------------------------------------


def test_the_route_is_not_registered_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is nothing to reach, rather than a handler that refuses.

    An absent route cannot become a 200 through an unrelated change to
    a dependency or a middleware.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv("SHIKKHOKPLUS_GLOBAL_DAILY_SMS", "50")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv("SHIKKHOKPLUS_OTP_HMAC_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_ADAPTER", "bulksmsbd")

    # The startup check refuses this configuration, which is mechanism
    # three -- so to test mechanism TWO in isolation the environment is
    # production with the flag off.
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "")

    from app.contract.routes import _api_routes
    from app.main import create_app

    paths = {route.path for route in _api_routes(create_app())}

    assert "/staging/last-otp" not in paths


def test_the_route_is_registered_when_permitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the check itself.

    If the route were never registered in any environment, the test
    above would pass while proving nothing.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    from app.contract.routes import _api_routes
    from app.main import create_app

    paths = {route.path for route in _api_routes(create_app())}

    assert "/staging/last-otp" in paths


# ---------------------------------------------------------------------------
# MECHANISM 3 -- the startup refusal.
# ---------------------------------------------------------------------------


def test_a_production_process_refuses_to_start_with_the_outbox_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfiguration fails at boot, not quietly at request time.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv("SHIKKHOKPLUS_GLOBAL_DAILY_SMS", "50")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv("SHIKKHOKPLUS_OTP_HMAC_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_ADAPTER", "bulksmsbd")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_BASE_URL", "https://x")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_API_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_SENDER_ID", "s")

    with pytest.raises(ConfigurationError) as error:
        check_startup_configuration("production")

    assert "STAGING_OUTBOX" in str(error.value)


def test_an_otherwise_valid_production_process_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the check: the refusal must be about the outbox alone.

    Without this, the test above would pass against a check that
    refused every production process for some unrelated reason.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "")
    monkeypatch.setenv("SHIKKHOKPLUS_GLOBAL_DAILY_SMS", "50")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")
    monkeypatch.setenv("SHIKKHOKPLUS_OTP_HMAC_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_ADAPTER", "bulksmsbd")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_BASE_URL", "https://x")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_API_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_SENDER_ID", "s")

    check_startup_configuration("production")


# ---------------------------------------------------------------------------
# The writer, and the read window.
# ---------------------------------------------------------------------------


def test_the_writer_is_a_no_op_when_disabled(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production records nothing, so the table stays empty.

    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    record_outbox(
        restricted_session,
        phone="+8801711111111",
        message="code 123456",
        correlation_id=str(uuid.uuid4()),
    )
    restricted_session.commit()

    count = restricted_session.execute(
        sa.text("SELECT count(*) FROM staging_sms_outbox")
    ).scalar_one()
    assert count == 0


def test_a_recorded_message_reads_back(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point, when it is permitted.

    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    record_outbox(
        restricted_session,
        phone="+8801711111111",
        message="Your code is 123456",
        correlation_id=str(uuid.uuid4()),
    )
    restricted_session.commit()

    entry = read_outbox(restricted_session, phone="+8801711111111")

    assert entry is not None
    assert "123456" in entry.message


def test_an_expired_entry_is_not_returned(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window is shorter than the OTP's own expiry.

    The outbox must never outlive the thing it exposes, or a code that
    the auth path has already rejected is still readable here.

    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    restricted_session.execute(
        sa.text(
            "INSERT INTO staging_sms_outbox "
            "(id, phone, message, correlation_id, recorded_at) "
            "VALUES (:id, :phone, :m, :c, :then)"
        ),
        {
            "id": uuid.uuid4(),
            "phone": "+8801711111111",
            "m": "Your code is 999999",
            "c": str(uuid.uuid4()),
            "then": dt.datetime.now(tz=dt.UTC) - dt.timedelta(minutes=6),
        },
    )
    restricted_session.commit()

    assert read_outbox(restricted_session, phone="+8801711111111") is None


def test_reading_raises_when_disabled(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: the reader refuses even without a route.

    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")

    with pytest.raises(RuntimeError, match="not enabled"):
        read_outbox(restricted_session, phone="+8801711111111")


def test_an_unknown_number_records_nothing(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outbox must not become an existence oracle [BR2.7].

    **Found by running the thing, not by reading it.** The
    unknown-number path does equivalent work and rolls it back, so no
    OTP is persisted -- but it still RENDERS a message, and recording
    that put an entry in the outbox for a number with no account.

    The entry's code could never verify, which makes it worse than
    useless: it is indistinguishable from a real one, so an operator
    wastes time on a code that cannot work, and its mere existence
    answers the question the byte-identical response refuses to answer.

    :param restricted_session: A session as the application role
    :param monkeypatch: The patcher
    :return: None
    """
    import datetime as dt_module
    import os as os_module

    from fastapi.testclient import TestClient

    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv("SHIKKHOKPLUS_OTP_HMAC_KEY", "test-only-hmac-key")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", "AAAAAAAAAAA")

    from app.db.models import Account
    from app.main import create_app

    known = "+8801711111111"
    unknown = "+8801799999999"

    restricted_session.add(
        Account(phone=known, created_at=dt_module.datetime.now(tz=dt_module.UTC))
    )
    restricted_session.commit()

    app = create_app()
    app.state.engine = restricted_session.get_bind()
    with TestClient(app) as client:
        client.post("/v1/auth/otp", json={"phone": unknown})
        client.post("/v1/auth/otp", json={"phone": known})

    restricted_session.expire_all()
    recorded = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT phone FROM staging_sms_outbox")
        )
    }

    assert known in recorded, "the known number should be readable"
    assert unknown not in recorded, (
        "an unknown number was recorded, which answers the question the "
        "byte-identical issue response exists to refuse"
    )
    assert os_module.environ.get(OUTBOX_FORCE_ENV) == "1"
