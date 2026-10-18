"""Access tokens, and refresh rotation with reuse detection.

**Reuse detection degrades silently into non-rotating tokens**, because
the happy path is identical either way [BR4.1]. The difference appears
only when an old token is presented again -- which is exactly the
stolen-token case the mechanism exists for. So it is tested as a state
machine over five transitions rather than as a happy path.

**The family is the unit of invalidation, not the token.** Invalidating
only the presented token leaves the thief's working, which inverts the
control: the victim's client gets logged out and the attacker keeps the
session.

Two things are deliberately **absent from the access token**: a role
claim and a lens claim. A lens baked into a 15-minute token is a cached
role by another name, and it would survive an ownership change for up to
fifteen minutes -- which is exactly what BR1.2 and BR1.3 forbid.

``kid`` and two valid verification keys cost almost nothing now and are a
mass-logout incident to retrofit later: rotating the signing key without
them force-logs-out every holder of a 30-day refresh token, at exactly
the moment rotation is needed [BR4.3].
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from dataclasses import dataclass
from typing import Any, Final

import jwt
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth.hashing import generate_refresh_token, hash_refresh_token
from app.errors import AuthorizationError

__all__ = [
    "ACCESS_TOKEN_LIFETIME",
    "JWT_ACTIVE_KID_ENV",
    "REFRESH_TOKEN_LIFETIME",
    "TokenPair",
    "issue_pair",
    "rotate",
    "verify_access_token",
]

#: Fifteen minutes, enforced server-side [BR4.2].
ACCESS_TOKEN_LIFETIME: Final = dt.timedelta(minutes=15)

#: Thirty days. Long enough that a signing-key rotation without ``kid``
#: would be a mass-logout event, which is why ``kid`` is here from the
#: first commit.
REFRESH_TOKEN_LIFETIME: Final = dt.timedelta(days=30)

#: Names the environment variable holding the active key id.
JWT_ACTIVE_KID_ENV: Final = "SHIKKHOKPLUS_JWT_ACTIVE_KID"

#: Names the variable holding the key map, as ``kid:secret`` pairs.
JWT_KEYS_ENV: Final = "SHIKKHOKPLUS_JWT_KEYS"

_ALGORITHM: Final = "HS256"


@dataclass(frozen=True, slots=True)
class TokenPair:
    """One access token and the refresh token that will replace it.

    :ivar access_token: The signed, short-lived bearer token
    :ivar refresh_token: The opaque long-lived token, stored hashed
    :ivar family_id: The rotation chain this pair belongs to
    """

    access_token: str
    refresh_token: str
    family_id: uuid.UUID


def _keys() -> dict[str, str]:
    """Read the verification key map from the environment.

    :return: Key id to secret
    :raises RuntimeError: The environment names no keys
    """
    raw = os.environ.get(JWT_KEYS_ENV)
    if not raw:
        raise RuntimeError(
            f"{JWT_KEYS_ENV} is unset. Signing keys are never hardcoded."
        )
    pairs = [entry.split(":", 1) for entry in raw.split(",") if entry]
    return {kid.strip(): secret.strip() for kid, secret in pairs}


def _active_kid() -> str:
    """Return the key id new tokens are signed under.

    :return: The active key id
    :raises RuntimeError: The environment names no active key
    """
    kid = os.environ.get(JWT_ACTIVE_KID_ENV)
    if not kid:
        raise RuntimeError(f"{JWT_ACTIVE_KID_ENV} is unset.")
    return kid


def issue_pair(
    session: Session,
    account_id: uuid.UUID,
    correlation_id: str,
    family_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> TokenPair:
    """Issue an access token and a refresh token.

    :param session: The session to write the refresh row through
    :param account_id: The authenticated account
    :param correlation_id: Ties any audit row to this request
    :param family_id: Continue an existing chain, or None to start one
    :param now: The moment of issue, or None for the clock
    :return: The new pair
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    chain = family_id or uuid.uuid4()

    refresh = generate_refresh_token()
    session.execute(
        sa.text(
            "INSERT INTO refresh_token "
            "(id, account_id, token_hash, family_id, issued_at, expires_at) "
            "VALUES (:id, :account_id, :token_hash, :family_id, "
            ":issued_at, :expires_at)"
        ),
        {
            "id": uuid.uuid4(),
            "account_id": account_id,
            "token_hash": hash_refresh_token(refresh),
            "family_id": chain,
            "issued_at": moment,
            "expires_at": moment + REFRESH_TOKEN_LIFETIME,
        },
    )

    return TokenPair(
        access_token=_sign(account_id, moment),
        refresh_token=refresh,
        family_id=chain,
    )


