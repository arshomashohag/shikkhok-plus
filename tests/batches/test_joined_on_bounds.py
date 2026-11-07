"""A seat's start date is bounded, so a typo cannot back-bill years.

Fee generation walks every month from ``joined_on`` to today and charges
each one [audit C-24]. Nothing bounded the date: typing 2006 for 2026
created about 240 cycles at the current fee on the next run, each one a
due the teacher would have to waive by hand. And ``inactive_from`` could
fall before the seat even started.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.authz.lenses import TeacherLens
from app.batches.service import add_enrollment, set_inactive_from
from app.errors import ValidationError
from app.local_time import bangladesh_today
from tests.batches.conftest import TeacherFixture, make_teacher


def _lens(teacher: TeacherFixture) -> TeacherLens:
    """Build the lens the service requires.

    :param teacher: The teacher to build a lens for
    :return: That teacher's lens
    """
    return TeacherLens(account_id=teacher.account_id, owner_id=teacher.owner_id)


def test_a_start_date_years_ago_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """The typo the audit found: 2006 for 2026.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    today = bangladesh_today()

    with pytest.raises(ValidationError) as refusal:
        add_enrollment(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            display_name="Typo",
            joined_on=today.replace(year=today.year - 20),
        )
    assert refusal.value.code == "JOINED_ON_OUT_OF_RANGE"


def test_a_start_date_far_in_the_future_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """A start a year away is a typo too.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)

    with pytest.raises(ValidationError):
        add_enrollment(
            restricted_session,
            lens=_lens(teacher),
            batch_id=teacher.batch_id,
            display_name="Far",
            joined_on=bangladesh_today() + dt.timedelta(days=400),
        )


def test_a_start_date_a_few_months_back_is_kept(
    restricted_session: Session, owner_session: Session
) -> None:
    """Recording a student who joined last term still works.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    joined = bangladesh_today() - dt.timedelta(days=90)

    row = add_enrollment(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        display_name="Last term",
        joined_on=joined,
    )
    assert row.enrollment_id is not None


def test_leaving_before_joining_is_refused(
    restricted_session: Session, owner_session: Session
) -> None:
    """An end date before the start date describes no seat.

    :param restricted_session: A session as the application role
    :param owner_session: A session able to arrange fixture data
    :return: None
    """
    teacher = make_teacher(owner_session)
    joined = bangladesh_today() - dt.timedelta(days=30)
    row = add_enrollment(
        restricted_session,
        lens=_lens(teacher),
        batch_id=teacher.batch_id,
        display_name="Left early",
        joined_on=joined,
    )

    with pytest.raises(ValidationError) as refusal:
        set_inactive_from(
            restricted_session,
            lens=_lens(teacher),
            enrollment_id=row.enrollment_id,
            inactive_from=joined - dt.timedelta(days=1),
        )
    assert refusal.value.code == "INACTIVE_BEFORE_JOINED"
