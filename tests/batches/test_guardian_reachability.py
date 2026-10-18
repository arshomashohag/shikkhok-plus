"""Step 13 (RED): a guardian reaches seats, not children [NFR14.15].

**Two rules both satisfy the happy path and only one is correct.** The
wrong one resolves a guardian's view by finding their children and then
showing every enrollment of those children; the right one reads
``guardian_account_id`` directly [BR5.3].

The difference appears only when the same child is enrolled with two
teachers and only one of them recorded this guardian -- which is why the
pair of tests below matters more than either alone. The child-keyed
implementation passes the first and fails the second.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.authz.lenses import GuardianLens
from app.batches.service import list_guardian_children
from tests.batches.conftest import enroll, make_teacher


def test_a_guardian_reaches_the_seat_they_were_recorded_on(
    restricted_session: Session, owner_session: Session
) -> None:
    """The recorded guardian sees the child's enrollment.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.batches.conftest import _account

    teacher = make_teacher(owner_session, name="Physics")
    child = _account(owner_session)
    guardian = _account(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=child,
        guardian_account_id=guardian,
    )

    children = list_guardian_children(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=None),
    )

    assert [row.display_name for row in children] == ["Rahim"]


def test_a_guardian_does_not_reach_a_teacher_who_did_not_record_them(
    restricted_session: Session, owner_session: Session
) -> None:
    """The same child, two teachers, one recorded guardian.

    **This is the test that separates the two rules.** Resolving by
    "find this guardian's children, then show every enrollment of those
    children" merges two teachers' records: the guardian would see the
    second teacher's batch for the same child, which is a cross-teacher
    leak dressed as a convenience.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.batches.conftest import _account

    recorded = make_teacher(owner_session, name="Physics")
    other = make_teacher(owner_session, name="Chemistry")
    child = _account(owner_session)
    guardian = _account(owner_session)

    enroll(
        owner_session,
        batch_id=recorded.batch_id,
        display_name="Rahim (physics)",
        student_account_id=child,
        guardian_account_id=guardian,
    )
    # The SAME child, with a different teacher, who recorded no guardian.
    enroll(
        owner_session,
        batch_id=other.batch_id,
        display_name="Rahim (chemistry)",
        student_account_id=child,
        guardian_account_id=None,
    )

    children = list_guardian_children(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=None),
    )

    assert [row.display_name for row in children] == ["Rahim (physics)"]


def test_the_list_returns_distinct_children_not_enrollments(
    restricted_session: Session, owner_session: Session
) -> None:
    """One child in three of a teacher's batches is one child.

    The cardinality is a requirement, not a detail: a guardian with one
    child enrolled in three subjects should see one child, not three.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.batches.conftest import _account

    teacher = make_teacher(owner_session, name="Physics")
    second_batch = make_teacher(owner_session, name="Chemistry")
    child = _account(owner_session)
    guardian = _account(owner_session)

    for batch_id in (teacher.batch_id, second_batch.batch_id):
        enroll(
            owner_session,
            batch_id=batch_id,
            display_name="Rahim",
            student_account_id=child,
            guardian_account_id=guardian,
        )

    children = list_guardian_children(
        restricted_session,
        lens=GuardianLens(account_id=guardian, child_enrollment_id=None),
    )

    assert len({row.student_account_id for row in children}) == 1


def test_a_guardian_with_no_recorded_seat_reaches_nothing(
    restricted_session: Session, owner_session: Session
) -> None:
    """An account nobody recorded as a guardian sees an empty list.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    from tests.batches.conftest import _account

    teacher = make_teacher(owner_session, name="Physics")
    child = _account(owner_session)
    stranger = _account(owner_session)
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Rahim",
        student_account_id=child,
    )

    children = list_guardian_children(
        restricted_session,
        lens=GuardianLens(account_id=stranger, child_enrollment_id=None),
    )

    assert children == []
