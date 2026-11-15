"""What a username is, who may take one, and what a released one leaves behind.

The Usernames component [U1: FR1, FR3, FR5, FR7]. Three things live here
and nowhere else:

* **The judgement of a candidate** (:func:`refusal_of`, :func:`judge`):
  trim, then the FR1 rules in one fixed precedence, each refusal a
  literal ``message_key`` that never echoes the input [BR1.1 to BR1.8].
  The reserved list is here and only here.
* **The claim rule** (:func:`claim_allowed`): one decision used at
  sign-up, at verify, at the first choice and at every rename [BR6.9].
  A name is claimable when no OTHER account has its key and no live hold
  blocks it; only the account that released a held name may take it
  back, and a hold released by nobody blocks everyone.
* **The hold ledger** (:func:`place_hold`, :func:`live_hold`,
  :func:`clear_hold`): one row per keyed digest, never the name
  [BR7.1 to BR7.4]. Expired rows block nobody; the retention purge
  removes them on its own schedule [BR7.6].

And the one unit of work that changes an account's username,
:func:`apply_change`: the first choice, an ordinary rename, the one
exempt reclaim per window and a case-only change, as the decision table
in functional-spec W8 lays them out, with **the window judged before
availability** so a closed window tells the caller nothing about anyone
else's name [NFR1.6].

**Every comparison uses the lowercase key** [BR1.7]; the display form
keeps the person's casing. **Thirty days is an exact duration** between
UTC instants, not a calendar month. **No username is logged, audited or
put in an error here** [BR8.4]: audit rows carry the account id, and the
one refusal with details carries a timestamp.
"""

from __future__ import annotations

import datetime as dt
import re
import string
import uuid
from dataclasses import dataclass
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.auth.hashing import keyed_digest
from app.db.advisory import account_key, lock_keys, username_key
from app.errors import AuthorizationError, ConflictError, ValidationError

__all__ = [
    "HOLD_PERIOD",
    "INPUT_MAX_LENGTH",
    "MAX_LENGTH",
    "MIN_LENGTH",
    "RENAME_WINDOW",
    "RESERVED",
    "Availability",
    "Candidate",
    "ChangeResult",
    "Hold",
    "UsernameChangeTooSoon",
    "UsernamePasswordRequired",
    "UsernameRefused",
    "UsernameUnavailable",
    "apply_change",
    "availability",
    "claim_allowed",
    "clear_hold",
    "counter_value",
    "hold_digest",
    "holder_of",
    "is_username_clash",
    "iso_utc",
    "judge",
    "key_of",
    "live_hold",
    "next_change_at",
    "place_hold",
    "reclaim_unused",
    "refusal_of",
    "utc_now",
    "window_open",
]

#: The shortest and longest username FR1 allows, inclusive [BR1.3].
MIN_LENGTH: Final = 3
MAX_LENGTH: Final = 20

#: The longest input any request schema accepts; longer is a 422 before
#: anything here runs [BR1.3].
INPUT_MAX_LENGTH: Final = 64

#: How long a released name is held, and how long an ordinary rename
#: closes the window for: exactly 30 x 24 hours [BR6.2, BR7.2].
HOLD_PERIOD: Final = dt.timedelta(days=30)
RENAME_WINDOW: Final = dt.timedelta(days=30)

#: Names nobody may take, compared by exact key [BR1.8]. ``admin_1`` is
#: not reserved: FR1.5 says "compared without regard to case", not
#: "contains".
RESERVED: Final[frozenset[str]] = frozenset(
    {
        "admin",
        "administrator",
        "support",
        "help",
        "shikkhokplus",
        "shikkhok",
        "system",
        "root",
        "staff",
        "teacher",
        "official",
    }
)

#: The only characters a username may hold: Latin letters, digits, ``_``
#: and ``.`` [BR1.2]. Spelled out rather than ``\w``, which matches Bangla.
_CHARACTERS: Final = re.compile(r"[A-Za-z0-9_.]*")

#: The purpose prefixes that keep each keyed digest apart [BR7.1, NFR3.3].
_HOLD_PURPOSE: Final = "username-hold:v1:"
_COUNTER_PURPOSE: Final = "username-counter:v1:"

#: The uniqueness backstop's name, which a duplicate key reports [BR10.2].
_KEY_CONSTRAINT: Final = "uq_account_username_key"

