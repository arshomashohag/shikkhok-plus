"""On staging the outbox serves the operator's own numbers and no others.

Staging is reachable from the internet through CloudFront, so an outbox
answering for any number let anyone who knew a real person's phone
number sign in as them there [C-19]. These tests pin the three halves
of the restriction: no allowlist means no outbox on staging, a number
outside the list is never recorded, and reading one back answers
exactly as for a number with no message.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import ENVIRONMENT_ENV
from app.gateway.outbox import (
    OUTBOX_FORCE_ENV,
    OUTBOX_NUMBERS_ENV,
    outbox_enabled,
    outbox_number_permitted,
    read_outbox,
    record_outbox,
)

OPERATOR = "+8801711111111"
STRANGER = "+8801722222222"


@pytest.mark.parametrize("allowlist", [None, "", " , "])
def test_staging_without_an_allowlist_has_no_outbox(
    monkeypatch: pytest.MonkeyPatch, allowlist: str | None
) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    if allowlist is None:
        monkeypatch.delenv(OUTBOX_NUMBERS_ENV, raising=False)
    else:
        monkeypatch.setenv(OUTBOX_NUMBERS_ENV, allowlist)

    assert outbox_enabled() is False


def test_staging_with_an_allowlist_has_an_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Guards the test above: a predicate that was always false on
    # staging would pass it.
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv(OUTBOX_NUMBERS_ENV, OPERATOR)

    assert outbox_enabled() is True


def test_an_unset_environment_name_permits_no_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The startup checks read an unset name as development, for the
    # suite's sake. The outbox does not: a deployed host with the name
    # missing must not hand out codes.
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")

    assert outbox_enabled() is False


def test_development_needs_no_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, "development")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.delenv(OUTBOX_NUMBERS_ENV, raising=False)

    assert outbox_enabled() is True
    assert outbox_number_permitted(STRANGER) is True


@pytest.mark.parametrize(
    ("allowlist", "phone", "expected"),
    [
        (OPERATOR, OPERATOR, True),
        (OPERATOR, STRANGER, False),
        (f"{STRANGER}, {OPERATOR}", OPERATOR, True),
        (f"{STRANGER}\n{OPERATOR}", OPERATOR, True),
        # Exact match only: a prefix of a listed number is not listed.
        (OPERATOR, OPERATOR[:-1], False),
    ],
)
def test_the_allowlist_is_an_exact_match(
    monkeypatch: pytest.MonkeyPatch, allowlist: str, phone: str, expected: bool
) -> None:
    monkeypatch.setenv(OUTBOX_NUMBERS_ENV, allowlist)

    assert outbox_number_permitted(phone) is expected


def _staging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure staging with the outbox on for the operator only.

    :param monkeypatch: The patcher
    :return: None
    """
    monkeypatch.setenv(ENVIRONMENT_ENV, "staging")
    monkeypatch.setenv(OUTBOX_FORCE_ENV, "1")
    monkeypatch.setenv(OUTBOX_NUMBERS_ENV, OPERATOR)


def test_a_number_outside_the_allowlist_is_not_recorded(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staging(monkeypatch)

    for phone in (OPERATOR, STRANGER):
        record_outbox(
            restricted_session,
            phone=phone,
            message="Your code is 123456",
            correlation_id=str(uuid.uuid4()),
        )
    restricted_session.commit()

    recorded = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT phone FROM staging_sms_outbox")
        )
    }
    assert recorded == {OPERATOR}


def test_a_number_outside_the_allowlist_reads_as_having_no_message(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arranged through the table directly, as an entry written before
    # the allowlist narrowed would be: the reader must refuse it too.
    _staging(monkeypatch)
    restricted_session.execute(
        sa.text(
            "INSERT INTO staging_sms_outbox "
            "(id, phone, message, correlation_id, recorded_at) "
            "VALUES (:id, :phone, 'Your code is 654321', :c, now())"
        ),
        {"id": uuid.uuid4(), "phone": STRANGER, "c": str(uuid.uuid4())},
    )
    restricted_session.commit()

    assert read_outbox(restricted_session, phone=STRANGER) is None
