"""Batch and enrollment operations, each scoped by a lens.

**The scoping value lives inside the lens** [TC-11, security-design §A],
which is what converts authorization from a precondition someone can
forget into a data dependency they cannot compile without. There is no
``owner_id`` parameter on any function here: it comes from the lens or it
does not come at all.

Three rules in this module are load-bearing and easy to implement
plausibly wrong, so each is named where it is enforced:

* a teacher reading another's batch gets a **not-found**, never a
  forbidden, because a 403 confirms the batch exists [NFR14.13];
* a guardian's reachable seats are found through ``guardian_account_id``
  and **never through the child** [BR5.3], since resolving by child
  merges two teachers' records;
* removal tests **two** conditions, because an erased seat looks dormant
  and deleting it destroys the marker that blocks reattachment [BR6.2].
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Account, Batch, BatchSubject, Enrollment, Exam, ScheduleSlot
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.money import Money

__all__ = [
    "BatchChanges",
    "BatchNotFound",
    "BatchSummary",
    "EnrollmentNotRemovable",
    "GuardianChildRow",
    "RosterRow",
    "add_enrollment",
    "create_batch",
    "list_batches",
    "list_guardian_children",
    "list_roster",
    "list_student_batches",
    "remove_enrollment",
    "set_inactive_from",
    "update_batch",
]


class BatchNotFound(AuthorizationError):
    """A batch does not exist, or is not this lens's to read.

    **The two cases are deliberately indistinguishable**, and that is
    why this is an ``AuthorizationError`` carrying 404 rather than a
    ``ValidationError``. Separating them would let a caller enumerate
    which batch ids are real; answering 400 would claim a well-formed
    request was malformed [NFR14.13].
    """

    def __init__(self, code: str, message_key: str) -> None:
        """Initialize the refusal with its disclosure-safe status.

        The status is fixed here rather than passed, so no raise site
        can accidentally answer 403 and reopen the oracle.

        :param code: A stable machine value
        :param message_key: The client string resource to render
        """
        super().__init__(code=code, message_key=message_key, status=404)


class EnrollmentNotRemovable(ConflictError):
    """The seat holds history or a record of someone's erasure.

    A ``ConflictError`` rather than a validation failure: the request is
    well-formed and the state forbids it, so the caller refetches and
    decides rather than retrying [error taxonomy].
    """


@dataclass(frozen=True, slots=True)
class RosterRow:
    """One seat as a teacher sees it.

    Carries ``enrollment_id`` and never a student account id [ADR-001],
    and ``display_name`` from the enrollment rather than from a profile
    -- reaching ``Profile`` for a nicer name is the plausible privacy
    breach this Unit is most likely to commit [security-design §C].

    :ivar enrollment_id: The teacher-facing key for this seat
    :ivar display_name: The teacher-typed name
    :ivar guardian_phone: The teacher-typed guardian contact, if any
    :ivar fee_amount: This seat's fee, or None when it inherits the
        batch default. None is NOT zero: zero is a waiver [AC2.2.5]
    :ivar is_dormant: True while **no link has accepted** this seat
        [BR7.2]. Not "nobody has signed in": after D1 a named account
        may still be pending, and reading the link would show a seat as
        claimed the moment a stranger signs up on a mistyped number
    :ivar inactive_from: The date after which no cycle generates
    :ivar student_state: The student link's own decision --
        ``pending``, ``accepted`` or ``declined`` [BR2.1]
    :ivar guardian_state: The guardian link's own decision, plus a
        fourth value ``absent`` when no guardian is recorded [BR2.2].

        **``absent`` is not ``pending``**, and the distinction is
        load-bearing rather than tidy: ``guardian_account_id`` is
        nullable and a seat genuinely can have no guardian, so
        reporting ``pending`` there would count a decision nobody was
        asked for as outstanding.
    :ivar is_removable: Whether removal would succeed [BR3.1].

        **Sent because the client must not derive it.** Removal tests
        two conditions and this row carries only the first: a client
        inferring removability from the link states it displays would
        offer the action on an erased seat, whose marker it never saw.
    """

    enrollment_id: uuid.UUID
    display_name: str
    guardian_phone: str | None
    fee_amount: Money | None
    is_dormant: bool
    inactive_from: dt.date | None
    student_state: str
    guardian_state: str
    is_removable: bool


@dataclass(frozen=True, slots=True)
class GuardianChildRow:
    """One reachable seat as a guardian sees it.

    :ivar enrollment_id: The seat, which BR5.1 keys the route on
    :ivar student_account_id: The child, used to count DISTINCT children
    :ivar display_name: The teacher-typed name
    :ivar batch_name: Which class, so attribution is possible [BR5.2]
    """

    enrollment_id: uuid.UUID
    student_account_id: uuid.UUID | None
    display_name: str
    batch_name: str


def _nobody_accepted(record: Enrollment) -> bool:
    """Report whether no link on this seat has accepted it.

    **The predicate D1's migration made necessary** [BR7.1, BR7.2].
    Both of this module's merged readers of the link columns -- the
    roster's dormancy flag and ``remove_enrollment``'s claimed check --
    read ``student_account_id`` as "claimed", which was correct only
    while signing in WAS acceptance. After BR5.1 signing up links the
    account and leaves the decision ``pending``, so the link stopped
    answering that question and this does instead.

    **Either link's acceptance claims the seat.** A guardian who
    accepts a seat whose student has not is holding a lens over it, so
    a derivation reading only ``student_decision`` would report a
    claimed seat as removable -- which is the harm in the opposite
    direction from the one this unit is mostly about.

    One function for both callers, deliberately: two copies of a
    predicate that must agree is how they stop agreeing, and the pair
    that was wrong together is the pair this replaces.

    :param record: The seat to test
    :return: True when neither link carries ``accepted``
    """
    return (
        record.student_decision != "accepted" and record.guardian_decision != "accepted"
    )


def _guardian_state(record: Enrollment) -> str:
    """Report the guardian link's decision, or that there is no link.

    **One predicate for both callers.** The roster reads it per row and
    :func:`roster_row_of` reports it for a seat just created; two copies
    of a predicate that must agree is how they stop agreeing, which is
    the reasoning :func:`_nobody_accepted` already records for its own
    pair of callers.

    **``absent`` is a fourth value and not a null** [BR2.2]. A seat with
    no guardian recorded has no decision to report, and answering
    ``pending`` there would count a decision nobody was asked for --
    making the batch's outstanding figure wrong by exactly the number of
    guardian-less seats.

    **The link is the teacher-typed number, not the account id.** A
    guardian the teacher recorded who has not signed up yet carries
    ``guardian_phone`` and a NULL ``guardian_account_id`` [BR5.1,
    ``_LINK_GUARDIAN_SEATS``], and they are genuinely pending: they were
    asked and have not answered. Keying absence on the account id would
    report every unregistered guardian as ``absent``, which is the exact
    inversion this rule exists to prevent.

    :param record: The seat to read
    :return: The guardian decision, or ``absent``
    """
    if record.guardian_phone is None and record.guardian_account_id is None:
        return "absent"
    return record.guardian_decision


def _is_removable(record: Enrollment) -> bool:
    """Report whether removal would succeed on this seat.

    **The two conditions :func:`remove_enrollment` tests, and the roster
    carries only one of them** [BR3.1, NFR14.31]. A seat is removable
    when no link accepted it AND no erasure marker is set; the row
    carries the decisions and does not carry the markers, so a client
    deriving removability from what it displays would offer removal on
    an erased seat. That is a wrong answer presented as an available
    action, not a style preference.

    **The same two predicates the write path uses**, deliberately. This
    answers "would removal succeed", so if it answered differently from
    the function that performs it, the roster would offer an action the
    server then refuses -- which is worse than not offering it, because
    the teacher has already decided by the time they learn.

    :param record: The seat to test
    :return: True when removal would be permitted
    """
    was_erased = (
        record.student_relink_blocked_at is not None
        or record.guardian_relink_blocked_at is not None
    )
    return _nobody_accepted(record) and not was_erased


def _roster_row(record: Enrollment) -> RosterRow:
    """Build one roster row from a seat.

    **One builder, so the add-student response and the roster cannot
    disagree about a seat.** A teacher who adds a student sees the row
    the response carried; the next roster read must show the same seat
    the same way, and two hand-written mappings of the same columns is
    how that stops being true.

    The decisions are **added beside** ``is_dormant`` rather than
    replacing it [BR2.1]: the flag is the seat-level collapse of both
    links and these are the links themselves, so the shared
    :func:`_nobody_accepted` stays the one source for the first.

    :param record: The seat to describe
    :return: The row a teacher reads
    """
    return RosterRow(
        enrollment_id=record.id,
        display_name=record.display_name,
        guardian_phone=record.guardian_phone,
        fee_amount=record.fee_amount,
        is_dormant=_nobody_accepted(record),
        inactive_from=record.inactive_from,
        student_state=record.student_decision,
        guardian_state=_guardian_state(record),
        is_removable=_is_removable(record),
    )


def _owned_batch(session: Session, *, lens: TeacherLens, batch_id: uuid.UUID) -> Batch:
    """Load a batch this lens owns, or refuse without confirming it exists.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch being read
    :return: The batch
    :raises BatchNotFound: No such batch, or it belongs to another owner
    """
    batch = session.execute(
        # owner_id comes from the LENS. There is no parameter to forge
        # and no default to forget.
        sa.select(Batch).where(Batch.id == batch_id, Batch.owner_id == lens.owner_id)
    ).scalar_one_or_none()

    if batch is None:
        raise BatchNotFound(
            code="BATCH_NOT_FOUND",
            message_key="batch.not_found",
        )
    return batch


def list_roster(
    session: Session, *, lens: TeacherLens, batch_id: uuid.UUID
) -> list[RosterRow]:
    """List the seats in one of this teacher's batches.

    **Each row carries both link decisions separately** [BR2.1], and the
    seat appears once. Collapsing them would lose the case the roster
    exists to show: a student who accepted and a guardian who declined
    is a student who is enrolled and owes a fee beside a guardian who
    simply does not watch, and either single value is wrong.

    No extra statement and no join [NFR20.10]: both are columns of the
    rows this select already reads.

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch whose roster to read
    :return: One row per seat, ordered by display name
    :raises BatchNotFound: The batch is not this lens's to read
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)

    rows = session.execute(
        sa.select(Enrollment)
        .where(Enrollment.batch_id == batch_id)
        .order_by(Enrollment.display_name, Enrollment.id)
    ).scalars()

    return [_roster_row(row) for row in rows]


