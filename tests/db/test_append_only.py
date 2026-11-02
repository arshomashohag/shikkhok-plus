"""The ledger and the sign-in audit log are append-only IN THE DATABASE.

**Before ``0015`` both were append-only by rule and review only** [PA-SEC-3]:
the application role held full ``UPDATE`` and ``DELETE`` on each, so a
leaked application credential could rewrite what a family paid or erase
the trail that answers "was this child's data accessed". These tests
connect as that role and assert what it can no longer do, and -- the
half that keeps the control honest -- what the application still needs
and still can.

Every assertion of a refusal runs as ``shikkhok_app``. An assertion made
as the owner would pass whatever the grants said.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.fees.ledger_writer import append_entry, supersede
from app.governance.commands import WINDOWS, purge_table
from app.money import Money
from tests.batches.conftest import enroll, make_teacher


def _seat(owner_session: Session) -> uuid.UUID:
    """Create one seat for ledger rows to hang from.

    :param owner_session: An arranging session
    :return: The enrollment id
    """
    teacher = make_teacher(owner_session)
    return enroll(owner_session, batch_id=teacher.batch_id, display_name="Rahim")


def _refused(session: Session, statement: str, params: dict[str, object]) -> str:
    """Run a statement that must be refused, and return the refusal.

    :param session: The restricted session
    :param statement: The SQL to attempt
    :param params: Its bind parameters
    :return: The database's error message
    """
    with pytest.raises(sa.exc.ProgrammingError) as refusal:
        session.execute(sa.text(statement), params)
    session.rollback()
    return str(refusal.value.orig)


def _audit_row(owner_session: Session, *, age: dt.timedelta) -> uuid.UUID:
    """Plant one audit row of a given age, as the owner.

    :param owner_session: An arranging session
    :param age: How long ago the event occurred, by the real clock
    :return: The row id
    """
    row_id = uuid.uuid4()
    owner_session.execute(
        sa.text(
            "INSERT INTO auth_audit_log (id, account_id, event, occurred_at, "
            "correlation_id) VALUES (:id, NULL, 'otp_issued', :at, :cid)"
        ),
        {"id": row_id, "at": dt.datetime.now(tz=dt.UTC) - age, "cid": row_id.hex},
    )
    owner_session.commit()
    return row_id


def _exists(session: Session, row_id: uuid.UUID) -> bool:
    """Say whether an audit row is still there.

    :param session: A reading session
    :param row_id: The row
    :return: True when present
    """
    return bool(
        session.execute(
            sa.text("SELECT count(*) FROM auth_audit_log WHERE id = :id"),
            {"id": row_id},
        ).scalar_one()
    )


def test_the_application_cannot_rewrite_a_ledger_amount(
    owner_session: Session, restricted_session: Session
) -> None:
    """An entry's amount is fixed once written, for the application role.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    seat = _seat(owner_session)
    entry = append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    restricted_session.commit()

    message = _refused(
        restricted_session,
        "UPDATE ledger_entry SET amount = 1.00 WHERE id = :id",
        {"id": entry.id},
    )

    assert "permission denied" in message
    stored = restricted_session.execute(
        sa.text("SELECT amount FROM ledger_entry WHERE id = :id"), {"id": entry.id}
    ).scalar_one()
    assert Money(stored) == Money("1500.00")


@pytest.mark.parametrize("column", ["kind", "period", "enrollment_id", "created_at"])
def test_no_other_ledger_column_is_writable(
    owner_session: Session, restricted_session: Session, column: str
) -> None:
    """Only ``superseded_by_id`` came back; every other column stays shut.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param column: A column the application never updates
    :return: None
    """
    seat = _seat(owner_session)
    entry = append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    restricted_session.commit()

    message = _refused(
        restricted_session,
        f"UPDATE ledger_entry SET {column} = {column} WHERE id = :id",  # noqa: S608  parametrized literal
        {"id": entry.id},
    )

    assert "permission denied" in message


