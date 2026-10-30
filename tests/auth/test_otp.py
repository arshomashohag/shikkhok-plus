"""Expiry, single use, the attempt ceiling, and the existence oracle.

The oracle test is the one worth reading carefully. **A test asserting
only that the two responses match leaves the louder channel wide open**:
the known branch performs a transactional INSERT and the unknown branch,
written naively, performs none -- and a write means lock acquisition and
a WAL flush, which dominates a hash computation as a timing signal.

So the assertion is that both branches **issue the same statements**, and
it is made by capturing them, not by reading the code.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.otp import (
    ATTEMPT_CEILING,
    CODE_LIFETIME,
    OTP_PURPOSE,
    IssuedCode,
)
from app.auth.otp import (
    issue as _issue,
)
from app.auth.otp import (
    verify as _verify,
)
from app.db.models import Account
from app.errors import ValidationError

KNOWN = "+8801711111111"
UNKNOWN = "+8801799999999"
CORRELATION = "test-correlation-id"


# Every test in THIS file is about the sign-in purpose: the oracle, the
# expiry, the single-use rule and the attempt ceiling are all properties
# of one code regardless of what it is for. The purpose is bound once
# here rather than repeated at thirty call sites, which would make the
# one file where the purpose MATTERS -- test_otp_purpose.py -- read the
# same as this one.
#
# Bound explicitly to OTP_PURPOSE rather than defaulted in `issue`
# itself: the absent default is the control, and a wrapper that supplied
# one in production code is exactly what D6 was the second consumer of.


def issue(
    session: Session,
    phone: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> IssuedCode:
    """Issue a SIGN-IN code.

    :param session: The session to write through
    :param phone: The number to issue for
    :param correlation_id: Ties the audit row to this request
    :param now: The moment of issue, or None for the clock
    :return: The code and whether an account existed
    """
    return _issue(session, phone, correlation_id, purpose=OTP_PURPOSE, now=now)


def verify(
    session: Session,
    phone: str,
    code: str,
    correlation_id: str,
    now: dt.datetime | None = None,
) -> uuid.UUID:
    """Verify a SIGN-IN code.

    :param session: The session to work through
    :param phone: The number being verified
    :param code: The presented code
    :param correlation_id: Ties the audit row to this request
    :param now: The moment of verification, or None for the clock
    :return: The authenticated account's id
    :raises ValidationError: The code is wrong, expired, used or dead
    """
    return _verify(session, phone, code, correlation_id, purpose=OTP_PURPOSE, now=now)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a test HMAC key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")


@pytest.fixture
def known_account(owner_session: Session) -> uuid.UUID:
    """Create the account the known-number branch finds.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(phone=KNOWN, created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(record)
    owner_session.commit()
    return record.id


# ---------------------------------------------------------------------------
# THE EXISTENCE ORACLE. [BR2.7]
# ---------------------------------------------------------------------------


def _normalize(statement: str) -> str:
    """Reduce a statement to its shape, dropping values and whitespace.

    :param statement: The raw SQL
    :return: A comparable shape
    """
    return re.sub(r"\s+", " ", statement).strip().lower()


def _capture(engine: Engine, session: Session, phone: str) -> list[str]:
    """Record every statement one issue call makes.

    :param engine: The engine to watch
    :param session: The session to issue through
    :param phone: The number to issue for
    :return: The normalized statements, in order
    """
    seen: list[str] = []

    def record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        seen.append(_normalize(statement))

    event.listen(engine, "before_cursor_execute", record)
    try:
        issue(session, phone, CORRELATION)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return seen


def test_both_branches_issue_the_same_statements(
    restricted_session: Session, restricted_engine: Engine, known_account: uuid.UUID
) -> None:
    # THE LOUDER CHANNEL. A database write involves lock acquisition and
    # a WAL flush -- a far larger and more reliable timing signal than a
    # hash. An early return on the unknown branch skips the INSERT
    # entirely, and this is what detects that [BR2.7].
    known = _capture(restricted_engine, restricted_session, KNOWN)
    unknown = _capture(restricted_engine, restricted_session, UNKNOWN)

    known_inserts = [s for s in known if s.startswith("insert into otp_request")]
    unknown_inserts = [s for s in unknown if s.startswith("insert into otp_request")]

    assert known_inserts, "the known branch did not INSERT"
    assert unknown_inserts == known_inserts, (
        "the unknown branch did not perform the equivalent write: the "
        "WAL flush is the oracle this rule exists to close [BR2.7]"
    )


def test_the_unknown_branch_keeps_a_row_that_can_never_verify(
    restricted_session: Session,
) -> None:
    # The row is KEPT so verify answers an unknown number exactly as it
    # answers a known one (tries left, expiry) [BR2.7]. Its code was
    # never sent, and even the right digits authenticate nobody.
    issued = issue(restricted_session, UNKNOWN, CORRELATION)
    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM otp_request WHERE phone = :phone"),
        {"phone": UNKNOWN},
    ).scalar_one()
    assert rows == 1

    with pytest.raises(ValidationError) as refused:
        verify(restricted_session, UNKNOWN, issued.code, CORRELATION)
    assert refused.value.message_key == "auth.otp.not_valid"


