"""Deployment settings the public pages read from the environment."""

from __future__ import annotations

import os
from typing import Final

__all__ = [
    "DEFAULT_ORIGIN",
    "HUB_REVIEWS_ENV",
    "SITE_URL_ENV",
    "WEB_APP_URL_ENV",
    "reviews_enabled",
    "site_url",
    "web_app_url",
]

#: The public site's origin: canonical links, ``hreflang`` and sitemap
#: ``loc`` values are absolute URLs on it [R1].
SITE_URL_ENV: Final[str] = "SHIKKHOKPLUS_SITE_URL"

#: The web app's origin: a public page's report link opens the report form
#: there, at ``/ui/hub-report`` [R1].
WEB_APP_URL_ENV: Final[str] = "SHIKKHOKPLUS_WEB_APP_URL"

#: The reviews switch. Reviews are off unless this is exactly ``on``.
HUB_REVIEWS_ENV: Final[str] = "SHIKKHOKPLUS_HUB_REVIEWS"

#: The origin used when either variable is unset, as locally and in tests.
DEFAULT_ORIGIN: Final[str] = "http://localhost"


def site_url() -> str:
    """Return the public site's origin, with no trailing slash.

    Read at each call rather than once at import, so a test or a restarted
    process sees the current value.

    :return: The origin, e.g. ``https://shikkhokplus.com``
    """
    return (os.environ.get(SITE_URL_ENV) or DEFAULT_ORIGIN).rstrip("/")


def web_app_url() -> str:
    """Return the web app's origin, with no trailing slash.

    Read at each call, as :func:`site_url` is.

    :return: The origin, e.g. ``https://app.shikkhokplus.com``
    """
    return (os.environ.get(WEB_APP_URL_ENV) or DEFAULT_ORIGIN).rstrip("/")


def reviews_enabled() -> bool:
    """Say whether hub reviews are switched on.

    True only for the exact string ``on``: unset, ``ON``, ``true``, ``1``
    and `` on`` are all off, so a typo can never switch the feature on.
    Read at each call rather than once at import, so a test or a restarted
    process sees the current value.

    :return: True when reviews are on
    """
    return os.environ.get(HUB_REVIEWS_ENV) == "on"