@dataclass(frozen=True)
class StudentBatchRow:
    """One batch a student has accepted a seat in.

    :ivar enrollment_id: Their seat, which every student read is keyed on
    :ivar batch_name: The batch
    :ivar teacher_display_name: What the teacher is called, or None
    :ivar subjects: The subjects taught
    :ivar schedule: The weekly classes as (weekday, start, end)
    """

    enrollment_id: uuid.UUID
    batch_name: str
    teacher_display_name: str | None
    subjects: list[str]
    schedule: list[tuple[int, dt.time, dt.time]]


def list_student_batches(
    session: Session, *, lens: StudentLens
) -> list[StudentBatchRow]:
    """List the batches this student has ACCEPTED a seat in (S1).

    **The acceptance predicate is in this query**, not inherited from
    the lens. The guardian list once relied on the lens instead and
    leaked linked-but-unaccepted seats, because the lens is granted by
    ANY accepted link rather than per seat [BR1.1].

    :param session: The session to query through
    :param lens: The student lens carrying the authenticated account
    :return: One row per accepted seat, ordered by batch name
    """
    rows = session.execute(
        sa.select(Enrollment.id, Batch.id, Batch.name, Batch.teacher_display_name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.student_account_id == lens.account_id,
            Enrollment.student_decision == "accepted",
        )
        .order_by(Batch.name, Enrollment.id)
    ).all()
    batch_ids = [batch_id for _, batch_id, _, _ in rows]
    subjects: dict[uuid.UUID, list[str]] = {batch_id: [] for batch_id in batch_ids}
    for batch_id, name in session.execute(
        sa.select(BatchSubject.batch_id, BatchSubject.name)
        .where(BatchSubject.batch_id.in_(batch_ids))
        .order_by(BatchSubject.name)
    ).all():
        subjects[batch_id].append(name)
    schedules: dict[uuid.UUID, list[tuple[int, dt.time, dt.time]]] = {
        batch_id: [] for batch_id in batch_ids
    }
    for batch_id, weekday, start, end in session.execute(
        sa.select(
            ScheduleSlot.batch_id,
            ScheduleSlot.weekday,
            ScheduleSlot.start_time,
            ScheduleSlot.end_time,
        )
        .where(ScheduleSlot.batch_id.in_(batch_ids))
        .order_by(ScheduleSlot.weekday, ScheduleSlot.start_time)
    ).all():
        schedules[batch_id].append((weekday, start, end))
    return [
        StudentBatchRow(
            enrollment_id=enrollment_id,
            batch_name=name,
            teacher_display_name=teacher,
            subjects=subjects[batch_id],
            schedule=schedules[batch_id],
        )
        for enrollment_id, batch_id, name, teacher in rows
    ]


