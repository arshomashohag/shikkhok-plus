"""Step 9: the roster reports both link states separately [BR2.1, BR2.2].

**Written from the criterion, not from the aggregate.** AC1.10.7 says a
seat held by two people shows both link states; § 1 of the functional
spec says a seat with no guardian reports ``absent``. Both were knowable
before the fields existed, and neither needs the implementation read to
know what to assert.

The case these exist for is the one the previous shape could not express
[functional-spec § 1]: a seat whose student accepted and whose guardian
declined is **not dormant**, carries no ``inactive_from``, and reported
a plain ``active`` -- losing exactly the distinction the roster has to
show. So each test below asserts the new fields **and** that ``status``
still answers what it always answered, because the two are different
axes and folding them together is what produced the gap.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import (
    EnrollmentNotRemovable,
    add_enrollment,
    list_roster,
    remove_enrollment,
)
from app.db.models import Account
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def _account(session: Session) -> uuid.UUID:
    """Create one account with a unique number.

    :param session: An arranging session
    :return: The new account's id
    """
    record = Account(
        phone=f"+88017{uuid.uuid4().int % 10**8:08d}",
        created_at=dt.datetime.now(tz=dt.UTC),
    )
    session.add(record)
    session.commit()
    return record.id


def test_a_seat_with_no_guardian_reports_absent_not_pending(
    restricted_session: Session, owner_session: Session
) -> None:
    """A decision nobody was asked for is not outstanding [BR2.2].

    ``absent`` is a fourth VALUE, not a null and not ``pending``.
    Reporting ``pending`` here would make the outstanding figure wrong
    by exactly the number of guardian-less seats.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="No guardian recorded",
        guardian_phone=None,
        student_decision="pending",
        guardian_decision="pending",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert rows[0].student_state == "pending"
    assert rows[0].guardian_state == "absent"


def test_a_recorded_guardian_who_has_not_answered_is_pending_not_absent(
    restricted_session: Session, owner_session: Session
) -> None:
    """The link is the teacher-typed number, not the account id [BR5.1].

    **The inversion this guards against is the expensive one.** A
    guardian the teacher recorded who has not signed up yet carries a
    number and a NULL account id; they were asked and have not answered,
    so they are pending. Keying absence on the account id would report
    every unregistered guardian as ``absent`` -- removing them from the
    outstanding figure, which is the opposite of what BR2.2 wants.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Guardian recorded, not signed up",
        guardian_phone="+8801711111111",
        student_decision="pending",
        guardian_decision="pending",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert rows[0].guardian_state == "pending"


def test_a_split_seat_returns_both_states_and_appears_once(
    restricted_session: Session, owner_session: Session
) -> None:
    """One row, two decisions, neither collapsed [BR2.1, AC1.10.7].

    **The case the previous shape could not express.** The student is
    enrolled and owes a fee; the guardian simply does not watch. Either
    single value for the seat is wrong, so the row carries both.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Student in, guardian out",
        guardian_account_id=_account(owner_session),
        guardian_phone="+8801722222222",
        student_decision="accepted",
        guardian_decision="declined",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert len(rows) == 1
    assert rows[0].student_state == "accepted"
    assert rows[0].guardian_state == "declined"


def test_a_split_seat_is_not_dormant_and_reports_active(
    restricted_session: Session, owner_session: Session
) -> None:
    """`status` keeps answering its own question [functional-spec § 1].

    The acceptance fields sit BESIDE ``status`` rather than replacing
    it. A split seat is genuinely not dormant -- a link accepted -- and
    has no ``inactive_from``, so ``active`` is the right answer on that
    axis. What was wrong before is that ``active`` was the ONLY answer.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Student in, guardian out",
        guardian_phone="+8801733333333",
        student_decision="accepted",
        guardian_decision="declined",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert rows[0].is_dormant is False
    assert rows[0].inactive_from is None
    assert rows[0].student_state == "accepted"
    assert rows[0].guardian_state == "declined"


def test_a_declined_seat_is_still_dormant_and_still_removable(
    restricted_session: Session, owner_session: Session
) -> None:
    """A decline is not an acceptance [BR7.2, AC2.5.1a].

    Nobody accepted, so the seat stays dormant and removable: re-adding
    the number creates a fresh seat the person is free to decline again.
    The roster's job is to show that it was DECLINED rather than merely
    unanswered, which is the per-row mark [BR1.1].

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Refused the seat",
        student_decision="declined",
        guardian_decision="declined",
    )

    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert rows[0].is_dormant is True
    assert rows[0].student_state == "declined"