def test_the_known_branch_stores_its_row(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issue(restricted_session, KNOWN, CORRELATION)
    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM otp_request WHERE phone = :phone"),
        {"phone": KNOWN},
    ).scalar_one()
    assert rows == 1


def test_both_branches_return_the_same_response_shape(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    known = issue(restricted_session, KNOWN, CORRELATION)
    unknown = issue(restricted_session, UNKNOWN, CORRELATION)
    assert len(known.code) == len(unknown.code)
    assert known.code.isdigit() and unknown.code.isdigit()


def test_an_unknown_number_still_writes_an_audit_row(
    restricted_session: Session,
) -> None:
    issue(restricted_session, UNKNOWN, CORRELATION)
    row = restricted_session.execute(
        sa.text(
            "SELECT account_id, event FROM auth_audit_log WHERE correlation_id = :cid"
        ),
        {"cid": CORRELATION},
    ).one()
    # Nullable BY DESIGN: a placeholder would reintroduce the oracle.
    assert row.account_id is None
    assert row.event == "OTP_ISSUED"


def test_the_audit_row_carries_no_phone_number(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issued = issue(restricted_session, KNOWN, CORRELATION)
    columns = restricted_session.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'auth_audit_log'"
        )
    ).scalars()
    assert "phone" not in set(columns)

    row = restricted_session.execute(
        sa.text("SELECT * FROM auth_audit_log WHERE correlation_id = :cid"),
        {"cid": CORRELATION},
    ).one()
    rendered = " ".join(str(value) for value in row)
    assert KNOWN not in rendered
    assert issued.code not in rendered


# ---------------------------------------------------------------------------
# Expiry, single use, the attempt ceiling. [BR2.3]
# ---------------------------------------------------------------------------


