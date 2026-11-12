"""A misconfigured production process must not start.

Each check here guards a **silent** failure — the process runs, nothing
raises, and a guarantee is quietly gone. That is the same shape as the
audit bug this Bolt fixed, and the reason these are startup assertions
rather than comments in a runbook.
"""

from __future__ import annotations

import pytest

from app.config import (
    ENVIRONMENT_ENV,
    LOCAL_DEV_MFA_KEY,
    ConfigurationError,
    check_startup_configuration,
)

#: Test-only JWT signing material: long enough to pass, and recognisable
#: if it ever leaked into a message. Named and valued as a fixture, as
#: tests/conftest.py names its key, so the secrets scan does not read it
#: as a credential.
SIGNING_MATERIAL = "test-signing-material-" + "x" * 20

COMPLETE = {
    "SHIKKHOKPLUS_GLOBAL_DAILY_SMS": "2000",
    "SHIKKHOKPLUS_SMS_APP_HASH": "ABCDEFGHIJK",
    "SHIKKHOKPLUS_OTP_HMAC_KEY": "a-real-key",
    "SHIKKHOKPLUS_SMS_ADAPTER": "bulksmsbd",
    "SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER": "X-Client-Address",
    # 32 bytes, base64; not the local-development key.
    "SHIKKHOKPLUS_MFA_KEYS": "k1:" + "B" * 43 + "=",
    "SHIKKHOKPLUS_MFA_ACTIVE_KID": "k1",
    "SHIKKHOKPLUS_EMAIL_ADAPTER": "ses",
    "SHIKKHOKPLUS_SES_SMTP_HOST": "email-smtp.us-east-1.amazonaws.com",
    "SHIKKHOKPLUS_SES_SMTP_USERNAME": "AKIAEXAMPLE",
    "SHIKKHOKPLUS_SES_SMTP_PASSWORD": "smtp-password",
    "SHIKKHOKPLUS_EMAIL_FROM": "ShikkhokPlus <no-reply@example.com>",
    "SHIKKHOKPLUS_JWT_KEYS": "k1:" + SIGNING_MATERIAL,
    "SHIKKHOKPLUS_JWT_ACTIVE_KID": "k1",
}