def list_guardian_children(
    session: Session, *, lens: GuardianLens
) -> list[GuardianChildRow]:
    """List the seats this guardian was recorded on.

    **Resolved through ``guardian_account_id``, never through the child**
    [BR5.3, NFR14.15]. The alternative -- find this guardian's children,
    then show every enrollment of those children -- merges two teachers'
    records: a guardian recorded by teacher A would see teacher B's batch
    for the same child.

    **Filtered to ACCEPTED links here, not transitively.** This used to
    carry no decision predicate, on the reasoning that ``GuardianLens``
    is withheld for an unaccepted link. It is not withheld per SEAT: the
    lens is granted by ANY accepted guardian link, so a guardian who
    accepted their own child's seat also saw every seat merely linked to
    their number -- including one a teacher created by mistyping a digit:
    a stranger's child's name and batch [BR1.1]. Linking at seat creation
    made that common. The fee and marks reads check acceptance per seat
    and were never exposed; this list now does the same.

    :param session: The session to query through
    :param lens: The guardian lens carrying the authenticated account
    :return: One row per reachable seat, ordered by batch then name
    """
    rows = session.execute(
        sa.select(Enrollment, Batch.name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.guardian_account_id == lens.account_id,
            Enrollment.guardian_decision == "accepted",
        )
        .order_by(Batch.name, Enrollment.display_name, Enrollment.id)
    ).all()

    return [
        GuardianChildRow(
            enrollment_id=enrollment.id,
            student_account_id=enrollment.student_account_id,
            display_name=enrollment.display_name,
            batch_name=batch_name,
        )
        for enrollment, batch_name in rows
    ]


