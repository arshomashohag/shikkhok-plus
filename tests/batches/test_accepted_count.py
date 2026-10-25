"""Step 2 (RED): the accepted count, written from the criterion [NFR23.4].

**Written before the aggregate exists**, and that ordering is the point.
AC1.3.5a says "how many seats have been **accepted** out of the total",
and BR1.4 says the total is every seat the teacher created, declined ones
included. Both are knowable without having written any SQL -- so writing
the test afterwards would let the aggregate define what the count means
rather than the criterion.

**Two definitions were available and only one is right.** A seat counts
as accepted when **at least one link** accepted it [BR1.2]: a student who
accepted is a student who joined, whatever the guardian did. The
alternative -- both links, or the student link alone -- would report a
split seat as not-joined, and a teacher reading that number would chase
someone who is already in the class.

**The denominator is the trap** [BR1.4]. Excluding declined seats makes
it shrink silently as people decline, so "9 of 12" becomes "9 of 11" with
nothing having been removed, and a teacher cannot tell a decline from a
removal. These tests arrange declined seats deliberately for that reason.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import list_batches
from app.db.models import Batch
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _second_batch(session: Session, *, owner_id: uuid.UUID) -> uuid.UUID:
    """Add a second batch under an existing owner.

    ``make_teacher`` creates a fresh owner each time, so it cannot
    arrange two batches one lens sees. This exists so the grouping
    assertion has two batches to confuse.

    :param session: An arranging session
    :param owner_id: The owner both batches hang from
    :return: The new batch's id
    """
    batch = Batch(
        owner_id=owner_id,
        name="Chemistry",
        marksheet_visible=True,
        active=True,
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(batch)
    session.commit()
    return batch.id


def test_a_batch_with_no_seats_counts_zero_of_zero(
    restricted_session: Session, owner_session: Session
) -> None:
    """A new batch reports the shape of the number before any seat exists.

    W1 renders the count from the first moment, so a teacher meets
    "0 of 0" rather than meeting the number later [functional-spec W1].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)

    summaries = list_batches(restricted_session, lens=_lens(teacher))

    assert len(summaries) == 1
    assert summaries[0].accepted_count == 0
    assert summaries[0].enrollment_count == 0


def test_one_accepted_link_makes_the_seat_accepted(
    restricted_session: Session, owner_session: Session
) -> None:
    """At least one accepted link counts the seat [BR1.2].

    The split seat is the discriminating case: student accepted,
    guardian declined. An implementation requiring BOTH links, or
    reading only ``student_decision``, gets a different answer here and
    the same answer on every seat where the two links agree.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Student in, guardian out",
        student_decision="accepted",
        guardian_decision="declined",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Guardian in, student out",
        student_decision="declined",
        guardian_decision="accepted",
    )

    summaries = list_batches(restricted_session, lens=_lens(teacher))

    assert summaries[0].accepted_count == 2
    assert summaries[0].enrollment_count == 2


def test_the_denominator_includes_declined_seats(
    restricted_session: Session, owner_session: Session
) -> None:
    """A declined seat is still a seat the teacher created [BR1.4].

    The arrangement is the worked example from AC1.3.5a's own wording:
    nine accepted out of twelve, where the three that are not accepted
    include a declined one. An implementation that filtered declined
    seats out of the total would report nine of eleven.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    for index in range(9):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Accepted {index}",
            student_decision="accepted",
            guardian_decision="pending",
        )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Refused the seat",
        student_decision="declined",
        guardian_decision="declined",
    )
    for index in range(2):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Unanswered {index}",
            student_decision="pending",
            guardian_decision="pending",
        )

    summaries = list_batches(restricted_session, lens=_lens(teacher))

    assert summaries[0].accepted_count == 9
    assert summaries[0].enrollment_count == 12


def test_a_batch_everyone_declined_counts_zero_of_its_seats(
    restricted_session: Session, owner_session: Session
) -> None:
    """Zero accepted, and the denominator does not collapse with it.

    The boundary that distinguishes a correct conditional aggregate from
    one whose numerator and denominator share a filter: both are zero
    only if the seats vanished from the total too.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    for index in range(3):
        enroll(
            owner_session,
            batch_id=teacher.batch_id,
            display_name=f"Declined {index}",
            student_decision="declined",
            guardian_decision="declined",
        )

    summaries = list_batches(restricted_session, lens=_lens(teacher))

    assert summaries[0].accepted_count == 0
    assert summaries[0].enrollment_count == 3


def test_counts_are_per_batch_and_do_not_leak_across_them(
    restricted_session: Session, owner_session: Session
) -> None:
    """One grouped statement must still group [NFR20.8].

    An aggregate that lost its ``GROUP BY``, or whose results were
    zipped onto the wrong batch, passes every single-batch test above.
    Two batches with deliberately different counts is what catches it.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    first = make_teacher(owner_session, name="Physics")
    second_batch_id = _second_batch(owner_session, owner_id=first.owner_id)

    enroll(
        owner_session,
        batch_id=first.batch_id,
        display_name="Physics accepted",
        student_decision="accepted",
        guardian_decision="pending",
    )
    enroll(
        owner_session,
        batch_id=first.batch_id,
        display_name="Physics pending",
        student_decision="pending",
        guardian_decision="pending",
    )
    enroll(
        owner_session,
        batch_id=second_batch_id,
        display_name="Chemistry declined",
        student_decision="declined",
        guardian_decision="declined",
    )

    summaries = {
        summary.batch.name: summary
        for summary in list_batches(restricted_session, lens=_lens(first))
    }

    assert summaries["Physics"].accepted_count == 1
    assert summaries["Physics"].enrollment_count == 2
    assert summaries["Chemistry"].accepted_count == 0
    assert summaries["Chemistry"].enrollment_count == 1
