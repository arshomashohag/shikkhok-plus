"""A planned topic is not a logged topic, on any read.

Written before the fix. One ``topic`` column holds the plan before a
class starts and what was covered after it [spec: Topics and notes], so
``topic is not None`` no longer means "a topic was logged": a plan
written for a class nobody then recorded would read as covered. The
decision is ``status == "held" and topic is not None`` everywhere, and
the family lists, which show what was COVERED, carry no plan at all.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session as DbSession

from app.analytics.today import today_view
from app.authz.lenses import StudentLens, TeacherLens
from app.db.models import Session
from app.local_time import DHAKA
from app.teaching.announcements import family_batch_view
from app.teaching.sessions import list_sessions
from app.teaching.submissions import write_topic
from tests.batches.conftest import TeacherFixture, enroll

NOW = dt.datetime(2027, 5, 10, 12, 0, tzinfo=DHAKA)
TODAY = NOW.date()


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _class(
    owner_session: DbSession,
    teacher: TeacherFixture,
    day: dt.date,
    *,
    status: str = "scheduled",
    topic: str | None = None,
) -> uuid.UUID:
    """Add one class at 16:00 with a stored topic.

    :param owner_session: An arranging session
    :param teacher: The owner
    :param day: Its date
    :param status: Its status
    :param topic: Its stored topic
    :return: The session id
    """
    row = Session(
        batch_id=teacher.batch_id,
        date=day,
        start_time=dt.time(16, 0),
        status=status,
        origin="recurrence",
        topic=topic,
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


@pytest.fixture
def planned_today(
    restricted_session: DbSession,
    owner_session: DbSession,
    teacher: TeacherFixture,
) -> uuid.UUID:
    """Plan a class today at 16:00, writing the plan at noon.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: The session id
    """
    sid = _class(owner_session, teacher, TODAY)
    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=sid,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="Optics",
        plan=True,
        notes=None,
        notes_supplied=False,
        now=NOW,
    )
    restricted_session.commit()
    return sid


def test_a_plan_is_not_logged_on_the_sessions_list(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    planned_today: uuid.UUID,
) -> None:
    """The batch's session list says a planned class has no topic logged.

    :param restricted_session: The restricted session
    :param teacher: The owner
    :param planned_today: The planned class
    :return: None
    """
    row = next(
        entry
        for entry in list_sessions(
            restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
        )
        if entry.session_id == planned_today
    )

    assert (row.status, row.topic) == ("scheduled", "Optics")
    assert row.topic_logged is False


def test_a_held_class_with_a_topic_is_logged_on_the_sessions_list(
    restricted_session: DbSession,
    owner_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    """The decision still says logged for a held class, blank included.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :return: None
    """
    held = _class(owner_session, teacher, TODAY, status="held", topic="")

    row = next(
        entry
        for entry in list_sessions(
            restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
        )
        if entry.session_id == held
    )

    assert row.topic_logged is True


def test_a_plan_is_not_logged_on_today(
    restricted_session: DbSession,
    teacher: TeacherFixture,
    planned_today: uuid.UUID,
) -> None:
    """Today's class list says a planned class has no topic logged.

    :param restricted_session: The restricted session
    :param teacher: The owner
    :param planned_today: The planned class
    :return: None
    """
    view = today_view(restricted_session, lens=_lens(teacher), now=NOW)
    row = next(c for c in view.classes if c.session_id == planned_today)

    assert row.topic_logged is False


def test_a_family_sees_no_plan_on_an_unrecorded_past_class(
    restricted_session: DbSession,
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A past class planned and never recorded shows nothing as covered.

    :param restricted_session: The restricted session
    :param owner_session: An arranging session
    :param teacher: The owner
    :param account_factory: Makes accounts
    :return: None
    """
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
    )
    planned = _class(owner_session, teacher, TODAY - dt.timedelta(days=2), topic="Plan")
    held = _class(
        owner_session,
        teacher,
        TODAY - dt.timedelta(days=1),
        status="held",
        topic="Refraction",
    )

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )
    rows = {entry.session_id: entry for entry in view.past_sessions}

    assert (rows[planned].topic, rows[planned].topic_logged) == (None, False)
    assert (rows[held].topic, rows[held].topic_logged) == ("Refraction", True)
