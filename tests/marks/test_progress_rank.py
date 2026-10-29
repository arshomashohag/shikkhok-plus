"""A student's results carry the subject and, where published, the rank.

**Written before the fields existed.** S2 reads "Weekly test 4 ·
তাপগতিবিদ্যা · 12 Oct · rank 5 of 19". The rank is a disclosure: it is
sent only where the exam's marksheet would publish its comparison --
enough marked results and marking complete [BR6.4] -- the same rule the
marksheet itself applies, so the two cannot disagree. Otherwise the rank
is null and the screen shows the mark alone.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session as DbSession

from app.authz.lenses import StudentLens, TeacherLens
from app.marks.entry import record_mark
from app.marks.views import guardian_progress
from tests.marks.conftest import TOTAL_MARKS


def _mark_all(
    session: DbSession,
    lens: TeacherLens,
    exam: uuid.UUID,
    marks: dict[uuid.UUID, int],
) -> None:
    """Record a mark for each seat.

    :param session: The session to write through
    :param lens: The teacher
    :param exam: The exam
    :param marks: Seat to mark
    :return: None
    """
    for seat, value in marks.items():
        record_mark(
            session,
            lens=lens,
            exam_id=exam,
            enrollment_id=seat,
            result_state="marked",
            marks=value,
        )


def test_a_published_exam_gives_the_rank_and_the_subject(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Six marked, the viewer second highest: rank 2 of 6.

    :param restricted_session: The application-role session
    :param teacher_lens: The batch's owner
    :param exam: One exam out of 100 on the batch
    :param seat_factory: Makes seats
    :param account_factory: Makes accounts
    :return: None
    """
    viewer = account_factory()
    mine = seat_factory("Viewer", student_account_id=viewer)
    others = [seat_factory(f"S{i}") for i in range(5)]
    _mark_all(
        restricted_session,
        teacher_lens,
        exam,
        {mine: 90, **dict(zip(others, [95, 80, 70, 60, 50], strict=True))},
    )

    [entry] = guardian_progress(
        restricted_session, lens=StudentLens(account_id=viewer), enrollment_id=mine
    )

    assert (entry.marks, entry.rank, entry.ranked_out_of) == (90, 2, 6)
    assert entry.subject_name == "Physics"
    assert entry.total_marks == TOTAL_MARKS


def test_too_few_results_give_no_rank(
    restricted_session: DbSession,
    teacher_lens: TeacherLens,
    exam: uuid.UUID,
    seat_factory: Callable[..., uuid.UUID],
    account_factory: Callable[[], uuid.UUID],
) -> None:
    """Three marked is below the disclosure floor: the mark, no rank.

    :param restricted_session: The application-role session
    :param teacher_lens: The batch's owner
    :param exam: One exam out of 100 on the batch
    :param seat_factory: Makes seats
    :param account_factory: Makes accounts
    :return: None
    """
    viewer = account_factory()
    mine = seat_factory("Viewer", student_account_id=viewer)
    others = [seat_factory(f"S{i}") for i in range(2)]
    _mark_all(
        restricted_session,
        teacher_lens,
        exam,
        {mine: 90, **dict(zip(others, [95, 80], strict=True))},
    )

    [entry] = guardian_progress(
        restricted_session, lens=StudentLens(account_id=viewer), enrollment_id=mine
    )

    assert (entry.marks, entry.rank, entry.ranked_out_of) == (90, None, None)
