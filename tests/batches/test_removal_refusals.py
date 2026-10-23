"""Step 3 (RED): the two refusals are a PAIR, not one failure [NFR23.5].

**A test asserting "removal is refused" passes for both cases and
distinguishes neither**, which is why this file exists separately from
``test_removal.py``. That file asserts each refusal fires on the right
shape of seat; these assert the two are **telling the teacher different
things**, because the remedies differ [BR3.2]:

* ``ENROLLMENT_CLAIMED`` -- somebody accepted, so mark the seat inactive
  instead and the record stands [FR1.9i, ADR-003];
* ``ENROLLMENT_ERASED`` -- the account was erased, so the seat cannot be
  reused at all.

A screen showing one message for both leaves a teacher trying the remedy
that cannot work, and D2 is the unit where that difference first reaches
a person.

**Partly green against built code, deliberately.** ``remove_enrollment``
already raises both codes. What was never asserted is that the two carry
**different message keys** -- the half a screen actually renders -- and
that neither invites a retry. A pair that converged on one key would
satisfy every merged test in this directory.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import EnrollmentNotRemovable, remove_enrollment
from app.db.models import Enrollment
from app.errors import ConflictError
from app.errors.handler import to_response
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _claimed_seat(session: Session, *, batch_id: uuid.UUID) -> uuid.UUID:
    """Arrange a seat whose student link accepted.

    :param session: An arranging session
    :param batch_id: The batch to seat them in
    :return: The enrollment id
    """
    return enroll(
        session,
        batch_id=batch_id,
        display_name="Accepted the seat",
        student_decision="accepted",
        guardian_decision="pending",
    )


def _erased_seat(session: Session, *, batch_id: uuid.UUID) -> uuid.UUID:
    """Arrange a seat nobody accepted whose holder erased their account.

    **The marker is set directly**, and that is marked rather than
    quiet: no service path in D2's scope sets an erasure marker, so
    going through one is not available. After erasure the link is NULL
    again and both decisions are back to ``pending``, which is exactly
    the shape that makes this seat look removable to a check reading
    acceptance alone [BR6.2].

    :param session: An arranging session
    :param batch_id: The batch to seat them in
    :return: The enrollment id
    """
    enrollment_id = enroll(
        session,
        batch_id=batch_id,
        display_name="Left and erased",
        student_decision="pending",
        guardian_decision="pending",
    )
    record = session.get(Enrollment, enrollment_id)
    assert record is not None
    record.student_relink_blocked_at = dt.datetime.now(tz=dt.UTC)
    session.commit()
    return enrollment_id


def test_the_two_refusals_carry_different_codes_and_message_keys(
    restricted_session: Session, owner_session: Session
) -> None:
    """The pair is distinguishable on both halves a screen reads.

    **This is the assertion the unit exists for.** The code is what the
    client switches on; the message key is what it renders. A pair
    agreeing on either one collapses two remedies into one screen, and
    only asserting them together catches it.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    claimed = _claimed_seat(owner_session, batch_id=teacher.batch_id)
    erased = _erased_seat(owner_session, batch_id=teacher.batch_id)

    with pytest.raises(EnrollmentNotRemovable) as claimed_refusal:
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=claimed
        )
    with pytest.raises(EnrollmentNotRemovable) as erased_refusal:
        remove_enrollment(restricted_session, lens=_lens(teacher), enrollment_id=erased)

    assert claimed_refusal.value.code == "ENROLLMENT_CLAIMED"
    assert erased_refusal.value.code == "ENROLLMENT_ERASED"
    assert claimed_refusal.value.code != erased_refusal.value.code
    assert claimed_refusal.value.message_key != erased_refusal.value.message_key


def test_the_claimed_refusal_names_the_inactive_remedy(
    restricted_session: Session, owner_session: Session
) -> None:
    """A claimed seat's key is the one whose remedy is marking inactive.

    The key is asserted by name because it is the contract the client
    resolves against, and ``message-keys.json`` publishes it: a rename
    on either surface must break something.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    claimed = _claimed_seat(owner_session, batch_id=teacher.batch_id)

    with pytest.raises(EnrollmentNotRemovable) as refusal:
        remove_enrollment(
            restricted_session, lens=_lens(teacher), enrollment_id=claimed
        )

    assert refusal.value.message_key == "enrollment.remove.claimed"


def test_the_erased_refusal_names_the_cannot_reuse_remedy(
    restricted_session: Session, owner_session: Session
) -> None:
    """An erased seat's key is the one whose remedy is that there is none.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    erased = _erased_seat(owner_session, batch_id=teacher.batch_id)

    with pytest.raises(EnrollmentNotRemovable) as refusal:
        remove_enrollment(restricted_session, lens=_lens(teacher), enrollment_id=erased)

    assert refusal.value.message_key == "enrollment.remove.erased"


def test_neither_refusal_invites_a_retry(
    restricted_session: Session, owner_session: Session
) -> None:
    """Retryability is a property of the error CLASS [team: Error handling].

    Both refusals are ``ConflictError``: the request was well-formed and
    the state forbids it, so repeating it unchanged cannot succeed.
    Asserted because the screen reads ``retryable`` from the envelope
    rather than deciding, so a refusal that arrived retryable would put
    a retry button on a wall.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    claimed = _claimed_seat(owner_session, batch_id=teacher.batch_id)
    erased = _erased_seat(owner_session, batch_id=teacher.batch_id)

    for enrollment_id in (claimed, erased):
        with pytest.raises(EnrollmentNotRemovable) as refusal:
            remove_enrollment(
                restricted_session, lens=_lens(teacher), enrollment_id=enrollment_id
            )

        assert isinstance(refusal.value, ConflictError)
        envelope = json.loads(bytes(to_response(refusal.value).body))
        assert envelope["error"]["retryable"] is False
