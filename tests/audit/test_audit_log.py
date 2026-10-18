"""Append-only, closed enum, and no field a secret could land in.

**An audit log that leaks what it audits is a common and self-defeating
mistake** [BR6.2]. The structural assertion below is the one that
matters: the row carries **no free-form string field but the correlation
id**, so there is nowhere for a phone number to be added later by someone
debugging in good faith.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.db.models import Account, AuthAuditLog

CORRELATION = "test-correlation-id"


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create an account to attribute audit rows to.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(
        phone=f"+8801{uuid.uuid4().int % 10**9:09d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(record)
    owner_session.commit()
    return record.id


def test_the_row_carries_no_free_form_field_but_the_correlation_id() -> None:
    # THE STRUCTURAL ASSERTION. A `message`, `detail` or `note` column is
    # where a phone number eventually lands, added by someone debugging
    # in good faith. The absence is the mechanism.
    string_columns = {
        name
        for name, column in AuthAuditLog.__table__.columns.items()
        if isinstance(column.type, sa.String | sa.Text)
    }
    assert string_columns == {"event", "correlation_id"}


def test_there_is_no_phone_or_token_column() -> None:
    columns = set(AuthAuditLog.__table__.columns.keys())
    assert not columns & {
        "phone",
        "number",
        "otp",
        "code",
        "token",
        "message",
        "detail",
        "note",
        "name",
    }


def test_the_event_vocabulary_is_closed() -> None:
    # An open vocabulary is how a free-form value re-enters a log
    # specified not to have one.
    assert {event.value for event in AuthEvent} == {
        "OTP_ISSUED",
        "VERIFY_FAILED",
        "VERIFY_SUCCEEDED",
        "REFRESH_ROTATED",
        "REFRESH_REUSE_DETECTED",
    }


def test_the_account_id_is_nullable() -> None:
    # An OTP issued for an unknown number has no account, and recording
    # a placeholder would reintroduce the existence oracle [BR2.7].
    assert AuthAuditLog.__table__.columns["account_id"].nullable is True


def test_every_event_type_round_trips(
    restricted_session: Session, account: uuid.UUID
) -> None:
    for event in AuthEvent:
        write_audit(
            restricted_session,
            account_id=account,
            event=event,
            correlation_id=CORRELATION,
        )
    restricted_session.commit()

    stored = {
        row[0]
        for row in restricted_session.execute(
            sa.text("SELECT event FROM auth_audit_log")
        )
    }
    assert stored == {event.value for event in AuthEvent}


def test_a_correlation_id_appears_on_every_row(
    restricted_session: Session, account: uuid.UUID
) -> None:
    write_audit(
        restricted_session,
        account_id=account,
        event=AuthEvent.OTP_ISSUED,
        correlation_id=CORRELATION,
    )
    restricted_session.commit()

    missing = restricted_session.execute(
        sa.text(
            "SELECT count(*) FROM auth_audit_log "
            "WHERE correlation_id IS NULL OR correlation_id = ''"
        )
    ).scalar_one()
    assert missing == 0


def test_an_unknown_number_writes_a_row_with_no_account(
    restricted_session: Session,
) -> None:
    write_audit(
        restricted_session,
        account_id=None,
        event=AuthEvent.OTP_ISSUED,
        correlation_id=CORRELATION,
    )
    restricted_session.commit()

    stored = restricted_session.execute(
        sa.text("SELECT account_id FROM auth_audit_log")
    ).scalar_one()
    assert stored is None


def test_the_audit_write_fails_open_rather_than_raising(
    restricted_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The log must NOT fail the authentication it was recording. A
    # raise here would mean a database hiccup locks everyone out.
    def explode(*args: object, **kwargs: object) -> None:
        raise sa.exc.OperationalError("INSERT", {}, Exception("down"))

    monkeypatch.setattr(restricted_session, "execute", explode)

    write_audit(
        restricted_session,
        account_id=None,
        event=AuthEvent.OTP_ISSUED,
        correlation_id=CORRELATION,
    )


def test_a_failed_audit_write_alerts_the_operator(
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Failing open makes the log SUPPRESSIBLE by causing write failures,
    # which would be a real weakness if it were silent. So: silent to
    # the user, LOUD to the operator. This alert is the whole resolution
    # of that tension, and an audit log that can be disabled without
    # anyone noticing is worse than one that fails loudly.
    def explode(*args: object, **kwargs: object) -> None:
        raise sa.exc.OperationalError("INSERT", {}, Exception("down"))

    monkeypatch.setattr(restricted_session, "execute", explode)

    with caplog.at_level(logging.CRITICAL):
        write_audit(
            restricted_session,
            account_id=None,
            event=AuthEvent.OTP_ISSUED,
            correlation_id=CORRELATION,
        )

    assert any(record.levelno >= logging.CRITICAL for record in caplog.records), (
        "a failed audit write was silent: the log is now suppressible"
    )


def test_the_audit_log_is_append_only_in_practice(
    restricted_session: Session, account: uuid.UUID
) -> None:
    # Asserted over this Unit's own source: there is no UPDATE and no
    # DELETE against the table anywhere in the application.
    import pathlib
    import re

    app_root = pathlib.Path(__file__).resolve().parents[2] / "app"
    pattern = re.compile(r"\b(UPDATE|DELETE\s+FROM)\s+auth_audit_log\b", re.IGNORECASE)
    offenders = [
        path.name for path in app_root.rglob("*.py") if pattern.search(path.read_text())
    ]
    assert offenders == []
