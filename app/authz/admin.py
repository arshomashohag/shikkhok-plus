"""Who is a platform administrator: an allowlist of phone numbers.

**Configuration, not a column.** ``Account`` deliberately has no role
column [BR1.1], and an administrator flag would be the same stale-role
defect in a new place. The allowlist lives in the deployment's runtime
environment, so granting or revoking it is a deploy-time decision a
person makes, recorded where the other secrets are.

**Empty means nobody.** An unset or blank variable grants the lens to no
account, so a deployment that forgets it has no administration surface
rather than an open one.
"""

from __future__ import annotations

import os
from typing import Final

from app.accounts.phone import canonical_phone
from app.errors import ValidationError

__all__ = ["PLATFORM_ADMIN_PHONES_ENV", "is_platform_admin", "platform_admin_phones"]

#: Comma-separated phone numbers, in any spelling ``canonical_phone``
#: accepts.
PLATFORM_ADMIN_PHONES_ENV: Final = "SHIKKHOKPLUS_PLATFORM_ADMIN_PHONES"


def platform_admin_phones() -> frozenset[str]:
    """Read the allowlist, canonicalised.

    Read per call rather than at import, so a test or a restarted process
    sees the current value and nothing caches a revoked number.

    :return: The canonical numbers, possibly empty
    :raises ValidationError: An entry is not a Bangladeshi mobile number;
        a typo must fail loudly rather than silently lock the admin out
    """
    raw = os.environ.get(PLATFORM_ADMIN_PHONES_ENV, "")
    phones: set[str] = set()
    for entry in raw.split(","):
        if entry.strip():
            phones.add(canonical_phone(entry))
    return frozenset(phones)


def is_platform_admin(phone: str) -> bool:
    """Report whether a stored phone number is on the allowlist.

    A malformed allowlist answers False for everyone rather than raising
    into a request: the misconfiguration is reported by
    :func:`platform_admin_phones` wherever it is called directly.

    :param phone: The account's stored, canonical number
    :return: True only for an allowlisted number
    """
    try:
        return phone in platform_admin_phones()
    except ValidationError:
        return False
