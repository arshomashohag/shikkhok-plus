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
from typing import Final

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.identifier import resolve_link_target
from app.analytics.seats import owing_ledger_for_seats
from app.authz.lenses import TeacherLens
from app.batches.service import (
    BatchNotFound,
    _check_joined_on,
    _owned_batch,
    _refuse_second_seat,
)
from app.db.advisory import contact_key, lock_keys
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
    :ivar student_email: The student's address, as the teacher typed it,
        lowercased [U2]
    :ivar guardian_email: The guardian's address, likewise
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
    student_email: str | None
    guardian_email: str | None
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
    four contacts.

    :ivar display_name: The new name, or None to keep it
    :ivar student_phone: The new student number, or None to clear it
    :ivar student_phone_set: Whether the student number is being changed
    :ivar guardian_phone: The new guardian number, or None to clear it
    :ivar guardian_phone_set: Whether the guardian number is being changed
    :ivar student_email: The new student address, or None to clear it
    :ivar student_email_set: Whether the student address is being changed
    :ivar guardian_email: The new guardian address, or None to clear it
    :ivar guardian_email_set: Whether the guardian address is being changed
    """

    display_name: str | None = None
    student_phone: str | None = None
    student_phone_set: bool = False
    guardian_phone: str | None = None
    guardian_phone_set: bool = False
    student_email: str | None = None
    student_email_set: bool = False
    guardian_email: str | None = None
    guardian_email_set: bool = False


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
        # Absent only when no guardian contact of either kind is recorded
        # and no account is linked: a guardian recorded by email alone is
        # pending, not absent [BR1.6], and reading only the phone would
        # tell the teacher whether an account holds the address [NFR1.4].
        has_guardian = (
            student.guardian_phone is not None
            or student.guardian_email is not None
            or any(seat.guardian_account_id is not None for seat, _, _ in mine)
        )
        rows.append(
            StudentRow(
                student_id=student.id,
                display_name=student.display_name,
                student_phone=student.student_phone,
                guardian_phone=student.guardian_phone,
                student_email=student.student_email,
                guardian_email=student.guardian_email,
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


# --------------------------------------------------------------------------
# Linking seats to a verified contact [U2: BR3.2 to BR3.8]
# --------------------------------------------------------------------------

#: The guardian half, keyed by the kind of contact verified. A phone takes
#: every empty, unblocked guardian link recording it; an email takes only
#: those recording NO phone [BR3.3], because a link that records a phone
#: belongs to that phone's holder [BR2.1].
#:
#: **The link and NOT the decision** [BR3.4], and only an EMPTY link
#: [BR3.5]: the condition names the link's current state, so a concurrent
#: teacher edit holding the seat row makes this re-check the committed row
#: rather than overwrite it [BR2.6].
_LINK_GUARDIANS: Final = {
    "phone": sa.text(
        """
        UPDATE enrollment
        SET guardian_account_id = :account_id
        WHERE guardian_phone = :value
          AND guardian_account_id IS NULL
          AND guardian_relink_blocked_at IS NULL
        """
    ),
    "email": sa.text(
        """
        UPDATE enrollment
        SET guardian_account_id = :account_id
        WHERE guardian_email = :value
          AND guardian_phone IS NULL
          AND guardian_account_id IS NULL
          AND guardian_relink_blocked_at IS NULL
        """
    ),
}

#: The student half, under the guardian half's rules plus one more: an
#: account is the student of at most one seat per batch [BR3.7,
#: ``uq_enrollment_batch_student``]. A batch where the account already
#: holds a student link is skipped, and of two candidate seats in one
#: batch only the oldest is taken. Skipping is silent: the seat waits for
#: the teacher, and the sign-up or contact add it rides on succeeds.
_STUDENT_MATCH: Final = {
    "phone": "c.student_phone = :value",
    "email": "c.student_email = :value AND c.student_phone IS NULL",
}
_LINK_STUDENTS: Final = {
    kind: sa.text(
        f"""
        UPDATE enrollment
        SET student_account_id = :account_id
        WHERE id IN (
            SELECT DISTINCT ON (c.batch_id) c.id
            FROM enrollment c
            WHERE {match}
              AND c.student_account_id IS NULL
              AND c.student_relink_blocked_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM enrollment o
                  WHERE o.batch_id = c.batch_id
                    AND o.student_account_id = :account_id
              )
            ORDER BY c.batch_id, c.created_at, c.id
        )
          AND student_account_id IS NULL
          AND student_relink_blocked_at IS NULL
        """  # noqa: S608 -- `match` is one of two literals in this module
    )
    for kind, match in _STUDENT_MATCH.items()
}


def link_seats(
    session: Session, *, account_id: uuid.UUID, kind: str, value: str
) -> None:
    """Attach the seats a verified contact names to the account that holds it.

    Two set-based statements whatever the number of seats [NFR8.4]: one
    per link. Adds to the caller's transaction and does not commit.

    :param session: The session to write through
    :param account_id: The account that now holds the contact
    :param kind: ``phone`` or ``email``
    :param value: The canonical contact
    :return: None
    """
    parameters = {"account_id": account_id, "value": value}
    session.execute(_LINK_GUARDIANS[kind], parameters)
    session.execute(_LINK_STUDENTS[kind], parameters)


#: Every seat the account holds a link on, locked in ascending id order
#: [NFR4.2 LO-2], so a teacher edit of the same seats either finished
#: first or waits for the erasure.
_LOCK_HELD_SEATS: Final = sa.text(
    """
    SELECT id FROM enrollment
    WHERE student_account_id = :account_id OR guardian_account_id = :account_id
    ORDER BY id
    FOR UPDATE
    """
)

#: Each role's erasure marker, set where the link is the erased account
#: and only where it is not already set [NFR3.1]. The link itself is
#: cleared afterwards by ``ON DELETE SET NULL`` when the account row goes.
_BLOCK_STUDENT_LINKS: Final = sa.text(
    """
    UPDATE enrollment SET student_relink_blocked_at = :now
    WHERE student_account_id = :account_id AND student_relink_blocked_at IS NULL
    """
)
_BLOCK_GUARDIAN_LINKS: Final = sa.text(
    """
    UPDATE enrollment SET guardian_relink_blocked_at = :now
    WHERE guardian_account_id = :account_id AND guardian_relink_blocked_at IS NULL
    """
)


def block_relinking(session: Session, *, account_id: uuid.UUID) -> int:
    """Mark every link an erased account held so nothing relinks it [NFR3.1].

    Called by account deletion before the account row is deleted. Without
    the markers, ``ON DELETE SET NULL`` would leave an empty link still
    recording the erased person's contact, and whoever verified that
    contact next would be handed the seat. The block is per LINK: the
    other link of the same seat is untouched.

    Adds to the caller's transaction and does not commit.

    :param session: The session to write through
    :param account_id: The account being erased
    :return: How many links were blocked, for the deletion's own record
    """
    session.execute(_LOCK_HELD_SEATS, {"account_id": account_id})
    parameters = {"account_id": account_id, "now": dt.datetime.now(tz=dt.UTC)}
    blocked = 0
    for statement in (_BLOCK_STUDENT_LINKS, _BLOCK_GUARDIAN_LINKS):
        result = session.connection().execute(statement, parameters)
        blocked += result.rowcount
    return blocked


#: The four recorded contacts of a student, as (kind, column) pairs.
_CONTACT_COLUMNS: Final = (
    ("phone", "student_phone"),
    ("phone", "guardian_phone"),
    ("email", "student_email"),
    ("email", "guardian_email"),
)


def _contacts_of(holder: object) -> list[tuple[str, str]]:
    """List the recorded contacts on a student or a change, as (kind, value).

    :param holder: A ``Student`` or a ``StudentChanges``
    :return: Every recorded contact, absent ones skipped
    """
    found: list[tuple[str, str]] = []
    for kind, column in _CONTACT_COLUMNS:
        value = getattr(holder, column)
        if value is not None:
            found.append((kind, value))
    return found


def _lock_for_save(
    session: Session, student_id: uuid.UUID | None, contacts: list[tuple[str, str]]
) -> list[Enrollment]:
    """Take a teacher save's locks, in the one order, and read the seats.

    **Contact keys first, then the student's seat rows** [NFR4.2 LO-1 to
    LO-3]. The keys serialise this save against a match for the same
    contact [BR2.7]: a match that committed first is seen when the target
    is resolved, and one that starts later sees this seat. The seat rows,
    locked in ascending id order and read fresh under the lock, serialise
    it against a holder's accept, decline or erasure of the same seats
    [BR2.6]: the decision this save checks is the decision in force when
    it writes.

    :param session: The session to write through
    :param student_id: The student, or None for one not yet written
    :param contacts: Every contact the save resolves, before and after
    :return: The student's seats, locked
    """
    lock_keys(session, [contact_key(kind, value) for kind, value in contacts])
    if student_id is None:
        return []
    return list(
        session.execute(
            sa.select(Enrollment)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars()
    )


def _email_taken_error() -> ConflictError:
    """Build the refusal for a student email another student has [BR1.2].

    :return: The error
    """
    return ConflictError(code="STUDENT_EMAIL_TAKEN", message_key="student.email.taken")


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
    :raises ValidationError: The start date is outside the allowed window
    :raises ConflictError: The student already has a seat in the batch
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)
    # Here because this is the one place a seat is created [audit C-24].
    _check_joined_on(joined_on)
    siblings = _lock_for_save(session, student.id, _contacts_of(student))
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
    # Each link's target by the one precedence rule [BR2.1]: the phone's
    # account when a phone is recorded, the email's only when none is.
    student_account = (
        None
        if student_blocked
        else resolve_link_target(
            session, phone=student.student_phone, email=student.student_email
        )
    )
    guardian_account = (
        None
        if guardian_blocked
        else resolve_link_target(
            session, phone=student.guardian_phone, email=student.guardian_email
        )
    )
    _refuse_second_seat(
        session,
        batch_id=batch_id,
        student_phone=student.student_phone,
        student_account_id=student_account,
        student_email=student.student_email,
    )

    record = Enrollment(
        batch_id=batch_id,
        student_id=student.id,
        student_account_id=student_account,
        guardian_account_id=guardian_account,
        display_name=student.display_name,
        guardian_phone=student.guardian_phone,
        student_phone=student.student_phone,
        # Copies of the student's addresses, as the numbers are [BR1.5].
        student_email=student.student_email,
        guardian_email=student.guardian_email,
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


def _email_taken(
    session: Session,
    *,
    lens: TeacherLens,
    email: str | None,
    except_id: uuid.UUID | None = None,
) -> Student | None:
    """Find this teacher's student who already has a student email [BR1.2].

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param email: A canonical student address, or None
    :param except_id: A student to ignore, for edits
    :return: That student, archived or not, or None
    """
    if email is None:
        return None
    statement = sa.select(Student).where(
        Student.owner_id == lens.owner_id, Student.student_email == email
    )
    if except_id is not None:
        statement = statement.where(Student.id != except_id)
    return session.execute(statement).scalar_one_or_none()


def _identify(
    session: Session,
    *,
    lens: TeacherLens,
    student_phone: str | None,
    student_email: str | None,
) -> tuple[Student | None, str]:
    """Find the existing student a create names, by phone first [BR1.7].

    A typed number identifies the student, as it always has. A typed
    student email must then agree: belonging to a DIFFERENT student of
    this teacher, it is refused rather than quietly moved. With no number,
    the email identifies by the same active-or-archived rule.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param student_phone: The typed student number, canonical
    :param student_email: The typed student address, canonical
    :return: The student found, or None; and ``phone`` or ``email`` for
        which contact found it
    :raises ConflictError: The email belongs to another student
    """
    by_email = _email_taken(session, lens=lens, email=student_email)
    if student_phone is None:
        return by_email, "email"
    by_phone = _phone_taken(session, lens=lens, phone=student_phone)
    if by_phone is not None and by_phone.archived_at is None:
        return by_phone, "phone"
    if by_email is not None and (by_phone is None or by_email.id != by_phone.id):
        raise _email_taken_error()
    return by_phone, "phone"


def find_or_create_student(
    session: Session,
    *,
    lens: TeacherLens,
    display_name: str,
    student_phone: str | None,
    guardian_phone: str | None,
    reuse_by_phone: bool,
    client_mutation_id: uuid.UUID | None = None,
    student_email: str | None = None,
    guardian_email: str | None = None,
) -> Student:
    """Return the student to seat, creating one when needed. No commit.

    A number -- or, with no number, a student email -- belonging to an
    archived student brings that student back rather than making a second
    one, so their history stays theirs [BR1.7].

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param display_name: The typed name
    :param student_phone: The typed student number, canonical
    :param guardian_phone: The typed guardian number, canonical
    :param reuse_by_phone: Whether an ACTIVE student with this number is
        reused (the add-to-batch path) rather than refused (the
        add-student path)
    :param client_mutation_id: The create's retry key, stored on a new
        student so a resend finds it
    :param student_email: The typed student address, canonical
    :param guardian_email: The typed guardian address, canonical
    :return: The student
    :raises ConflictError: The number or the address is taken and reuse
        was not asked for
    """
    existing, found_by = _identify(
        session, lens=lens, student_phone=student_phone, student_email=student_email
    )
    if existing is not None and existing.archived_at is None:
        if reuse_by_phone and found_by == "phone":
            return existing
        if found_by == "email":
            raise _email_taken_error()
        _refuse_taken(existing)
    if existing is not None:
        changes = StudentChanges(
            display_name=display_name,
            guardian_phone=guardian_phone,
            guardian_phone_set=True,
            guardian_email=guardian_email,
            guardian_email_set=True,
            student_email=student_email,
            student_email_set=student_email is not None,
        )
        # The revive path refuses exactly as an edit does [BR2.4, BR2.5;
        # review R-06]: a changed contact on an accepted or erased link,
        # or a student link that would seat its account twice in a batch.
        after = _after(existing, changes)
        links = _changed_links(existing, after)
        seats = _lock_for_save(
            session,
            existing.id,
            _contacts_of(existing)
            + [
                (kind, value)
                for kind, column in _CONTACT_COLUMNS
                if (value := after[column]) is not None
            ],
        )
        for link in sorted(links):
            _refuse_relink(seats, link=link)
        if "student" in links:
            _refuse_student_twice(session, existing, seats, after)
        existing.archived_at = None
        _apply_identity(session, existing, changes)
        return existing

    student = Student(
        owner_id=lens.owner_id,
        display_name=display_name,
        student_phone=student_phone,
        guardian_phone=guardian_phone,
        student_email=student_email,
        guardian_email=guardian_email,
        created_at=dt.datetime.now(tz=dt.UTC),
        client_mutation_id=client_mutation_id,
    )
    # In a savepoint: two creates of one number or address at once both
    # pass the reads above, and the partial unique index refuses the
    # second -- with the same refusal a sequential duplicate gets [BR1.2].
    try:
        with session.begin_nested():
            session.add(student)
            session.flush()
    except IntegrityError as error:
        raise _uniqueness_refusal(error) from None
    return student


def _uniqueness_refusal(error: IntegrityError) -> ConflictError:
    """Map a per-teacher uniqueness violation to its business refusal.

    :param error: The violation a concurrent duplicate reached
    :return: The refusal a sequential duplicate gets
    :raises IntegrityError: Any other constraint, re-raised unmapped
    """
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_student_owner_email":
        return _email_taken_error()
    if constraint == "uq_student_owner_phone":
        return ConflictError(
            code="STUDENT_PHONE_TAKEN", message_key="student.phone_taken"
        )
    raise error


def replayed_student(
    session: Session, *, lens: TeacherLens, client_mutation_id: uuid.UUID | None
) -> Student | None:
    """Return the student an earlier create under this key made, if any.

    **Serialized, not just looked up** [audit C-25]. Two resends of one
    create arrive together on a slow network; both would find nothing and
    both create. A transaction-scoped advisory lock on the teacher and the
    key makes the second wait for the first to commit, after which it
    finds the first's student. The unique index on the key is the
    backstop. No key, no lock: old clients keep today's behaviour.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param client_mutation_id: The request's retry key, or None
    :return: The earlier student, or None to create one
    """
    if client_mutation_id is None:
        return None
    session.execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.func.hashtextextended(
                    f"student:{lens.owner_id}:{client_mutation_id}", 0
                )
            )
        )
    )
    return session.scalars(
        sa.select(Student).where(
            Student.owner_id == lens.owner_id,
            Student.client_mutation_id == client_mutation_id,
        )
    ).one_or_none()


def create_student(
    session: Session,
    *,
    lens: TeacherLens,
    display_name: str,
    student_phone: str | None = None,
    guardian_phone: str | None = None,
    seats: list[SeatRequest] | None = None,
    client_mutation_id: uuid.UUID | None = None,
    student_email: str | None = None,
    guardian_email: str | None = None,
) -> StudentRow:
    """Record a student and, optionally, seat them in batches [D3].

    All or nothing: a refusal on any batch leaves no student behind.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param display_name: The typed name
    :param student_phone: The typed student number, canonical
    :param guardian_phone: The typed guardian number, canonical
    :param seats: The batches to put them in, possibly none
    :param client_mutation_id: The retry key
    :param student_email: The typed student address, canonical [U2]
    :param guardian_email: The typed guardian address, canonical
    :return: The new student
    :raises ConflictError: The number or the address belongs to another
        student, or a batch is listed twice
    :raises BatchNotFound: A batch is not this lens's
    """
    earlier = replayed_student(
        session, lens=lens, client_mutation_id=client_mutation_id
    )
    if earlier is not None:
        return get_student(session, lens=lens, student_id=earlier.id)
    requested = seats or []
    if len({seat.batch_id for seat in requested}) != len(requested):
        raise ConflictError(
            code="ENROLLMENT_STUDENT_ALREADY_SEATED",
            message_key="enrollment.student_already_in_batch",
        )
    try:
        # The typed contacts' keys before anything resolves a target
        # [BR2.7]; a revived student's own adds its old ones, still ahead
        # of every seat-row lock [LO-1].
        lock_keys(
            session,
            [
                contact_key(kind, value)
                for kind, value in (
                    ("phone", student_phone),
                    ("phone", guardian_phone),
                    ("email", student_email),
                    ("email", guardian_email),
                )
                if value is not None
            ],
        )
        student = find_or_create_student(
            session,
            lens=lens,
            display_name=display_name,
            student_phone=student_phone,
            guardian_phone=guardian_phone,
            reuse_by_phone=False,
            client_mutation_id=client_mutation_id,
            student_email=student_email,
            guardian_email=guardian_email,
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


def _after(student: Student, changes: StudentChanges) -> dict[str, str | None]:
    """Compute a student's four contacts as they will be after an edit.

    :param student: The student, as stored
    :param changes: The edit
    :return: Each contact column to its value after the edit
    """
    return {
        column: getattr(changes, column)
        if getattr(changes, f"{column}_set")
        else getattr(student, column)
        for _, column in _CONTACT_COLUMNS
    }


def _changed_links(student: Student, after: dict[str, str | None]) -> set[str]:
    """Name the links whose recorded contacts an edit changes.

    A link is the student's (``student_phone``, ``student_email``) or the
    guardian's (``guardian_phone``, ``guardian_email``). A value equal to
    the stored one is no change.

    :param student: The student, as stored
    :param after: The contacts after the edit
    :return: ``student``, ``guardian``, both or neither
    """
    return {
        column.split("_", 1)[0]
        for _, column in _CONTACT_COLUMNS
        if after[column] != getattr(student, column)
    }


def _apply_identity(
    session: Session, student: Student, changes: StudentChanges
) -> list[Enrollment]:
    """Write new identity fields to a student AND every seat. No commit.

    **A changed contact relinks its link and resets it** [BR2.3]. For each
    link with at least one changed contact, every seat's link is set to
    the target its contacts resolve to after the change by the one
    precedence rule [BR2.1] -- possibly nobody -- and its decision becomes
    ``pending``: a different contact is a different person, who has
    agreed to nothing. That holds even when the target is unchanged. A
    seat whose link is erased keeps an empty link whatever is recorded.

    Takes the save's locks first (:func:`_lock_for_save`), for the
    contacts before AND after the change, so the seats it writes are the
    seats it read.

    :param session: The session to write through
    :param student: The student
    :param changes: The edit
    :return: The student's seats, locked and written
    """
    after = _after(student, changes)
    links = _changed_links(student, after)
    keys = _contacts_of(student) + [
        (kind, value)
        for kind, column in _CONTACT_COLUMNS
        if (value := after[column]) is not None
    ]
    seats = _lock_for_save(session, student.id, keys)
    if changes.display_name is not None:
        student.display_name = changes.display_name
        for seat in seats:
            seat.display_name = changes.display_name
    for link in sorted(links):
        phone, email = after[f"{link}_phone"], after[f"{link}_email"]
        setattr(student, f"{link}_phone", phone)
        setattr(student, f"{link}_email", email)
        target = resolve_link_target(session, phone=phone, email=email)
        for seat in seats:
            setattr(seat, f"{link}_phone", phone)
            setattr(seat, f"{link}_email", email)
            blocked = getattr(seat, f"{link}_relink_blocked_at") is not None
            setattr(seat, f"{link}_account_id", None if blocked else target)
            setattr(seat, f"{link}_decision", "pending")
    session.flush()
    return seats


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
    """Edit a student's name or contacts, on the student and every seat.

    The name can always change. A contact -- number or address -- can
    change only while nobody holding that link has accepted it and it was
    never erased [BR2.4], checked on the seat rows LOCKED for this edit,
    so a holder's concurrent accept either committed first and refuses
    the edit, or waits and then finds the link re-pointed [BR2.6].

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param student_id: The student
    :param changes: What to change
    :return: The student, as edited
    :raises StudentNotFound: Not this lens's student
    :raises ConflictError: A contact is taken, accepted or erased, or the
        new student link's account already sits in one of its batches
    """
    student = _owned_student(session, lens=lens, student_id=student_id)
    after = _after(student, changes)
    links = _changed_links(student, after)
    keys = _contacts_of(student) + [
        (kind, value)
        for kind, column in _CONTACT_COLUMNS
        if (value := after[column]) is not None
    ]
    try:
        seats = _lock_for_save(session, student.id, keys)
        for link in sorted(links):
            _refuse_relink(seats, link=link)
        _refuse_duplicate_contacts(session, lens, student, after)
        if "student" in links:
            _refuse_student_twice(session, student, seats, after)
        _apply_identity(session, student, changes)
    except ConflictError:
        session.rollback()
        raise
    session.commit()
    return get_student(session, lens=lens, student_id=student_id)


def _refuse_duplicate_contacts(
    session: Session,
    lens: TeacherLens,
    student: Student,
    after: dict[str, str | None],
) -> None:
    """Refuse a student number or address another student of this teacher has.

    Archived or not: two records for one contact is the duplicate D2 and
    BR1.2 exist to prevent.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param student: The student being edited
    :param after: The contacts after the edit
    :return: None
    :raises ConflictError: The number or the address is taken
    """
    phone, email = after["student_phone"], after["student_email"]
    if phone != student.student_phone and _phone_taken(
        session, lens=lens, phone=phone, except_id=student.id
    ):
        raise ConflictError(
            code="STUDENT_PHONE_TAKEN", message_key="student.phone_taken"
        )
    if email != student.student_email and _email_taken(
        session, lens=lens, email=email, except_id=student.id
    ):
        raise _email_taken_error()


def _refuse_student_twice(
    session: Session,
    student: Student,
    seats: list[Enrollment],
    after: dict[str, str | None],
) -> None:
    """Refuse a relink that would seat one account twice in a batch [BR2.5].

    :param session: The session to query through
    :param student: The student being edited
    :param seats: The student's seats, locked
    :param after: The contacts after the edit
    :return: None
    :raises ConflictError: The new target already holds another student
        seat in one of this student's batches
    """
    target = resolve_link_target(
        session, phone=after["student_phone"], email=after["student_email"]
    )
    if target is None or not seats:
        return
    clash = session.execute(
        sa.select(Enrollment.id).where(
            Enrollment.batch_id.in_([seat.batch_id for seat in seats]),
            Enrollment.student_account_id == target,
            Enrollment.student_id != student.id,
        )
    ).first()
    if clash is not None:
        raise ConflictError(
            code="ENROLLMENT_STUDENT_ALREADY_SEATED",
            message_key="enrollment.student_already_in_batch",
        )


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
