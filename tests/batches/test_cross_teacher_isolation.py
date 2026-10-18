"""Step 12 (RED): the leak itself, not the mechanism [NFR14.14].

**This is the test B3 could not write.** U3 had one account and no second
party, so every isolation claim it made was about a mechanism -- a lens
exists, a dependency is declared -- rather than about an outcome. The
first Unit with two teachers in it is the first that can assert the thing
the project actually cares about: one teacher's roster never shows
another teacher's row.

The predicate is authorization and the correct output is knowable from
the requirement, so ``team.md``'s ordering puts these first.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import BatchNotFound, list_roster
from tests.batches.conftest import TeacherFixture, enroll, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_each_roster_shows_only_its_own_teachers_rows(
    restricted_session: Session, two_teachers: tuple[TeacherFixture, ...]
) -> None:
    """The shared student appears once per teacher, under that teacher's name.

    Both teachers enrolled the **same account**, so a query that scoped
    on the student rather than on the owner would return both rows to
    both teachers and still look correct in a single-teacher test.

    :param restricted_session: A session as the application role
    :param two_teachers: Two teachers sharing one student account
    :return: None
    """
    first, second = two_teachers

    first_roster = list_roster(
        restricted_session, lens=_lens(first), batch_id=first.batch_id
    )
    second_roster = list_roster(
        restricted_session, lens=_lens(second), batch_id=second.batch_id
    )

    assert [row.display_name for row in first_roster] == ["Rahim (physics)"]
    assert [row.display_name for row in second_roster] == ["Rahim (chemistry)"]


def test_another_owners_batch_is_not_found(
    restricted_session: Session, two_teachers: tuple[TeacherFixture, ...]
) -> None:
    """A teacher reading another's batch gets a not-found, never its rows.

    :param restricted_session: A session as the application role
    :param two_teachers: Two teachers sharing one student account
    :return: None
    """
    first, second = two_teachers

    with pytest.raises(BatchNotFound):
        list_roster(restricted_session, lens=_lens(first), batch_id=second.batch_id)


def test_the_refusal_does_not_confirm_the_batch_exists(
    restricted_session: Session, two_teachers: tuple[TeacherFixture, ...]
) -> None:
    """A real batch and an invented one are refused identically [NFR14.13].

    A 403 for one and a 404 for the other is an existence oracle: it
    tells an attacker which batch ids are real, which is exactly what the
    404 choice exists to prevent.

    :param restricted_session: A session as the application role
    :param two_teachers: Two teachers sharing one student account
    :return: None
    """
    import uuid

    first, second = two_teachers

    with pytest.raises(BatchNotFound) as real:
        list_roster(restricted_session, lens=_lens(first), batch_id=second.batch_id)
    with pytest.raises(BatchNotFound) as invented:
        list_roster(restricted_session, lens=_lens(first), batch_id=uuid.uuid4())

    assert type(real.value) is type(invented.value)
    assert str(real.value) == str(invented.value)


def test_the_roster_is_scoped_by_the_lens_not_by_a_parameter(
    restricted_session: Session, owner_session: Session
) -> None:
    """A forged owner id in the lens reaches only that owner's batches.

    The scoping value lives **inside** the lens object [TC-11], so there
    is no separate parameter to forge. This test pins that the service
    reads it from there: given a lens for teacher A and a batch of
    teacher B, nothing is returned no matter what else is passed.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session, name="Maths")
    intruder = make_teacher(owner_session, name="Biology")
    enroll(
        owner_session,
        batch_id=teacher.batch_id,
        display_name="Only in Maths",
        student_account_id=None,
    )

    # The intruder's own lens, pointed at someone else's batch.
    with pytest.raises(BatchNotFound):
        list_roster(restricted_session, lens=_lens(intruder), batch_id=teacher.batch_id)