def test_a_code_presented_at_five_minutes_and_one_second_is_refused(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    issued = issue(restricted_session, KNOWN, CORRELATION, now=now)

    late = now + CODE_LIFETIME + dt.timedelta(seconds=1)
    with pytest.raises(ValidationError):
        verify(restricted_session, KNOWN, issued.code, CORRELATION, now=late)


def test_a_code_presented_within_the_window_verifies(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    issued = issue(restricted_session, KNOWN, CORRELATION, now=now)

    inside = now + CODE_LIFETIME - dt.timedelta(seconds=1)
    assert (
        verify(restricted_session, KNOWN, issued.code, CORRELATION, now=inside)
        == known_account
    )


def test_a_verified_code_cannot_verify_again(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issued = issue(restricted_session, KNOWN, CORRELATION)
    verify(restricted_session, KNOWN, issued.code, CORRELATION)

    with pytest.raises(ValidationError):
        verify(restricted_session, KNOWN, issued.code, CORRELATION)


def test_the_sixth_attempt_is_refused_and_the_code_is_dead_afterwards(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    # THE HALF A CONFIRMATORY TEST MISSES. An implementation that counts
    # attempts without invalidating the code passes "the 6th is refused"
    # and leaves brute force open, because a CORRECT 7th still works.
    issued = issue(restricted_session, KNOWN, CORRELATION)

    for _ in range(ATTEMPT_CEILING):
        with pytest.raises(ValidationError):
            verify(restricted_session, KNOWN, "000000", CORRELATION)

    with pytest.raises(ValidationError):
        verify(restricted_session, KNOWN, "000000", CORRELATION)

    with pytest.raises(ValidationError):
        verify(restricted_session, KNOWN, issued.code, CORRELATION)


def test_a_wrong_code_below_the_ceiling_leaves_the_code_alive(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issued = issue(restricted_session, KNOWN, CORRELATION)

    with pytest.raises(ValidationError):
        verify(restricted_session, KNOWN, "000000", CORRELATION)

    assert verify(restricted_session, KNOWN, issued.code, CORRELATION) == known_account


def test_every_refusal_returns_the_same_code(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    # Distinguishing expired from wrong from exhausted tells an attacker
    # which assumption was right and tells a user nothing actionable.
    now = dt.datetime.now(tz=dt.UTC)
    issued = issue(restricted_session, KNOWN, CORRELATION, now=now)

    with pytest.raises(ValidationError) as wrong:
        verify(restricted_session, KNOWN, "000000", CORRELATION, now=now)

    late = now + CODE_LIFETIME + dt.timedelta(seconds=1)
    with pytest.raises(ValidationError) as expired:
        verify(restricted_session, KNOWN, issued.code, CORRELATION, now=late)

    assert wrong.value.code == expired.value.code


def test_a_wrong_code_says_how_many_tries_are_left(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issue(restricted_session, KNOWN, CORRELATION)

    with pytest.raises(ValidationError) as first:
        verify(restricted_session, KNOWN, "000000", CORRELATION)
    with pytest.raises(ValidationError) as second:
        verify(restricted_session, KNOWN, "000000", CORRELATION)

    assert first.value.message_key == "auth.otp.wrong"
    assert first.value.details == {"attempts_left": str(ATTEMPT_CEILING - 1)}
    assert second.value.details == {"attempts_left": str(ATTEMPT_CEILING - 2)}


def test_the_last_wrong_try_says_none_are_left(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issue(restricted_session, KNOWN, CORRELATION)
    for _ in range(ATTEMPT_CEILING - 1):
        with pytest.raises(ValidationError):
            verify(restricted_session, KNOWN, "000000", CORRELATION)

    with pytest.raises(ValidationError) as last:
        verify(restricted_session, KNOWN, "000000", CORRELATION)

    assert last.value.message_key == "auth.otp.no_tries_left"
    assert last.value.details is None


def test_an_expired_code_says_it_expired(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    issued = issue(restricted_session, KNOWN, CORRELATION, now=now)

    late = now + CODE_LIFETIME + dt.timedelta(seconds=1)
    with pytest.raises(ValidationError) as refused:
        verify(restricted_session, KNOWN, issued.code, CORRELATION, now=late)

    assert refused.value.message_key == "auth.otp.expired"


def test_a_used_code_is_not_called_expired(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    issued = issue(restricted_session, KNOWN, CORRELATION, now=now)
    verify(restricted_session, KNOWN, issued.code, CORRELATION, now=now)

    late = now + CODE_LIFETIME + dt.timedelta(seconds=1)
    with pytest.raises(ValidationError) as refused:
        verify(restricted_session, KNOWN, issued.code, CORRELATION, now=late)

    assert refused.value.message_key == "auth.otp.not_valid"


def _refusal(session: Session, phone: str, now: dt.datetime) -> tuple[object, ...]:
    """Run one wrong verify and one expired verify, keeping each answer.

    :param session: The session to work through
    :param phone: The number to probe
    :param now: The moment the code is issued
    :return: The two refusals' observable parts
    """
    issue(session, phone, CORRELATION, now=now)
    seen: list[object] = []
    for moment in (now, now + CODE_LIFETIME + dt.timedelta(seconds=1)):
        with pytest.raises(ValidationError) as refused:
            verify(session, phone, "000000", CORRELATION, now=moment)
        seen.append(
            (refused.value.code, refused.value.message_key, refused.value.details)
        )
    return tuple(seen)


def test_every_answer_is_the_same_with_or_without_an_account(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    # THE ORACLE THE TRIES-LEFT COUNT COULD HAVE OPENED [BR2.7]. A count
    # for a registered number and none for an unregistered one would
    # answer "is this number registered?" for anyone who asks.
    now = dt.datetime.now(tz=dt.UTC)

    assert _refusal(restricted_session, KNOWN, now) == _refusal(
        restricted_session, UNKNOWN, now
    )


def test_a_dormant_account_activates_on_first_verify(
    restricted_session: Session, owner_session: Session
) -> None:
    # This is what lets a student or guardian claim a record a teacher
    # created, without being invited [AC1.2.1].
    dormant = Account(phone="+8801755555555", created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(dormant)
    owner_session.commit()
    assert dormant.activated_at is None

    issued = issue(restricted_session, dormant.phone, CORRELATION)
    verify(restricted_session, dormant.phone, issued.code, CORRELATION)

    activated = restricted_session.execute(
        sa.text("SELECT activated_at FROM account WHERE id = :id"),
        {"id": dormant.id},
    ).scalar_one()
    assert activated is not None


def test_the_stored_value_is_never_the_transmitted_code(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    issued = issue(restricted_session, KNOWN, CORRELATION)
    stored = restricted_session.execute(
        sa.text("SELECT otp_hash FROM otp_request WHERE phone = :phone"),
        {"phone": KNOWN},
    ).scalar_one()
    assert stored != issued.code


def test_an_attempt_row_is_written_per_attempt(
    restricted_session: Session, known_account: uuid.UUID
) -> None:
    # A row per attempt rather than a counter, so the audit log can
    # answer "was this code attacked" rather than only "how many times".
    issue(restricted_session, KNOWN, CORRELATION)
    for _ in range(3):
        with pytest.raises(ValidationError):
            verify(restricted_session, KNOWN, "000000", CORRELATION)

    attempts = restricted_session.execute(
        sa.text("SELECT count(*) FROM verify_attempt")
    ).scalar_one()
    assert attempts == 3
