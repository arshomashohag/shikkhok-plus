"""A code issued for one purpose cannot be spent on another.

**As built before D6, a sign-in code would confirm an account
deletion.** ``issue()`` wrote the module constant ``OTP_PURPOSE`` and
``verify()`` selected ``WHERE phone = :phone`` with no purpose
predicate, so the two never had to agree -- and D6's public deletion
route is the second consumer that makes the gap reachable.

Test-first under the ordering predicate: the correct answer is knowable
from the requirement without the code, and a wrong answer is an
authorization error of the sharpest kind -- a code someone requested to
sign in destroying their account instead [DESIGN-1].

**The shadowing test is the one that distinguishes the two plausible
fixes**, and the ORDERING inside it is the test. ``verify()`` returns
the latest row for the phone; a purpose check applied AFTER the row is
fetched passes every single-code test and refuses a real user whose
deletion code happens to be older than a sign-in code they requested
while making up their mind. The refusal is ``_refused()``, which is
deliberately contentless, so they are told nothing and conclude the
feature is broken.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.hashing import OTP_HMAC_KEY_ENV
from app.auth.otp import DELETION_PURPOSE, OTP_PURPOSE, issue, verify
from app.db.models import Account
from app.errors import ValidationError

PHONE = "+8801733333333"
CORRELATION = "test-correlation-id"


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a test HMAC key.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create the account every code here is issued against.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(phone=PHONE, created_at=dt.datetime.now(tz=dt.UTC))
    owner_session.add(record)
    owner_session.commit()
    return record.id


def test_a_sign_in_code_does_not_verify_for_deletion(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """The finding, asserted directly.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    issued = issue(restricted_session, PHONE, CORRELATION, purpose=OTP_PURPOSE)

    with pytest.raises(ValidationError):
        verify(
            restricted_session,
            PHONE,
            issued.code,
            CORRELATION,
            purpose=DELETION_PURPOSE,
        )


def test_a_deletion_code_does_not_sign_in(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """The inverse, which a one-directional filter would pass.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    issued = issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)

    with pytest.raises(ValidationError):
        verify(
            restricted_session,
            PHONE,
            issued.code,
            CORRELATION,
            purpose=OTP_PURPOSE,
        )


def test_each_purpose_verifies_its_own_code(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """The positive half, so the filter is not merely refusing everything.

    Without this, a ``verify()`` that refused unconditionally would pass
    both tests above.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    sign_in = issue(restricted_session, PHONE, CORRELATION, purpose=OTP_PURPOSE)
    assert (
        verify(
            restricted_session,
            PHONE,
            sign_in.code,
            CORRELATION,
            purpose=OTP_PURPOSE,
        )
        == account
    )

    deletion = issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)
    assert (
        verify(
            restricted_session,
            PHONE,
            deletion.code,
            CORRELATION,
            purpose=DELETION_PURPOSE,
        )
        == account
    )


# ---------------------------------------------------------------------------
# THE SHADOWING CASE.
#
# **A test that issues only ONE code passes against the shadowing
# defect.** With one row, `ORDER BY issued_at DESC LIMIT 1` returns it
# whether the purpose is filtered in the WHERE or checked afterwards, so
# the two implementations are indistinguishable.
#
# The bug needs TWO codes for one number with the deletion one OLDER.
# Reversing the order in this test tests nothing.
# ---------------------------------------------------------------------------


def test_a_later_sign_in_code_does_not_shadow_a_deletion_code(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """Issue deletion, THEN sign-in, then verify the deletion code.

    The real sequence this models: a person requests a deletion code, is
    unsure, signs in to look at their data first, then returns to the
    deletion page with the code they were sent.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    deletion = issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)
    issue(restricted_session, PHONE, CORRELATION, purpose=OTP_PURPOSE)

    assert (
        verify(
            restricted_session,
            PHONE,
            deletion.code,
            CORRELATION,
            purpose=DELETION_PURPOSE,
        )
        == account
    ), (
        "the deletion code was refused because a NEWER sign-in code "
        "shadowed it, so the purpose is being checked after the row is "
        "fetched rather than in the WHERE beside `phone` [DESIGN-1]."
    )


def test_a_later_deletion_code_does_not_shadow_a_sign_in_code(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """The mirror, so the fix is symmetric rather than special-cased.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    sign_in = issue(restricted_session, PHONE, CORRELATION, purpose=OTP_PURPOSE)
    issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)

    assert (
        verify(
            restricted_session,
            PHONE,
            sign_in.code,
            CORRELATION,
            purpose=OTP_PURPOSE,
        )
        == account
    )


def test_a_consumed_deletion_code_cannot_be_replayed(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """The single-use rule carries over unchanged [NFR14.81].

    No new mechanism: the deletion path calls ``verify()`` rather than
    reimplementing it, so ``consumed_at`` is set in the same transaction
    as the check that read it.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    issued = issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)
    verify(
        restricted_session,
        PHONE,
        issued.code,
        CORRELATION,
        purpose=DELETION_PURPOSE,
    )

    with pytest.raises(ValidationError):
        verify(
            restricted_session,
            PHONE,
            issued.code,
            CORRELATION,
            purpose=DELETION_PURPOSE,
        )


def test_the_purpose_is_written_to_the_row(
    restricted_session: Session, account: uuid.UUID
) -> None:
    """``issue()`` stores the purpose it was given, not a constant.

    The filter in ``verify()`` is only as good as what ``issue()``
    wrote. A ``verify()`` correctly filtering on a column every row sets
    to ``"otp"`` would refuse every deletion and pass no test above
    except the refusals.

    :param restricted_session: The non-superuser session
    :param account: The account under test
    :return: None
    """
    issue(restricted_session, PHONE, CORRELATION, purpose=DELETION_PURPOSE)

    stored = (
        restricted_session.execute(
            sa.text("SELECT purpose FROM otp_request WHERE phone = :phone"),
            {"phone": PHONE},
        )
        .scalars()
        .all()
    )

    assert stored == [DELETION_PURPOSE]


def test_the_two_purposes_are_distinct_and_fit_the_column() -> None:
    """``otp_request.purpose`` is ``String(32)``; both values fit.

    Asserted rather than assumed, because the sibling control -- the
    ceiling scopes -- has already met a PostgreSQL refusal on exactly
    this kind of length.

    :return: None
    """
    assert OTP_PURPOSE != DELETION_PURPOSE
    for value in (OTP_PURPOSE, DELETION_PURPOSE):
        assert len(value) <= 32, value
