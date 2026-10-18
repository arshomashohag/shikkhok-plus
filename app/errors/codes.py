"""The error code registry.

**No code distinguishes "you may not reach this" from "this does not
exist."** A pair such as ``BATCH_NOT_FOUND`` / ``BATCH_NOT_YOURS`` is an
existence oracle even though each code reads as good practice on its own:
teacher A probes ids and reads the difference, enumerating teacher B's
batches. There is one code for both cases, and a test asserts the registry
contains no such pair [NFR14.3, BR1.5].

**Each status is paired with its codes, and the pairing is asserted.** A
403 carrying ``ACCESS_TOKEN_EXPIRED`` would tell a prober their token was
fine and the *resource* was the problem -- the oracle re-entering through a
field the status rule alone does not constrain.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = [
    "ACCESS_TOKEN_EXPIRED",
    "AUTH_401_CODES",
    "AUTH_403_CODES",
    "LENS_HINT_REQUIRED",
    "LENS_NOT_AVAILABLE",
    "NOT_AVAILABLE",
    "TOKEN_MISSING",
    "auth_status_for",
]

#: The single code covering BOTH an unreachable resource and an absent one.
#: Deliberately named for what the caller may do rather than for what the
#: server found, because the latter is the thing that must not be disclosed.
NOT_AVAILABLE: Final = "NOT_AVAILABLE"

#: The access token has expired. The one code on which the client may
#: refresh and replay exactly once [B.3].
ACCESS_TOKEN_EXPIRED: Final = "ACCESS_TOKEN_EXPIRED"  # noqa: S105  an error code, not a credential

#: No credential was presented at all.
TOKEN_MISSING: Final = "TOKEN_MISSING"  # noqa: S105  an error code, not a credential

#: A lens hint named a lens the account's data does not support [BR1.7].
LENS_NOT_AVAILABLE: Final = "LENS_NOT_AVAILABLE"

#: More than one lens is available and the route is lens-ambiguous [B.4].
LENS_HINT_REQUIRED: Final = "LENS_HINT_REQUIRED"

#: Codes that mean "authenticate again" and therefore carry 401.
AUTH_401_CODES: Final[frozenset[str]] = frozenset(
    {ACCESS_TOKEN_EXPIRED, TOKEN_MISSING}
)

#: Codes that mean "authenticated, but no lens grants this" and carry 403.
AUTH_403_CODES: Final[frozenset[str]] = frozenset(
    {NOT_AVAILABLE, LENS_NOT_AVAILABLE}
)


def auth_status_for(code: str) -> Literal[401, 403]:
    """Return the status an authorization code must carry.

    Keeping this a lookup rather than a judgement at the raise site is what
    makes the pairing assertable: a 403 can never carry a 401-only code.

    :param code: An authorization error code
    :return: 401 for a credential problem, 403 otherwise
    :raises KeyError: The code is in neither authorization set
    """
    if code in AUTH_401_CODES:
        return 401
    if code in AUTH_403_CODES:
        return 403
    raise KeyError(f"{code!r} is not a registered authorization code")