def _sign(account_id: uuid.UUID, moment: dt.datetime) -> str:
    """Sign one access token.

    **No role claim and no lens claim.** Either would be a cached role
    surviving an ownership change for the token's lifetime.

    :param account_id: The subject
    :param moment: The issue time
    :return: The encoded token
    """
    kid = _active_kid()
    return jwt.encode(
        {
            "sub": str(account_id),
            "iat": int(moment.timestamp()),
            "exp": int((moment + ACCESS_TOKEN_LIFETIME).timestamp()),
        },
        _keys()[kid],
        algorithm=_ALGORITHM,
        headers={"kid": kid},
    )


def verify_access_token(token: str, now: dt.datetime | None = None) -> uuid.UUID:
    """Verify an access token against **either** configured key.

    :param token: The presented bearer token
    :param now: The moment to compare expiry against, or None for the clock
    :return: The authenticated account
    :raises AuthorizationError: The token is unverifiable or expired
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        raise _unauthenticated("TOKEN_MISSING") from error

    secret = _keys().get(header.get("kid", ""))
    if secret is None:
        raise _unauthenticated("TOKEN_MISSING")

    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError as error:
        raise _unauthenticated("TOKEN_MISSING") from error

    # Expiry is compared SERVER-SIDE against our own clock rather than
    # trusted from the library's default, so the one assertion the rule
    # names is the one actually made [BR4.2].
    if moment.timestamp() >= float(claims["exp"]):
        raise _unauthenticated("ACCESS_TOKEN_EXPIRED")

    return uuid.UUID(claims["sub"])


def rotate(
    session: Session,
    presented: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> TokenPair:
    """Rotate a refresh token, invalidating the family on reuse.

    :param session: The session to work through
    :param presented: The refresh token the client sent
    :param correlation_id: Ties the audit row to this request
    :param now: The moment of rotation, or None for the clock
    :return: The replacement pair
    :raises AuthorizationError: The token is unknown, expired or replayed
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    digest = hash_refresh_token(presented)

    row = session.execute(
        sa.text(
            "SELECT id, account_id, family_id, expires_at, rotated_at "
            "FROM refresh_token WHERE token_hash = :digest FOR UPDATE"
        ),
        {"digest": digest},
    ).one_or_none()

    if row is None:
        raise _unauthenticated("TOKEN_MISSING")

    if row.rotated_at is not None:
        # REUSE. The whole family dies, not just this token --
        # invalidating only the presented one leaves the thief's working
        # and logs out the victim, which inverts the control [BR4.1].
        session.execute(
            sa.text(
                "UPDATE refresh_token SET rotated_at = coalesce(rotated_at, :now), "
                "reuse_detected_at = :now WHERE family_id = :family_id"
            ),
            {"now": moment, "family_id": row.family_id},
        )
        write_audit(
            session,
            account_id=row.account_id,
            event=AuthEvent.REFRESH_REUSE_DETECTED,
            correlation_id=correlation_id,
            occurred_at=moment,
        )
        session.commit()
        raise _unauthenticated("TOKEN_MISSING")

    if moment >= row.expires_at:
        raise _unauthenticated("TOKEN_MISSING")

    session.execute(
        sa.text("UPDATE refresh_token SET rotated_at = :now WHERE id = :id"),
        {"now": moment, "id": row.id},
    )
    pair = issue_pair(
        session,
        account_id=row.account_id,
        correlation_id=correlation_id,
        family_id=row.family_id,
        now=moment,
    )
    write_audit(
        session,
        account_id=row.account_id,
        event=AuthEvent.REFRESH_ROTATED,
        correlation_id=correlation_id,
        occurred_at=moment,
    )
    session.commit()
    return pair


def _unauthenticated(code: str) -> AuthorizationError:
    """Build the 401 every token failure returns.

    One code for every cause, for the same reason the OTP path has one:
    distinguishing "expired" from "replayed" from "unknown" tells an
    attacker which assumption was right.

    :param code: The stable machine code
    :return: The error to raise
    """
    return AuthorizationError(
        code=code,
        message_key="auth.token.not_valid",
        status=401,
    )
