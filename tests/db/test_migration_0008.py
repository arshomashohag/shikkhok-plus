"""``0008`` rewrites stored numbers canonically, and refuses to merge accounts.

Staged at ``0007`` with numbers written the way they actually were --
exactly as typed -- because what happens to EXISTING rows is the whole
point. An empty database would pass every assertion here vacuously.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from tests.db.migration_support import insert_account, stage_at, upgrade_to_head


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0007``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0007") as engine:
        yield engine


def _insert_seat(connection: Connection, *, guardian_phone: str | None) -> uuid.UUID:
    """Insert one seat at the ``0007`` shape.

    :param connection: An open connection to the staged database
    :param guardian_phone: The teacher-typed guardian number, as typed
    :return: The new enrollment's id
    """
    enrollment_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO enrollment (id, batch_id, display_name, guardian_phone, "
            "student_decision, guardian_decision, created_at) "
            "VALUES (:id, :batch, 'Rahim', :phone, 'pending', 'pending', :now)"
        ),
        {
            "id": enrollment_id,
            "batch": uuid.uuid4(),
            "phone": guardian_phone,
            "now": dt.datetime.now(dt.UTC),
        },
    )
    return enrollment_id


def _scalar(engine: Engine, sql: str, **params: object) -> object:
    """Read one value after the upgrade.

    :param engine: The staged engine
    :param sql: A query returning one value
    :param params: Its bind parameters
    :return: The value
    """
    with engine.begin() as connection:
        return connection.execute(sa.text(sql), params).scalar_one()


def test_an_account_typed_locally_becomes_canonical(staged: Engine) -> None:
    """The account can still sign in once requests arrive canonical.

    Left as ``01799-000801``, it would match nothing after this change:
    its owner's typed number now arrives as ``+8801799000801``.

    :param staged: The engine staged at ``0007``
    :return: None
    """
    with staged.begin() as connection:
        account_id = insert_account(connection, "01799-000801")

    upgrade_to_head(staged)

    stored = _scalar(staged, "SELECT phone FROM account WHERE id = :id", id=account_id)
    assert stored == "+8801799000801"


def test_a_guardian_number_becomes_canonical(staged: Engine) -> None:
    """A teacher-typed guardian number can now match the guardian's account.

    :param staged: The engine staged at ``0007``
    :return: None
    """
    with staged.begin() as connection:
        seat = _insert_seat(connection, guardian_phone="01811 222 333")

    upgrade_to_head(staged)

    stored = _scalar(
        staged, "SELECT guardian_phone FROM enrollment WHERE id = :id", id=seat
    )
    assert stored == "+8801811222333"


def test_a_number_that_will_not_convert_is_left_alone(staged: Engine) -> None:
    """A seed value or a typo is not guessed at.

    :param staged: The engine staged at ``0007``
    :return: None
    """
    with staged.begin() as connection:
        account_id = insert_account(connection, "not-a-number-1")

    upgrade_to_head(staged)

    stored = _scalar(staged, "SELECT phone FROM account WHERE id = :id", id=account_id)
    assert stored == "not-a-number-1"


def test_two_accounts_for_one_phone_stop_the_migration(staged: Engine) -> None:
    """The duplicate-account bug is surfaced, never silently merged.

    Merging would mean choosing whose batches and history survive, which
    is a person's decision. The error names both accounts.

    :param staged: The engine staged at ``0007``
    :return: None
    """
    with staged.begin() as connection:
        first = insert_account(connection, "01799000802")
        second = insert_account(connection, "+8801799000802")

    with pytest.raises(Exception, match="same phone") as caught:
        upgrade_to_head(staged)

    assert str(first) in str(caught.value)
    assert str(second) in str(caught.value)


def test_a_seat_can_now_hold_its_students_number(staged: Engine) -> None:
    """``student_phone`` exists, nullable, so linking has somewhere to look.

    :param staged: The engine staged at ``0007``
    :return: None
    """
    upgrade_to_head(staged)

    nullable = _scalar(
        staged,
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'enrollment' AND column_name = 'student_phone'",
    )
    assert nullable == "YES"
