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
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens, TeacherLens
from app.db.models import Batch, BatchSubject, Enrollment
from app.errors import AuthorizationError, ConflictError, ValidationError
from app.money import Money

__all__ = [
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
    "remove_enrollment",
    "set_inactive_from",
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
    :ivar is_dormant: True while nobody has signed in to this seat
    :ivar inactive_from: The date after which no cycle generates
    """

    enrollment_id: uuid.UUID
    display_name: str
    is_dormant: bool
    inactive_from: dt.date | None


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

    return [
        RosterRow(
            enrollment_id=row.id,
            display_name=row.display_name,
            is_dormant=row.student_account_id is None,
            inactive_from=row.inactive_from,
        )
        for row in rows
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

    :param session: The session to query through
    :param lens: The guardian lens carrying the authenticated account
    :return: One row per reachable seat, ordered by batch then name
    """
    rows = session.execute(
        sa.select(Enrollment, Batch.name)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Enrollment.guardian_account_id == lens.account_id)
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


def remove_enrollment(session: Session, *, enrollment_id: uuid.UUID) -> None:
    """Delete a seat, if it is both dormant and never erased.

    **Two conditions, and the second is the one that gets forgotten.**
    After an erasure ``student_account_id`` is NULL again, so a check
    reading only that column deletes the erased row -- destroying the
    marker that stops the number reattaching on its next sign-in, which
    is the harm the marker exists to prevent [BR6.2, §B.1].

    :param session: The session to write through
    :param enrollment_id: The seat to remove
    :return: None
    :raises EnrollmentNotRemovable: The seat is claimed or was erased
    """
    record = session.get(Enrollment, enrollment_id)
    if record is None:
        raise EnrollmentNotRemovable(
            code="ENROLLMENT_NOT_FOUND",
            message_key="enrollment.not_found",
        )

    if record.student_account_id is not None:
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
    enrollment_id: uuid.UUID,
    inactive_from: dt.date | None,
) -> None:
    """Record, or clear, the date after which no cycle generates.

    Written **per enrollment**, never per student: one person in two of
    a teacher's batches is two seats [AC2.2.3], and leaving one class
    does not leave the other. U7 reads this; U4 only records it.

    :param session: The session to write through
    :param enrollment_id: The seat to mark
    :param inactive_from: The date, or None to reactivate the seat
    :return: None
    :raises EnrollmentNotRemovable: No such enrollment
    """
    record = session.get(Enrollment, enrollment_id)
    if record is None:
        raise EnrollmentNotRemovable(
            code="ENROLLMENT_NOT_FOUND",
            message_key="enrollment.not_found",
        )

    record.inactive_from = inactive_from
    session.commit()


@dataclass(frozen=True, slots=True)
class BatchSummary:
    """A batch and its seat count, as its owner sees it.

    :ivar batch: The batch row
    :ivar subjects: The subjects taught
    :ivar enrollment_count: How many seats, computed server-side
    """

    batch: Batch
    subjects: list[str]
    enrollment_count: int


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
) -> Batch:
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
    :return: The new batch
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

    for subject in subjects:
        session.add(BatchSubject(batch_id=batch.id, name=subject))
    session.commit()
    return batch


def list_batches(session: Session, *, lens: TeacherLens) -> list[BatchSummary]:
    """List this teacher's batches with their seat counts.

    **The counts come from one grouped query, not one query per batch.**
    The roster's query-count property applies here for the same reason:
    a per-batch count is the N+1 shape with a different name.

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
    counts = dict(
        session.execute(
            sa.select(Enrollment.batch_id, sa.func.count(Enrollment.id))
            .where(Enrollment.batch_id.in_(batch_ids))
            .group_by(Enrollment.batch_id)
        ).all()
    )
    subjects: dict[uuid.UUID, list[str]] = {batch_id: [] for batch_id in batch_ids}
    for batch_id, subject_name in session.execute(
        sa.select(BatchSubject.batch_id, BatchSubject.name)
        .where(BatchSubject.batch_id.in_(batch_ids))
        .order_by(BatchSubject.name)
    ).all():
        subjects[batch_id].append(subject_name)

    return [
        BatchSummary(
            batch=batch,
            subjects=subjects[batch.id],
            enrollment_count=counts.get(batch.id, 0),
        )
        for batch in batches
    ]


def add_enrollment(
    session: Session,
    *,
    lens: TeacherLens,
    batch_id: uuid.UUID,
    display_name: str,
    student_account_id: uuid.UUID | None = None,
    guardian_account_id: uuid.UUID | None = None,
    guardian_phone: str | None = None,
    fee_amount: Money | None = None,
    joined_on: dt.date | None = None,
) -> Enrollment:
    """Add a seat to one of this teacher's batches.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param batch_id: The batch to add to
    :param display_name: The teacher-typed name
    :param student_account_id: The student, or None for a dormant seat
    :param guardian_account_id: The guardian, if one is recorded
    :param guardian_phone: The teacher-typed guardian contact
    :param fee_amount: This seat's fee, or None to inherit
    :param joined_on: When the student joined
    :return: The new enrollment
    :raises BatchNotFound: The batch is not this lens's to write
    """
    _owned_batch(session, lens=lens, batch_id=batch_id)

    record = Enrollment(
        batch_id=batch_id,
        student_account_id=student_account_id,
        guardian_account_id=guardian_account_id,
        display_name=display_name,
        guardian_phone=guardian_phone,
        fee_amount=fee_amount,
        joined_on=joined_on,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record
