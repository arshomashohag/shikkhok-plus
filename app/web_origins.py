"""Which browser origins may call this API: the web client's allowlist.

The web client (``web/``) is normally served from the API's own host,
which needs no CORS at all. When it is served from its own origin
instead -- a static host or CDN in front of the built PWA -- the browser
refuses every cross-origin call unless the API names that origin. This
module turns ``SHIKKHOKPLUS_WEB_ORIGINS`` into that list.

**Off unless configured.** Unset or empty, no CORS middleware is
installed and no response carries an ``Access-Control-Allow-*`` header,
which is exactly the behaviour before the web client existed.

**Exact origins only, never a wildcard.** The API authenticates with a
bearer token, not a cookie, so ``*`` would not leak a session by itself;
but an allowlist that accepts any origin also accepts a look-alike
phishing page that has talked someone out of an OTP, and lets it script
the API from the victim's browser at full speed. Naming the one origin
the PWA is served from costs nothing and closes that. A value that is
not a bare ``https`` origin is a deployment error and refuses to start,
on the same reasoning as :mod:`app.config`: a silently ignored entry is a
guarantee removed without any signal.

Plain ``http`` is accepted only for loopback, for a developer running
``vite preview`` against a local API.
"""

from __future__ import annotations

import os
from typing import Final
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import ConfigurationError

__all__ = ["WEB_ORIGINS_ENV", "parse_web_origins", "register_web_origins"]

#: Comma-separated exact origins, e.g. ``https://app.shikkhokplus.com``.
WEB_ORIGINS_ENV: Final = "SHIKKHOKPLUS_WEB_ORIGINS"

#: Hosts for which plain http is tolerated.
_LOOPBACK: Final = frozenset({"localhost", "127.0.0.1", "[::1]"})

#: Every header the web client sends. Nothing else is needed.
_ALLOWED_HEADERS: Final = (
    "Authorization",
    "Content-Type",
    "Accept",
    "X-Workspace-Id",
    "X-Client-Platform",
    "X-Client-Version",
)

#: Preflight results may be cached by the browser for this long.
_PREFLIGHT_MAX_AGE_S: Final = 600


def _check_origin(raw: str) -> str:
    """Validate one configured origin and return it normalised.

    :param raw: One comma-separated entry, already stripped
    :return: The origin, lower-cased, with no trailing slash
    :raises ConfigurationError: The entry is not a bare origin
    """
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    bare = not (parts.path not in ("", "/") or parts.query or parts.fragment)
    if not host or not bare or parts.username or parts.password:
        raise ConfigurationError(
            f"{WEB_ORIGINS_ENV} entry {raw!r} is not a bare origin "
            "(scheme://host[:port], no path)."
        )
    loopback = host in _LOOPBACK or f"[{host}]" in _LOOPBACK
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise ConfigurationError(
            f"{WEB_ORIGINS_ENV} entry {raw!r} must be https; plain http is "
            "accepted only for localhost."
        )
    return raw.rstrip("/").lower()


def parse_web_origins(raw: str | None) -> tuple[str, ...]:
    """Read the allowlist from the environment variable's value.

    :param raw: The variable's value, or None when unset
    :return: The allowed origins, in the order given; empty when unset
    :raises ConfigurationError: An entry is a wildcard or not an origin
    """
    entries = [e.strip() for e in (raw or "").split(",") if e.strip()]
    if "*" in entries:
        raise ConfigurationError(
            f"{WEB_ORIGINS_ENV} may not contain '*'. Name the web "
            "client's origin exactly."
        )
    return tuple(dict.fromkeys(_check_origin(e) for e in entries))


def register_web_origins(app: FastAPI, raw: str | None = None) -> tuple[str, ...]:
    """Install CORS for the configured web origins, if there are any.

    Added **after** every other middleware, so it is the outermost layer
    and answers a preflight before the request scope opens a database
    session for it.

    :param app: The application being built
    :param raw: The allowlist, or None to read the environment
    :return: The origins installed; empty when CORS stays off
    :raises ConfigurationError: The allowlist is malformed
    """
    origins = parse_web_origins(
        raw if raw is not None else os.environ.get(WEB_ORIGINS_ENV)
    )
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=list(_ALLOWED_HEADERS),
            allow_credentials=False,
            max_age=_PREFLIGHT_MAX_AGE_S,
        )
    return origins
