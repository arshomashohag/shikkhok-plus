"""Access tokens, and refresh rotation with reuse detection.

**Reuse detection degrades silently into non-rotating tokens**, because
the happy path is identical either way [BR4.1]. The difference appears
only when an old token is presented again -- which is exactly the
stolen-token case the mechanism exists for. So it is tested as a state
machine rather than as a happy path -- including the one bounded
exception, the grace for a retry after a lost response [PA-SEC-4].

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
    "ADMIN_AUDIENCE",
    "ADMIN_TOKEN_LIFETIME",
    "APP_MFA_CHALLENGE_AUDIENCE",
    "JWT_ACTIVE_KID_ENV",
    "MFA_CHALLENGE_AUDIENCE",
    "MFA_CHALLENGE_LIFETIME",
    "REFRESH_GRACE_WINDOW",
    "REFRESH_TOKEN_LIFETIME",
    "TokenPair",
    "issue_pair",
    "issue_scoped_token",
    "rotate",
    "verify_access_token",
    "verify_scoped_token",
]

#: Fifteen minutes, enforced server-side [BR4.2].
ACCESS_TOKEN_LIFETIME: Final = dt.timedelta(minutes=15)

#: Thirty days. Long enough that a signing-key rotation without ``kid``
#: would be a mass-logout event, which is why ``kid`` is here from the
#: first commit.
REFRESH_TOKEN_LIFETIME: Final = dt.timedelta(days=30)

#: How long after a rotation its old token may be re-presented as a
#: retry rather than a replay [PA-SEC-4]. Long enough to cover a mobile
#: client's timeout-and-retry on a lost response; short enough that a
#: thief holding the previous token gains a minute, not a session --
#: and even inside it, only while the successor is unused, so the moment
#: the real client spends its token the window is closed to everyone.
REFRESH_GRACE_WINDOW: Final = dt.timedelta(seconds=60)

#: Names the environment variable holding the active key id.
JWT_ACTIVE_KID_ENV: Final = "SHIKKHOKPLUS_JWT_ACTIVE_KID"

#: Names the variable holding the key map, as ``kid:secret`` pairs.
JWT_KEYS_ENV: Final = "SHIKKHOKPLUS_JWT_KEYS"

_ALGORITHM: Final = "HS256"

#: The audience of a platform administrator's access token. **Only the
#: admin sign-in issues one, and only the admin routes accept one**: an
#: app token carries no audience and is refused on admin routes, and an
#: admin token is refused everywhere else, so neither can stand in for
#: the other [TC-14, D-6].
ADMIN_AUDIENCE: Final = "shikkhokplus-admin"

#: An hour, with no refresh token: an administrator signs in again with
#: an SMS code and an authenticator code when it lapses.
ADMIN_TOKEN_LIFETIME: Final = dt.timedelta(hours=1)

#: The audience of the short-lived token that carries an administrator
#: from the SMS step to the authenticator step. It grants nothing on
#: its own.
MFA_CHALLENGE_AUDIENCE: Final = "shikkhokplus-admin-mfa"

#: Long enough to open an authenticator app, or to scan a QR code.
MFA_CHALLENGE_LIFETIME: Final = dt.timedelta(minutes=5)

#: The audience of the token that carries an app user from the SMS step
#: to the authenticator step, once they have turned the factor on. Not
#: the admin challenge's audience, so neither can finish the other's sign-in.
APP_MFA_CHALLENGE_AUDIENCE: Final = "shikkhokplus-mfa"


@dataclass(frozen=True, slots=True)
class TokenPair:
    """One access token and the refresh token that will replace it.

    :ivar access_token: The signed, short-lived bearer token
    :ivar refresh_token: The opaque long-lived token, stored hashed
    :ivar family_id: The rotation chain this pair belongs to
    :ivar account_id: The account the pair was issued to
    """

    access_token: str
    refresh_token: str
    family_id: uuid.UUID
    account_id: uuid.UUID


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
        account_id=account_id,
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

    # An app token carries no audience. One that does was issued for the
    # admin surface or the MFA step and is not an app session -- refused
    # explicitly here rather than relying on the library's behaviour for
    # an unexpected audience.
    if "aud" in claims:
        raise _unauthenticated("TOKEN_MISSING")

    # Expiry is compared SERVER-SIDE against our own clock rather than
    # trusted from the library's default, so the one assertion the rule
    # names is the one actually made [BR4.2].
    if moment.timestamp() >= float(claims["exp"]):
        raise _unauthenticated("ACCESS_TOKEN_EXPIRED")

    return uuid.UUID(claims["sub"])


def issue_scoped_token(
    account_id: uuid.UUID,
    audience: str,
    lifetime: dt.timedelta,
    extra: dict[str, str] | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Sign a token for one audience: the admin surface or the MFA step.

    :param account_id: The subject
    :param audience: :data:`ADMIN_AUDIENCE` or :data:`MFA_CHALLENGE_AUDIENCE`
    :param lifetime: How long it lives
    :param extra: Further string claims, such as the MFA stage
    :param now: The issue time, or None for the clock
    :return: The encoded token
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    kid = _active_kid()
    claims: dict[str, Any] = {
        **(extra or {}),
        "sub": str(account_id),
        "aud": audience,
        "iat": int(moment.timestamp()),
        "exp": int((moment + lifetime).timestamp()),
    }
    return jwt.encode(claims, _keys()[kid], algorithm=_ALGORITHM, headers={"kid": kid})


def verify_scoped_token(
    token: str, audience: str, now: dt.datetime | None = None
) -> dict[str, Any]:
    """Verify a token issued for exactly one audience.

    :param token: The presented token
    :param audience: The audience it must carry
    :param now: The moment to compare expiry against, or None for the clock
    :return: Its claims
    :raises AuthorizationError: 401 when it is unverifiable, expired, or
        issued for any other audience, including an app token with none
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
            audience=audience,
            options={"verify_exp": False, "require": ["aud", "sub", "exp"]},
        )
    except jwt.PyJWTError as error:
        raise _unauthenticated("TOKEN_MISSING") from error
    if moment.timestamp() >= float(claims["exp"]):
        raise _unauthenticated("ACCESS_TOKEN_EXPIRED")
    return claims


