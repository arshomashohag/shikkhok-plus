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

COMPLETE = {
    "SHIKKHOKPLUS_GLOBAL_DAILY_SMS": "2000",
    "SHIKKHOKPLUS_SMS_APP_HASH": "ABCDEFGHIJK",
    "SHIKKHOKPLUS_OTP_HMAC_KEY": "a-real-key",
    "SHIKKHOKPLUS_SMS_ADAPTER": "bulksmsbd",
    "SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER": "X-Client-Address",
    # 32 bytes, base64; not the local-development key.
    "SHIKKHOKPLUS_MFA_KEYS": "k1:" + "B" * 43 + "=",
    "SHIKKHOKPLUS_MFA_ACTIVE_KID": "k1",
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
