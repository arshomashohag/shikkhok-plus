"""Draft, review, publish, and decimal marks (decided 2026-11-05).

* An exam's marks are the teacher's own until they publish: a family's
  progress series and marksheet leave a draft out entirely, and no
  family is told about a draft result.
* Publishing is refused while a seat that could have sat the exam has
  no result, tells every seat with a result at once, and is idempotent.
* A mark may be decimal to two places; a third place is refused.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, TeacherLens
from app.db.models import Exam, Notification
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.marks.entry import record_mark
from app.marks.views import guardian_progress, publish_exam, seat_marksheet
from app.notifications.inbox import MARKS_AVAILABLE
from tests.batches.conftest import TeacherFixture, enroll
from tests.marks.conftest import EXAM_DATE, TOTAL_MARKS


def _draft(
    owner_session: DbSession, teacher: TeacherFixture, subject: uuid.UUID
) -> uuid.UUID:
    """Create an exam that has not been published.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param subject: The subject assessed
    :return: The exam id
    """
    row = Exam(
        batch_id=teacher.batch_id,
        batch_subject_id=subject,
        title="Draft test",
        date=EXAM_DATE,
        total_marks=TOTAL_MARKS,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    owner_session.add(row)
    owner_session.commit()
    return row.id


def _child(
    owner_session: DbSession,
    teacher: TeacherFixture,
    account_factory: Callable[[], uuid.UUID],
    name: str = "Rahim",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seat a child with an accepted guardian.

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param account_factory: Makes accounts
    :param name: The child's name
    :return: The seat and the guardian's account
    """
    guardian = account_factory()
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name=name,
        student_account_id=account_factory(),
        guardian_account_id=guardian,
        student_decision="accepted",
        guardian_decision="accepted",
    )
    return seat, guardian


def _told(owner_session: DbSession, exam_id: uuid.UUID) -> int:
    """Count the seats told an exam's results are out.

    Per seat rather than per item: a student and a guardian each get one.

    :param owner_session: A session able to read fixture data
    :param exam_id: The exam
    :return: How many seats were told
    """
    owner_session.expire_all()
    return (
        owner_session.scalar(
            sa.select(sa.func.count(sa.distinct(Notification.enrollment_id)))
            .select_from(Notification)
            .where(
                Notification.kind == MARKS_AVAILABLE, Notification.source_id == exam_id
            )
        )
        or 0
    )


def test_a_draft_is_invisible_to_the_family_until_published(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """No series entry, no marksheet and no notice for a draft.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :param teacher: The batch's owner
    :param teacher_lens: The teacher's lens
    :param subject: The subject assessed
    :param account_factory: Makes accounts
    :return: None
    """
    exam_id = _draft(owner_session, teacher, subject)
    seat, guardian = _child(owner_session, teacher, account_factory)
    lens = GuardianLens(account_id=guardian, child_enrollment_id=seat)

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_id,
        enrollment_id=seat,
        result_state="marked",
        marks=19.5,
    )

    assert guardian_progress(restricted_session, lens=lens, enrollment_id=seat) == []
    with pytest.raises(AuthorizationError):
        seat_marksheet(
            restricted_session, lens=lens, enrollment_id=seat, exam_id=exam_id
        )
    assert _told(owner_session, exam_id) == 0, "a draft result was announced"

    publish_exam(restricted_session, lens=teacher_lens, exam_id=exam_id)

    series = guardian_progress(restricted_session, lens=lens, enrollment_id=seat)
    assert [entry.marks for entry in series] == [19.5]
    assert _told(owner_session, exam_id) == 1


def test_publishing_waits_for_every_seat_that_could_have_sat_it(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Refused with the count while a seat has no result; an absence counts.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :param teacher: The batch's owner
    :param teacher_lens: The teacher's lens
    :param subject: The subject assessed
    :param account_factory: Makes accounts
    :return: None
    """
    exam_id = _draft(owner_session, teacher, subject)
    first, _ = _child(owner_session, teacher, account_factory, "Rahim")
    second, _ = _child(owner_session, teacher, account_factory, "Karim")
    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_id,
        enrollment_id=first,
        result_state="marked",
        marks=40,
    )

    with pytest.raises(ConflictError) as refused:
        publish_exam(restricted_session, lens=teacher_lens, exam_id=exam_id)
    assert refused.value.message_key == "marks.publish.incomplete"
    assert refused.value.details == {"not_entered": "1"}

    record_mark(
        restricted_session,
        lens=teacher_lens,
        exam_id=exam_id,
        enrollment_id=second,
        result_state="absent",
        marks=None,
    )
    publish_exam(restricted_session, lens=teacher_lens, exam_id=exam_id)
    publish_exam(restricted_session, lens=teacher_lens, exam_id=exam_id)

    assert _told(owner_session, exam_id) == 2, "each seat told once, twice published"


def test_a_correction_after_publishing_is_read_but_not_announced_again(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """A published exam's correction is visible at once and sends nothing.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :param teacher: The batch's owner
    :param teacher_lens: The teacher's lens
    :param subject: The subject assessed
    :param account_factory: Makes accounts
    :return: None
    """
    exam_id = _draft(owner_session, teacher, subject)
    seat, guardian = _child(owner_session, teacher, account_factory)
    for marks in (40.0, 42.25):
        if marks == 42.25:
            publish_exam(restricted_session, lens=teacher_lens, exam_id=exam_id)
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam_id,
            enrollment_id=seat,
            result_state="marked",
            marks=marks,
        )

    lens = GuardianLens(account_id=guardian, child_enrollment_id=seat)
    series = guardian_progress(restricted_session, lens=lens, enrollment_id=seat)
    assert [entry.marks for entry in series] == [42.25]
    assert _told(owner_session, exam_id) == 1


@pytest.mark.parametrize("marks", [19.125, 0.001])
def test_a_mark_with_a_third_decimal_place_is_refused(
    owner_session: DbSession,
    restricted_session: DbSession,
    teacher: TeacherFixture,
    teacher_lens: TeacherLens,
    subject: uuid.UUID,
    account_factory: Callable[[], uuid.UUID],
    marks: float,
) -> None:
    """Two places at most, as the column stores; never rounded silently.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: A session as the application role
    :param teacher: The batch's owner
    :param teacher_lens: The teacher's lens
    :param subject: The subject assessed
    :param account_factory: Makes accounts
    :param marks: The over-precise mark
    :return: None
    """
    exam_id = _draft(owner_session, teacher, subject)
    seat, _ = _child(owner_session, teacher, account_factory)

    with pytest.raises(ValidationError) as refused:
        record_mark(
            restricted_session,
            lens=teacher_lens,
            exam_id=exam_id,
            enrollment_id=seat,
            result_state="marked",
            marks=marks,
        )
    assert refused.value.message_key == "marks.too_precise"
