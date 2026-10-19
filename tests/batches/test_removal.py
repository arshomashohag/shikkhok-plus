"""Step 14 (RED): removal tests two conditions, not one [BR6.2, §B.1].

``student_account_id IS NULL`` means dormant. **After an erasure it is
true again**, because erasure is anonymize-in-place: the account link is
nulled and the seat reverts to looking unclaimed.

So a removal check reading the null column alone deletes the erased row
and destroys the marker that blocks reattachment -- and the erased number
silently reattaches on its next sign-in, which is the exact harm the
whole mechanism exists to prevent. The test that catches it needs an
erased seat in the fixture, which is why the fixture carries one.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import (
    BatchNotFound,
    EnrollmentNotRemovable,
    remove_enrollment,
)
from tests.batches.conftest import TeacherFixture, _account, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_a_dormant_never_claimed_seat_is_removed(
    restricted_session: Session, owner_session: Session
) -> None:
    """The only shape removal accepts.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enrollment_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Never signed in",
        student_account_id=None,
    )

    remove_enrollment(
        restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
    )

    from app.db.models import Enrollment

    assert restricted_session.get(Enrollment, enrollment_id) is None


def test_a_claimed_seat_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """A seat someone signed into keeps their history.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    student = _account(owner_session)
    enrollment_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Signed in",
        student_account_id=student,
    )

    with pytest.raises(EnrollmentNotRemovable):
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
        )


def test_an_erased_seat_is_refused_and_keeps_its_marker(
    restricted_session: Session, owner_session: Session
) -> None:
    """The test a null-only check fails.

    An erased seat has a NULL account again, so a check reading only
    that column deletes it -- taking the marker with it. The next time
    that phone number authenticates, dormant-resolution finds nothing
    blocking it and silently reattaches the person to a seat they
    explicitly erased.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.db.models import Enrollment

    teacher = make_teacher(owner_session)
    enrollment_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Erased by the student",
        student_account_id=None,
    )
    erased = owner_session.get(Enrollment, enrollment_id)
    assert erased is not None
    erased.student_relink_blocked_at = dt.datetime.now(tz=dt.UTC)
    owner_session.commit()

    with pytest.raises(EnrollmentNotRemovable):
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
        )

    restricted_session.expire_all()
    survivor = restricted_session.get(Enrollment, enrollment_id)
    assert survivor is not None
    assert survivor.student_relink_blocked_at is not None


def test_a_guardian_erasure_also_blocks_removal(
    restricted_session: Session, owner_session: Session
) -> None:
    """The guardian marker protects the row as the student's does.

    Both links erase independently [BR6.2], so a row carrying either
    marker holds a record of someone's erasure.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.db.models import Enrollment

    teacher = make_teacher(owner_session)
    enrollment_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Guardian erased",
        student_account_id=None,
    )
    record = owner_session.get(Enrollment, enrollment_id)
    assert record is not None
    record.guardian_relink_blocked_at = dt.datetime.now(tz=dt.UTC)
    owner_session.commit()

    with pytest.raises(EnrollmentNotRemovable):
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
        )


def test_the_refusal_names_which_condition_failed(
    restricted_session: Session, owner_session: Session
) -> None:
    """A claimed seat and an erased seat are refused for different reasons.

    The teacher's remedy differs: a claimed seat can be marked inactive,
    while an erased one cannot be reused at all. One message for both
    would send them down the wrong path.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from app.db.models import Enrollment

    teacher = make_teacher(owner_session)
    student = _account(owner_session)
    claimed = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Claimed",
        student_account_id=student,
    )
    erased_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Erased",
        student_account_id=None,
    )
    erased = owner_session.get(Enrollment, erased_id)
    assert erased is not None
    erased.student_relink_blocked_at = dt.datetime.now(tz=dt.UTC)
    owner_session.commit()

    with pytest.raises(EnrollmentNotRemovable) as claimed_error:
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=claimed
        )
    with pytest.raises(EnrollmentNotRemovable) as erased_error:
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=erased_id
        )

    # Asserted on the CODE, not on str(error). The code is what a client
    # switches on and what the error envelope carries; str() happens to
    # equal it today only because TaxonomyError passes the code to
    # Exception.__init__, which is a stringification detail this test
    # must not depend on.
    assert claimed_error.value.code == "ENROLLMENT_CLAIMED"
    assert erased_error.value.code == "ENROLLMENT_ERASED"
    assert claimed_error.value.message_key != erased_error.value.message_key


def test_an_unknown_enrollment_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """A seat that does not exist is refused, not silently ignored.

    A no-op return would report success for a removal that removed
    nothing, which is the shape that hides a wrong id from the caller.

    The refusal is a ``BatchNotFound`` rather than an enrollment-shaped
    error, and deliberately the SAME one another owner's seat gets: a
    distinct error for "does not exist" would tell a caller which
    enrollment ids are real.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    import uuid

    teacher = make_teacher(owner_session)

    with pytest.raises(BatchNotFound):
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=uuid.uuid4()
        )
