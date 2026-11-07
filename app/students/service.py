"""A teacher's students, and the seats they hold in that teacher's batches.

Decided by the owner on 2026-11-05: a teacher keeps ONE list of students,
and the same student can sit in any number of that teacher's batches.

**This module is the one writer of a student's identity on its seats.**
Every read that grants a lens, generates a fee or renders a roster reads
the name, numbers, account links and decisions on ``enrollment``, and
those reads are unchanged. So whenever a student's name or numbers
change, every seat of that student changes in the same transaction here,
and a new seat copies what its student's other seats already hold.

**Acceptance is per student** [D1]. A person who accepted one seat of a
student has accepted that student, so a seat added later for the same
student starts accepted for that link, and an accept or decline through
any seat is written to every seat of the student (``app.accounts.
decisions``). Naming a number on a new student is still never consent:
a link nobody accepted starts ``pending`` [ADR-013, BR5.1].

**Removal never loses a debt** [D4]. A student can be removed only when
none of their seats is active and they owe nothing. A student who still
has seats is archived rather than deleted, because those seats are the
teacher's fee, attendance and marks history.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics.seats import owing_ledger_for_seats
from app.authz.lenses import TeacherLens
from app.batches.service import (
    BatchNotFound,
    _account_for,
    _owned_batch,
    _refuse_second_seat,
)
from app.db.models import Batch, Enrollment, Student
from app.errors import AuthorizationError, ConflictError
from app.money import Money, derive

__all__ = [
    "SeatRequest",
    "StudentChanges",
    "StudentFilter",
    "StudentNotFound",
    "StudentRow",
    "StudentSeat",
    "add_students_to_batch",
    "create_student",
    "enroll_student",
    "find_or_create_student",
    "get_student",
    "list_students",
    "remove_student",
    "seat_for",
    "update_student",
]


class StudentNotFound(AuthorizationError):
    """A student does not exist, or is not this lens's to read.

    404 for both, like :class:`~app.batches.service.BatchNotFound`, so a
    caller cannot learn which student ids are real.
    """

    def __init__(self) -> None:
        """Initialize the refusal with its disclosure-safe status."""
        super().__init__(
            code="STUDENT_NOT_FOUND", message_key="student.not_found", status=404
        )


@dataclass(frozen=True, slots=True)
class SeatRequest:
    """One batch to put a student in.

    :ivar batch_id: The batch
    :ivar fee_amount: This seat's fee, or None to inherit the batch's
    """

    batch_id: uuid.UUID
    fee_amount: Money | None = None


@dataclass(frozen=True, slots=True)
class StudentSeat:
    """One of a student's seats, as the teacher sees it on the student.

    :ivar enrollment_id: The seat
    :ivar batch_id: Its batch
    :ivar batch_name: That batch's name
    :ivar fee_amount: What this seat is charged: its own fee, else the
        batch default, else None when neither is set
    :ivar inactive_from: The date the student left, if they did
    :ivar outstanding: What this seat owes now, never negative
    :ivar is_removable: Whether the seat itself can be deleted, which is
        the roster's own rule: nobody accepted it and nothing was erased
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    fee_amount: Money | None
    inactive_from: dt.date | None
    outstanding: Money
    is_removable: bool


@dataclass(frozen=True, slots=True)
class StudentRow:
    """One student, with every seat they hold in this teacher's batches.

    :ivar student_id: The student
    :ivar display_name: The teacher-typed name
    :ivar student_phone: The student's number, as the teacher typed it
    :ivar guardian_phone: The guardian's number, as the teacher typed it
    :ivar student_state: ``accepted`` when the student accepted any seat,
        ``declined`` when they declined and accepted none, else
        ``pending``
    :ivar guardian_state: The same for the guardian, or ``absent`` when
        no guardian was recorded
    :ivar seats: The student's seats, by batch name
    :ivar total_outstanding: What the student owes across every seat
    :ivar is_removable: Whether removing the student would succeed [D4]
    """

    student_id: uuid.UUID
    display_name: str
    student_phone: str | None
    guardian_phone: str | None
    student_state: str
    guardian_state: str
    seats: list[StudentSeat]
    total_outstanding: Money
    is_removable: bool


