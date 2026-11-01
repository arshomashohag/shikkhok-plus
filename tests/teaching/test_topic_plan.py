"""Planning a class's topics before it starts, versus logging them after.

A topic written BEFORE the class starts is a plan: the class stays
``scheduled``. A topic written as covered marks the class ``held``. Once
the class has started a plan is refused, because from then on the only
honest write is "this is what we covered".
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from pydantic import ValidationError as SchemaError
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import QueuedSubmission, Session
from app.errors import ConflictError
from app.schemas.teaching import TopicWriteRequest
from app.teaching.submissions import write_topic
from tests.batches.conftest import TeacherFixture

SESSION_DATE = dt.date(2027, 5, 10)
BEFORE_START = dt.datetime(2027, 5, 10, 9, 59, tzinfo=dt.UTC)
AT_START = dt.datetime(2027, 5, 10, 10, 0, tzinfo=dt.UTC)


@pytest.fixture
def owned_session(owner_session: DbSession, teacher: TeacherFixture) -> uuid.UUID:
    """One scheduled session at 16:00 Bangladesh time.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :return: The session id
    """
    row = Session(
        batch_id=teacher.batch_id,
        date=SESSION_DATE,
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def _write(
    session: DbSession,
    teacher: TeacherFixture,
    session_id: uuid.UUID,
    *,
    topic: str | None,
    plan: bool,
    now: dt.datetime,
    notes: str | None = None,
    base_version: int = 0,
    mutation: uuid.UUID | None = None,
):
    """Call ``write_topic`` as the fixture teacher.

    :param session: The restricted session
    :param teacher: The teacher fixture
    :param session_id: The session written
    :param topic: The topic
    :param plan: Whether this is a plan
    :param now: The clock
    :param notes: The notes
    :param base_version: The version composed against
    :param mutation: The replay key
    :return: The write's result
    """
    return write_topic(
        session,
        lens=TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id),
        session_id=session_id,
        base_version=base_version,
        client_mutation_id=mutation or uuid.uuid4(),
        topic=topic,
        plan=plan,
        notes=notes,
        now=now,
        notes_supplied=True,
    )


def _row(owner_session: DbSession, session_id: uuid.UUID) -> Session:
    """Reload a session row fresh.

    :param owner_session: The arranging session
    :param session_id: The session
    :return: The row
    """
    owner_session.expire_all()
    return owner_session.get_one(Session, session_id)


def test_plan_before_start_keeps_class_scheduled(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    result = _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=True,
        now=BEFORE_START,
        notes="bring prisms",
    )
    row = _row(owner_session, owned_session)
    assert (row.topic, row.notes, row.status) == ("Optics", "bring prisms", "scheduled")
    assert row.topic_version == result.topic_version == 1


def test_plan_after_start_is_refused_and_writes_nothing(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    with pytest.raises(ConflictError) as raised:
        _write(
            restricted_session,
            teacher,
            owned_session,
            topic="Optics",
            plan=True,
            now=AT_START,
        )
    assert raised.value.code == "CLASS_STARTED"
    assert raised.value.message_key == "teaching.topic.class_started"
    restricted_session.rollback()
    row = _row(owner_session, owned_session)
    assert (row.topic, row.status, row.topic_version) == (None, "scheduled", 0)


def test_plan_can_be_cleared_to_none_before_start(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=True,
        now=BEFORE_START,
    )
    _write(
        restricted_session,
        teacher,
        owned_session,
        topic=None,
        plan=True,
        now=BEFORE_START,
        base_version=1,
    )
    row = _row(owner_session, owned_session)
    assert row.topic is None
    assert row.status == "scheduled"
    assert row.topic_version == 2


def test_covered_write_marks_held_and_stores_notes(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=False,
        now=AT_START,
        notes="ran long",
    )
    row = _row(owner_session, owned_session)
    assert (row.topic, row.notes, row.status) == ("Optics", "ran long", "held")


def test_notes_alone_on_a_plan_do_not_mark_held(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    _write(
        restricted_session,
        teacher,
        owned_session,
        topic=None,
        plan=True,
        now=BEFORE_START,
        notes="just a note",
    )
    row = _row(owner_session, owned_session)
    assert (row.notes, row.status) == ("just a note", "scheduled")


def test_none_topic_without_plan_is_422() -> None:
    with pytest.raises(SchemaError):
        TopicWriteRequest(
            base_topic_version=0, client_mutation_id=uuid.uuid4(), topic=None
        )
    plan = TopicWriteRequest(
        base_topic_version=0, client_mutation_id=uuid.uuid4(), topic=None, plan=True
    )
    assert plan.topic is None


def test_replayed_plan_is_idempotent(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    mutation = uuid.uuid4()
    first = _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=True,
        now=BEFORE_START,
        mutation=mutation,
    )
    second = _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=True,
        now=AT_START,
        mutation=mutation,
    )
    assert second.replayed is True
    assert second.topic_version == first.topic_version == 1
    count = owner_session.scalar(
        sa.select(sa.func.count())
        .select_from(QueuedSubmission)
        .where(QueuedSubmission.session_id == owned_session)
    )
    assert count == 1


def test_start_uses_rescheduled_date_and_time(
    restricted_session, owner_session, teacher, owned_session
) -> None:
    row = _row(owner_session, owned_session)
    row.date = dt.date(2027, 5, 12)
    row.start_time = dt.time(8, 0)
    owner_session.commit()
    _write(
        restricted_session,
        teacher,
        owned_session,
        topic="Optics",
        plan=True,
        now=AT_START,
    )
    with pytest.raises(ConflictError):
        _write(
            restricted_session,
            teacher,
            owned_session,
            topic="Optics",
            plan=True,
            now=dt.datetime(2027, 5, 12, 2, 0, tzinfo=dt.UTC),
            base_version=1,
        )