def test_the_application_cannot_delete_a_ledger_entry(
    owner_session: Session, restricted_session: Session
) -> None:
    """No application path deletes a ledger row, so the role cannot.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    seat = _seat(owner_session)
    entry = append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    restricted_session.commit()

    message = _refused(
        restricted_session, "DELETE FROM ledger_entry WHERE id = :id", {"id": entry.id}
    )

    assert "permission denied" in message


def test_supersession_still_works_as_the_application(
    owner_session: Session, restricted_session: Session
) -> None:
    """The one post-insert write the ledger takes is still permitted.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    seat = _seat(owner_session)
    original = append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="credit_grant",
        amount=Money("1500.00"),
    )
    # The mirror kind verification writes to withdraw a grant; amounts
    # are never negative, the kind carries the direction.
    compensation = append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="credit_apply",
        amount=Money("1500.00"),
    )
    supersede(restricted_session, original=original, compensation=compensation)
    restricted_session.commit()

    stored = restricted_session.execute(
        sa.text("SELECT superseded_by_id FROM ledger_entry WHERE id = :id"),
        {"id": original.id},
    ).scalar_one()
    assert stored == compensation.id


def test_deleting_a_seat_still_cascades_through_the_ledger(
    owner_session: Session, restricted_session: Session
) -> None:
    """A referential action runs as the owner, so the revoke spares it.

    The account and batch deletion paths remove seats, and a seat's
    entries go with it through ``ON DELETE CASCADE``. Asserted rather
    than reasoned, because if the action ran as the deleting role the
    revoke would have broken account deletion.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    seat = _seat(owner_session)
    append_entry(
        restricted_session,
        enrollment_id=seat,
        period="2026-10",
        kind="charge",
        amount=Money("1500.00"),
    )
    restricted_session.commit()

    restricted_session.execute(
        sa.text("DELETE FROM enrollment WHERE id = :id"), {"id": seat}
    )
    restricted_session.commit()

    remaining = restricted_session.execute(
        sa.text("SELECT count(*) FROM ledger_entry WHERE enrollment_id = :id"),
        {"id": seat},
    ).scalar_one()
    assert remaining == 0


@pytest.mark.parametrize(
    "assignment",
    ["event = 'verify_failed'", "account_id = NULL", "occurred_at = now()"],
)
def test_the_application_cannot_update_an_audit_row(
    owner_session: Session, restricted_session: Session, assignment: str
) -> None:
    """No column of the audit log is writable by the application.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :param assignment: The rewrite attempted
    :return: None
    """
    row_id = _audit_row(owner_session, age=dt.timedelta(days=400))

    message = _refused(
        restricted_session,
        f"UPDATE auth_audit_log SET {assignment} WHERE id = :id",  # noqa: S608  parametrized literal
        {"id": row_id},
    )

    assert "permission denied" in message


def test_the_application_cannot_delete_an_audit_row_inside_retention(
    owner_session: Session, restricted_session: Session
) -> None:
    """A recent sign-in record survives a delete by the application role.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    row_id = _audit_row(owner_session, age=dt.timedelta(days=1))

    message = _refused(
        restricted_session, "DELETE FROM auth_audit_log WHERE id = :id", {"id": row_id}
    )

    assert "retention window" in message
    assert _exists(restricted_session, row_id)


def test_a_bulk_delete_takes_nothing_when_any_row_is_protected(
    owner_session: Session, restricted_session: Session
) -> None:
    """A wipe attempt fails whole; it does not delete the old rows it reached.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    old = _audit_row(owner_session, age=dt.timedelta(days=400))
    recent = _audit_row(owner_session, age=dt.timedelta(hours=1))

    _refused(restricted_session, "DELETE FROM auth_audit_log", {})

    assert _exists(restricted_session, old)
    assert _exists(restricted_session, recent)


def test_the_retention_purge_still_runs_as_the_application(
    owner_session: Session, restricted_session: Session
) -> None:
    """At the real clock, the purge deletes what expired and keeps the rest.

    **This is the coupling between the trigger's floor and the purge's
    window.** If the window were ever shortened below the floor, the
    purge's first expired-but-protected row would raise here, rather
    than in the scheduled job against production.

    :param owner_session: An arranging session
    :param restricted_session: The application's role
    :return: None
    """
    window = WINDOWS["auth_audit_log"]
    expired = _audit_row(owner_session, age=window.keep_for + dt.timedelta(hours=1))
    fresh = _audit_row(owner_session, age=window.keep_for - dt.timedelta(days=2))

    deleted, _ = purge_table(restricted_session, window, now=dt.datetime.now(tz=dt.UTC))

    assert deleted == 1
    assert not _exists(restricted_session, expired)
    assert _exists(restricted_session, fresh)