@dataclass(frozen=True, slots=True)
class StudentFilter:
    """Which of the teacher's students to list. Applied server-side.

    :ivar batch_id: Only students with a seat in this batch
    :ivar unassigned: Only students with no seat at all
    :ivar exclude_batch_id: Only students WITHOUT a seat in this batch,
        for the roster's "add existing students" picker
    :ivar query: Only students whose name or number contains this text
    """

    batch_id: uuid.UUID | None = None
    unassigned: bool = False
    exclude_batch_id: uuid.UUID | None = None
    query: str | None = None


@dataclass(frozen=True, slots=True)
class StudentChanges:
    """An edit to a student.

    A ``*_set`` flag distinguishes "clear" from "leave as it is" for the
    two numbers.

    :ivar display_name: The new name, or None to keep it
    :ivar student_phone: The new student number, or None to clear it
    :ivar student_phone_set: Whether the student number is being changed
    :ivar guardian_phone: The new guardian number, or None to clear it
    :ivar guardian_phone_set: Whether the guardian number is being changed
    """

    display_name: str | None = None
    student_phone: str | None = None
    student_phone_set: bool = False
    guardian_phone: str | None = None
    guardian_phone_set: bool = False


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _owned_student(
    session: Session, *, lens: TeacherLens, student_id: uuid.UUID
) -> Student:
    """Load a student this lens owns, or refuse without confirming it exists.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :return: The student
    :raises StudentNotFound: No such student, or another owner's
    """
    student = session.execute(
        sa.select(Student).where(
            Student.id == student_id,
            Student.owner_id == lens.owner_id,
            Student.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if student is None:
        raise StudentNotFound
    return student


def _link_state(decisions: list[str]) -> str:
    """Collapse one link's per-seat decisions into the student's state.

    :param decisions: The link's decision on each seat
    :return: ``accepted``, ``declined`` or ``pending``
    """
    if "accepted" in decisions:
        return "accepted"
    if decisions and all(value == "declined" for value in decisions):
        return "declined"
    return "pending"


def _seat_removable(record: Enrollment) -> bool:
    """Apply the roster's own removability rule to one seat.

    :param record: The seat
    :return: True when deleting the seat would be permitted
    """
    accepted = (
        record.student_decision == "accepted" or record.guardian_decision == "accepted"
    )
    erased = (
        record.student_relink_blocked_at is not None
        or record.guardian_relink_blocked_at is not None
    )
    return not accepted and not erased


def _rows(session: Session, students: list[Student]) -> list[StudentRow]:
    """Describe students with their seats, in three statements total.

    One read for the seats of every listed student, one for their
    ledger, then a fold in memory, so the count does not grow with the
    number of students or seats.

    :param session: The session to query through
    :param students: The students, in the order to return them
    :return: One row per student
    """
    if not students:
        return []
    ids = [student.id for student in students]
    seats = session.execute(
        sa.select(Enrollment, Batch.name, Batch.default_fee)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Enrollment.student_id.in_(ids))
        .order_by(Batch.name, Enrollment.id)
    ).all()
    # Only what each seat owes is shown, so only months still owing are
    # folded [C-14].
    ledger = owing_ledger_for_seats(session, [seat.id for seat, _, _ in seats])

    by_student: dict[uuid.UUID, list[tuple[Enrollment, str, Money | None]]] = (
        defaultdict(list)
    )
    for seat, batch_name, default_fee in seats:
        if seat.student_id is not None:
            by_student[seat.student_id].append((seat, batch_name, default_fee))

    rows: list[StudentRow] = []
    for student in students:
        mine = by_student.get(student.id, [])
        described = []
        for seat, batch_name, default_fee in mine:
            owed = derive(ledger.get(seat.id, [])).total_outstanding
            described.append(
                StudentSeat(
                    enrollment_id=seat.id,
                    batch_id=seat.batch_id,
                    batch_name=batch_name,
                    fee_amount=seat.fee_amount
                    if seat.fee_amount is not None
                    else default_fee,
                    inactive_from=seat.inactive_from,
                    outstanding=owed if owed.is_positive() else Money.ZERO,
                    is_removable=_seat_removable(seat),
                )
            )
        total = Money.sum(seat.outstanding for seat in described)
        has_guardian = student.guardian_phone is not None or any(
            seat.guardian_account_id is not None for seat, _, _ in mine
        )
        rows.append(
            StudentRow(
                student_id=student.id,
                display_name=student.display_name,
                student_phone=student.student_phone,
                guardian_phone=student.guardian_phone,
                student_state=_link_state([s.student_decision for s, _, _ in mine]),
                guardian_state=_link_state([s.guardian_decision for s, _, _ in mine])
                if has_guardian
                else "absent",
                seats=described,
                total_outstanding=total,
                is_removable=not total.is_positive()
                and all(seat.inactive_from is not None for seat in described),
            )
        )
    return rows


def list_students(
    session: Session,
    *,
    lens: TeacherLens,
    where: StudentFilter | None = None,
    limit: int | None = None,
    after: uuid.UUID | None = None,
) -> list[StudentRow]:
    """List this teacher's students, filtered server-side.

    The filters run here rather than on the client, because filtering a
    domain list is a decision the server owes the client [TC-9].

    **Keyset pages, when asked for** [C-14]. The order is
    ``(lower(display_name), id)``, so a page is "the next ``limit``
    students after this one" and stays correct while students are added
    between pages, which an offset would not. With neither argument the
    whole list is returned, as it always was.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param where: Which students to list; all of them when None
    :param limit: At most this many; None for all
    :param after: Continue after this student, the last of the previous
        page; None to start from the first
    :return: One row per student, ordered by name
    :raises BatchNotFound: A filter names a batch this lens does not own
    :raises StudentNotFound: ``after`` is no student of this lens's
    """
    where = where or StudentFilter()
    statement = sa.select(Student).where(
        Student.owner_id == lens.owner_id, Student.archived_at.is_(None)
    )
    seated = sa.select(Enrollment.student_id).where(Enrollment.student_id == Student.id)
    if where.batch_id is not None:
        _owned_batch(session, lens=lens, batch_id=where.batch_id)
        statement = statement.where(
            seated.where(Enrollment.batch_id == where.batch_id).exists()
        )
    if where.exclude_batch_id is not None:
        _owned_batch(session, lens=lens, batch_id=where.exclude_batch_id)
        statement = statement.where(
            ~seated.where(Enrollment.batch_id == where.exclude_batch_id).exists()
        )
    if where.unassigned:
        statement = statement.where(~seated.exists())
    if where.query:
        pattern = "%" + _escape_like(where.query.strip()) + "%"
        statement = statement.where(
            sa.or_(
                Student.display_name.ilike(pattern, escape="\\"),
                Student.student_phone.ilike(pattern, escape="\\"),
                Student.guardian_phone.ilike(pattern, escape="\\"),
            )
        )
    key = sa.func.lower(Student.display_name)
    if after is not None:
        # Archived or not: a student archived between two pages still
        # marks where the previous page ended.
        mark = session.execute(
            sa.select(key).where(Student.id == after, Student.owner_id == lens.owner_id)
        ).scalar_one_or_none()
        if mark is None:
            raise StudentNotFound
        statement = statement.where(sa.tuple_(key, Student.id) > (mark, after))
    statement = statement.order_by(key, Student.id)
    if limit is not None:
        statement = statement.limit(limit)
    students = list(session.execute(statement).scalars())
    return _rows(session, students)


def _escape_like(text: str) -> str:
    """Escape the LIKE wildcards in typed search text.

    :param text: What the teacher typed
    :return: The same text, matching literally
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_student(
    session: Session, *, lens: TeacherLens, student_id: uuid.UUID
) -> StudentRow:
    """Read one of this teacher's students with every seat.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :return: The student
    :raises StudentNotFound: Not this lens's student
    """
    return _rows(session, [_owned_student(session, lens=lens, student_id=student_id)])[
        0
    ]


# --------------------------------------------------------------------------
# Writing seats
# --------------------------------------------------------------------------


def _siblings(session: Session, student_id: uuid.UUID) -> list[Enrollment]:
    """Every seat a student already holds.

    :param session: The session to query through
    :param student_id: The student
    :return: The seats
    """
    return list(
        session.execute(
            sa.select(Enrollment).where(Enrollment.student_id == student_id)
        ).scalars()
    )


def _carried_decision(
    siblings: list[Enrollment], *, link: str, account_id: uuid.UUID | None
) -> str:
    """Choose the decision a new seat's link starts with [D1].

    ``accepted`` only when the SAME account accepted another seat of this
    student, so acceptance is never carried to somebody new. A decline is
    not carried: a new class is a new question.

    :param siblings: The student's other seats
    :param link: ``student`` or ``guardian``
    :param account_id: The account the new seat's link resolves to
    :return: ``accepted`` or ``pending``
    """
    if account_id is None:
        return "pending"
    for seat in siblings:
        if link == "student":
            if seat.student_account_id == account_id and (
                seat.student_decision == "accepted"
            ):
                return "accepted"
        elif seat.guardian_account_id == account_id and (
            seat.guardian_decision == "accepted"
        ):
            return "accepted"
    return "pending"


def seat_for(
    session: Session,
    *,
    lens: TeacherLens,
    student: Student,
    batch_id: uuid.UUID,
    fee_amount: Money | None = None,
    joined_on: dt.date | None = None,
) -> Enrollment:
    """Create one seat for a student, copying what their other seats hold.

    Does not commit.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param student: The student, already owned by this lens
    :param batch_id: The batch to seat them in
    :param fee_amount: This seat's fee, or None to inherit
    :param joined_on: When the student joined
    :return: The new seat, flushed
    :raises BatchNotFound: The batch is not this lens's
    :raises ConflictError: The student already has a seat in the batch
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    siblings = _siblings(session, student.id)
    if any(seat.batch_id == batch_id for seat in siblings):
        raise ConflictError(
            code="ENROLLMENT_STUDENT_ALREADY_SEATED",
            message_key="enrollment.student_already_in_batch",
        )

    # An erased link stays erased on every seat of the student [BR6.2]:
    # the marker is what stops the number reattaching, so a new seat
    # that dropped it would reattach it.
    student_blocked = next(
        (s.student_relink_blocked_at for s in siblings if s.student_relink_blocked_at),
        None,
    )
    guardian_blocked = next(
        (
            s.guardian_relink_blocked_at
            for s in siblings
            if s.guardian_relink_blocked_at
        ),
        None,
    )
    student_account = (
        None if student_blocked else _account_for(session, student.student_phone)
    )
    guardian_account = (
        None if guardian_blocked else _account_for(session, student.guardian_phone)
    )
    _refuse_second_seat(
        session,
        batch_id=batch_id,
        student_phone=student.student_phone,
        student_account_id=student_account,
    )

    record = Enrollment(
        batch_id=batch_id,
        student_id=student.id,
        student_account_id=student_account,
        guardian_account_id=guardian_account,
        display_name=student.display_name,
        guardian_phone=student.guardian_phone,
        student_phone=student.student_phone,
        fee_amount=fee_amount,
        joined_on=joined_on,
        # STATED, never defaulted [ADR-013]: pending unless the same
        # account already accepted this student [D1].
        student_decision=_carried_decision(
            siblings, link="student", account_id=student_account
        ),
        guardian_decision=_carried_decision(
            siblings, link="guardian", account_id=guardian_account
        ),
        student_relink_blocked_at=student_blocked,
        guardian_relink_blocked_at=guardian_blocked,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.flush()
    return record


def _phone_taken(
    session: Session,
    *,
    lens: TeacherLens,
    phone: str | None,
    except_id: uuid.UUID | None = None,
) -> Student | None:
    """Find this teacher's student who already has a number [D2].

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param phone: A canonical student number, or None
    :param except_id: A student to ignore, for edits
    :return: That student, archived or not, or None
    """
    if phone is None:
        return None
    statement = sa.select(Student).where(
        Student.owner_id == lens.owner_id, Student.student_phone == phone
    )
    if except_id is not None:
        statement = statement.where(Student.id != except_id)
    return session.execute(statement).scalar_one_or_none()


def _refuse_taken(existing: Student | None) -> None:
    """Refuse a number another of this teacher's students already has.

    :param existing: The student holding it, or None
    :return: None
    :raises ConflictError: The number belongs to an active student
    """
    if existing is not None and existing.archived_at is None:
        raise ConflictError(
            code="STUDENT_PHONE_TAKEN",
            message_key="student.phone_taken",
        )


def find_or_create_student(
    session: Session,
    *,
    lens: TeacherLens,
    display_name: str,
    student_phone: str | None,
    guardian_phone: str | None,
    reuse_by_phone: bool,
) -> Student:
    """Return the student to seat, creating one when needed. No commit.

    A number belonging to an archived student brings that student back
    rather than making a second one, so their history stays theirs.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param display_name: The typed name
    :param student_phone: The typed student number, canonical
    :param guardian_phone: The typed guardian number, canonical
    :param reuse_by_phone: Whether an ACTIVE student with this number is
        reused (the add-to-batch path) rather than refused (the
        add-student path)
    :return: The student
    :raises ConflictError: The number is taken and reuse was not asked for
    """
    existing = _phone_taken(session, lens=lens, phone=student_phone)
    if existing is not None and existing.archived_at is None:
        if reuse_by_phone:
            return existing
        _refuse_taken(existing)
    if existing is not None:
        existing.archived_at = None
        _apply_identity(
            session,
            existing,
            display_name=display_name,
            guardian_phone=guardian_phone,
            guardian_phone_set=True,
        )
        return existing

    student = Student(
        owner_id=lens.owner_id,
        display_name=display_name,
        student_phone=student_phone,
        guardian_phone=guardian_phone,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(student)
    session.flush()
    return student


def create_student(
    session: Session,
    *,
    lens: TeacherLens,
    display_name: str,
    student_phone: str | None = None,
    guardian_phone: str | None = None,
    seats: list[SeatRequest] | None = None,
) -> StudentRow:
    """Record a student and, optionally, seat them in batches [D3].

    All or nothing: a refusal on any batch leaves no student behind.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param display_name: The typed name
    :param student_phone: The typed student number, canonical
    :param guardian_phone: The typed guardian number, canonical
    :param seats: The batches to put them in, possibly none
    :return: The new student
    :raises ConflictError: The number belongs to another student, or a
        batch is listed twice
    :raises BatchNotFound: A batch is not this lens's
    """
    requested = seats or []
    if len({seat.batch_id for seat in requested}) != len(requested):
        raise ConflictError(
            code="ENROLLMENT_STUDENT_ALREADY_SEATED",
            message_key="enrollment.student_already_in_batch",
        )
    try:
        student = find_or_create_student(
            session,
            lens=lens,
            display_name=display_name,
            student_phone=student_phone,
            guardian_phone=guardian_phone,
            reuse_by_phone=False,
        )
        for seat in requested:
            seat_for(
                session,
                lens=lens,
                student=student,
                batch_id=seat.batch_id,
                fee_amount=seat.fee_amount,
            )
    except (ConflictError, BatchNotFound):
        session.rollback()
        raise
    session.commit()
    return get_student(session, lens=lens, student_id=student.id)


def enroll_student(
    session: Session,
    *,
    lens: TeacherLens,
    student_id: uuid.UUID,
    batch_id: uuid.UUID,
    fee_amount: Money | None = None,
) -> StudentRow:
    """Put an existing student in one more batch.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :param batch_id: The batch
    :param fee_amount: This seat's fee, or None to inherit
    :return: The student, with the new seat
    :raises StudentNotFound: Not this lens's student
    :raises BatchNotFound: Not this lens's batch
    :raises ConflictError: Already in that batch
    """
    student = _owned_student(session, lens=lens, student_id=student_id)
    try:
        seat_for(
            session,
            lens=lens,
            student=student,
            batch_id=batch_id,
            fee_amount=fee_amount,
        )
    except (ConflictError, BatchNotFound):
        session.rollback()
        raise
    session.commit()
    return get_student(session, lens=lens, student_id=student_id)


def add_students_to_batch(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    student_ids: list[uuid.UUID],
) -> int:
    """Seat several existing students in one batch, all or nothing.

    The roster's "add existing students" picker.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :param student_ids: The students
    :return: How many seats were created
    :raises StudentNotFound: A student is not this lens's
    :raises BatchNotFound: Not this lens's batch
    :raises ConflictError: A student is already in the batch
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    unique = list(dict.fromkeys(student_ids))
    try:
        for student_id in unique:
            student = _owned_student(session, lens=lens, student_id=student_id)
            seat_for(session, lens=lens, student=student, batch_id=batch_id)
    except (ConflictError, BatchNotFound, StudentNotFound):
        session.rollback()
        raise
    session.commit()
    return len(unique)


# --------------------------------------------------------------------------
# Editing and removing
# --------------------------------------------------------------------------


def _apply_identity(
    session: Session,
    student: Student,
    *,
    display_name: str | None = None,
    student_phone: str | None = None,
    student_phone_set: bool = False,
    guardian_phone: str | None = None,
    guardian_phone_set: bool = False,
) -> None:
    """Write new identity fields to a student AND every seat. No commit.

    A changed number relinks each seat to the account that number signs
    in with, and resets that link to ``pending``: a different number is
    a different person, who has agreed to nothing.

    :param session: The session to write through
    :param student: The student
    :param display_name: The new name, or None to keep it
    :param student_phone: The new student number
    :param student_phone_set: Whether to apply ``student_phone``
    :param guardian_phone: The new guardian number
    :param guardian_phone_set: Whether to apply ``guardian_phone``
    :return: None
    """
    seats = _siblings(session, student.id)
    if display_name is not None:
        student.display_name = display_name
        for seat in seats:
            seat.display_name = display_name
    if student_phone_set and student_phone != student.student_phone:
        student.student_phone = student_phone
        account = _account_for(session, student_phone)
        for seat in seats:
            seat.student_phone = student_phone
            seat.student_account_id = account
            seat.student_decision = "pending"
    if guardian_phone_set and guardian_phone != student.guardian_phone:
        student.guardian_phone = guardian_phone
        account = _account_for(session, guardian_phone)
        for seat in seats:
            seat.guardian_phone = guardian_phone
            seat.guardian_account_id = account
            seat.guardian_decision = "pending"
    session.flush()


def _refuse_relink(seats: list[Enrollment], *, link: str) -> None:
    """Refuse to change a number someone has accepted or erased.

    Changing an accepted number would hand that person's view of the
    child to whoever holds the new one; changing an erased one would
    reattach records the person deleted [BR6.2].

    :param seats: The student's seats
    :param link: ``student`` or ``guardian``
    :return: None
    :raises ConflictError: The link is accepted or erased on some seat
    """
    for seat in seats:
        decision = (
            seat.student_decision if link == "student" else seat.guardian_decision
        )
        blocked = (
            seat.student_relink_blocked_at
            if link == "student"
            else seat.guardian_relink_blocked_at
        )
        if decision == "accepted":
            raise ConflictError(
                code="STUDENT_NUMBER_ACCEPTED",
                message_key="student.number_accepted",
            )
        if blocked is not None:
            raise ConflictError(
                code="STUDENT_NUMBER_ERASED",
                message_key="student.number_erased",
            )


def update_student(
    session: Session,
    *,
    lens: TeacherLens,
    student_id: uuid.UUID,
    changes: StudentChanges,
) -> StudentRow:
    """Edit a student's name or numbers, on the student and every seat.

    The name can always change. A number can change only while nobody
    holding it has accepted and it was never erased.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :param changes: What to change
    :return: The student, as edited
    :raises StudentNotFound: Not this lens's student
    :raises ConflictError: The number is taken, accepted or erased
    """
    student = _owned_student(session, lens=lens, student_id=student_id)
    seats = _siblings(session, student.id)
    if changes.student_phone_set and changes.student_phone != student.student_phone:
        _refuse_relink(seats, link="student")
        # Archived or not: two records for one number is the duplicate
        # D2 exists to prevent.
        if _phone_taken(
            session, lens=lens, phone=changes.student_phone, except_id=student.id
        ):
            raise ConflictError(
                code="STUDENT_PHONE_TAKEN", message_key="student.phone_taken"
            )
    if changes.guardian_phone_set and changes.guardian_phone != student.guardian_phone:
        _refuse_relink(seats, link="guardian")

    _apply_identity(
        session,
        student,
        display_name=changes.display_name,
        student_phone=changes.student_phone,
        student_phone_set=changes.student_phone_set,
        guardian_phone=changes.guardian_phone,
        guardian_phone_set=changes.guardian_phone_set,
    )
    session.commit()
    return get_student(session, lens=lens, student_id=student_id)


def remove_student(
    session: Session, *, lens: TeacherLens, student_id: uuid.UUID
) -> None:
    """Remove a student who is in no active batch and owes nothing [D4].

    A student with no seats is deleted. A student whose seats remain as
    history is archived: hidden from the list, with every seat, fee and
    mark kept exactly as it was.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :return: None
    :raises StudentNotFound: Not this lens's student
    :raises ConflictError: Still in an active batch, or still owes money
    """
    row = get_student(session, lens=lens, student_id=student_id)
    if any(seat.inactive_from is None for seat in row.seats):
        raise ConflictError(
            code="STUDENT_IN_ACTIVE_BATCH",
            message_key="student.remove.in_active_batch",
        )
    if row.total_outstanding.is_positive():
        raise ConflictError(code="STUDENT_OWES", message_key="student.remove.owes")
    student = _owned_student(session, lens=lens, student_id=student_id)
    if row.seats:
        student.archived_at = dt.datetime.now(tz=dt.UTC)
    else:
        session.delete(student)
    session.commit()