def _owned_enrollment(
    session: Session, *, lens: TeacherLens, enrollment_id: uuid.UUID
) -> Enrollment:
    """Load a seat in one of this lens's batches, or refuse.

    **An enrollment is reached through its batch, never by id alone.**
    ``session.get(Enrollment, id)`` loads any row in the database, so a
    write scoped on the id alone is reachable by any authenticated
    teacher who guesses a UUID -- and it looks correct, because the
    handler above it resolved a lens.

    The refusal is a :class:`BatchNotFound` and not an enrollment-shaped
    error, deliberately: telling the caller the enrollment exists but
    belongs to someone else is the same existence oracle a 403 would be
    [NFR14.13].

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :param enrollment_id: The seat being reached
    :return: The enrollment
    :raises BatchNotFound: No such seat, or its batch is another owner's
    """
    record = session.execute(
        sa.select(Enrollment)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(
            Enrollment.id == enrollment_id,
            # owner_id from the LENS. The join is what makes the scope
            # unforgeable: there is no enrollment-level owner column, so
            # a query that skips the batch cannot be scoped at all.
            Batch.owner_id == lens.owner_id,
        )
    ).scalar_one_or_none()

    if record is None:
        raise BatchNotFound(
            code="BATCH_NOT_FOUND",
            message_key="batch.not_found",
        )
    return record


