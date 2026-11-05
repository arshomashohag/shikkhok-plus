"""``0018``'s backfill: existing seats become a teacher's students.

Seats of one teacher sharing a student number merge into one student;
a seat with no number stays a student of its own; another teacher's seat
with the same number is that teacher's own student.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from tests.db.migration_support import insert_account, stage_at, upgrade_to_head

NUMBER = "+8801812345678"


@pytest.fixture
def staged(postgres_url: str) -> Iterator[Engine]:
    """Yield an engine on a throwaway database staged at ``0017``.

    :param postgres_url: The owner connection URL
    :return: A context manager yielding the staged engine
    """
    with stage_at(postgres_url, "0017") as engine:
        yield engine


def _owner(connection: Connection, phone: str) -> uuid.UUID:
    """Insert a teacher.

    :param connection: An open connection
    :param phone: The teacher's number
    :return: The owner id
    """
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text("INSERT INTO owner (id, account_id, created_at) VALUES (:i, :a, :n)"),
        {
            "i": owner_id,
            "a": insert_account(connection, phone),
            "n": dt.datetime.now(dt.UTC),
        },
    )
    return owner_id


def _batch(connection: Connection, owner_id: uuid.UUID, name: str) -> uuid.UUID:
    """Insert a batch.

    :param connection: An open connection
    :param owner_id: Its owner
    :param name: Its name
    :return: The batch id
    """
    batch_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO batch (id, owner_id, name, marksheet_visible, active, "
            "created_at) VALUES (:i, :o, :name, true, true, :n)"
        ),
        {"i": batch_id, "o": owner_id, "name": name, "n": dt.datetime.now(dt.UTC)},
    )
    return batch_id


def _seat(
    connection: Connection,
    batch_id: uuid.UUID,
    name: str,
    phone: str | None,
    *,
    created: dt.datetime,
) -> uuid.UUID:
    """Insert a seat at the ``0017`` shape.

    :param connection: An open connection
    :param batch_id: Its batch
    :param name: The typed name
    :param phone: The typed student number
    :param created: When it was created
    :return: The seat id
    """
    seat_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO enrollment (id, batch_id, display_name, student_phone, "
            "student_decision, guardian_decision, created_at) "
            "VALUES (:i, :b, :name, :p, 'pending', 'pending', :c)"
        ),
        {"i": seat_id, "b": batch_id, "name": name, "p": phone, "c": created},
    )
    return seat_id


def test_seats_sharing_a_number_become_one_student(staged: Engine) -> None:
    """The case the change exists for, plus its two boundaries.

    :param staged: The engine staged at ``0017``
    :return: None
    """
    early = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    late = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    with staged.begin() as connection:
        teacher = _owner(connection, "+8801700000001")
        other = _owner(connection, "+8801700000002")
        physics = _batch(connection, teacher, "Physics")
        chemistry = _batch(connection, teacher, "Chemistry")
        maths = _batch(connection, other, "Maths")
        first = _seat(connection, physics, "Rafiq", NUMBER, created=early)
        second = _seat(connection, chemistry, "Rafiq H.", NUMBER, created=late)
        nameless = _seat(connection, physics, "Nusrat", None, created=early)
        elsewhere = _seat(connection, maths, "Rafiq", NUMBER, created=early)
        orphan = _seat(connection, uuid.uuid4(), "Nobody", None, created=early)

    upgrade_to_head(staged)

    with staged.begin() as connection:
        link = dict(
            connection.execute(sa.text("SELECT id, student_id FROM enrollment")).all()
        )
        students = {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                sa.text("SELECT id, owner_id, display_name FROM student")
            ).all()
        }

    assert link[first] == link[second] == first
    # The earliest seat supplies the name.
    assert students[first] == (teacher, "Rafiq")
    assert link[nameless] == nameless
    assert link[elsewhere] == elsewhere
    assert students[elsewhere][0] == other
    # A seat whose batch is missing has no owner to give a student.
    assert link[orphan] is None
    assert len(students) == 3