def rotate(
    session: Session,
    presented: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> TokenPair:
    """Rotate a refresh token, invalidating the family on reuse.

    **One exception to reuse** [PA-SEC-4]: the immediately previous
    token, re-presented within :data:`REFRESH_GRACE_WINDOW` while its
    successor is unused, is a client retrying after a lost response.
    The server committed the rotation and the response never arrived;
    without this, the client's only retry logs the person out. That
    case revokes the unreceived successor and issues a fresh pair in
    the same family. Every other re-presentation is reuse.

    :param session: The session to work through
    :param presented: The refresh token the client sent
    :param correlation_id: Ties the audit row to this request
    :param now: The moment of rotation, or None for the clock
    :return: The replacement pair
    :raises AuthorizationError: The token is unknown, expired or replayed
    """
    moment = now or dt.datetime.now(tz=dt.UTC)
    digest = hash_refresh_token(presented)

    # FOR UPDATE on the presented row serializes every rotation, grace
    # or replay of one token: two concurrent retries cannot both read
    # its successor unused and each open a live branch.
    row = session.execute(
        sa.text(
            "SELECT id, account_id, family_id, expires_at, rotated_at, "
            "reuse_detected_at "
            "FROM refresh_token WHERE token_hash = :digest FOR UPDATE"
        ),
        {"digest": digest},
    ).one_or_none()

    if row is None:
        raise _unauthenticated("TOKEN_MISSING")

    if row.rotated_at is not None:
        successor_id = _unused_successor_within_grace(session, row, moment)
        if successor_id is not None:
            return _reissue_within_grace(
                session, row, successor_id, correlation_id, moment
            )
        # REUSE: an older token, outside the window, a spent successor,
        # or a family already revoked. The whole family dies, not just
        # this token --
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


def _unused_successor_within_grace(
    session: Session, row: sa.Row[Any], moment: dt.datetime
) -> uuid.UUID | None:
    """Return the presented token's unused successor, if a grace applies.

    **A grace applies only to the immediately previous token of a live
    family** [PA-SEC-4], and every condition below is one edge of that:

    * within :data:`REFRESH_GRACE_WINDOW` of the presented token's
      rotation, and the token itself not expired;
    * the family not already revoked;
    * the token's direct successor -- the one row its rotation issued,
      found by ``issued_at`` equal to its ``rotated_at``, because both
      are written with the same moment -- exists exactly once and has
      itself never been rotated or revoked.

    The last one is what makes this a retry rather than a replay. If the
    successor has been spent, the client that rotated DID receive it, so
    the old token reappearing is the stolen-token case and gets today's
    answer. It is also what limits a token to one grace: the grace
    revokes the successor, so the same old token presented again finds
    it spent.

    The successor is locked too, so a concurrent legitimate rotation of
    it and this grace serialize rather than both succeeding.

    :param session: The session to read through
    :param row: The presented, already-rotated token's row
    :param moment: The moment of this request
    :return: The successor's id, or None when this is a replay
    """
    if row.reuse_detected_at is not None or moment >= row.expires_at:
        return None
    if not row.rotated_at <= moment <= row.rotated_at + REFRESH_GRACE_WINDOW:
        return None

    successors = session.execute(
        sa.text(
            "SELECT id, rotated_at, reuse_detected_at FROM refresh_token "
            "WHERE family_id = :family_id AND issued_at = :rotated_at "
            "AND id <> :id FOR UPDATE"
        ),
        {"family_id": row.family_id, "rotated_at": row.rotated_at, "id": row.id},
    ).all()
    if len(successors) != 1:
        return None
    successor = successors[0]
    if successor.rotated_at is not None or successor.reuse_detected_at is not None:
        return None
    successor_id: uuid.UUID = successor.id
    return successor_id


def _reissue_within_grace(
    session: Session,
    row: sa.Row[Any],
    successor_id: uuid.UUID,
    correlation_id: str,
    moment: dt.datetime,
) -> TokenPair:
    """Revoke the unreceived successor and issue a fresh pair in its place.

    **A fresh pair, not the lost one**: only hashes are stored, so the
    pair whose response was lost cannot be returned. It stays in the
    same family, so a later reuse of anything in the chain still revokes
    everything the client holds.

    The successor is revoked by setting ``rotated_at`` -- so presenting
    it is reuse -- and ``expires_at`` to now, so it earns **no grace of
    its own**: it was never received by the client that retried, so if
    it ever turns up, someone else had it.

    :param session: The session to write through
    :param row: The presented token's row
    :param successor_id: The unreceived successor to revoke
    :param correlation_id: Ties the audit row to this request
    :param moment: The moment of this request
    :return: The replacement pair
    """
    session.execute(
        sa.text(
            "UPDATE refresh_token SET rotated_at = :now, expires_at = :now "
            "WHERE id = :id"
        ),
        {"now": moment, "id": successor_id},
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
        event=AuthEvent.REFRESH_GRACE_REISSUED,
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