def remove_enrollment(
    session: Session, *, lens: TeacherLens, enrollment_id: uuid.UUID
) -> None:
    """Delete a seat, if no link accepted it and none was ever erased.

    **Two conditions, and the second is the one that gets forgotten.**
    After an erasure the link is NULL again, so a check reading only
    acceptance deletes the erased row -- destroying the marker that
    stops the number reattaching on its next sign-in, which is the harm
    the marker exists to prevent [BR6.2, §B.1].

    The first condition reads the DECISION columns and not the link
    columns [BR7.1]; see :func:`_nobody_accepted` for why that change
    belongs in the same Unit that changed what the link means.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param enrollment_id: The seat to remove
    :return: None
    :raises BatchNotFound: The seat is not this lens's to write
    :raises EnrollmentNotRemovable: The seat is claimed or was erased
    """
    record = _owned_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    # THE DECISION, NOT THE LINK [BR7.1, AC2.5.1a]. This read
    # ``student_account_id IS NOT NULL`` until D1, and that was correct
    # only while signing in WAS acceptance. After BR5.1 it starts
    # refusing to remove a seat created on a MISTYPED NUMBER the instant
    # that stranger signs up -- closing the single recovery path the
    # acceptance model exists to open, in a merged routed write path
    # rather than on a screen.
    #
    # A declined seat is removable for the same reason a pending one
    # is: nobody accepted, so nothing is destroyed, and re-adding the
    # number creates a fresh seat the person is free to decline again.
    # ADR-003 is intact -- a teacher still cannot make an ACCEPTED
    # person's records go away.
    if not _nobody_accepted(record):
        raise EnrollmentNotRemovable(
            code="ENROLLMENT_CLAIMED",
            message_key="enrollment.remove.claimed",
        )

    was_erased = (
        record.student_relink_blocked_at is not None
        or record.guardian_relink_blocked_at is not None
    )
    if was_erased:
        raise EnrollmentNotRemovable(
            # A DIFFERENT code from the claimed case, because the
            # teacher's remedy differs: a claimed seat can be marked
            # inactive, an erased one cannot be reused at all.
            code="ENROLLMENT_ERASED",
            message_key="enrollment.remove.erased",
        )

    session.delete(record)
    session.commit()


def set_inactive_from(
    session: Session,
    *,
    lens: TeacherLens,
    enrollment_id: uuid.UUID,
    inactive_from: dt.date | None,
) -> None:
    """Record, or clear, the date after which no cycle generates.

    Written **per enrollment**, never per student: one person in two of
    a teacher's batches is two seats [AC2.2.3], and leaving one class
    does not leave the other. U7 reads this; U4 only records it.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param enrollment_id: The seat to mark
    :param inactive_from: The date, or None to reactivate the seat
    :return: None
    :raises BatchNotFound: The seat is not this lens's to write
    """
    record = _owned_enrollment(session, lens=lens, enrollment_id=enrollment_id)

    record.inactive_from = inactive_from
    session.commit()


@dataclass(frozen=True, slots=True)
class BatchSummary:
    """A batch and its seat counts, as its owner sees it.

    **Two numbers, one of them a numerator** [BR1.2]. The pair renders
    as "9 of 12 accepted", and the denominator is the one that is easy
    to get wrong: ``enrollment_count`` counts **every** seat the teacher
    created, declined ones included [BR1.4]. Excluding declined seats
    would shrink it silently as people refuse, so "9 of 12" becomes
    "9 of 11" with nothing having been removed and the teacher unable to
    tell a decline from a removal.

    :ivar batch: The batch row
    :ivar subjects: The subjects taught
    :ivar subject_ids: Each subject's key, parallel to ``subjects``
    :ivar schedule: The weekly classes as (weekday, start, end), in
        weekday then time order
    :ivar enrollment_count: How many seats, computed server-side. The
        DENOMINATOR, and it excludes nothing
    :ivar accepted_count: How many of those seats at least one link has
        accepted [BR1.2]. Either link's acceptance counts the seat: a
        student who accepted has joined, whatever the guardian did
    """

    batch: Batch
    subjects: list[str]
    subject_ids: list[uuid.UUID]
    enrollment_count: int
    accepted_count: int
    schedule: list[tuple[int, dt.time, dt.time]] = field(default_factory=list)


