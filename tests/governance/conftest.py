"""The fixture a deletion test is worthless without.

**A deletion test with no retained rows asserts nothing about
retention.** Every ``RETAIN_WITH_BASIS`` assertion is vacuously true
over an empty set, so a fixture that creates only an account and a
profile produces a suite that is green whatever the cascades do.

So :func:`populated_account` builds a seat with **attendance, marks, a
fee cycle, a settled ledger and a payment claim** before anything is
deleted -- one row in every table the manifest says must survive an
account deletion and that an account can actually reach.

**Both roles, and the student is the one that was broken.** A
guardian's link was already ``SET NULL``; a student's was ``CASCADE``
until ``0007``. A test using only a guardian passes against the defect
``0007`` exists to fix.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Attendance,
    Batch,
    BatchSubject,
    Enrollment,
    Exam,
    FeeCycle,
    LedgerEntryRow,
    Mark,
    Owner,
    PaymentClaim,
    Profile,
    QueuedSubmission,
    RefreshToken,
)
from app.db.models import Session as ClassSession
from app.money import Money


@dataclass(frozen=True, slots=True)
class PopulatedSeat:
    """One seat with every retained kind of row hanging off it.

    :ivar teacher_account_id: The teacher who owns the batch
    :ivar student_account_id: The student holding the seat
    :ivar guardian_account_id: The guardian recorded for the seat
    :ivar student_phone: The student's number
    :ivar guardian_phone: The guardian's number
    :ivar teacher_phone: The teacher's number
    :ivar batch_id: The batch
    :ivar enrollment_id: The seat itself
    """

    teacher_account_id: uuid.UUID
    student_account_id: uuid.UUID
    guardian_account_id: uuid.UUID
    student_phone: str
    guardian_phone: str
    teacher_phone: str
    batch_id: uuid.UUID
    enrollment_id: uuid.UUID


def _make_account(session: Session, phone: str) -> uuid.UUID:
    """Create one account with a profile and a refresh token.

    The profile and token are not decoration: both are ``HARD_DELETE``
    and account-scoped, so an account without them would make two of
    the absence assertions vacuous.

    :param session: An arranging session
    :param phone: The account's number
    :return: The new account's id
    """
    now = dt.datetime.now(tz=dt.UTC)
    account = Account(phone=phone, created_at=now, activated_at=now)
    session.add(account)
    session.commit()

    session.add(Profile(account_id=account.id, self_name="Self", address="Somewhere"))
    session.add(
        RefreshToken(
            account_id=account.id,
            token_hash=uuid.uuid4().hex,
            family_id=uuid.uuid4(),
            issued_at=now,
            expires_at=now + dt.timedelta(days=30),
        )
    )
    session.commit()
    return account.id


@pytest.fixture
def populated_seat(owner_session: Session) -> PopulatedSeat:
    """Build a teacher, a student, a guardian and a fully populated seat.

    :param owner_session: A session able to arrange fixture data
    :return: Every id the deletion tests assert against
    """
    return build_populated_seat(owner_session)


def build_populated_seat(owner_session: Session) -> PopulatedSeat:
    """Arrange one complete seat, callable more than once per test.

    **Exposed as a function and not only as a fixture** because the
    two-path comparison needs TWO identically shaped seats in one test:
    it deletes one by each path and compares what survives. A fixture
    yielding one seat cannot give it the second.

    :param owner_session: A session able to arrange fixture data
    :return: Every id the deletion tests assert against
    """
    now = dt.datetime.now(tz=dt.UTC)
    suffix = uuid.uuid4().int % 10**6

    teacher_phone = f"+88016{suffix:06d}01"
    student_phone = f"+88016{suffix:06d}02"
    guardian_phone = f"+88016{suffix:06d}03"

    teacher = _make_account(owner_session, teacher_phone)
    student = _make_account(owner_session, student_phone)
    guardian = _make_account(owner_session, guardian_phone)

    owner = Owner(account_id=teacher, created_at=now)
    owner_session.add(owner)
    owner_session.commit()

    batch = Batch(
        owner_id=owner.id,
        name="Deletion fixture",
        default_fee=Money("1000.00"),
        fee_due_day=5,
        marksheet_visible=True,
        active=True,
        created_at=now,
    )
    owner_session.add(batch)
    owner_session.commit()

    subject = BatchSubject(batch_id=batch.id, name="Physics")
    owner_session.add(subject)
    owner_session.commit()

    enrollment = Enrollment(
        batch_id=batch.id,
        student_account_id=student,
        guardian_account_id=guardian,
        guardian_phone=guardian_phone,
        display_name="Teacher-typed name",
        student_decision="accepted",
        guardian_decision="accepted",
        created_at=now,
    )
    owner_session.add(enrollment)
    owner_session.commit()

    class_session = ClassSession(
        batch_id=batch.id,
        batch_subject_id=subject.id,
        date=now.date(),
        start_time=dt.time(16, 0),
        status="held",
        origin="ad_hoc",
        attendance_version=1,
        topic_version=0,
        created_at=now,
    )
    owner_session.add(class_session)
    owner_session.commit()

    # The queued submission names the TEACHER, which is what makes it
    # the third contradicting reference `0007` fixes -- and the one a
    # reading of pairs missed.
    submission = QueuedSubmission(
        session_id=class_session.id,
        submitted_by_account_id=teacher,
        kind="attendance",
        client_mutation_id=uuid.uuid4(),
        base_version=0,
        resulting_version=1,
        created_at=now,
    )
    owner_session.add(submission)
    owner_session.commit()

    owner_session.add(
        Attendance(
            session_id=class_session.id,
            enrollment_id=enrollment.id,
            present=True,
            recorded_at=now,
            recorded_by_account_id=teacher,
            submission_id=submission.id,
        )
    )

    exam = Exam(
        batch_id=batch.id,
        batch_subject_id=subject.id,
        title="Term one",
        date=now.date(),
        total_marks=100,
        created_at=now,
    )
    owner_session.add(exam)
    owner_session.commit()

    owner_session.add(
        Mark(
            exam_id=exam.id,
            enrollment_id=enrollment.id,
            result_state="marked",
            marks=87,
            recorded_at=now,
            recorded_by_account_id=teacher,
            created_at=now,
        )
    )

    period = now.strftime("%Y-%m")
    owner_session.add(
        FeeCycle(
            enrollment_id=enrollment.id,
            period=period,
            due_date=now.date(),
            created_at=now,
        )
    )

    # The claim is submitted by the STUDENT, which is the second
    # contradicting reference: before `0007` a student's deletion took
    # the record of a payment they made, with its channel and
    # transaction reference.
    claim = PaymentClaim(
        enrollment_id=enrollment.id,
        period=period,
        claimed_amount=Money("1000.00"),
        channel="bkash",
        transaction_id="TRX123456",
        submitted_by_account_id=student,
        submitted_at=now,
        status="approved_full",
        approved_amount=Money("1000.00"),
        verified_by_account_id=teacher,
        verified_at=now,
    )
    owner_session.add(claim)
    owner_session.commit()

    owner_session.add(
        LedgerEntryRow(
            enrollment_id=enrollment.id,
            period=period,
            kind="charge",
            amount=Money("1000.00"),
            created_by_account_id=teacher,
            created_at=now,
        )
    )
    owner_session.add(
        LedgerEntryRow(
            enrollment_id=enrollment.id,
            period=period,
            kind="receipt",
            amount=Money("1000.00"),
            payment_claim_id=claim.id,
            created_by_account_id=teacher,
            created_at=now,
        )
    )
    owner_session.commit()

    return PopulatedSeat(
        teacher_account_id=teacher,
        student_account_id=student,
        guardian_account_id=guardian,
        student_phone=student_phone,
        guardian_phone=guardian_phone,
        teacher_phone=teacher_phone,
        batch_id=batch.id,
        enrollment_id=enrollment.id,
    )
