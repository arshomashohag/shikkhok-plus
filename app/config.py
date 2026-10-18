"""Startup configuration checks, so a missing value fails loudly.

**Every silent default in this system removes a guarantee without any
signal**, which is the same shape as the audit bug this Bolt already
fixed: the thing still runs, nothing fails or warns, and the property
you were relying on is simply gone.

Two such defaults existed and are checked here:

* ``SHIKKHOKPLUS_GLOBAL_DAILY_SMS`` defaults to a **test** value. Unset
  in production, that test number silently becomes the money ceiling —
  either far too high, which is a budget risk, or far too low, which
  locks every teacher out for the day.
* ``SHIKKHOKPLUS_SMS_APP_HASH`` defaults to ``""``. An empty app hash
  renders a perfectly valid SMS that **never triggers SMS Retriever**,
  so autofill silently never fires and users type every code by hand
  with nothing to explain why.

The checks run at application startup rather than at first use, so a
misconfigured deployment fails on the deploy instead of on a teacher's
first sign-in attempt. That follows the same reasoning as the gateway's
https assertion, which raises in the constructor.

**Production only.** Tests and local development set what they need and
should not have to set what they do not.
"""

from __future__ import annotations

import os
from typing import Final

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.gateway.null import ADAPTER_ENV, REAL_ADAPTER_SENTINEL

__all__ = ["ConfigurationError", "check_startup_configuration"]

#: Names the variable that selects production behaviour.
ENVIRONMENT_ENV: Final = "SHIKKHOKPLUS_ENVIRONMENT"

#: The SMS Retriever app hash is exactly 11 characters.
APP_HASH_LENGTH: Final = 11


class ConfigurationError(RuntimeError):
    """A value needed in production is missing or implausible.

    Deliberately **not** a :class:`~app.errors.TaxonomyError`: that
    hierarchy describes what a *request* did, and this is a deployment
    that should never have started serving.
    """


def check_startup_configuration(environment: str | None = None) -> None:
    """Refuse to start a production process that is misconfigured.

    :param environment: The environment name, or None to read it
    :return: None
    :raises ConfigurationError: A required production value is missing
    """
    resolved = environment or os.environ.get(ENVIRONMENT_ENV, "development")
    if resolved != "production":
        return

    problems: list[str] = []

    if not os.environ.get("SHIKKHOKPLUS_GLOBAL_DAILY_SMS"):
        problems.append(
            "SHIKKHOKPLUS_GLOBAL_DAILY_SMS is unset, so the code's TEST "
            "default would become the production money ceiling. The "
            "value derives from the per-SMS rate against the monthly "
            "budget and is a deployment decision."
        )

    app_hash = os.environ.get("SHIKKHOKPLUS_SMS_APP_HASH", "")
    if len(app_hash) != APP_HASH_LENGTH:
        problems.append(
            f"SHIKKHOKPLUS_SMS_APP_HASH is {len(app_hash)} characters, "
            f"not {APP_HASH_LENGTH}. A wrong or empty hash renders a "
            "valid SMS that never triggers SMS Retriever, so autofill "
            "silently never fires and nothing reports it."
        )

    if not os.environ.get(OTP_HMAC_KEY_ENV):
        problems.append(
            f"{OTP_HMAC_KEY_ENV} is unset. Issuing a code would raise "
            "on the first request rather than at startup."
        )

    if os.environ.get(ADAPTER_ENV) != REAL_ADAPTER_SENTINEL:
        # The null adapter defaulting is CORRECT everywhere else -- it
        # fails toward not sending. In production it means no teacher
        # ever receives a code, which is equally silent and worse.
        problems.append(
            f"{ADAPTER_ENV} does not select the real adapter, so this "
            "production process would send no SMS at all while "
            "reporting every send as successful."
        )

    if problems:
        raise ConfigurationError("refusing to start: " + " | ".join(problems))