#: The reserved refusal's key, which the lookups answer as ``reserved``.
_RESERVED_KEY: Final = "account.username.reserved"


class UsernameRefused(ValidationError):
    """A candidate broke one FR1 rule; the key names which [BR1.6].

    Never carries the input: the client keeps what was typed [FR1.6].
    """

    def __init__(self, message_key: str) -> None:
        """Refuse with one rule's key.

        :param message_key: Which rule; written literally by the caller
        """
        super().__init__(code="USERNAME_INVALID", message_key=message_key)


class UsernameUnavailable(ConflictError):
    """The name is taken or held, which are one answer [BR6.9, ADR-007].

    Not retryable: the remedy is a different name, not the same request.
    """

    def __init__(self) -> None:
        """Refuse without saying which of the two it was."""
        super().__init__(
            code="USERNAME_UNAVAILABLE", message_key="account.username.unavailable"
        )


class UsernameChangeTooSoon(ConflictError):
    """An ordinary rename inside the 30-day window [BR6.2, BR6.5].

    :ivar next_change_at: When an ordinary rename is next allowed
    """

    def __init__(self, next_change_at: dt.datetime) -> None:
        """Refuse, saying when, as an ISO 8601 UTC string [BR6.2].

        :param next_change_at: When an ordinary rename is next allowed
        """
        super().__init__(
            code="USERNAME_CHANGE_TOO_SOON",
            message_key="account.username.change_too_soon",
            details={"next_change_at": iso_utc(next_change_at)},
        )
        self.next_change_at = next_change_at


