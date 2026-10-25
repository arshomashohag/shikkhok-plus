"""Announcements and the family batch reads [BR7.1, BR7.2, BR7.3].

**Four parts, and the fourth is the one an implementation adds by
habit**: assert the schema has NO expiry column and the unit ships no
scheduled job touching announcements. A silently expiring announcement
is a message the teacher believes was delivered.

Written test-after, from the acceptance criteria rather than from the
implementation -- the predicate does not hold here, because there is
no money and no authorization answer knowable in advance that is not
already covered by the lens-scoped read layer's own tests.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Session
from app.errors import AuthorizationError
from app.teaching.announcements import (
    delete_announcement,
    edit_announcement,
    family_batch_view,
    list_announcements,
    post_announcement,
)
from app.teaching.submissions import SeatMark, submit_roster, write_topic
from tests.batches.conftest import TeacherFixture, enroll, make_teacher

TODAY = dt.date(2027, 4, 15)


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the fixture teacher's lens.

    :param teacher: The teacher fixture
    :return: The lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_an_announcement_reaches_every_accepted_family_member(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    post_announcement(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        body="Bring your protractors",
    )

    as_student = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )
    as_guardian = family_batch_view(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=seat),
        enrollment_id=seat,
        today=TODAY,
    )

    assert [row.body for row in as_student.announcements] == ["Bring your protractors"]
    assert [row.body for row in as_guardian.announcements] == ["Bring your protractors"]


def test_an_edited_announcement_shows_as_edited(
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    posted = post_announcement(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        body="First",
    )
    assert posted.edited is False

    edited = edit_announcement(
        restricted_session,
        lens=_lens(teacher),
        announcement_id=posted.announcement_id,
        body="Second",
    )

    assert edited.edited is True
    assert edited.body == "Second"


def test_a_deleted_announcement_disappears_but_its_row_survives(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )
    posted = post_announcement(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        body="Cancelled, sorry",
    )

    delete_announcement(
        restricted_session,
        lens=_lens(teacher),
        announcement_id=posted.announcement_id,
    )

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )
    assert view.announcements == []
    assert (
        list_announcements(
            restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
        )
        == []
    )

    # SOFT-deleted: the row survives, which is what the governance
    # basis and FR9.2's history both require.
    surviving = restricted_session.execute(
        sa.text("SELECT deleted_at FROM announcement WHERE id = :id"),
        {"id": posted.announcement_id},
    ).scalar_one()
    assert surviving is not None


def test_the_announcement_table_has_no_expiry_column(
    restricted_session: DbSession,
) -> None:
    # **The part an implementation adds by habit** [AC3.3.4]. Stated
    # as an absence because the obvious implementation of
    # "announcements" adds an expiry.
    columns = {
        row[0]
        for row in restricted_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'announcement'"
            )
        )
    }

    assert columns == {
        "id",
        "batch_id",
        "body",
        "created_at",
        "edited_at",
        "deleted_at",
        "posted_by_account_id",
    }
    assert not any(
        "expir" in name or "valid_until" in name or name == "ttl" for name in columns
    )


def test_this_unit_ships_no_scheduled_job_touching_announcements() -> None:
    # The other half of the same absence: no column AND no job. A
    # grep over the unit's own command modules, which are the only
    # places a scheduled job can live.
    root = pathlib.Path(__file__).resolve().parents[2]
    for module in (root / "app" / "teaching" / "commands.py",):
        text = module.read_text()
        assert "announcement" not in text.lower(), (
            f"{module} mentions announcements: no job may remove one "
            "on the passage of time [AC3.3.4]"
        )


def test_another_teacher_cannot_read_or_post(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
) -> None:
    other = make_teacher(owner_session, name="Chemistry")
    foreign = TeacherLens(account_id=other.account_id, owner_id=other.owner_id)

    with pytest.raises(AuthorizationError):
        list_announcements(restricted_session, lens=foreign, batch_id=teacher.batch_id)
    with pytest.raises(AuthorizationError):
        post_announcement(
            restricted_session,
            lens=foreign,
            batch_id=teacher.batch_id,
            body="Not mine",
        )


def test_the_family_view_carries_a_server_timestamp(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # BR7.3. A client cannot state an age the server never sent; it
    # would have to use the device clock, which is the very thing
    # excluded from decisions.
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )

    assert view.served_at.tzinfo is not None
    assert view.served_at <= dt.datetime.now(tz=dt.UTC)


def test_the_family_view_shows_the_next_class_and_past_topics(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )

    past = Session(
        batch_id=teacher.batch_id,
        date=TODAY - dt.timedelta(days=2),
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    upcoming = Session(
        batch_id=teacher.batch_id,
        date=TODAY + dt.timedelta(days=3),
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add_all([past, upcoming])
    owner_session.commit()

    write_topic(
        restricted_session,
        lens=_lens(teacher),
        session_id=past.id,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        topic="Refraction",
    )
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=past.id,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[SeatMark(enrollment_id=seat, present=False)],
    )

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )

    assert view.next_session_date == TODAY + dt.timedelta(days=3)
    assert len(view.past_sessions) == 1
    assert view.past_sessions[0].topic == "Refraction"
    assert view.past_sessions[0].topic_logged is True
    assert view.past_sessions[0].present is False


def test_a_guardian_sees_their_own_childs_attendance_and_no_other(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    child = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    other_child = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Someone else",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    past = Session(
        batch_id=teacher.batch_id,
        date=TODAY - dt.timedelta(days=1),
        start_time=dt.time(16, 0),
        status="scheduled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(past)
    owner_session.commit()

    # The child was present; the other child was absent. A view that
    # leaked the other seat's row would show the wrong value.
    submit_roster(
        restricted_session,
        lens=_lens(teacher),
        session_id=past.id,
        base_version=0,
        client_mutation_id=uuid.uuid4(),
        seats=[
            SeatMark(enrollment_id=child, present=True),
            SeatMark(enrollment_id=other_child, present=False),
        ],
    )

    view = family_batch_view(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=child),
        enrollment_id=child,
        today=TODAY,
    )

    assert len(view.past_sessions) == 1
    assert view.past_sessions[0].present is True


def test_a_guardian_requesting_a_non_child_seat_is_refused_identically(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    guardian = account_factory()
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="My child",
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    stranger = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Someone else",
        student_account_id=account_factory(),
        student_decision="accepted",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError) as real_id:
        family_batch_view(
            restricted_session,
            lens=GuardianLens(account_id=guardian),
            enrollment_id=stranger,
            today=TODAY,
        )
    with pytest.raises(AuthorizationError) as invented:
        family_batch_view(
            restricted_session,
            lens=GuardianLens(account_id=guardian),
            enrollment_id=uuid.uuid4(),
            today=TODAY,
        )

    assert (
        real_id.value.code,
        real_id.value.message_key,
        real_id.value.status,
        real_id.value.details,
    ) == (
        invented.value.code,
        invented.value.message_key,
        invented.value.status,
        invented.value.details,
    )


def test_a_pending_student_reads_nothing(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    # BR5.2: the student branch requires student_decision =
    # 'accepted'. A pending seat reaches nothing.
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Not yet",
        student_account_id=student,
        student_decision="pending",
        guardian_decision="pending",
    )

    with pytest.raises(AuthorizationError):
        family_batch_view(
            restricted_session,
            lens=StudentLens(account_id=student),
            enrollment_id=seat,
            today=TODAY,
        )


def test_a_cancelled_session_is_not_in_the_family_view(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    student = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=student,
        student_decision="accepted",
        guardian_decision="pending",
    )
    cancelled = Session(
        batch_id=teacher.batch_id,
        date=TODAY - dt.timedelta(days=1),
        start_time=dt.time(16, 0),
        status="cancelled",
        origin="recurrence",
        attendance_version=0,
        topic_version=0,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(cancelled)
    owner_session.commit()

    view = family_batch_view(
        restricted_session,
        lens=StudentLens(account_id=student),
        enrollment_id=seat,
        today=TODAY,
    )

    assert view.past_sessions == []
