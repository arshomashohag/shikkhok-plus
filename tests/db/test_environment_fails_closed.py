"""An environment name not known to be safe is checked as production.

The startup checks used to run only for the exact string
``production``, so ``prod``, ``Production`` or a blank value skipped
every one of them [C-19]. These tests pin the fail-closed reading, and
the placeholder SMS Retriever hash a deploy fallback once supplied.
"""

from __future__ import annotations

import pytest

from app.config import (
    ENVIRONMENT_ENV,
    PLACEHOLDER_APP_HASH,
    ConfigurationError,
    check_startup_configuration,
    is_production,
)

COMPLETE = {
    "SHIKKHOKPLUS_GLOBAL_DAILY_SMS": "2000",
    "SHIKKHOKPLUS_SMS_APP_HASH": "ABCDEFGHIJK",
    "SHIKKHOKPLUS_OTP_HMAC_KEY": "a-real-key",
    "SHIKKHOKPLUS_SMS_ADAPTER": "bulksmsbd",
    "SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER": "X-Client-Address",
    "SHIKKHOKPLUS_MFA_KEYS": "k1:" + "B" * 43 + "=",
    "SHIKKHOKPLUS_MFA_ACTIVE_KID": "k1",
    "SHIKKHOKPLUS_EMAIL_ADAPTER": "ses",
    "SHIKKHOKPLUS_SES_SMTP_HOST": "email-smtp.us-east-1.amazonaws.com",
    "SHIKKHOKPLUS_SES_SMTP_USERNAME": "AKIAEXAMPLE",
    "SHIKKHOKPLUS_SES_SMTP_PASSWORD": "smtp-password",
    "SHIKKHOKPLUS_EMAIL_FROM": "ShikkhokPlus <no-reply@example.com>",
}


@pytest.mark.parametrize(
    "name", ["prod", "Production", "production ", "staging ", "live", "unset"]
)
def test_an_unknown_name_is_checked_as_production(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, name)
    for key in COMPLETE:
        monkeypatch.delenv(key, raising=False)

    assert is_production() is True
    with pytest.raises(ConfigurationError, match="GLOBAL_DAILY_SMS"):
        check_startup_configuration()


@pytest.mark.parametrize("name", ["development", "test", "staging"])
def test_the_known_safe_names_are_not_checked(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, name)
    for key in COMPLETE:
        monkeypatch.delenv(key, raising=False)

    assert is_production() is False
    check_startup_configuration()


def test_an_unset_name_is_development(monkeypatch: pytest.MonkeyPatch) -> None:
    # What the suite and a fresh clone rely on. A deployed host never
    # runs unset: its compose file refuses to start without a name.
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)

    assert is_production() is False


def test_the_placeholder_app_hash_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Eleven characters, so the length check alone passed it.
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_APP_HASH", PLACEHOLDER_APP_HASH)

    with pytest.raises(ConfigurationError, match="placeholder"):
        check_startup_configuration()


def test_a_real_looking_hash_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guards the test above.
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    for key, value in COMPLETE.items():
        monkeypatch.setenv(key, value)

    check_startup_configuration()
