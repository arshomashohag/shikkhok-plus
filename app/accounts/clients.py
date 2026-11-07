"""Which app an account uses: recorded at sign-in and token refresh.

**The client says what it is; nothing is inferred.** Each client sends
``X-Client-Platform`` (``android`` or ``web``) and optionally
``X-Client-Version``. Nothing here reads a User-Agent, a device model or
any identifier [TC-3, D-37]: a two-value enum and an app version are
enough to answer "how many people use the web app", and anything more
would be collecting for its own sake.

**Recorded only where a token is issued**, never on every request. An
access token lives fifteen minutes and is renewed through
``POST /v1/auth/refresh``, so ``last_seen_at`` is accurate to that
window at the cost of one upsert per renewal rather than one write per
call. A request without the header, from an older app build, records
nothing rather than guessing.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = [
    "CLIENT_PLATFORM_HEADER",
    "CLIENT_VERSION_HEADER",
    "PLATFORMS",
    "Platform",
    "parse_platform",
    "parse_version",
    "record_client",
]

#: An app an account can use.
Platform = Literal["android", "web"]

#: Both, in the order every list presents them.
PLATFORMS: Final[tuple[Platform, ...]] = ("android", "web")

#: The header naming the app: ``android`` or ``web``.
CLIENT_PLATFORM_HEADER: Final = "X-Client-Platform"

#: The header carrying the app's own version string, such as ``1.4.0``.
CLIENT_VERSION_HEADER: Final = "X-Client-Version"

#: A version is short and plain: digits, letters, dots, plus, hyphen.
#: Anything else is dropped rather than stored, so the column cannot
#: become a free-text field a client fills with something identifying.
_VERSION: Final = re.compile(r"[0-9A-Za-z.+\-]{1,32}")

_UPSERT: Final = sa.text(
    "INSERT INTO account_client "
    "(account_id, platform, app_version, first_seen_at, last_seen_at) "
    "VALUES (:account_id, CAST(:platform AS client_platform), :version, "
    ":now, :now) "
    "ON CONFLICT (account_id, platform) DO UPDATE SET "
    "last_seen_at = GREATEST(account_client.last_seen_at, EXCLUDED.last_seen_at), "
    "app_version = COALESCE(EXCLUDED.app_version, account_client.app_version)"
)


def parse_platform(raw: str | None) -> Platform | None:
    """Read the platform header, case-insensitively.

    :param raw: The header value, or None when absent
    :return: ``android`` or ``web``, or None for anything else
    """
    if raw is None:
        return None
    value = raw.strip().lower()
    for platform in PLATFORMS:
        if value == platform:
            return platform
    return None


def parse_version(raw: str | None) -> str | None:
    """Read the version header, dropping anything implausible.

    :param raw: The header value, or None when absent
    :return: The version, or None
    """
    if raw is None:
        return None
    value = raw.strip()
    return value if _VERSION.fullmatch(value) else None


def record_client(
    session: Session,
    account_id: uuid.UUID,
    platform_header: str | None,
    version_header: str | None,
    now: dt.datetime | None = None,
) -> str | None:
    """Note that an account was just seen on a platform.

    Does not commit: the caller's transaction carries it, so at sign-in
    the record and the token it accompanies land together.

    :param session: The session to write through
    :param account_id: The account a token was just issued to
    :param platform_header: ``X-Client-Platform``, or None
    :param version_header: ``X-Client-Version``, or None
    :param now: The moment, or None for the clock
    :return: The platform recorded, or None when nothing was recorded
    """
    platform = parse_platform(platform_header)
    if platform is None:
        return None
    session.execute(
        _UPSERT,
        {
            "account_id": account_id,
            "platform": platform,
            "version": parse_version(version_header),
            "now": now or dt.datetime.now(tz=dt.UTC),
        },
    )
    return platform
