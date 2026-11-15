"""What account deletion does to the hub's listing, report and moderation rows."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.governance.deletion import delete_account
from tests.batches.conftest import make_teacher


def _phone(session: Session, account_id: uuid.UUID) -> str:
    """Read an account's number.

    :param session: A session
    :param account_id: The account
    :return: Its phone number
    """
    return str(
        session.execute(
            sa.text("SELECT phone FROM account WHERE id = :a"), {"a": account_id}
        ).scalar_one()
    )


def _count(session: Session, table: str, column: str, value: uuid.UUID) -> int:
    """Count a table's rows for one key.

    :param session: A session
    :param table: The table
    :param column: The column
    :param value: The key
    :return: The row count
    """
    return int(
        session.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {column} = :v"),  # noqa: S608
            {"v": value},
        ).scalar_one()
    )


def test_solo_owner_deletion_removes_listing_centre_survives_manager(
    owner_session: Session,
) -> None:
    """A solo owner's listings go; a centre's listing outlives a manager.

    :param owner_session: An arranging session
    :return: None
    """
    solo = make_teacher(owner_session)
    manager = make_teacher(owner_session)
    centre = uuid.uuid4()
    owner_session.execute(
        sa.text(
            "INSERT INTO owner (id, account_id, created_at, kind, name) "
            "VALUES (:id, NULL, now(), 'organisation', 'Udoy Coaching')"
        ),
        {"id": centre},
    )
    owner_session.execute(
        sa.text(
            "INSERT INTO owner_member (id, owner_id, account_id, invited_phone, "
            "display_name, role, decision, created_at) VALUES "
            "(gen_random_uuid(), :o, :a, '+8801700000001', 'Manager', 'manager', "
            "'accepted', now())"
        ),
        {"o": centre, "a": manager.account_id},
    )
    for owner_id in (solo.owner_id, centre):
        owner_session.execute(
            sa.text(
                "INSERT INTO owner_listing (owner_id, public_name) VALUES (:o, 'N')"
            ),
            {"o": owner_id},
        )
    owner_session.execute(
        sa.text(
            "INSERT INTO batch_listing (batch_id, owner_id, show_fee, show_schedule) "
            "VALUES (:b, :o, false, false)"
        ),
        {"b": solo.batch_id, "o": solo.owner_id},
    )
    owner_session.commit()

    delete_account(owner_session, _phone(owner_session, solo.account_id))
    owner_session.expire_all()
    assert _count(owner_session, "owner_listing", "owner_id", solo.owner_id) == 0
    assert _count(owner_session, "batch_listing", "owner_id", solo.owner_id) == 0
    assert _count(owner_session, "owner", "id", solo.owner_id) == 1

    delete_account(owner_session, _phone(owner_session, manager.account_id))
    owner_session.expire_all()
    assert _count(owner_session, "owner_listing", "owner_id", centre) == 1


def test_reporter_deletion_removes_their_reports(owner_session: Session) -> None:
    """A reporter's deletion takes their reports and nobody else's.

    :param owner_session: An arranging session
    :return: None
    """
    one = make_teacher(owner_session)
    two = make_teacher(owner_session)
    target = uuid.uuid4()
    for reporter in (one, two):
        owner_session.execute(
            sa.text(
                "INSERT INTO hub_report (id, target_kind, target_id, "
                "reporter_account_id, reason) VALUES (gen_random_uuid(), "
                "'listing', :t, :a, 'spam')"
            ),
            {"t": target, "a": reporter.account_id},
        )
    owner_session.commit()

    delete_account(owner_session, _phone(owner_session, one.account_id))
    owner_session.expire_all()
    assert _count(owner_session, "hub_report", "target_id", target) == 1
    assert (
        _count(owner_session, "hub_report", "reporter_account_id", two.account_id) == 1
    )
