"""The exams a centre member is the examiner of [C4].

Derived from the account in the query that reads them: the exams whose
examiner is a membership the account holds, accepted and unrevoked.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.db.models import Batch, BatchSubject, Exam, Owner, OwnerMember

__all__ = ["MyExam", "my_exams"]


@dataclass(frozen=True, slots=True)
class MyExam:
    """One exam the caller marks.

    :ivar exam_id: The exam
    :ivar centre_name: Its centre
    :ivar batch_name: Its batch
    :ivar subject_name: Its subject
    :ivar title: Its name
    :ivar date: When it was sat
    :ivar total_marks: The denominator
    :ivar published: Whether its results have been published
    :ivar cancelled: Whether it was cancelled
    """

    exam_id: uuid.UUID
    centre_name: str
    batch_name: str
    subject_name: str
    title: str
    date: dt.date
    total_marks: int
    published: bool
    cancelled: bool


def my_exams(session: DbSession, *, account_id: uuid.UUID) -> list[MyExam]:
    """List the exams this account is the examiner of, newest first.

    :param session: The session to read through
    :param account_id: The authenticated account
    :return: The exams
    """
    rows = session.execute(
        sa.select(Exam, Owner.name, Batch.name, BatchSubject.name)
        .join(Batch, Batch.id == Exam.batch_id)
        .join(Owner, Owner.id == Batch.owner_id)
        .join(BatchSubject, BatchSubject.id == Exam.batch_subject_id)
        .join(
            OwnerMember,
            sa.and_(
                OwnerMember.id == Exam.examiner_member_id,
                OwnerMember.owner_id == Batch.owner_id,
                OwnerMember.account_id == account_id,
                OwnerMember.decision == "accepted",
                OwnerMember.revoked_at.is_(None),
            ),
        )
        .order_by(Exam.date.desc(), Exam.created_at.desc(), Exam.id)
    ).all()
    return [
        MyExam(
            exam_id=exam.id,
            centre_name=centre or "",
            batch_name=batch,
            subject_name=subject,
            title=exam.title,
            date=exam.date,
            total_marks=exam.total_marks,
            published=exam.published_at is not None,
            cancelled=exam.cancelled_at is not None,
        )
        for exam, centre, batch, subject in rows
    ]
