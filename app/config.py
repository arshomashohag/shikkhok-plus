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

**Production, and anything that is not KNOWN not to be production**
[C-19]. Tests and local development set what they need and should not
have to set what they do not, so ``development``, ``test`` and
``staging`` are exempt -- and every other value is checked as
production. The checks used to run only for the exact string
``production``, so a mistyped ``prod`` or ``Production`` skipped every
one of them and also permitted the staging outbox and the seeders: the
check failed open on precisely the mistake it exists to catch.

An UNSET name still means ``development``, because the test suite and a
fresh clone rely on it; a deployed host never runs with it unset, since
the host's compose file refuses to start without one.
"""

from __future__ import annotations

import os
from typing import Final

from app.auth.client_address import TRUSTED_CLIENT_IP_HEADER_ENV
from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.mfa_crypto import MFA_ACTIVE_KID_ENV, MFA_KEYS_ENV, keyring_configured
from app.authz.admin import (
    ADMIN_ALLOWED_CIDRS_ENV,
    ADMIN_EDGE_SECRET_ENV,
    PLATFORM_ADMIN_PHONES_ENV,
)
from app.gateway.email import EMAIL_ADAPTER_ENV, email_gateway_configured
from app.gateway.null import ADAPTER_ENV, REAL_ADAPTER_SENTINEL

__all__ = [
    "NON_PRODUCTION_ENVIRONMENTS",
    "ConfigurationError",
    "check_startup_configuration",
    "is_production",
    "resolve_environment",
]

#: Names the variable that selects production behaviour.
ENVIRONMENT_ENV: Final = "SHIKKHOKPLUS_ENVIRONMENT"

#: The only names that are NOT checked as production. Exact strings: a
#: capitalised or space-padded name is not in this set, so it is checked.
NON_PRODUCTION_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {"development", "test", "staging"}
)

#: The SMS Retriever app hash is exactly 11 characters.
APP_HASH_LENGTH: Final = 11

#: The local-development placeholder hash. It has the right length, so a
#: length check alone passes it -- which is how a deploy fallback of this
#: value would have reached production with autofill silently broken.
PLACEHOLDER_APP_HASH: Final = "AAAAAAAAAAA"

#: The MFA key docker-compose.yml supplies by default, base64 of
#: ``local-dev-only-mfa-key-32-bytes!``. Public, so production refuses it.
LOCAL_DEV_MFA_KEY: Final = "bG9jYWwtZGV2LW9ubHktbWZhLWtleS0zMi1ieXRlcyE="


class ConfigurationError(RuntimeError):
    """A value needed in production is missing or implausible.

    Deliberately **not** a :class:`~app.errors.TaxonomyError`: that
    hierarchy describes what a *request* did, and this is a deployment
    that should never have started serving.
    """


def resolve_environment(environment: str | None = None) -> str:
    """Return the environment name in force.

    :param environment: An explicit name, or None (or empty) to read it
    :return: The name, ``development`` when the variable is unset
    """
    return environment or os.environ.get(ENVIRONMENT_ENV, "development")


def is_production(environment: str | None = None) -> bool:
    """Report whether the production checks apply.

    :param environment: An explicit name, or None to read it
    :return: True for every name not known to be non-production
    """
    return resolve_environment(environment) not in NON_PRODUCTION_ENVIRONMENTS


def check_startup_configuration(environment: str | None = None) -> None:
    """Refuse to start a production process that is misconfigured.

    :param environment: The environment name, or None to read it
    :return: None
    :raises ConfigurationError: A required production value is missing
    """
    if not is_production(environment):
        return

    problems: list[str] = []

    # FIRST, because it is the only item here that hands an attacker a
    # credential rather than degrading a feature. Everything else in
    # this function describes a process that serves badly; this one
    # describes a process that serves OTPs to anyone who asks.
    if os.environ.get("SHIKKHOKPLUS_STAGING_OUTBOX") == "1":
        problems.append(
            "SHIKKHOKPLUS_STAGING_OUTBOX is enabled in a production "
            "process. That route returns the most recent OTP for any "
            "phone number to an unauthenticated caller. It exists so a "
            "person can sign in on a staging host with no SMS "
            "credentials, and it must never reach production."
        )

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
    elif app_hash == PLACEHOLDER_APP_HASH:
        problems.append(
            "SHIKKHOKPLUS_SMS_APP_HASH is the local-development "
            "placeholder. It has the right length and matches no signed "
            "build, so autofill silently never fires."
        )

    if not os.environ.get(OTP_HMAC_KEY_ENV):
        problems.append(
            f"{OTP_HMAC_KEY_ENV} is unset. Issuing a code would raise "
            "on the first request rather than at startup."
        )

    # Production always runs behind the proxy chain, so the peer is the
    # proxy and never the caller. Unset, the per-IP limits either count
    # every caller in one bucket -- ten requests an hour for the whole
    # country -- or, with uvicorn trusting forwarded headers, let each
    # caller choose a fresh bucket per request. Both run silently.
    if not os.environ.get(TRUSTED_CLIENT_IP_HEADER_ENV, "").strip():
        problems.append(
            f"{TRUSTED_CLIENT_IP_HEADER_ENV} is unset, so per-IP limits "
            "would count the proxy's address (or a caller-chosen "
            "forwarded header) instead of the verified client address."
        )

    # An administrator configured without the locks that make the admin
    # surface safe. Each of these fails CLOSED on its own -- no edge
    # secret or no networks means nobody gets in -- so the process would run,
    # and the admin surface would be silently unusable. Reported here
    # instead, at the deploy, where it can be fixed.
    if os.environ.get(PLATFORM_ADMIN_PHONES_ENV, "").strip():
        for name in (ADMIN_EDGE_SECRET_ENV, ADMIN_ALLOWED_CIDRS_ENV):
            if not os.environ.get(name, "").strip():
                problems.append(
                    f"{name} is unset while {PLATFORM_ADMIN_PHONES_ENV} names "
                    "administrators, so no administrator can reach the admin "
                    "surface. Set it, or clear the administrator list."
                )

    # **Every account can turn on two-step verification**, not only
    # administrators, so a production process without a keyring serves
    # normally until someone tries -- and then their enrollment fails
    # with a 500. Reported here instead. The development key is refused
    # too: it is committed in docker-compose.yml, so a secret sealed
    # with it is sealed with a key anyone can read.
    if not keyring_configured():
        problems.append(
            f"{MFA_KEYS_ENV} / {MFA_ACTIVE_KID_ENV} are unset or "
            "malformed, so no account can turn on two-step verification "
            "and no administrator can finish signing in."
        )
    elif LOCAL_DEV_MFA_KEY in os.environ.get(MFA_KEYS_ENV, ""):
        problems.append(
            f"{MFA_KEYS_ENV} holds the local-development key committed "
            "in docker-compose.yml. Generate a real one."
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

    # The email twin of the SMS adapter check [0032]. The null adapter
    # mails nobody and reports success, so an email-only account could
    # neither finish signing up nor recover its password -- silently.
    if not email_gateway_configured():
        problems.append(
            f"{EMAIL_ADAPTER_ENV} does not select the SES adapter, or its "
            "SMTP settings are incomplete, so this production process "
            "would email no code at all while reporting every send as "
            "successful."
        )

    if problems:
        raise ConfigurationError("refusing to start: " + " | ".join(problems))
