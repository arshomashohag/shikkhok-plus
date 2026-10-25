"""The session roster, and the scope checks every D4 read shares.

**The lens is the scoping value, not a guard** [TC-11, D-2]. Every
function here takes a lens and derives its query from the value inside
it, so a caller cannot compile a scoped query without one.

**D4 adds no row-level-security policy, so these scope checks and the
adversarial probes against them ARE the mechanism** [NFR14.52]. The
built policy is on ``profile``, where ``account_id`` IS the subject;
none of D4's six tables has a column naming its READER. ``attendance``
is keyed by ``(session_id, enrollment_id)``, and reaching the reader
from a row requires joining enrollment to account and branching on
which of three lenses is asking -- which is the lens resolver's job and
not a policy predicate's. The revisit trigger is named in the
migration: any of these tables gaining a column identifying a reader
directly.

**Every pre-authorization refusal is the shared ``NOT_AVAILABLE``.** A
pair such as ``SESSION_NOT_FOUND`` / ``SESSION_NOT_YOURS`` is an
existence oracle even though each code reads as good practice alone: a
prober reads the difference and enumerates which ids are real.

**BR1.5's predicate is ONE indexed query with four clauses**, not a
filter applied after a broader read. A seat excluded by a Python
comprehension over a wider result set is a seat that was already
fetched, and the next function to reuse that fetch inherits the leak.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens
from app.db.models import Batch, Enrollment, Session
from app.errors import AuthorizationError
from app.errors.codes import NOT_AVAILABLE

__all__ = [
    "RosterSeat",
    "readable_enrollment",
    "readable_session",
    "refuse",
    "session_roster",
    "writable_session",
]


def refuse() -> AuthorizationError:
    """Build the one refusal every D4 scope check raises.

    A function rather than a constant so each raise site gets its own
    exception instance, and so there is exactly one place the code and
    message key are chosen. **One shared refusal path is also what
    makes the IDOR timing property structurally unlikely** rather than
    asserted: both the "no such thing" and the "not yours" cases reach
    the same raise before any resource-specific work happens
    [security-design § 2.3].

    :return: The shared refusal
    """
    return AuthorizationError(
        code=NOT_AVAILABLE,
        message_key="teaching.not_available",
    )


@dataclass(frozen=True, slots=True)
class RosterSeat:
    """One seat on a session's roster, as its teacher sees it.

    Carries the **enrollment id and never a global account key**
    [BR5.3, ADR-001]. A roster is the most natural place in the whole
    product to leak a student's identity to a teacher, because it is
    literally a list of people; the shape of this row is the mechanical
    half of the rule.

    :ivar enrollment_id: The teacher-facing key
    :ivar display_name: The TEACHER-typed name, never self-authored
    :ivar present: What was recorded, or None where nothing was
    """

    enrollment_id: uuid.UUID
    display_name: str
    present: bool | None


def readable_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
) -> Session:
    """Return a session this teacher lens reaches, or refuse.

    The scope is the batch's owner matching the lens's ``owner_id``
    [BR5.2, reader 2]. The refusal does not distinguish an invented id
    from another teacher's real one.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param session_id: The session being read
    :return: The session row
    :raises AuthorizationError: No batch this lens owns holds it
    """
    row = session.scalars(
        sa.select(Session)
        .join(Batch, Batch.id == Session.batch_id)
        .where(Session.id == session_id, Batch.owner_id == lens.owner_id)
    ).one_or_none()
    if row is None:
        raise refuse()
    return row


def writable_session(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
) -> Session:
    """Return a session this lens may WRITE to, or refuse.

    Authorization first, then the two state refusals [§ 5.4, § 5.6]:
    a write to a ``cancelled`` session [BR1.6] and any write to an
    ``inactive`` batch [BR5.5] are ``ConflictError`` rather than
    ``ValidationError``, because the request is well-formed and the
    CURRENT STATE is what forbids it -- which is the built class's own
    docstring.

    **The ordering is the security property.** Both state checks run
    only after the lens has been proved to reach the session, so
    neither can disclose the existence of a session to a stranger.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param session_id: The session being written
    :return: The session row
    :raises AuthorizationError: No batch this lens owns holds it
    :raises ConflictError: The session is cancelled, or its batch is
        inactive
    """
    from app.errors import ConflictError

    row = readable_session(session, lens=lens, session_id=session_id)

    if row.status == "cancelled":
        raise ConflictError(
            code="SESSION_CANCELLED",
            message_key="teaching.session.cancelled",
        )

    active = session.scalars(
        sa.select(Batch.active).where(Batch.id == row.batch_id)
    ).one()
    if not active:
        raise ConflictError(
            code="BATCH_INACTIVE",
            message_key="teaching.batch.inactive",
        )
    return row


def readable_enrollment(
    session: DbSession,
    *,
    lens: Lens,
    enrollment_id: uuid.UUID,
) -> Enrollment:
    """Return an enrollment this lens reaches, or refuse.

    **The three branches are the three readers BR5.2 names**, and each
    reads its OWN decision column. This project recorded on 2026-10-22
    that adding a column is not adding a behaviour and that the queries
    which must start reading it have to be named: a guardian branch
    that checked only ``guardian_account_id`` would hand a lens to
    someone a teacher named and who never agreed.

    :param session: The session to read through
    :param lens: The lens asking
    :param enrollment_id: The seat being read
    :return: The enrollment row
    :raises AuthorizationError: This lens does not reach that seat
    """
    record = session.get(Enrollment, enrollment_id)
    if record is None:
        raise refuse()

    if isinstance(lens, TeacherLens):
        owned = session.scalars(
            sa.select(Batch.id).where(
                Batch.id == record.batch_id, Batch.owner_id == lens.owner_id
            )
        ).one_or_none()
        if owned is None:
            raise refuse()
        return record

    if isinstance(lens, StudentLens):
        if (
            record.student_account_id == lens.account_id
            and record.student_decision == "accepted"
        ):
            return record
        raise refuse()

    if isinstance(lens, GuardianLens):
        if (
            record.guardian_account_id == lens.account_id
            and record.guardian_decision == "accepted"
        ):
            return record
        raise refuse()

    raise refuse()


def roster_predicate(session_date: dt.date) -> sa.ColumnElement[bool]:
    """Build BR1.5's four-clause membership predicate.

    Returned as a predicate rather than applied inline so the roster
    read and the attendance write share ONE definition: a write that
    accepted a seat the read never showed would record attendance
    against a student who is not in the class.

    The clauses, each with the failure it prevents:

    * ``inactive_from IS NULL OR inactive_from > D`` -- a student who
      left in March must not appear on an April roster and be marked
      absent every week;
    * ``student_decision <> 'declined'`` -- a seat someone declined,
      the mistyped-digit case, must stop appearing to be marked. Note
      this is **not** ``= 'accepted'``: pending is the normal state of
      a new seat and a teacher must be able to mark it;
    * ``joined_on IS NULL OR joined_on <= D`` -- a seat is never
      recorded against a class it could not have attended.

    :param session_date: The date the session falls on
    :return: The predicate, for a query already joined to enrollment
    """
    return sa.and_(
        sa.or_(
            Enrollment.inactive_from.is_(None),
            Enrollment.inactive_from > session_date,
        ),
        Enrollment.student_decision != "declined",
        sa.or_(
            Enrollment.joined_on.is_(None),
            Enrollment.joined_on <= session_date,
        ),
    )


def session_roster(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
) -> list[RosterSeat]:
    """List the seats on one session's roster [BR1.5, BR5.2 reader 1].

    **A seat with no attendance row carries ``present = None``**, which
    is a different fact from ``False``: nothing has been recorded yet.
    AC3.1.4 defaults every seat to present in the UI and the teacher
    marks only exceptions, so an unsubmitted roster is an ABSENT row
    rather than a false one -- and collapsing the two here would tell a
    guardian their child was marked absent from a class nobody has
    marked at all.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param session_id: The session whose roster to build
    :return: One row per seat, ordered by the teacher-typed name
    :raises AuthorizationError: This lens does not reach that session
    """
    from app.db.models import Attendance

    row = readable_session(session, lens=lens, session_id=session_id)

    rows = session.execute(
        sa.select(
            Enrollment.id,
            Enrollment.display_name,
            Attendance.present,
        )
        .select_from(Enrollment)
        .outerjoin(
            Attendance,
            sa.and_(
                Attendance.enrollment_id == Enrollment.id,
                Attendance.session_id == row.id,
            ),
        )
        .where(
            Enrollment.batch_id == row.batch_id,
            roster_predicate(row.date),
        )
        .order_by(Enrollment.display_name, Enrollment.id)
    ).all()

    return [
        RosterSeat(
            enrollment_id=entry[0],
            display_name=entry[1],
            present=entry[2],
        )
        for entry in rows
    ]