def test_status_still_returns_each_of_its_three_values(
    restricted_session: Session, owner_session: Session
) -> None:
    """The existing axis is untouched by the new one.

    Arranged so each of ``dormant``, ``active`` and ``inactive`` is
    produced by a different seat, because a change that quietly
    collapsed two of them would still satisfy every per-seat assertion
    above.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="A nobody answered",
        student_decision="pending",
        guardian_decision="pending",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="B accepted and present",
        student_decision="accepted",
        guardian_decision="pending",
    )
    left_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="C accepted and left",
        student_decision="accepted",
        guardian_decision="pending",
    )
    from app.db.models import Enrollment

    left = owner_session.get(Enrollment, left_id)
    assert left is not None
    left.inactive_from = dt.date(2026, 1, 1)
    owner_session.commit()

    rows = {
        row.display_name: row
        for row in list_roster(
            restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
        )
    }

    assert rows["A nobody answered"].is_dormant is True
    assert rows["B accepted and present"].is_dormant is False
    assert rows["B accepted and present"].inactive_from is None
    assert rows["C accepted and left"].is_dormant is False
    assert rows["C accepted and left"].inactive_from == dt.date(2026, 1, 1)


def test_removability_agrees_with_what_removal_actually_does(
    restricted_session: Session, owner_session: Session
) -> None:
    """The row's answer and the write path's answer are the same [BR3.1].

    **This is the assertion the field exists for.** A roster offering
    removal on a seat the server then refuses is worse than one that
    never offered it, because the teacher has already decided by the
    time they learn. Three seats, one per outcome, and the erased one is
    the case a client derivation gets wrong: it looks exactly like a
    removable seat from the decisions alone.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="A nobody accepted",
        student_decision="pending",
        guardian_decision="pending",
    )
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="B accepted",
        student_decision="accepted",
        guardian_decision="pending",
    )
    erased_id = enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="C erased",
        student_decision="pending",
        guardian_decision="pending",
    )
    from app.db.models import Enrollment

    erased = owner_session.get(Enrollment, erased_id)
    assert erased is not None
    erased.student_relink_blocked_at = dt.datetime.now(tz=dt.UTC)
    owner_session.commit()

    rows = {
        row.display_name: row
        for row in list_roster(
            restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
        )
    }

    assert rows["A nobody accepted"].is_removable is True
    assert rows["B accepted"].is_removable is False
    # The erased seat's DECISIONS are both pending, so a derivation from
    # the displayed link states would say removable. It is not.
    assert rows["C erased"].student_state == "pending"
    assert rows["C erased"].guardian_state == "absent"
    assert rows["C erased"].is_removable is False

    for name, row in rows.items():
        try:
            remove_enrollment(
                restricted_session,
                lens=_lens(teacher),
                enrollment_id=row.enrollment_id,
            )
            actually_removable = True
        except EnrollmentNotRemovable:
            actually_removable = False
        assert actually_removable is row.is_removable, name


def test_a_newly_added_seat_is_pending_on_both_links(
    restricted_session: Session, owner_session: Session
) -> None:
    """W2: a seat a teacher creates is pending, never accepted [ADR-013].

    Asserted through ``add_enrollment`` rather than the fixture helper,
    because the service is the path a teacher actually takes and the
    helper deliberately follows the migration's backfill rule instead.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)

    row = add_enrollment(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        display_name="Just added",
        guardian_phone="+8801744444444",
    )

    assert row.student_state == "pending"
    assert row.guardian_state == "pending"
    assert row.is_dormant is True


def test_a_newly_added_seat_with_no_guardian_reports_absent(
    restricted_session: Session, owner_session: Session
) -> None:
    """The add response and the roster describe the seat identically.

    Both come from one builder, so this asserts the ABSENCE of the
    drift rather than the builder: an add response reporting ``pending``
    while the next roster read computed ``absent`` for the same seat
    would be two mappings disagreeing about one row.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)

    added = add_enrollment(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        display_name="No guardian at all",
    )
    rows = list_roster(
        restricted_session, lens=_lens(teacher), batch_id=teacher.batch_id
    )

    assert added.guardian_state == "absent"
    assert rows[0].guardian_state == added.guardian_state
    assert rows[0].student_state == added.student_state
