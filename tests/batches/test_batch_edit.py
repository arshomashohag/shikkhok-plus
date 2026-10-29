"""Editing a batch: its name, subjects, fee and due day.

**Written before the edit existed.** Two of these are money and
authorization decisions and are test-first by the team's predicate: a
fee change must not rewrite a charge already made, and another teacher
must not be able to edit this batch. The others pin the subject rule: a
subject an exam was set in cannot be dropped, because the exam would
lose what it was a test of.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches import service
from app.batches.service import BatchChanges
from app.db.models import Batch, BatchSubject, Exam, LedgerEntryRow
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.fees.generation import generate_due_cycles
from app.money import Money
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


@pytest.fixture
def teacher(owner_session: Session) -> TeacherFixture:
    """Provide a teacher owning one batch with a 1500 fee due on the 10th.

    :param owner_session: An arranging session
    :return: The teacher
    """
    return make_teacher(owner_session, name="Physics A")


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build a teacher's lens.

    :param teacher: The teacher
    :return: Their lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_named_fields_change_and_others_stay(
    restricted_session: Session, teacher: TeacherFixture
) -> None:
    """A PATCH changes what it names and leaves the rest alone.

    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    summary = service.update_batch(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        changes=BatchChanges(name="Physics B", fee_due_day=5),
    )

    assert summary.batch.name == "Physics B"
    assert summary.batch.fee_due_day == 5
    assert summary.batch.default_fee == Money("1500.00")


def test_another_teacher_cannot_edit_this_batch(
    owner_session: Session, restricted_session: Session, teacher: TeacherFixture
) -> None:
    """A stranger's edit is refused and changes nothing.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    stranger = make_teacher(owner_session, name="Chemistry")

    with pytest.raises(AuthorizationError):
        service.update_batch(
            restricted_session,
            lens=_lens(stranger),
            batch_id=teacher.batch_id,
            changes=BatchChanges(name="Taken"),
        )

    owner_session.expire_all()
    batch = owner_session.get(Batch, teacher.batch_id)
    assert batch is not None
    assert batch.name == "Physics A"


def test_a_new_fee_leaves_charges_already_made_alone(
    owner_session: Session, restricted_session: Session, teacher: TeacherFixture
) -> None:
    """October was charged 1500; raising the fee to 1600 charges November.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    seat = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_decision="pending",
    )
    generate_due_cycles(owner_session, today=dt.date(2026, 10, 15))

    service.update_batch(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        changes=BatchChanges(default_fee=Money("1600.00")),
    )
    generate_due_cycles(owner_session, today=dt.date(2026, 11, 15))

    charges = dict(
        owner_session.execute(
            sa.select(LedgerEntryRow.period, LedgerEntryRow.amount).where(
                LedgerEntryRow.enrollment_id == seat,
                LedgerEntryRow.kind == "charge",
            )
        ).all()
    )
    assert charges["2026-10"] == Money("1500.00")
    assert charges["2026-11"] == Money("1600.00")


def test_subjects_are_added_and_unused_ones_dropped(
    restricted_session: Session, teacher: TeacherFixture
) -> None:
    """The list given is the list kept; existing keys survive.

    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    lens = _lens(teacher)
    first = service.update_batch(
        restricted_session,
        lens=lens,
        batch_id=teacher.batch_id,
        changes=BatchChanges(subjects=["Mechanics", "Optics"]),
    )
    mechanics = first.subject_ids[first.subjects.index("Mechanics")]

    second = service.update_batch(
        restricted_session,
        lens=lens,
        batch_id=teacher.batch_id,
        changes=BatchChanges(subjects=["Mechanics", "Waves"]),
    )

    assert second.subjects == ["Mechanics", "Waves"]
    assert second.subject_ids[second.subjects.index("Mechanics")] == mechanics


def test_a_subject_with_an_exam_cannot_be_dropped(
    owner_session: Session, restricted_session: Session, teacher: TeacherFixture
) -> None:
    """Dropping it would orphan the exam, so the edit is refused whole.

    :param owner_session: An arranging session
    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    subject = BatchSubject(batch_id=teacher.batch_id, name="Optics")
    owner_session.add(subject)
    owner_session.flush()
    owner_session.add(
        Exam(
            batch_id=teacher.batch_id,
            batch_subject_id=subject.id,
            title="Mid-term",
            date=dt.date(2026, 10, 20),
            total_marks=100,
            created_at=dt.datetime.now(tz=dt.UTC),
        )
    )
    owner_session.commit()

    with pytest.raises(ConflictError):
        service.update_batch(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            changes=BatchChanges(name="Renamed", subjects=["Waves"]),
        )

    owner_session.expire_all()
    batch = owner_session.get(Batch, teacher.batch_id)
    assert batch is not None
    assert batch.name == "Physics A"


def test_an_empty_subject_list_is_refused(
    restricted_session: Session, teacher: TeacherFixture
) -> None:
    """A batch always teaches something, as at creation.

    :param restricted_session: The application-role session
    :param teacher: The batch's owner
    :return: None
    """
    with pytest.raises(ValidationError):
        service.update_batch(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            changes=BatchChanges(subjects=[]),
        )