class UsernamePasswordRequired(ValidationError):
    """A rename, reclaim or case-only change came without a password.

    Or the account has none to give [BR6.1, Q4]; the client reads
    ``has_password`` from ``GET /v1/me`` and routes to setting one.
    """

    def __init__(self) -> None:
        """Refuse, pointing at the password."""
        super().__init__(
            code="USERNAME_PASSWORD_REQUIRED",
            message_key="account.username.password_required",
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """A username that passed FR1 [entities: UsernameCandidate].

    :ivar text: The display form: trimmed, otherwise as typed
    :ivar key: Its lowercase form, which every comparison uses
    """

    text: str
    key: str


@dataclass(frozen=True, slots=True)
class Hold:
    """A live hold on one name [BR7.4].

    :ivar releasing_account_id: The account that may take it back, or
        None when nobody may
    """

    releasing_account_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class Availability:
    """What a lookup may say about a name, and nothing more [BR3.1].

    :ivar status: ``available``, ``unavailable``, ``invalid`` or
        ``reserved``
    :ivar message_key: For ``invalid``, which rule; otherwise None
    """

    status: Literal["available", "unavailable", "invalid", "reserved"]
    message_key: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeResult:
    """What a username change answers [UsernameChangeResponse].

    :ivar username: The stored username, in its display form
    :ivar next_change_at: When an ordinary rename is next allowed, or
        None while the window is open
    """

    username: str
    next_change_at: dt.datetime | None


def utc_now() -> dt.datetime:
    """Return the moment a username decision is taken at.

    The one clock the username routes read, so a test steps through the
    30-day window by replacing it rather than by sleeping.

    :return: Now, in UTC
    """
    return dt.datetime.now(tz=dt.UTC)


def iso_utc(moment: dt.datetime) -> str:
    """Render an instant as ISO 8601 UTC with seconds and ``Z`` [BR6.2].

    :param moment: An aware instant
    :return: ``YYYY-MM-DDTHH:MM:SSZ``
    """
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ judgement


def key_of(text: str) -> str:
    """Return the lowercase key a username is compared by [BR1.7].

    :param text: The display form
    :return: Its key
    """
    return text.lower()


def refusal_of(raw: str) -> UsernameRefused | None:
    """Judge a candidate by FR1, returning the first rule it breaks.

    In BR1.6's fixed order, stopping at the first failure: characters,
    then length, then the first letter, then the dots, then the reserved
    list. Each refusal's key is written literally, for the key scanner.

    :param raw: What was typed
    :return: The refusal, or None when the candidate is valid
    """
    text = raw.strip()
    if not _CHARACTERS.fullmatch(text):
        return UsernameRefused(message_key="account.username.invalid_character")
    if len(text) < MIN_LENGTH:
        return UsernameRefused(message_key="account.username.too_short")
    if len(text) > MAX_LENGTH:
        return UsernameRefused(message_key="account.username.too_long")
    if text[0] not in string.ascii_letters:
        return UsernameRefused(message_key="account.username.must_start_with_letter")
    if text.endswith(".") or ".." in text:
        return UsernameRefused(message_key="account.username.bad_dot")
    if key_of(text) in RESERVED:
        return UsernameRefused(message_key="account.username.reserved")
    return None


def judge(raw: str) -> Candidate:
    """Accept a candidate, or raise the one refusal it earns [BR1.6].

    :param raw: What was typed
    :return: The candidate's display form and key
    :raises UsernameRefused: It breaks an FR1 rule
    """
    refused = refusal_of(raw)
    if refused is not None:
        raise refused
    text = raw.strip()
    return Candidate(text=text, key=key_of(text))


# --------------------------------------------------------- the digests


def hold_digest(key: str) -> str:
    """Return the identifier a hold on one name is stored under [BR7.1].

    :param key: The name's lowercase key
    :return: Lowercase hex HMAC-SHA256 over ``username-hold:v1:`` + key
    """
    return keyed_digest(_HOLD_PURPOSE + key)


def counter_value(key: str, network: str | None = None) -> str:
    """Return a username failure counter's scope value [NFR3.3].

    Keyed, so a counter row is not reversible by dictionary for the 48
    hours it lives. ``u:`` plus 62 hex characters is exactly the 64 the
    column holds, and can never equal a phone (``+880...``), an email
    (``e:...``), an account (``acct:...``) or a prefix value.

    :param key: The lowercase key typed at sign-in, judged or not
    :param network: The caller's /64 for the per-network scope, or None
        for the across-networks one
    :return: The scope value
    """
    message = _COUNTER_PURPOSE + key
    if network is not None:
        message += "|" + network
    return "u:" + keyed_digest(message)[:62]


# ------------------------------------------------------ the hold ledger

_LIVE_HOLD: Final = sa.text(
    "SELECT releasing_account_id FROM username_hold "
    "WHERE key_digest = :digest AND held_until > :now"
)

#: One row per digest; the latest release wins, ``created_at`` keeps the
#: first [BR7.3].
_PLACE_HOLD: Final = sa.text(
    "INSERT INTO username_hold "
    "(key_digest, held_until, releasing_account_id, created_at) "
    "VALUES (:digest, :until, :releasing, :now) "
    "ON CONFLICT (key_digest) DO UPDATE SET "
    "held_until = EXCLUDED.held_until, "
    "releasing_account_id = EXCLUDED.releasing_account_id"
)

_CLEAR_HOLD: Final = sa.text("DELETE FROM username_hold WHERE key_digest = :digest")

_HOLDER: Final = sa.text("SELECT id FROM account WHERE username_key = :key")


def live_hold(session: Session, key: str, now: dt.datetime) -> Hold | None:
    """Return the live hold on a name, if any [BR7.2].

    Live while ``now`` is strictly earlier than ``held_until``; an
    expired row reads as no hold, purged or not.

    :param session: The session to read through
    :param key: The name's lowercase key
    :param now: The moment to judge at
    :return: The hold, or None
    """
    row = session.execute(
        _LIVE_HOLD, {"digest": hold_digest(key), "now": now}
    ).one_or_none()
    if row is None:
        return None
    releasing: uuid.UUID | None = row.releasing_account_id
    return Hold(releasing_account_id=releasing)


def place_hold(
    session: Session,
    key: str,
    *,
    releasing_account_id: uuid.UUID | None,
    now: dt.datetime,
) -> None:
    """Hold a released name for 30 days. Does not commit [BR7.3, BR7.4].

    :param session: The session to write through
    :param key: The released name's lowercase key
    :param releasing_account_id: The account that may take it back, or
        None for a deletion
    :param now: The moment of release
    :return: None
    """
    session.execute(
        _PLACE_HOLD,
        {
            "digest": hold_digest(key),
            "until": now + HOLD_PERIOD,
            "releasing": releasing_account_id,
            "now": now,
        },
    )


def clear_hold(session: Session, key: str) -> None:
    """Remove any hold row on a name. Does not commit [BR6.9].

    :param session: The session to write through
    :param key: The claimed name's lowercase key
    :return: None
    """
    session.execute(_CLEAR_HOLD, {"digest": hold_digest(key)})


def holder_of(session: Session, key: str) -> uuid.UUID | None:
    """Return the account holding a name, if any.

    :param session: The session to read through
    :param key: The name's lowercase key
    :return: The account id, or None
    """
    holder: uuid.UUID | None = session.execute(
        _HOLDER, {"key": key}
    ).scalar_one_or_none()
    return holder


def claim_allowed(
    session: Session, key: str, account_id: uuid.UUID | None, now: dt.datetime
) -> bool:
    """Decide whether an account may take a name: the one claim rule [BR6.9].

    Taken under the name's advisory key by every writer, which is what
    makes the account read and the hold read one decision [BR10.1].

    :param session: The session to read through
    :param key: The candidate's lowercase key
    :param account_id: The claiming account, or None for a person not
        signed in, whom no hold can belong to
    :param now: The moment to judge holds at
    :return: True when no other account has it and no live hold blocks it
    """
    holder = holder_of(session, key)
    if holder is not None and holder != account_id:
        return False
    hold = live_hold(session, key, now)
    if hold is None:
        return True
    return account_id is not None and hold.releasing_account_id == account_id


def availability(
    session: Session, raw: str, *, caller: uuid.UUID | None, now: dt.datetime
) -> Availability:
    """Answer a lookup: four statuses and nothing more [BR3.1, BR3.2].

    Held and taken are the same ``unavailable``. Signed in, a name the
    caller itself holds -- its current key, or a live hold it released --
    is ``available``, because a rename would take it [BR3.2]. Reads only:
    no lock, no write. The ceilings are the caller's, consumed first.

    :param session: The session to read through
    :param raw: The candidate as typed
    :param caller: The signed-in account, or None for the public lookup
    :param now: The moment to judge holds at
    :return: The answer
    """
    refused = refusal_of(raw)
    if refused is not None:
        if refused.message_key == _RESERVED_KEY:
            return Availability(status="reserved")
        return Availability(status="invalid", message_key=refused.message_key)
    key = key_of(raw.strip())
    holder = holder_of(session, key)
    if holder is not None:
        return _answer(holder == caller)
    hold = live_hold(session, key, now)
    if hold is None:
        return Availability(status="available")
    return _answer(caller is not None and hold.releasing_account_id == caller)


def _answer(available: bool) -> Availability:
    """Render a yes or no as the lookup's answer.

    :param available: Whether the caller could take the name
    :return: ``available`` or ``unavailable``
    """
    return Availability(status="available" if available else "unavailable")


# ------------------------------------------------------------ the window


def window_open(changed_at: dt.datetime | None, now: dt.datetime) -> bool:
    """Report whether an ordinary rename is allowed now [BR6.2].

    :param changed_at: The last ordinary rename, or None
    :param now: The moment of the request
    :return: True when there was none, or 30 days have passed
    """
    return changed_at is None or now >= changed_at + RENAME_WINDOW


def next_change_at(
    changed_at: dt.datetime | None, now: dt.datetime
) -> dt.datetime | None:
    """Return when an ordinary rename is next allowed, or None if now.

    :param changed_at: The last ordinary rename, or None
    :param now: The moment of the request
    :return: ``changed_at`` + 30 days while the window is closed, else None
    """
    if changed_at is None or window_open(changed_at, now):
        return None
    return changed_at + RENAME_WINDOW


def reclaim_unused(changed_at: dt.datetime, reclaimed_at: dt.datetime | None) -> bool:
    """Report whether this window's one exempt reclaim is still unused.

    [BR6.4, BR6.5] Unused while never spent, or spent before the last
    ordinary rename opened the current window.

    :param changed_at: The last ordinary rename
    :param reclaimed_at: The last exempt reclaim, or None
    :return: True when a reclaim would be exempt
    """
    return reclaimed_at is None or reclaimed_at < changed_at


# ------------------------------------------------------ the change unit

#: The account's username columns, re-read under its key [NFR4.2].
_LOCKED_ACCOUNT: Final = sa.text(
    "SELECT username, username_key, username_changed_at, username_reclaimed_at "
    "FROM account WHERE id = :id FOR UPDATE"
)

_STORE: Final = sa.text(
    "UPDATE account SET username = :text, username_key = :key, "
    "username_changed_at = :changed, username_reclaimed_at = :reclaimed "
    "WHERE id = :id"
)


def is_username_clash(error: sa.exc.IntegrityError) -> bool:
    """Report whether an integrity error is the username key's uniqueness.

    [BR10.2] A writer that reached the constraint lost a race the
    advisory key should have serialised; its answer is the same clean
    ``unavailable``, never a server error. Any other constraint keeps its
    own handling.

    :param error: The driver error, wrapped
    :return: True for ``uq_account_username_key``
    """
    diagnostics: object = getattr(error.orig, "diag", None)
    name: object = getattr(diagnostics, "constraint_name", None)
    return name == _KEY_CONSTRAINT


@dataclass(frozen=True, slots=True)
class _Current:
    """The account's username columns, as the locked re-read found them.

    :ivar text: The display form
    :ivar key: Its key
    :ivar changed_at: The last ordinary rename, or None
    :ivar reclaimed_at: The last exempt reclaim, or None
    """

    text: str
    key: str
    changed_at: dt.datetime | None
    reclaimed_at: dt.datetime | None


def apply_change(
    session: Session,
    account_id: uuid.UUID,
    candidate: Candidate,
    *,
    password_confirmed: bool,
    now: dt.datetime,
    correlation_id: str,
) -> ChangeResult:
    """Give the account a username, or change it: one re-runnable unit.

    [W7, W8, W8a; NFR4.2, NFR4.3] The WHOLE transaction, ending in its own
    commit and sending nothing before it, so the route runs it under the
    bounded retry. Two lock calls: the account's key, then a re-read of
    the row ``FOR UPDATE``, then the new and the old names' keys, with the
    old key taken from that locked re-read so a stale one can never be
    held [R-06]. Username keys come last, as everywhere [BR10.1].

    An account with no username is a first choice [BR5.3]. One that has
    one -- including one that gained it a moment ago on another device --
    is a rename and needs ``password_confirmed`` [BR6.1].

    :param session: The request's session
    :param account_id: The authenticated account
    :param candidate: The judged candidate
    :param password_confirmed: The route confirmed the account's password
    :param now: The moment of the request
    :param correlation_id: Ties the audit row to the request
    :return: The stored username and when it may next change
    :raises AuthorizationError: 401 when the account is gone
    :raises UsernamePasswordRequired: A rename without a confirmed password
    :raises UsernameUnavailable: The name is taken or held [BR6.9]
    :raises UsernameChangeTooSoon: An ordinary rename inside the window
    """
    lock_keys(session, [account_key(account_id)])
    row = session.execute(_LOCKED_ACCOUNT, {"id": account_id}).one_or_none()
    if row is None:
        # Deleted between authentication and here: the next request is a
        # 401 anyway, so this one answers as that one will.
        raise AuthorizationError(
            code="NOT_AUTHENTICATED", message_key="auth.token.not_valid", status=401
        )
    if row.username_key is None:
        result = _first_choice(session, account_id, candidate, now, correlation_id)
    else:
        if not password_confirmed:
            raise UsernamePasswordRequired()
        current = _Current(
            text=row.username,
            key=row.username_key,
            changed_at=row.username_changed_at,
            reclaimed_at=row.username_reclaimed_at,
        )
        lock_keys(session, [username_key(candidate.key), username_key(current.key)])
        result = _rename(session, account_id, candidate, current, now, correlation_id)
    session.commit()
    return result


def _first_choice(
    session: Session,
    account_id: uuid.UUID,
    candidate: Candidate,
    now: dt.datetime,
    correlation_id: str,
) -> ChangeResult:
    """Set the first username: no limit, no hold, no window [BR5.3].

    :param session: The request's session
    :param account_id: The account
    :param candidate: The judged candidate
    :param now: The moment of the request
    :param correlation_id: Ties the audit row to the request
    :return: The username, with no next-change limit
    :raises UsernameUnavailable: The name is taken or held
    """
    lock_keys(session, [username_key(candidate.key)])
    if not claim_allowed(session, candidate.key, account_id, now):
        raise UsernameUnavailable()
    _store(session, account_id, candidate, changed_at=None, reclaimed_at=None)
    clear_hold(session, candidate.key)
    write_audit(session, account_id, AuthEvent.USERNAME_SET, correlation_id, now)
    return ChangeResult(username=candidate.text, next_change_at=None)


def _rename(
    session: Session,
    account_id: uuid.UUID,
    candidate: Candidate,
    current: _Current,
    now: dt.datetime,
    correlation_id: str,
) -> ChangeResult:
    """Judge and apply a rename by functional-spec W8's decision table.

    The window comes BEFORE availability [NFR1.6]: with it closed, only
    an exempt reclaim of the caller's own held name reads any further,
    and every other target is ``change_too_soon`` without a read of
    whether anyone else has it.

    :param session: The request's session
    :param account_id: The account
    :param candidate: The judged candidate
    :param current: The locked re-read
    :param now: The moment of the request
    :param correlation_id: Ties the audit row to the request
    :return: The username and when it may next change
    :raises UsernameUnavailable: The name is taken or held [BR6.9]
    :raises UsernameChangeTooSoon: Inside the window, and not an exempt
        reclaim [BR6.2, BR6.5]
    """
    if candidate.key == current.key:
        return _case_only(session, account_id, candidate, current, now, correlation_id)
    if window_open(current.changed_at, now):
        if not claim_allowed(session, candidate.key, account_id, now):
            raise UsernameUnavailable()
        _store(
            session,
            account_id,
            candidate,
            changed_at=now,
            reclaimed_at=current.reclaimed_at,
        )
        next_change: dt.datetime = now + RENAME_WINDOW
    else:
        assert current.changed_at is not None  # noqa: S101 -- the window is closed
        hold = live_hold(session, candidate.key, now)
        if (
            hold is None
            or hold.releasing_account_id != account_id
            or not reclaim_unused(current.changed_at, current.reclaimed_at)
        ):
            raise UsernameChangeTooSoon(current.changed_at + RENAME_WINDOW)
        # The exempt reclaim [BR6.4]: the window does not move.
        _store(
            session,
            account_id,
            candidate,
            changed_at=current.changed_at,
            reclaimed_at=now,
        )
        next_change = current.changed_at + RENAME_WINDOW
    clear_hold(session, candidate.key)
    place_hold(session, current.key, releasing_account_id=account_id, now=now)
    write_audit(session, account_id, AuthEvent.USERNAME_CHANGED, correlation_id, now)
    return ChangeResult(username=candidate.text, next_change_at=next_change)


def _case_only(
    session: Session,
    account_id: uuid.UUID,
    candidate: Candidate,
    current: _Current,
    now: dt.datetime,
    correlation_id: str,
) -> ChangeResult:
    """Apply a change of letter case only, which is not a rename [BR6.7, Q3].

    The identical text is a no-op with no audit row. Otherwise only the
    display form changes: no hold, and neither timestamp moves.

    :param session: The request's session
    :param account_id: The account
    :param candidate: The judged candidate, same key as the current one
    :param current: The locked re-read
    :param now: The moment of the request
    :param correlation_id: Ties the audit row to the request
    :return: The username and whatever the window currently reports
    """
    if candidate.text != current.text:
        _store(
            session,
            account_id,
            candidate,
            changed_at=current.changed_at,
            reclaimed_at=current.reclaimed_at,
        )
        write_audit(
            session, account_id, AuthEvent.USERNAME_CHANGED, correlation_id, now
        )
    return ChangeResult(
        username=candidate.text,
        next_change_at=next_change_at(current.changed_at, now),
    )


def _store(
    session: Session,
    account_id: uuid.UUID,
    candidate: Candidate,
    *,
    changed_at: dt.datetime | None,
    reclaimed_at: dt.datetime | None,
) -> None:
    """Write the account's username columns, mapping a duplicate key.

    :param session: The request's session
    :param account_id: The account
    :param candidate: The name to store
    :param changed_at: The value ``username_changed_at`` is to hold
    :param reclaimed_at: The value ``username_reclaimed_at`` is to hold
    :return: None
    :raises UsernameUnavailable: The key's uniqueness refused it [BR10.2]
    """
    try:
        session.execute(
            _STORE,
            {
                "text": candidate.text,
                "key": candidate.key,
                "changed": changed_at,
                "reclaimed": reclaimed_at,
                "id": account_id,
            },
        )
    except sa.exc.IntegrityError as error:
        if is_username_clash(error):
            raise UsernameUnavailable() from error
        raise