def _configure(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    """Install a production environment with optional overrides.

    :param monkeypatch: The patcher
    :param overrides: Values to replace, or None to unset
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    for key, value in {**COMPLETE, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_a_fully_configured_production_process_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    check_startup_configuration()


def test_development_is_not_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    # Local work and the test suite set what they need. Requiring
    # production values everywhere would make the check something
    # people route around.
    monkeypatch.setenv(ENVIRONMENT_ENV, "development")
    for key in COMPLETE:
        monkeypatch.delenv(key, raising=False)
    check_startup_configuration()


def test_an_unset_global_ceiling_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # THE MONEY ONE. Unset, the code's TEST default becomes the
    # production ceiling: either far too high, which is a budget risk,
    # or far too low, which locks every teacher out for the day.
    _configure(monkeypatch, SHIKKHOKPLUS_GLOBAL_DAILY_SMS=None)
    with pytest.raises(ConfigurationError, match="GLOBAL_DAILY_SMS"):
        check_startup_configuration()


def test_an_empty_app_hash_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # THE SILENT ONE. An empty hash renders a perfectly VALID SMS that
    # never triggers SMS Retriever -- autofill never fires, nothing
    # fails or logs, and users type every code by hand forever.
    _configure(monkeypatch, SHIKKHOKPLUS_SMS_APP_HASH="")
    with pytest.raises(ConfigurationError, match="APP_HASH"):
        check_startup_configuration()


def test_a_wrong_length_app_hash_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A truncated hash fails the same way an empty one does, and is
    # likelier: it looks right in a configuration file.
    _configure(monkeypatch, SHIKKHOKPLUS_SMS_APP_HASH="ABC")
    with pytest.raises(ConfigurationError, match="APP_HASH"):
        check_startup_configuration()


def test_a_missing_hmac_key_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, SHIKKHOKPLUS_OTP_HMAC_KEY=None)
    with pytest.raises(ConfigurationError, match="HMAC"):
        check_startup_configuration()


def test_the_null_adapter_in_production_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Defaulting to the null adapter is CORRECT everywhere else: it
    # fails toward not spending money. In production it means no
    # teacher ever receives a code while every send reports success --
    # equally silent, and worse.
    _configure(monkeypatch, SHIKKHOKPLUS_SMS_ADAPTER=None)
    with pytest.raises(ConfigurationError, match="ADAPTER"):
        check_startup_configuration()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_unset_trusted_client_header_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    # Production always sits behind the proxy, so without the header the
    # per-IP limits count the proxy (one bucket for everyone) or a
    # forwarded header the caller chooses (a bucket per request) [PA-SEC-2].
    _configure(monkeypatch, SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER=value)
    with pytest.raises(ConfigurationError, match="TRUSTED_CLIENT_IP_HEADER"):
        check_startup_configuration()


def test_every_problem_is_reported_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One deploy, one failure, every reason. Reporting the first
    # problem only turns a misconfiguration into several deploy cycles.
    _configure(
        monkeypatch,
        SHIKKHOKPLUS_GLOBAL_DAILY_SMS=None,
        SHIKKHOKPLUS_SMS_APP_HASH="",
    )
    with pytest.raises(ConfigurationError) as raised:
        check_startup_configuration()
    assert "GLOBAL_DAILY_SMS" in str(raised.value)
    assert "APP_HASH" in str(raised.value)


def test_a_missing_mfa_keyring_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every account can turn on two-step verification, so this is not
    # an administrator-only setting: without it, enrollment fails with a
    # 500 for whoever tries first.
    _configure(monkeypatch, SHIKKHOKPLUS_MFA_KEYS=None)
    with pytest.raises(ConfigurationError, match="MFA_KEYS"):
        check_startup_configuration()


def test_an_mfa_active_kid_naming_no_key_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, SHIKKHOKPLUS_MFA_ACTIVE_KID="k2")
    with pytest.raises(ConfigurationError, match="MFA_ACTIVE_KID"):
        check_startup_configuration()


def test_the_local_development_mfa_key_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, SHIKKHOKPLUS_MFA_KEYS=f"k1:{LOCAL_DEV_MFA_KEY}")
    with pytest.raises(ConfigurationError, match="local-development key"):
        check_startup_configuration()


def test_production_without_the_email_sender_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The null adapter mails nobody and reports success, so an email-only
    # account could neither finish signing up nor recover its password.
    _configure(monkeypatch, SHIKKHOKPLUS_EMAIL_ADAPTER=None)
    with pytest.raises(ConfigurationError, match="EMAIL_ADAPTER"):
        check_startup_configuration()


def test_production_with_half_the_smtp_settings_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, SHIKKHOKPLUS_SES_SMTP_PASSWORD=None)
    with pytest.raises(ConfigurationError, match="EMAIL_ADAPTER"):
        check_startup_configuration()


# ---------------------------------------------------------- JWT keyring


def test_an_unset_jwt_keyring_refuses_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # It used to be read lazily, so the first sign-in failed instead
    # of the boot [ARC-7].
    _configure(monkeypatch, SHIKKHOKPLUS_JWT_KEYS=None)
    with pytest.raises(ConfigurationError, match="SHIKKHOKPLUS_JWT_KEYS"):
        check_startup_configuration()


@pytest.mark.parametrize("environment", ["production", "development", "test"])
@pytest.mark.parametrize(
    ("keys", "active", "named"),
    [
        ("k1" + SIGNING_MATERIAL, "k1", "entry 1"),
        ("k1:" + SIGNING_MATERIAL + ",:" + SIGNING_MATERIAL, "k1", "entry 2"),
        ("k1:", "k1", "entry 1"),
        ("k1:" + SIGNING_MATERIAL, "k2", "SHIKKHOKPLUS_JWT_ACTIVE_KID"),
        ("k1:" + SIGNING_MATERIAL, None, "SHIKKHOKPLUS_JWT_ACTIVE_KID"),
        ("k1:tiny-key-material", "k1", "32"),
    ],
)
def test_a_malformed_jwt_keyring_refuses_to_start_anywhere(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    keys: str,
    active: str | None,
    named: str,
) -> None:
    # Set but wrong is never intended, so it fails in every environment,
    # and the message never carries key material.
    _configure(
        monkeypatch, SHIKKHOKPLUS_JWT_KEYS=keys, SHIKKHOKPLUS_JWT_ACTIVE_KID=active
    )
    monkeypatch.setenv(ENVIRONMENT_ENV, environment)

    with pytest.raises(ConfigurationError, match=named) as refused:
        check_startup_configuration()

    assert SIGNING_MATERIAL not in str(refused.value)
    assert "tiny-key-material" not in str(refused.value)


def test_an_unset_jwt_keyring_stays_lazy_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The OpenAPI emitter and many tests build the app with no keys.
    monkeypatch.setenv(ENVIRONMENT_ENV, "development")
    monkeypatch.delenv("SHIKKHOKPLUS_JWT_KEYS", raising=False)
    monkeypatch.delenv("SHIKKHOKPLUS_JWT_ACTIVE_KID", raising=False)
    check_startup_configuration()


def test_the_app_refuses_to_build_with_a_malformed_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wired to startup, not only to the function.
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_ENV, "test")
    monkeypatch.setenv("SHIKKHOKPLUS_JWT_KEYS", "k1:" + SIGNING_MATERIAL)
    monkeypatch.setenv("SHIKKHOKPLUS_JWT_ACTIVE_KID", "nope")

    with pytest.raises(ConfigurationError, match="ACTIVE_KID"):
        create_app()
