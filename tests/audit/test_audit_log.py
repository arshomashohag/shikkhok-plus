"""Append-only, closed enum, and no field a secret could land in.

**An audit log that leaks what it audits is a common and self-defeating
mistake** [BR6.2]. The structural assertion below is the one that
matters: the row carries **no free-form string field but the correlation
id**, so there is nowhere for a phone number to be added later by someone
debugging in good faith.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.audit.log import AuthEvent, write_audit
from app.db.models import Account, AuthAuditLog
from app.db.roles import APP_ROLE


@contextlib.contextmanager
def _audit_insert_revoked(engine: Engine) -> Iterator[None]:
    """Remove the restricted role's INSERT on the audit table.

    A context manager rather than an inline try/finally, so the grant
    comes back on ANY exit path. A leaked revoke would break every
    later test in the session with a permission error far from its
    cause -- and the privacy and auth suites would then fail for a
    reason that has nothing to do with what they assert.

    :param engine: An owner-privileged engine
    :return: A context manager holding the revoke
    """
    with engine.begin() as connection:
        connection.execute(sa.text(f"REVOKE INSERT ON auth_audit_log FROM {APP_ROLE}"))
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f"GRANT INSERT ON auth_audit_log TO {APP_ROLE}"))


CORRELATION = "test-correlation-id"


@pytest.fixture
def account(owner_session: Session) -> uuid.UUID:
    """Create an account to attribute audit rows to.

    :param owner_session: A session able to arrange fixture data
    :return: The account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
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
        # D1's two, added as NAMED MEMBERS rather than as one event
        # plus a `detail` column -- which is the free-form string this
        # log is specified not to have, arriving through the one door
        # still open [NFR12.7, NFR12.9, NFR12.10].
        "ACCOUNT_CREATED",
        "SIGNUP_CEILING_BREACHED",
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


def test_a_failed_audit_write_does_not_destroy_the_callers_work(
    restricted_session: Session, owner_engine: Engine
) -> None:
    # THE REGRESSION. Catching the exception is NOT enough, and the
    # first version of write_audit got this wrong.
    #
    # PostgreSQL aborts the whole transaction on a failed statement, so
    # a swallowed error leaves the caller holding an aborted
    # transaction whose commit() issues a ROLLBACK and RETURNS
    # NORMALLY. Measured: otp.issue returned a code, the SMS went out,
    # and the OTP row was silently lost -- a code that can never
    # verify, after consuming a ceiling slot.
    #
    # Fail-open means the authentication SURVIVES its unrecorded audit,
    # so the assertion is on the caller's row, not on the absence of a
    # raise.
    phone = f"+88017{uuid.uuid4().int % 10**8:08d}"
    restricted_session.execute(
        sa.text(
            "INSERT INTO otp_request "
            "(id, phone, otp_hash, purpose, issued_at, expires_at) "
            "VALUES (:id, :phone, :hash, 'otp', :now, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "phone": phone,
            "hash": "x" * 64,
            "now": dt.datetime.now(tz=dt.UTC),
        },
    )

    # Break the audit write the way a real failure would: the role
    # loses the privilege the INSERT needs. The revoke is a FIXTURE
    # rather than an inline try/finally, so the grant is restored even
    # if this test is interrupted between the revoke and the try --
    # otherwise a leaked revoke breaks every later test in the session
    # with a confusing permission error far from its cause.
    with _audit_insert_revoked(owner_engine):
        write_audit(
            restricted_session,
            account_id=None,
            event=AuthEvent.OTP_ISSUED,
            correlation_id=CORRELATION,
        )
        restricted_session.commit()

    survived = restricted_session.execute(
        sa.text("SELECT count(*) FROM otp_request WHERE phone = :phone"),
        {"phone": phone},
    ).scalar_one()
    assert survived == 1, (
        "the caller's OTP row was lost when the audit write failed. The "
        "user would receive a code that can never verify, having "
        "already consumed a ceiling slot."
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


def test_family_invalidation_survives_a_failed_audit_write(
    restricted_session: Session, owner_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The security-critical half of fail-open, and the one the savepoint
    # fix has to hold on: reuse detection invalidates the whole token
    # family and THEN writes REFRESH_REUSE_DETECTED. If the audit
    # failure took the invalidation down with it, a stolen token would
    # stay live precisely when the mechanism exists to kill it.
    from app.auth.hashing import OTP_HMAC_KEY_ENV
    from app.auth.tokens import (
        JWT_ACTIVE_KID_ENV,
        JWT_KEYS_ENV,
        issue_pair,
        rotate,
    )
    from app.errors import AuthorizationError

    monkeypatch.setenv(OTP_HMAC_KEY_ENV, "test-only-hmac-key")
    monkeypatch.setenv(JWT_KEYS_ENV, "k1:a-test-secret-padded-to-32-bytes")
    monkeypatch.setenv(JWT_ACTIVE_KID_ENV, "k1")

    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    with owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO account (id, phone, created_at) VALUES (:id, :phone, :now)"
            ),
            {
                "id": record.id or uuid.uuid4(),
                "phone": record.phone,
                "now": record.created_at,
            },
        )
        account_id = connection.execute(
            sa.text("SELECT id FROM account WHERE phone = :phone"),
            {"phone": record.phone},
        ).scalar_one()

    first = issue_pair(restricted_session, account_id, CORRELATION)
    restricted_session.commit()
    second = rotate(restricted_session, first.refresh_token, CORRELATION)

    with _audit_insert_revoked(owner_engine):
        with pytest.raises(AuthorizationError):
            rotate(restricted_session, first.refresh_token, CORRELATION)
        restricted_session.commit()

    # The whole family must be dead even though its audit row was lost.
    with pytest.raises(AuthorizationError):
        rotate(restricted_session, second.refresh_token, CORRELATION)
