"""Whether an exam may be written, reported rather than guessed.

**The gap this closes.** `ExamResultsPayload` on the client carries a
`writable` flag described as "decided server-side [BR5.5]", and no
response returned one. A client defaulting it to true would offer a
mark-entry field whose save is then refused — which a person blames on
the app, not on the rule.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import Batch
from app.marks.entry import exam_is_writable
from tests.marks.conftest import TeacherFixture


def test_an_exam_in_an_active_batch_is_writable(
    owner_session: DbSession,
    exam: uuid.UUID,
) -> None:
    """The ordinary case.

    :param owner_session: A session able to arrange fixture data
    :param exam: The exam fixture
    :return: None
    """
    assert exam_is_writable(owner_session, exam_id=exam) is True


def test_an_exam_in_an_inactive_batch_is_not_writable(
    owner_session: DbSession,
    teacher: TeacherFixture,
    exam: uuid.UUID,
) -> None:
    """The rule `_writable_exam` raises on, asked rather than raised.

    Both come from one condition, so the screen cannot offer an entry
    field the write would reject [BR5.5].

    :param owner_session: A session able to arrange fixture data
    :param teacher: The batch's owner
    :param exam: The exam fixture
    :return: None
    """
    owner_session.execute(
        sa.update(Batch).where(Batch.id == teacher.batch_id).values(active=False)
    )
    owner_session.commit()

    assert exam_is_writable(owner_session, exam_id=exam) is False


def test_an_exam_that_does_not_exist_is_not_writable(
    owner_session: DbSession,
) -> None:
    """Absent is not writable.

    Returning True for an unknown id would let a screen offer entry
    for an exam that was deleted underneath it.

    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    assert exam_is_writable(owner_session, exam_id=uuid.uuid4()) is False
