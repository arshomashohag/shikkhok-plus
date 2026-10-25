"""The next exam: today counts, yesterday does not [BR3.1-BR3.4].

Written before ``app/analytics/upcoming.py`` existed. An unscoped
``LIMIT 1`` returns **somebody's** soonest exam, which is an
authorization error, and the boundary cases are knowable from the rule
before any code -- so the test-first predicate holds.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.analytics.upcoming import next_exam
from tests.analytics.conftest import add_batch, add_exam, lens_for
from tests.batches.conftest import TeacherFixture

TODAY = dt.date(2027, 6, 15)


def test_an_exam_dated_today_is_upcoming(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The boundary, in the inclusive direction [BR3.1, BR3.2].

    ``>=`` rather than ``>``: an exam a teacher is about to sit is the
    one they most need to see, and reporting zero days is correct.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    add_exam(owner_session, batch_id=teacher.batch_id, title="Today", date=TODAY)

    found = next_exam(restricted_session, lens_for(teacher), today=TODAY)

    assert found is not None
    assert found.title == "Today"
    assert found.days_remaining == 0


def test_an_exam_dated_yesterday_is_not_upcoming(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The boundary, in the exclusive direction [BR3.1].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Yesterday",
        date=TODAY - dt.timedelta(days=1),
    )

    assert next_exam(restricted_session, lens_for(teacher), today=TODAY) is None


def test_days_remaining_is_zero_one_and_seven(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Whole days, computed server-side [BR3.2].

    Three separate teachers rather than three exams on one, because the
    soonest would otherwise mask the other two.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    from tests.batches.conftest import make_teacher

    for offset in (0, 1, 7):
        other = make_teacher(owner_session, name=f"Batch +{offset}")
        add_exam(
            owner_session,
            batch_id=other.batch_id,
            title=f"In {offset}",
            date=TODAY + dt.timedelta(days=offset),
        )
        found = next_exam(restricted_session, lens_for(other), today=TODAY)
        assert found is not None
        assert found.days_remaining == offset


def test_two_exams_on_one_date_resolve_by_created_at_and_stay_stable(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """The stated tiebreaker, and its repeatability [BR3.3].

    ``(date, created_at, exam_id)``. "Deterministic" with no key named
    is how two implementations disagree while both satisfying the
    criterion, and how one implementation disagrees with itself after a
    query-plan change -- so the key is asserted, and so is the fact that
    repeated reads agree.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Created second",
        date=TODAY + dt.timedelta(days=3),
        subject_name="Chemistry",
        created_at=dt.datetime(2027, 6, 2, 12, 0, tzinfo=dt.UTC),
    )
    add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Created first",
        date=TODAY + dt.timedelta(days=3),
        subject_name="Physics",
        created_at=dt.datetime(2027, 6, 1, 12, 0, tzinfo=dt.UTC),
    )

    first = next_exam(restricted_session, lens_for(teacher), today=TODAY)
    second = next_exam(restricted_session, lens_for(teacher), today=TODAY)

    assert first is not None
    assert first.title == "Created first"
    assert second is not None
    assert first.exam_id == second.exam_id


def test_no_upcoming_exam_is_an_absence_rather_than_a_failure(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """A teacher between terms gets nothing scheduled [BR3.4].

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    assert next_exam(restricted_session, lens_for(teacher), today=TODAY) is None


def test_the_exam_spans_every_owned_batch(
    owner_session: Session,
    restricted_session: Session,
    teacher: TeacherFixture,
) -> None:
    """Cross-batch, like every other figure in this unit [BR3.1].

    The sooner exam sits on the teacher's SECOND batch, so an
    implementation reading only one batch returns the later one.

    :param owner_session: A session able to arrange fixture data
    :param restricted_session: The session under test
    :param teacher: The teacher
    :return: None
    """
    second = add_batch(owner_session, teacher.owner_id, "Chemistry")
    add_exam(
        owner_session,
        batch_id=teacher.batch_id,
        title="Later, first batch",
        date=TODAY + dt.timedelta(days=20),
    )
    add_exam(
        owner_session,
        batch_id=second,
        title="Sooner, second batch",
        date=TODAY + dt.timedelta(days=4),
        subject_name="Chemistry",
    )

    found = next_exam(restricted_session, lens_for(teacher), today=TODAY)

    assert found is not None
    assert found.title == "Sooner, second batch"
    assert found.batch_name == "Chemistry"
    assert found.subject_name == "Chemistry"