def create_batch(
    session: Session,
    *,
    lens: TeacherLens,
    name: str,
    subjects: list[str],
    teacher_display_name: str | None = None,
    default_fee: Money | None = None,
    fee_due_day: int | None = None,
    collection_number: str | None = None,
    collection_channel: str | None = None,
) -> BatchSummary:
    """Create a batch owned by this lens's owner.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param name: The teacher's name for the class
    :param subjects: One or more subjects taught
    :param teacher_display_name: What students see the teacher called
    :param default_fee: The inherited fee
    :param fee_due_day: Day of month 1-31
    :param collection_number: Where payments are sent
    :param collection_channel: Which service that number belongs to
    :return: The new batch as the list describes it, so the create
        response and the list cannot describe one batch differently --
        including the subject keys an exam or a class is created against
    :raises ValidationError: No subject was named
    """
    if not subjects:
        raise ValidationError(
            code="BATCH_NEEDS_A_SUBJECT",
            message_key="batch.create.subject_required",
        )

    batch = Batch(
        # From the LENS. There is no owner_id parameter to forge.
        owner_id=lens.owner_id,
        name=name,
        teacher_display_name=teacher_display_name,
        default_fee=default_fee,
        fee_due_day=fee_due_day,
        collection_number=collection_number,
        collection_channel=collection_channel,
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.flush()

    rows = [BatchSubject(batch_id=batch.id, name=subject) for subject in subjects]
    session.add_all(rows)
    session.flush()
    session.commit()
    ordered = sorted(rows, key=lambda row: (row.name, row.id))
    return BatchSummary(
        batch=batch,
        subjects=[row.name for row in ordered],
        subject_ids=[row.id for row in ordered],
        # A new batch holds no seats, so both numbers are zero and the
        # count renders from the first moment [W1].
        enrollment_count=0,
        accepted_count=0,
    )


def list_batches(session: Session, *, lens: TeacherLens) -> list[BatchSummary]:
    """List this teacher's batches with their seat counts.

    **The counts come from one grouped query, not one query per batch.**
    The roster's query-count property applies here for the same reason:
    a per-batch count is the N+1 shape with a different name. The
    accepted count joined that statement as a conditional aggregate
    rather than arriving as a fourth one [NFR20.7, NFR20.8].

    :param session: The session to query through
    :param lens: The teacher lens carrying the owner id
    :return: One summary per batch, newest first
    """
    batches = list(
        session.execute(
            sa.select(Batch)
            .where(Batch.owner_id == lens.owner_id)
            .order_by(Batch.created_at.desc(), Batch.id)
        ).scalars()
    )
    if not batches:
        return []

    batch_ids = [batch.id for batch in batches]
    # **One pass for both numbers** [NFR20.7, NFR20.8]. The numerator is
    # a conditional aggregate on the statement that already computes the
    # denominator, so adding the accepted count costs no additional
    # statement however many batches a teacher owns -- which is the N+1
    # property this query was already written to hold.
    #
    # `count(...) FILTER (WHERE ...)` rather than `sum(CASE WHEN ...)`:
    # both are one pass, and FILTER says what it means. Syntax-checked
    # against the pinned SQLAlchemy 2.1.5 before this was written, since
    # a fourth grouped statement was the named fallback.
    counted = session.execute(
        sa.select(
            Enrollment.batch_id,
            sa.func.count(Enrollment.id),
            # EITHER link's acceptance claims the seat [BR1.2]. Reading
            # only `student_decision` would report a seat whose guardian
            # accepted as not joined.
            sa.func.count(Enrollment.id).filter(
                sa.or_(
                    Enrollment.student_decision == "accepted",
                    Enrollment.guardian_decision == "accepted",
                )
            ),
        )
        .where(Enrollment.batch_id.in_(batch_ids))
        .group_by(Enrollment.batch_id)
    ).all()
    counts = {batch_id: total for batch_id, total, _ in counted}
    accepted = {batch_id: taken for batch_id, _, taken in counted}
    subjects: dict[uuid.UUID, list[str]] = {batch_id: [] for batch_id in batch_ids}
    subject_ids: dict[uuid.UUID, list[uuid.UUID]] = {
        batch_id: [] for batch_id in batch_ids
    }
    # The key travels with the name in the same ordered statement, so
    # the two lists cannot fall out of step.
    for batch_id, subject_id, subject_name in session.execute(
        sa.select(BatchSubject.batch_id, BatchSubject.id, BatchSubject.name)
        .where(BatchSubject.batch_id.in_(batch_ids))
        .order_by(BatchSubject.name, BatchSubject.id)
    ).all():
        subjects[batch_id].append(subject_name)
        subject_ids[batch_id].append(subject_id)
    # The schedule in one grouped statement too, for T6's card line. Read
    # from the model directly: the teaching module owns the WRITE, and
    # importing it here would close a cycle (it imports this module).
    schedules: dict[uuid.UUID, list[tuple[int, dt.time, dt.time]]] = {
        batch_id: [] for batch_id in batch_ids
    }
    for batch_id, weekday, start, end in session.execute(
        sa.select(
            ScheduleSlot.batch_id,
            ScheduleSlot.weekday,
            ScheduleSlot.start_time,
            ScheduleSlot.end_time,
        )
        .where(ScheduleSlot.batch_id.in_(batch_ids))
        .order_by(ScheduleSlot.weekday, ScheduleSlot.start_time)
    ).all():
        schedules[batch_id].append((weekday, start, end))

    return [
        BatchSummary(
            batch=batch,
            subjects=subjects[batch.id],
            subject_ids=subject_ids[batch.id],
            enrollment_count=counts.get(batch.id, 0),
            accepted_count=accepted.get(batch.id, 0),
            schedule=schedules[batch.id],
        )
        for batch in batches
    ]


def _account_for(session: Session, phone: str | None) -> uuid.UUID | None:
    """Find the account a canonical number signs in with, if any.

    Exact comparison is correct only because every stored and incoming
    number is canonical [0008, ``app.schemas.phone``]; before that it
    missed every number typed in a different spelling.

    :param session: The session to query through
    :param phone: A canonical number, or None
    :return: The account's id, or None
    """
    if phone is None:
        return None
    return session.execute(
        sa.select(Account.id).where(Account.phone == phone)
    ).scalar_one_or_none()


def _refuse_second_seat(
    session: Session,
    *,
    batch_id: uuid.UUID,
    student_phone: str | None,
    student_account_id: uuid.UUID | None,
) -> None:
    """Refuse a second seat for one student in one batch.

    **A clear refusal instead of a 500.** A student holds at most one seat
    per batch (``uq_enrollment_batch_student``). Once seats link to
    accounts by number, adding the same student twice -- an easy slip --
    hit that constraint as a server error. Refusing on the NUMBER too,
    not only on a linked account, also keeps two waiting seats from
    colliding when that student later signs up.

    :param session: The session to query through
    :param batch_id: The batch
    :param student_phone: The typed student number, canonical, or None
    :param student_account_id: The account it resolves to, or None
    :return: None
    :raises ConflictError: That student already has a seat here
    """
    clauses = []
    if student_phone is not None:
        clauses.append(Enrollment.student_phone == student_phone)
    if student_account_id is not None:
        clauses.append(Enrollment.student_account_id == student_account_id)
    if not clauses:
        return
    taken = session.execute(
        sa.select(Enrollment.id).where(
            Enrollment.batch_id == batch_id, sa.or_(*clauses)
        )
    ).first()
    if taken is not None:
        raise ConflictError(
            code="ENROLLMENT_STUDENT_ALREADY_SEATED",
            message_key="enrollment.student_already_in_batch",
        )


def add_enrollment(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    display_name: str,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    guardian_phone: str | None = None,
    student_phone: str | None = None,
    fee_amount: Money | None = None,
    joined_on: dt.date | None = None,
) -> RosterRow:
    """Add a seat to one of this teacher's batches.

    **Returns the roster row, not the ORM record** [D2]. The seat a
    teacher has just added is the seat they are about to see on the
    roster, so both come from :func:`_roster_row` and cannot describe
    it differently -- the add response reporting ``pending`` while the
    roster computes ``absent`` for the same seat is the drift this
    removes rather than documents.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch to add to
    :param display_name: The teacher-typed name
    :param student_account_id: The student, or None for a dormant seat
    :param guardian_account_id: The guardian, if one is recorded
    :param guardian_phone: The teacher-typed guardian contact
    :param student_phone: The teacher-typed student number, canonical
    :param fee_amount: This seat's fee, or None to inherit
    :param joined_on: When the student joined
    :return: The new seat, as the roster describes it
    :raises BatchNotFound: The batch is not this lens's to write
    :raises ConflictError: That student already has a seat in the batch
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)

    student_account = student_account_id or _account_for(session, student_phone)
    _refuse_second_seat(
        session,
        batch_id=batch_id,
        student_phone=student_phone,
        student_account_id=student_account,
    )

    # **Link to a person who is ALREADY signed up** [BR5.1]. A number with
    # no account waits on the seat and links at sign-up instead. Before
    # this, a guardian who signed up first was never linked at all, and a
    # student could not be linked by any route.
    #
    # Linking is not agreeing: both decisions are stated `pending` below
    # whatever this finds, so the person is offered an invitation and
    # granted nothing. Nothing the teacher reads changes either -- the
    # roster reports decisions, not links -- so this reveals to no
    # teacher whether a number has an account.
    record = Enrollment(
        batch_id=batch_id,
        student_account_id=student_account_id or _account_for(session, student_phone),
        guardian_account_id=guardian_account_id
        or _account_for(session, guardian_phone),
        display_name=display_name,
        guardian_phone=guardian_phone,
        student_phone=student_phone,
        fee_amount=fee_amount,
        joined_on=joined_on,
        # STATED, because the columns carry no default [ADR-013]. A seat
        # a teacher creates is pending from creation whether or not the
        # number already has an account: naming someone is not their
        # agreement, which is the whole of BR5.1.
        student_decision="pending",
        guardian_decision="pending",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return _roster_row(record)


@dataclass(frozen=True, slots=True)
class BatchChanges:
    """What an edit names. ``None`` means leave it as it is.

    :ivar name: The teacher's name for the class
    :ivar subjects: The full list of subjects to keep, or None
    :ivar teacher_display_name: What students see the teacher called
    :ivar default_fee: The inherited fee, for cycles not yet generated
    :ivar fee_due_day: Day of month 1-31
    :ivar collection_number: Where payments are sent
    :ivar collection_channel: Which service that number belongs to
    :ivar marksheet_visible: U6's toggle
    :ivar active: False collapses the batch to read-only history
    """

    name: str | None = None
    subjects: list[str] | None = None
    teacher_display_name: str | None = None
    default_fee: Money | None = None
    fee_due_day: int | None = None
    collection_number: str | None = None
    collection_channel: str | None = None
    marksheet_visible: bool | None = None
    active: bool | None = None


def update_batch(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    changes: BatchChanges,
) -> BatchSummary:
    """Edit a batch this lens owns [AC2.3.1].

    **A fee change is forward-only.** A charge is a ledger entry written
    when its cycle generated, so a new ``default_fee`` reaches only the
    cycles generated after it; nothing already owed is rewritten.

    **Subjects are the full list to keep.** A name already present keeps
    its key, so sessions and exams naming it are untouched; a new name
    is added; a name left out is removed -- unless an exam was set in it,
    which refuses the whole edit, because the exam would lose what it
    was a test of. A class that named a removed subject keeps its record
    and loses only the subject label.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :param changes: What to change
    :return: The batch as the list describes it
    :raises BatchNotFound: No such batch, or another owner's
    :raises ValidationError: The subject list is empty
    :raises ConflictError: A subject to remove has an exam
    """
    batch = _owned_batch(session, lens=lens, batch_id=batch_id)
    if changes.subjects is not None:
        _replace_subjects(session, lens=lens, batch_id=batch.id, names=changes.subjects)

    for column in (
        "name",
        "teacher_display_name",
        "default_fee",
        "fee_due_day",
        "collection_number",
        "collection_channel",
        "marksheet_visible",
        "active",
    ):
        value = getattr(changes, column)
        if value is not None:
            setattr(batch, column, value)
    session.commit()

    return next(
        summary
        for summary in list_batches(session, lens=lens)
        if summary.batch.id == batch.id
    )


def _replace_subjects(
    session: Session, *, lens: TeacherLens, batch_id: uuid.UUID, names: list[str]
) -> None:
    """Make a batch's subjects exactly these names, keeping existing keys.

    Re-checks ownership itself rather than trusting its caller, so the
    write sweep in ``test_every_write_is_scoped.py`` sees it scoped.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch
    :param names: The subjects to keep
    :raises ValidationError: The list is empty
    :raises ConflictError: A subject to remove has an exam
    """
    batch_id = _owned_batch(session, lens=lens, batch_id=batch_id).id
    wanted = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    if not wanted:
        raise ValidationError(
            code="BATCH_NEEDS_A_SUBJECT",
            message_key="batch.create.subject_required",
        )
    existing = list(
        session.scalars(
            sa.select(BatchSubject).where(BatchSubject.batch_id == batch_id)
        )
    )
    dropped = [row for row in existing if row.name not in wanted]
    examined = session.scalar(
        sa.select(sa.func.count())
        .select_from(Exam)
        .where(Exam.batch_subject_id.in_([row.id for row in dropped]))
    )
    if dropped and examined:
        session.rollback()
        raise ConflictError(
            code="SUBJECT_HAS_EXAMS",
            message_key="batch.subject_in_use",
        )
    for row in dropped:
        session.delete(row)
    kept = {row.name for row in existing}
    session.add_all(
        BatchSubject(batch_id=batch_id, name=name)
        for name in wanted
        if name not in kept
    )
    session.flush()
