"""The queued write paths: the unit's centre of gravity.

**There are two of them -- the roster and the topic log -- and they
follow the same sequence under the same rules** [BR2.1, BR3.3-BR3.8,
§ B.7]. Both are composed on a device, both carry a ``base_version``
and a ``client_mutation_id``, and both are replayed when a flaky send
is retried. A topic write with no replay check re-executes on exactly
the path NFR5 built the queue for -- double-applying, or being refused
as stale -- so the replay store serves both, distinguished by ``kind``.

``kind`` is in ``UNIQUE (session_id, kind, resulting_version)`` and
deliberately NOT in ``UNIQUE (submitted_by_account_id,
client_mutation_id)``. The version counters are separate, so without
``kind`` a topic write reaching topic version N+1 would collide with
the roster write that reached attendance version N+1 on the same
session. The mutation id is unique per account whatever path it
arrived on, so the same id on the other path is still the same client
decision and is still a replay.

**The whole module is one sequence, and the ORDER is the security
property** [security-design § 5.4, BR3.10]:

1. **Resolve the lens.** If it does not reach the session, refuse with
   the shared ``NOT_AVAILABLE`` **before any version is compared**.
2. **Replay check**, scoped by ``(submitted_by_account_id,
   client_mutation_id)`` -- BOTH columns.
3. **State checks**: a cancelled session or an inactive batch.
4. **The conditional update**, one statement.
5. **Apply**, in ONE transaction.

Step 1 is first because ``ATTENDANCE_VERSION_CONFLICT`` carries
``current_state`` in ``error.details`` and **``current_state`` IS the
roster**. Emitting it before the authorization check would hand a
stranger the class's attendance in an error body.

Step 2 is scoped by both columns because the uniqueness is per
ACCOUNT [§ B.7], so account B presenting account A's id is **not a
duplicate at all**. A lookup on ``client_mutation_id`` alone finds
A's row and returns it -- which § 5.2 names as the implementation
everybody reaches for and which ships as a silent success. It is
**not** scoped by ``kind``, for the same reason: one account's
mutation id is one client decision whatever endpoint it reaches, so
presenting it on the other path is refused rather than answered with
a version from the wrong counter.

**The mechanism in step 4 is a conditional update, not a lock.**

    UPDATE session SET attendance_version = :base + 1
     WHERE id = :id AND attendance_version = :base

**Zero rows affected means someone else won.** That single statement is
both the check and the write, so no window exists between them. A
pessimistic lock is the wrong tool for this path specifically: the
contender is not a concurrent request but a STALE one, composed hours
earlier on a phone with no connectivity, and there is no transaction to
hold open across that gap [BR3.3, ADR-006].

**No new error class** [NFR19.35]. ``ConflictError``'s built docstring
already states this semantic exactly: *"Valid request; current state
forbids it. Refetch and decide. Retrying as-is is wrong."*
``retryable`` is false because retryability is a property of the class
read in one place -- a raise site cannot set it, and this one does not
try.

**The conflict is never logged with its roster** [NFR24.15]. The
conflict is interesting, so it will be logged; the error body already
carries the roster; and the obvious implementation logs the error body.
The log line here carries the session id and the two version numbers
and nothing else.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import TeacherLens
from app.db.models import Attendance, Enrollment, QueuedSubmission, Session
from app.errors import ConflictError
from app.teaching.roster import roster_predicate, writable_session

__all__ = [
    "ATTENDANCE_KIND",
    "ATTENDANCE_VERSION_CONFLICT",
    "TOPIC_KIND",
    "TOPIC_VERSION_CONFLICT",
    "SeatMark",
    "SubmissionResult",
    "TopicResult",
    "submit_roster",
    "write_topic",
]

log = logging.getLogger(__name__)

#: The descriptive conflict code [BR3.10]. Permitted by the oracle rule
#: in ``app/errors/codes.py`` because it is reached ONLY after
#: authorization: it creates no code pair distinguishing "does not
#: exist" from "you may not reach this", and the built registry test
#: cannot catch an individually-disclosing 409 -- which is why the
#: ordering above is the real control.
ATTENDANCE_VERSION_CONFLICT = "ATTENDANCE_VERSION_CONFLICT"

#: The same mechanism on the other queued path [BR2.1]. A SEPARATE
#: counter, because one shared counter would refuse a topic log
#: because a roster arrived -- a conflict the teacher cannot act on,
#: since there is nothing to compare and nothing to re-apply
#: differently.
TOPIC_VERSION_CONFLICT = "TOPIC_VERSION_CONFLICT"

#: The two values of ``queued_submission.kind``. Named here rather
#: than written as literals at the three call sites, so a typo is an
#: import error rather than a row the replay lookup never matches.
ATTENDANCE_KIND = "attendance"
TOPIC_KIND = "topic"


def _rows_affected(result: object) -> int:
    """Return how many rows a DML statement touched.

    **``rowcount`` is the whole conflict mechanism**, and
    ``Session.execute`` is annotated to return the generic ``Result``,
    which does not carry it -- only ``CursorResult`` does. This is the
    first DML in the backend to read it.

    Written as a CHECKED narrow rather than a ``cast``: a cast would
    assert the property while this proves it, and if SQLAlchemy ever
    returned something else for an UPDATE the failure would be a loud
    ``TypeError`` here rather than a silent ``AttributeError`` inside
    the guarded write.

    :param result: What ``Session.execute`` returned for an UPDATE
    :return: The number of rows the statement matched
    :raises TypeError: The result carries no row count
    """
    if not isinstance(result, CursorResult):
        raise TypeError(
            f"an UPDATE returned {type(result).__name__}, which carries "
            "no rowcount. The conditional update's zero-rows branch is "
            "the whole conflict mechanism [BR3.3]."
        )
    count: int = result.rowcount
    return count


@dataclass(frozen=True, slots=True)
class SeatMark:
    """One seat's presence, as the client submitted it.

    :ivar enrollment_id: The seat
    :ivar present: Whether the student attended
    """

    enrollment_id: uuid.UUID
    present: bool


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """What an accepted or replayed write produced.

    ``replayed`` is **server-side vocabulary and not a queue state**
    [BR3.9]: the four queue states are client-side and appear in no
    response schema, because the server cannot know whether an item is
    queued on a device it has never heard from.

    :ivar attendance_version: The version now in force
    :ivar submission_id: The accepted write's row
    :ivar replayed: True when this returned a stored result unchanged
    """

    attendance_version: int
    submission_id: uuid.UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class TopicResult:
    """What an accepted or replayed topic write produced.

    The topic log's counterpart to :class:`SubmissionResult`, and it
    exists for the same reason: a caller cannot tell an accepted write
    from a replayed one by the version alone, because a replay returns
    the ORIGINAL version and that is exactly what a fresh write would
    have returned had it been the first.

    :ivar topic_version: The version now in force
    :ivar submission_id: The accepted write's row
    :ivar replayed: True when this returned a stored result unchanged
    """

    topic_version: int
    submission_id: uuid.UUID
    replayed: bool


def _existing_submission(
    session: DbSession,
    *,
    account_id: uuid.UUID,
    client_mutation_id: uuid.UUID,
    kind: str,
) -> QueuedSubmission | None:
    """Find this ACCOUNT's prior submission under this mutation id.

    **Scoped by both columns of the constraint.** A lookup on
    ``client_mutation_id`` alone would find another account's row and
    return it -- a silent success, and the shape § 5.2 names
    explicitly.

    ``kind`` is **not** part of the lookup, because the uniqueness is
    not either: the same account cannot hold two rows under one
    mutation id whatever path they came from, so a row found under the
    other kind is the same client decision replayed onto the wrong
    endpoint. That is a conflict rather than a replay -- returning a
    topic version where a roster version was asked for would be a
    silent wrong answer -- so it is refused here.

    :param session: The session to read through
    :param account_id: The authenticated account
    :param client_mutation_id: The client's replay key
    :param kind: Which queued path is asking
    :return: The prior submission of this kind, or None
    :raises ConflictError: The id was already spent on the other path
    """
    prior = session.scalars(
        sa.select(QueuedSubmission).where(
            QueuedSubmission.submitted_by_account_id == account_id,
            QueuedSubmission.client_mutation_id == client_mutation_id,
        )
    ).one_or_none()

    if prior is not None and prior.kind != kind:
        raise ConflictError(
            code="MUTATION_ID_ALREADY_USED",
            message_key="teaching.mutation_id.already_used",
            details={"expected_kind": kind, "stored_kind": prior.kind},
        )
    return prior


def _conflict(
    session: DbSession,
    *,
    row: Session,
    base_version: int,
) -> ConflictError:
    """Build the version conflict, carrying the current state.

    Reached **only after authorization** has succeeded, which is what
    makes carrying ``current_state`` permissible at all.

    :param session: The session to read the current roster through
    :param row: The session whose version did not match
    :param base_version: What the client composed against
    :return: The conflict, with its details
    """
    current = session.scalars(
        sa.select(Session.attendance_version).where(Session.id == row.id)
    ).one()
    marks = session.execute(
        sa.select(Attendance.enrollment_id, Attendance.present).where(
            Attendance.session_id == row.id
        )
    ).all()

    # LOGGED WITHOUT THE ROSTER [NFR24.15]. The conflict is
    # interesting, so it will be logged; the error body already carries
    # the roster; and the obvious implementation logs the error body.
    log.info(
        "attendance roster refused on a version conflict",
        extra={
            "session_id": str(row.id),
            "expected_version": base_version,
            "current_version": current,
        },
    )

    return ConflictError(
        code=ATTENDANCE_VERSION_CONFLICT,
        message_key="error.attendance_version_conflict",
        details={
            "expected_version": str(base_version),
            "current_version": str(current),
            "current_state": ",".join(
                f"{entry[0]}:{'present' if entry[1] else 'absent'}"
                for entry in sorted(marks, key=lambda entry: str(entry[0]))
            ),
        },
    )


def _assert_seats_are_on_the_roster(
    session: DbSession,
    *,
    row: Session,
    seats: list[SeatMark],
) -> None:
    """Refuse a roster naming a seat the read would not show [BR1.5].

    The write must accept exactly the seats the roster read returns. A
    write that accepted a declined seat would record attendance
    against a student who is not in the class, and the correction
    history would then faithfully record it -- which is worse than no
    history, because it looks authoritative.

    :param session: The session to read through
    :param row: The session being written
    :param seats: What the client submitted
    :raises ConflictError: A named seat is not on this roster
    """
    if not seats:
        return

    allowed = set(
        session.scalars(
            sa.select(Enrollment.id).where(
                Enrollment.batch_id == row.batch_id,
                roster_predicate(row.date),
            )
        ).all()
    )
    unknown = {mark.enrollment_id for mark in seats} - allowed
    if unknown:
        # The COUNT, not the ids: an enrollment id in a log line is
        # permitted [§ 1.1], but a refusal message is rendered to a
        # client and the ids add nothing it does not already hold.
        raise ConflictError(
            code="SEAT_NOT_ON_ROSTER",
            message_key="teaching.seat.not_on_roster",
            details={"unknown_seats": str(len(unknown))},
        )


def submit_roster(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    base_version: int,
    client_mutation_id: uuid.UUID,
    seats: list[SeatMark],
    composed_at: dt.datetime | None = None,
) -> SubmissionResult:
    """Apply one roster write, or refuse it [BR3.3-BR3.8].

    The sequence is the module docstring's five steps, in that order.

    :param session: The session to work through
    :param lens: The teacher lens; authorization runs FIRST
    :param session_id: The session whose roster this is
    :param base_version: The ``attendance_version`` it was composed
        against
    :param client_mutation_id: The client's replay key
    :param seats: One mark per seat, the whole roster at once
    :param composed_at: The device's clock, recorded and never read in
        a decision [NFR24.20]
    :return: The version now in force, and whether this was a replay
    :raises AuthorizationError: This lens does not reach the session
    :raises ConflictError: The session is cancelled, its batch is
        inactive, a seat is not on the roster, or the version is stale
    """
    # 1. AUTHORIZATION, and the state checks that follow it. Before
    #    any version is compared, and before any replay is looked up.
    row = writable_session(session, lens=lens, session_id=session_id)

    # 2. REPLAY, scoped by BOTH columns.
    prior = _existing_submission(
        session,
        account_id=lens.account_id,
        client_mutation_id=client_mutation_id,
        kind=ATTENDANCE_KIND,
    )
    if prior is not None:
        # The ORIGINAL stored result, with nothing written and
        # `created_at` untouched -- which is what makes a replay
        # observably a replay [§ 5.3].
        return SubmissionResult(
            attendance_version=prior.resulting_version,
            submission_id=prior.id,
            replayed=True,
        )

    _assert_seats_are_on_the_roster(session, row=row, seats=seats)

    # 4. THE GUARDED WRITE, in one statement. Zero rows affected means
    #    someone else won; the check and the write are one statement,
    #    so no window exists between them.
    updated = _rows_affected(
        session.execute(
            sa.update(Session)
            .where(
                Session.id == session_id,
                Session.attendance_version == base_version,
            )
            .values(attendance_version=base_version + 1, status="held")
        )
    )

    if updated == 0:
        session.rollback()
        raise _conflict(session, row=row, base_version=base_version)

    # 5. APPLY, in the SAME transaction. If any part fails, none of it
    #    is applied [BR3.5] -- not k-1 rows, zero.
    submission = QueuedSubmission(
        session_id=session_id,
        kind=ATTENDANCE_KIND,
        submitted_by_account_id=lens.account_id,
        client_mutation_id=client_mutation_id,
        base_version=base_version,
        resulting_version=base_version + 1,
        composed_at=composed_at,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(submission)
    session.flush()

    recorded = dt.datetime.now(tz=dt.UTC)
    for mark in seats:
        # Upsert on (session_id, enrollment_id): a re-submission
        # REPLACES rather than appends [BR3.5].
        session.execute(
            pg_insert(Attendance)
            .values(
                id=uuid.uuid4(),
                session_id=session_id,
                enrollment_id=mark.enrollment_id,
                present=mark.present,
                recorded_at=recorded,
                recorded_by_account_id=lens.account_id,
                submission_id=submission.id,
            )
            .on_conflict_do_update(
                constraint="uq_attendance_session_enrollment",
                set_={
                    "present": mark.present,
                    "recorded_at": recorded,
                    "recorded_by_account_id": lens.account_id,
                    "submission_id": submission.id,
                },
            )
        )

    session.commit()
    return SubmissionResult(
        attendance_version=base_version + 1,
        submission_id=submission.id,
        replayed=False,
    )


def write_topic(
    session: DbSession,
    *,
    lens: TeacherLens,
    session_id: uuid.UUID,
    base_version: int,
    client_mutation_id: uuid.UUID,
    topic: str,
    composed_at: dt.datetime | None = None,
) -> TopicResult:
    """Write a session's topic, against its OWN version [BR2.1].

    **The same five-step sequence as the roster**, in the same order,
    against ``topic_version`` rather than ``attendance_version``. The
    two counters are separate because the paths touch disjoint
    columns: one shared counter would refuse a topic log because a
    roster arrived from another device, which is a conflict the
    teacher cannot act on.

    **The replay check is not optional here.** This is the second
    queued path, composed on the same mid-class screen and resent by
    the same queue after a flaky send; without it a retried topic
    write re-executes -- double-applying, or being refused as stale
    for a change the teacher already made. The submission row it
    writes carries ``kind='topic'`` so its version cannot collide with
    the roster write that reached the same number.

    **An empty string is a topic logged as blank, and is a different
    fact from NULL** [BR2.2]. Collapsing the two makes it impossible to
    tell a class nobody logged from one logged as nothing, which is the
    whole content of AC3.4.2's "topics covered in each".

    :param session: The session to work through
    :param lens: The teacher lens; authorization runs FIRST
    :param session_id: The session being written
    :param base_version: The ``topic_version`` it was composed against
    :param client_mutation_id: The client's replay key
    :param topic: What was covered; '' means logged-and-blank
    :param composed_at: The device's clock, recorded and never read in
        a decision [NFR24.20]
    :return: The version now in force, and whether this was a replay
    :raises AuthorizationError: This lens does not reach the session
    :raises ConflictError: The session is cancelled, its batch is
        inactive, the mutation id was spent on the other queued path,
        or the version is stale
    """
    # 1. AUTHORIZATION, and the state checks that follow it. Before
    #    any version is compared, and before any replay is looked up
    #    [§ 5.4].
    writable_session(session, lens=lens, session_id=session_id)

    # 2. REPLAY, scoped by BOTH columns of the constraint.
    prior = _existing_submission(
        session,
        account_id=lens.account_id,
        client_mutation_id=client_mutation_id,
        kind=TOPIC_KIND,
    )
    if prior is not None:
        # The ORIGINAL stored result, with nothing written and
        # `created_at` untouched [§ 5.3].
        return TopicResult(
            topic_version=prior.resulting_version,
            submission_id=prior.id,
            replayed=True,
        )

    updated = _rows_affected(
        session.execute(
            sa.update(Session)
            .where(
                Session.id == session_id,
                Session.topic_version == base_version,
            )
            .values(
                topic=topic,
                topic_version=base_version + 1,
                status="held",
            )
        )
    )

    if updated == 0:
        session.rollback()
        current = session.scalars(
            sa.select(Session.topic_version).where(Session.id == session_id)
        ).one()
        # No `current_state` here: the topic is one teacher-authored
        # string rather than a roster, so the conflict can carry what
        # the record now says without disclosing a child's data.
        raise ConflictError(
            code=TOPIC_VERSION_CONFLICT,
            message_key="error.topic_version_conflict",
            details={
                "expected_version": str(base_version),
                "current_version": str(current),
            },
        )

    # 5. APPLY, in the SAME transaction as the guarded update. The
    #    submission row is what makes the next resend of this write a
    #    replay rather than a second application.
    submission = QueuedSubmission(
        session_id=session_id,
        kind=TOPIC_KIND,
        submitted_by_account_id=lens.account_id,
        client_mutation_id=client_mutation_id,
        base_version=base_version,
        resulting_version=base_version + 1,
        composed_at=composed_at,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(submission)
    session.flush()

    session.commit()
    return TopicResult(
        topic_version=base_version + 1,
        submission_id=submission.id,
        replayed=False,
    )
