"""Deployment settings the public pages read from the environment."""

from __future__ import annotations

import os
from typing import Final

__all__ = ["DEFAULT_ORIGIN", "SITE_URL_ENV", "site_url"]

#: The public site's origin: canonical links, ``hreflang`` and sitemap
#: ``loc`` values are absolute URLs on it [R1].
SITE_URL_ENV: Final[str] = "SHIKKHOKPLUS_SITE_URL"

#: The origin used when the variable is unset, as locally and in tests.
DEFAULT_ORIGIN: Final[str] = "http://localhost"


def site_url() -> str:
    """Return the public site's origin, with no trailing slash.

    Read at each call rather than once at import, so a test or a restarted
    process sees the current value.

    :return: The origin, e.g. ``https://shikkhokplus.com``
    """
    return (os.environ.get(SITE_URL_ENV) or DEFAULT_ORIGIN).rstrip("/")
